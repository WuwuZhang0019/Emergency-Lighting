"""Native CCKK2 panel dispatch and cancellation adapters. Date: 2026-10-09."""
import copy
import unittest
from autolisp_host import Symbol, Pair, truth
import test_diagram_update as update


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
        self.assertEqual(self.get('position',self.get('plan',record)),[100.,200.,0.])
        self.assertEqual(self.variables,self.original)
        self.assertIsNone(self.h.lookup('*EL:CCKK2REQUEST*'))
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(len(self.commands),4)  # existing diagram is updated, never duplicated

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
