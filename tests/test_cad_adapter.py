"""CAD record boundary checks with entget-shaped data. Date: 2026-10-11.

Runs source geometry and topology, with database calls replaced by fixtures.
These checks are not real AutoCAD acceptance.
"""
import pathlib
import unittest

from autolisp_host import Host, Pair, Symbol, equal, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CadAdapterTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'config', 'geometry', 'topology', 'device-library', 'device-assets',
                     'device-ui', 'device-recognition', 'device-inputs', 'store-compact', 'diagram-store'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        self.entities = {}
        self.bounds = {}
        self.blocks = {}
        self.next_entity = {}
        self.selected = []
        self.h.frames[0][':VLAX-TRUE'] = -1
        self.h.builtins.update({
            'EL:ENTITYBOUNDS': lambda entity: self.bounds.get(entity),
            'ENTGET': lambda entity,*apps: self.entities[entity],
            'TBLSEARCH': lambda table, name: self.blocks.get(name) if table == 'BLOCK' else [Pair(2, name)],
            'ENTNEXT': lambda entity: self.next_entity.get(entity),
            'TRANS': lambda point, *args: point,
            'SSGET': lambda *args: self.selected or None,
            'SSLENGTH': len,
            'SSNAME': lambda ss, index: ss[index],
            'VLAX-ENAME->VLA-OBJECT': lambda entity: entity,
            'VLAX-PROPERTY-AVAILABLE-P': lambda *args: None,
            'VLA-GET-ISDYNAMICBLOCK': lambda entity: 0,
            'EL:DRAWINGID': lambda: 'adapter-fixture.dwg',
            'NAMEDOBJDICT': lambda:'NOD', 'DICTSEARCH': lambda *args:None,
        })
        self.h.run('''
          (setq cfg (EL:DefaultConfig "adapter-fixture.dwg"))
          (setq cfg (EL:Put 'params (EL:SuggestedParams) cfg))
          (setq cfg (EL:Put 'panel-layers '("P") cfg))
          (setq cfg (EL:Put 'panel-names '("BOX") cfg))
          (setq cfg (EL:Put 'device-layers '("D") cfg))
          (setq cfg (EL:Put 'device-names '("LAMP") cfg))
          (setq cfg (EL:Put 'wire-layers '("W") cfg))''')

    def call(self, function, *args):
        return self.h.call(Symbol(function.upper()), list(args))

    def get(self, key, record):
        return self.call('EL:Get', Symbol(key.upper()), record)

    def line(self, name, a, b, layer='0', visibility=None):
        # Like Autodesk's entget LINE example: optional code 60 is absent.
        self.entities[name] = [Pair(0, 'LINE'), Pair(5, name), Pair(8, layer),
                               Pair(10, a), Pair(11, b), Pair(210, [0.0, 0.0, 1.0]), Pair(410, 'Model')]
        if visibility is not None:
            self.entities[name].append(Pair(60, visibility))

    def block(self, name, layer, handle, position, visibility=None):
        self.bounds[handle] = [[position[0]-1., position[1]-1., position[2]], [position[0]+1., position[1]+1., position[2]]]
        self.entities[handle] = [Pair(0, 'INSERT'), Pair(5, handle), Pair(8, layer),
                                 Pair(2, name), Pair(10, position), Pair(410, 'Model')]
        corners = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)]
        children = [f'{name}-edge-{i}' for i in range(4)]
        self.blocks[name] = [Pair(2, name), Pair(10, [0.0, 0.0, 0.0]), Pair(70, 0), Pair(-2, children[0])]
        for i, child in enumerate(children):
            self.line(child, list(corners[i]), list(corners[(i+1) % 4]), visibility=visibility)
            self.next_entity[child] = children[i+1] if i < 3 else f'{name}-end'
        self.entities[f'{name}-end'] = [Pair(0, 'ENDBLK')]
        return handle

    def contour(self, handle):
        return self.call('EL:BlockContour', handle, [1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0], 0.1, None)

    def test_host_rejects_nil_numeric_comparison_but_equal_can_test_absence(self):
        with self.assertRaisesRegex(TypeError, 'numberp: nil'):
            self.h.run('(= nil 1)')
        self.assertFalse(truth(self.h.run('(equal nil 1)')))

    def test_nil_type_and_snapshot_signature_match_autolisp(self):
        self.assertIsNone(self.h.run('(type nil)'))
        with self.assertRaisesRegex(TypeError, 'numberp: nil'):
            self.h.run("(= (type nil) 'ENAME)")
        self.assertIsNone(self.h.run('(EL:StableData nil)'))
        data = [[Symbol('EMPTY')], [1, None, 'box']]
        self.assertTrue(equal(self.call('EL:StableData', data), data))
        self.assertIsInstance(self.call('EL:Signature', data), str)

    def test_advanced_trace_then_power_still_reaches_legacy_dialog(self):
        # Date: 2026-10-11. The shared power cleanup is provided by panel.
        for name in ('statistics', 'panel', 'main', 'diagram-commands'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        panel = self.block('BOX', 'P', 'panel', [0.0, 0.0, 0.0])
        lamp = self.block('LAMP', 'D', 'lamp', [12.0, 0.0, 0.0])
        self.line('wire', [1.0, 0.0, 0.0], [11.0, 0.0, 0.0], layer='W')
        self.selected = [panel, lamp, 'wire']
        cfg = self.h.run("(setq cfg (EL:Put 'calibrated T cfg))")
        prompts, dialogs = [], []

        def keyword(prompt):
            prompts.append(prompt)
            return None  # Enter accepts the default outgoing circuit.

        def power_dialog(result, config, library):
            dialogs.append(result)
            # Exercise the actual empty-power row initialization as well.
            self.h.run("(setq *EL:PowerRows* (EL:PowerTableRows *EL:Result*))")
            self.h.run('(EL:PowerUISelect 0)')
            return None

        def save_config(updated):
            nonlocal cfg
            cfg = updated
            return cfg

        self.h.builtins.update({
            'EL:LOADCONFIG': lambda: cfg,
            'ENTSEL': lambda prompt: [panel if '配电箱' in prompt else 'wire', [0.0, 0.0, 0.0]],
            'EL:REVIEWEXITS': lambda seeds: [seeds],
            'EL:SAVECONFIG': save_config,
            'HANDENT': lambda handle: handle,
            'REDRAW': lambda *args: None,
            'INITGET': lambda *args: None,
            'GETKWORD': keyword,
            'EL:LOADLIBRARY': lambda: None,
            'EL:POWERDIALOG': power_dialog,
            'SET_TILE': lambda *args: None,
        })
        self.h.run('(c:ELTRACE) (c:ELPOWER)')
        self.assertEqual(len(prompts), 0)
        self.assertEqual(len(dialogs), 1)
        circuits = self.get('circuits', dialogs[0])
        self.assertEqual(self.get('devices', circuits[0]), ['lamp'])
        self.assertTrue(truth(self.get('complete', circuits[0])))
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))

    def gap_command(self, flags=None, actions=(None,)):
        self.h.load_definitions(ROOT / 'src/main.lsp')
        self.entities['a'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'a'), Pair(8, 'W'),
                              Pair(10, [0.0, 0.0]), Pair(10, [10.0, 0.0]), Pair(410, 'Model')]
        if flags is not None:
            self.entities['a'].append(Pair(70, flags))
        self.line('b', [20.0, 0.0, 0.0], [30.0, 0.0, 0.0], 'W')
        self.selected = ['a', 'b']
        self.block('BOX', 'P', 'unused-panel', [10000.0, 0.0, 0.0])
        self.block('LAMP', 'D', 'unused-lamp', [11000.0, 0.0, 0.0])
        cfg = self.h.lookup('CFG')  # Bind before the command's local cfg shadows it.
        self.messages, self.draws, self.zoom_calls, self.picks = [], [], [], []
        keywords = iter(actions)

        def pick(prompt):
            self.picks.append(prompt)
            return ['a', [10.0, 0.0, 0.0]]

        self.h.builtins.update({
            'EL:LOADCONFIG': lambda: cfg,
            'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'GETVAR': lambda name: {'VIEWSIZE': 100.0, 'VIEWCTR': [0.0, 0.0]}[name],
            'ENTSEL': pick, 'HANDENT': lambda handle: handle,
            'REDRAW': lambda *args: None, 'GRTEXT': lambda *args: None,
            'GRDRAW': lambda *args: self.draws.append(args),
            'VLAX-3D-POINT': lambda point: point,
            'VLA-ZOOMCENTER': lambda *args: self.zoom_calls.append(args),
            'INITGET': lambda *args: None, 'GETKWORD': lambda prompt: next(keywords),
            'PRINC': lambda *args: self.messages.extend(args),
        })

    def test_gap_command_missing_polyline_flags_previews_and_cleans_up(self):
        self.gap_command()
        self.h.run('(c:ELGAPTEST)')
        self.assertEqual(len(self.picks), 1)
        self.assertIn('找到一对双向几何匹配', ''.join(self.messages))
        self.assertTrue(self.draws)
        self.assertIsNone(self.h.lookup('*EL:HIGHLIGHT*'))
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))
        self.assertIsNone(self.h.lookup('*EL:RESULT*'))
        self.assertIsNone(self.get('gap-pairs', self.h.lookup('CFG')))

    def test_gap_command_locate_then_enter_restores_view(self):
        self.gap_command(flags=0, actions=('Locate', None))
        self.h.run('(c:ELGAPTEST)')
        self.assertEqual(len(self.zoom_calls), 2)
        self.assertEqual(self.zoom_calls[-1], ('app', [0.0, 0.0, 0.0], 100.0))

    def test_gap_command_without_params_uses_defaults_without_numeric_prompts(self):
        self.gap_command()
        cfg = self.call('EL:Put', Symbol('PARAMS'), None, self.h.lookup('CFG'))
        self.h.builtins['EL:LOADCONFIG'] = lambda: cfg
        self.h.builtins['GETREAL'] = lambda *args: self.fail('unexpected parameter prompt')
        self.h.run('(c:ELGAPTEST)')
        self.assertIn('已自动采用默认识别参数', ''.join(self.messages))
        self.assertIn('找到一对双向几何匹配', ''.join(self.messages))
        self.assertIsNone(self.get('params', cfg))  # Preview must not persist defaults.

    def test_gap_range_expands_to_long_gap_without_repick_or_changing_other_values(self):
        self.gap_command(actions=('Range', None))
        self.line('b', [2510.0, 0.0, 0.0], [2520.0, 0.0, 0.0], 'W')
        prompts = []
        self.h.builtins['GETREAL'] = lambda prompt: prompts.append(prompt) or 3000.0
        self.h.run('(c:ELGAPTEST)')
        messages = ''.join(self.messages)
        self.assertLess(messages.index('无合格候选'), messages.index('找到一对双向几何匹配'))
        self.assertIn('2500.000', messages)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(len(self.picks), 1)
        preview = self.h.lookup('*EL:PICKPARAMS*')
        saved = self.get('params', self.h.lookup('CFG'))
        self.assertEqual(self.get('Dmax', preview), 3000.0)
        self.assertEqual(self.get('Dmax', saved), 2000.0)
        for key in ('eps_touch', 'eps_boundary', 'eps_perp', 'eps_z', 'theta_max', 'R0'):
            self.assertEqual(self.get(key, preview), self.get(key, saved))

    def test_gap_range_rejects_invalid_value_and_enter_keeps_existing_range(self):
        self.gap_command(actions=('Range', None))
        values = iter((10.0, None))
        self.h.builtins['GETREAL'] = lambda prompt: next(values)
        self.h.run('(c:ELGAPTEST)')
        self.assertIn('请重新输入', ''.join(self.messages))
        self.assertEqual(self.get('Dmax', self.h.lookup('*EL:PICKPARAMS*')), 2000.0)

    def test_gap_command_preserves_current_custom_range_without_advanced_prompts(self):
        self.gap_command()
        params = self.call('EL:Put', Symbol('DMAX'), 800.0, self.h.run('(EL:SuggestedParams)'))
        cfg = self.call('EL:Put', Symbol('PARAMS'), params, self.h.lookup('CFG'))
        self.h.builtins['EL:LOADCONFIG'] = lambda: cfg
        self.h.builtins['GETREAL'] = lambda prompt: self.fail('unexpected parameter prompt')
        self.h.run('(c:ELGAPTEST)')
        self.assertEqual(self.get('Dmax', self.h.lookup('*EL:PICKPARAMS*')), 800.0)

    def test_gap_command_requires_equipment_samples_before_search(self):
        self.gap_command()
        cfg = self.call('EL:Put', Symbol('DEVICE-LAYERS'), None, self.h.lookup('CFG'))
        self.h.builtins['EL:LOADCONFIG'] = lambda: cfg
        self.h.run('(c:ELGAPTEST)')
        self.assertIn('请先运行 ELSETUP', ''.join(self.messages))
        self.assertFalse(self.picks)
        self.assertFalse(self.draws)

    def test_gap_command_explains_whole_wire_equipment_exclusion(self):
        self.gap_command()
        self.block('BOX', 'P', 'panel', [-1.0, 0.0, 0.0])
        self.selected.append('panel')  # The unpicked end of a touches this panel.
        self.h.run('(c:ELGAPTEST)')
        self.assertIn('这整条导线已接设备或配电箱', ''.join(self.messages))
        self.assertNotIn('找到一对双向几何匹配', ''.join(self.messages))

    def test_gap_command_read_error_reports_entity_and_does_not_continue(self):
        self.gap_command()

        def fail_record(*args):
            # Invoke the command handler while its dynamic bindings are active.
            self.call('*error*', 'bad argument type: numberp: nil')
            raise RuntimeError('injected CAD read failure')

        self.h.builtins['EL:WIRERECORD'] = fail_record
        with self.assertRaisesRegex(RuntimeError, 'injected CAD read failure'):
            self.h.run('(c:ELGAPTEST)')
        messages = ''.join(self.messages)
        self.assertIn('numberp: nil', messages)
        self.assertIn('ELGAPTEST 失败阶段：采集对象', messages)
        self.assertIn('LWPOLYLINE', messages)
        self.assertIn("'a'", messages)
        self.assertFalse(self.picks)
        self.assertFalse(self.draws)
        self.assertIsNone(self.h.lookup('*EL:GAPSTAGE*'))
        self.assertIsNone(self.h.lookup('*EL:HIGHLIGHT*'))

    def test_contour_polyline_missing_flags_matches_explicit_zero(self):
        panel = self.block('BOX', 'P', 'panel', [0.0, 0.0, 0.0])
        child = 'BOX-edge-0'
        self.entities[child] = [Pair(0, 'LWPOLYLINE'), Pair(10, [-1.0, -1.0]),
                                Pair(10, [1.0, -1.0]), Pair(10, [1.0, 1.0])]
        implicit = self.contour(panel)
        self.entities[child].append(Pair(70, 0))
        self.assertTrue(equal(implicit, self.contour(panel)))
        self.assertIsNone(self.get('issues', implicit))

    def test_gap_command_closed_polyline_keeps_closed_diagnostic(self):
        self.gap_command(flags=1)
        wire = self.call('EL:WireRecord', 'a', self.h.lookup('CFG'))
        self.assertIn(Symbol('CLOSED_WIRE'), [self.get('code', i) for i in self.get('issues', wire)])
        self.assertIsNone(self.get('ends', wire))

    def test_visible_block_without_optional_visibility_code_has_contour(self):
        handle = self.block('BOX', 'P', 'panel', [10.0, 20.0, 0.0])
        result = self.contour(handle)
        self.assertEqual(len(self.get('segments', result)), 4)
        self.assertIsNone(self.get('issues', result))
        self.assertEqual(self.get('segments', result)[0][0], [9.0, 21.0, 0.0])

    def test_explicit_visible_block_has_same_contour(self):
        handle = self.block('BOX', 'P', 'panel', [10.0, 20.0, 0.0])
        implicit = self.contour(handle)
        self.block('BOX', 'P', 'panel', [10.0, 20.0, 0.0], visibility=0)
        self.assertTrue(equal(self.contour(handle), implicit))

    def test_invisible_geometry_is_excluded(self):
        handle = self.block('BOX', 'P', 'panel', [10.0, 20.0, 0.0], visibility=1)
        result = self.contour(handle)
        self.assertIsNone(self.get('segments', result))
        self.assertIn(Symbol('EMPTY_CONTOUR'), [self.get('code', issue) for issue in self.get('issues', result)])

    def test_two_command_shared_snapshot_and_topology_accept_ordinary_blocks(self):
        panel = self.block('BOX', 'P', 'panel', [0.0, 0.0, 0.0])
        lamp = self.block('LAMP', 'D', 'lamp', [12.0, 0.0, 0.0])
        self.line('wire', [1.0, 0.0, 0.0], [11.0, 0.0, 0.0], layer='W')
        self.selected = [panel, lamp, 'wire']
        cfg = self.h.lookup('CFG')
        snapshot = self.call('EL:CollectEndpointSnapshot', cfg)
        self.assertEqual(len(self.get('blocks', snapshot)), 2)
        self.assertEqual(len(self.get('wires', snapshot)), 1)
        self.assertEqual(len(self.get('ends', snapshot)), 2)
        self.assertIsNone(self.get('issues', snapshot))
        preview = self.call('EL:BuildPhysical', snapshot, cfg, None)
        self.call('EL:FindGapCandidates', self.get('snapshot', preview), cfg)
        physical = self.call('EL:BuildPhysical', snapshot, cfg, panel)
        seeds = self.call('EL:SeedCandidates', self.get('snapshot', physical), cfg, panel)
        self.assertEqual(len(seeds), 1)
        result = self.call('EL:AnalyzeSnapshot', snapshot, cfg, panel, seeds)
        self.assertEqual(self.get('devices', self.get('circuits', result)[0]), ['lamp'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
