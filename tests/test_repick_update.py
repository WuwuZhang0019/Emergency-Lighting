"""Re-pick shared numbered feeders and update an owned old diagram. Date: 2026-10-13."""
import copy
import unittest
from pathlib import Path

from autolisp_host import Pair, Symbol, truth
import test_fixed_diagnostics as diag
import test_diagram_update as update
import test_circuit_number as numbering
import test_concentrated_trunk as trunk

ROOT = Path(__file__).resolve().parents[1]
pair = numbering.pair


class NumberedFeederTests(unittest.TestCase):
    call = diag.FixedDiagnosticTests.call
    get = diag.FixedDiagnosticTests.get

    def setUp(self):
        self.f = diag.FixedDiagnosticTests()
        self.f.setUp()
        self.h = self.f.h
        self.addCleanup(self.f.doCleanups)
        self.f.entities.clear()
        self.f.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.f.selected = ['panel']
        for direction, feeder, common, handles, numbers in (
                (1, 'D95F', 'D960', ['D969', 'D97E', 'D980'], [1, 2, 3]),
                (-1, 'EDCB', 'ECBF', ['ECC1', 'ECC2', 'ECC5'], [5, 4, 6])):
            self.f.line(feeder, [direction * 1., 0., 0.], [direction * 10., 0., 0.], 'W')
            self.f.line(common, [direction * 10., -12., 0.], [direction * 10., 12., 0.], 'W')
            self.f.selected += [feeder, common]
            for y, handle, number in zip((-12., 0., 12.), handles, numbers):
                self.f.line(handle, [direction * 10., y, 0.], [direction * 29., y, 0.], 'W')
                self.f.entities[handle].append([-3, ['linenum', Pair(1000, f'ZE{number}')]])
                self.f.block('LAMP', 'D', f'lamp{number}', [direction * 30., y, 0.])
                self.f.selected += [handle, f'lamp{number}']
        self.cfg = self.f.cfg

    def recognize(self):
        raw = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        return self.call('EL:PreparedResult', raw, [pair('diagram-id', 'old-diagram')])

    def test_log_two_shared_feeders_become_six_sorted_numbered_circuits(self):
        events = []
        self.h.builtins['EL:LOGEVENT'] = lambda name, data: events.append((name, data))
        network = self.call('EL:SimpleNetwork', self.call('EL:SimpleCollect', self.cfg), self.cfg, 'panel')
        original = self.call('EL:SplitNetwork', network, self.cfg)
        self.assertEqual(len(self.get('circuits', original)), 2)
        conflicted = self.call('EL:ResolveCircuitNumbers', original)
        self.assertFalse(truth(self.call('EL:CircuitNumbersReady', conflicted)))
        self.assertEqual([set(self.get('candidates', self.get('number-evidence', c)))
                          for c in self.get('circuits', conflicted)],
                         [{'ZE1', 'ZE2', 'ZE3'}, {'ZE4', 'ZE5', 'ZE6'}])
        plane = copy.deepcopy(self.f.entities)
        result = self.recognize()
        circuits = self.get('circuits', result)
        self.assertEqual([self.get('circuit-number', c) for c in circuits], [f'ZE{i}' for i in range(1, 7)])
        self.assertTrue(truth(self.call('EL:CircuitNumbersReady', result)))
        self.assertTrue(truth(self.get('complete', result)))
        self.assertEqual([self.get('devices', c) for c in circuits], [[f'lamp{i}'] for i in range(1, 7)])
        self.assertTrue(all(not set(self.get('wires', c)) & {'D95F', 'D960', 'EDCB', 'ECBF'} for c in circuits))
        self.assertEqual(self.f.entities, plane)
        self.assertTrue(truth(self.call('EL:FreshResult', result, self.cfg)))
        self.assertEqual(sum(name == 'CIRCUIT_NUMBER_BRANCH_SPLIT' for name, _ in events), 2)

    def test_serial_different_numbers_remain_a_real_conflict(self):
        self.f.entities.clear()
        self.f.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.f.block('LAMP', 'D', 'lamp', [30., 0., 0.])
        self.f.selected = ['panel', 'lamp']
        for handle, a, b, number in [('feed', 1., 10., None), ('first', 10., 20., 1), ('second', 20., 29., 2)]:
            self.f.line(handle, [a, 0., 0.], [b, 0., 0.], 'W')
            self.f.selected.append(handle)
            if number:
                self.f.entities[handle].append([-3, ['linenum', Pair(1000, f'ZE{number}')]])
        result = self.recognize()
        self.assertEqual(len(self.get('circuits', result)), 1)
        self.assertFalse(truth(self.call('EL:CircuitNumbersReady', result)))

    def test_unmarked_arm_is_not_dropped_to_suppress_conflict(self):
        self.f.entities['D980'].pop()
        result = self.recognize()
        circuits = self.get('circuits', result)
        self.assertFalse(truth(self.call('EL:CircuitNumbersReady', result)))
        devices = {device for c in circuits for device in self.get('devices', c)}
        self.assertEqual(devices, {f'lamp{i}' for i in range(1, 7)})

    def test_same_native_number_on_independent_arms_still_blocks_generation(self):
        self.f.entities['ECC2'][-1] = [-3, ['linenum', Pair(1000, 'ZE1')]]
        result = self.recognize()
        self.assertFalse(truth(self.call('EL:CircuitNumbersReady', result)))

    def test_regular_repick_reaches_panel_with_native_branches_and_saved_target(self):
        seen = []
        picks = iter([['panel', [0., 0., 0.]]] + [[key, [10., y, 0.]] for key, y in [('D969', -12.), ('D97E', 0.), ('D980', 12.)]] + [[key, [-10., y, 0.]] for key, y in [('ECC1', -12.), ('ECC2', 0.), ('ECC5', 12.)]] + [None])
        record = [pair('diagram-id', 'old-diagram'), pair('source-panel-handle', 'panel'), pair('panel-number', 'ALE1')]
        self.h.builtins.update({'EL:STOREREAD': lambda: [pair('diagrams', [record])],
                               'EL:PICKMODEL': lambda *args: next(picks),
                               'EL:EDITPANEL': lambda result, cfg: seen.append(result)})
        self.call('EL:FixedStatPick')
        self.assertEqual(len(seen), 1)
        result = self.call('EL:PreparedResult', seen[0], record)
        self.assertEqual([self.get('circuit-number', c) for c in self.get('circuits', result)],
                         [f'ZE{i}' for i in range(1, 7)])
        self.assertEqual(self.get('panel-number', result), 'ALE1')
        self.assertEqual(self.get('update-diagram-id', result), 'old-diagram')
        self.assertEqual(self.f.writes, [])


class RepickTargetTests(unittest.TestCase):
    call = diag.FixedDiagnosticTests.call
    get = diag.FixedDiagnosticTests.get

    def setUp(self):
        self.f = update.UpdateTests()
        self.f.setUp()
        self.h = self.f.h
        self.h.load_definitions(ROOT / 'src/diagram-commands.lsp')
        self.addCleanup(self.f.doCleanups)
        self.record = self.h.lookup('RECORD')
        self.store = self.call('EL:StorePutDiagram', self.record, self.h.lookup('STORE'))

    def test_same_source_reuses_record_without_any_extra_pick(self):
        self.h.builtins['EL:PICKMODEL'] = lambda *args: self.fail('exact source must not repick output')
        self.assertEqual(self.call('EL:RepickRecord', self.get('source-panel-handle', self.record), self.store), self.record)

    def test_new_source_pick_does_not_rebind_an_old_output(self):
        picks = []
        self.h.builtins['EL:PICKMODEL'] = lambda *args: picks.append(args) or ['panel', [0., 0., 0.]]
        record = self.call('EL:RepickRecord', 'new-source', self.store)
        self.assertIsNone(record)
        self.assertEqual(picks, [])
        self.assertEqual(self.get('source-panel-handle', self.record), 'source')
        self.assertEqual(len(self.get('diagrams', self.store)), 1)

    def test_foreign_output_is_rejected_and_enter_explicitly_creates_new(self):
        picks = iter([['b0', [0., 0., 0.]], None])
        self.h.builtins['EL:PICKMODEL'] = lambda *args: next(picks)
        self.assertIsNone(self.call('EL:RepickRecord', 'new-source', self.store))
        self.assertEqual(len(self.get('diagrams', self.store)), 1)

    def test_changed_target_record_is_not_replaced_or_fallback_created(self):
        result = [pair('panel', 'new-source'), pair('update-diagram-id', self.get('diagram-id', self.record)),
                  pair('update-source-panel', 'wrong-source')]
        with self.assertRaises(RuntimeError):
            self.call('EL:RecordForResult', result, self.store)

    def test_explicit_old_record_cannot_overwrite_current_new_source_record(self):
        other = [pair('diagram-id', 'other'), pair('source-panel-handle', 'new-source')]
        store = self.call('EL:StorePutDiagram', other, self.store)
        result = [pair('panel', 'new-source'), pair('update-diagram-id', self.get('diagram-id', self.record)),
                  pair('update-source-panel', 'source')]
        selected=self.call('EL:RecordForResult', result, store)
        self.assertEqual(self.get('source-panel-handle',selected),'new-source')
        self.assertEqual(self.get('diagram-id',self.call('EL:DiagramForPanel','new-source',store)),'other')

    def test_actual_update_retains_old_panel_and_changes_power_at_original_position(self):
        result = self.call('EL:Put', Symbol('PANEL'), 'new-source', self.h.lookup('RESULT'))
        result = self.call('EL:Put', Symbol('UPDATE-DIAGRAM-ID'), self.get('diagram-id', self.record), result)
        result = self.call('EL:Put', Symbol('UPDATE-SOURCE-PANEL'), 'source', result)
        record = self.call('EL:RecordForResult', result, self.store)
        before = copy.deepcopy(self.f.entities['panel'])
        self.h.set(Symbol('RESULT'), result)
        self.h.set(Symbol('RECORD'), record)
        self.h.run("""(setq result (EL:Put 'circuits (cons (EL:Put 'watts 47 (car cs)) (cdr cs)) result)
          plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))""")
        updated = self.f.update()
        self.assertEqual(self.get('panel-output-handle', updated), 'panel')
        self.assertEqual(self.f.entities['panel'], before)
        self.assertEqual(self.get('source-panel-handle', updated), 'new-source')
        self.assertIn(('t0', '47W'), self.f.writes)
        self.assertFalse(any(e.startswith('new-block-') for e in self.f.entities))

    def prepare_sync(self):
        self.f.install_sync()
        self.h.run("""(setq result (EL:Put 'panel "new-source" (EL:Put 'update-diagram-id "d1"
          (EL:Put 'update-source-panel "source" result))))
          (setq result (EL:Put 'circuits (cons (EL:Put 'watts 47 (car (EL:Get 'circuits result)))
            (cdr (EL:Get 'circuits result))) result))""")

    def test_real_sync_writes_replacement_under_same_id_without_new_panel(self):
        self.prepare_sync()
        before = copy.deepcopy(self.f.entities['panel'])
        self.assertTrue(truth(self.h.run("(EL:SyncDiagram result nil nil 'cap300 T nil)")))
        store = self.call('EL:StoreRead')
        self.assertEqual(len(self.get('diagrams', store)), 1)
        record = self.call('EL:DiagramForPanel', 'new-source', store)
        self.assertEqual(self.get('diagram-id', record), 'd1')
        self.assertEqual(self.get('panel-output-handle', record), 'panel')
        self.assertEqual(self.f.entities['panel'], before)
        self.assertIn(('t0', '47W'), self.f.writes)
        self.assertFalse(any(e.startswith('new-block-') for e in self.f.entities))

    def test_replacement_write_failure_rolls_back_old_output_and_binding(self):
        self.prepare_sync()
        before = copy.deepcopy((self.f.entities, self.f.dictionary, self.f.dynamic))
        self.h.builtins['EL:STOREWRITE'] = lambda *args: None
        self.assertFalse(truth(self.h.run("(EL:SyncDiagram result nil nil 'cap300 T nil)")))
        self.assertEqual((self.f.entities, self.f.dictionary, self.f.dynamic), before)

    def test_saved_trunk_is_replaced_by_explicit_starts_with_old_target(self):
        f = trunk.TrunkTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        seen = []
        record = [pair('diagram-id', 'd'), pair('source-panel-handle', 'panel'), pair('config', f.cfg)]
        store = [pair('diagrams', [record])]
        picks = iter([['panel', [0., 0., 0.]]] + [[f'w{i}', [10., y, 0.]] for i, y in enumerate((-12., -6., 0., 6., 12.))] + [None])
        f.h.builtins.update({'EL:STOREREAD': lambda: store,
                            'EL:PICKMODEL': lambda *args: next(picks),
                            'EL:EDITPANEL': lambda result, cfg: seen.append((result, cfg))})
        f.call('EL:FixedStatPick')
        self.assertEqual(len(seen), 1)
        f.assert_five(seen[0][0])
        self.assertIsNone(f.get('concentrated-trunk', seen[0][1]))
        self.assertEqual(len(f.get('circuit-starts', seen[0][1])), 5)
        self.assertEqual(f.get('update-diagram-id', seen[0][0]), 'd')


if __name__ == '__main__':
    unittest.main()
