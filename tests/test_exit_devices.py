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

    def test_actual_command_shows_exit_and_power_in_one_dialog(self):
        def start():
            self.assertEqual(self.dialogs, ['el_panel'])
            self.assertNotIn('f_exits', self.lists)
            self.assertNotIn('f_exits', self.actions)
            self.assertNotIn('f_apply', self.actions)
            self.assertNotIn('f_count0', self.tiles)
            self.assertNotIn('b_name0', self.tiles)
            self.assertEqual(self.tiles['b_watts0'], '')
            return 0
        self.h.builtins['START_DIALOG'] = start
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.dialogs, ['el_panel'])
        self.assertEqual(self.writes, [])

    def test_all_picked_circuits_ignore_previous_exclusions(self):
        self.block('SIGN', 'D', 'c', [0., 10., 0.])
        self.line('out2', [0., 1., 0.], [0., 9., 0.], 'W')
        self.selected += ['c', 'out2']
        result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        circuits = self.get('circuits', result)
        self.assertEqual(len(circuits), 2)
        keys = [self.get('key', self.get('seed', c)) for c in circuits]
        result = self.call('EL:Put', Symbol('EXCLUDED-SEEDS'), keys, result)
        def start():
            draft = self.h.lookup('*EL:PANELDRAFT*')
            self.assertEqual(len(self.get('circuits', draft)), 2)
            self.assertFalse(self.get('excluded-seeds', draft))
            self.assertEqual(self.h.lookup('*EL:FIXEDEXITSELECTION*'), '0 1 ')
            return 1
        self.h.builtins['START_DIALOG'] = start
        response = self.call('EL:PanelDialog', result, self.cfg, None, None)
        self.assertEqual(len(self.get('circuits', self.get('result', response))), 2)

    def test_integrated_preview_returns_to_same_layout_with_draft(self):
        previews = []
        self.h.builtins.update({'GET_TILE': lambda key: self.tiles.get(key, ''),
            'DONE_DIALOG': lambda status: status,
            'EL:FIXEDEXITPREVIEW': lambda result, selection: previews.append(selection)})
        def start():
            if not previews:
                self.tiles['b_watts0'] = '9'
                return self.h.run(self.actions['f_preview'])
            self.assertNotIn('f_exits', self.tiles)
            self.assertEqual(self.tiles['b_watts0'], '9')
            return 0
        self.h.builtins['START_DIALOG'] = start
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.dialogs, ['el_panel', 'el_panel'])
        self.assertEqual(previews, ['0 '])
        self.assertEqual(self.writes, [])

    def test_selection_refresh_and_preview_preserve_selected_devices(self):
        self.block('SIGN', 'D', 'c', [0., 10., 0.])
        self.line('out2', [0., 1., 0.], [0., 9., 0.], 'W')
        self.selected += ['c', 'out2']
        result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        calls = []
        self.h.builtins.update({'EL:FIXEDEXITHIGHLIGHT': lambda result, selection: calls.append(selection),
                               'GETSTRING': lambda *args: ''})

        def start():
            if not calls:
                self.h.frames[0]['$VALUE'] = '0'
                self.h.run(self.actions['f_exits'])
                self.assertEqual(self.tiles['f_count0'], '数量：1')
                return 2
            self.assertEqual(self.tiles['f_exits'], '0')
            self.assertEqual(self.tiles['f_count0'], '数量：1')
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
        self.assertEqual(self.tiles['f_count0'], '数量：2')
        self.h.frames[0]['*EL:FIXEDEXITSELECTION*'] = ''
        self.call('EL:FixedExitDevices')
        self.assertEqual(self.tiles['f_count0'], '')
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
