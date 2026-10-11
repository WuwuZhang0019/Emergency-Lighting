"""Date: 2026-10-12. Preset/pick contracts; native CAD acceptance pending."""
import unittest
from autolisp_host import Pair, Symbol, truth
import test_auto_wire as auto

class PresetTests(unittest.TestCase):
    def setUp(self):
        f = auto.AutoWireTests(); f.setUp()
        self.h, self.call, self.get = f.h, f.call, f.get
        self.f = f
        self.cfg = self.call('EL:Put', Symbol('PRESET-SCOPED'), True, f.cfg)
        self.h.builtins['EL:PRESETLOAD'] = lambda: self.cfg
        self.saved = []
        self.h.builtins['EL:PRESETSAVE'] = lambda data: self.saved.append(data) or data
        self.h.builtins['INITGET'] = lambda *args: None
        self.h.builtins['GETKWORD'] = lambda *args: None
        self.h.builtins['CHR'] = chr

    def test_exact_defaults_and_validation(self):
        data = self.call('EL:PresetDefault')
        self.assertTrue(truth(self.call('EL:PresetValid', data)))
        self.assertEqual(self.get('panel-names', data), ['$equip_U$00000398(Zhangyufeng)'])
        self.assertEqual(self.get('panel-layers', data), ['POWR_电力大设备_E'])
        self.assertEqual(self.get('wire-layers', data), ['LITE_应急照明布线_E'])
        self.assertEqual(self.get('device-layers', data), ['LITE_照明设备_E'])
        self.assertFalse(truth(self.call('EL:PresetValid', self.call('EL:Put', Symbol('WIRE-LAYERS'), None, data))))

    def test_selection_filters_literal_layers_at_database_boundary(self):
        filters = []
        self.h.builtins['SSGET'] = lambda *args: filters.append(args) or None
        self.call('EL:PresetSelection', self.cfg, 'INSERT,LINE,LWPOLYLINE', [Symbol('DEVICE-LAYERS')])
        self.assertIn(Pair(8, 'D'), filters[0][1])
        self.assertEqual(self.call('EL:PresetEscape', 'A[1]*,B'), 'A`[1`]`*`,B')

    def test_unrelated_blocks_never_read_bounds_even_if_selection_returns_them(self):
        self.f.block('WALL', 'ARCH', 'wall', [4., 0., 0.])
        self.f.block('OTHER', 'D', 'other', [4., 0., 0.])
        self.f.selected.extend(['wall', 'other'])
        original = self.h.builtins['EL:ENTITYBOUNDS'] if 'EL:ENTITYBOUNDS' in self.h.builtins else None
        # The adapter's native bounds boundary is an observable read.
        reads = []
        self.h.builtins['EL:ENTITYBOUNDS'] = lambda e: reads.append(e) or self.f.bounds[e]
        self.call('EL:SimpleCollect', self.cfg)
        self.assertNotIn('wall', reads); self.assertNotIn('other', reads)
        self.assertIn('panel', reads)

    def test_pick_deduplicates_and_ignores_wrong_layer_nonblock_xref(self):
        self.f.block('NEW', 'D', 'new', [0., 0., 0.])
        self.f.block('WRONG', 'ARCH', 'wrong', [0., 0., 0.])
        self.f.block('XREF', 'D', 'xref', [0., 0., 0.])
        self.f.blocks['XREF'] = [Pair(70, 4)]
        picks = iter([['w1'], ['wrong'], ['xref'], ['new'], ['new'], None])
        self.h.builtins['ENTSEL'] = lambda *args: next(picks)
        self.call('EL:PresetPickWork')
        self.assertEqual(self.get('device-names', self.saved[-1]), ['LAMP', 'NEW'])

    def test_escape_does_not_save_partial_picks(self):
        self.f.block('NEW', 'D', 'new', [0., 0., 0.])
        picks = iter([['new'], RuntimeError('cancelled')])
        def pick(*args):
            value = next(picks)
            if isinstance(value, Exception): raise value
            return value
        self.h.builtins['ENTSEL'] = pick
        with self.assertRaises(RuntimeError): self.call('EL:PresetPickWork')
        self.assertEqual(self.saved, [])

    def test_remove_only_selected_name(self):
        self.f.block('LAMP', 'D', 'lamp', [0., 0., 0.])
        self.h.builtins['GETKWORD'] = lambda *args: '2'
        picks = iter([['lamp'], None])
        self.h.builtins['ENTSEL'] = lambda *args: next(picks)
        self.call('EL:PresetPickWork')
        self.assertFalse(self.get('device-names', self.saved[-1]))

    def test_empty_device_list_and_wrong_panel_stop_before_geometry(self):
        empty = self.call('EL:Put', Symbol('DEVICE-NAMES'), None, self.cfg)
        self.h.builtins['EXIT'] = lambda: (_ for _ in ()).throw(RuntimeError('validation'))
        with self.assertRaises(RuntimeError): self.call('EL:PresetReady', 'panel', empty)
        wrong = self.call('EL:Put', Symbol('PANEL-NAMES'), ['OTHER'], self.cfg)
        with self.assertRaises(RuntimeError): self.call('EL:PresetReady', 'panel', wrong)

    def test_saved_preset_loads_again_and_corruption_does_not_fall_back(self):
        self.h.builtins.pop('EL:PRESETLOAD')
        self.h.builtins.pop('EL:PRESETSAVE')
        store = {}
        self.h.builtins.update({
            'EL:PRESETPATH': lambda: 'user/recognition-preset.eld',
            'VL-FILENAME-DIRECTORY': lambda path: 'user',
            'EL:DLMKDIR': lambda path: True,
            'FINDFILE': lambda path: path if path in store else None,
            'EL:WRITEDATA': lambda path, data: store.__setitem__(path, data) or True,
            'EL:READDATA': lambda path: store.get(path),
            'EXIT': lambda: (_ for _ in ()).throw(RuntimeError('validation')),
        })
        data = self.call('EL:PresetDefault')
        data = self.call('EL:Put', Symbol('DEVICE-NAMES'), ['设备A', '设备B'], data)
        self.call('EL:PresetSave', data)
        self.assertEqual(self.call('EL:PresetLoad'), data)
        store['user/recognition-preset.eld'] = None
        with self.assertRaises(RuntimeError): self.call('EL:PresetLoad')
        self.h.builtins['EL:WRITEDATA'] = lambda *args: True
        with self.assertRaises(RuntimeError): self.call('EL:PresetSave', data)

    def test_failed_hide_already_visible_does_not_require_locked_write(self):
        from pathlib import Path
        self.h.load_definitions(Path(__file__).resolve().parents[1] / 'src/panel.lsp')
        self.h.run("""(setq *EL:ThumbHidden* '(("locked" -1)))""")
        self.h.builtins['VLA-GET-VISIBLE'] = lambda *args: -1
        self.h.builtins['VLA-PUT-VISIBLE'] = lambda *args: self.fail('unnecessary locked write')
        self.assertTrue(truth(self.call('EL:ThumbRestore')))
        self.assertFalse(self.h.lookup('*EL:THUMBHIDDEN*'))

    def test_locked_neighbor_preflight_never_writes_visibility(self):
        from pathlib import Path
        self.h.load_definitions(Path(__file__).resolve().parents[1] / 'src/panel.lsp')
        self.h.builtins['SSGET'] = lambda *args: ['panel', 'w1']
        self.h.builtins['TBLSEARCH'] = lambda table, name: [Pair(70, 4 if name == 'W' else 0)]
        self.h.builtins['VLA-PUT-VISIBLE'] = lambda *args: self.fail('source mutation')
        self.h.builtins['EXIT'] = lambda: (_ for _ in ()).throw(RuntimeError('locked'))
        with self.assertRaises(RuntimeError):
            self.call('EL:ThumbIsolate', [Pair(Symbol('ID'), 'panel')])
        self.assertFalse(self.h.lookup('*EL:THUMBHIDDEN*'))

if __name__ == '__main__': unittest.main()
