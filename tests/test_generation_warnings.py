"""Date: 2026-10-23. Status: warning-only explicit generation; finite CAD adapters."""
import copy
import json
from pathlib import Path
import unittest
from autolisp_host import Pair, Symbol, cons, truth
import test_cckk_panel_command as native
from test_cckk_assembly import field

ROOT = Path(__file__).resolve().parents[1]
HOTEL = json.loads((ROOT/'tests/fixtures/hotel-generation-number-warning-20261022.json').read_text(encoding='utf-8'))


class GenerationWarningTests(unittest.TestCase):
    def fixture(self):
        f = native.PanelCommandTests(); f.setUp(); f.two_circuits()
        f.h.builtins['ALERT'] = lambda *args: self.fail('Generate must not show a modal alert')
        f.events = []
        f.h.builtins['EL:LOGEVENT'] = lambda *args: f.events.append(args)
        return f

    def put(self, f, key, value, row):
        return f.call('EL:Put', Symbol(key.upper()), value, row)

    def hotel(self, f):
        rows, inputs = [], []
        base = f.get('circuits', f.h.lookup('RESULT'))[0]
        for i, item in enumerate(HOTEL['circuits'], 1):
            c = copy.deepcopy(base)
            for key, value in {'id':item['id'], 'circuit-uid':'hotel-'+item['id'],
                'seed-key':item['start'], 'seed':[Pair(Symbol('KEY'), item['start'])],
                'output-order':i,'complete':True,'watts':item['watts'],'power-complete':True}.items():
                c = self.put(f, key, value, c)
            scope = [Pair(Symbol('STATUS'), Symbol('READY')),
                     cons(Symbol('SOURCES'), [x['handle'] for x in item['inputs']])]
            c = self.put(f, 'number-scope', scope, c)
            for x in item['inputs']:
                inputs.append([Pair(Symbol('HANDLE'),x['handle']),
                    Pair(Symbol('STATUS'),Symbol('READY' if x['values'] else 'MISSING')),
                    cons(Symbol('VALUES'),x['values'] or None)])
            rows.append(c)
        result = self.put(f, 'number-policy-version', 1, self.put(f, 'number-inputs', inputs,
                  self.put(f, 'circuits', rows, f.h.lookup('RESULT'))))
        expected={f.get('handle',row):row for row in inputs}
        f.h.builtins['EL:READWIRENUMBERDATA']=lambda handle:expected.get(handle)
        result = f.call('EL:ResolveCircuitNumbers', result)
        return self.put(f, 'can-generate', None, result)

    def click(self, f, result):
        f.h.set('*EL:PANELDRAFT*',result)
        f.h.set('*EL:PANELCAPACITY*',Symbol('CAP300'))
        f.h.set('*EL:PANELTEMPLATEREADY*',True)
        closed=[];f.h.builtins['EL:PANELCLOSE']=closed.append
        f.call('EL:PanelGenerateBody')
        self.assertEqual(closed,[2])
        self.assertEqual(f.h.lookup('*EL:PANELACTION*'),Symbol('GENERATE'))
        return f.h.lookup('*EL:PANELDRAFT*')

    def test_reported_number_conflicts_do_not_block_button_or_native_output(self):
        f=self.fixture();result=self.hotel(f)
        source=copy.deepcopy(f.get('number-inputs',result))
        self.assertEqual([f.get('number-status',c) for c in f.get('circuits',result)],
                         [Symbol('CONFLICT'),Symbol('READY'),Symbol('CONFLICT'),Symbol('READY'),Symbol('READY')])
        result=self.click(f,result)
        f.h.set('RESULT',result)
        self.assertTrue(truth(f.invoke()))
        record=f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        actual=f.get('rows',record)[:5]
        self.assertEqual([f.get('watts',r) for r in actual],[23,48,3,68,90])
        self.assertEqual([f.get('circuit-number',r) for r in actual],
                         ['待核对-R1','ZE1','待核对-R3','ZE2','ZE4'])
        self.assertEqual(f.get('status',record),Symbol('STALE'))
        self.assertEqual(f.get('number-inputs',record),source)
        for row, candidates in ((actual[0],['ZE3','4ALE(JZ)-ZE3']), (actual[2],['ZE5','4ALE(JZ)-ZE5'])):
            self.assertEqual(f.get('number-status',row),Symbol('CONFLICT'))
            self.assertEqual(f.get('candidates',f.get('number-evidence',row)),candidates)
        self.assertIn('GENERATION_WITH_WARNINGS',[event[0] for event in f.events])
        self.assertEqual(len(f.commands),8)  # Five actual rows, two reserve rows and panel.

    def test_connection_and_unknown_power_warn_and_keep_all_rows_without_fake_zero(self):
        f=self.fixture();result=self.hotel(f)
        rows=f.get('circuits',result)
        issue=[Pair(Symbol('CODE'),Symbol('OTHER_PANEL')),Pair(Symbol('OBJECT'),'BOX2')]
        rows[0]=self.put(f,'issues',[issue],rows[0])
        rows[1]=self.put(f,'watts',None,self.put(f,'power-complete',None,rows[1]))
        result=self.click(f,self.put(f,'circuits',rows,result))
        f.h.set('RESULT',result)
        self.assertTrue(truth(f.invoke()))
        record=f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        rows=f.get('rows',record)
        self.assertEqual([f.get('watts',r) for r in rows[:5]],[None,None,3,68,90])
        self.assertEqual(len(rows),7)
        self.assertTrue(all(f.get('block-handle',r) for r in rows))
        self.assertIsNone(f.get('text-handle',rows[0]));self.assertIsNone(f.get('text-handle',rows[1]))

    def test_changed_library_and_number_sources_use_displayed_snapshot_with_warning(self):
        f=self.fixture();result=self.click(f,self.hotel(f))
        f.h.set('RESULT',result)
        f.h.builtins['EL:DLSUBMISSIONCURRENT']=lambda *args: None
        f.h.builtins['EL:NUMBERINPUTSCURRENT']=lambda *args: None
        f.h.builtins['EL:FRESHRESULT']=lambda *args: None
        self.assertTrue(truth(f.invoke()))
        record=f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual(f.get('status',record),Symbol('STALE'))
        warnings=[detail for event,detail in f.events if event=='GENERATION_REVIEW_WARNING']
        self.assertTrue(warnings)
        self.assertEqual([f.get('watts',r) for r in f.get('rows',record)[:5]],[23,48,3,68,90])

    def test_unsaved_library_form_is_retained_and_does_not_cancel_generate(self):
        f=self.fixture();result=self.hotel(f)
        f.h.set('*EL:PANELDRAFT*',result)
        f.h.set('*EL:PANELTEMPLATEREADY*',True)
        f.h.set('*EL:PANELCAPACITY*',Symbol('CAP300'))
        f.h.set('*EL:DLUISTATE*',[Pair(Symbol('DRAFTS'),[['raw watts','1.5']])])
        f.h.builtins['EL:PANELLIBRARYFLUSH']=lambda: None
        closed=[];f.h.builtins['EL:PANELCLOSE']=closed.append
        before=copy.deepcopy(f.h.lookup('*EL:DLUISTATE*'))
        f.call('EL:PanelGenerate')
        self.assertEqual(closed,[2])
        self.assertEqual(f.h.lookup('*EL:DLUISTATE*'),before)

    def test_write_failure_rolls_back_and_keeps_input_without_modal_dialog(self):
        f=self.fixture();result=self.click(f,self.hotel(f));f.h.set('RESULT',result)
        before=copy.deepcopy(f.entities);f.fail_at=3
        self.assertFalse(truth(f.invoke()))
        self.assertEqual(f.entities,before)
        self.assertEqual(f.get('number-inputs',f.h.lookup('RESULT')),f.get('number-inputs',result))

    def test_real_panel_submit_and_native_placement_keep_all_five_circuits(self):
        f=self.fixture();result=self.put(f,'engine',Symbol('FIXED'),self.hotel(f));cfg=f.h.lookup('CFG')
        def dialog(value,config,powers,capacity):
            value=self.click(f,value)
            return [Pair(Symbol('RESULT'),value),Pair(Symbol('CONFIG'),config),
                    Pair(Symbol('CAPACITY'),Symbol('CAP300')),Pair(Symbol('GENERATE'),True)]
        f.h.builtins.update({'EL:PANELDIALOG':dialog,'EL:DLSNAPSHOT':lambda:None,
            'EL:DLPREPARE':lambda r,p,*args:[Pair(Symbol('RESULT'),r),Pair(Symbol('POWERS'),p)],
            'EL:REMEMBERPANELPOWERS':lambda *args:True,'EL:SAVENAMEPOWERS':lambda *args:True,
            'EL:TEMPLATEREADY':lambda *args:True,'EL:CURRENTJUNCTIONCONFIG':lambda value:value})
        f.call('EL:EditPanelOnce',result,cfg)
        record=f.h.run("(EL:Get 'record (EL:Get (namedobjdict) *EL:DiagramDiagnostics*))")
        self.assertTrue(truth(f.get('panel-output-handle',record)))
        self.assertEqual(len(f.commands),8)
        self.assertEqual([f.get('watts',r) for r in f.get('rows',record)[:5]],[23,48,3,68,90])
        self.assertEqual(f.get('status',record),Symbol('STALE'))

    def test_ambiguous_output_identity_gets_unique_new_keys_without_mutating_inputs(self):
        f=self.fixture();result=self.hotel(f);rows=f.get('circuits',result)
        rows[0]=self.put(f,'id','review-row-2',self.put(f,'circuit-uid','review-output/2',rows[0]))
        rows[1]=self.put(f,'id','',self.put(f,'circuit-uid',None,rows[1]))
        result=self.put(f,'circuits',rows,result);before=copy.deepcopy(result)
        generated=f.call('EL:GenerationResult',result)
        self.assertEqual(result,before)
        rows=f.get('circuits',generated)
        self.assertEqual(len({f.get('id',c) for c in rows}),5)
        self.assertEqual(len({f.get('circuit-uid',c) for c in rows}),5)
        f.h.set('RESULT',generated)
        self.assertTrue(truth(f.invoke()))
        record=f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual(len(f.get('rows',record)),7)
        self.assertEqual(f.get('status',record),Symbol('STALE'))

    def test_overlimit_load_is_reported_and_still_drawn_with_its_known_watts(self):
        f=self.fixture();result=self.hotel(f);rows=f.get('circuits',result)
        issue=[Pair(Symbol('CODE'),Symbol('POWER_OVER_LIMIT')),Pair(Symbol('OBJECT'),'R1')]
        rows[0]=self.put(f,'watts',173,self.put(f,'power-issues',[issue],rows[0]))
        result=self.click(f,self.put(f,'circuits',rows,result));f.h.set('RESULT',result)
        self.assertTrue(truth(f.invoke()))
        record=f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual(f.get('watts',f.get('rows',record)[0]),173)
        self.assertTrue(any('超过172W' in str(d) for e,d in f.events if e=='GENERATION_WITH_WARNINGS'))

    def test_reserve_numbers_do_not_reuse_an_unresolved_original_candidate(self):
        f=self.fixture();result=self.hotel(f);rows=f.get('circuits',result)
        evidence=self.put(f,'candidates',['ZE6','4ALE(JZ)-ZE6'],f.get('number-evidence',rows[0]))
        rows[0]=self.put(f,'number-evidence',evidence,rows[0])
        output=f.call('EL:FixedOutputs',rows)
        self.assertEqual([f.get('circuit-number',r) for r in output[-2:]],['ZE7','ZE8'])
        self.assertEqual(f.get('candidates',f.get('number-evidence',rows[0])),['ZE6','4ALE(JZ)-ZE6'])

    def test_physical_row_limit_uses_text_feedback_and_preserves_all_input_rows(self):
        f=self.fixture();result=self.hotel(f);base=f.get('circuits',result)[0]
        rows=[self.put(f,'id',f'R{i}',base) for i in range(9)]
        f.h.set('*EL:PANELDRAFT*',self.put(f,'circuits',rows,result));closed=[]
        f.h.builtins['EL:PANELCLOSE']=closed.append
        f.call('EL:PanelGenerateBody')
        self.assertEqual(closed,[])
        self.assertEqual(len(f.get('circuits',f.h.lookup('*EL:PANELDRAFT*'))),9)
        self.assertIn('不会截断',f.call('EL:PanelCircuitLimitText',f.h.lookup('*EL:PANELDRAFT*')))

    def test_failed_generation_returns_to_same_panel_without_recognition_or_alert(self):
        f=self.fixture();result=self.hotel(f);cfg=f.h.lookup('CFG');shown=[];prepared=[]
        def dialog(value,config,powers,capacity):
            shown.append((value,config,powers,capacity))
            if len(shown)==1:
                return [Pair(Symbol('RESULT'),value),Pair(Symbol('CONFIG'),config),
                        Pair(Symbol('CAPACITY'),Symbol('CAP600')),Pair(Symbol('GENERATE'),True)]
            return None
        def prepare(value,powers,*args):
            prepared.append(True)
            self.assertEqual(len(prepared),1,'retry must not refresh library defaults')
            return [Pair(Symbol('RESULT'),value),Pair(Symbol('POWERS'),powers)]
        f.h.builtins.update({'EL:PANELDIALOG':dialog,'EL:DLSNAPSHOT':lambda:None,
            'EL:DLPREPARE':prepare,
            'EL:REMEMBERPANELPOWERS':lambda *args:True,'EL:SAVENAMEPOWERS':lambda *args:True,
            'EL:SAVEDRAFT':lambda *args:True,'EL:TEMPLATEREADY':lambda *args:True,
            'EL:INVOKECCKK2':lambda *args:None,
            'EL:RECOGNIZEFIXED':lambda *args:self.fail('retry must reuse the displayed snapshot')})
        f.call('EL:EditPanel',result,cfg)
        self.assertEqual(len(shown),2)
        self.assertEqual(shown[1][3],Symbol('CAP600'))
        self.assertEqual(f.get('number-inputs',shown[1][0]),f.get('number-inputs',result))
        self.assertEqual([f.get('watts',c) for c in f.get('circuits',shown[1][0])],[23,48,3,68,90])

    def test_unavailable_template_returns_to_same_panel_with_saved_inputs(self):
        f=self.fixture();result=self.hotel(f);cfg=f.h.lookup('CFG');shown=[]
        def dialog(value,config,powers,capacity):
            shown.append(value)
            if len(shown)==1:
                return [Pair(Symbol('RESULT'),value),Pair(Symbol('CONFIG'),config),
                        Pair(Symbol('CAPACITY'),Symbol('CAP300')),Pair(Symbol('GENERATE'),True)]
            return None
        f.h.builtins.update({'EL:PANELDIALOG':dialog,'EL:DLSNAPSHOT':lambda:None,
            'EL:DLPREPARE':lambda r,p,*args:[Pair(Symbol('RESULT'),r),Pair(Symbol('POWERS'),p)],
            'EL:REMEMBERPANELPOWERS':lambda *args:True,'EL:SAVENAMEPOWERS':lambda *args:True,
            'EL:SAVEDRAFT':lambda *args:True,'EL:MARKSTALE':lambda *args:True,
            'EL:TEMPLATEREADY':lambda *args:None,
            'EL:INVOKECCKK2':lambda *args:self.fail('missing template must preserve the panel')})
        f.call('EL:EditPanel',result,cfg)
        self.assertEqual(len(shown),2)
        self.assertEqual([f.get('watts',c) for c in f.get('circuits',shown[1])],[23,48,3,68,90])

    def test_failed_draft_save_still_dispatches_explicit_generation(self):
        f=self.fixture();result=self.hotel(f)
        cfg=f.h.lookup('CFG');calls=[]
        edited=[Pair(Symbol('RESULT'),result),Pair(Symbol('CONFIG'),cfg),
                Pair(Symbol('CAPACITY'),Symbol('CAP300')),Pair(Symbol('GENERATE'),True)]
        f.h.builtins.update({'EL:PANELDIALOG':lambda *args:edited,'EL:DLSNAPSHOT':lambda:None,
            'EL:DLPREPARE':lambda r,p,*args:[Pair(Symbol('RESULT'),r),Pair(Symbol('POWERS'),p)],
            'EL:REMEMBERPANELPOWERS':lambda *args:None,'EL:SAVENAMEPOWERS':lambda *args:True,
            'EL:SAVEDRAFT':lambda *args:None,'EL:TEMPLATEREADY':lambda *args:True,
            'EL:INVOKECCKK2':lambda *args:calls.append(args) or True})
        f.call('EL:EditPanelOnce',result,cfg)
        self.assertEqual(len(calls),1)
        self.assertTrue(truth(f.get('generation-warning-mode',calls[0][0])))


if __name__=='__main__':unittest.main()
