"""Whole-box incremental regressions. Date: 2026-10-08. No real CAD acceptance."""
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

    def test_open_contour_has_no_invented_interior(self):
        self.block('LAMP', 'D', 'lamp', [0., 0., 0.])
        self.next_entity['LAMP-edge-2'] = 'LAMP-end'
        rec = self.record('lamp')
        self.assertFalse(truth(self.call('EL:RegionContains', [0., 0., 0.], rec)))
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


if __name__ == '__main__':
    unittest.main()
