"""P1 source sampling equivalence and bounded reuse. Date: 2026-10-11."""
import unittest
from autolisp_host import Symbol, truth
import test_panel as fixtures


class FreshnessReuseTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PanelTests()
        self.f.setUp()
        self.h = self.f.h
        self.f.plan()
        self.h.builtins['HANDENT'] = lambda e: e if e in self.f.entities else None
        self.h.builtins['EL:MANAGEDENTITY'] = lambda e: None
        self.h.builtins['GETVAR'] = lambda key: {'DWGNAME':'sample.dwg','DWGPREFIX':'C:/cad/'}.get(key)

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def result(self):
        return self.call('EL:RecognizeFixed', self.f.cfg, 'panel')

    def test_signature_equals_complete_recognition_in_branched_and_gap_networks(self):
        for gap in (False, True):
            with self.subTest(gap=gap):
                if gap:
                    fixtures.simple.SimpleFlowTests.gap_plan(self.f)
                result = self.result()
                fresh = self.call('EL:FixedFreshSnapshot', self.f.cfg, 'panel')
                self.assertEqual(fresh, self.f.get('snapshot', result))

    def test_same_operation_reuses_but_input_and_writes_force_new_sample(self):
        result = self.result()
        scans = []
        self.h.functions[Symbol('EL:TESTFRESHSNAPSHOT')] = self.h.functions[Symbol('EL:FIXEDFRESHSNAPSHOT')]
        def scan(*args):
            scans.append(args)
            return self.h.call(Symbol('EL:TESTFRESHSNAPSHOT'), list(args))
        # Host function dispatch via a wrapper avoids mocking the comparison.
        self.h.builtins['EL:FIXEDFRESHSNAPSHOT'] = scan
        self.h.frames[0]['*EL:FRESHSCOPEENABLED*'] = True
        for _ in range(3):
            self.assertTrue(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.assertEqual(len(scans), 1)
        self.h.builtins['GETSTRING'] = lambda *args: ''
        self.call('EL:PerfInput', Symbol('GETSTRING'), [])
        self.assertTrue(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.assertEqual(len(scans), 2)
        self.h.builtins['TEST-WRITE'] = lambda: True
        self.call('EL:PerfWrite', Symbol('TEST-WRITE'), [])
        self.assertTrue(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.assertEqual(len(scans), 3)

    def test_unscoped_calls_and_rule_changes_are_not_reused(self):
        result = self.result()
        self.assertTrue(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.f.line('w1', [1., 0., 0.], [8., 0., 0.], 'W')
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.h.frames[0]['*EL:FRESHSCOPEENABLED*'] = True
        changed = self.f.call('EL:Put', Symbol('CALIBRATED'), True, self.f.cfg)
        self.assertFalse(truth(self.call('EL:FreshResult', result, changed)))

    def test_input_change_is_detected_even_with_a_previous_successful_sample(self):
        result = self.result()
        self.h.frames[0]['*EL:FRESHSCOPEENABLED*'] = True
        self.assertTrue(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.f.block('LAMP', 'D', 'added', [4., 0., 0.])
        self.f.selected.append('added')
        self.call('EL:FreshBoundary')
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.f.cfg)))


if __name__ == '__main__':
    unittest.main()
