"""Fixed entry, real panel fill and missing system-variable regressions. Date: 2026-10-11.

Finite CAD/DCL adapters only; native AutoCAD acceptance remains pending.
"""
import unittest
from pathlib import Path
from autolisp_host import Symbol, truth
import test_panel as panel
import test_diagnostics as diagnostics
import test_cad_adapter as adapter


class FixedDiagnosticTests(unittest.TestCase):
    call = panel.PanelTests.call
    get = panel.PanelTests.get
    line = panel.PanelTests.line
    block = panel.PanelTests.block
    plan = panel.PanelTests.plan
    logging = diagnostics.DiagnosticTests.logging

    def setUp(self):
        panel.PanelTests.setUp(self)
        self.logging()
        for name in ('generation', 'fixed', 'diagram-update', 'diagram-commands', 'insert-circuit'):
            self.h.load_definitions(adapter.ROOT / 'src' / f'{name}.lsp')
        self.plan()
        self.h.builtins['EL:DLSNAPSHOT'] = lambda: self.h.run(
            "'((root . \"library-fixture/\") (catalog (schema . EL_DEVICE_LIBRARY_V1) (library-id . \"LIB-FIXTURE\") (revision . 0) (next-id . 1) (devices)) (index) (present))")
        self.tiles, self.dialogs, self.writes, self.variables = {}, [], [], []
        picks = iter([['panel', [0., 0., 0.]], ['w1', [1., 0., 0.]]])

        def getvar(key):
            self.variables.append(key)
            return {'FINGERPRINTGUID': 'guid', 'CDATE': 20261009.12,
                    'MILLISECS': 100}.get(key)  # Unknown variable => nil, including HANDSEED.

        def tile(key, value):
            if not isinstance(value, str):
                raise TypeError('bad argument type: stringp nil')
            self.tiles[key] = value

        def strcat(*values):
            if any(type(value) is not str for value in values):
                raise TypeError('bad argument type: stringp nil')
            return ''.join(values)

        self.h.builtins.update({
            'GETVAR': getvar, 'EL:ENSUREROOT': lambda: True,
            'STRCAT': strcat, 'FINDFILE': lambda path: path if Path(path).exists() else None,
            'EL:PICKMODEL': lambda *args: next(picks),
            'EL:LOADCONFIG': lambda: self.cfg,
            # Date: 2026-10-12. Explicit fixture preset avoids machine registry.
            'EL:PRESETLOAD': lambda: self.cfg,
            'CHR': chr,
            'HANDENT': lambda e: e if e in self.entities else None,
            'EL:REVIEWFIXEDEXITS': lambda result, record: result,
            'EL:CLEARPICKHIGHLIGHTS': lambda: None,
            'EL:CLEARGAPPREVIEW': lambda: None,
            'LOAD_DIALOG': lambda path: 1,
            'NEW_DIALOG': lambda name, number: self.dialogs.append(name) or True,
            'UNLOAD_DIALOG': lambda number: None,
            'SET_TILE': tile, 'MODE_TILE': lambda *args: None,
            'START_LIST': lambda *args: None, 'ADD_LIST': lambda *args: None,
            'END_LIST': lambda: None, 'ACTION_TILE': lambda *args: None,
            'EL:THUMBCAPTURE': lambda block: None,
            'DIMX_TILE': lambda key: 160, 'DIMY_TILE': lambda key: 60,
            'START_IMAGE': lambda key: None, 'END_IMAGE': lambda: None,
            'FILL_IMAGE': lambda *args: None, 'VECTOR_IMAGE': lambda *args: None,
            'START_DIALOG': lambda: 0,  # Cancel must preserve all persistent data.
            'EL:STOREWRITE': lambda value: self.writes.append(value),
            'EL:WRITEDATA': lambda *args: self.writes.append(args),
        })

    def test_first_use_unknown_handseed_reaches_real_panel_without_writes(self):
        self.call('EL:FixedStatPick')
        self.assertEqual(self.dialogs, ['el_panel'])
        self.assertEqual(self.tiles['p_row0'], 'ZE1 | 0W')
        self.assertEqual(self.tiles['b_watts0'], '')
        self.assertEqual(self.writes, [])
        self.assertNotIn('HANDSEED', self.variables)
        log = self.log.read_text(encoding='utf-8')
        for value in ('031', 'PICKS', 'panel', 'w1', 'PREPARE_PANEL', 'PANEL_FILL', 'END'):
            self.assertIn(value, log)
        self.assertFalse(truth(self.h.lookup('*EL:LOGACTIVE*')))

    def test_single_wire_without_devices_returns_feedback_and_logs(self):
        self.selected = ['panel', 'w1']
        alerts, returns = [], []
        self.h.builtins.update({'ALERT': alerts.append,
            'EL:PANELSTARTDIALOG': lambda: returns.append(True),
            'EL:EDITPANEL': lambda *args: self.fail('empty result reached editor')})
        self.call('EL:FixedStatPick')
        self.assertIn('未识别到连接设备', alerts[0])
        self.assertEqual(returns, [True])
        self.assertEqual(self.writes, [])
        self.assertFalse(truth(self.h.lookup('*EL:RESULT*')))
        self.assertIn('NO_CONNECTED_DEVICES', self.log.read_text(encoding='utf-8'))

    def test_empty_device_rows_do_not_call_native_sort(self):
        self.h.builtins['VL-SORT'] = lambda *args: self.fail('empty rows sorted')
        self.assertFalse(truth(self.call('EL:SimpleRows', None, None)))

    def test_new_record_avoids_existing_ids_and_retains_existing_record(self):
        first = self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial'))
        store = self.call('EL:StorePutDiagram', first, self.call('EL:StoreInitial'))
        second = self.call('EL:NewRecord', 'panel', store)
        self.assertNotEqual(self.get('diagram-id', first), self.get('diagram-id', second))
        self.assertEqual(self.call('EL:DiagramForPanel', 'panel', store), first)
        self.assertEqual(self.writes, [])

    def test_panel_fill_failure_reports_stage_and_original_error(self):
        def fail(key, value):
            raise TypeError('bad argument type: stringp nil')
        self.h.builtins['SET_TILE'] = fail
        with self.assertRaisesRegex(TypeError, 'stringp nil') as caught:
            self.call('EL:FixedStatPick')
        # Subset host requires explicit dispatch of AutoCAD's error hook.
        self.call('*ERROR*', str(caught.exception))
        log = self.log.read_text(encoding='utf-8')
        for value in ('PICKS', 'PANEL_FILL', 'ERROR', 'stringp nil', 'END'):
            self.assertIn(value, log)
        self.assertIn('失败阶段', ''.join(self.messages))
        self.assertIn(self.log.as_posix(), ''.join(self.messages))
        self.assertEqual(self.writes, [])
        self.assertFalse(truth(self.h.lookup('*EL:LOGACTIVE*')))
        self.assertIsNone(self.h.lookup('*EL:DIALOGID*'))

    def test_unwritable_log_still_reports_panel_failure_on_command_line(self):
        self.h.builtins['OPEN'] = lambda *args: None
        def fail(*args):
            raise TypeError('bad argument type: stringp nil')
        self.h.builtins['SET_TILE'] = fail
        with self.assertRaisesRegex(TypeError, 'stringp nil') as caught:
            self.call('EL:FixedStatPick')
        self.call('*ERROR*', str(caught.exception))
        text = ''.join(self.messages)
        for value in ('日志写入失败', 'PANEL_FILL', 'stringp nil'):
            self.assertIn(value, text)
        self.assertEqual(self.writes, [])

    def test_missing_drawing_identity_opens_panel_with_stable_fallback(self):
        getvar = self.h.builtins['GETVAR']
        for missing in (None, ''):
            self.h.builtins['GETVAR'] = lambda key: missing if key == 'FINGERPRINTGUID' else getvar(key)
            first = self.get('drawing-uuid', self.call('EL:StoreInitial'))
            self.assertTrue(first.startswith('EL-'))
            self.assertEqual(first, self.get('drawing-uuid', self.call('EL:StoreInitial')))
        self.call('EL:FixedStatPick')
        self.assertEqual(self.dialogs, ['el_panel'])
        self.assertEqual(self.writes, [])

    def test_power_reopen_preserves_legacy_record_identity_and_appends_session(self):
        self.call('EL:FixedStatPick')
        record = self.h.run("'((diagram-id . \"guid/panel/A0\") (source-panel-handle . \"panel\"))")
        store = self.call('EL:StorePutDiagram', record, self.call('EL:StoreInitial'))
        self.h.builtins['EL:STOREREAD'] = lambda: store
        self.h.run('(EL:EditPanel *EL:Result* *EL:FixedConfig*)')
        self.assertEqual(self.dialogs, ['el_panel', 'el_panel'])
        log = self.log.read_text(encoding='utf-8')
        self.assertEqual(log.count('| BEGIN |'), 2)
        self.assertEqual(log.count('| ENTER NEW_RECORD |'), 1)
        self.assertIn('guid/panel/A0', log)
        self.assertEqual(self.writes, [])

    def test_recognition_failure_uses_outer_error_handler(self):
        def fail(*args):
            raise TypeError('recognition stringp nil')
        self.h.builtins['EL:RECOGNIZEFIXED'] = fail
        with self.assertRaisesRegex(TypeError, 'recognition stringp nil') as caught:
            self.call('EL:FixedStatPick')
        self.call('*ERROR*', str(caught.exception))
        log = self.log.read_text(encoding='utf-8')
        for value in ('PICKS', 'RECOGNIZE_FIXED', 'recognition stringp nil', 'END'):
            self.assertIn(value, log)
        self.assertFalse(truth(self.h.lookup('*EL:LOGACTIVE*')))
        self.assertEqual(self.writes, [])


if __name__ == '__main__':
    unittest.main()
