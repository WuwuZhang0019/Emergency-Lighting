"""Native CCKK2 panel dispatch and cancellation adapters. Date: 2026-10-10."""
import copy
import unittest
from autolisp_host import Symbol, Pair, truth
import test_diagram_update as update
from test_cckk_assembly import field


class PanelCommandTests(unittest.TestCase):
    call=update.UpdateTests.call
    get=update.UpdateTests.get
    entity=update.UpdateTests.entity
    generation_fixture=update.UpdateTests.generation_fixture
    install_transaction=update.UpdateTests.install_transaction
    install_sync=update.UpdateTests.install_sync

    def setUp(self):
        update.UpdateTests.setUp(self)
        self.install_sync()
        self.variables={'CMDECHO':1,'ATTREQ':1,'DRAGMODE':0,'CLAYER':'source-layer',
                        'TILEMODE':1,'CVPORT':2}
        self.original=dict(self.variables)
        old_getvar=self.h.builtins['GETVAR']
        self.commands=[]
        self.last=None
        self.fail_at=None
        def command(*args):
            self.commands.append(args)
            if self.fail_at==len(self.commands): raise RuntimeError('Function cancelled')
            self.assertEqual(args[0],'_.-INSERT')
            point=[100.,200.,0.] if args[-1]=='pause' else args[-1]
            self.last='native-'+str(len(self.commands))
            self.entity(self.last,'INSERT',point)
            self.entities[self.last].append(Pair(2,args[1]))
        self.h.frames[0]['PAUSE']='pause'
        self.h.builtins.update({
            'GETVAR':lambda key:self.variables[key] if key in self.variables else old_getvar(key),
            'SETVAR':lambda key,value:self.variables.__setitem__(key,value),
            'COMMAND':command,'ENTLAST':lambda:self.last,'TRANS':lambda p,*args:p,
            'GETINT':lambda *args:self.fail('panel invocation must not ask for circuit count'),
            'GETPOINT':lambda *args:self.fail('CCKK2 must use native drag placement'),
            'VLA-REGEN':lambda *args:None,'EL:CONFIRMDIAGRAM':lambda:True,
            'EL:EFFECTIVENAME':lambda e:next((p.cdr for p in self.entities[e] if isinstance(p,Pair) and p.car==2),
                                            'dfgjhdrtyjtfgj4SADFG3' if e=='panel' else 'fghjftyuk'),
            'EL:ALLOWEDVALUES':lambda e:['CAP300','CAP600','CAP1000'] if e in ('panel','native-1')
                                      else ['NORMAL','GROUND','RESERVE'],
        })
        self.h.run("""(setq result (EL:Put 'circuits (list (EL:Put 'watts 85 (car cs))) result))
          (setq record (EL:Put 'panel-output-handle nil (EL:Put 'cckk-labels nil record)))
          (setq record (EL:Put 'rows (list (car (EL:Get 'rows record))) record))
          (setq cfg (list (cons 'template template)))
          (EL:StoreWrite (EL:StorePutDiagram record store))""")

    def invoke(self):
        return self.h.run("(EL:InvokeCCKK2 result cfg nil 'cap300)")

    def two_circuits(self):
        self.h.run("""(setq result (EL:Put 'circuits
          (mapcar '(lambda (c) (EL:Put 'ground-source 'manual c))
            (list (EL:Put 'watts 85 (car cs)) (EL:Put 'watts 20 (cadr cs)))) result))""")

    def assert_two_circuit_output(self):
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        rows=self.get('rows',record)
        self.assertEqual(len(rows),4)
        self.assertEqual([self.get('watts',r) for r in rows[:2]],[85,20])
        self.assertEqual([field(self.entities[self.get('text-handle',r)],1)
                          for r in rows[:2]],['85W','20W'])
        self.assertTrue(all(self.get('text-handle',r) is None for r in rows[2:]))
        self.assertEqual([self.dynamic[self.get('block-handle',r)] for r in rows],
                         ['NORMAL','NORMAL','RESERVE','RESERVE'])
        self.assertEqual([field(self.entities[self.get('handle',label)],1)
                          for label in self.get('cckk-labels',record)],
                         ['CK-B1AL1','商铺疏散指示及应急照明','商铺疏散指示及应急照明'])
        for flag in ('OPEN','DIRTY','RUNNING'):
            self.assertFalse(truth(self.h.lookup('*EL:TRANSACTION'+flag+'*')))
        self.assertNotIn('EL_FIXED_TX',self.dictionary)

    def test_two_circuit_generate_click_recovers_memory_and_repeated_update(self):
        self.two_circuits()
        self.h.run('(setq *EL:TransactionOpen* T *EL:TransactionDirty* T)')
        # Reproduce the reported UNDOCTL=61, without a dictionary TX marker.
        state=[61]; prompts=[]; events=[]; messages=[]
        original_getvar=self.h.builtins['GETVAR']
        begin=self.h.builtins['VLA-STARTUNDOMARK']
        def end(_): state[0] &= ~8
        def start(doc):
            self.assertEqual(state[0] & 8,0)
            begin(doc); state[0] |= 8
        edited=self.h.run("(list (cons 'result result) (cons 'config cfg) '(generate . T) '(capacity . cap300))")
        self.h.builtins.update({
            'GETVAR':lambda key:state[0] if key=='UNDOCTL' else original_getvar(key),
            'VLA-ENDUNDOMARK':end,'VLA-STARTUNDOMARK':start,
            'INITGET':lambda *args:None,'GETKWORD':lambda *args:prompts.append(args) or 'Yes',
            'COMMAND-S':lambda *args:self.fail('recovery must preserve user edits'),
            'EL:PANELDIALOG':lambda *args:edited,'EL:FIXEDPOWERS':lambda *args:None,
            'EL:REMEMBERPANELPOWERS':lambda *args:True,'EL:SAVENAMEPOWERS':lambda *args:True,
            'EL:TEMPLATEREADY':lambda *args:True,'EL:CLEARPICKHIGHLIGHTS':lambda:None,
            'EL:LOGEVENT':lambda name,data:events.append(name),
            'PRINC':lambda value='':messages.append(value) or value,
        })
        self.h.run('(setq *EL:LogActive* T) (EL:EditPanel result cfg)')
        self.assertEqual(len(prompts),1)
        self.assertIn('TRANSACTION_MEMORY_RECOVERED',events)
        self.assertEqual(len(self.commands),5, ''.join(messages))  # box + 2 actual + 2 reserve
        self.assertEqual(len(self.undo),2)  # saved draft then generated diagram
        self.assert_two_circuit_output()
        count=len(self.entities)
        self.h.run('(EL:EditPanel result cfg)')
        self.assertEqual(len(self.commands),5)
        self.assertEqual(len(self.entities),count)
        self.assertEqual(len(prompts),1)
        self.assert_two_circuit_output()

    def test_two_circuit_cancel_then_retry_releases_live_guard(self):
        self.two_circuits()
        self.fail_at=3
        self.assertFalse(truth(self.invoke()))
        self.assertFalse(any(e.startswith('native-') for e in self.entities))
        for flag in ('OPEN','DIRTY','RUNNING'):
            self.assertFalse(truth(self.h.lookup('*EL:TRANSACTION'+flag+'*')))
        self.fail_at=None
        self.commands.clear()
        self.assertTrue(truth(self.invoke()))
        self.assert_two_circuit_output()

    def test_panel_calls_real_command_places_native_box_and_85w_circuits(self):
        # The actual c:CCKK2 function runs; native COMMAND calls are recorded.
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(len(self.commands),4)
        self.assertEqual(self.commands[0][-1],'pause')
        self.assertEqual(self.commands[1][-1],[6527.,-5300.,0.])
        self.assertEqual(self.dynamic['native-1'],'CAP300')
        self.assertEqual(self.dynamic['native-2'],'NORMAL')
        self.assertEqual(self.dynamic['native-3'],'RESERVE')
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        row=self.get('rows',record)[0]
        self.assertIn(Pair(1,'85W'),self.entities[self.get('text-handle',row)])
        labels=self.get('cckk-labels',record)
        self.assertEqual(len(labels),2)
        for label,text,point,style,layer,color in zip(labels,
                ['CK-B1AL1','商铺疏散指示及应急照明'],[[2550.,-255.,0.],[17510.,-5235.,0.]],
                ['ICDA-STYLE1','_TEL_DIM'],['SYS_系统标注_E','TEL_TEXT'],[0,256]):
            data=self.entities[self.get('handle',label)]
            for code,expected in [(0,'TEXT'),(1,text),(11,point),(7,style),(8,layer),(62,color),
                                  (40,350.),(41,.7),(72,1),(73,0),(440,0)]:
                self.assertEqual(field(data,code),expected)
        self.assertEqual(self.get('position',self.get('plan',record)),[100.,200.,0.])
        self.assertEqual(self.variables,self.original)
        self.assertIsNone(self.h.lookup('*EL:CCKK2REQUEST*'))
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(len(self.commands),4)  # existing diagram is updated, never duplicated

    def test_missing_v53_captions_repaired_without_reinserting_blocks(self):
        self.assertTrue(truth(self.invoke()))
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        for label in self.get('cckk-labels',record):
            del self.entities[self.get('handle',label)]
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(len(self.commands),4)
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual([field(self.entities[self.get('handle',label)],1)
                          for label in self.get('cckk-labels',record)],
                         ['CK-B1AL1','商铺疏散指示及应急照明'])
        count=len(self.entities)
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(len(self.entities),count)

    def test_caption_creation_failure_rolls_back_instead_of_silent_omission(self):
        original=self.h.builtins['ENTMAKE']
        self.h.builtins['ENTMAKE']=lambda data:None if field(data,1)=='商铺疏散指示及应急照明' else original(data)
        before=set(self.entities)
        self.assertFalse(truth(self.invoke()))
        self.assertFalse(any(e.startswith('native-') for e in self.entities))
        self.assertEqual(set(self.entities),before)
        self.assertEqual(self.variables,self.original)

    def test_escape_restores_variables_and_undoes_partial_native_objects(self):
        for fail_at in (1,3):
            with self.subTest(fail_at=fail_at):
                self.setUp()
                before=copy.deepcopy((self.entities,self.dictionary,self.dynamic))
                self.fail_at=fail_at
                self.assertFalse(truth(self.invoke()))
                # Stale bookkeeping may update the XRecord after rollback.
                for entity,data in before[0].items():
                    if entity!=self.dictionary['EL_FIXED_V1']:
                        self.assertEqual(self.entities[entity],data)
                self.assertFalse(any(e.startswith('native-') for e in self.entities))
                self.assertEqual(self.variables,self.original)
                self.assertIsNone(self.h.lookup('*EL:CCKK2REQUEST*'))
