"""Actual update functions against a finite DWG adapter. Date: 2026-10-09."""
import copy
import math
import unittest
import test_diagram_store as db
import test_kernel as kernel
from autolisp_host import Pair, Symbol, truth

class UpdateTests(unittest.TestCase):
    generation_fixture=kernel.KernelTests.generation_fixture
    def setUp(self):
        db.StoreTests.setUp(self)
        for name in ('geometry','statistics','generation','fixed','panel','diagram-update','diagram-commands'):
            self.h.load_definitions(db.ROOT/'src'/f'{name}.lsp')
        self.generation_fixture()
        self.h.run('''(setq template (EL:Put 'panel (EL:Put 'name "dfgjhdrtyjtfgj4SADFG3" (EL:Get 'panel template))
          (EL:Put 'circuit (EL:Put 'name "fghjftyuk" (EL:Get 'circuit template)) template)))
          (setq store (EL:StoreInitial) result (EL:Put 'panel "source" result))
          (setq cs (EL:Get 'circuits result))
          (setq cs (list (EL:Put 'seed-key 's1 (EL:Put 'output-order 1 (EL:Put 'circuit-uid "u1" (car cs))))
            (EL:Put 'seed-key 's2 (EL:Put 'output-order 2 (EL:Put 'circuit-uid "u2" (cadr cs))))))
          (setq result (EL:Put 'circuits cs result))
          (setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))
          (setq record '((diagram-id . "d1") (source-panel-handle . "source") (panel-output-handle . "panel")))''')
        self.writes=[]; self.dynamic={}; self.deleted=[]; self.counter=0
        def text_write(e,value):
            self.writes.append((e,value))
            self.entities[e]=[Pair(1,value) if isinstance(p,Pair) and p.car==1 else p for p in self.entities[e]]
        def move(e,start,end):
            self.entities[e]=[Pair(10,end) if isinstance(p,Pair) and p.car==10 else p for p in self.entities[e]]
        def create_text(space,row,plan,layer):
            self.counter+=1; e='new-text-'+str(self.counter)
            self.entity(e,'TEXT',self.get('text-position',row),self.get('text',row)); return e
        def create_block(space,name,pos,scale,rotation,prop,value,layer):
            self.counter+=1; e='new-block-'+str(self.counter); self.entity(e,'INSERT',pos)
            self.dynamic[e]=value; return e
        self.h.builtins.update({'VLAX-GET-ACAD-OBJECT':lambda:'app','VLA-GET-ACTIVEDOCUMENT':lambda _:'doc',
          'VLA-GET-MODELSPACE':lambda _:'space','VLAX-ENAME->VLA-OBJECT':lambda e:e,
          'VLAX-VLA-OBJECT->ENAME':lambda e:e,'VLAX-3D-POINT':lambda p:p,
          'EL:DYNAMICPROPERTY':lambda e,name:e,'VLA-GET-VALUE':lambda e:self.dynamic.get(e),
          'VLAX-VARIANT-VALUE':lambda v:v,'EL:SETDYNAMICVALUE':lambda e,name,value:self.dynamic.__setitem__(e,value) or True,
          'VLA-PUT-TEXTSTRING':text_write,'VLA-MOVE':move,'EL:CREATEANNOTATION':create_text,'EL:CREATEBLOCK':create_block,
          'REGAPP':lambda _:True,'ENTDEL':lambda e:self.entities.pop(e,None) and self.deleted.append(e) or e})
        self.entity('panel','INSERT',[0.,0.,0.]); self.dynamic['panel']='CAP300'
        handles=[]
        for i,row in enumerate(self.get('rows',self.h.lookup('PLAN'))):
            key=self.get('circuit-uid',row); block=f'b{i}'; text=f't{i}'
            self.entity(block,'INSERT',self.get('position',row));self.dynamic[block]=self.get('value',row)
            self.call('EL:TagEntity',block,self.h.lookup('STORE'),self.h.lookup('RECORD'),'circuit',key)
            h=[Pair(Symbol('CIRCUIT-UID'),key),Pair(Symbol('BLOCK-HANDLE'),block)]
            if self.get('text',row):
                self.entity(text,'TEXT',self.get('text-position',row),self.get('text',row))
                self.call('EL:TagEntity',text,self.h.lookup('STORE'),self.h.lookup('RECORD'),'text',key)
                h.append(Pair(Symbol('TEXT-HANDLE'),text))
            handles.append(h)
        self.h.frames[0]['HANDLES']=handles
        self.h.run("(setq record (EL:Put 'rows (EL:RecordRows result plan handles) (EL:Put 'plan plan record)))")
        self.call('EL:TagEntity','panel',self.h.lookup('STORE'),self.h.lookup('RECORD'),'panel','panel')

    def call(self,fn,*args): return self.h.call(Symbol(fn.upper()),list(args))
    def get(self,key,row): return self.call('EL:Get',Symbol(key.upper()),row)
    def entity(self,e,kind,point,text=''):
        self.entities[e]=[Pair(-1,e),Pair(5,e),Pair(0,kind),Pair(10,point),Pair(1,text),Pair(8,'EL-SYSTEM'),
          Pair(410,'Model'),Pair(41,1.),Pair(42,1.),Pair(43,1.),Pair(50,0.)]
    def update(self,structural=False):
        return self.h.run("(EL:ApplyUpdate result template plan record store "+('T' if structural else 'nil')+")")

    def test_power_update_keeps_handles_manual_position_and_no_reserve_text(self):
        self.entities['t0']=[Pair(10,[99.,88.,0.]) if isinstance(p,Pair) and p.car==10 else p for p in self.entities['t0']]
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'watts 135 (car cs)) (cdr cs)) result)) (setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))")
        updated=self.update(); self.assertEqual(self.writes,[('t0','135W')]); self.assertEqual(self.counter,0)
        self.assertEqual(next(p.cdr for p in self.entities['t0'] if isinstance(p,Pair) and p.car==10),[99.,88.,0.])
        self.assertEqual([self.get('block-handle',r) for r in self.get('rows',updated)],['b0','b1','b2','b3'])
        self.assertEqual(len([e for e in self.entities if e.startswith('t')]),2)

    def test_missing_text_only_is_recreated(self):
        del self.entities['t0']; updated=self.update()
        self.assertEqual(self.counter,1);self.assertEqual(self.get('text-handle',self.get('rows',updated)[0]),'new-text-1')
        self.assertEqual(len([r for r in self.get('rows',updated) if self.get('text-handle',r)]),2)

    def test_remove_retains_reserve_identity_and_cleans_owned_row(self):
        self.h.run("(setq result (EL:Put 'circuits (cdr cs) result)) (setq plan (EL:FixedPlan result template 'cap600 '(0.0 0.0 0.0) 0.0 1.0))")
        updated=self.update(True)
        self.assertEqual(self.deleted,['b0','t0']);self.assertEqual(self.counter,0)
        self.assertEqual([self.get('block-handle',r) for r in self.get('rows',updated)],['b1','b2','b3'])
        self.assertEqual(self.dynamic['panel'],'CAP600')

    def test_ground_change_updates_state_and_not_power(self):
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'is-ground T (car cs)) (cdr cs)) result)) (setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))")
        self.update();self.assertEqual(self.dynamic['b0'],'GROUND'); self.assertEqual(self.writes,[])

    def install_transaction(self):
        self.undo=[]
        def begin(_): self.undo.append(copy.deepcopy((self.entities,self.dictionary,self.dynamic)))
        def rollback(*args):
            self.assertEqual(args,('_.UNDO','1'))
            self.entities,self.dictionary,self.dynamic=copy.deepcopy(self.undo.pop())
        def remove(_,key): return self.dictionary.pop(key,None)
        self.h.builtins.update({'VLA-STARTUNDOMARK':begin,'VLA-ENDUNDOMARK':lambda _:None,
          'COMMAND-S':rollback,'REDRAW':lambda:None,'DICTREMOVE':remove,
          'GETVAR':lambda key:1 if key=='UNDOCTL' else 'drawing-guid',
          'EXIT':lambda:(_ for _ in ()).throw(RuntimeError('LISP exit'))})

    def test_failed_write_rolls_back_modified_deleted_created_and_dictionary(self):
        self.install_transaction()
        before=copy.deepcopy((self.entities,self.dictionary,self.dynamic))
        self.h.run("(setq result (EL:Put 'circuits (cdr cs) result)) (setq plan (EL:FixedPlan result template 'cap600 '(0.0 0.0 0.0) 0.0 1.0))")
        self.h.builtins['EL:STOREWRITE']=lambda store:(_ for _ in ()).throw(RuntimeError('XRecord write failure'))
        outcome=self.h.run("(EL:Transaction 'EL:ApplyUpdate (list result template plan record store T))")
        self.assertFalse(truth(outcome));self.assertEqual((self.entities,self.dictionary,self.dynamic),before)
        self.assertFalse(truth(self.h.lookup('*EL:TRANSACTIONOPEN*')))

    def test_successful_single_undo_restores_both_graphics_and_record(self):
        self.install_transaction(); before=copy.deepcopy((self.entities,self.dictionary,self.dynamic))
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'watts 135 (car cs)) (cdr cs)) result)) (setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))")
        self.assertTrue(truth(self.h.run("(EL:Transaction 'EL:ApplyUpdate (list result template plan record store nil))")))
        self.assertIn('EL_FIXED_V1',self.dictionary);self.assertNotIn('EL_FIXED_TX',self.dictionary)
        self.h.builtins['COMMAND-S']('_.UNDO','1')
        self.assertEqual((self.entities,self.dictionary,self.dynamic),before)

    def test_layout_conflict_and_locked_layer_preflight(self):
        self.h.builtins['TBLSEARCH']=lambda table,name:[Pair(70,0)]
        self.assertFalse(truth(self.h.run("(EL:Get 'layout-conflict (EL:CheckLayout record store))")))
        self.entities['t0']=[Pair(10,[99.,88.,0.]) if isinstance(p,Pair) and p.car==10 else p for p in self.entities['t0']]
        self.assertTrue(truth(self.h.run("(EL:Get 'layout-conflict (EL:CheckLayout record store))")))
        self.h.builtins['TBLSEARCH']=lambda table,name:[Pair(70,4)]
        with self.assertRaises(RuntimeError): self.h.run('(EL:CheckLayout record store)')

    def test_identical_update_is_noop_and_manual_text_content_is_repaired(self):
        self.h.run("(setq record (EL:Put 'template template (EL:Put 'status 'current (EL:Put 'capacity-option 'cap300 (EL:Put 'power-signature (EL:Signature (EL:Get 'power-config result)) record)))))")
        self.assertTrue(truth(self.h.run('(EL:DiagramUnchanged record result plan store)')))
        self.h.builtins['VLA-PUT-TEXTSTRING']('t0','manual')
        self.assertFalse(truth(self.h.run('(EL:DiagramUnchanged record result plan store)')))

    def test_new_row_appends_before_existing_reserve_handles(self):
        self.h.run("(setq result (EL:Put 'circuits (append cs '(((id . \"R3\") (circuit-uid . \"u3\") (watts . 12) (output-order . 3)))) result)) (setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))")
        updated=self.update(True)
        rows=self.get('rows',updated)
        self.assertEqual(len(rows),5); self.assertEqual(self.counter,2)
        self.assertEqual([self.get('block-handle',r) for r in rows[-2:]],['b2','b3'])
        self.assertTrue(all(self.get('text-handle',r) is None for r in rows[-2:]))

    def install_sync(self):
        self.install_transaction()
        self.h.frames[0][':VLAX-FALSE']=0
        self.h.builtins.update({'TBLSEARCH':lambda *args:[Pair(70,0)],
          'EL:EFFECTIVENAME':lambda e:'dfgjhdrtyjtfgj4SADFG3' if e=='panel' else 'fghjftyuk',
          'VLA-GET-READONLY':lambda e:0,
          'EL:ALLOWEDVALUES':lambda e:['CAP300','CAP600','CAP1000'] if e=='panel' else ['NORMAL','GROUND','RESERVE'],
          'EL:TEMPLATERUNTIMEVALID':lambda *args:True,'EL:FRESHRESULT':lambda *args:True,
          'EL:UNIQUEDIAGRAM':lambda *args:True,'EL:WRITEDATA':lambda *args:True})
        self.h.run('''(setq cs (mapcar '(lambda (c) (EL:Put 'seed (list (cons 'key (EL:Get 'seed-key c))) c)) cs))
          (setq result (EL:Put 'circuits cs result) *EL:Root* "root/")
          (setq record (EL:Put 'template template (EL:Put 'status 'current (EL:Put 'capacity-option 'cap300
            (EL:Put 'power-signature (EL:Signature (EL:Get 'power-config result)) record)))))
          (EL:StoreWrite (EL:StorePutDiagram record store))''')

    def test_common_sync_noop_and_invalid_result_never_reports_saved(self):
        self.install_sync()
        before=copy.deepcopy(self.entities)
        self.assertTrue(truth(self.h.run("(EL:SyncDiagram result nil nil 'cap300 T nil)")))
        self.assertEqual(self.entities,before);self.assertEqual(self.undo,[])
        self.h.builtins['EL:PRINTSTATISTICS']=lambda *args:None
        self.assertFalse(truth(self.h.run("(EL:SyncDiagram (EL:Put 'can-generate nil result) nil nil 'cap300 T nil)")))
        self.assertEqual(self.h.run("(EL:Get 'status (EL:DiagramForPanel \"source\" (EL:StoreRead)))"),Symbol('STALE'))
        self.assertEqual(self.writes,[])

    def test_confirmed_fixed_update_uses_new_template_and_persists_sources(self):
        self.install_sync()
        self.h.builtins['EL:ALLOWEDVALUES'] = lambda e: ['CAP300','CAP600','CAP1000'] if e == 'panel' else ['NORMAL','GROUND','BURIED','RESERVE']
        self.h.run('''(setq cs (mapcar '(lambda (c) (EL:Put 'ground-source 'manual c)) cs))
          (setq cs (cons (EL:Put 'is-ground T (car cs)) (cdr cs)))
          (setq result (EL:Put 'engine 'fixed (EL:Put 'capacity-source 'manual (EL:Put 'circuits cs result))))
          (setq circuit (EL:Get 'circuit template))
          (setq states (mapcar '(lambda (s) (if (equal (EL:Get 'option s) 'ground) (EL:Put 'value "BURIED" s) s)) (EL:Get 'states circuit)))
          (setq new-template (EL:Put 'circuit (EL:Put 'states states circuit) template))
          (setq cfg (list (cons 'template new-template)))''')
        self.assertTrue(truth(self.h.run("(EL:SyncDiagram result cfg nil 'cap600 T nil)")))
        self.assertEqual(self.dynamic['panel'], 'CAP600')
        self.assertEqual(self.dynamic['b0'], 'BURIED')
        self.assertEqual(self.writes, [])
        record = self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual(self.get('capacity-source', record), Symbol('MANUAL'))
        self.assertEqual(self.get('capacity-option', record), Symbol('CAP600'))
        self.assertEqual(self.get('template', record), self.h.lookup('NEW-TEMPLATE'))
        self.assertEqual(self.h.run("(EL:Get 'fixed-template (EL:StoreRead))"), self.h.lookup('NEW-TEMPLATE'))
        actual = self.get('rows', record)[:2]
        self.assertEqual([self.get('ground-source', r) for r in actual], [Symbol('MANUAL')] * 2)
        self.assertEqual([self.get('block-handle', r) for r in actual], ['b0', 'b1'])

    def test_whole_rotation_scale_is_adopted_but_panel_only_move_is_rejected(self):
        self.h.builtins['TBLSEARCH']=lambda *args:[Pair(70,0)]
        import math
        for e,data in list(self.entities.items()):
            pos=next(p.cdr for p in data if isinstance(p,Pair) and p.car==10)
            transformed=[100.-2.*pos[1],200.+2.*pos[0],2.*pos[2]]
            self.entities[e]=[Pair(10,transformed) if isinstance(p,Pair) and p.car==10 else
              Pair(p.car,2.) if isinstance(p,Pair) and p.car in (41,42,43) else
              Pair(50,math.pi/2) if isinstance(p,Pair) and p.car==50 else p for p in data]
        transform=self.h.run('(EL:CheckLayout record store)')
        self.assertFalse(truth(self.get('layout-conflict',transform)))
        self.assertEqual(self.get('scale',transform),2.)
        self.entities['panel']=[Pair(10,[500.,600.,0.]) if isinstance(p,Pair) and p.car==10 else p for p in self.entities['panel']]
        with self.assertRaises(RuntimeError):self.h.run('(EL:CheckLayout record store)')

    def test_dynamic_failure_rolls_back_prior_capacity_change(self):
        self.install_transaction();before=copy.deepcopy((self.entities,self.dictionary,self.dynamic))
        original=self.h.builtins['EL:SETDYNAMICVALUE']
        self.h.builtins['EL:SETDYNAMICVALUE']=lambda e,prop,value:False if e=='b0' else original(e,prop,value)
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'is-ground T (car cs)) (cdr cs)) result)) (setq plan (EL:FixedPlan result template 'cap600 '(0.0 0.0 0.0) 0.0 1.0))")
        self.assertFalse(truth(self.h.run("(EL:Transaction 'EL:ApplyUpdate (list result template plan record store nil))")))
        self.assertEqual((self.entities,self.dictionary,self.dynamic),before)

    def test_existing_undo_group_saves_capacity_and_powers_with_real_transaction(self):
        self.install_transaction()
        state, events = [9], []
        begin = self.h.builtins['VLA-STARTUNDOMARK']
        def end(doc):
            events.append('end')
            state[0] = 1
        def start(doc):
            events.append('start')
            state[0] = 9
            begin(doc)
        self.h.builtins.update({
            'GETVAR': lambda key: state[0] if key == 'UNDOCTL' else 'drawing-guid',
            'VLA-ENDUNDOMARK': end, 'VLA-STARTUNDOMARK': start,
            'PRINC': lambda *args: args[0] if args else None,
            'EL:TEMPLATEREADY': lambda *args: None,
        })
        self.h.run("(setq fresh-result result result (EL:Put 'capacity-source 'manual result))")
        self.assertTrue(truth(self.h.run("(EL:SaveDraft result nil '((\"LAMP\" . 7)) 'cap600)")))
        self.assertEqual(events, ['end', 'start', 'end'])
        self.h.run('(setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity reopened)"), Symbol('CAP600'))
        self.assertEqual(self.h.run("(EL:Get 'powers reopened)"), self.h.run("'((\"LAMP\" . 7))"))
        self.assertEqual(self.h.run("(EL:Get 'capacity-source (EL:PreparedResult fresh-result reopened))"), Symbol('MANUAL'))
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity-source reopened)"), Symbol('MANUAL'))

    def test_start_failure_is_caught_without_writing_or_undoing_user_work(self):
        self.install_transaction()
        self.h.builtins['VLA-STARTUNDOMARK'] = lambda _: (_ for _ in ()).throw(RuntimeError('start failed'))
        messages = []
        self.h.builtins['PRINC'] = lambda value='': messages.append(value) or value
        self.assertIsNone(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))"))
        self.assertNotIn('EL_FIXED_V1', self.dictionary)
        self.assertEqual(self.undo, [])
        self.assertIn('start failed', ''.join(messages))

    def test_commit_failure_rolls_back_and_keeps_original_error(self):
        self.install_transaction()
        before = copy.deepcopy((self.entities, self.dictionary, self.dynamic))
        calls, messages = [], []
        def end(_):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('commit failed')
        self.h.builtins.update({'VLA-ENDUNDOMARK': end,
                               'PRINC': lambda value='': messages.append(value) or value})
        self.assertIsNone(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))"))
        self.assertEqual((self.entities, self.dictionary, self.dynamic), before)
        self.assertIn('commit failed', ''.join(messages))

    def test_rollback_failure_is_reported_without_erasing_original_error(self):
        self.install_transaction()
        messages = []
        self.h.builtins.update({
            'EL:STOREWRITE': lambda _: (_ for _ in ()).throw(RuntimeError('write failed')),
            'COMMAND-S': lambda *args: (_ for _ in ()).throw(RuntimeError('undo failed')),
            'PRINC': lambda value='': messages.append(value) or value,
        })
        self.assertIsNone(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))"))
        self.assertIn('write failed', ''.join(messages))
        self.assertIn('自动撤销未完成', ''.join(messages))
        self.assertTrue(truth(self.h.lookup('*EL:TRANSACTIONOPEN*')))

    def install_interrupted_marker(self):
        self.install_transaction()
        self.h.run('(setq marker (entmakex \'((0 . "XRECORD") (100 . "AcDbXrecord") (1 . "transaction")))) (dictadd (namedobjdict) "EL_FIXED_TX" marker)')
        def rename(_, old, new):
            if new in self.dictionary or old not in self.dictionary:
                return None
            self.dictionary[new] = self.dictionary.pop(old)
            return True
        self.h.builtins['DICTRENAME'] = rename

    def test_recovery_archives_marker_without_changing_graphics_or_store(self):
        self.install_interrupted_marker()
        self.dictionary['EL_FIXED_TX_INTERRUPTED_1'] = 'old-archive'
        self.entities['old-archive'] = [Pair(0, 'XRECORD')]
        before = copy.deepcopy(self.entities)
        marker = self.dictionary['EL_FIXED_TX']
        self.assertTrue(truth(self.h.run('(EL:ArchiveInterruptedTransaction)')))
        self.assertEqual(self.entities, before)
        self.assertEqual(self.dictionary['EL_FIXED_TX_INTERRUPTED_2'], marker)
        self.assertNotIn('EL_FIXED_TX', self.dictionary)
        self.assertEqual(self.undo, [])
        self.assertTrue(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        self.assertIn('EL_FIXED_V1', self.dictionary)
        self.assertEqual(self.dictionary['EL_FIXED_TX_INTERRUPTED_2'], marker)

    def test_recovery_cancel_keeps_marker_and_all_entities(self):
        self.install_interrupted_marker()
        before = copy.deepcopy((self.entities, self.dictionary))
        self.h.builtins.update({'INITGET': lambda *args: None, 'GETKWORD': lambda *args: None})
        self.h.run('(c:ELRECOVER)')
        self.assertEqual((self.entities, self.dictionary), before)

    def test_save_recovers_inline_and_continues_without_separate_command(self):
        self.install_interrupted_marker()
        before = copy.deepcopy(self.entities)
        self.h.builtins.update({'INITGET': lambda *args: None, 'GETKWORD': lambda *args: 'Yes',
                               'EL:TEMPLATEREADY': lambda *args: None})
        self.assertTrue(truth(self.h.run("(EL:SaveDraft result nil nil 'cap600)")))
        self.assertNotIn('EL_FIXED_TX', self.dictionary)
        self.assertIn('EL_FIXED_TX_INTERRUPTED_1', self.dictionary)
        self.assertIn('EL_FIXED_V1', self.dictionary)
        for entity, data in before.items():
            self.assertEqual(self.entities[entity], data)

    def test_large_template_draft_recovers_saves_and_reopens_with_bounded_read(self):
        self.install_interrupted_marker()
        sizes=db.install_bounded_read(self.h)
        before=copy.deepcopy(self.entities)
        definition='图块定义 "0001" C:\\项目\\应急\n'*2400
        self.h.frames[0]['DEFINITION']=definition
        self.h.builtins.update({'INITGET':lambda *args:None, 'GETKWORD':lambda *args:'Yes',
                               'EL:TEMPLATEREADY':lambda *args:True})
        self.h.run("(setq template (EL:Put 'panel (EL:Put 'definition definition (EL:Get 'panel template)) template) cfg (list (cons 'template template)) result (EL:Put 'capacity-source 'manual result))")
        self.assertTrue(truth(self.h.run("(EL:SaveDraft result cfg '((\"LAMP\" . 7)) 'cap600)")))
        self.assertNotIn('EL_FIXED_TX',self.dictionary)
        self.assertIn('EL_FIXED_TX_INTERRUPTED_1',self.dictionary)
        self.h.run('(setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity reopened)"),Symbol('CAP600'))
        self.assertEqual(self.h.run("(EL:Get 'powers reopened)"),self.h.run("'((\"LAMP\" . 7))"))
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity-source reopened)"),Symbol('MANUAL'))
        self.assertEqual(self.h.run("(EL:Get 'definition (EL:Get 'panel (EL:Get 'template (EL:Get 'config reopened))))"),definition)
        self.assertEqual(self.h.run("(EL:Get 'definition (EL:Get 'panel (EL:Get 'fixed-template (EL:StoreRead))))"),definition)
        for entity,data in before.items():
            self.assertEqual(self.entities[entity],data)
        self.assertLessEqual(max(sizes),256)
        self.assertGreater(len(self.h.run('(EL:StoreText (EL:StoreRead))')),87345)

    def test_corrupt_xrecord_readback_rolls_back_existing_store_and_graphics(self):
        self.h.run('(EL:StoreWrite store)')
        self.install_transaction()
        before=copy.deepcopy((self.entities,self.dictionary,self.dynamic))
        original=self.h.builtins['ENTMOD']
        entity=self.dictionary['EL_FIXED_V1']
        def corrupt(data):
            if any(p.car==-1 and p.cdr==entity for p in data):
                data=list(data)
                data[-1]=Pair(1,data[-1].cdr[:-1])
            return original(data)
        self.h.builtins['ENTMOD']=corrupt
        self.assertIsNone(self.h.run("(EL:Transaction 'EL:StoreWrite (list (EL:Put 'notes \"new\" store)))"))
        self.assertEqual((self.entities,self.dictionary,self.dynamic),before)
        self.assertFalse(truth(self.h.lookup('*EL:TRANSACTIONOPEN*')))

    def test_draft_then_sync_keep_low_real_digits_and_default_capacity(self):
        self.install_sync()
        params=[Pair(Symbol('THETA_MAX'),math.pi/36), Pair(Symbol('EPS_Z'),1e-20)]
        self.h.frames[0]['PARAMS']=params
        self.h.run("(setq cfg (list (cons 'template template) (cons 'params params)) result (EL:Put 'capacity-source 'default result))")
        self.h.builtins['EL:TEMPLATEREADY']=lambda *args:True
        self.assertTrue(truth(self.h.run("(EL:SaveDraft result cfg nil nil)")))
        self.h.run('(setq saved (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertEqual(self.h.run("(EL:Get 'params (EL:Get 'config saved))"),params)
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity saved)"),Symbol('CAP300'))
        self.assertTrue(truth(self.h.run("(EL:SyncDiagram result cfg nil 'cap300 T nil)")))
        self.h.run('(setq synced (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertEqual(self.h.run("(EL:Get 'params (EL:Get 'config synced))"),params)
        self.assertEqual(self.h.run("(EL:Get 'capacity-option synced)"),Symbol('CAP300'))
        self.assertEqual(self.h.run("(EL:Get 'panel-output-handle synced)"),'panel')
        self.assertNotIn('EL_FIXED_TX',self.dictionary)

    def test_native_readback_value_mismatch_reports_field_and_rolls_back(self):
        self.h.run('(EL:StoreWrite store)')
        self.install_transaction()
        before=copy.deepcopy((self.entities,self.dictionary,self.dynamic))
        original=self.h.builtins['ENTMOD']; entity=self.dictionary['EL_FIXED_V1']; events=[]
        self.h.builtins['EL:LOGEVENT']=lambda stage,context:events.append((stage,context))
        def corrupt(data):
            if any(p.car==-1 and p.cdr==entity for p in data):
                data=[Pair(40,0.0) if p.car==40 else p for p in data]
            return original(data)
        self.h.builtins['ENTMOD']=corrupt
        next_store=self.call('EL:Put',Symbol('TEST-REAL'),1e-20,self.h.lookup('STORE'))
        self.assertIsNone(self.call('EL:Transaction',Symbol('EL:STOREWRITE'),[next_store]))
        self.assertEqual((self.entities,self.dictionary,self.dynamic),before)
        mismatch=[context for stage,context in events if stage=='STORE_MISMATCH']
        self.assertEqual(len(mismatch),1)
        self.assertEqual(self.get('stage',mismatch[0]),Symbol('READBACK'))
        self.assertIn(Symbol('TEST-REAL'),self.get('path',mismatch[0]))
        self.assertEqual(self.get('number-difference',mismatch[0]),1e-20)

    def test_inline_recovery_cancel_does_not_start_transaction(self):
        self.install_interrupted_marker()
        before = copy.deepcopy((self.entities, self.dictionary))
        self.h.builtins.update({'INITGET': lambda *args: None, 'GETKWORD': lambda *args: None})
        self.assertIsNone(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))"))
        self.assertEqual((self.entities, self.dictionary), before)
        self.assertEqual(self.undo, [])

    def test_running_transaction_cannot_be_recovered_or_nested(self):
        self.install_interrupted_marker()
        self.h.run('(setq *EL:TransactionRunning* T)')
        self.h.builtins['GETKWORD'] = lambda *args: self.fail('must not prompt during active transaction')
        self.assertIsNone(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))"))
        self.assertIn('EL_FIXED_TX', self.dictionary)
        self.assertEqual(self.undo, [])

    def test_recovery_command_yes_archives_marker(self):
        self.install_interrupted_marker()
        self.h.builtins.update({'INITGET': lambda *args: None, 'GETKWORD': lambda *args: 'Yes'})
        self.h.run('(c:ELRECOVER)')
        self.assertNotIn('EL_FIXED_TX', self.dictionary)
        self.assertIn('EL_FIXED_TX_INTERRUPTED_1', self.dictionary)

    def test_recovery_rejects_unrecognized_marker(self):
        self.install_interrupted_marker()
        self.entities[self.dictionary['EL_FIXED_TX']] = [Pair(0, 'XRECORD'), Pair(1, 'foreign')]
        before = copy.deepcopy((self.entities, self.dictionary))
        with self.assertRaises(RuntimeError):
            self.h.run('(EL:ArchiveInterruptedTransaction)')
        self.assertEqual((self.entities, self.dictionary), before)

    def test_recovery_failed_rename_keeps_blocker(self):
        self.install_interrupted_marker()
        before = copy.deepcopy((self.entities, self.dictionary))
        self.h.builtins['DICTRENAME'] = lambda *args: None
        with self.assertRaises(RuntimeError):
            self.h.run('(EL:ArchiveInterruptedTransaction)')
        self.assertEqual((self.entities, self.dictionary), before)

    def test_disabled_or_unclosed_undo_is_not_a_truthy_message(self):
        self.install_transaction()
        self.h.builtins['PRINC'] = lambda *args: args[0] if args else None
        for state in (0, 9):
            with self.subTest(state=state):
                self.h.builtins['GETVAR'] = lambda key: state if key == 'UNDOCTL' else 'drawing-guid'
                self.assertIsNone(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))"))
                self.assertNotIn('EL_FIXED_V1', self.dictionary)
                self.assertEqual(self.undo, [])

    def test_sync_rejects_prompt_string_and_does_not_export_or_report_success(self):
        self.install_sync()
        messages, exports = [], []
        self.h.builtins.update({
            'EL:TRANSACTION': lambda *args: '请启用 UNDO 并结束已有撤销组。',
            'PRINC': lambda value='': messages.append(value) or value,
            'EL:WRITEDATA': lambda *args: exports.append(args) or True,
        })
        self.assertIsNone(self.h.run("(EL:SyncDiagram result nil nil 'cap600 T nil)"))
        self.assertEqual(exports, [])
        self.assertNotIn('系统图已同步', ''.join(messages))

    def test_draft_requires_store_readback_not_only_success_flag(self):
        self.h.builtins.update({'EL:TRANSACTION': lambda *args: True,
                               'EL:TEMPLATEREADY': lambda *args: None})
        self.assertFalse(truth(self.h.run("(EL:SaveDraft result nil nil 'cap600)")))
