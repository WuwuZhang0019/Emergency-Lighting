"""Sampled ELLIPSE pose reuse regressions. Date: 2026-10-21.

Finite ENTGET fixtures exercise source algorithms, not native AutoCAD acceptance.
The small ellipse keeps the real DXF axis ratio and parameter interval; the
original CE2 dimensions are checked once without an expensive ring rebuild.
"""
import math
import unittest
from pathlib import Path

from autolisp_host import Pair, Symbol, truth
import test_contact_reuse as reuse


class PoseReuseTests(unittest.TestCase):
    def setUp(self):
        reuse.ContactReuseTests.setUp(self)
        params = self.call('EL:Put', Symbol('EPS_DEVICE'), 0., self.get('params', self.cfg))
        self.cfg = self.call('EL:Put', Symbol('PARAMS'), params, self.cfg)

    call = reuse.ContactReuseTests.call
    get = reuse.ContactReuseTests.get
    block = reuse.ContactReuseTests.block
    line = reuse.ContactReuseTests.line
    count = reuse.ContactReuseTests.count
    batch = reuse.ContactReuseTests.batch

    RATIO = 0.9999999992735643
    START = 4.712388872673587
    END = 10.99557417985317
    MAJOR = (-0.0000363221437224, 337.2181972712175, 0.)

    def ellipse(self, handle='a', name='ELLIPSE', pos=(1000., 1000., 0.),
                factor=.001, ratio=None, hole=False):
        self.block(name, 'D', handle, list(pos))
        edge = name+'-edge-0'
        self.entities[edge] = [Pair(0, 'ELLIPSE'), Pair(5, edge), Pair(8, '0'),
            Pair(10, [0., 0., 0.]), Pair(11, [v*factor for v in self.MAJOR]),
            Pair(40, self.RATIO if ratio is None else ratio), Pair(41, self.START),
            Pair(42, self.END), Pair(210, [0., 0., 1.])]
        # Two open arrow segments remain conductive geometry inside the ellipse.
        arrow = name+'-arrow'
        self.entities[arrow] = [Pair(0, 'LWPOLYLINE'), Pair(5, arrow), Pair(8, '0'),
            Pair(70, 0), Pair(10, [-150.*factor, 0.]),
            Pair(10, [0., 100.*factor]), Pair(10, [150.*factor, 0.])]
        self.next_entity[edge] = arrow
        self.next_entity[arrow] = name+'-end'
        if hole:
            child = name+'-hole'
            self.entities[child] = [Pair(0, 'LWPOLYLINE'), Pair(5, child),
                Pair(8, 'EL_HOLE'), Pair(70, 1), Pair(10, [-.05, -.05]),
                Pair(10, [.05, -.05]), Pair(10, [.05, .05]), Pair(10, [-.05, .05])]
            self.next_entity[arrow] = child
            self.next_entity[child] = name+'-end'
        return handle

    def record(self, handle):
        return [Pair(Symbol('ID'), handle), Pair(Symbol('ENTITY'), handle),
                Pair(Symbol('NAME'), 'shared visible name')]

    def open_context(self):
        self.h.frames.append({'*EL:DEVICETEMPLATEENABLED*': True,
                              '*EL:DEVICETEMPLATECACHE*': None,
                              '*EL:DEVICECONTACTCACHE*': None})
        self.addCleanup(self.h.frames.pop)

    def shape(self, handle):
        return self.call('EL:DeviceContactShape', self.record(handle))

    def segments(self, shape):
        return [self.call('EL:ContactWorldSegment', edge, shape)
                for edge in self.call('EL:ContactRawSegments', shape) or []]

    def assert_contacts_equal(self, old, new, handle):
        matrix = self.call('EL:InsertMatrix', handle)
        cfg = self.call('EL:StrictDeviceConfig', self.cfg)
        points = [[0., 0., 0.], [.2, 0., 0.], [.6, 0., 0.],
                  [.05, 0., 0.], [.2, 0., .01]]
        points += [[-.15, 0., 0.]]
        world_points = [self.call('EL:AffinePoint', p, matrix) for p in points]
        # Actual sampled WCS vertices exercise contact boundaries after reuse.
        world_points += [edge[0] for edge in self.get('segments', old)[:3]]
        for point in world_points:
            self.assertEqual(truth(self.call('EL:ContourPointHit', point, old, cfg)),
                             truth(self.call('EL:ContourPointHit', point, new, cfg)), point)
        for a, b in (([-.6, 0., 0.], [.6, 0., 0.]),
                     ([-.6, .6, 0.], [.6, .6, 0.]),
                     ([-.6, 0., .01], [.6, 0., .01])):
            wire = [Pair(Symbol('SEGMENTS'), [[self.call('EL:AffinePoint', a, matrix),
                                              self.call('EL:AffinePoint', b, matrix)]])]
            self.assertEqual(truth(self.call('EL:ContourPathHit', wire, old, cfg)),
                             truth(self.call('EL:ContourPathHit', wire, new, cfg)))

    def test_repeated_real_ellipse_pose_builds_contour_rings_and_tree_once(self):
        handles = [self.ellipse(handle=str(i), pos=(10000.+20.*i, 10000.+3.*i, float(i))) for i in range(4)]
        expected = self.batch(handles, None)
        reads = self.count('EL:DeviceContour')
        rings = self.count('EL:ClosedRings')
        prepared = self.count('EL:PrepareContourContact')
        actual = self.batch(handles, True)
        self.assertEqual((len(reads), len(rings), len(prepared)), (1, 1, 1))
        first = actual[0]
        self.assertTrue(self.get('sampled-curves', first))
        self.assertFalse(self.get('curves', first))
        self.assertEqual(len(self.segments(first)), 66)
        self.assertTrue(self.get('regions', first))
        self.assertTrue(self.get('contact-tree', first))
        for handle, old, new in zip(handles, expected, actual):
            self.assertEqual(self.get('id', old), self.get('id', new))
            self.assertEqual(self.get('segments', old), self.segments(new))
            self.assert_contacts_equal(old, new, handle)
        for new in actual[1:]:
            template = self.get('contact-template', new)
            self.assertTrue(template)
            for field in ('segments', 'regions', 'holes', 'contact-tree'):
                # The finite host's CDR slices proper lists at EL:Get. Compare
                # their elements: native geometry/index nodes must stay shared.
                before, after = self.get(field, first), self.get(field, template)
                self.assertEqual(before, after)
                for original, shared in zip(before or [], after or []):
                    self.assertIs(original, shared)
            # No 2000-edge/ring copy should be needed for every sampled instance.
            for field in ('segments', 'regions', 'holes'):
                self.assertFalse(self.get(field, new))

    def test_original_ce2_keeps_real_ellipse_and_2050_segments(self):
        self.ellipse(factor=1.)
        sampled = self.count('EL:EllipseSegments')
        shape = self.call('EL:DeviceContour', 'a')
        self.assertEqual(len(sampled), 1)
        self.assertEqual(self.get('sampled-curves', shape), True)
        self.assertFalse(self.get('curves', shape))
        self.assertEqual(len(self.get('segments', shape)), 2050)
        data, error = sampled[0]
        self.assertEqual(next(p.cdr for p in data if p.car == 40), self.RATIO)
        self.assertEqual(next(p.cdr for p in data if p.car == 11), list(self.MAJOR))
        self.assertEqual((next(p.cdr for p in data if p.car == 41), next(p.cdr for p in data if p.car == 42)), (self.START, self.END))
        self.assertEqual(error, .0005)

    def test_holes_and_elevation_share_prepared_shape_with_equal_contact_results(self):
        handles = [self.ellipse(hole=True), self.ellipse(handle='b', pos=(1020., 1003., 5.), hole=True)]
        expected = self.batch(handles, None)
        actual = self.batch(handles, True)
        first, second = actual
        self.assertTrue(self.get('holes', first))
        original_holes = self.get('holes', first)
        shared_holes = self.get('holes', self.get('contact-template', second))
        self.assertEqual(original_holes, shared_holes)
        self.assertIs(original_holes[0], shared_holes[0])
        for handle, old, new in zip(handles, expected, actual):
            self.assert_contacts_equal(old, new, handle)
        strict = self.call('EL:StrictDeviceConfig', self.cfg)
        self.assertFalse(truth(self.call('EL:ContourPointHit', [1020., 1003., 5.], second, strict)))
        self.assertTrue(truth(self.call('EL:ContourPointHit', [1020.2, 1003., 5.], second, strict)))
        self.assertFalse(truth(self.call('EL:ContourPointHit', [1020.2, 1003., 0.], second, strict)))

    def test_full_pose_rotation_mirror_normal_and_nonuniform_scales_do_not_mix(self):
        transforms = ([], [Pair(50, math.pi/4)], [Pair(41, -1.)],
                      [Pair(41, 2.), Pair(42, .5)], [Pair(43, 2.)],
                      [Pair(210, [0., 0., -1.])])
        self.h.builtins['TRANS'] = lambda p, n, *a: [-p[0], p[1], -p[2]] if n == [0., 0., -1.] else p
        handles = []
        for i, transform in enumerate(transforms):
            for j in range(2):
                handle = f'{i}-{j}'
                self.ellipse(handle=handle, pos=(1000.+20.*j, 1000., 0.))
                self.entities[handle].extend(transform)
                handles.append(handle)
        expected = self.batch(handles, None)
        reads = self.count('EL:DeviceContour')
        actual = self.batch(handles, True)
        self.assertEqual(len(reads), len(transforms))
        for handle, old, new in zip(handles, expected, actual):
            self.assertEqual(self.get('segments', old), self.segments(new))
            self.assert_contacts_equal(old, new, handle)

    def test_actual_anonymous_definitions_and_axis_ratios_do_not_mix(self):
        handles = []
        for i, (name, ratio) in enumerate((('*U1', self.RATIO), ('*U2', .6))):
            handles += [self.ellipse(handle=f'{i}-{j}', name=name,
                        pos=(1000.+20.*i+3.*j, 1000., 0.), ratio=ratio) for j in range(2)]
        reads = self.count('EL:DeviceContour')
        actual = self.batch(handles, True)
        self.assertEqual(len(reads), 2)
        self.assertNotEqual(self.segments(actual[0]), self.segments(actual[2]))
        self.assertIsNot(self.get('contact-template', actual[1]), self.get('contact-template', actual[3]))

    def test_definition_edit_with_identical_outer_bounds_rebuilds(self):
        self.ellipse(); self.ellipse(handle='b', pos=(1020., 1000., 0.))
        self.open_context()
        first = self.shape('a')
        child = 'ELLIPSE-arrow'
        # Internal edit leaves the ellipse and outer bounds untouched.
        self.entities[child][-1] = Pair(10, [.17, .02])
        reads = self.count('EL:DeviceContour')
        changed = self.shape('b')
        self.assertEqual(len(reads), 1)
        self.assertFalse(self.get('contact-template', changed))
        direct = self.batch(['b'], None)[0]
        self.assertEqual(self.get('segments', direct), self.segments(changed))
        self.assertNotEqual(self.segments(first), self.segments(changed))

    def test_wcs_sampling_error_is_part_of_pose_validity(self):
        self.ellipse(); self.ellipse(handle='b', pos=(1020., 1000., 0.))
        self.open_context()
        first = self.shape('a')
        self.h.builtins['EL:DEVICECONTOURTOLERANCE'] = lambda: .0001
        reads = self.count('EL:DeviceContour')
        changed = self.shape('b')
        self.assertEqual(len(reads), 1)
        self.assertFalse(self.get('contact-template', changed))
        self.assertGreater(len(self.segments(changed)), len(self.segments(first)))

    def test_drawing_owner_and_fresh_boundary_rebuild_pose(self):
        for change in ('owner', 'epoch'):
            with self.subTest(change=change):
                self.setUp()
                self.ellipse(); self.ellipse(handle='b', pos=(1020., 1000., 0.))
                self.h.frames.append({'*EL:DEVICETEMPLATEENABLED*': True,
                    '*EL:DEVICETEMPLATECACHE*': None, '*EL:DEVICECONTACTCACHE*': None})
                try:
                    self.shape('a')
                    if change == 'owner':
                        self.h.builtins['NAMEDOBJDICT'] = lambda: 'another-drawing'
                    else:
                        self.call('EL:FreshBoundary')
                    reads = self.count('EL:DeviceContour')
                    shape = self.shape('b')
                    self.assertEqual(len(reads), 1)
                    self.assertFalse(self.get('contact-template', shape))
                finally:
                    self.h.frames.pop()

    def test_same_recognition_network_and_split_share_instance_and_pose_results(self):
        root = Path(__file__).resolve().parents[1]
        self.h.load_definitions(root/'src'/'panel.lsp')
        self.block('BOX', 'P', 'panel', [998., 1000., 0.])
        self.ellipse(); self.ellipse(handle='b', pos=(1020., 1000., 0.))
        self.ellipse(handle='later', pos=(1005., 1000., 0.))
        self.line('wire', [999., 1000., 0.], [1020., 1000., 0.], 'W')
        self.selected = ['panel', 'wire', 'a', 'b']
        self.cfg = self.call('EL:Put', Symbol('DEVICE-NAMES'), ['ELLIPSE'], self.cfg)
        self.h.frames[0]['*EL:RECOGNITIONPASS*'] = True
        reads = self.count('EL:DeviceContour')
        network = self.call('EL:SimpleNetwork', self.call('EL:SimpleCollect', self.cfg), self.cfg, 'panel')
        self.assertEqual(sorted(self.get('id', d) for d in self.get('devices', network)), ['a', 'b'])
        self.assertEqual(len(reads), 1)
        self.assertTrue(self.h.lookup('*EL:RECOGNITIONCONTACTS*'))
        reads.clear()
        definitions = self.count('EL:DeviceDefinitionContour')
        params, body = self.h.functions[Symbol('EL:EXITNUMBERSCOPE')]
        original_scope = [Symbol('LAMBDA'), params, *body]
        scopes = []

        def number_scope(seed, current_network, cfg):
            # Requery both built instances and one matching pose first needed
            # by numbering. This executes the actual DeviceContactShape path.
            scopes.append([self.shape(h) for h in ('a', 'b', 'later')])
            return self.h.call(original_scope, [seed, current_network, cfg])

        self.h.builtins['EL:EXITNUMBERSCOPE'] = number_scope
        split = self.call('EL:SplitNetwork', network, self.cfg)
        self.assertEqual(len(self.get('circuits', split)), 1)
        self.assertEqual(len(scopes), 1)
        self.assertTrue(self.get('contact-template', scopes[0][2]))
        self.assertEqual((len(reads), len(definitions)), (0, 0))

    def test_fresh_boundary_invalidates_the_same_instance_id_cache(self):
        self.ellipse()
        self.open_context()
        first = self.shape('a')
        self.assertTrue(self.get('contact-ready', first))
        self.call('EL:FreshBoundary')
        reads = self.count('EL:DeviceContour')
        second = self.shape('a')
        self.assertEqual(len(reads), 1)
        self.assertFalse(self.get('contact-template', second))
        self.assertTrue(self.get('contact-ready', second))
        self.assertEqual(self.segments(first), self.segments(second))

    def test_origin_to_translated_fractional_ellipse_falls_back_without_contact_changes(self):
        handles = [self.ellipse(pos=(0., 0., 0.)),
                   self.ellipse(handle='b', pos=(20., 3., 0.))]
        old = self.batch(handles, None)
        reads = self.count('EL:DeviceContour')
        new = self.batch(handles, True)
        self.assertEqual(len(reads), 2)
        self.assertFalse(self.get('contact-template', new[1]))
        self.assertEqual(self.get('segments', old[1]), self.segments(new[1]))
        self.assert_contacts_equal(old[1], new[1], 'b')

    def test_large_wcs_translation_uses_original_instance_path(self):
        handles = [self.ellipse(), self.ellipse(handle='b', pos=(1e12, -1e12, 0.))]
        direct = self.batch(handles, None)
        reads = self.count('EL:DeviceContour')
        shapes = self.batch(handles, True)
        self.assertEqual(len(reads), 2)
        self.assertFalse(self.get('contact-template', shapes[1]))
        self.assertEqual(self.get('segments', direct[1]), self.segments(shapes[1]))
        self.assert_contacts_equal(direct[1], shapes[1], 'b')

    def contact_cfg(self, tolerance):
        return self.call('EL:StrictDeviceConfig', self.call('EL:Put', Symbol('PARAMS'),
            self.call('EL:Put', Symbol('EPS_DEVICE'), tolerance, self.get('params', self.cfg)), self.cfg))

    def test_reused_point_and_path_keep_both_sides_of_xy_tolerance(self):
        handles = [self.ellipse(), self.ellipse(handle='b', pos=(1020., 1003., 0.))]
        old = self.batch(handles, None)[1]
        new = self.batch(handles, True)[1]
        peak = max((p for edge in self.get('segments', old) for p in edge), key=lambda p: p[1])
        for tolerance in (.01, 1.e-7):
            cfg = self.contact_cfg(tolerance)
            for gap, z, expected in ((tolerance*.99, 0., True), (tolerance*1.01, 0., False),
                                     (tolerance*.99, .001, False)):
                point = [peak[0], peak[1]+gap, z]
                wire = [Pair(Symbol('SEGMENTS'), [[[peak[0]-1., peak[1]+gap, z],
                                                  [peak[0]+1., peak[1]+gap, z]]])]
                self.assertEqual(truth(self.call('EL:ContourPointHit', point, old, cfg)), expected)
                self.assertEqual(truth(self.call('EL:ContourPointHit', point, new, cfg)), expected)
                self.assertEqual(truth(self.call('EL:ContourPathHit', wire, old, cfg)), expected)
                self.assertEqual(truth(self.call('EL:ContourPathHit', wire, new, cfg)), expected)

    def test_real_wire_width_contacts_reused_ellipse_without_materializing_all_edges(self):
        handles = [self.ellipse(), self.ellipse(handle='b', pos=(1020., 1003., 5.))]
        old = self.batch(handles, None)[1]
        new = self.batch(handles, True)[1]
        self.assertTrue(self.get('contact-template', new))
        cfg = self.contact_cfg(.01)
        peak = max((p for edge in self.get('segments', old) for p in edge), key=lambda p: p[1])
        self.h.builtins['EL:TRANSFORMSEGMENTS'] = lambda *a: self.fail('wide-wire query transformed a full edge collection')
        for gap, dz, expected in ((.005, 0., True), (.0101, 0., False), (.005, .001, False)):
            y, z = peak[1]+.1+gap, peak[2]+dz
            self.entities['wide'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'wide'), Pair(8, 'W'),
                Pair(70, 0), Pair(43, .2), Pair(38, z),
                Pair(10, [peak[0]-1., y]), Pair(10, [peak[0]+1., y])]
            wire = self.call('EL:WireRecord', 'wide', self.cfg)
            self.assertTrue(self.get('contact-strips', wire))
            self.assertFalse(truth(self.call('EL:ContourPathHit', wire, old, cfg)))
            self.assertFalse(truth(self.call('EL:ContourPathHit', wire, new, cfg)))
            self.assertEqual(truth(self.call('EL:WideDevicePathHit', wire, old, cfg)), expected)
            self.assertEqual(truth(self.call('EL:WideDevicePathHit', wire, new, cfg)), expected)

    def test_adjacent_sampled_devices_keep_contact_threshold_and_elevation(self):
        self.ellipse(handle='seed')
        seed = self.call('EL:DeviceContour', 'seed')
        xs = [p[0] for edge in self.get('segments', seed) for p in edge]
        span = max(xs)-min(xs)
        handles = ['seed', self.ellipse(handle='b', pos=(1020., 1000., 0.))]
        for handle, gap, z in (('near', .005, 0.), ('far', .0101, 0.), ('high', .005, .001)):
            handles.append(self.ellipse(handle=handle, pos=(1020.+span+gap, 1000., z)))
        old = dict(zip(handles, self.batch(handles, None)))
        new = dict(zip(handles, self.batch(handles, True)))
        self.assertTrue(self.get('contact-template', new['b']))
        self.h.frames[0]['*EL:DEVICECONTACTTOLERANCE*'] = .01
        self.h.builtins['EL:TRANSFORMSEGMENTS'] = lambda *a: self.fail('device query transformed a full edge collection')
        for shapes in (old, new):
            self.h.builtins['EL:DEVICECONTACTSHAPE'] = lambda block: shapes[self.get('id', block)]
            for handle, expected in (('near', True), ('far', False), ('high', False)):
                a, b = self.record('b'), self.record(handle)
                self.assertEqual(truth(self.call('EL:DevicesTouch', a, b)), expected)
                self.assertEqual(truth(self.call('EL:DevicesTouch', b, a)), expected)

    def test_cancel_or_prepare_exception_never_publishes_pose(self):
        for stage in ('EL:ClosedRings', 'EL:PrepareContourContact'):
            with self.subTest(stage=stage):
                self.setUp()
                self.ellipse(); self.ellipse(handle='b', pos=(1020., 1000., 0.))
                self.h.frames.append({'*EL:DEVICETEMPLATEENABLED*': True,
                    '*EL:DEVICETEMPLATECACHE*': None, '*EL:DEVICECONTACTCACHE*': None})
                try:
                    self.h.builtins[stage.upper()] = lambda *a: (_ for _ in ()).throw(RuntimeError('cancelled'))
                    with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                        self.shape('a')
                    self.h.builtins.pop(stage.upper())
                    reads = self.count('EL:DeviceContour')
                    second = self.shape('b')
                    self.assertEqual(len(reads), 1)
                    self.assertFalse(self.get('contact-template', second))
                    self.assertTrue(self.get('contact-ready', second))
                finally:
                    self.h.frames.pop()


if __name__ == '__main__':
    unittest.main()
