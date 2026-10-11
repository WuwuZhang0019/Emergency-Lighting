"""P1a native write interface and UID dependency checks. Date: 2026-10-11.

Finite DWG adapter evidence does not establish native AutoCAD acceptance.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
from test_cckk_assembly import field
import test_diagram_update as updates


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = updates.UpdateTests()
        self.fixture.setUp()
        self.fixture.install_sync()
        self.h = self.fixture.h
        self.native = []
        self.master = []
        self.h.frames[0][':VLAX-FALSE'] = 0
        # Exercise the production dynamic setter and block constructor.
        self.h.builtins.pop('EL:SETDYNAMICVALUE')
        self.h.builtins.pop('EL:CREATEBLOCK')
        self.h.builtins['VLA-GET-VALUE'] = lambda e: ('variant', 8, self.fixture.dynamic.get(e))
        self.h.builtins['VLAX-VARIANT-VALUE'] = lambda v: v[2] if isinstance(v, tuple) and v[0] == 'variant' else v
        self.h.builtins['VLAX-VARIANT-TYPE'] = lambda v: v[1]

        def put_value(e, variant):
            self.native.append(('value', e, variant[2]))
            self.fixture.dynamic[e] = variant[2]

        def put_layer(e, layer):
            self.native.append(('layer', e, layer))
            self.fixture.entities[e] = [Pair(8, layer) if isinstance(p, Pair) and p.car == 8 else p
                                        for p in self.fixture.entities[e]]

        def insert(space, point, name, sx, sy, sz, angle):
            self.fixture.counter += 1
            entity = 'new-block-' + str(self.fixture.counter)
            self.fixture.entity(entity, 'INSERT', point)
            self.fixture.dynamic[entity] = 'NORMAL'
            self.native.append(('insert', entity, name))
            return entity

        self.h.builtins.update({'VLA-PUT-VALUE': put_value, 'VLA-PUT-LAYER': put_layer,
                                'VLA-INSERTBLOCK': insert})
        for name, kind in [('VLA-PUT-TEXTSTRING', 'text'), ('VLA-MOVE', 'move'),
                           ('ENTMOD', 'entmod'), ('ENTMAKE', 'create-text'), ('ENTDEL', 'delete')]:
            original = self.h.builtins[name]
            def wrapped(*args, fn=original, label=kind):
                # A transaction marker is not a diagram output entity.
                entity = args[0] if label in ('text', 'move', 'delete') else field(args[0], -1)
                if label != 'delete' or not (isinstance(entity, str) and entity.isdigit()):
                    self.native.append((label, entity, args[1:] if len(args) > 1 else None))
                return fn(*args)
            self.h.builtins[name] = wrapped
        original = self.h.builtins['VLA-SETXRECORDDATA']
        def replace(*args):
            self.master.append(args[0])
            return original(*args)
        self.h.builtins['VLA-SETXRECORDDATA'] = replace
        self.fixture.undo.clear()

    def sync(self, capacity='cap300'):
        return self.h.run(f"(EL:SyncDiagram result nil nil '{capacity} T nil)")

    def changes(self):
        return self.fixture.get('operations', self.h.lookup('*EL:LASTUPDATEOPERATIONS*')) or []

    def new_plan(self, capacity='cap300'):
        self.h.run(f"(setq plan (EL:FixedPlan result template '{capacity} '(0.0 0.0 0.0) 0.0 1.0))")

    def test_no_change_has_no_native_write_or_transaction(self):
        before = copy.deepcopy((self.fixture.entities, self.fixture.dictionary, self.fixture.dynamic))
        self.assertTrue(truth(self.sync()))
        self.assertEqual(self.native, [])
        self.assertEqual(self.master, [])
        self.assertEqual(self.fixture.undo, [])
        self.assertEqual(self.changes(), [])
        self.assertEqual((self.fixture.entities, self.fixture.dictionary, self.fixture.dynamic), before)

    def test_single_power_update_writes_only_its_text_and_one_record(self):
        self.h.builtins['VLA-MOVE']('t0', field(self.fixture.entities['t0'], 10), [77., 88., 0.])
        self.native.clear()
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'watts 135 (car cs)) (cdr cs)) result))")
        self.assertTrue(truth(self.sync()))
        self.assertEqual(self.native, [('text', 't0', ('135W',))])
        self.assertEqual(len(self.master), 1)
        self.assertEqual(field(self.fixture.entities['t0'], 10), [77., 88., 0.])
        changes = self.changes()
        self.assertEqual(len(changes), 1)
        op = changes[0]
        self.assertEqual(self.fixture.get('uid', op), 'u1')
        self.assertEqual(self.fixture.get('handle', op), 't0')
        self.assertEqual(self.fixture.get('before', op), '120W')
        self.assertEqual(self.fixture.get('after', op), '135W')
        self.assertEqual(self.fixture.get('depends-on', op), ['u1'])
        self.native.clear(); self.master.clear(); self.fixture.undo.clear()
        self.assertTrue(truth(self.sync()))
        self.assertEqual((self.native, self.master, self.fixture.undo), ([], [], []))

    def test_type_change_writes_only_one_dynamic_value(self):
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'is-ground T (car cs)) (cdr cs)) result))")
        self.assertTrue(truth(self.sync()))
        self.assertEqual(self.native, [('value', 'b0', 'GROUND')])
        self.assertEqual(len(self.master), 1)
        self.assertEqual(self.fixture.get('reason', self.changes()[0]), Symbol('CIRCUIT-TYPE'))

    def test_capacity_change_writes_only_panel_dynamic_value(self):
        self.assertTrue(truth(self.sync('cap600')))
        self.assertEqual(self.native, [('value', 'panel', 'CAP600')])
        self.assertEqual(len(self.master), 1)

    def test_actual_layer_difference_repairs_only_that_object(self):
        self.h.builtins['VLA-PUT-LAYER']('b0', 'manual-layer')
        self.native.clear()
        self.assertTrue(truth(self.sync()))
        self.assertEqual(self.native, [('layer', 'b0', 'EL-SYSTEM')])
        self.assertEqual(self.fixture.get('before', self.changes()[0]), 'manual-layer')

    def test_added_uid_keeps_existing_blocks_and_renumbers_reserves_in_place(self):
        before = copy.deepcopy(self.fixture.entities)
        self.h.run('''(setq result (EL:Put 'circuits (append cs
          '(((id . "R3") (circuit-uid . "u3") (seed-key . s3) (watts . 12) (output-order . 3)))) result))''')
        # Identity-removal confirmation belongs to SyncDiagram; this fixture
        # executes the already-confirmed stable-UID update transaction directly.
        self.new_plan()
        record = self.h.run("(EL:Transaction 'EL:ApplyUpdate (list result template plan record store T))")
        self.assertTrue(truth(record))
        rows = self.fixture.get('rows', record)
        self.assertEqual([self.fixture.get('block-handle', r) for r in rows[:2]], ['b0', 'b1'])
        self.assertEqual([self.fixture.get('block-handle', r) for r in rows[-2:]], ['b2', 'b3'])
        self.assertFalse(any(op[0] == 'delete' for op in self.native))
        self.assertEqual(len([op for op in self.native if op[0] == 'insert']), 1)
        self.assertEqual(len([op for op in self.native if op[0] == 'create-text']), 3)
        for entity in ('b0', 'b1', 't0', 't1', 'caption-panel-label', 'caption-label/u1', 'caption-label/u2'):
            self.assertEqual(self.fixture.entities[entity], before[entity])
            self.assertFalse(any(op[1] == entity for op in self.native))
        self.assertTrue(all(self.fixture.get('uid', op) in ('u3', 'number/u3', 'label/u3') or
                            self.fixture.get('uid', op).startswith(('number/reserve-', 'reserve-'))
                            for op in self.changes()))

    def test_removed_uid_deletes_only_owned_members_retains_caption_handles(self):
        self.h.run("(setq result (EL:Put 'circuits (cdr cs) result))")
        self.new_plan()
        record = self.h.run("(EL:Transaction 'EL:ApplyUpdate (list result template plan record store T))")
        self.assertTrue(truth(record))
        deleted = {op[1] for op in self.native if op[0] == 'delete'}
        self.assertEqual(deleted, {'b0', 't0', 'caption-number/u1', 'caption-label/u1'})
        self.assertFalse(any(op[0] in ('insert', 'create-text') for op in self.native))
        self.assertEqual([self.fixture.get('block-handle', r) for r in self.fixture.get('rows', record)],
                         ['b1', 'b2', 'b3'])
        self.assertEqual(self.fixture.get('handle', self.fixture.call('EL:By', Symbol('UID'), 'number/u2',
                            self.fixture.get('cckk-labels', record))), 'caption-number/u2')
        self.assertEqual(len(self.master), 1)

    def test_stale_global_operation_list_is_not_reused_by_direct_update(self):
        self.assertTrue(truth(self.h.run('(EL:DiagramUnchanged record result plan store)')))
        self.h.builtins['VLA-PUT-TEXTSTRING']('t0', 'manual')
        self.native.clear()
        self.fixture.update()
        self.assertEqual(self.native, [('text', 't0', ('120W',))])

    def test_foreign_or_locked_entity_stops_before_any_write(self):
        self.fixture.entities['b0'] = [p for p in self.fixture.entities['b0']
                                        if not (isinstance(p, list) and p[0] == -3)]
        with self.assertRaises(RuntimeError):
            self.fixture.update()
        self.assertEqual((self.native, self.master), ([], []))

    def test_locked_layer_stops_read_only_planning_before_any_write(self):
        self.h.builtins['TBLSEARCH'] = lambda table, name: [Pair(70, 4)]
        with self.assertRaises(RuntimeError):
            self.fixture.update()
        self.assertEqual((self.native, self.master), ([], []))

    def test_actual_native_failure_rolls_back_graphics_and_store(self):
        before = copy.deepcopy((self.fixture.entities, self.fixture.dictionary, self.fixture.dynamic))
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'is-ground T (car cs)) (cdr cs)) result))")
        def fail_text(*args):
            raise RuntimeError('native value failure')
        self.h.builtins['VLA-PUT-VALUE'] = fail_text
        self.assertFalse(truth(self.sync('cap600')))
        # SyncDiagram marks the failed diagram stale in a separate transaction;
        # the failed update itself restores all diagram entities and dynamics.
        self.assertEqual(self.fixture.dynamic, before[2])
        for entity in before[0]:
            if not entity.isdigit():
                self.assertEqual(self.fixture.entities[entity], before[0][entity])

    def test_identical_update_metrics_report_zero_operations_and_native_writes(self):
        self.fixture.call('EL:PerfStart', 'ELUPDATE')
        self.assertTrue(truth(self.sync()))
        metrics = self.h.lookup('*EL:PERFMETRICS*')
        for key in ('incremental-operations', 'entity-write-attempts', 'master-write-attempts', 'transaction-starts'):
            self.assertEqual(self.fixture.call('EL:Get', key, metrics), 0, key)

    def test_transaction_start_callback_invalidates_the_precomputed_write_set(self):
        original = self.h.builtins['VLA-STARTUNDOMARK']
        def callback(document):
            original(document)
            # Simulate a third-party reactor changing an initially unchanged row.
            self.fixture.dynamic['b1'] = 'GROUND'
        self.h.builtins['VLA-STARTUNDOMARK'] = callback
        self.assertTrue(truth(self.sync('cap600')))
        self.assertEqual(self.native, [('value', 'panel', 'CAP600'), ('value', 'b1', 'NORMAL')])
        self.assertEqual({self.fixture.get('handle', op) for op in self.changes()}, {'panel', 'b1'})

    def test_business_only_change_compares_saved_record_and_writes_once(self):
        self.h.run("(setq store (EL:StoreRead) record (EL:Put 'config '((any-option . T)) record))")
        result = self.h.run("(EL:Transaction 'EL:ApplyUpdate (list result template plan record store nil))")
        self.assertTrue(truth(result))
        self.assertEqual(self.native, [])
        self.assertEqual(len(self.master), 1)
        self.assertTrue(truth(self.fixture.get('record-changed', self.h.lookup('*EL:LASTUPDATEOPERATIONS*'))))
        self.assertEqual(self.h.run('(EL:Get \'config (EL:DiagramForPanel "source" (EL:StoreRead)))'),
                         [Pair(Symbol('ANY-OPTION'), True)])

    def test_write_reactor_changes_unplanned_member_and_final_readback_rolls_back(self):
        before = copy.deepcopy((self.fixture.entities, self.fixture.dynamic))
        original = self.h.builtins['VLA-PUT-VALUE']
        def callback(entity, variant):
            original(entity, variant)
            if entity == 'panel':
                self.fixture.dynamic['b1'] = 'GROUND'
        self.h.builtins['VLA-PUT-VALUE'] = callback
        self.assertFalse(truth(self.sync('cap600')))
        self.assertEqual(self.fixture.dynamic, before[1])
        for entity in before[0]:
            if not entity.isdigit():
                self.assertEqual(self.fixture.entities[entity], before[0][entity])


if __name__ == '__main__':
    unittest.main()
