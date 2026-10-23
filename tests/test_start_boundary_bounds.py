"""Conservative start-boundary broad phase. Date: 2026-10-21.

Status: frozen legacy equivalence and exact-call counts; not native CAD timing.
"""
import math
import random
import unittest

from autolisp_host import Pair, Symbol
import test_start_snapshot_performance as baseline


class StartBoundaryBoundsTests(unittest.TestCase):
    # Reuse the independent pre-optimization oracle, not the production filter.
    setUp = baseline.StartSnapshotPerformanceTests.setUp
    get = baseline.StartSnapshotPerformanceTests.get
    row = staticmethod(baseline.StartSnapshotPerformanceTests.row)

    def call(self, name, *args):
        self.h.steps = 0
        return self.h.call(Symbol(name.upper()), list(args))

    def wire(self, name, segments, *, prepare=True, strips=None):
        endpoints = [self.row(key=[name, Symbol('START')], point=segments[0][0]),
                     self.row(key=[name, Symbol('END')], point=segments[-1][1])]
        wire = self.row(id=name, segments=segments, ends=endpoints,
                        contact_strips=strips, extra=[name, 'preserve'])
        return self.call('EL:PrepareWireBounds', wire) if prepare else wire

    def fixture(self, others, points=None, tolerance=.01):
        points = points or [[0., 0., 0.]]
        roots, starts = [], []
        for i, point in enumerate(points):
            name = f'root-{i}'
            roots.append(self.wire(name, [[point, [point[0]+10., point[1], point[2]]]]))
            starts.append(self.row(wire=name, end=Symbol('START'), point=point))
        # Deliberately interleave roots so source and excluded orders are tested.
        wires = others[:1] + roots + others[1:]
        snapshot = self.row(wires=wires, ends=['old'],
                            blocks=[self.row(id='device', marker='keep')],
                            opaque=[self.row(value=42), 'unrelated'])
        cfg = self.row(circuit_starts=starts, params=self.row(eps_touch=tolerance))
        return snapshot, cfg

    def measured(self, function, snapshot, cfg):
        params, body = self.h.functions[Symbol('EL:TOUCHES')]
        original = [Symbol('LAMBDA'), params, *body]
        calls = []

        def counted(point, segments, tolerance, epsilon):
            calls.append((point, segments, tolerance, epsilon))
            return self.h.call(original, [point, segments, tolerance, epsilon])

        self.h.builtins['EL:TOUCHES'] = counted
        # Each oracle/production sample represents a separate command.
        self.h.frames[0]['*EL:PERFACTIVE*'] = None
        self.call('EL:PerfStart', 'ELSTAT')
        try:
            result = self.call(function, snapshot, cfg, 'panel')
            metrics = self.h.lookup('*EL:PERFMETRICS*')
            return result, calls, metrics
        finally:
            del self.h.builtins['EL:TOUCHES']

    def assert_equivalent(self, snapshot, cfg):
        expected, old_calls, _ = self.measured('TEST:LegacyStartSnapshot', snapshot, cfg)
        actual, new_calls, metrics = self.measured('EL:StartSnapshot', snapshot, cfg)
        self.assertEqual(actual, expected)
        # Exact calls preserve the original wire/start order and tolerances.
        remaining = iter(old_calls)
        for current in new_calls:
            self.assertTrue(any(item == current for item in remaining))
        self.assertEqual(self.call('EL:Get', 'start-boundary-exact-checks', metrics), len(new_calls))
        return actual, old_calls, new_calls, metrics

    def test_source_order_short_circuit_and_payload_match_legacy(self):
        wires = [self.wire('far', [[[100., 100., 0.], [150., 100., 0.]]]),
                 self.wire('last-hit', [[[60., -1., 0.], [60., 1., 0.]]]),
                 self.wire('first-hit', [[[-1., 0., 0.], [1., 0., 0.]]]),
                 self.wire('missing-envelope', [[[20., -1., 0.], [20., 1., 0.]]], prepare=False),
                 self.wire('tail', [[[2., 5., 0.], [3., 5., 0.]]])]
        snapshot, cfg = self.fixture(wires, [[float(x), 0., 0.] for x in (0, 20, 40, 60)])
        actual, old, new, metrics = self.assert_equivalent(snapshot, cfg)
        self.assertEqual([self.get('id', row) for row in self.get('start-boundary-source', actual)],
                         ['last-hit', 'first-hit', 'missing-envelope'])
        self.assertEqual([self.get('id', row) for row in self.get('wires', actual)],
                         ['far', 'root-0', 'root-1', 'root-2', 'root-3', 'tail'])
        self.assertEqual(len(old), 15)
        self.assertEqual(len(new), 4)
        self.assertEqual(self.call('EL:Get', 'start-boundary-bounds-fallback-wires', metrics), 1)
        self.assertEqual(self.get('ends', snapshot), ['old'])

    def test_zero_and_boundary_tolerances_keep_exact_contact_decision(self):
        for tolerance in (0., .01, 3.):
            with self.subTest(tolerance=tolerance):
                offsets = [0., tolerance, -tolerance,
                           math.nextafter(tolerance, math.inf),
                           math.nextafter(tolerance, -math.inf), tolerance+1.e-6]
                wires = [self.wire(f'w{i}', [[[-10., y, 0.], [10., y, 0.]]])
                         for i, y in enumerate(offsets)]
                self.assert_equivalent(*self.fixture(wires, tolerance=tolerance))

    def test_elevation_and_sloped_segments_retain_original_first_endpoint_rule(self):
        epsilon = self.call('EL:GapEpsilon')
        wires = [self.wire(f'z-{i}', [[[-1., 0., z], [1., 0., z]]])
                 for i, z in enumerate((0., epsilon, -epsilon, .9*epsilon, 1.1*epsilon))]
        # The old exact predicate, including its first-endpoint Z rule, decides.
        wires += [self.wire('sloped-a', [[[0., 0., 0.], [1., 0., 10.]]]),
                  self.wire('sloped-b', [[[-1., 0., 10.], [0., 0., 0.]]])]
        self.assert_equivalent(*self.fixture(wires))

    def test_curved_and_wide_source_envelopes_do_not_change_exact_geometry(self):
        points = self.call('EL:ArcPoints', [0., 5., 0.], 5., -math.pi/2., math.pi, .01)
        curve = self.call('EL:Segments', points)
        wide_segments = [[[0., 5., 0.], [10., 5., 0.]]]
        # Its strip reaches the root but its centreline does not: coarse pass
        # must still call the unchanged exact predicate rather than remove it.
        strip = self.call('EL:WireStrip', wide_segments[0][0], wide_segments[0][1], 20., 20.)
        wires = [self.wire('curve', curve),
                 self.wire('wide', wide_segments, strips=[strip]),
                 self.wire('empty-envelope', [[[0., 0., 0.], [0., 0., 0.]]])]
        actual, _, new, _ = self.assert_equivalent(*self.fixture(wires))
        self.assertIn('wide', [self.get('id', wire) for wire in self.get('wires', actual)])
        self.assertEqual(len(new), 3)

    def test_missing_invalid_and_unproven_envelopes_fall_back_without_new_errors(self):
        invalid = [None, 'not-bounds', [], [[0., 0., 0.]],
                   [[0., 0.], [10., 10., 0.]],
                   [[10., 0., 0.], [0., 0., 0.]],
                   [[0., 1., 0.], [10., 0., 0.]],
                   [[0., 0., 1.], [10., 0., 0.]],
                   [[0., 0., 0.], [10., 'bad', 0.]],
                   [[0., 0., 0.], [10., math.inf, 0.]],
                   [[0., 0., 0.], [10., math.nan, 0.]],
                   Pair([0., 0., 0.], 'improper'),
                   [[0., 0., 0.], Pair(10., 7.)]]
        wires = [self.wire('no-key', [[[-1., 0., 0.], [1., 0., 0.]]], prepare=False)]
        for i, bounds in enumerate(invalid):
            wire = self.wire(f'invalid-{i}', [[[-1., 0., 0.], [1., 0., 0.]]], prepare=False)
            wires.append(self.call('EL:Put', Symbol('CONTACT-BOUNDS'), bounds, wire))
        _, old, new, metrics = self.assert_equivalent(*self.fixture(wires))
        self.assertEqual(len(old), len(new))
        self.assertEqual(self.call('EL:Get', 'start-boundary-bounds-rejected', metrics), 0)
        self.assertEqual(self.call('EL:Get', 'start-boundary-bounds-fallback-wires', metrics), len(wires))

    def test_large_coordinate_roundoff_expands_broad_phase_only(self):
        for coordinate in (1.e-9, 0., 1.e9, -1.e9, 1.e12, 1.e17):
            with self.subTest(coordinate=coordinate):
                root = [coordinate, coordinate, coordinate]
                wires = [self.wire('at-end', [[root, [coordinate+10., coordinate, coordinate]]]),
                         self.wire('far', [[[coordinate+1.e6, coordinate+1.e6, coordinate],
                                             [coordinate+1.e6+10., coordinate+1.e6, coordinate]]])]
                for tolerance in (0., .01):
                    self.assert_equivalent(*self.fixture(wires, [root], tolerance))

    def test_random_multisegment_wire_results_match_frozen_oracle(self):
        rng = random.Random(20261021)
        points = [[float(x), 0., 0.] for x in (0, 20, 40, 60)]
        wires = []
        for i in range(60):
            root = points[i % len(points)]
            x, y = root[0]+rng.uniform(-.1, .1), rng.uniform(-.1, .1)
            segments = [[[x, y, 0.], [x+rng.uniform(-20., 20.), y+rng.uniform(-20., 20.), 0.]],
                        [[x+30., y+30., 0.], [x+40., y+40., 0.]]]
            wires.append(self.wire(f'wire-{i}', segments, prepare=i % 9 != 0))
        self.assert_equivalent(*self.fixture(wires, points, .03))

    def test_distant_batch_avoids_exact_work_and_reports_batch_counts(self):
        count = 300
        points = [[float(x), 0., 0.] for x in (0, 20, 40, 60)]
        wires = [self.wire(f'far-{i}', [[[1000.+20.*i, 100., 0.], [1010.+20.*i, 100., 0.]]])
                 for i in range(count)]
        _, old, new, metrics = self.assert_equivalent(*self.fixture(wires, points))
        self.assertEqual(len(old), 4*count)
        self.assertEqual(new, [])
        for key, expected in (('pair-checks', 4*count), ('bounds-rejected', 4*count),
                              ('exact-checks', 0), ('bounds-fallback-wires', 0)):
            self.assertEqual(self.call('EL:Get', f'start-boundary-{key}', metrics), expected)
        stage = self.call('EL:Get', 'START_BOUNDARY_FILTER', self.h.lookup('*EL:PERFSTAGES*'))
        self.assertEqual(self.get('calls', stage), 1)
        self.assertEqual(self.get('interrupted', stage), 0)
        self.assertEqual(self.get('parents', stage), ['START_SNAPSHOT'])
        self.assertIsNone(self.h.lookup('*EL:PERFPENDING*'))


if __name__ == '__main__':
    unittest.main()
