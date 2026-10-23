"""Placement timing preserves CAD output and rollback. Date: 2026-10-21.

Status: focused adapter checks; synthetic clocks are not native CAD timings.
"""
import copy
import unittest

from autolisp_host import Symbol, truth
import test_cckk_panel_command as native


class PlacementTimingTests(unittest.TestCase):
    def setUp(self):
        self.f = native.PanelCommandTests()
        self.f.setUp()
        self.f.two_circuits()
        self.f.install_view()
        self.h = self.f.h
        self.clock = 0
        getvar = self.h.builtins['GETVAR']
        command = self.h.builtins['COMMAND']
        dynamic = self.h.builtins['EL:SETDYNAMICVALUE']
        entmake = self.h.builtins['ENTMAKE']

        def insert(*args):
            self.clock += 100 if args[-1] == 'pause' else 5
            return command(*args)

        def set_dynamic(*args):
            self.clock += 7
            return dynamic(*args)

        def make_text(*args):
            self.clock += 2
            return entmake(*args)

        self.h.builtins.update({
            'GETVAR': lambda key: self.clock if key == 'MILLISECS' else getvar(key),
            'COMMAND': insert,
            'EL:SETDYNAMICVALUE': set_dynamic,
            'ENTMAKE': make_text,
        })
        self.before = copy.deepcopy((self.f.entities, self.f.dictionary, self.f.dynamic))
        self.call('EL:PerfStart', 'ELSTAT')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, record):
        return self.f.get(key, record)

    def field(self, key, record):
        return self.call('EL:Get', key, record)

    def invoke(self, placement_only=True):
        self.h.frames[0]['*EL:PLACEMENTONLY*'] = placement_only
        return self.f.invoke()

    def stage(self, name):
        return self.field(name, self.h.lookup('*EL:PERFSTAGES*'))

    def rows(self, name):
        return sorted((r for r in self.h.lookup('*EL:MONITORROWS*') or []
                       if self.get('stage', r) == name), key=lambda r: self.get('id', r))

    def mark(self, name):
        return self.field(name, self.h.lookup('*EL:PERFMARKS*'))

    def assert_closed(self):
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))
        self.assertEqual(self.h.lookup('*EL:PERFWAITDEPTH*'), 0)
        self.assertEqual(self.f.variables, self.f.original)
        for flag in ('OPEN', 'DIRTY', 'RUNNING'):
            self.assertFalse(truth(self.h.lookup('*EL:TRANSACTION' + flag + '*')))

    def assert_rolled_back(self):
        self.assertEqual((self.f.entities, self.f.dictionary, self.f.dynamic), self.before)
        self.assert_closed()

    def test_success_distinguishes_native_dynamic_batch_and_required_cleanup(self):
        self.assertTrue(truth(self.invoke()))
        self.f.assert_two_circuit_output()
        # The native drag interval remains mixed CAD/user time. Fixed inserts,
        # state switches and text construction have independent measured work.
        self.assertEqual(self.get('inclusive-ms', self.stage('PLACEMENT_INPUT')), 100)
        self.assertEqual(self.get('inclusive-ms', self.stage('NATIVE_INSERT')), 20)
        self.assertEqual(self.get('calls', self.stage('NATIVE_INSERT')), 4)
        self.assertEqual(self.get('inclusive-ms', self.stage('PANEL_DYNAMIC_SET')), 7)
        self.assertEqual(self.get('inclusive-ms', self.stage('CIRCUIT_DYNAMIC_SET')), 28)
        self.assertEqual(self.get('calls', self.stage('CREATE_POWER_TEXT')), 2)
        self.assertEqual(self.get('inclusive-ms', self.stage('CREATE_POWER_TEXT')), 4)
        self.assertEqual(self.get('inclusive-ms', self.stage('CREATE_CAPTIONS')), 14)
        ordered = ('PLACEMENT_INPUT', 'PANEL_DYNAMIC_SET', 'PLACEMENT_PLAN_REBUILD',
                   'PLACEMENT_TEMPLATE_VERIFY', 'PLACEMENT_NUMBER_VERIFY',
                   'PLACEMENT_LIBRARY_VERIFY', 'PLACEMENT_SOURCE_VERIFY',
                   'CREATE_CIRCUITS', 'CREATE_CAPTIONS', 'DIAGRAM_FINALIZE',
                   'TX_MARKER_CLEANUP', 'TX_COMMIT')
        ids = [self.get('id', self.rows(name)[0]) for name in ordered]
        self.assertEqual(ids, sorted(ids))
        captions = self.rows('CREATE_CAPTIONS')[0]
        finalize = self.rows('DIAGRAM_FINALIZE')[0]
        self.assertEqual(self.mark('placement-confirmed')[0], 100)
        self.assertEqual(self.mark('graphics-complete')[0],
                         self.get('start', captions) + self.get('elapsed-ms', captions))
        self.assertEqual(self.get('start', finalize), self.mark('graphics-complete')[0])
        self.assertEqual(self.field('master-write-attempts', self.h.lookup('*EL:PERFMETRICS*')), 0)
        self.assertFalse(truth(self.stage('SAVE_CREATED_DIAGRAM')))
        self.assertEqual(self.f.zoomed, [])
        self.assertEqual(self.f.regenerated, [])
        self.assert_closed()

    def test_legacy_finalize_keeps_required_save_after_graphics_complete(self):
        # Keep the real DWG writer, but observe the native boundary it reaches.
        self.h.functions[Symbol('TEST:STOREWRITE')] = self.h.functions[Symbol('EL:STOREWRITE')]
        seen = []

        def save(store):
            seen.append(truth(self.mark('graphics-complete')))
            self.clock += 11
            return self.call('TEST:STOREWRITE', store)

        self.h.builtins['EL:STOREWRITE'] = save
        self.assertTrue(truth(self.invoke(False)))
        self.f.assert_two_circuit_output()
        self.assertEqual(seen, [True])
        self.assertEqual(self.get('calls', self.stage('SAVE_CREATED_DIAGRAM')), 1)
        self.assertGreaterEqual(self.get('inclusive-ms', self.stage('DIAGRAM_FINALIZE')), 11)
        self.assertFalse(truth(self.stage('PLACEMENT_SOURCE_VERIFY')))
        self.assert_closed()

    def test_native_cancel_unwinds_wait_without_claiming_placement_or_graphics(self):
        self.f.fail_at = 1
        self.assertFalse(truth(self.invoke()))
        self.assertEqual(self.get('interrupted', self.stage('PLACEMENT_INPUT')), 1)
        self.assertFalse(truth(self.stage('PANEL_DYNAMIC_SET')))
        self.assertFalse(truth(self.mark('placement-confirmed')))
        self.assertFalse(truth(self.mark('graphics-complete')))
        self.assert_rolled_back()

    def test_dynamic_failure_keeps_failed_stage_and_rolls_back_partial_rows(self):
        dynamic = self.h.builtins['EL:SETDYNAMICVALUE']

        def fail_second_row(entity, *args):
            if entity == 'native-3':
                raise RuntimeError('dynamic native failure')
            return dynamic(entity, *args)

        self.h.builtins['EL:SETDYNAMICVALUE'] = fail_second_row
        self.assertFalse(truth(self.invoke()))
        self.assertEqual(self.get('interrupted', self.stage('CIRCUIT_DYNAMIC_SET')), 1)
        self.assertEqual(self.get('interrupted', self.stage('CREATE_CIRCUITS')), 1)
        self.assertEqual(self.get('calls', self.stage('NATIVE_INSERT')), 2)
        self.assertEqual(self.get('calls', self.stage('CREATE_POWER_TEXT')), 1)
        self.assertFalse(truth(self.stage('CREATE_CAPTIONS')))
        self.assertFalse(truth(self.mark('graphics-complete')))
        self.assert_rolled_back()

    def test_source_changed_after_placement_stops_before_rows(self):
        def current(*args):
            return not truth(self.mark('placement-confirmed'))

        self.h.builtins['EL:FRESHRESULT'] = current
        self.assertFalse(truth(self.invoke()))
        self.assertEqual(self.get('calls', self.stage('PLACEMENT_TEMPLATE_VERIFY')), 1)
        self.assertEqual(self.get('calls', self.stage('PLACEMENT_SOURCE_VERIFY')), 1)
        self.assertFalse(truth(self.stage('CREATE_CIRCUITS')))
        self.assertFalse(truth(self.mark('graphics-complete')))
        self.assert_rolled_back()

    def test_cleanup_failure_does_not_turn_completed_graphics_into_committed_output(self):
        self.h.builtins['DICTREMOVE'] = lambda *args: None
        self.assertFalse(truth(self.invoke()))
        self.assertTrue(truth(self.mark('graphics-complete')))
        self.assertEqual(self.get('interrupted', self.stage('TX_MARKER_CLEANUP')), 1)
        self.assertFalse(truth(self.stage('TX_COMMIT')))
        self.assert_rolled_back()


if __name__ == '__main__':
    unittest.main()
