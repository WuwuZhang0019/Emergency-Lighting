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


if __name__ == '__main__':
    unittest.main()
