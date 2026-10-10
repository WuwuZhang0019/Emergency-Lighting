"""Filled device primitives and downstream branches. Date: 2026-10-10.

Synthetic entget fixtures; the supplied ELD omits the SOLID vertex data.
"""
import unittest
from autolisp_host import Pair
import test_analytic_curves as analytic
import test_simple_flow as simple


class SolidContactTests(unittest.TestCase):
    setUp = analytic.AnalyticCurveTests.setUp
    call = analytic.AnalyticCurveTests.call
    get = analytic.AnalyticCurveTests.get
    block = analytic.AnalyticCurveTests.block
    line = analytic.AnalyticCurveTests.line
    batch = analytic.AnalyticCurveTests.batch
    shape = analytic.AnalyticCurveTests.shape
    point = analytic.AnalyticCurveTests.point
    path = analytic.AnalyticCurveTests.path
    network = simple.SimpleFlowTests.network

    def solid(self, name='FILLED', handle='a', pos=(0., 0., 0.), triangle=False, typ='SOLID'):
        self.block(name, 'D', handle, list(pos))
        edge = name + '-edge-0'
        self.entities[edge] = [Pair(0, typ), Pair(5, edge), Pair(8, '0'),
            Pair(10, [-1., -1., 0.]), Pair(11, [1., -1., 0.]),
            Pair(12, [-1., 1., 0.]), Pair(13, [-1., 1., 0.] if triangle else [1., 1., 0.])]
        self.next_entity[edge] = name + '-end'
        return edge

    def test_quad_perimeter_and_interior_are_not_bow_tie(self):
        for typ in ('SOLID', 'TRACE'):
            with self.subTest(typ=typ):
                self.setUp()
                self.solid(typ=typ)
                shape = self.shape()
                self.assertFalse(self.get('issues', shape))
                self.assertEqual(len(self.get('segments', shape)), 4)
                for p in ([0., 0., 0.], [.7, .6, 0.], [-.7, .6, 0.]):
                    self.assertTrue(self.point(p, shape))
                self.assertTrue(self.path([0., 0., 0.], [.1, .1, 0.], shape))
                self.assertFalse(self.point([1.01, 0., 0.], shape))
                self.assertFalse(self.point([0., 0., .01], shape))

    def test_triangle_does_not_use_bounding_rectangle(self):
        self.solid(triangle=True)
        shape = self.shape()
        self.assertEqual(len(self.get('segments', shape)), 3)
        self.assertTrue(self.point([-.5, -.5, 0.], shape))
        self.assertFalse(self.point([.7, .7, 0.], shape))
        self.assertFalse(self.path([.6, .7, 0.], [.8, .7, 0.], shape))

    def test_solid_branch_counts_all_downstream_devices(self):
        self.block('BOX', 'P', 'panel', [-10., 0., 0.])
        self.solid()
        self.block('END', 'D', 'b', [10., 0., 0.])
        self.block('END', 'D', 'c', [0., 10., 0.])
        self.line('w1', [-9., 0., 0.], [-.5, 0., 0.], 'W')
        self.line('w2', [.5, 0., 0.], [9., 0., 0.], 'W')
        self.line('w3', [0., .5, 0.], [0., 9., 0.], 'W')
        self.selected = ['panel', 'a', 'b', 'c', 'w1', 'w2', 'w3']
        result = self.network()
        self.assertEqual(sorted(self.get('id', b) for b in self.get('devices', result)), ['a', 'b', 'c'])

    def test_mirror_scale_and_translation_reuse_preserves_filled_region(self):
        self.solid(pos=(10., 20., 3.), triangle=True)
        self.entities['a'] += [Pair(41, -2.), Pair(42, 2.)]
        self.solid(handle='b', pos=(30., 40., 3.), triangle=True)
        self.entities['b'] += [Pair(41, -2.), Pair(42, 2.)]
        a, b = self.batch(['a', 'b'], True)
        self.assertTrue(self.point([11., 19., 3.], a))
        self.assertTrue(self.point([31., 39., 3.], b))
        self.assertFalse(self.point([29., 41., 3.], b))

    def test_nested_solid_preserves_interior_after_parent_transform(self):
        self.solid(name='CHILD', handle='nested', pos=(2., 0., 0.), triangle=True)
        self.block('PARENT', 'D', 'a', [10., 20., 0.])
        self.blocks['PARENT'] = [Pair(2, 'PARENT'), Pair(10, [0., 0., 0.]),
                                 Pair(70, 0), Pair(-2, 'nested')]
        self.next_entity['nested'] = 'PARENT-end'
        shape = self.shape()
        self.assertTrue(self.point([11.5, 19.5, 0.], shape))
        self.assertFalse(self.point([12.7, 20.7, 0.], shape))

    def test_hidden_solid_does_not_supply_contact_region(self):
        edge = self.solid()
        self.entities[edge].append(Pair(60, 1))
        shape = self.shape()
        self.assertFalse(self.get('segments', shape))
        self.assertFalse(self.point([0., 0., 0.], shape))


if __name__ == '__main__':
    unittest.main()
