"""Region index semantics and work-count regressions. Date: 2026-10-08.

Synthetic fixtures and a frozen v15 oracle; not real AutoCAD timings.
"""
import math
import random
import unittest

from autolisp_host import Host, Symbol, truth
from test_cad_adapter import ROOT


LEGACY = '''
(defun test:Simple (ring / valid a b elevation)
  (setq valid T elevation (caddr (caar ring)))
  (foreach a ring
    (if (or (> (abs (- (caddr (car a)) elevation)) (EL:GapEpsilon))
            (> (abs (- (caddr (cadr a)) elevation)) (EL:GapEpsilon))) (setq valid nil))
    (foreach b ring
      (if (and (not (equal a b)) (EL:GapHitsSegment (car a) (cadr a) (car b) (cadr b)))
        (setq valid nil)))) valid)
(defun test:Closed (segments / pending ring start point matches seg loops finished)
  (setq pending segments)
  (while pending
    (setq seg (car pending) pending (cdr pending) ring (list seg)
          start (car seg) point (cadr seg) finished nil)
    (while (and (not finished) (not (equal start point 1.0e-7)))
      (setq matches (vl-remove-if-not '(lambda (s) (or (equal point (car s) 1.0e-7) (equal point (cadr s) 1.0e-7))) pending))
      (if (= (length matches) 1)
        (progn (setq seg (car matches) pending (vl-remove seg pending))
          (if (equal point (cadr seg) 1.0e-7) (setq seg (reverse seg)))
          (setq ring (append ring (list seg)) point (cadr seg)))
        (setq finished T)))
    (if (and (not finished) (> (length ring) 2) (test:Simple ring)) (setq loops (cons ring loops)))) loops)
'''


class RegionIndexTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'geometry'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        self.h.run(LEGACY)
        self.tests = 0
        params, body = self.h.functions[Symbol('EL:GAPHITSSEGMENT')]
        original = [Symbol('LAMBDA'), params, *body]

        def counted(*args):
            self.tests += 1
            return self.h.call(original, list(args))

        self.h.builtins['EL:GAPHITSSEGMENT'] = counted

    def call(self, name, value):
        self.h.steps = 0
        return self.h.call(Symbol(name.upper()), [value])

    @staticmethod
    def polygon(points):
        points = [list(p) if len(p) == 3 else [*p, 0.] for p in points]
        return [[a, b] for a, b in zip(points, points[1:] + points[:1])]

    def circle(self, n, x=0., y=0.):
        return self.polygon([(x+100.*math.cos(math.tau*i/n), y+100.*math.sin(math.tau*i/n)) for i in range(n)])

    def test_index_matches_legacy_for_concavity_branches_duplicates_and_fuzzy_endpoints(self):
        square = self.polygon([(0., 0.), (4., 0.), (4., 4.), (0., 4.)])
        concave = self.polygon([(0., 0.), (6., 0.), (6., 6.), (4., 6.), (4., 2.), (2., 2.), (2., 6.), (0., 6.)])
        crossed = self.polygon([(0., 0.), (4., 4.), (0., 4.), (4., 0.)])
        fuzzy = [[list(a), list(b)] for a, b in square]
        fuzzy[1][0][0] += .5e-7
        nonplanar = self.polygon([(0., 0., 0.), (4., 0., 0.), (4., 4., 1.), (0., 4., 0.)])
        near_z = self.polygon([(0., 0., 0.), (4., 4., .9e-7), (0., 4., 0.), (4., 0., -.9e-7)])
        fixtures = [[], square, concave, crossed, fuzzy, nonplanar, near_z,
                    square[:-1], square+[square[0]], square+[list(reversed(square[0]))],
                    square+[[[4., 0., 0.], [6., -1., 0.]]],
                    square+self.circle(16, 20., 20.), square+[[[2., 2., 0.], [2., 2., 0.]]]]
        rng = random.Random(16)
        for segments in fixtures:
            for _ in range(4):
                ordered = [s if rng.random() < .5 else list(reversed(s)) for s in segments]
                rng.shuffle(ordered)
                self.assertEqual(self.call('EL:ClosedRings', ordered), self.call('test:Closed', ordered))

    def test_random_crossings_match_all_pairs_oracle(self):
        rng = random.Random(1600)
        for _ in range(25):
            ring = self.polygon([(rng.uniform(-10., 10.), rng.uniform(-10., 10.)) for _ in range(10)])
            self.assertEqual(truth(self.call('EL:SimpleRing', ring)), truth(self.call('test:Simple', ring)))

    def test_circle_intersection_work_drops_from_all_pairs_to_local_neighbors(self):
        ring = self.circle(64)
        self.tests = 0
        self.assertTrue(truth(self.call('test:Simple', ring)))
        baseline = self.tests
        self.tests = 0
        self.assertTrue(truth(self.call('EL:SimpleRing', ring)))
        self.assertEqual(baseline, 64*63)
        self.assertLess(self.tests, baseline//10)

    def test_3107_segment_fixture_retains_six_rings_with_bounded_intersection_work(self):
        # Same segment count as the user's cancelled block, synthetic geometry.
        self.h.step_limit = 30000000  # Explicit larger fixture budget; defaults remain bounded.
        segments = sum((self.circle(512, i*500., 0.) for i in range(6)), [])
        segments += [[[i*5., 500., 0.], [i*5.+1., 501., 0.]] for i in range(35)]
        self.assertEqual(len(segments), 3107)
        self.tests = 0
        rings = self.call('EL:ClosedRings', segments)
        self.assertEqual(len(rings), 6)
        self.assertEqual(sorted(map(len, rings)), [512]*6)
        self.assertLess(self.tests, 3107*6)


if __name__ == '__main__':
    unittest.main()
