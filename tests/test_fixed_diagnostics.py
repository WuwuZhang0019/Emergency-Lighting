"""Fixed entry, real panel fill and missing system-variable regressions. Date: 2026-10-09.

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
        for name in ('fixed', 'diagram-update', 'diagram-commands'):
            self.h.load_definitions(adapter.ROOT / 'src' / f'{name}.lsp')
        self.plan()
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
            'START_DIALOG': lambda: 0,  # Cancel must preserve all persistent data.
            'EL:STOREWRITE': lambda value: self.writes.append(value),
            'EL:WRITEDATA': lambda *args: self.writes.append(args),
        })

    def test_first_use_unknown_handseed_reaches_real_panel_without_writes(self):
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.dialogs, ['el_panel'])
        self.assertIn('实际', self.tiles['p_row0'])
        self.assertEqual(self.tiles['p_watts'], '')
        self.assertEqual(self.writes, [])
        self.assertNotIn('HANDSEED', self.variables)
        log = self.log.read_text(encoding='utf-8')
        for value in ('026', 'PICKS', 'panel', 'w1', 'PREPARE_PANEL', 'PANEL_FILL', 'END'):
            self.assertIn(value, log)
        self.assertFalse(truth(self.h.lookup('*EL:LOGACTIVE*')))

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
            self.h.run('(c:ELSTAT)')
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
            self.h.run('(c:ELSTAT)')
        self.call('*ERROR*', str(caught.exception))
        text = ''.join(self.messages)
        for value in ('日志写入失败', 'PANEL_FILL', 'stringp nil'):
            self.assertIn(value, text)
        self.assertEqual(self.writes, [])

    def test_missing_drawing_identity_stops_with_specific_message_and_log(self):
        getvar = self.h.builtins['GETVAR']
        self.h.builtins['GETVAR'] = lambda key: None if key == 'FINGERPRINTGUID' else getvar(key)
        with self.assertRaisesRegex(RuntimeError, 'quit / exit abort') as caught:
            self.h.run('(c:ELSTAT)')
        self.call('*ERROR*', str(caught.exception))
        self.assertIn('图纸标识或来源箱体句柄为空', ''.join(self.messages))
        self.assertIn('NEW_RECORD', self.log.read_text(encoding='utf-8'))
        self.assertEqual(self.dialogs, [])
        self.assertEqual(self.writes, [])

    def test_power_reopen_preserves_legacy_record_identity_and_appends_session(self):
        self.h.run('(c:ELSTAT)')
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
            self.h.run('(c:ELSTAT)')
        self.call('*ERROR*', str(caught.exception))
        log = self.log.read_text(encoding='utf-8')
        for value in ('PICKS', 'RECOGNIZE_FIXED', 'recognition stringp nil', 'END'):
            self.assertIn(value, log)
        self.assertFalse(truth(self.h.lookup('*EL:LOGACTIVE*')))
        self.assertEqual(self.writes, [])


if __name__ == '__main__':
    unittest.main()
