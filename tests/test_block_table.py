"""Unified block table behavior. Date: 2026-10-10. Native CAD pending."""
import unittest
from pathlib import Path
from autolisp_host import Symbol, truth
import test_exit_devices as exits


class BlockTableTests(unittest.TestCase):
    def setUp(self):
        self.f = exits.ExitDeviceTests()
        self.f.setUp()
        self.h, self.call, self.get = self.f.h, self.f.call, self.f.get
        self.tiles = self.f.tiles
        self.h.builtins['GET_TILE'] = lambda key: self.tiles.get(key, '')
        self.h.builtins['DONE_DIALOG'] = lambda status: status
        self.result = self.call('EL:RecognizeFixed', self.f.cfg, 'panel')

    def dialog(self, action):
        self.h.builtins['START_DIALOG'] = action
        return self.call('EL:PanelDialog', self.result, self.f.cfg, None, None)

    def populate(self):
        blocks = [self.h.run(f"'((id . \"id{i}\") (name . \"TYPE{i}\"))") for i in range(6)]
        cs = self.get('circuits', self.result)
        cs = [self.call('EL:Put', Symbol('DEVICES'), [f'id{i}' for i in range(6)], cs[0])]
        self.result = self.call('EL:Put', Symbol('CIRCUITS'), cs, self.result)
        snapshot = self.call('EL:Put', Symbol('BLOCKS'), blocks, self.get('snapshot', self.result))
        self.result = self.call('EL:Put', Symbol('SNAPSHOT'), snapshot, self.result)

    def test_paging_keeps_every_visible_power_and_ground_setting(self):
        self.populate()
        def action():
            for i in range(4):
                self.tiles[f'b_watts{i}'] = str(i + 1)
            self.call('EL:PanelBlockGround', 0, '1')
            self.call('EL:PanelBlockPage', 4)
            self.assertEqual(self.get('name', self.h.lookup('*EL:THUMBROWS*')[self.h.lookup('*EL:THUMBPAGE*')]), 'TYPE4')
            self.tiles['b_watts0'], self.tiles['b_watts1'] = '5', '6'
            self.call('EL:PanelBlockPage', -4)
            self.assertEqual(self.tiles['b_watts3'], '4')
            self.assertEqual(self.tiles['b_ground0'], '1')
            self.assertTrue(truth(self.get('is-ground', self.get('circuits', self.h.lookup('*EL:PANELDRAFT*'))[0])))
            return self.call('EL:PanelAccept') or 1
        response = self.dialog(action)
        powers = self.get('powers', response)
        for i in range(6):
            self.assertEqual(self.call('EL:Get', f'TYPE{i}', powers), i + 1)

    def test_invalid_input_blocks_page_ground_and_save_without_partial_store(self):
        self.populate()
        def action():
            self.tiles['b_watts0'], self.tiles['b_watts1'] = '7', '12x'
            self.call('EL:PanelBlockPage', 4)
            self.assertEqual(self.get('name', self.h.lookup('*EL:THUMBROWS*')[self.h.lookup('*EL:THUMBPAGE*')]), 'TYPE0')
            self.assertEqual(self.tiles['b_watts1'], '12x')
            self.assertFalse(self.h.lookup('*EL:PANELPOWERS*'))
            self.call('EL:PanelBlockGround', 0, '1')
            self.assertEqual(self.tiles['b_ground0'], '0')
            self.assertFalse(self.call('EL:PanelStoreSelections'))
            return 0
        self.dialog(action)

    def test_ground_is_any_marked_type_and_unchecking_last_clears_it(self):
        self.populate()
        def action():
            self.call('EL:PanelBlockGround', 0, '1')
            self.call('EL:PanelBlockGround', 1, '1')
            self.call('EL:PanelBlockGround', 0, '0')
            c = self.get('circuits', self.h.lookup('*EL:PANELDRAFT*'))[0]
            self.assertTrue(truth(self.get('is-ground', c)))
            self.assertEqual(self.get('ground-evidence', c), ['id1'])
            self.call('EL:PanelBlockGround', 1, '0')
            c = self.get('circuits', self.h.lookup('*EL:PANELDRAFT*'))[0]
            self.assertFalse(truth(self.get('is-ground', c)))
            self.assertEqual(self.get('ground-source', c), Symbol('MANUAL'))
            return 0
        self.dialog(action)

    def test_ground_choices_save_and_restore_with_draft(self):
        store = [self.call('EL:StoreInitial')]
        self.h.builtins.update({
            'EL:STOREREAD': lambda: store[0],
            'EL:STOREWRITE': lambda value: store.__setitem__(0, value) or True,
            'EL:TRANSACTION': lambda fn, args: self.h.builtins['EL:STOREWRITE'](args[0]),
        })
        def action():
            self.call('EL:PanelBlockGround', 0, '1')
            return 1
        response = self.dialog(action)
        self.assertTrue(truth(self.call('EL:SaveDraft', self.get('result', response), self.f.cfg, None, Symbol('CAP300'))))
        record = self.call('EL:DiagramForPanel', 'panel', store[0])
        prepared = self.call('EL:PreparedResult', self.result, record)
        self.assertTrue(truth(self.call('EL:Get', 'LAMP', self.get('block-ground', prepared))))
        self.result = prepared
        def reopen():
            self.assertEqual(self.tiles['b_ground0'], '1')
            self.assertTrue(truth(self.get('is-ground', self.get('circuits', self.h.lookup('*EL:PANELDRAFT*'))[0])))
            return 0
        self.dialog(reopen)

    def test_ground_changes_only_circuits_containing_the_marked_type(self):
        self.populate()
        c = self.get('circuits', self.result)[0]
        circuits = [self.call('EL:Put', Symbol('DEVICES'), ids, c)
                    for ids in (['id0', 'id1'], ['id0'], ['id2'])]
        self.result = self.call('EL:Put', Symbol('CIRCUITS'), circuits, self.result)
        def action():
            self.call('EL:PanelBlockGround', 0, '1')
            cs = self.get('circuits', self.h.lookup('*EL:PANELDRAFT*'))
            self.assertEqual([truth(self.get('is-ground', c)) for c in cs], [True, True, False])
            return 0
        self.dialog(action)

    def test_main_panel_uses_only_controls_present_in_dcl(self):
        import re
        ui = (Path(__file__).resolve().parents[1] / 'ui/power.dcl').read_text(encoding='utf-8').split('el_panel : dialog {')[1]
        keys = set(re.findall(r'key = "([^"]+)"', ui))
        for name in ('SET_TILE', 'MODE_TILE', 'ACTION_TILE', 'START_LIST'):
            original = self.h.builtins[name]
            def checked(key, *args, original=original):
                self.assertIn(key, keys)
                return original(key, *args)
            self.h.builtins[name] = checked
        self.dialog(lambda: 0)

    def test_circuit_preview_returns_to_same_block_page_with_power(self):
        self.populate()
        previews = []
        self.h.builtins['EL:FIXEDEXITPREVIEW'] = lambda result, selection: previews.append(selection)
        def action():
            if not previews:
                self.call('EL:PanelBlockPage', 4)
                self.tiles['b_watts0'] = '9'
                return self.call('EL:PanelSelect', 0)
            self.assertEqual(self.get('name', self.h.lookup('*EL:THUMBROWS*')[self.h.lookup('*EL:THUMBPAGE*')]), 'TYPE4')
            self.assertEqual(self.tiles['b_watts0'], '9')
            return 0
        self.dialog(action)
        self.assertEqual(previews, ['0'])
        self.assertEqual(self.f.dialogs, ['el_panel', 'el_panel'])

    def test_main_dcl_has_inline_table_and_no_duplicate_editor(self):
        ui = (Path(__file__).resolve().parents[1] / 'ui/power.dcl').read_text(encoding='utf-8').split('el_panel : dialog {')[1]
        for key in ('p_devices', 'p_watts', 'p_ground0', 'f_exits', 'f_apply', 'b_name0', 'f_count0', 'f_hint0'):
            self.assertNotIn(f'key = "{key}"', ui)
        for i in range(4):
            for prefix in ('f_image', 'b_watts', 'b_ground'):
                self.assertIn(f'key = "{prefix}{i}"', ui)


if __name__ == '__main__':
    unittest.main()
