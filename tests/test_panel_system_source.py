"""Drawing-first system-block preparation through real panel callbacks.

Date: 2026-10-23. Status: focused adapter regression; native CAD acceptance pending.
"""
import copy
import unittest

from autolisp_host import Symbol, truth
import test_panel_library_toggle as layouts


BLOCKS = ['ZYF_Tool_应急照明配电箱图块', 'ZYF_Tool_应急照明配电回路图块']
STYLES = ['_TEL_DIM', 'ICDA-STYLE1']


class PanelSystemSourceTests(unittest.TestCase):
    fixture = layouts.PanelLibraryToggleTests.fixture

    def prepared_fixture(self, expanded):
        f, callbacks, path, opened = self.fixture(expanded)
        self.addCleanup(f.doCleanups)
        self.messages, self.alerts = [], []
        f.h.builtins.update({
            'EL:TEMPLATEREADY': lambda *args: None,
            'EL:DLPANELSUBMISSIONREADY': lambda: True,
            'EL:RECOGNIZEFIXED': lambda *args: self.fail('preparation repeated recognition'),
            'ALERT': self.alerts.append,
            'PRINC': lambda value='': self.messages.append(str(value)),
        })
        return f, callbacks, path, opened

    def snapshot(self, f):
        return copy.deepcopy([f.h.lookup(key) for key in (
            '*EL:PANELDRAFT*', '*EL:PANELPOWERS*', '*EL:PANELCAPACITY*')])

    def invoke(self, f, callbacks, key):
        return f.invoke_action(callbacks, key)

    def test_both_layouts_share_visible_source_buttons_and_missing_rows(self):
        compact = layouts.panel_tiles('el_panel_compact')
        expanded = layouts.panel_tiles('el_panel')
        for key, kind in (('p_system_drawing', 'button'), ('p_system_import', 'button'),
                          ('p_system_blocks', 'text'), ('p_system_styles', 'text'),
                          ('p_system_notice', 'text'), ('p_system_notice1', 'text')):
            self.assertEqual(compact[key], expanded[key])
            self.assertEqual(compact[key]['tile_type'], kind)
        self.assertEqual(compact['p_system_drawing']['label'], '检查本图图块')
        self.assertEqual(compact['p_system_import']['label'], '从图库补入缺项')

    def test_missing_definitions_keep_the_same_dialog_and_show_import_action(self):
        for expanded in (False, True):
            for styles_only in (False, True):
                with self.subTest(expanded=expanded, styles_only=styles_only):
                    f, callbacks, _, _ = self.prepared_fixture(expanded)
                    f.h.step_limit = 2_000_000
                    initial_cfg, before = copy.deepcopy(f.cfg), []
                    table = f.h.builtins['TBLSEARCH']
                    def symbols(kind, name):
                        if kind == 'BLOCK' and name in BLOCKS:
                            return [name] if styles_only else None
                        if kind == 'STYLE' and name in STYLES:
                            return None
                        return table(kind, name)
                    f.h.builtins.update({
                        'TBLSEARCH': symbols,
                        'EL:CAPTUREFIXEDTEMPLATE': lambda *a: self.fail('missing definitions closed the panel'),
                        'EL:SYSTEMIMPORTWORK': lambda *a: self.fail('Generate imported without the source button'),
                    })
                    def generate_then_close():
                        f.call('EL:PanelCapacity', 'p_600')
                        before.append(self.snapshot(f))
                        self.invoke(f, callbacks, 'p_generate')
                        self.assertIsNone(f.closed)
                        after = self.snapshot(f)
                        self.assertEqual(after[0], f.call('EL:GenerationResult', before[0][0]))
                        self.assertEqual(after[1:], before[0][1:])
                        self.assertEqual(f.h.lookup('*EL:PANELCONFIG*'), initial_cfg)
                        self.assertIn('从图库补入缺项', f.tiles['p_system_notice'] + f.tiles['p_system_notice1'])
                        self.assertIn('_TEL_DIM / ICDA-STYLE1', f.tiles['p_system_styles'])
                        self.assertFalse(truth(f.h.lookup('*EL:PANELACTION*')))
                        state = f.call('EL:Get', 'NOD', f.h.lookup('*EL:PANELTEMPLATEDIAGNOSTICS*'))
                        self.assertEqual(f.get('stage', state), Symbol('MISSING-DEFINITIONS'))
                        self.assertEqual(f.get('missing-styles', state), STYLES)
                        self.assertEqual(f.get('missing-blocks', state), None if styles_only else BLOCKS)
                        self.invoke(f, callbacks, 'cancel')
                    f.actions = [generate_then_close]
                    self.assertIsNone(f.dialog())
                    self.assertEqual(len(f.dialogs), 1)
                    self.assertEqual(self.alerts, [])
                    self.assertEqual(f.cfg, initial_cfg)
                    self.assertIsNone(f.h.lookup('*EL:SYSTEMBLOCKSOURCE*'))

    def test_import_prepares_only_then_later_generation_defaults_to_drawing(self):
        for expanded in (False, True):
            with self.subTest(expanded=expanded):
                f, callbacks, _, _ = self.prepared_fixture(expanded)
                initial_cfg, before, sources = copy.deepcopy(f.cfg), [], []
                table = f.h.builtins['TBLSEARCH']
                f.h.builtins['TBLSEARCH'] = lambda kind, name: (
                    [name] if (kind == 'BLOCK' and name in BLOCKS) or
                    (kind == 'STYLE' and name in STYLES) else table(kind, name))
                captured = f.h.run("'((verified . panel-source-fixture))")

                def capture(cfg):
                    sources.append(f.call('EL:SystemBlockSource'))
                    return captured

                f.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = capture

                def import_missing():
                    f.call('EL:PanelCapacity', 'p_600')
                    before.append(self.snapshot(f))
                    self.invoke(f, callbacks, 'p_system_import')
                    self.assertEqual(f.closed, 24)

                def generate_after_prepare():
                    self.assertEqual(self.snapshot(f), before[0])
                    self.assertEqual(f.call('EL:SystemBlockSource'), Symbol('DRAWING'))
                    self.assertIsNone(f.h.lookup('*EL:SYSTEMBLOCKSOURCE*'))
                    self.assertFalse(truth(f.h.lookup('*EL:PANELACTION*')))
                    self.assertTrue(truth(f.h.lookup('*EL:PANELTEMPLATEREADY*')))
                    self.assertEqual(f.h.lookup('*EL:PANELCONFIG*'),
                                     f.call('EL:Put', Symbol('TEMPLATE'), captured, initial_cfg))
                    # A subsequent preparation must not inherit the import permission.
                    f.h.set('*EL:PANELTEMPLATEREADY*', None)
                    self.invoke(f, callbacks, 'p_generate')
                    self.assertEqual(f.closed, 4)

                f.actions = [import_missing, generate_after_prepare]
                result = f.dialog()
                self.assertTrue(truth(f.get('generate', result)))
                self.assertEqual(f.get('capacity', result), Symbol('CAP600'))
                self.assertEqual(f.get('result', result), f.call('EL:GenerationResult', before[0][0]))
                self.assertEqual(f.get('powers', result), before[0][1])
                self.assertEqual(f.get('config', result),
                                 f.call('EL:Put', Symbol('TEMPLATE'), captured, initial_cfg))
                self.assertEqual(sources, [Symbol('LIBRARY'), Symbol('DRAWING')])
                self.assertEqual(len(f.dialogs), 2)
                self.assertEqual(self.alerts, [])
                self.assertEqual(f.cfg, initial_cfg)
                self.assertIsNone(f.h.lookup('*EL:SYSTEMBLOCKSOURCE*'))

    def test_failed_or_cancelled_import_keeps_flushed_edits_capacity_and_result(self):
        for expanded in (False, True):
            for cancelled in (False, True):
                with self.subTest(expanded=expanded, cancelled=cancelled):
                    f, callbacks, _, _ = self.prepared_fixture(expanded)
                    initial_cfg, captured_state = copy.deepcopy(f.cfg), []

                    def capture(cfg):
                        captured_state.append(self.snapshot(f))
                        if cancelled:
                            raise RuntimeError('Function cancelled')
                        f.h.set('*EL:SYSTEMBLOCKNOTICE*', '图库未找到，请核对后重试。')
                        return None

                    f.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = capture

                    def edit_and_import():
                        f.call('EL:PanelCapacity', 'p_1000')
                        if expanded:
                            f.tiles['dl_display'] = '保留的设备名称'
                            f.tiles['dl_watts'] = '17'
                        self.invoke(f, callbacks, 'p_system_import')
                        self.assertEqual(f.closed, 24)

                    def returned():
                        self.assertEqual(self.snapshot(f), captured_state[0])
                        self.assertEqual(f.h.lookup('*EL:PANELCONFIG*'), initial_cfg)
                        self.assertEqual(f.tiles['p_capacity'], 'p_1000')
                        self.assertFalse(truth(f.h.lookup('*EL:PANELTEMPLATEREADY*')))
                        notice = f.tiles['p_system_notice'] + f.tiles['p_system_notice1']
                        self.assertIn('Function cancelled' if cancelled else '图库未找到', notice)
                        state = f.call('EL:Get', 'NOD', f.h.lookup('*EL:PANELTEMPLATEDIAGNOSTICS*'))
                        self.assertEqual(f.get('stage', state), Symbol('PREPARE-FAILED'))
                        self.assertEqual(f.get('source', state), Symbol('LIBRARY'))
                        self.assertIn('Function cancelled' if cancelled else '图库未找到', f.get('message', state))
                        if expanded:
                            self.assertEqual(f.tiles['dl_display'], '保留的设备名称')
                            self.assertEqual(f.tiles['dl_watts'], '17')
                            self.assertEqual(f.get('watts', f.call('EL:DLUIEntry')), 17)
                        self.invoke(f, callbacks, 'cancel')

                    f.actions = [edit_and_import, returned]
                    self.assertIsNone(f.dialog())
                    self.assertEqual(self.alerts, [])
                    self.assertEqual(f.cfg, initial_cfg)
                    self.assertIsNone(f.h.lookup('*EL:SYSTEMBLOCKSOURCE*'))
                    self.assertIn('当前识别结果、功率和容量已保留', ''.join(self.messages))
                    self.assertIn('Function cancelled' if cancelled else '图库未找到',
                                  ''.join(self.messages))

    def test_real_ensure_policy_reports_missing_then_imports_only_by_explicit_button(self):
        for expanded in (False, True):
            with self.subTest(expanded=expanded):
                f, callbacks, _, _ = self.prepared_fixture(expanded)
                initial_cfg = copy.deepcopy(f.cfg)
                target = {'BLOCK': set(), 'STYLE': set()}
                opens, sources = [], []
                captured = f.h.run("'((verified . imported-panel-source-fixture))")
                table, findfile = f.h.builtins['TBLSEARCH'], f.h.builtins['FINDFILE']

                def symbols(kind, name):
                    required = BLOCKS if kind == 'BLOCK' else STYLES if kind == 'STYLE' else []
                    if name in required:
                        return [name] if name in target[kind] else None
                    return table(kind, name)

                def locate(path):
                    if path.endswith('/templates/系统图块库.dwg'):
                        opens.append(('find', path))
                        return path
                    return findfile(path)

                def import_work(path, blocks, styles):
                    opens.append(('import', path, blocks, styles))
                    target['BLOCK'].update(blocks)
                    target['STYLE'].update(styles)
                    return True

                def capture(cfg):
                    sources.append(f.call('EL:SystemBlockSource'))
                    return captured if truth(f.call('EL:EnsureSystemBlocks', BLOCKS, STYLES)) else None

                f.h.builtins.update({
                    'TBLSEARCH': symbols, 'FINDFILE': locate,
                    'VL-STRING-RIGHT-TRIM': lambda chars, value: value.rstrip(chars),
                    'VL-LOAD-COM': lambda: True,
                    'EL:SYSTEMIMPORTWORK': import_work,
                    'EL:CAPTUREFIXEDTEMPLATE': capture,
                })

                def check_drawing():
                    self.invoke(f, callbacks, 'p_system_drawing')
                    self.assertEqual(f.closed, 23)

                def import_missing():
                    self.assertEqual(opens, [])
                    self.assertIn('缺少图块', f.tiles['p_system_blocks'])
                    self.assertIn('缺少样式', f.tiles['p_system_styles'])
                    self.assertEqual(f.h.lookup('*EL:PANELCONFIG*'), initial_cfg)
                    self.invoke(f, callbacks, 'p_system_import')
                    self.assertEqual(f.closed, 24)

                def prepared():
                    self.assertEqual(f.call('EL:SystemBlockSource'), Symbol('DRAWING'))
                    self.assertEqual(f.tiles['p_system_blocks'], '图块：使用本图已有定义')
                    self.assertIn('模板已准备', f.tiles['p_system_styles'])
                    self.assertFalse(truth(f.h.lookup('*EL:PANELACTION*')))
                    self.assertTrue(truth(f.h.lookup('*EL:PANELTEMPLATEREADY*')))
                    self.assertEqual(f.h.lookup('*EL:PANELCONFIG*'),
                                     f.call('EL:Put', Symbol('TEMPLATE'), captured, initial_cfg))
                    self.invoke(f, callbacks, 'cancel')

                f.actions = [check_drawing, import_missing, prepared]
                self.assertIsNone(f.dialog())
                self.assertEqual(sources, [Symbol('DRAWING'), Symbol('LIBRARY')])
                self.assertEqual([event[0] for event in opens], ['find', 'import'])
                self.assertEqual(opens[1][2:], (BLOCKS, STYLES))
                self.assertEqual(target, {'BLOCK': set(BLOCKS), 'STYLE': set(STYLES)})
                self.assertEqual(self.alerts, [])
                self.assertTrue(all(name in ''.join(self.messages) for name in BLOCKS + STYLES))
                self.assertIn('当前输入保留', ''.join(self.messages))
                self.assertIn('所需系统图块和文字样式已导入', ''.join(self.messages))
                self.assertIsNone(f.h.lookup('*EL:SYSTEMBLOCKSOURCE*'))

    def test_switched_drawing_does_not_read_or_export_the_new_drawings_definitions(self):
        f, _, _, _ = self.prepared_fixture(False)
        f.h.set('*EL:PANELSYSTEMOWNER*', 'original-drawing')
        f.h.set('*EL:PANELTEMPLATEREADY*', True)
        f.h.builtins['NAMEDOBJDICT'] = lambda: 'other-drawing'
        f.h.builtins['TBLSEARCH'] = lambda *a: self.fail('read definitions from another drawing')
        state = f.call('EL:PanelSystemRecord', Symbol('PREPARED'), Symbol('LIBRARY'), None)
        self.assertEqual(f.get('stage', state), Symbol('CONTEXT-CHANGED'))
        self.assertFalse(truth(f.get('template-ready', state)))
        contexts = f.h.lookup('*EL:PANELTEMPLATEDIAGNOSTICS*')
        self.assertEqual(f.call('EL:Get', 'original-drawing', contexts), state)
        self.assertIsNone(f.call('EL:Get', 'other-drawing', contexts))

    def test_cancel_never_prepares_or_imports(self):
        for expanded in (False, True):
            with self.subTest(expanded=expanded):
                f, callbacks, _, _ = self.prepared_fixture(expanded)
                f.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = lambda *args: self.fail('cancel prepared template')
                f.h.builtins['EL:SYSTEMIMPORTWORK'] = lambda *args: self.fail('cancel imported library')
                f.actions = [lambda: self.invoke(f, callbacks, 'cancel')]
                self.assertIsNone(f.dialog())
                self.assertEqual(len(f.dialogs), 1)
                self.assertEqual(self.alerts, [])


if __name__ == '__main__':
    unittest.main()
