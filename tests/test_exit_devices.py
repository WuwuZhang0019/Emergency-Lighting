"""Exit review must expose recognized devices. Date: 2026-10-09."""
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

    def test_actual_command_shows_devices_before_and_after_exit_confirmation(self):
        def start():
            if self.dialogs[-1] == 'el_fixed_exits':
                self.assertIn('已识别设备 2 个', self.lists['f_exits'][0])
                self.assertEqual(self.lists['f_devices'], ['LAMP\t2'])
                self.assertIn('已识别 2 个设备', self.tiles['f_status'])
                return 1
            self.assertEqual(self.lists['p_devices'], ['LAMP\t2\t待填写'])
            return 0
        self.h.builtins['START_DIALOG'] = start
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.dialogs, ['el_fixed_exits', 'el_panel'])
        self.assertEqual(self.writes, [])

    def test_selection_refresh_and_preview_preserve_selected_devices(self):
        self.block('SIGN', 'D', 'c', [0., 10., 0.])
        self.line('out2', [0., 1., 0.], [0., 9., 0.], 'W')
        self.selected += ['c', 'out2']
        result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        calls = []
        self.h.builtins.update({'EL:EXITHIGHLIGHT': lambda selection: calls.append(selection),
                               'GETSTRING': lambda *args: ''})

        def start():
            if not calls:
                self.h.frames[0]['$VALUE'] = '0'
                self.h.run(self.actions['f_exits'])
                self.assertEqual(self.lists['f_devices'], ['SIGN\t1'])
                return 2
            self.assertEqual(self.tiles['f_exits'], '0')
            self.assertEqual(self.lists['f_devices'], ['SIGN\t1'])
            return 1
        self.h.builtins['START_DIALOG'] = start
        reviewed = self.call('EL:ReviewFixedExits', result, None)
        self.assertEqual(len(self.get('circuits', reviewed)), 1)
        self.assertEqual(self.get('devices', self.get('circuits', reviewed)[0]), ['c'])

    def test_empty_and_shared_devices_are_reported_without_invented_counts(self):
        result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        circuit = self.get('circuits', result)[0]
        result = self.call('EL:Put', Symbol('CIRCUITS'), [circuit, circuit], result)
        self.h.frames[0].update({'*EL:FIXEDEXITRESULT*': result,
            '*EL:EXITSNAPSHOT*': self.get('snapshot', result), '*EL:FIXEDEXITSELECTION*': '0 1'})
        self.call('EL:FixedExitDevices')
        self.assertEqual(self.lists['f_devices'], ['LAMP\t2'])
        self.h.frames[0]['*EL:FIXEDEXITSELECTION*'] = ''
        self.call('EL:FixedExitDevices')
        self.assertEqual(self.lists['f_devices'], [])
        self.assertIn('尚未选择出线', self.tiles['f_status'])
        empty = self.call('EL:Put', Symbol('DEVICES'), None, circuit)
        self.h.frames[0]['*EL:FIXEDEXITRESULT*'] = self.call('EL:Put', Symbol('CIRCUITS'), [empty], result)
        self.h.frames[0]['*EL:FIXEDEXITSELECTION*'] = '0'
        self.call('EL:FixedExitDevices')
        self.assertIn('未识别到设备', self.tiles['f_status'])

    def test_fixed_entry_keeps_free_end_gap_device_recognition(self):
        self.entities.clear()
        simple.SimpleFlowTests.gap_plan(self)
        result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        self.assertEqual(self.get('devices', self.get('circuits', result)[0]), ['after'])


if __name__ == '__main__':
    unittest.main()
