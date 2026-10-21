"""Conservative current-prefix numbering bounds. Date: 2026-10-21.

Status: pure-source exact boundary equivalence; native CAD time remains pending.
"""
import copy
from pathlib import Path
import random
import unittest

from autolisp_host import Host, Pair, Symbol
from check_store_read_work import exact

ROOT = Path(__file__).resolve().parents[1]

# Frozen from 9108cf8: joint search with the original exact 32-step grid.
LEGACY = """
(defun oracle:PrefixFirstDevice (wire entry target devices cfg / block shape candidates hits row low high middle slice measures
    *EL:NumberProbeActive* *EL:NumberProbePoints* *EL:NumberProbeSegments*)
  (if (and devices (> (abs (- target entry)) 1.0e-12))
    (progn
    (setq *EL:NumberProbeActive* T cfg (EL:StrictDeviceConfig cfg) measures (EL:NumberPathMeasures wire)
      slice (EL:NumberPathSliceMeasured wire entry target measures))
    (foreach block devices
      (setq shape (EL:DeviceContactShape block))
      (if (EL:NumberShapeHitStrict slice shape cfg)
        (setq candidates (cons (cons (EL:Get 'id block) shape) candidates))))
    (if candidates
      (progn
        (setq candidates (reverse candidates) low 0.0 high 1.0)
        (repeat 32
          (setq middle (/ (+ low high) 2.0) hits nil
            slice (EL:NumberPathSliceMeasured wire entry (+ entry (* middle (- target entry))) measures))
          (foreach row candidates
            (if (EL:NumberShapeHitStrict slice (cdr row) cfg) (setq hits (cons row hits))))
          (if hits (setq high middle candidates (reverse hits)) (setq low middle)))
        (list (+ entry (* high (- target entry))) (caar candidates)))))))
"""


def pair(key, value):
    return Pair(Symbol(key.upper()), value)


class NumberPrefixBoundsTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'config', 'geometry', 'topology', 'simple', 'circuit-number'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        self.h.run(LEGACY)
        self.cfg = self.h.run('(EL:DefaultConfig "test")')
        self.shapes = {}
        self.shape_reads = []
        self.slices = []
        self.exact_checks = []
        self.counts = []
        self.h.builtins['EL:DEVICECONTACTSHAPE'] = self.shape
        self.h.builtins['EL:PERFCOUNT'] = lambda key, count: self.counts.append((key, count))
        for name, target in [('EL:NUMBERPATHSLICEMEASURED', self.slices),
                             ('EL:NUMBERSHAPEHITSTRICT', self.exact_checks)]:
            params, body = self.h.functions[Symbol(name)]
            function = [Symbol('LAMBDA'), params, *body]

            def observe(*values, function=function, target=target):
                target.append(values)
                return self.h.call(function, list(values))

            self.h.builtins[name] = observe

    def call(self, name, *values):
        self.h.steps = 0
        return self.h.call(Symbol(name.upper()), list(values))

    def get(self, key, row):
        return self.call('EL:Get', Symbol(key.upper()), row)

    def shape(self, block):
        name = self.get('id', block)
        self.shape_reads.append(name)
        return self.shapes[name]

    def device(self, name, bounds, hole=None, native_bounds='same'):
        ring = self.call('EL:BoundsSegments', bounds)
        holes = [self.call('EL:BoundsSegments', hole)] if hole else None
        self.shapes[name] = [pair('segments', ring + (holes[0] if holes else [])),
                             pair('regions', [ring]), pair('holes', holes)]
        return [pair('id', name), pair('bounds', bounds if native_bounds == 'same' else native_bounds)]

    def circle(self, name, x, y, radius, offset=0.):
        self.shapes[name] = [pair('curves', [[[offset+x, y, 0.], radius, 0., 6.283185307179586, True]])]
        return [pair('id', name), pair('bounds', [[offset+x-radius, y-radius, 0.],
                                                [offset+x+radius, y+radius, 0.]])]

    @staticmethod
    def wire(points=None, width=None, stale=False):
        points = points or [[0., 0., 0.], [10., 0., 0.], [20., 0., 0.]]
        rows = [pair('segments', [[a, b] for a, b in zip(points, points[1:])])]
        if width:
            rows.append(pair('width-profiles', [[points[0], points[-1], *width]]))
        if stale:
            rows.append(pair('contact-bounds', [[10000., 10000., 0.], [10001., 10001., 0.]]))
        return rows

    def compare(self, wire, entry, target, devices):
        inputs = copy.deepcopy((wire, devices, self.cfg))
        self.shape_reads.clear()
        self.slices.clear()
        self.exact_checks.clear()
        expected = self.call('oracle:PrefixFirstDevice', wire, entry, target, devices, self.cfg)
        reads, slices, checks = self.shape_reads[:], self.slices[:], len(self.exact_checks)
        self.shape_reads.clear()
        self.slices.clear()
        self.exact_checks.clear()
        actual = self.call('EL:NumberFirstDevice', wire, entry, target, devices, self.cfg)
        self.assertEqual(exact(actual), exact(expected))
        self.assertEqual(self.shape_reads, reads)
        # Compare each exact start/finish and generated prefix, not only count.
        self.assertEqual(exact(self.slices), exact(slices))
        self.assertEqual(exact((wire, devices, self.cfg)), exact(inputs))
        self.assertIsNone(self.h.lookup('*EL:NUMBERPROBEACTIVE*'))
        return actual, checks, len(self.exact_checks)

    def test_forward_reverse_holes_and_equal_distance_keep_original_winner(self):
        first = self.device('first', [[4., -2., 0.], [6., 2., 0.]])
        tie = self.device('tie', [[4., -2., 0.], [6., 2., 0.]])
        far = self.device('far', [[12., -2., 0.], [14., 2., 0.]])
        hole = self.device('hole', [[2., -2., 0.], [18., 2., 0.]],
                           [[3., -1., 0.], [17., 1., 0.]])
        for entry, target, devices in [(0., 20., [far, first, tie]),
                (0., 20., [tie, first, far]), (20., 0., [first, tie, far]),
                (10., 20., [hole, far]), (10., 0., [hole, first]),
                (10., 10., [first]), (0., 20., [])]:
            with self.subTest(entry=entry, target=target, ids=[self.get('id', b) for b in devices]):
                self.compare(self.wire(), entry, target, devices)

    def test_wide_strip_containment_taper_and_end_caps_preserve_boundaries(self):
        inside = self.device('inside', [[7., 1., 0.], [8., 2., 0.]])
        edge = self.device('edge', [[20., -1., 0.], [21., 1., 0.]])
        outside = self.device('outside', [[5., 5., 0.], [6., 6., 0.]])
        for width in ([6., 6.], [2., 8.], [8., 2.]):
            for entry, target in ((0., 20.), (20., 0.), (10., 20.), (10., 0.)):
                with self.subTest(width=width, entry=entry, target=target):
                    self.compare(self.wire(width=width), entry, target, [outside, edge, inside])

    def test_current_prefix_bounds_ignore_inherited_full_wire_envelope(self):
        wire = self.wire(width=[6., 6.], stale=True)
        measures = self.call('EL:NumberPathMeasures', wire)
        prefix = self.call('EL:NumberPathSliceMeasured', wire, 0., 5., measures)
        before = copy.deepcopy(prefix)
        self.assertEqual(self.call('EL:NumberPrefixBounds', prefix), [[0., -3., 0.], [5., 3., 0.]])
        self.assertEqual(prefix, before)
        first = self.device('first', [[4., 1., 0.], [6., 2., 0.]])
        self.compare(wire, 0., 20., [first])
        self.compare(wire, 20., 0., [first])

    def test_missing_invalid_and_unprovable_native_bounds_use_exact_fallback(self):
        invalid = [None, [], 'bad', [[0., 0.], [1., 1.]],
                   [[8., 2., 0.], [4., -2., 0.]],
                   [[float('nan'), -2., 0.], [6., 2., 0.]],
                   [[4., -2., 0.], [float('inf'), 2., 0.]], Pair('broken', 7)]
        self.h.frames[0]['*EL:PERFACTIVE*'] = True
        for index, bounds in enumerate(invalid):
            device = self.device(f'invalid-{index}', [[4., -2., 0.], [6., 2., 0.]], native_bounds=bounds)
            self.counts.clear()
            with self.subTest(bounds=bounds):
                result, old, new = self.compare(self.wire(), 0., 20., [device])
                self.assertIsNotNone(result)
                self.assertEqual(old, new)
                counts = dict(self.counts)
                self.assertEqual(counts['number-prefix-bounds-fallbacks'], 33)
                self.assertEqual(counts['number-prefix-bounds-rejected'], 0)

    def test_curves_large_coordinates_strict_epsilon_and_both_directions(self):
        for offset in (0., 154776.123456789, 1.e9):
            ring = self.device('ring', [[offset+12., -2., 0.], [offset+14., 2., 0.]])
            circle = self.circle('circle', 8., 0., 1., offset)
            wire = self.wire([[offset+i, 0., 0.] for i in range(0, 21, 2)])
            for entry, target in ((0., 20.), (20., 0.), (10., 20.), (10., 0.)):
                self.compare(wire, entry, target, [ring, circle])
        for separation in (.0099999, .01, .0100001, .0101):
            adjacent = self.device('edge', [[4., separation, 0.], [6., 1., 0.]])
            self.compare(self.wire(), 0., 20., [adjacent])

    def test_seeded_geometry_rotations_multiple_segments_and_order_match(self):
        rng = random.Random(170)
        for index in range(12):
            x, y = rng.uniform(-100., 100.), rng.uniform(-100., 100.)
            dx, dy = [(1., 0.), (0., 1.), (.6, .8), (-.8, .6)][index % 4]
            centers = [[x+(3.+n*4.)*dx, y+(3.+n*4.)*dy, 0.] for n in range(4)]
            devices = [self.device(f'device-{n}', [[p[0]-.5, p[1]-.5, 0.], [p[0]+.5, p[1]+.5, 0.]])
                       for n, p in enumerate(centers)]
            rng.shuffle(devices)
            points = [[x+s*dx, y+s*dy, 0.] for s in (0., 7., 20.)]
            for entry, target in ((0., 20.), (20., 0.)):
                self.compare(self.wire(points, width=[2., 2.] if index%2 else None), entry, target, devices)

    def test_batch_counters_explain_rejected_exact_tests_and_keep_32_probes(self):
        near = self.device('near', [[80., -1., 0.], [82., 1., 0.]])
        far = [self.device(f'far-{n}', [[float(n), 100., 0.], [float(n)+1., 101., 0.]])
               for n in range(16)]
        self.h.frames[0]['*EL:PERFACTIVE*'] = True
        self.h.builtins['EL:TICK'] = lambda: self.fail('Prefix search adds no Tick calls')
        result, old, new = self.compare(self.wire([[0., 0., 0.], [100., 0., 0.]]), 0., 100., far+[near])
        self.assertIsNotNone(result)
        self.assertEqual(len(self.slices), 33)
        self.assertLess(new, old-16)
        counts = dict(self.counts)
        self.assertEqual(len(self.counts), len(counts))  # One final batch per key.
        self.assertEqual(counts['number-prefix-searches'], 1)
        self.assertEqual(counts['number-prefix-bounds-builds'], 33)
        self.assertGreaterEqual(counts['number-prefix-bounds-rejected'], 17)
        self.assertEqual(counts['number-prefix-exact-tests'], new)
        self.assertEqual(counts['number-prefix-bounds-tests'] + counts['number-prefix-bounds-fallbacks'],
                         counts['number-prefix-exact-tests'] + counts['number-prefix-bounds-rejected'])

    def test_profiling_disabled_has_no_tick_or_metric_calls(self):
        device = self.device('one', [[8., -1., 0.], [9., 1., 0.]])
        self.h.builtins['EL:TICK'] = lambda: self.fail('No extra clocks with profiling disabled')
        self.h.builtins['EL:PERFCOUNT'] = lambda *args: self.fail('No per-probe metrics with profiling disabled')
        self.compare(self.wire(), 0., 20., [device])


if __name__ == '__main__':
    unittest.main()
