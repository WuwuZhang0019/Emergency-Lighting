"""Date: 2026-10-12. Preset/pick contracts; native CAD acceptance pending."""
import fnmatch
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
        self.events = []
        self.h.builtins['EL:LOGEVENT'] = lambda name, data: self.events.append((name, data))
        self.h.builtins['WCMATCH'] = wildcard_match

    def empty_config(self):
        return self.call('EL:Put', Symbol('DEVICE-NAMES'), None, self.cfg)

    def picks(self, values):
        values = iter(values)
        def pick(*args):
            value = next(values)
            if isinstance(value, Exception): raise value
            return [value] if value else None
        self.h.builtins['ENTSEL'] = pick

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

    def test_wrong_panel_stops_before_device_picking_and_geometry(self):
        self.h.builtins['EXIT'] = lambda: (_ for _ in ()).throw(RuntimeError('validation'))
        self.h.builtins['ENTSEL'] = lambda *args: self.fail('wrong panel entered registration')
        wrong = self.call('EL:Put', Symbol('PANEL-NAMES'), ['OTHER'], self.empty_config())
        with self.assertRaises(RuntimeError): self.call('EL:PresetReady', 'panel', wrong)
        self.assertEqual(self.saved, [])

    def test_first_registration_returns_updated_config_and_keeps_original_fields(self):
        empty = self.call('EL:Put', Symbol('TEMPLATE'), 'kept-template', self.empty_config())
        self.picks(['a', 'a', 'b', None])
        self.h.builtins['GETKWORD'] = lambda *args: self.fail('first registration asked add/remove')
        ready = self.call('EL:PresetReady', 'panel', empty)
        self.assertEqual(self.get('device-names', ready), ['LAMP'])
        self.assertEqual(self.get('template', ready), 'kept-template')
        self.assertEqual(self.get('params', ready), self.get('params', empty))
        self.assertFalse(self.get('device-names', empty))
        self.assertTrue(truth(self.call('EL:PresetValid', self.saved[0])))
        self.assertEqual([name for name, _ in self.events], ['PRESET_DEVICE_REQUIRED', 'PRESET_DEVICE_REGISTERED'])

    def test_no_valid_pick_returns_nil_without_save_or_geometry(self):
        self.f.block('WRONG', 'ARCH', 'wrong', [0., 0., 0.])
        self.picks(['w1', 'wrong', None])
        self.h.builtins['EL:PANELWIRECANDIDATES'] = lambda *args: self.fail('empty list scanned geometry')
        self.h.builtins['EXIT'] = lambda: self.fail('empty registration aborted command')
        self.assertIsNone(self.call('EL:PanelWireConfig', 'panel', self.empty_config()))
        self.assertEqual(self.saved, [])
        self.assertEqual(self.events[-1][0], 'PRESET_DEVICE_CANCELLED')
        self.assertEqual(self.get('reason', self.events[-1][1]), Symbol('EMPTY'))

    def test_escape_discards_partial_names_and_unwinds_interaction(self):
        self.call('EL:PerfStart', 'ELSTAT')
        self.picks(['a', RuntimeError('Function cancelled')])
        self.assertIsNone(self.call('EL:PresetReady', 'panel', self.empty_config()))
        self.assertEqual(self.saved, [])
        self.assertEqual(self.get('reason', self.events[-1][1]), Symbol('ESCAPE'))
        self.assertEqual(self.h.lookup('*EL:PERFWAITDEPTH*'), 0)
        self.assertFalse(self.h.lookup('*EL:PERFPENDING*'))
        stage = self.call('EL:Get', 'USER_INPUT', self.h.lookup('*EL:PERFSTAGES*'))
        self.assertEqual(self.get('calls', stage), 2)
        self.assertEqual(self.get('interrupted', stage), 1)

    def test_unexpected_pick_error_remains_a_validation_failure(self):
        self.picks([TypeError('bad argument type: numberp nil')])
        self.h.builtins['EXIT'] = lambda: (_ for _ in ()).throw(RuntimeError('validation'))
        with self.assertRaisesRegex(RuntimeError, 'validation'):
            self.call('EL:PresetReady', 'panel', self.empty_config())
        self.assertEqual(self.saved, [])
        self.assertEqual(self.events[-1][0], 'VALIDATION_FAILED')
        self.assertIn('numberp nil', self.get('message', self.events[-1][1]))

    def test_registered_names_do_not_prompt_or_resave(self):
        self.h.builtins['ENTSEL'] = lambda *args: self.fail('registered list requested another pick')
        self.assertEqual(self.call('EL:PresetReady', 'panel', self.cfg), self.cfg)
        self.assertEqual(self.saved, [])
        self.assertEqual(self.events, [])

    def test_wire_config_propagates_registered_names_to_real_network(self):
        self.picks(['a', None])
        ready = self.call('EL:PanelWireConfig', 'panel', self.empty_config())
        self.assertEqual(self.get('device-names', ready), ['LAMP'])
        snapshot = self.call('EL:SimpleCollect', ready)
        result = self.call('EL:SimpleNetwork', snapshot, ready, 'panel')
        self.assertEqual(sorted(self.get('id', row) for row in self.get('devices', result)), ['a', 'b'])

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

def wildcard_match(value, patterns):
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns.split(','))


class PresetEntryTests(unittest.TestCase):
    def fixture(self, trunk=False):
        import test_fixed_diagnostics as diag
        import test_concentrated_trunk as concentrated
        f = concentrated.TrunkTests() if trunk else diag.FixedDiagnosticTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.cfg = f.call('EL:Put', Symbol('DEVICE-NAMES'), None, f.cfg)
        self.saved, self.edited, self.model_picks, self.starts = [], [], [], []
        self.highlighted = set()
        models = iter(['trunk', 'panel'] if trunk else ['panel'])
        def model(*args):
            entity = next(models)
            self.model_picks.append(entity)
            self.highlighted.add(entity)
            return [entity, [0., 0., 0.]]
        def start():
            self.starts.append(True)
            if len(self.starts) == 1:
                return [Pair(Symbol('PICK-PANEL'), Symbol('TRUNK') if trunk else True)]
            self.assertFalse(self.highlighted, 'returned panel kept cancelled selection highlighted')
        def save(data):
            self.saved.append(data)
            f.cfg = data
            return data
        f.h.builtins.update({
            'EL:PICKMODEL': model,
            'EL:PRESETSAVE': save,
            'EL:EDITPANEL': lambda result, cfg: self.edited.append((result, cfg)),
            'EL:PANELSTARTDIALOG': start,
            'EL:MARKSTALE': lambda *args: self.fail('registration cancellation changed saved record'),
            'EL:CLEARPICKHIGHLIGHTS': self.highlighted.clear,
            'WCMATCH': wildcard_match,
        })
        return f

    def picks(self, f, values):
        values = iter(values)
        def pick(*args):
            value = next(values)
            if isinstance(value, Exception): raise value
            return [value] if value else None
        f.h.builtins['ENTSEL'] = pick

    def test_both_entries_register_then_continue_with_same_panel_and_number(self):
        for trunk in (False, True):
            with self.subTest(trunk=trunk):
                f = self.fixture(trunk)
                f.entities['number'] = [Pair(0, 'TEXT'), Pair(1, 'ZZ-B1ALE(JZ)')]
                number_picks = []
                f.h.builtins['NENTSEL'] = lambda *args: number_picks.append(True) or ['number']
                self.picks(f, ['d0' if trunk else 'a', None])
                f.h.run('(c:ELSTAT)')
                self.assertEqual(self.model_picks, ['trunk', 'panel'] if trunk else ['panel'])
                self.assertEqual(number_picks, [True])
                self.assertEqual(len(self.edited), 1)
                result, cfg = self.edited[0]
                self.assertEqual(f.get('panel-number', result), 'ZZ-B1ALE(JZ)')
                self.assertEqual(f.get('device-names', cfg), ['LAMP'])
                self.assertTrue(f.get('circuits', result))
                if trunk: f.assert_five(result)
                self.assertEqual(len(self.saved), 1)
                self.assertEqual(f.writes, [])
                text = f.log.read_text(encoding='utf-8')
                self.assertIn('PRESET_DEVICE_REGISTERED', text)
                self.assertNotIn('VALIDATION_FAILED', text)
                self.assertNotIn('| ERROR |', text)

    def test_both_entries_return_to_start_on_enter_or_escape_without_writes(self):
        for trunk in (False, True):
            for cancel in (None, RuntimeError('Function cancelled')):
                with self.subTest(trunk=trunk, cancel=cancel):
                    f = self.fixture(trunk)
                    self.picks(f, [cancel] if cancel is None else ['d0' if trunk else 'a', cancel])
                    f.h.builtins['EL:RECOGNIZEFIXED'] = lambda *args: self.fail('cancelled registration recognized')
                    f.h.builtins['EL:ENTITYBOUNDS'] = lambda *args: self.fail('cancelled registration read bounds')
                    f.h.run('(c:ELSTAT)')
                    self.assertEqual(len(self.starts), 2)
                    self.assertEqual(self.edited, [])
                    self.assertEqual(self.saved, [])
                    self.assertEqual(f.writes, [])
                    self.assertFalse(f.h.lookup('*EL:RESULT*'))
                    self.assertFalse(f.h.lookup('*EL:PERFACTIVE*'))
                    self.assertFalse(f.h.lookup('*EL:PERFPENDING*'))
                    summary = f.h.lookup('*EL:PERFLASTSUMMARY*')
                    self.assertEqual(f.get('status', summary), Symbol('COMMAND-FINISHED'))
                    text = f.log.read_text(encoding='utf-8')
                    self.assertIn('PRESET_DEVICE_CANCELLED', text)
                    self.assertNotIn('VALIDATION_FAILED', text)
                    self.assertNotIn('| ERROR |', text)

    def test_saved_registration_is_reused_on_next_stat(self):
        f = self.fixture()
        self.picks(f, ['a', None])
        f.h.run('(EL:FixedStatPick)')
        f.h.builtins['EL:PICKMODEL'] = lambda *args: ['panel', [0., 0., 0.]]
        f.h.builtins['ENTSEL'] = lambda *args: self.fail('saved preset asked for device again')
        f.h.run('(EL:FixedStatPick)')
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(len(self.edited), 2)
        self.assertEqual(f.writes, [])

    def test_preset_write_failure_never_continues_recognition(self):
        f = self.fixture()
        self.picks(f, ['a', None])
        def fail(data): raise RuntimeError('preset write failed')
        f.h.builtins['EL:PRESETSAVE'] = fail
        f.h.builtins['EL:RECOGNIZEFIXED'] = lambda *args: self.fail('failed save continued recognition')
        with self.assertRaisesRegex(RuntimeError, 'preset write failed'):
            f.h.run('(EL:FixedStatPick)')
        self.assertEqual(self.edited, [])
        self.assertEqual(f.writes, [])


if __name__ == '__main__': unittest.main()
