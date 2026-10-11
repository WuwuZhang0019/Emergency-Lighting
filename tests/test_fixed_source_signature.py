"""Exact typed freshness regression for log19; no native CAD acceptance. Date: 2026-10-11."""
import copy
from pathlib import Path
import unittest
from autolisp_host import Pair, Symbol, truth
import test_diagram_store as db
import test_diagram_update as update
import test_post_stat_workflow as workflow

ROOT = Path(__file__).resolve().parents[1]
def pair(key, value): return Pair(Symbol(key.upper()), value)

class FixedSourceSignatureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = db.StoreTests()
        self.fixture.setUp()
        self.h = self.fixture.h
        self.h.load_definitions(ROOT/'src/panel.lsp')
        self.h.load_definitions(ROOT/'src/geometry.lsp')
        self.events=[]
        self.h.builtins['EL:LOGEVENT']=lambda *args:self.events.append(args)
        # A realistic long snapshot: many individually bounded wire RAW strings.
        self.source=[pair('drawing','drawing-guid'), pair('wires',[
            [pair('id',str(i)),pair('segments',[[[float(i),2.0,0.0],[float(i)+1,3.0,0.0]]]),
             pair('raw','(LWPOLYLINE 中文图层 width50) '*100)] for i in range(111)]),
            pair('blocks',[[pair('id','B'),pair('name','灯具'),pair('bounds',[[0.,0.,0.],[1.,1.,0.]])]])]
        self.assertGreater(len(db.dump(self.source).encode('gb2312')),305127)
        self.h.frames[0]['CFG']=[pair('drawing','drawing-guid')]
        self.h.frames[0]['SOURCE']=self.source
        self.h.run("(setq baseline (EL:CircuitSnapshot source \"panel\") result (list (cons 'drawing \"drawing-guid\") (cons 'rules (EL:RecognitionRules cfg)) (cons 'snapshot baseline)))")

    def call(self,name,*args): return self.h.call(Symbol(name.upper()),list(args))
    def get(self,key,value): return self.call('EL:Get',Symbol(key.upper()),value)

    def test_no_large_printer_call_and_repeated_freshness_passes(self):
        def bounded_printer(value):
            text=db.dump(value)
            if len(text)>10000: raise RuntimeError('large VL-PRIN1-TO-STRING is forbidden')
            return text
        self.h.builtins['VL-PRIN1-TO-STRING']=bounded_printer
        self.h.run('(setq fresh (EL:CircuitSnapshot source "panel"))')
        signature=self.h.run("(EL:Get 'signature fresh)")
        self.assertEqual(signature[0],Symbol('EL_FIXED_SOURCE_V1'))
        self.assertTrue(truth(self.h.run('(EL:SourceCurrent result cfg fresh)')))
        self.assertEqual(self.events,[])

    def test_exact_changes_still_fail_and_log_bounded_leaf_evidence(self):
        def bounded_printer(value):
            text=db.dump(value)
            if len(text)>10000: raise RuntimeError('diagnostics must not print whole source lists')
            return text
        self.h.builtins['VL-PRIN1-TO-STRING']=bounded_printer
        for change in ('tiny-coordinate','raw','delete-block','drawing','rules'):
            with self.subTest(change=change):
                source=copy.deepcopy(self.source)
                if change=='tiny-coordinate': source[1].cdr[0][1].cdr[0][0][0]=1.e-15
                if change=='raw': source[1].cdr[0][2]=pair('raw',source[1].cdr[0][2].cdr+' changed')
                if change=='delete-block': source[2]=pair('blocks',[])
                self.h.frames[0]['CHANGED']=source
                self.h.run('(setq fresh (EL:CircuitSnapshot changed "panel"))')
                cfg=self.h.lookup('CFG')
                if change=='drawing': cfg=self.call('EL:Put',Symbol('DRAWING'),'different',cfg)
                if change=='rules': cfg=self.call('EL:Put',Symbol('WIRE-LAYERS'),['different'],cfg)
                self.events.clear()
                self.assertFalse(truth(self.call('EL:SourceCurrent',self.h.lookup('RESULT'),cfg,self.h.lookup('FRESH'))))
                for stage,data in self.events:
                    self.assertLess(len(db.dump(data)),2000)
                if change in ('tiny-coordinate','raw','delete-block'):
                    diff=next(data for stage,data in self.events if stage=='SOURCE_FIELD_DIFFERENCE' and self.get('field',data)==Symbol('SIGNATURE'))
                    self.assertTrue(self.get('path',self.get('difference',diff)))

    def test_native_dxf_roundtrip_preserves_typed_signature(self):
        self.h.run("(setq record (list '(diagram-id . \"d1\") '(source-panel-handle . \"panel\") (cons 'source-signature (EL:Get 'signature baseline))))")
        self.assertTrue(truth(self.h.run('(EL:StoreWrite (EL:StorePutDiagram record (EL:StoreInitial)))')))
        self.assertTrue(truth(self.h.run('(equal record (EL:DiagramForPanel "panel" (EL:StoreRead)))')))

class FixedSourceMigrationTests(unittest.TestCase):
    def test_old_record_upgrades_then_noop_keeps_output_handles(self):
        f=update.UpdateTests();f.setUp();f.install_sync()
        f.h.run("(setq record (EL:Put 'source-signature \"old printed signature\" record)) (EL:StoreWrite (EL:StorePutDiagram record store))")
        f.h.run("(setq result (EL:Put 'snapshot (EL:CircuitSnapshot '((drawing . \"fixture\") (wires)) \"source\") result))")
        old=f.h.run("(EL:Get 'panel-output-handle record)")
        self.assertTrue(truth(f.h.run("(EL:SyncDiagram result nil nil 'cap300 T nil)")))
        f.h.run('(setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertEqual(f.h.run("(car (EL:Get 'source-signature reopened))"),Symbol('EL_FIXED_SOURCE_V1'))
        self.assertEqual(old,f.h.run("(EL:Get 'panel-output-handle reopened)"))
        before=copy.deepcopy(f.entities)
        self.assertTrue(truth(f.h.run("(EL:SyncDiagram result nil nil 'cap300 T nil)")))
        self.assertEqual(f.entities,before)

class RejectionAlertTimingTests(unittest.TestCase):
    def test_actual_command_alerts_count_as_user_wait(self):
        for path in ('source-changed','no-devices'):
            with self.subTest(path=path):
                f=workflow.PostStatWorkflowTests();f.setUp()
                clock=[0]; reports=[]; alerts=[]
                original=f.h.builtins['GETVAR']
                def alert(text): alerts.append(text);clock[0]+=5000
                f.h.builtins.update({'GETVAR':lambda key:clock[0] if key=='MILLISECS' else original(key),
                    'EL:PERFREPORT':reports.append,'ALERT':alert})
                f.call('EL:PerfStart','ELSTAT')
                if path=='no-devices':
                    f.call('EL:PickedDevicesReady',None)
                else:
                    f.h.builtins.update({'EL:FRESHRESULT':lambda *a:None,'EL:MARKSTALE':lambda *a:None,
                        'EL:REMEMBERPANELPOWERS':lambda *a:True,'EL:SAVENAMEPOWERS':lambda *a:True})
                    f.actions=[lambda:f.done(1)]
                    f.call('EL:EditPanelOnce',f.result,f.cfg)
                clock[0]+=20
                f.call('EL:PerfFinish',Symbol('COMMAND-FINISHED'))
                self.assertEqual(len(alerts),1)
                self.assertEqual(f.get('interaction-ms',reports[0]),5000)
                self.assertEqual(f.get('program-ms',reports[0]),20)
