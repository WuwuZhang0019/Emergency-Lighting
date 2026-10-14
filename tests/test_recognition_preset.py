"""Date: 2026-10-15. Library-driven recognition; picking remains a separate action."""
import unittest
from autolisp_host import Pair, Symbol, truth
import test_auto_wire as auto


class PresetTests(unittest.TestCase):
    def setUp(self):
        f = auto.AutoWireTests(); f.setUp()
        self.h, self.call, self.get, self.f = f.h, f.call, f.get, f
        self.cfg = self.call('EL:Put', Symbol('PRESET-SCOPED'), True, f.cfg)
        self.h.builtins['EL:PRESETLOAD'] = lambda: self.cfg
        self.saved, self.events, self.alerts = [], [], []
        self.h.builtins.update({
            'EL:PRESETSAVE': lambda data: self.saved.append(data) or data,
            'EL:LOGEVENT': lambda name, data: self.events.append((name, data)),
            'EL:DLSNAPSHOT': lambda: self.h.run("'((catalog (devices)))"),
            'ENTSEL': lambda *args: self.fail('statistics entered device picking'),
            'ALERT': self.alerts.append, 'CHR': chr,
        })

    def empty_config(self):
        return self.call('EL:Put', Symbol('DEVICE-NAMES'), None, self.cfg)

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
        reads = []
        self.h.builtins['EL:ENTITYBOUNDS'] = lambda e: reads.append(e) or self.f.bounds[e]
        self.call('EL:SimpleCollect', self.cfg)
        self.assertNotIn('wall', reads); self.assertNotIn('other', reads)
        self.assertIn('panel', reads)

    def test_empty_library_returns_guidance_without_pick_save_or_exit(self):
        self.h.builtins['EXIT'] = lambda: self.fail('empty library aborted statistics')
        self.h.builtins['EL:PANELWIRECANDIDATES'] = lambda *args: self.fail('empty library scanned wires')
        self.assertIsNone(self.call('EL:PanelWireConfig', 'panel', self.empty_config()))
        self.assertEqual(self.saved, [])
        self.assertEqual(self.events[-1][0], 'DEVICE_LIBRARY_PICK_REQUIRED')
        self.assertIn('拾取设备入库', self.alerts[0])

    def test_wrong_panel_still_rejected_before_library_or_geometry(self):
        self.h.builtins['EXIT'] = lambda: (_ for _ in ()).throw(RuntimeError('validation'))
        self.h.builtins['EL:DLSNAPSHOT'] = lambda: self.fail('wrong panel loaded library')
        wrong = self.call('EL:Put', Symbol('PANEL-NAMES'), ['OTHER'], self.empty_config())
        with self.assertRaises(RuntimeError): self.call('EL:PresetReady', 'panel', wrong)
        self.assertEqual(self.saved, [])

    def test_library_draft_with_graphic_supplies_name_and_keeps_missing_watts(self):
        import test_device_library as backend
        b = backend.DeviceLibraryTests(); b.setUp()
        row = b.put('watts', None, b.put('active', None, b.put('status', Symbol('DRAFT'), b.entry('LAMP'))))
        catalog = b.call('EL:DLUpsert', b.cat, row)
        snapshot = [Pair(Symbol('CATALOG'), catalog), [Symbol('INDEX')]]
        self.h.builtins['EL:DLSNAPSHOT'] = lambda: snapshot
        empty = self.call('EL:Put', Symbol('TEMPLATE'), 'kept-template', self.empty_config())
        ready = self.call('EL:PanelWireConfig', 'panel', empty)
        self.assertEqual(self.get('device-names', ready), ['LAMP'])
        self.assertEqual(self.get('template', ready), 'kept-template')
        result = self.call('EL:SimpleNetwork', self.call('EL:SimpleCollect', ready), ready, 'panel')
        self.assertEqual(sorted(self.get('id', r) for r in self.get('devices', result)), ['a', 'b'])
        self.assertFalse(self.call('EL:DLLookup', 'LAMP', snapshot))
        self.assertEqual(self.saved, [])

    def test_legacy_names_still_work_when_library_is_unavailable(self):
        self.h.builtins['EL:DLSNAPSHOT'] = lambda: None
        self.assertEqual(self.call('EL:PresetReady', 'panel', self.cfg), self.cfg)
        self.assertEqual(self.saved, [])

    def test_pick_command_opens_separate_library_picker(self):
        calls = []
        self.h.builtins['EL:DLUIPICKOPEN'] = lambda: calls.append(True)
        self.call('c:ELDEVPICK')
        self.assertEqual(calls, [True])
        self.assertEqual(self.saved, [])

    def test_failed_hide_already_visible_does_not_require_locked_write(self):
        from pathlib import Path
        self.h.load_definitions(Path(__file__).resolve().parents[1] / 'src/panel.lsp')
        self.h.run('(setq *EL:ThumbHidden* \'(("locked" -1)))')
        self.h.builtins['VLA-GET-VISIBLE'] = lambda *args: -1
        self.h.builtins['VLA-PUT-VISIBLE'] = lambda *args: self.fail('unnecessary locked write')
        self.assertTrue(truth(self.call('EL:ThumbRestore')))


class PresetEntryTests(unittest.TestCase):
    def test_both_statistics_entries_use_library_without_inline_picking(self):
        import test_fixed_diagnostics as diag
        import test_concentrated_trunk as concentrated
        for trunk in (False, True):
            with self.subTest(trunk=trunk):
                f = concentrated.TrunkTests() if trunk else diag.FixedDiagnosticTests(); f.setUp()
                self.addCleanup(f.doCleanups)
                edited, names = [], []
                # The direct entry now requests explicit circuit starts after the panel.
                models = iter([['trunk', [0., 0., 0.]], ['panel', [0., 0., 0.]]] if trunk else
                              [['panel', [0., 0., 0.]], ['w1', [1., 0., 0.]], None])
                f.h.builtins.update({
                    'EL:PICKMODEL': lambda *args: next(models),
                    'ENTSEL': lambda *args: self.fail('statistics started device picking'),
                    'EL:PRESETSAVE': lambda *args: self.fail('statistics saved recognition preset'),
                    'EL:DLRECOGNITIONNAMES': lambda *args: names.append(True) or ['LAMP'],
                    'EL:EDITPANEL': lambda result, cfg: edited.append((result, cfg)),
                })
                f.cfg = f.call('EL:Put', Symbol('DEVICE-NAMES'), None, f.cfg)
                f.entities['number'] = [Pair(0, 'TEXT'), Pair(1, 'ZZ-B1ALE(JZ)')]
                f.h.builtins['NENTSEL'] = lambda *args: ['number']
                f.call('EL:FixedTrunkPick' if trunk else 'EL:FixedStatPick')
                self.assertEqual(len(edited), 1)
                result, cfg = edited[0]
                self.assertEqual(f.get('panel-number', result), 'ZZ-B1ALE(JZ)')
                self.assertEqual(f.get('device-names', cfg), ['LAMP'])
                self.assertTrue(names)
                self.assertEqual(f.writes, [])


if __name__ == '__main__': unittest.main()
