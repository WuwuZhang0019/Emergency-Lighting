"""Expandable panel with strict finite DCL tiles and real catalogs. Date: 2026-10-16.

Native AutoCAD sizing, focus and screen placement still need manual acceptance.
"""
import json
from pathlib import Path
import re
import unittest

from autolisp_host import Symbol, truth
import test_post_stat_workflow as workflow

ROOT = Path(__file__).resolve().parents[1]


def panel_tiles(name):
    """Resolve the actual DCL subassemblies; absent tiles are errors in callbacks."""
    source = (ROOT / 'ui/power.dcl').read_text(encoding='utf-8')
    tokens = re.findall(r'//[^\n]*|"(?:\\.|[^"\\])*"|[A-Za-z_][\w]*|[0-9.]+|[:;{}=]', source)
    tokens = [token for token in tokens if not token.startswith('//')]
    cursor, definitions = 0, {}

    def body(kind):
        nonlocal cursor
        assert tokens[cursor] == '{'
        cursor += 1
        attributes, children = {}, []
        while tokens[cursor] != '}':
            token = tokens[cursor]
            cursor += 1
            if token == ':':
                base = tokens[cursor]
                cursor += 1
                children.append(body(base))
            elif tokens[cursor] == '=':
                value = tokens[cursor + 1]
                attributes[token] = json.loads(value) if value.startswith('"') else value
                assert tokens[cursor + 2] == ';'
                cursor += 3
            else:
                assert tokens[cursor] == ';'
                cursor += 1
                children.append((token, {}, []))
        cursor += 1
        return kind, attributes, children

    while cursor < len(tokens):
        identity = tokens[cursor]
        assert tokens[cursor + 1] == ':'
        base = tokens[cursor + 2]
        cursor += 3
        definitions[identity] = body(base)

    resolved = {}

    def visit(node):
        kind, attributes, children = node
        if kind in definitions:
            visit(definitions[kind])
        if 'key' in attributes:
            key = attributes['key']
            assert key not in resolved, f'duplicate DCL key: {key}'
            resolved[key] = attributes
        for child in children:
            visit(child)

    visit(definitions[name])
    return resolved


class PanelLibraryToggleTests(unittest.TestCase):
    def fixture(self, expanded=False):
        f = workflow.PostStatWorkflowTests()
        f.setUp()
        path = workflow.install_library_files(f, self)
        f.h.set('*EL:PANELLIBRARYEXPANDED*', True if expanded else None)
        callbacks, opened, live = {}, [], {}
        screen_position = [240, 110]

        def check(key):
            self.assertIn(key, live, f'touched absent tile {key}')

        def new_dialog(name, handle, *placement):
            nonlocal live
            live = panel_tiles(name)
            callbacks.clear()
            f.tiles.clear()
            f.tiles.update({key: attributes.get('value', '') for key, attributes in live.items()})
            f.dialogs.append(name)
            opened.append((name, placement))
            return True

        def set_tile(key, value):
            check(key)
            self.assertIsInstance(value, str)
            f.tiles[key] = value

        def get_tile(key):
            check(key)
            return f.tiles[key]

        def action_tile(key, action):
            check(key)
            callbacks[key] = action

        def done(status):
            f.closed = status
            return screen_position[:]

        f.h.builtins.update({
            'NEW_DIALOG': new_dialog, 'SET_TILE': set_tile, 'GET_TILE': get_tile,
            'MODE_TILE': lambda key, mode: check(key), 'ACTION_TILE': action_tile,
            'START_LIST': lambda key, *args: check(key),
            'START_IMAGE': check, 'DONE_DIALOG': done,
        })
        return f, callbacks, path, opened

    def invoke(self, f, callbacks, key):
        return f.invoke_action(callbacks, key)

    def test_layouts_share_left_controls_and_compact_has_no_library_tiles(self):
        compact, expanded = panel_tiles('el_panel_compact'), panel_tiles('el_panel')
        self.assertTrue(set(compact) < set(expanded))
        for key, attributes in compact.items():
            self.assertEqual(attributes, expanded[key])
        for key in ('p_pick', 'p_trunk', 'p_capacity', 'f_preview', 'p_generate',
                    'p_library_toggle', 'p_diagnostic', 'p_diagnostic_path', 'cancel'):
            self.assertIn(key, compact)
        self.assertFalse(any(key.startswith('dl_') for key in compact))
        self.assertNotIn('p_block_library_open', compact)
        for key in ('dl_save', 'dl_import', 'dl_export', 'dl_open', 'dl_rows', 'p_block_library_open'):
            self.assertIn(key, expanded)

    def test_default_home_expands_collapses_and_preserves_position_without_writing(self):
        f, callbacks, path, opened = self.fixture()
        original = path.read_bytes()
        f.h.builtins['EL:RECOGNIZEFIXED'] = lambda *args: self.fail('toggle re-recognized the drawing')

        def expand():
            self.assertIn('展开设备库', f.tiles['p_library_toggle'])
            self.assertNotIn('dl_rows', callbacks)
            self.invoke(f, callbacks, 'p_library_toggle')

        def collapse():
            self.assertIn('收起设备库', f.tiles['p_library_toggle'])
            self.assertIn('dl_rows', callbacks)
            self.invoke(f, callbacks, 'p_library_toggle')

        f.actions = [expand, collapse, lambda: self.invoke(f, callbacks, 'cancel')]
        self.assertIsNone(f.call('EL:PanelDialog', None, None, None, None))
        self.assertEqual(f.dialogs, ['el_panel_compact', 'el_panel', 'el_panel_compact'])
        self.assertEqual(opened[0][1], ())
        for _, placement in opened[1:]:
            self.assertEqual(placement, ('', [240, 110]))
        self.assertEqual(path.read_bytes(), original)
        self.assertIsNone(f.h.lookup('*EL:PANELLIBRARYEXPANDED*'))

    def test_collapse_saves_current_fields_and_restores_selection_search_and_capacity(self):
        f, callbacks, path, _ = self.fixture(expanded=True)
        snapshot = f.call('EL:DLSnapshot')
        catalog = f.get('catalog', snapshot)
        row = f.call('EL:DLEntryNew', catalog, 'BACKUP')
        for key, value in {'display': '备用照明', 'watts': 8, 'ground-confirmed': True,
                           'active': True, 'status': Symbol('READY'), 'asset-revision': 1,
                           'block-file': 'assets/ELDEV2/1/block.dwg',
                           'legend-file': 'assets/ELDEV2/1/legend.sld',
                           'legend-size': [800, 600], 'legend-checksum': 'sld-123-31'}.items():
            row = f.call('EL:Put', Symbol(key.upper()), value, row)
        self.assertTrue(truth(f.call('EL:DLCommit', snapshot, f.call('EL:DLUpsert', catalog, row))))

        def edit():
            f.tiles['dl_rows'] = '1'
            self.invoke(f, callbacks, 'dl_rows')
            f.tiles.update(dl_watts='12', dl_display='保留的备用照明', dl_aliases='备用别名',
                           dl_ground='2', dl_query='BACKUP', dl_deleted='1')
            f.call('EL:PanelCapacity', 'p_600')
            self.invoke(f, callbacks, 'p_library_toggle')

        def expand():
            state = f.h.lookup('*EL:DLUISTATE*')
            self.assertEqual(f.get('selected', state), 'ELDEV2')
            self.assertEqual(f.get('query', state), 'BACKUP')
            self.assertEqual(f.tiles['p_capacity'], 'p_600')
            self.invoke(f, callbacks, 'p_library_toggle')

        def check_restored():
            for key, value in {'dl_watts': '12', 'dl_display': '保留的备用照明',
                               'dl_aliases': '备用别名', 'dl_ground': '2',
                               'dl_query': 'BACKUP', 'dl_deleted': '1', 'p_capacity': 'p_600'}.items():
                self.assertEqual(f.tiles[key], value)
            self.assertEqual(f.get('selected', f.h.lookup('*EL:DLUISTATE*')), 'ELDEV2')
            self.invoke(f, callbacks, 'cancel')

        f.actions = [edit, expand, check_restored]
        f.dialog()
        rows = f.get('devices', f.call('EL:DLParse', path.read_text(encoding='utf-8')))
        self.assertEqual([f.get('watts', row) for row in rows], [5, 12])
        self.assertEqual(f.dialogs, ['el_panel', 'el_panel_compact', 'el_panel'])
        self.assertTrue(truth(f.h.lookup('*EL:PANELLIBRARYEXPANDED*')))

    def test_invalid_power_or_write_failure_does_not_hide_unsaved_input(self):
        for failure in ('invalid_power', 'write_failure'):
            with self.subTest(failure=failure):
                f, callbacks, path, _ = self.fixture(expanded=True)
                original = path.read_bytes()
                commit = f.h.builtins.get('EL:DLCOMMIT')

                def edit():
                    f.tiles['dl_watts'] = '1.5' if failure == 'invalid_power' else '17'
                    if failure == 'write_failure':
                        f.h.builtins['EL:DLCOMMIT'] = lambda *args: None
                    self.invoke(f, callbacks, 'p_library_toggle')
                    self.assertIsNone(f.closed)
                    self.assertTrue(truth(f.h.lookup('*EL:PANELLIBRARYEXPANDED*')))
                    self.assertEqual(f.tiles['dl_watts'], '1.5' if failure == 'invalid_power' else '17')
                    self.assertEqual(path.read_bytes(), original)
                    if commit is None:
                        f.h.builtins.pop('EL:DLCOMMIT', None)
                    else:
                        f.h.builtins['EL:DLCOMMIT'] = commit
                    f.tiles['dl_watts'] = '17'
                    self.invoke(f, callbacks, 'p_library_toggle')

                f.actions = [edit, lambda: self.invoke(f, callbacks, 'cancel')]
                f.dialog()
                self.assertEqual(f.dialogs, ['el_panel', 'el_panel_compact'])
                saved = f.get('devices', f.call('EL:DLParse', path.read_text(encoding='utf-8')))[0]
                self.assertEqual(f.get('watts', saved), 17)

    def test_compact_generation_uses_current_capacity_without_flushing_hidden_controls(self):
        f, callbacks, _, _ = self.fixture()
        f.h.builtins['EL:DLUIFLUSH'] = lambda: self.fail('compact generation read hidden controls')
        f.h.builtins['EL:TEMPLATEREADY'] = lambda *args: True
        f.h.builtins['EL:DLPANELSUBMISSIONREADY'] = lambda: True

        def generate():
            f.call('EL:PanelCapacity', 'p_600')
            self.invoke(f, callbacks, 'p_generate')

        f.actions = [generate]
        result = f.dialog()
        self.assertTrue(truth(f.get('generate', result)))
        self.assertEqual(f.get('capacity', result), Symbol('CAP600'))
        self.assertEqual(f.dialogs, ['el_panel_compact'])

    def test_preview_and_diagnostic_path_survive_both_widths(self):
        f, callbacks, _, _ = self.fixture()
        previews, folders = [], []
        f.h.builtins['EL:ALLCIRCUITCOLORPREVIEW'] = lambda result: previews.append(result)

        def export():
            f.h.set('*EL:DIAGNOSTICEXPORTPATH*', 'C:/diagnostics/ELDIAG')
            return '诊断资料已导出'

        f.h.builtins['EL:PANELDIAGNOSTICEXPORT'] = export
        f.h.builtins['EL:DIAGNOSTICOPENFOLDER'] = lambda path: folders.append(path) or '已打开'

        def preview():
            f.call('EL:PanelCapacity', 'p_1000')
            self.invoke(f, callbacks, 'f_preview')

        def check_and_toggle():
            self.assertEqual(f.tiles['p_diagnostic_path'], 'C:/diagnostics/ELDIAG')
            self.assertEqual(f.tiles['p_capacity'], 'p_1000')
            self.invoke(f, callbacks, 'p_library_toggle')

        f.actions = [preview, lambda: self.invoke(f, callbacks, 'p_diagnostic'),
                     check_and_toggle, check_and_toggle,
                     lambda: self.invoke(f, callbacks, 'p_diagnostic_open'),
                     lambda: self.invoke(f, callbacks, 'cancel')]
        f.dialog()
        self.assertEqual(len(previews), 1)
        self.assertEqual(folders, ['C:/diagnostics/ELDIAG'])
        self.assertEqual(f.tiles['p_capacity'], 'p_1000')
        self.assertEqual(f.tiles['p_diagnostic_action'], '已打开')

    def test_expanded_choice_is_remembered_and_unreadable_library_can_be_collapsed(self):
        f, callbacks, _, _ = self.fixture()
        f.actions = [lambda: self.invoke(f, callbacks, 'p_library_toggle'),
                     lambda: self.invoke(f, callbacks, 'cancel')]
        f.dialog()
        f.actions = [lambda: self.invoke(f, callbacks, 'cancel')]
        f.dialog()
        self.assertEqual(f.dialogs, ['el_panel_compact', 'el_panel', 'el_panel'])

        f.h.builtins['EL:DLSNAPSHOT'] = lambda: None
        f.h.builtins['EL:DLUIFLUSH'] = lambda: self.fail('unreadable editor tried to save disabled fields')
        f.actions = [lambda: self.invoke(f, callbacks, 'p_library_toggle'),
                     lambda: self.invoke(f, callbacks, 'cancel')]
        f.call('EL:PanelDialog', None, None, None, None)
        self.assertEqual(f.dialogs[-2:], ['el_panel', 'el_panel_compact'])


if __name__ == '__main__':
    unittest.main()
