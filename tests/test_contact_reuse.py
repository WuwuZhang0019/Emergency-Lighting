"""Contact stall regression. Date: 2026-10-10; finite CAD adapters only."""
import unittest

from autolisp_host import Pair, Symbol, truth
import test_simple_flow as simple
import test_diagnostics as diagnostics


class ContactReuseTests(unittest.TestCase):
    setUp = simple.SimpleFlowTests.setUp
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    block = simple.SimpleFlowTests.block
    line = simple.SimpleFlowTests.line
    logging = diagnostics.DiagnosticTests.logging

    def count(self, name):
        params, body = self.h.functions[Symbol(name.upper())]
        original = [Symbol('LAMBDA'), params, *body]
        calls = []

        def counted(*args):
            calls.append(args)
            return self.h.call(original, list(args))

        self.h.builtins[name.upper()] = counted
        return calls

    def batch(self, handles, enabled):
        self.h.frames.append({'*EL:DEVICETEMPLATEENABLED*': enabled,
                              '*EL:DEVICETEMPLATECACHE*': None,
                              '*EL:DEVICECONTACTCACHE*': None})
        try:
            return [self.call('EL:DeviceContactShape',
                    [Pair(Symbol('ID'), h), Pair(Symbol('ENTITY'), h),
                     Pair(Symbol('NAME'), 'device')]) for h in handles]
        finally:
            self.h.frames.pop()

    def test_twelve_translated_instances_expand_and_find_rings_once(self):
        handles = [self.block('LAMP', 'D', str(i), [i*20., i*3., 0.]) for i in range(12)]
        contours = self.count('EL:BlockContour')
        rings = self.count('EL:ClosedRings')
        preparations = self.count('EL:PrepareContourContact')
        expected = self.batch(handles, None)
        self.assertEqual(len(contours), 12)
        self.assertEqual(len(rings), 12)
        contours.clear(); rings.clear(); preparations.clear()
        actual = self.batch(handles, True)
        self.assertEqual(len(contours), 1)
        self.assertEqual(len(rings), 1)
        self.assertEqual(len(preparations), 1)
        for old, new in zip(expected, actual):
            for field in ('segments', 'regions', 'holes', 'segment-bounds'):
                self.assertEqual(self.get(field, old), self.get(field, new))
            self.assertEqual(self.get('id', old), self.get('id', new))
            for point in ([0., 0., 0.], [20., 3., 0.], [21., 3., 0.], [25., 3., 0.]):
                self.assertEqual(truth(self.call('EL:ContourPointHit', point, old, self.cfg)),
                                 truth(self.call('EL:ContourPointHit', point, new, self.cfg)))
        self.assertIsNone(self.h.lookup('*EL:DEVICETEMPLATECACHE*'))

    def test_dense_shared_index_matches_uncached_contacts(self):
        import math
        handles = [self.block('LAMP', 'D', str(i), [i*20., 0., 0.]) for i in range(3)]
        def contour(entity, *args):
            x = float(entity)*20.
            points = [[x+math.cos(i*math.tau/128), math.sin(i*math.tau/128), 0.] for i in range(128)]
            return [Pair(Symbol('SEGMENTS'), [[points[i], points[(i+1)%128]] for i in range(128)])]
        self.h.builtins['EL:BLOCKCONTOUR'] = contour
        expected = self.batch(handles, None)
        prepared = self.count('EL:PrepareContourContact')
        actual = self.batch(handles, True)
        self.assertEqual(len(prepared), 1)
        self.assertTrue(self.get('contact-tree', actual[0]))
        for old, new in zip(expected, actual):
            for x in (0., 1., 2., 20., 21., 22., 40., 41.):
                point = [x, 0., 0.]
                self.assertEqual(truth(self.call('EL:ContourPointHit', point, old, self.cfg)),
                                 truth(self.call('EL:ContourPointHit', point, new, self.cfg)))
                wire = [Pair(Symbol('SEGMENTS'), [[[x, -2., 0.], [x, 2., 0.]]])]
                self.assertEqual(truth(self.call('EL:ContourPathHit', wire, old, self.cfg)),
                                 truth(self.call('EL:ContourPathHit', wire, new, self.cfg)))

    def test_empty_panel_network_skips_unrelated_device_contours(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.line('empty', [1., 0., 0.], [10., 0., 0.], 'W')
        self.block('LAMP', 'D', 'remote', [100., 50., 0.])
        self.block('LAMP', 'D', 'remote2', [102., 50., 0.])
        self.line('remote-wire', [90., 50., 0.], [99., 50., 0.], 'W')
        self.selected = ['panel', 'empty', 'remote', 'remote2', 'remote-wire']
        snapshot = self.call('EL:SimpleCollect', self.cfg)
        contours = self.count('EL:DeviceContactShape')
        result = self.call('EL:SimpleNetwork', snapshot, self.cfg, 'panel')
        self.assertFalse(self.get('devices', result))
        self.assertEqual(len(contours), 0)

    def test_rotation_scale_and_anonymous_definitions_are_not_interchanged(self):
        handles = [self.block('LAMP', 'D', h, [i*20., 0., 0.])
                   for i, h in enumerate(('a', 'b', 'mirror', 'rotated'))]
        self.entities['mirror'].append(Pair(41, -1.))
        self.entities['rotated'].append(Pair(50, 0.5))
        handles.append(self.block('*U2', 'D', 'dynamic', [100., 0., 0.]))
        contours = self.count('EL:BlockContour')
        expected = self.batch(handles, None)
        contours.clear()
        actual = self.batch(handles, True)
        self.assertEqual(len(contours), 4)
        for old, new in zip(expected, actual):
            self.assertEqual(self.get('segments', old), self.get('segments', new))

    def test_holes_and_elevation_translate_and_each_pass_reloads_geometry(self):
        handles = [self.block('LAMP', 'D', h, p) for h, p in
                   (('a', [0., 0., 0.]), ('b', [20., 30., 5.]))]
        self.entities['LAMP-edge-0'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'LAMP-edge-0'),
            Pair(8, 'EL_HOLE'), Pair(70, 1), Pair(10, [-1., -1.]),
            Pair(10, [1., -1.]), Pair(10, [1., 1.]), Pair(10, [-1., 1.])]
        self.next_entity['LAMP-edge-0'] = 'LAMP-end'
        expected = self.batch(handles, None)
        actual = self.batch(handles, True)
        self.assertTrue(self.get('holes', actual[0]))
        self.assertEqual(self.get('holes', expected[1]), self.get('holes', actual[1]))
        self.line('LAMP-edge-0', [-.5, -.5, 0.], [.5, -.5, 0.], 'EL_HOLE')
        changed = self.batch(handles, True)
        self.assertNotEqual(self.get('segments', actual[1]), self.get('segments', changed[1]))

    def test_large_bounds_do_not_allocate_lists_per_endpoint_and_report_progress(self):
        self.logging()
        self.h.run('(EL:LogStart)')
        self.h.frames[0]['*EL:CONTACTCONTEXT*'] = [Pair(Symbol('ID'), '2223'), Pair(Symbol('SEGMENTS'), 8200)]
        self.h.builtins['MAPCAR'] = lambda *a: self.fail('per-endpoint list allocation')
        segments = [[[float(i), -float(i), 2.], [float(i+1), 1., -3.]] for i in range(8200)]
        self.assertEqual(self.call('EL:SegmentBounds', segments), [[0., -8199., -3.], [8200., 1., 2.]])
        log = self.log.read_text(encoding='utf-8')
        for value in ('2223', '4096', '8192', 'CONTACT_PROGRESS'):
            self.assertIn(value, log)

    def test_cancel_during_bounds_retains_device_and_segment_count(self):
        self.logging()
        self.h.run('(EL:LogStart)')
        self.block('LAMP', 'D', 'lamp-2223', [0., 0., 0.])
        self.h.builtins['EL:SEGMENTBOUNDS'] = lambda *a: (_ for _ in ()).throw(RuntimeError('cancelled'))
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.batch(['lamp-2223'], True)
        self.call('EL:LogFailure', 'cancelled')
        log = self.log.read_text(encoding='utf-8')
        self.assertIn('CONTACT_BOUNDS', log)
        self.assertIn('lamp-2223', log)
        self.assertIn('SEGMENTS', log)

    def test_occupied_endpoint_does_not_expand_more_device_geometry(self):
        self.h.builtins['EL:SPATIALBOXQUERY'] = lambda *a: self.fail('already occupied')
        ep = [Pair(Symbol('POINT'), [0., 0., 0.]), Pair(Symbol('OCCUPIED'), True)]
        result = self.call('EL:SimpleEndState', ep, None, self.cfg)
        self.assertTrue(truth(self.get('occupied', result)))

    def test_device_contact_stops_after_first_exact_hit(self):
        shape = [Pair(Symbol('SEGMENTS'), [[[0., 0., 0.], [1., 0., 0.]]])]
        self.h.builtins['EL:DEVICECONTACTSHAPE'] = lambda *a: shape
        self.h.builtins['EL:CONTACTSEGMENTS'] = lambda *a: self.get('segments', shape) * 5000
        calls = self.count('EL:Touches')
        self.assertTrue(truth(self.call('EL:DevicesTouch', None, None)))
        self.assertEqual(len(calls), 1)

    def test_native_extents_skip_contact_bounds_scan_but_do_not_prove_contact(self):
        self.block('LAMP', 'D', 'a', [0., 0., 0.])
        calls = self.count('EL:LogCall')
        shape = self.call('EL:DeviceContactShape', [Pair(Symbol('ID'), 'a'),
            Pair(Symbol('ENTITY'), 'a'), Pair(Symbol('BOUNDS'), [[-10., -10., 0.], [10., 10., 0.]])])
        self.assertNotIn('CONTACT_BOUNDS', [args[0] for args in calls])
        self.assertFalse(truth(self.call('EL:ContourPointHit', [5., 5., 0.], shape, self.cfg)))
        self.assertTrue(truth(self.call('EL:ContourPointHit', [1., 0., 0.], shape, self.cfg)))
