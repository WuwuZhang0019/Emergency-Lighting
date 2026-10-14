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
            point=getattr(self,'placement',[100.,200.,0.]) if args[-1]=='pause' else args[-1]
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
            'VLA-REGEN':lambda *args:None,'EL:CONFIRMDIAGRAM':lambda:self.fail('placement must not ask Yes/No'),
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

    def install_view(self):
        # Execute the real padded zoom; only native entity extents and COM are adapted.
        self.h.load_definitions(update.db.ROOT/'src/simple.lsp')
        self.zoomed=[]; self.view_entities=[]; self.view_events=[]
        self.messages=[]; self.regenerated=[]
        def bounds(entity):
            self.view_entities.append(entity)
            data=self.entities[entity]
            p=field(data,11) if field(data,0)=='TEXT' else field(data,10)
            # Deliberately include full text width, not just insertion points.
            return [[p[0]-200.,p[1]-300.,p[2]],
                    [p[0]+6000.,p[1]+500.,p[2]]]
        self.h.builtins.update({
            'EL:ENTITYBOUNDS':bounds,
            'VLA-ZOOMWINDOW':lambda app,lo,hi:self.zoomed.append((lo,hi)),
            'VLA-REGEN':lambda *args:self.regenerated.append(args),
            'EL:LOGEVENT':lambda name,data:self.view_events.append((name,data)),
            'PRINC':lambda text=None:self.messages.append(text) or text,
        })

    def deleted_output_fixture(self, all_members):
        self.two_circuits(); self.four_circuits()
        self.assertTrue(truth(self.invoke()))
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        refs=self.call('EL:DiagramOutputRefs',record)
        handles=[ref[0] for ref in refs]
        removed=handles if all_members else [self.get('panel-output-handle',record)]
        for handle in removed: self.entities.pop(handle)
        return record,handles

    def test_deleted_four_circuit_output_stays_in_history_when_new_one_is_placed(self):
        self.install_view()
        old,handles=self.deleted_output_fixture(True)
        # In native AutoCAD, HANDENT can still resolve an erased entity name.
        original=self.h.builtins['HANDENT']
        self.h.builtins['HANDENT']=lambda h:h if h in handles else original(h)
        before=len(self.commands)
        self.assertTrue(truth(self.invoke()))
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual(self.commands[before][-1],'pause')
        self.assertEqual(len(self.commands)-before,7)
        self.assertNotEqual(self.get('panel-output-handle',record),self.get('panel-output-handle',old))
        self.assertNotEqual(self.get('diagram-id',record),self.get('diagram-id',old))
        self.assertEqual(self.call('EL:StoreRecord',self.get('diagram-id',old)),old)
        rows=self.get('rows',record)
        self.assertEqual([self.get('circuit-uid',r) for r in rows],
                         [self.get('circuit-uid',r) for r in self.get('rows',old)])
        self.assertEqual([self.get('watts',r) for r in rows[:4]],[85,20,20,20])
        self.assertEqual(len(self.get('cckk-labels',record)),11)
        self.assertEqual(self.get('status',record),Symbol('CURRENT'))
        self.assertNotIn('DIAGRAM_REBUILD',[e[0] for e in self.view_events])
        self.assertIn('DIAGRAM_VIEW_SHOWN',[e[0] for e in self.view_events])

    def test_new_generation_leaves_old_remnants_and_unrelated_entities(self):
        old,handles=self.deleted_output_fixture(False)
        self.entity('unrelated','TEXT',[12.,34.,0.],'keep')
        unrelated=copy.deepcopy(self.entities['unrelated'])
        self.assertTrue(truth(self.invoke()))
        self.assertTrue(any(h in self.entities for h in handles))
        self.assertEqual(self.entities['unrelated'],unrelated)
        self.assertNotIn('EL_FIXED_TX',self.dictionary)

    def test_cancel_rebuild_restores_remnants_and_old_association(self):
        old,handles=self.deleted_output_fixture(False)
        before=copy.deepcopy(self.entities)
        self.fail_at=len(self.commands)+3
        self.assertFalse(truth(self.invoke()))
        for h in handles:
            if h in before: self.assertEqual(self.entities[h],before[h])
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual(self.get('panel-output-handle',record),self.get('panel-output-handle',old))
        self.assertEqual(self.get('rows',record),self.get('rows',old))
        self.assertNotIn('EL_FIXED_TX',self.dictionary)

    def test_foreign_old_remnant_does_not_block_new_generation(self):
        old,handles=self.deleted_output_fixture(False)
        handle=self.get('block-handle',self.get('rows',old)[0])
        self.entities[handle]=[p for p in self.entities[handle]
                               if not (isinstance(p,list) and p[0]==-3)]
        before=copy.deepcopy(self.entities[handle]);commands=len(self.commands)
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(self.entities[handle],before)
        self.assertGreater(len(self.commands),commands)

    def test_old_box_ownership_or_lock_does_not_block_new_generation(self):
        self.install_view();self.assertTrue(truth(self.invoke()))
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        handle=self.get('panel-output-handle',record)
        original=copy.deepcopy(self.entities[handle])
        self.entities[handle]=[p for p in original if not (isinstance(p,list) and p[0]==-3)]
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(self.entities[handle],[p for p in original if not (isinstance(p,list) and p[0]==-3)])
        self.entities[handle]=[Pair(8,'locked-output') if isinstance(p,Pair) and p.car==8 else p for p in original]
        tblsearch=self.h.builtins['TBLSEARCH']
        self.h.builtins['TBLSEARCH']=lambda table,name:[Pair(70,4),Pair(62,7)] if name=='locked-output' else tblsearch(table,name)
        before=len(self.commands)
        self.assertTrue(truth(self.invoke()))
        self.assertGreater(len(self.commands),before)

    def four_circuits(self):
        self.h.run('''(setq result (EL:Put 'engine 'fixed result))
          (setq result (EL:Put 'circuits (append (EL:Get 'circuits result)
            (list (EL:Put 'id "R3" (EL:Put 'seed (list (cons 'key 's3)) (EL:Put 'output-order 3 (EL:Put 'watts 20 (car cs)))))
                  (EL:Put 'id "R4" (EL:Put 'seed (list (cons 'key 's4)) (EL:Put 'output-order 4 (EL:Put 'watts 20 (car cs))))))) result))
          (setq result (EL:PreparedResult result (EL:DiagramForPanel "source" (EL:StoreRead))))
          (setq result (EL:Put 'circuits (mapcar '(lambda (c)
            (EL:Put 'ground-source 'manual c)) (EL:Get 'circuits result)) result))''')

    def test_three_actual_plus_two_reserve_numbers_and_shrink(self):
        original_entities=set(self.entities)
        self.two_circuits(); self.four_circuits()
        self.h.run("(setq result (EL:Put 'circuits (reverse (cdr (reverse (EL:Get 'circuits result)))) result))")
        self.assertTrue(truth(self.invoke()))
        def check(count):
            record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
            labels=[l for l in self.get('cckk-labels',record) if self.get('kind',l)==Symbol('NUMBER')]
            self.assertEqual([field(self.entities[self.get('handle',l)],1) for l in labels],
                             [f'ZE{i+1}' for i in range(count)])
            for row,label in zip(self.get('rows',record),labels):
                self.assertEqual(self.get('parent-uid',label),self.get('circuit-uid',row))
                base=field(self.entities[self.get('block-handle',row)],10)
                self.assertEqual(field(self.entities[self.get('handle',label)],11),[base[0]+2100.,base[1]+140.,base[2]])
            return [self.get('handle',l) for l in labels]
        self.h.builtins.update({'INITGET':lambda *args:None, 'GETKWORD':lambda *args:'Replace'})
        handles=check(5)
        self.assertTrue(truth(self.invoke()))
        self.assertNotEqual(check(5),handles)
        self.assertTrue(all(handle in self.entities for handle in handles))
        self.h.run("(setq result (EL:Put 'circuits (list (car (EL:Get 'circuits result))) result))")
        self.assertTrue(truth(self.invoke()))
        check(3)
        self.assertEqual(sum(str(field(d,1)).startswith('ZE') for e,d in self.entities.items() if e not in original_entities),13)

    def test_two_to_four_creates_new_output_and_shows_only_new_entities(self):
        self.install_view()
        self.placement=[1279956.,449786.,0.]  # remote output, matching the field case
        self.two_circuits()
        self.assertTrue(truth(self.invoke()))
        old=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.four_circuits()
        self.zoomed.clear(); self.view_entities.clear(); self.view_events.clear()
        self.h.builtins['GETKWORD']=lambda *args:self.fail('no extra confirmation')
        self.assertTrue(truth(self.invoke()))
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        rows=self.get('rows',record)
        self.assertEqual(len(rows),6)
        self.assertEqual([self.get('watts',r) for r in rows[:4]],[85,20,20,20])
        self.assertEqual([field(self.entities[self.get('text-handle',r)],1) for r in rows[:4]],
                         ['85W','20W','20W','20W'])
        self.assertEqual(len(self.commands),12)  # first 5 entities, then a complete new 7-entity diagram
        self.assertNotEqual(self.get('panel-output-handle',record),self.get('panel-output-handle',old))
        self.assertNotEqual(self.get('diagram-id',record),self.get('diagram-id',old))
        self.assertEqual(self.call('EL:StoreRecord',self.get('diagram-id',old)),old)
        self.assertTrue(all(self.get('block-handle',r) in self.entities for r in self.get('rows',old)))
        self.assertTrue(all(self.get('text-handle',r) is None for r in rows[-2:]))
        expected={self.get('panel-output-handle',record)}
        expected.update(self.get('block-handle',r) for r in rows)
        expected.update(self.get('text-handle',r) for r in rows[:4])
        expected.update(self.get('handle',l) for l in self.get('cckk-labels',record))
        self.assertEqual(set(self.view_entities),expected)
        self.assertEqual(len(expected),22)  # box + six blocks + four powers + eleven labels
        self.assertEqual(len(self.zoomed),1)
        lo,hi=self.zoomed[0]
        for e in expected:
            data=self.entities[e]
            p=field(data,11) if field(data,0)=='TEXT' else field(data,10)
            self.assertLess(lo[0],p[0]-200.); self.assertLess(lo[1],p[1]-300.)
            self.assertGreater(hi[0],p[0]+6000.); self.assertGreater(hi[1],p[1]+500.)
        self.assertIn('DIAGRAM_VIEW_SHOWN',[e[0] for e in self.view_events])
        self.assertTrue(any('已生成新系统图' in str(m) for m in self.messages))
        self.assertFalse(truth(self.h.lookup('*EL:TRANSACTIONOPEN*')))
        # Repeating the same click creates another independently managed output.
        before=copy.deepcopy(self.entities)
        self.assertTrue(truth(self.invoke()))
        self.assertGreater(len(self.entities),len(before))
        for handle,*_ in self.call('EL:DiagramOutputRefs',record):
            self.assertEqual(self.entities[handle],before[handle])
        self.assertEqual(len(self.zoomed),2)

    def test_selecting_old_output_generates_successor_without_rebinding_history(self):
        self.two_circuits()
        self.assertTrue(truth(self.invoke()))
        first=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertTrue(truth(self.invoke()))
        second=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.h.run(f'''(setq result (EL:Put 'update-diagram-id
          "{self.get('diagram-id',first)}" (EL:Put 'update-source-panel "source" result)))''')
        self.assertTrue(truth(self.invoke()))
        third=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual(len({self.get('diagram-id',row) for row in (first,second,third)}),3)
        self.assertEqual(self.call('EL:StoreRecord',self.get('diagram-id',first)),first)
        self.assertEqual(self.call('EL:StoreRecord',self.get('diagram-id',second)),second)

    def test_first_four_circuit_placement_shows_output_but_save_does_not_move_view(self):
        self.install_view(); self.two_circuits(); self.four_circuits()
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(len(self.commands),7)
        self.assertEqual(len(self.zoomed),1)
        self.assertEqual(len(self.view_entities),22)
        self.assertTrue(truth(self.h.run("(EL:SyncDiagram result cfg nil 'cap300 nil T)")))
        self.assertTrue(truth(self.h.run("(EL:SyncDiagram result cfg nil 'cap300 T nil)")))
        self.assertEqual(len(self.zoomed),1)

    def test_view_failure_does_not_rollback_successful_generation(self):
        self.install_view(); self.two_circuits(); self.four_circuits()
        def fail_zoom(*args): raise RuntimeError('zoom unavailable')
        self.h.builtins['VLA-ZOOMWINDOW']=fail_zoom
        self.assertTrue(truth(self.invoke()))
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual(len(self.get('rows',record)),6)
        self.assertEqual(self.get('status',record),Symbol('CURRENT'))
        self.assertNotIn('EL_FIXED_TX',self.dictionary)
        self.assertIn('DIAGRAM_VIEW_FAILED',[e[0] for e in self.view_events])
        self.assertTrue(any('已保存，但自动定位未完成' in str(m) for m in self.messages))

    def test_failed_generation_does_not_show_partial_output(self):
        self.install_view(); self.two_circuits(); self.four_circuits()
        self.fail_at=4
        self.assertFalse(truth(self.invoke()))
        self.assertEqual(self.zoomed,[])
        self.assertEqual(self.view_entities,[])

    def test_view_rejects_missing_bounds_and_foreign_entity_without_writing(self):
        self.install_view()
        self.assertTrue(truth(self.invoke()))
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        store=self.h.run('(EL:StoreRead)')
        self.zoomed.clear()
        bounds=self.h.builtins['EL:ENTITYBOUNDS']
        self.h.builtins['EL:ENTITYBOUNDS']=lambda entity:None
        before=copy.deepcopy(self.entities)
        self.assertFalse(truth(self.call('EL:ShowDiagram',record,store)))
        self.assertEqual(self.entities,before)
        self.h.builtins['EL:ENTITYBOUNDS']=bounds
        handle=self.get('block-handle',self.get('rows',record)[0])
        self.entities[handle]=[p for p in self.entities[handle]
                               if not (isinstance(p,list) and p[0]==-3)]
        self.view_entities.clear()
        self.assertFalse(truth(self.call('EL:ShowDiagram',record,store)))
        self.assertNotIn(handle,self.view_entities)
        self.assertEqual(self.zoomed,[])

    def two_circuits(self):
        # Date: 2026-10-11. Numbered-output cases must supply the picked number.
        self.h.run("""(setq result (EL:Put 'panel-number "CK-B1AL1" result))
          (setq result (EL:Put 'circuits
          (mapcar '(lambda (c) (EL:Put 'ground-source 'manual c))
            (list (EL:Put 'watts 85 (car cs)) (EL:Put 'watts 20 (cadr cs)))) result))""")

    def assert_two_circuit_output(self):
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        rows=self.get('rows',record)
        self.assertEqual(len(rows),4)
        self.assertEqual([self.get('watts',r) for r in rows[:2]],[85,20])
        self.assertEqual([field(self.entities[self.get('text-handle',r)],1)
                          for r in rows[:2]],['85W','20W'])
        for r in rows[:2]:
            data=self.entities[self.get('text-handle',r)]
            for code,value in [(0,'TEXT'),(7,'_TEL_DIM'),(8,'TEL_TEXT'),(40,350.),
                               (41,.7),(62,256),(72,1),(73,0)]:
                self.assertEqual(field(data,code),value)
            block=field(self.entities[self.get('block-handle',r)],10)
            self.assertEqual(field(data,11),[block[0]+10983.,block[1]-450.,block[2]])
        self.assertTrue(all(self.get('text-handle',r) is None for r in rows[2:]))
        self.assertEqual([self.dynamic[self.get('block-handle',r)] for r in rows],
                         ['NORMAL','NORMAL','RESERVE','RESERVE'])
        self.assertEqual([field(self.entities[self.get('handle',label)],1)
                          for label in self.get('cckk-labels',record)],
                         ['CK-B1AL1','ZE1','商铺疏散指示及应急照明','ZE2','商铺疏散指示及应急照明','ZE3','ZE4'])
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
            'INITGET':lambda *args:None,'GETKWORD':lambda *args:self.fail('generate must not ask Yes/No'),
            'COMMAND-S':lambda *args:self.fail('recovery must preserve user edits'),
            'EL:PANELDIALOG':lambda *args:edited,'EL:FIXEDPOWERS':lambda *args:None,
            'EL:DLSNAPSHOT':lambda:self.call('EL:Put',Symbol('ROOT'),'library-fixture/',
                self.call('EL:Put',Symbol('CATALOG'),self.call('EL:DLCatalogInitial','LIB-CCKK'),None)),
            'EL:REMEMBERPANELPOWERS':lambda *args:True,'EL:SAVENAMEPOWERS':lambda *args:True,
            'EL:TEMPLATEREADY':lambda *args:True,'EL:CLEARPICKHIGHLIGHTS':lambda:None,
            'EL:LOGEVENT':lambda name,data:events.append(name),
            'PRINC':lambda value='':messages.append(value) or value,
        })
        self.h.run('(setq *EL:LogActive* T) (EL:EditPanel result cfg)')
        self.assertEqual(len(prompts),0)
        self.assertIn('TRANSACTION_MEMORY_RECOVERED',events)
        self.assertEqual(len(self.commands),5, ''.join(messages))  # box + 2 actual + 2 reserve
        self.assertEqual(len(self.undo),2)  # saved draft then generated diagram
        self.assert_two_circuit_output()
        count=len(self.entities)
        self.h.run('(EL:EditPanel result cfg)')
        self.assertEqual(len(self.commands),10)
        self.assertGreater(len(self.entities),count)
        self.assertEqual(len(prompts),0)
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

    def test_power_uses_cckk_entmake_not_the_activex_annotation_path(self):
        self.two_circuits()
        self.h.builtins['EL:CREATEANNOTATION']=lambda *args:self.fail('fixed power must use original CCKK TEXT')
        self.assertTrue(truth(self.invoke()))
        self.assert_two_circuit_output()

    def test_nil_after_first_row_rolls_back_without_recovery_then_retry_succeeds(self):
        self.two_circuits()
        before=copy.deepcopy(self.entities)
        events=[]
        def interrupted(result,template,capacity,plan,record,store):
            panel=self.call('EL:CCKK2ManagedBlock',self.get('panel-name',plan),None,
                            self.get('panel',template),self.get('panel-value',plan))
            row=self.get('rows',plan)[0]
            circuit=self.call('EL:CCKK2ManagedBlock',self.get('name',self.get('circuit',template)),
                              self.get('position',row),self.get('circuit',template),self.get('value',row))
            self.call('EL:CreatePowerAnnotation','space',row,plan,'TEL_TEXT',circuit)
            return None  # observed TX_WRITE NIL, with objects already created
        self.h.builtins.update({'EL:CCKK2CREATECONFIGURED':interrupted,
                               'EL:LOGEVENT':lambda stage,context:events.append(stage)})
        self.assertFalse(truth(self.invoke()))
        self.assertIn('TRANSACTION_ERROR',events)
        self.assertNotIn('TRANSACTION_MEMORY_RECOVERED',events)
        self.assertNotIn('TRANSACTION_RECOVERY_REQUIRED',events)
        self.assertFalse(any(e.startswith('native-') for e in self.entities))
        for e,data in before.items():
            if e!=self.dictionary['EL_FIXED_V1']: self.assertEqual(self.entities[e],data)
        for flag in ('OPEN','DIRTY','RUNNING'):
            self.assertFalse(truth(self.h.lookup('*EL:TRANSACTION'+flag+'*')))
        del self.h.builtins['EL:CCKK2CREATECONFIGURED']
        self.commands.clear()
        self.assertTrue(truth(self.invoke()))
        self.assert_two_circuit_output()

    def test_power_entmake_failure_rolls_back_all_rows(self):
        self.two_circuits()
        original=self.h.builtins['ENTMAKE']
        self.h.builtins['ENTMAKE']=lambda data:None if field(data,1)=='20W' else original(data)
        before=set(self.entities)
        self.assertFalse(truth(self.invoke()))
        self.assertEqual(set(self.entities),before)
        self.assertFalse(truth(self.h.lookup('*EL:TRANSACTIONOPEN*')))

    def test_power_tag_silent_write_failure_is_read_back_and_rolled_back(self):
        self.two_circuits()
        original=self.h.builtins['ENTMOD']
        self.h.builtins['ENTMOD']=lambda data:data if field(data,1)=='85W' else original(data)
        before=set(self.entities)
        self.assertFalse(truth(self.invoke()))
        self.assertEqual(set(self.entities),before)
        self.assertFalse(truth(self.h.lookup('*EL:TRANSACTIONOPEN*')))

    def test_rollback_failure_does_not_start_stale_record_write_or_recovery(self):
        self.two_circuits()
        self.fail_at=3
        events=[]
        self.h.builtins.update({
            'COMMAND-S':lambda *args:(_ for _ in ()).throw(RuntimeError('undo failed')),
            'EL:LOGEVENT':lambda stage,context:events.append(stage)})
        self.assertFalse(truth(self.invoke()))
        self.assertIn('ROLLBACK_ERROR',events)
        self.assertNotIn('TRANSACTION_RECOVERY_REQUIRED',events)
        self.assertTrue(truth(self.h.lookup('*EL:TRANSACTIONOPEN*')))

    def test_existing_one_circuit_adds_second_using_reviewed_seed_identity(self):
        self.assertTrue(truth(self.invoke()))
        self.two_circuits()
        # Real dialog receives PreparedResult, then confirms every row's type.
        self.h.run('''(setq result (EL:Put 'engine 'fixed result))
          (setq result (EL:PreparedResult result (EL:DiagramForPanel "source" (EL:StoreRead))))
          (setq result (EL:Put 'circuits (mapcar '(lambda (c)
            (EL:Put 'ground-source 'manual c)) (EL:Get 'circuits result)) result))''')
        self.h.builtins['GETKWORD']=lambda *args:self.fail('adding a reviewed circuit must not prompt')
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(len(self.commands),9)  # complete second system diagram
        self.assert_two_circuit_output()
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual([field(self.entities[self.get('block-handle',r)],10)
                          for r in self.get('rows',record)],
                         [[6527.,-5300.,0.],[6527.,-6500.,0.],
                          [6527.,-7700.,0.],[6527.,-8900.,0.]])

    def test_panel_calls_real_command_places_native_box_and_85w_circuits(self):
        # The actual c:CCKK2 function runs; native COMMAND calls are recorded.
        self.h.run('(setq result (EL:Put \'panel-number "CK-B1AL1" result))')
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
        self.assertEqual(len(labels),5)
        numbers=[l for l in labels if self.get('kind',l)==Symbol('NUMBER')]
        self.assertEqual([self.get('text',l) for l in numbers],['ZE1','ZE2','ZE3'])
        for i,label in enumerate(numbers):
            data=self.entities[self.get('handle',label)]
            self.assertEqual(field(data,11),[8627.,-5160.-1200.*i,0.])
            for code,value in [(7,'_TEL_DIM'),(8,'TEL_TEXT'),(62,256),(40,350.),(41,.7),(72,1),(73,0)]:
                self.assertEqual(field(data,code),value)
        labels=[l for l in labels if self.get('kind',l)!=Symbol('NUMBER')]
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
        self.assertEqual(len(self.commands),8)  # same click produces a new box and rows

    def test_missing_old_captions_remain_untouched_when_new_output_is_generated(self):
        self.h.run('(setq result (EL:Put \'panel-number "CK-B1AL1" result))')
        self.assertTrue(truth(self.invoke()))
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        for label in self.get('cckk-labels',record):
            del self.entities[self.get('handle',label)]
        self.assertTrue(truth(self.invoke()))
        self.assertEqual(len(self.commands),8)
        record=self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertEqual([field(self.entities[self.get('handle',label)],1)
                          for label in self.get('cckk-labels',record)],
                         ['CK-B1AL1','ZE1','商铺疏散指示及应急照明','ZE2','ZE3'])
        count=len(self.entities)
        self.assertTrue(truth(self.invoke()))
        self.assertGreater(len(self.entities),count)

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
