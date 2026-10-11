"""Whole-box incremental regressions. Date: 2026-10-11. No real CAD acceptance."""
import unittest
from autolisp_host import Symbol, Pair, truth
import test_cad_adapter as adapter
ROOT = adapter.ROOT


class BoxTests(unittest.TestCase):
    setUp = adapter.CadAdapterTests.setUp
    call = adapter.CadAdapterTests.call
    get = adapter.CadAdapterTests.get
    line = adapter.CadAdapterTests.line
    block = adapter.CadAdapterTests.block

    def record(self, handle):
        return self.call('EL:BlockRecord', handle, self.h.lookup('CFG'))

    def path_hit(self, a, b, block):
        self.line('w', a, b, 'W')
        cfg = self.h.lookup('CFG')
        wire = self.call('EL:WireRecord', 'w', cfg)
        return truth(self.call('EL:PathBlockHit', wire, block, cfg))

    def test_interior_crossing_and_elevation(self):
        self.block('LAMP', 'UNSAMPLED', 'lamp', [0., 0., 0.])
        rec = self.record('lamp')
        self.assertTrue(truth(self.call('EL:RegionContains', [0., 0., 0.], rec)))
        self.assertTrue(self.path_hit([-5., 0., 0.], [5., 0., 0.], rec))
        self.assertFalse(self.path_hit([-5., 0., 2.], [5., 0., 2.], rec))
        self.assertFalse(self.path_hit([-5., 2., 0.], [5., 2., 0.], rec))

    def test_open_symbol_uses_whole_block_interior(self):
        self.block('LAMP', 'D', 'lamp', [0., 0., 0.])
        self.next_entity['LAMP-edge-2'] = 'LAMP-end'
        rec = self.record('lamp')
        self.assertTrue(truth(self.call('EL:RegionContains', [0., 0., 0.], rec)))
        self.assertTrue(self.path_hit([0., -1., 0.], [0., -2., 0.], rec))

    def test_concavity_holes_and_decoration(self):
        self.h.run('''
          (setq outer (EL:Segments '((0.0 0.0 0.0) (6.0 0.0 0.0) (6.0 6.0 0.0)
            (4.0 6.0 0.0) (4.0 2.0 0.0) (2.0 2.0 0.0) (2.0 6.0 0.0) (0.0 6.0 0.0) (0.0 0.0 0.0))))
          (setq hole (EL:Segments '((0.5 0.5 0.0) (1.5 0.5 0.0) (1.5 1.5 0.0) (0.5 1.5 0.0) (0.5 0.5 0.0))))
          (setq b (list (cons 'regions (list outer)) (cons 'holes (list hole))))''')
        b = self.h.lookup('B')
        for point, expected in [([3., 4., 0.], False), ([1., 1., 0.], False), ([1., 4., 0.], True)]:
            self.assertEqual(truth(self.call('EL:RegionContains', point, b)), expected)

    def test_crossed_or_nonplanar_loop_does_not_create_interior(self):
        for points in ["((0 0 0) (2 2 0) (0 2 0) (2 0 0) (0 0 0))",
                       "((0 0 0) (2 0 0) (2 2 1) (0 2 0) (0 0 0))"]:
            self.assertFalse(truth(self.h.run(f"(EL:ClosedRings (EL:Segments '{points}))")))

    def test_unsampled_block_discovery_and_identity_mapping(self):
        self.block('NEW', 'NEW_LAYER', 'new', [0., 0., 0.])
        self.line('w', [-5., 0., 0.], [5., 0., 0.], 'W')
        self.selected = ['new', 'w']
        snap = self.call('EL:CollectEndpointSnapshot', self.h.lookup('CFG'))
        rec = self.get('blocks', snap)[0]
        self.assertEqual(self.get('role', rec), Symbol('UNKNOWN'))
        identity = self.get('identity', rec)
        roles = [[Pair(Symbol('IDENTITY'), identity), Pair(Symbol('ROLE'), Symbol('DEVICE')), Pair(Symbol('CONFIRMED'), True)]]
        cfg = self.call('EL:Put', Symbol('ROLES'), roles, self.h.lookup('CFG'))
        self.assertEqual(self.get('role', self.call('EL:BlockRecord', 'new', cfg)), Symbol('DEVICE'))

    def analyze(self):
        cfg = self.h.lookup('CFG')
        snap = self.call('EL:CollectEndpointSnapshot', cfg)
        physical = self.call('EL:BuildPhysical', snap, cfg, 'panel')
        snap = self.get('snapshot', physical)
        seeds = self.call('EL:SeedCandidates', snap, cfg, 'panel')
        return self.call('EL:AnalyzeSnapshot', snap, cfg, 'panel', seeds)

    def test_three_exits_and_midpath_device_do_not_merge(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('LAMP', 'D', 'right', [12., 0., 0.])
        self.block('LAMP', 'D', 'left', [-12., 0., 0.])
        self.block('LAMP', 'D', 'top', [0., 12., 0.])
        self.block('LAMP', 'D', 'middle', [6., 0., 0.])
        for name, a, b in [('wr', [1., 0., 0.], [11., 0., 0.]),
                           ('wl', [-1., 0., 0.], [-11., 0., 0.]),
                           ('wt', [0., 1., 0.], [0., 11., 0.])]:
            self.line(name, a, b, 'W')
        self.selected = ['panel', 'right', 'left', 'top', 'middle', 'wr', 'wl', 'wt']
        result = self.analyze()
        circuits = self.get('circuits', result)
        self.assertEqual(len(circuits), 3)
        self.assertEqual(sorted(len(self.get('devices', c)) for c in circuits), [1, 1, 2])
        self.assertTrue(truth(self.get('complete', result)))
        self.assertTrue(all(truth(self.get('wire-attached', e)) for e in self.get('ends', self.get('snapshot', result))))
        ids = [(self.get('id', c), self.get('wire', self.get('seed', c))) for c in circuits]
        self.selected.reverse()
        self.assertEqual(ids, [(self.get('id', c), self.get('wire', self.get('seed', c))) for c in self.get('circuits', self.analyze())])

    def test_shared_device_conflicts_and_other_panel_stops_traversal(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('LAMP', 'D', 'shared', [10., 0., 0.])
        self.line('a', [1., 0., 0.], [9., 0., 0.], 'W')
        self.line('b', [0., 1., 0.], [10., 1., 0.], 'W')
        self.selected = ['panel', 'shared', 'a', 'b']
        result = self.analyze()
        self.assertEqual(len(self.get('circuits', result)), 2)
        self.assertTrue(all(not truth(self.get('complete', c)) for c in self.get('circuits', result)))
        self.block('BOX', 'P', 'other', [10., 0., 0.])
        self.block('LAMP', 'D', 'far', [20., 0., 0.])
        self.line('after', [11., 0., 0.], [19., 0., 0.], 'W')
        self.selected = ['panel', 'other', 'far', 'a', 'after']
        result = self.analyze()
        c = self.get('circuits', result)[0]
        self.assertFalse(truth(self.get('complete', c)))
        self.assertNotIn('far', self.get('devices', c) or [])

    def test_unknown_blocks_gap_and_ignore_does_not_short_wires(self):
        self.block('NEW', 'NEW', 'unknown', [0., 0., 0.])
        self.line('a', [-10., 0., 0.], [-1., 0., 0.], 'W')
        self.line('b', [1., 0., 0.], [10., 0., 0.], 'W')
        self.selected = ['unknown', 'a', 'b']
        cfg = self.h.lookup('CFG')
        snap = self.call('EL:CollectEndpointSnapshot', cfg)
        p = self.call('EL:BuildPhysical', snap, cfg, None)
        self.assertFalse(self.get('edges', p))
        self.assertTrue(all(truth(self.get('wire-attached', e)) for e in self.get('ends', self.get('snapshot', p))))
        rec = self.call('EL:Put', Symbol('ROLE'), Symbol('IGNORE'), self.get('blocks', snap)[0])
        snap = self.call('EL:Put', Symbol('BLOCKS'), [rec], snap)
        self.assertFalse(self.get('edges', self.call('EL:BuildPhysical', snap, cfg, None)))

    def test_power_table_merges_ids_and_keeps_identity_variants(self):
        self.h.load_definitions(ROOT / 'src/statistics.lsp')
        self.h.run('''
          (setq row1 '((identity "lamp" nil "def") (name . "lamp") (ids "a") (count . 1)))
          (setq row2 '((identity "lamp" nil "def") (name . "lamp") (ids "b") (count . 1)))
          (setq row3 '((identity "lamp" ((state . "other")) "def") (name . "lamp") (ids "c") (count . 1)))
          (setq result (list (cons 'circuits (list
            (list (cons 'id "R1") (cons 'counts (list row1 row3)))
            (list (cons 'id "R2") (cons 'counts (list row2)))))))''')
        rows = self.call('EL:PowerTableRows', self.h.lookup('RESULT'))
        self.assertEqual(len(rows), 2)
        row = next(r for r in rows if self.get('count', r) == 2)
        self.assertEqual(set(self.get('ids', row)), {'a', 'b'})
        self.assertEqual(len(self.get('circuits', row)), 2)

    def test_zero_watts_requires_explicit_confirmation(self):
        self.h.load_definitions(ROOT / 'src/statistics.lsp')
        self.h.load_definitions(ROOT / 'src/main.lsp')
        tiles = {'category': '4', 'display': '控制设备', 'watts': '0', 'zero': '0'}
        self.h.builtins.update({'GET_TILE': lambda key: tiles[key],
                               'SET_TILE': lambda key, val: tiles.update({key: val})})
        self.h.run('''(setq *EL:PowerRows* '(((identity "lamp" nil "def"))))
          (setq *EL:PowerIndex* 0)''')
        self.assertFalse(truth(self.h.run('(EL:PowerUISave)')))
        self.assertIsNone(self.h.lookup('*EL:POWEREDITS*'))
        tiles['zero'] = '1'
        self.assertTrue(truth(self.h.run('(EL:PowerUISave)')))
        self.assertEqual(self.get('watts', self.h.lookup('*EL:POWEREDITS*')[0]), 0)

    def test_migration_preserves_power_and_rejects_unconfirmed_roles(self):
        self.h.load_definitions(ROOT / 'src/statistics.lsp')
        self.h.run('''
          (setq power '((identity "LAMP" nil "definition") (category . lighting)
            (display . "lamp") (watts . 5)))
          (setq legacy (EL:Put 'version 1 (EL:Put 'powers (list power) cfg)))
          (setq migrated (EL:MigrateBoxConfig (EL:Put 'gap-pairs '(stale) legacy)))''')
        migrated = self.h.lookup('MIGRATED')
        self.assertEqual(self.get('version', migrated), 2)
        self.assertEqual(self.get('watts', self.get('powers', migrated)[0]), 5)
        self.assertFalse(self.get('gap-pairs', migrated))
        self.assertTrue(truth(self.call('EL:ConfigValid', migrated, 'adapter-fixture.dwg')))
        self.assertFalse(truth(self.h.run('''(EL:ConfigValid
          (EL:Put 'roles '(((identity "LAMP" nil "definition") (role . device))) migrated)
          "adapter-fixture.dwg")''')))

    def test_exit_cache_and_source_validity_ignore_only_power_changes(self):
        self.h.run('''
          (setq snapshot '((signature . "source")))
          (setq seeds '(((id . "R1") (key "wire" start))))
          (setq cfg (EL:RememberExits cfg "panel" snapshot seeds T))
          (setq result (list (cons 'drawing "adapter-fixture.dwg")
            (cons 'rules (EL:RecognitionRules cfg)) (cons 'snapshot snapshot)))''')
        self.assertTrue(truth(self.h.run('(EL:ReusableExits cfg "panel" snapshot)')))
        self.assertTrue(truth(self.h.run("(EL:SourceCurrent result (EL:Put 'powers '(new-power) cfg) snapshot)")))
        self.assertFalse(truth(self.h.run("(EL:SourceCurrent result cfg '((signature . \"changed\")))")))
        self.assertFalse(truth(self.h.run("(EL:SourceCurrent result (EL:Put 'roles '(changed) cfg) snapshot)")))
        self.assertFalse(truth(self.h.run("(EL:ReusableExits (EL:Put 'wire-layers '(\"OTHER\") cfg) \"panel\" snapshot)")))

    def test_arc_path_uses_arc_not_chord(self):
        self.block('LAMP', 'D', 'arc-lamp', [0., -5., 0.])
        self.block('LAMP', 'D', 'chord-lamp', [0., 0., 0.])
        self.entities['arc'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'arc'), Pair(8, 'W'),
            Pair(10, [-5., 0.]), Pair(42, 1.), Pair(10, [5., 0.]), Pair(410, 'Model')]
        cfg = self.h.lookup('CFG')
        wire = self.call('EL:WireRecord', 'arc', cfg)
        self.assertTrue(truth(self.call('EL:PathBlockHit', wire, self.record('arc-lamp'), cfg)))
        self.assertFalse(truth(self.call('EL:PathBlockHit', wire, self.record('chord-lamp'), cfg)))

    def test_whole_bounds_use_wcs_and_ignore_internal_holes(self):
        self.block('LAMP', 'D', 'nested', [2., 0., 0.])
        self.entities['outer'] = [Pair(0, 'INSERT'), Pair(5, 'outer'), Pair(8, 'D'), Pair(2, 'OUTER'),
            Pair(10, [10., 10., 0.]), Pair(41, 2.), Pair(42, 3.), Pair(50, 1.5707963267948966)]
        self.blocks['OUTER'] = [Pair(10, [0., 0., 0.]), Pair(70, 0), Pair(-2, 'nested')]
        self.next_entity['nested'] = 'LAMP-end'
        self.bounds['outer'] = [[7., 12., 0.], [13., 16., 0.]]
        rec = self.record('outer')
        self.assertTrue(truth(self.call('EL:RegionContains', [10., 14., 0.], rec)))
        self.assertFalse(truth(self.call('EL:RegionContains', [14., 10., 0.], rec)))
        self.entities['hole'] = [Pair(0, 'LWPOLYLINE'), Pair(8, 'EL_HOLE'), Pair(70, 1),
            *[Pair(10, p) for p in [[-.5, -.5], [.5, -.5], [.5, .5], [-.5, .5]]]]
        self.next_entity['LAMP-edge-3'] = 'hole'
        self.next_entity['hole'] = 'LAMP-end'
        rec = self.record('nested')
        self.assertFalse(self.get('issues', rec))
        self.assertTrue(truth(self.call('EL:RegionContains', [2., 0., 0.], rec)))
        self.assertTrue(truth(self.call('EL:RegionContains', [2.8, 0., 0.], rec)))

    def test_middle_crossing_other_panel_records_connection_and_requires_review(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('BOX', 'P', 'other', [10., 0., 0.])
        self.block('LAMP', 'D', 'far', [20., 0., 0.])
        self.line('w', [1., 0., 0.], [19., 0., 0.], 'W')
        self.selected = ['panel', 'other', 'far', 'w']
        result = self.analyze()
        self.assertFalse(truth(self.get('complete', result)))
        self.assertIn(['w', 'other'], self.get('path-contacts', self.get('snapshot', result)))
        self.assertIn(Symbol('OTHER_PANEL'), [self.get('code', i) for i in self.get('issues', self.get('circuits', result)[0])])

    def test_spatial_broad_phase_with_real_shaped_bounds_retains_coincident_blocks(self):
        self.block('LAMP', 'D', 'near', [0., 0., 0.])
        self.block('LAMP', 'D', 'coincident', [0., 0., 0.])
        self.block('LAMP', 'D', 'far', [1000., 0., 0.])
        self.line('w', [-5., 0., 0.], [5., 0., 0.], 'W')
        self.selected = ['near', 'coincident', 'far', 'w']
        self.h.builtins['EL:ENTITYBOUNDS'] = lambda e: (
            [[999., -1., 0.], [1001., 1., 0.]] if e == 'far' else [[-1., -1., 0.], [1., 1., 0.]])
        snap = self.call('EL:CollectEndpointSnapshot', self.h.lookup('CFG'))
        self.assertEqual(set(self.get('id', b) for b in self.get('blocks', snap)), {'near', 'coincident'})

    def test_drawing_role_overrides_library_role(self):
        self.block('LAMP', 'D', 'lamp', [0., 0., 0.])
        identity = self.get('identity', self.record('lamp'))
        cfg = self.call('EL:PutRole', self.h.lookup('CFG'), identity, Symbol('IGNORE'))
        lib_cfg = self.call('EL:PutRole', self.h.lookup('CFG'), identity, Symbol('DEVICE'))
        self.h.frames[0]['*EL:LIBRARYROLES*'] = self.get('roles', lib_cfg)
        self.assertEqual(self.get('role', self.call('EL:BlockRecord', 'lamp', cfg)), Symbol('IGNORE'))

    def test_unincluded_layer_at_panel_and_scope_extension(self):
        self.h.load_definitions(ROOT / 'src/main.lsp')
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.line('a', [1., 0., 0.], [10., 0., 0.], 'W')
        self.line('b', [0., 1., 0.], [0., 10., 0.], 'W2')
        self.selected = ['panel', 'a', 'b']
        cfg = self.h.lookup('CFG')
        snap = self.call('EL:CollectEndpointSnapshot', cfg)
        self.assertEqual(self.call('EL:OutsidePorts', snap, cfg, 'panel'), [['b', 'W2']])
        cfg = self.call('EL:ScopeLayer', cfg, 'W2')
        snap = self.call('EL:CollectEndpointSnapshot', cfg)
        self.assertFalse(self.call('EL:OutsidePorts', snap, cfg, 'panel'))
        self.assertEqual(len(self.get('wires', snap)), 2)

    def test_source_change_during_role_review_saves_nothing(self):
        for module in ('statistics', 'main', 'diagram-update'):
            self.h.load_definitions(ROOT / 'src' / f'{module}.lsp')
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('LAMP', 'D', 'lamp', [12., 0., 0.])
        self.line('wire', [1., 0., 0.], [11., 0., 0.], 'W')
        self.selected = ['panel', 'lamp', 'wire']
        cfg, writes = self.h.lookup('CFG'), []

        def changed(snapshot, config):
            self.line('wire', [1., 0., 0.], [20., 0., 0.], 'W')
            return config

        self.h.builtins.update({
            'EL:LOADCONFIG': lambda: cfg,
            'ENTSEL': lambda prompt: ['panel' if '配电箱' in prompt else 'wire', [0., 0., 0.]],
            'HANDENT': lambda handle: handle, 'REDRAW': lambda *args: None,
            'EL:REVIEWEXITS': lambda seeds: [seeds], 'EL:REVIEWROLES': changed,
            'EL:SAVECONFIG': lambda config: writes.append(config) or config,
        })
        self.h.run('(c:ELTRACE)')
        self.assertEqual(writes, [])
        self.assertIsNone(self.h.lookup('*EL:RESULT*'))
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))

    def test_exit_dialog_bulk_selection_and_scope_confirmation(self):
        self.h.load_definitions(ROOT / 'src/main.lsp')
        tiles, callbacks = {}, {}
        self.h.frames[0]['*EL:ROOT*'] = 'package/'
        self.h.builtins.update({
            'LOAD_DIALOG': lambda *args: 1, 'NEW_DIALOG': lambda *args: True,
            'UNLOAD_DIALOG': lambda *args: None, 'START_LIST': lambda *args: None,
            'ADD_LIST': lambda *args: None, 'END_LIST': lambda: None,
            'SET_TILE': lambda k, v: tiles.update({k: v}), 'GET_TILE': lambda k: tiles.get(k, '0'),
            'ACTION_TILE': lambda k, v: callbacks.update({k: v}), 'DONE_DIALOG': lambda n: n,
        })

        def start_dialog():
            tiles.update({'exits': '0 2', 'scope_exclude': '1', 'role_recheck': '1'})
            return self.h.run(callbacks['accept'])

        self.h.builtins['START_DIALOG'] = start_dialog
        result = self.h.run('''(EL:ReviewExits '(
          ((id . "R1") (wire . "a") (key "a" start) (point 1.0 0.0 0.0))
          ((id . "R2") (wire . "in") (key "in" start) (point 0.0 1.0 0.0))
          ((id . "R3") (wire . "c") (key "c" start) (point -1.0 0.0 0.0))))''')
        self.assertEqual([self.get('wire', seed) for seed in result[0]], ['a', 'c'])
        self.assertTrue(truth(self.h.lookup('*EL:SCOPECONFIRMED*')))
        self.assertTrue(truth(self.h.lookup('*EL:REVIEWALLROLES*')))
        self.assertIsNone(self.h.lookup('*EL:DIALOGID*'))


if __name__ == '__main__':
    unittest.main()
