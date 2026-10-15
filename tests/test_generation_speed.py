"""Date: 2026-10-15. Current-input storage and exact native-source reuse guards.

Finite CAD adapters; this is not native AutoCAD timing evidence.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
from check_recognition_six_work import six_fixture
from check_store_read_work import exact
import test_store_split as split_fixture
import test_cckk_panel_command as native_fixture


class NativeSourceReuseTests(unittest.TestCase):
    def setUp(self):
        self.f = six_fixture(3, 3, 2)
        self.f.call('EL:PerfStart', 'ELSTAT')
        self.result = self.f.call('EL:RecognizeFixed', self.f.cfg, 'panel')

    def metric(self, key):
        return self.f.call('EL:Get', key, self.f.h.lookup('*EL:PERFMETRICS*')) or 0

    def fresh(self):
        self.f.call('EL:FreshBoundary')
        return truth(self.f.call('EL:FreshResult', self.result, self.f.cfg))

    def test_unchanged_source_rechecks_native_data_without_rebuilding_candidates(self):
        before = exact(self.result)
        self.f.h.builtins['EL:WIRERECORDDXF'] = lambda *_: self.fail('reconstructed unchanged wire')
        self.f.h.builtins['EL:SPATIALTREE'] = lambda *_: self.fail('rebuilt unchanged candidate tree')
        self.assertTrue(self.fresh())
        self.assertEqual(self.metric('source-collect-calls'), 1)
        self.assertEqual(self.metric('source-derived-reuses'), 1)
        self.assertEqual(self.metric('source-native-entity-checks'), len(self.f.selected))
        self.assertGreater(self.metric('source-native-bounds-checks'), 0)
        self.assertGreater(self.metric('network-geometry-checks'), 0)
        self.assertEqual(exact(self.result), before)

    def test_wire_change_addition_and_removal_recollect_and_reject(self):
        for change in ('edit', 'add', 'delete'):
            with self.subTest(change=change):
                self.setUp()
                if change == 'edit':
                    self.f.line('remote-wire-0', [20000., 20000., 0.], [20020., 20000., 0.], 'W')
                elif change == 'add':
                    self.f.line('new-wire', [60000., 0., 0.], [60010., 0., 0.], 'W')
                    self.f.selected.append('new-wire')
                else:
                    self.f.selected.remove('remote-wire-0')
                self.assertFalse(self.fresh())
                self.assertEqual(self.metric('source-derived-reuses'), 0)
                self.assertEqual(self.metric('source-collect-calls'), 2)

    def test_definition_change_with_same_insert_data_and_bounds_is_still_detected(self):
        data = copy.deepcopy(self.f.entities['active-0-0'])
        self.f.line('LAMP-edge-0', [-.5, -.5, 0.], [.5, -.5, 0.])
        self.assertEqual(self.f.entities['active-0-0'], data)
        self.assertFalse(self.fresh())
        self.assertEqual(self.metric('source-derived-reuses'), 1)
        self.assertEqual(self.metric('network-proof-reuses'), 0)
        self.assertEqual(self.metric('network-build-calls'), 2)

    def test_changed_bounds_effective_name_layer_table_and_unknown_rule_disable_reuse(self):
        for change in ('bounds', 'name', 'layer', 'rule', 'signature'):
            with self.subTest(change=change):
                self.setUp()
                h = self.f.h
                if change == 'bounds':
                    original = h.builtins['EL:ENTITYBOUNDS']
                    h.builtins['EL:ENTITYBOUNDS'] = lambda e: ([[0., 0., 0.], [1., 1., 0.]]
                        if e == 'active-0-0' else original(e))
                elif change == 'name':
                    original = h.builtins['VLA-GET-EFFECTIVENAME']
                    h.builtins['VLA-GET-EFFECTIVENAME'] = lambda e: 'CHANGED' if e == 'active-0-0' else original(e)
                elif change == 'layer':
                    original = h.builtins['TBLSEARCH']
                    h.builtins['TBLSEARCH'] = lambda table, name: ([Pair(6, 'DASHED')]
                        if table == 'LAYER' and name == 'W' else original(table, name))
                elif change == 'rule':
                    self.f.cfg = self.f.call('EL:Put', Symbol('FUTURE-RULE'), 1, self.f.cfg)
                else:
                    snapshot = self.f.get('snapshot', self.result)
                    snapshot = self.f.call('EL:Put', Symbol('SIGNATURE'), ['changed'], snapshot)
                    self.result = self.f.call('EL:Put', Symbol('SNAPSHOT'), snapshot, self.result)
                self.assertFalse(truth(self.f.call('EL:CollectSourceCurrent', self.f.cfg, self.result)))
                self.assertEqual(self.metric('source-derived-reuses'), 0)

    def test_managed_output_is_excluded_but_unmanaged_addition_is_not(self):
        self.f.block('LAMP', 'D', 'new-output', [500., 500., 0.])
        self.f.entities['new-output'].append([-3, ['EL_FIXED_V1', Pair(1000, 'managed')]])
        self.f.selected.append('new-output')
        self.assertTrue(self.fresh())
        self.f.entities['new-output'].pop()
        self.assertFalse(truth(self.f.call('EL:CollectSourceCurrent', self.f.cfg, self.result)))

    def test_owner_command_end_and_callback_epoch_do_not_allow_stale_reuse(self):
        h = self.f.h
        h.builtins['NAMEDOBJDICT'] = lambda: 'OTHER-DWG'
        self.assertFalse(truth(self.f.call('EL:CollectSourceCurrent', self.f.cfg, self.result)))
        h.builtins['NAMEDOBJDICT'] = lambda: 'NOD'
        original = h.builtins['EL:ENTITYBOUNDS']
        def boundary(e):
            self.f.call('EL:FreshBoundary')
            return original(e)
        h.builtins['EL:ENTITYBOUNDS'] = boundary
        with self.assertRaises(RuntimeError):
            self.fresh()
        self.f.call('EL:PerfFinish', Symbol('FAILED'))
        self.assertIsNone(h.lookup('*EL:COLLECTMEMO*'))


class InputOnlyStoreTests(unittest.TestCase):
    def test_source_change_during_placement_rolls_back_and_keeps_saved_inputs(self):
        f = native_fixture.PanelCommandTests(); f.setUp(); f.two_circuits()
        f.h.run("(setq result (EL:Put 'engine 'fixed result))")
        self.assertTrue(truth(f.h.run("(EL:SaveDraft result cfg nil 'cap300)")))
        before = exact(f.h.run('(EL:StoreRead)'))
        source = {'changed': False}
        original = f.h.builtins['COMMAND']
        def command(*args):
            original(*args)
            if args[-1] == 'pause':
                source['changed'] = True
        f.h.builtins['COMMAND'] = command
        f.h.builtins['EL:FRESHRESULT'] = lambda *_: not source['changed']
        self.assertFalse(truth(f.invoke()))
        self.assertEqual(exact(f.h.run('(EL:StoreRead)')), before)
        self.assertFalse(any(key.startswith('native-') for key in f.entities))

    def test_current_inputs_roundtrip_and_other_box_full_snapshot_stays_exact(self):
        f = split_fixture.SplitStoreTests(); f.setUp()
        self.assertTrue(truth(f.get('committed', f.save())))
        original_other = copy.deepcopy(f.call('EL:StoreRecord', 'two'))
        current = f.call('EL:InputRecord', f.call('EL:StoreRecord', 'one'))
        proposed = f.call('EL:StorePutDiagram', current, f.call('EL:StoreRead'))
        self.assertTrue(truth(f.get('committed', f.save(proposed))))
        reopened = f.call('EL:StoreRecord', 'one')
        self.assertEqual(exact(reopened), exact(current))
        self.assertIsNone(f.get('source-signature', reopened))
        self.assertIsNone(f.get('draft-source-signature', reopened))
        self.assertEqual(f.get('input-record-version', reopened), 2)
        self.assertEqual(exact(f.call('EL:StoreRecord', 'two')), exact(original_other))
        self.assertEqual(f.get('custom-extension', reopened), f.get('custom-extension', f.h.lookup('RECORD1')))

    def test_failed_new_root_write_keeps_previous_complete_input_record(self):
        f = split_fixture.SplitStoreTests(); f.setUp()
        self.assertTrue(truth(f.get('committed', f.save())))
        old = copy.deepcopy(f.call('EL:StoreRead'))
        root_entity = f.dictionary['EL_FIXED_SPLIT_V1']
        original = f.h.builtins['VLA-SETXRECORDDATA']
        def fail_root(entity, codes, values):
            if entity == root_entity:
                raise RuntimeError('injected root publication failure')
            return original(entity, codes, values)
        f.h.builtins['VLA-SETXRECORDDATA'] = fail_root
        current = f.call('EL:InputRecord', f.call('EL:StoreRecord', 'one'))
        context = f.save(f.call('EL:StorePutDiagram', current, old))
        self.assertFalse(truth(f.get('outcome', context)))
        self.assertEqual(exact(f.call('EL:StoreRead')), exact(old))

    def test_six_circuit_output_keeps_watts_uids_inputs_and_two_reserves(self):
        f = native_fixture.PanelCommandTests(); f.setUp(); f.two_circuits()
        source = f.h.lookup('RESULT')
        first = f.get('circuits', source)[0]
        circuits = []
        for i in range(6):
            row = first
            for key, value in [('id', f'R{i+1}'), ('circuit-uid', f'U{i+1}'),
                               ('seed-key', [f'W{i+1}', Symbol('OUTLET')]), ('watts', 10+i),
                               ('seed', [[Symbol('KEY'), f'W{i+1}', Symbol('OUTLET')]]),
                               ('number-value', i+1), ('number-text', f'ZE{i+1}')]:
                row = f.call('EL:Put', Symbol(key.upper()), value, row)
            circuits.append(row)
        result = f.call('EL:Put', Symbol('CIRCUITS'), circuits, source)
        f.h.frames[0]['RESULT'] = result
        self.assertTrue(truth(f.invoke()))
        saved = f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        rows = f.get('rows', saved)
        self.assertEqual(len(rows), 8)
        self.assertEqual([f.get('watts', row) for row in rows[:6]], list(range(10, 16)))
        self.assertEqual([f.get('mode', row) for row in rows[6:]], [Symbol('RESERVE')]*2)
        self.assertTrue(all(f.get('circuit-uid', row) for row in rows[:6]))
        self.assertIsNone(f.get('source-signature', saved))
        self.assertEqual(f.get('input-record-version', saved), 2)
        self.assertEqual(len(f.commands), 9)


if __name__ == '__main__':
    unittest.main()
