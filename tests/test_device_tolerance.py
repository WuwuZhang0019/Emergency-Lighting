"""Bounded XY device contacts. Date: 2026-10-14. Status: finite CAD adapter.

These checks execute the source functions; native AutoCAD acceptance is pending.
"""
import math
import unittest

from autolisp_host import Pair, Symbol, truth
import test_cad_adapter as adapter


class DeviceToleranceGeometryTests(unittest.TestCase):
    call = adapter.CadAdapterTests.call
    get = adapter.CadAdapterTests.get

    def setUp(self):
        adapter.CadAdapterTests.setUp(self)
        self.cfg = self.h.lookup('CFG')
        self.cfg = self.call('EL:Put', Symbol('PARAMS'),
            self.call('EL:Put', Symbol('EPS_BOUNDARY'), .01,
                self.get('params', self.cfg)), self.cfg)

    def cfg_at(self, tol):
        return self.call('EL:Put', Symbol('PARAMS'),
            self.call('EL:Put', Symbol('EPS_BOUNDARY'), tol,
                self.get('params', self.cfg)), self.cfg)

    def shape(self, segments=None, curves=None, regions=None, holes=None):
        return self.call('EL:PrepareContourContact', [
            Pair(Symbol('SEGMENTS'), segments), Pair(Symbol('CURVES'), curves),
            Pair(Symbol('REGIONS'), regions), Pair(Symbol('HOLES'), holes)])

    def path(self, segments, shape, cfg=None):
        return truth(self.call('EL:ContourPathHit',
            [Pair(Symbol('SEGMENTS'), segments)], shape, cfg or self.cfg))

    def test_parallel_middle_contact_queries_shared_tree_with_tolerance(self):
        segments = [[[-1., float(i)*2., 0.], [1., float(i)*2., 0.]] for i in range(128)]
        shape = self.shape(segments=segments)
        self.assertTrue(self.get('contact-tree', shape))
        near = [[[-10., .005, 0.], [10., .005, 0.]]]
        bounds = self.call('EL:SegmentBounds', near)
        self.assertFalse(self.call('EL:ContactSegments', shape, bounds))
        self.assertEqual(len(self.call('EL:ContactSegmentsTolerance', shape, bounds, .01)), 1)
        self.assertTrue(self.path(near, shape))
        self.assertFalse(self.path(near, shape, self.cfg_at(self.call('EL:GapEpsilon'))))
        self.assertFalse(self.path([[[-10., .0101, 0.], [10., .0101, 0.]]], shape))
        self.assertFalse(self.path([[[-10., .005, .001], [10., .005, .001]]], shape))

    def test_segment_closest_points_reject_visible_gaps_and_different_elevations(self):
        a = [[-1.,0.,0.],[1.,0.,0.]]
        for b, expected in (([[-2.,.005,0.],[2.,.005,0.]], True),
                            ([[-2.,.0101,0.],[2.,.0101,0.]], False),
                            ([[1.005,0.,0.],[2.,0.,0.]], True),
                            ([[1.0101,0.,0.],[2.,0.,0.]], False),
                            ([[-2.,.005,.001],[2.,.005,.001]], False),
                            ([[0.,-1.,0.],[0.,1.,0.]], True)):
            self.assertEqual(truth(self.call('EL:SegmentsTouchTolerance', a, b, .01)), expected)

    def test_sloped_device_edge_does_not_expand_z_tolerance(self):
        edge = [[0.,-1.,0.],[0.,1.,.002]]
        shape = self.shape(segments=[edge])
        # XY meets at the origin, but the device edge is at Z=.001 there.
        self.assertFalse(truth(self.call('EL:ContourPointHit',[0.,0.,0.],shape,self.cfg)))
        self.assertFalse(self.path([[[-1.,0.,0.],[1.,0.,0.]]],shape))
        self.assertFalse(truth(self.call('EL:SegmentsTouchTolerance',
                                        [[-1.,0.,0.],[1.,0.,0.]],edge,.01)))

    def test_finite_arc_endpoint_uses_euclidean_distance_not_angle_padding(self):
        curve = [[0.,0.,0.],1.,0.,math.pi/2,None]
        for point, expected in (([1.005,-.005,0.], True),
                                ([1.009,-.009,0.], False),
                                ([1.,-.0095,0.], True),
                                ([1.,-.0101,0.], False),
                                ([1.005,-.005,.001], False)):
            self.assertEqual(truth(self.call('EL:CurvePointHit', point, curve, .01)), expected)
        self.assertFalse(truth(self.call('EL:CurvePointHit', [1.005,-.005,0.], curve,
                                         self.call('EL:GapEpsilon'))))

    def test_curve_segment_handles_arc_ends_and_tangents_with_same_limit(self):
        circle = [[0.,0.,0.],1.,0.,math.tau,None]
        arc = [[0.,0.,0.],1.,0.,math.pi/2,None]
        for segment, curve, expected in (([[-2.,1.005,0.],[2.,1.005,0.]], circle, True),
                                         ([[-2.,1.0101,0.],[2.,1.0101,0.]], circle, False),
                                         ([[1.005,-.02,0.],[1.005,-.005,0.]], arc, True),
                                         ([[1.009,-.02,0.],[1.009,-.009,0.]], arc, False),
                                         ([[-.5,1.005,0.],[.5,1.005,0.]], arc, True),
                                         ([[-.5,1.005,.001],[.5,1.005,.001]], arc, False)):
            self.assertEqual(truth(self.call('EL:CurveSegmentHit', segment, curve, .01)), expected)

    def test_curve_pairs_use_true_boundary_distance_and_keep_legacy_epsilon(self):
        a = [[0.,0.,0.],1.,0.,math.tau,None]
        for b, expected in (([[2.005,0.,0.],1.,0.,math.tau,None], True),
                            ([[2.0101,0.,0.],1.,0.,math.tau,None], False),
                            ([[0.,0.,0.],1.005,0.,math.tau,None], True),
                            ([[0.,0.,0.],.5,0.,math.tau,None], False),
                            ([[2.005,0.,.001],1.,0.,math.tau,None], False)):
            self.assertEqual(truth(self.call('EL:CurvesTouchTolerance', a, b, .01)), expected)
        b = [[2.005,0.,0.],1.,0.,math.tau,None]
        self.assertFalse(truth(self.call('EL:CurvesTouch', a, b)))
        self.assertFalse(truth(self.call('EL:CurvesTouchTolerance', a, b, self.call('EL:GapEpsilon'))))
        quarter = [[0.,0.,0.],1.,0.,math.pi/2,None]
        far_quarter = [[2.005,0.,0.],1.,0.,math.pi/2,None]
        self.assertFalse(truth(self.call('EL:CurvesTouchTolerance', quarter, far_quarter, .01)))
        angular_gap = [[0.,0.,0.],1.,-.005,-math.pi/4,None]
        self.assertTrue(truth(self.call('EL:CurvesTouchTolerance', quarter, angular_gap, .01)))
        angular_gap[2] = -.02
        self.assertFalse(truth(self.call('EL:CurvesTouchTolerance', quarter, angular_gap, .01)))

    def test_hole_interior_stays_empty_and_only_wall_band_can_touch(self):
        shape = self.shape(curves=[[[0.,0.,0.],2.,0.,math.tau,None],
                                   [[0.,0.,0.],1.,0.,math.tau,True]])
        for point, expected in (([0.,0.,0.], False), ([.5,0.,0.], False),
                                ([.98,0.,0.], False), ([.995,0.,0.], True),
                                ([1.005,0.,0.], True), ([1.5,0.,.001], False)):
            self.assertEqual(truth(self.call('EL:ContourPointHit', point, shape, self.cfg)), expected)
        self.assertFalse(self.path([[[-.5,0.,0.],[.5,0.,0.]]], shape))

    def test_visible_wire_width_and_tolerance_both_apply_without_z_expansion(self):
        ring = [[[-1.,-1.,0.],[1.,-1.,0.]], [[1.,-1.,0.],[1.,1.,0.]],
                [[1.,1.,0.],[-1.,1.,0.]], [[-1.,1.,0.],[-1.,-1.,0.]]]
        shape = self.shape(segments=ring, regions=[ring])
        for y, z, expected in ((1.104, 0., True), (1.111, 0., False), (1.104, .001, False)):
            self.entities['wire'] = [Pair(0,'LWPOLYLINE'),Pair(5,'wire'),Pair(8,'W'),
                Pair(70,0),Pair(43,.2),Pair(38,z),Pair(10,[-2.,y]),Pair(10,[2.,y])]
            wire = self.call('EL:WireRecord','wire',self.cfg)
            self.assertFalse(truth(self.call('EL:ContourPathHit',wire,shape,self.cfg)))
            strips = self.get('contact-strips',wire)
            self.assertEqual(len(strips),1)
            self.assertEqual(truth(self.call('EL:ContourPathHit',strips[0],shape,self.cfg)),expected)


class ActualDeviceToleranceTests(unittest.TestCase):
    def test_original_tiny_gap_chain_connects_with_default_and_stays_strict_at_zero(self):
        from actual_contact_fixture import ActualContactFixture
        for tolerance, expected in ((0., set()), (.01, {'F099','84B8','8267'})):
            with self.subTest(tolerance=tolerance):
                fx = ActualContactFixture()
                result = fx.build_case('tiny_device_chain',eps_device=tolerance)
                self.assertEqual({fx.get('id', b) for b in fx.get('devices',result) or []},expected)
                if tolerance:
                    self.assertEqual(set(fx.get('wire-ids',result)),{'F097','F159','F15A'})
                    self.assertEqual(len(fx.get('gap-pairs',result)),1)

    def test_original_shapes_still_reject_gap_above_limit_or_another_elevation(self):
        from actual_contact_fixture import ActualContactFixture
        for offset, z in ((.02,0.), (0.,.001)):
            with self.subTest(offset=offset,z=z):
                fx = ActualContactFixture()
                position = fx.dxf('F099',10)
                moved = fx.call('SUBST',fx.call('CONS',10,[position[0],position[1]+offset,z]),
                                fx.call('ASSOC',10,fx.record('F099')),fx.record('F099'))
                fx.entities['F099'] = moved
                result = fx.build_case('tiny_device_chain',eps_device=.01)
                self.assertFalse(fx.get('devices',result))


if __name__ == '__main__':
    unittest.main()
