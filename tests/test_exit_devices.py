"""Exit review must expose recognized devices. Date: 2026-10-10."""
import unittest
from autolisp_host import Symbol
import test_fixed_diagnostics as diagnostics
import test_simple_flow as simple


class ExitDeviceTests(unittest.TestCase):
    call = diagnostics.FixedDiagnosticTests.call
    get = diagnostics.FixedDiagnosticTests.get
    line = diagnostics.FixedDiagnosticTests.line
    block = diagnostics.FixedDiagnosticTests.block
    plan = diagnostics.FixedDiagnosticTests.plan
    logging = diagnostics.FixedDiagnosticTests.logging

    def setUp(self):
        diagnostics.FixedDiagnosticTests.setUp(self)
        del self.h.builtins['EL:REVIEWFIXEDEXITS']
        self.lists, self.actions = {}, {}
        self.current_list = None

        def start_list(key):
            self.current_list = key
            self.lists[key] = []

        self.h.builtins.update({
            'START_LIST': start_list,
            'ADD_LIST': lambda value: self.lists[self.current_list].append(value),
            'ACTION_TILE': lambda key, value: self.actions.__setitem__(key, value),
        })






    def test_fixed_entry_keeps_free_end_gap_device_recognition(self):
        self.entities.clear()
        simple.SimpleFlowTests.gap_plan(self)
        result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        self.assertEqual(self.get('devices', self.get('circuits', result)[0]), ['after'])


if __name__ == '__main__':
    unittest.main()
