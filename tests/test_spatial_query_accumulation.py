"""Ordered box/ray query accumulation. Date: 2026-10-21.

Status: focused source equivalence and logical allocation counts, not CAD timing.
"""
from pathlib import Path
import random
import unittest

from autolisp_host import Host, Pair, Symbol, seq

ROOT = Path(__file__).resolve().parents[1]

# Frozen before optimization. Full record lists and predicate visit sequences are
# compared, so coincident keys, duplicated rows and traversal order cannot hide.
LEGACY = """
(defun test:LegacySpatialBoxQuery (tree bounds tol / item result)
  (if (and tree (EL:BoundsOverlap (list (nth 3 tree) (nth 4 tree)) bounds tol))
    (progn
      (setq item (car tree))
      (if (EL:BoundsOverlap (EL:Get 'bounds item) bounds tol) (setq result (list item)))
      (append result (test:LegacySpatialBoxQuery (cadr tree) bounds tol)
                     (test:LegacySpatialBoxQuery (caddr tree) bounds tol)))))
(defun test:LegacySpatialRayQuery (tree p direction limit / item bounds result)
  (if (and tree (EL:RayBoxHits p direction limit (nth 3 tree) (nth 4 tree)))
    (progn
      (setq item (car tree) bounds (EL:Get 'bounds item))
      (if (EL:RayBoxHits p direction limit
            (if bounds (car bounds) (EL:Get 'point item))
            (if bounds (cadr bounds) (EL:Get 'point item))) (setq result (list item)))
      (append result (test:LegacySpatialRayQuery (cadr tree) p direction limit)
                     (test:LegacySpatialRayQuery (caddr tree) p direction limit)))))
"""


class SpatialQueryAccumulationTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'geometry'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        self.h.run(LEGACY)

    def call(self, name, *args):
        self.h.steps = 0
        return self.h.call(Symbol(name.upper()), list(args))

    @staticmethod
    def row(key, point, bounds=None, marker=None):
        return [Pair(Symbol('KEY'), key), Pair(Symbol('POINT'), list(point)),
                Pair(Symbol('BOUNDS'), bounds), Pair(Symbol('MARKER'), marker)]

    @staticmethod
    def field(key, row):
        return next((pair.cdr for pair in row if pair.car == Symbol(key.upper())), None)

    def tree(self, rows):
        # The fixed public tree layout without SpatialTree's sorting/deduping:
        # repeated keys and literally duplicated rows must both survive queries.
        if not rows:
            return None
        mid = len(rows)//2
        item = rows[mid]
        left, right = self.tree(rows[:mid]), self.tree(rows[mid+1:])
        bounds = self.field('bounds', item)
        lo = list(bounds[0] if bounds else self.field('point', item))
        hi = list(bounds[1] if bounds else lo)
        for child in (left, right):
            if child:
                lo = list(map(min, lo, child[3]))
                hi = list(map(max, hi, child[4]))
        return [item, left, right, lo, hi]

    def equivalent(self, kind, tree, *args, trace=False):
        predicate = 'EL:BOUNDSOVERLAP' if kind == 'Box' else 'EL:RAYBOXHITS'
        calls = []
        if trace:
            params, body = self.h.functions[Symbol(predicate)]
            original = [Symbol('LAMBDA'), params, *body]

            def counted(*values):
                calls.append(values)
                return self.h.call(original, list(values))

            self.h.builtins[predicate] = counted
        try:
            expected = self.call(f'test:LegacySpatial{kind}Query', tree, *args)
            expected_calls = calls[:]
            calls.clear()
            actual = self.call(f'EL:Spatial{kind}Query', tree, *args)
            self.assertEqual(actual, expected)
            if trace:
                self.assertEqual(calls, expected_calls)
            return actual
        finally:
            if trace:
                del self.h.builtins[predicate]

    def test_empty_tree_and_no_hits_return_native_nil(self):
        row = self.row('one', [0., 0., 0.], [[0., 0., 0.], [1., 1., 1.]])
        tree = self.tree([row])
        for source in (None, tree):
            self.assertIsNone(self.equivalent('Box', source,
                [[20., 20., 20.], [21., 21., 21.]], 0., trace=True))
            self.assertIsNone(self.equivalent('Ray', source,
                [20., 20., 20.], [1., 0., 0.], 1., trace=True))
        self.assertIsNone(self.equivalent('Box', tree, None, 0., trace=True))

    def test_node_left_right_order_keeps_duplicate_keys_and_duplicate_rows(self):
        bounds = [[0., 0., 0.], [1., 1., 1.]]
        rows = [self.row('same', [.5, .5, .5], bounds, f'row-{i}') for i in range(7)]
        rows[6] = rows[0]
        tree = self.tree(rows)
        expected = [rows[i] for i in (3, 1, 0, 2, 5, 4, 6)]
        self.assertEqual(self.equivalent('Box', tree, bounds, 0., trace=True), expected)
        self.assertEqual(self.equivalent('Ray', tree,
            [-1., .5, .5], [1., 0., 0.], 3., trace=True), expected)
        self.assertEqual(rows[0], rows[6])

    def test_box_boundary_tolerance_and_subtree_pruning_match_exact_predicates(self):
        rows = [self.row(str(i), [float(i*10), 0., 0.],
                        [[float(i*10), 0., 0.], [float(i*10+1), 1., 1.]])
                for i in range(-4, 5)]
        tree = self.tree(rows)
        queries = [None, [[-100., -100., -100.], [100., 100., 100.]],
                   [[1., 1., 1.], [1., 1., 1.]],
                   [[1.+1.e-7, 0., 0.], [2., 1., 1.]],
                   [[1.+2.e-7, 0., 0.], [2., 1., 1.]],
                   [[0., 0., 1.+1.e-7], [1., 1., 2.]],
                   [[-40., -2., -2.], [-39., 2., 2.]]]
        for query in queries:
            for tolerance in (-.01, 0., 1.e-7, .01):
                with self.subTest(query=query, tolerance=tolerance):
                    self.equivalent('Box', tree, query, tolerance, trace=True)

    def test_ray_boundaries_axis_parallel_zero_and_point_fallback_match(self):
        rows = [self.row('box', [0., 0., 0.], [[0., 0., 0.], [1., 1., 1.]]),
                self.row('point', [2., 0., 0.]),
                self.row('z', [-1., -1., 3.], [[-2., -2., 3.], [-1., -1., 4.]])]
        tree = self.tree(rows)
        cases = [([-1., 0., 0.], [1., 0., 0.], 1.),
                 ([-1., 0., 0.], [1., 0., 0.], 1.-1.e-7),
                 ([-1., 0., 0.], [1., 0., 0.], 1.-2.e-7),
                 ([3., 0., 0.], [-1., 0., 0.], 3.),
                 ([0., -1., 0.], [0., 1., 0.], 2.),
                 ([0., 0., -1.], [0., 0., 1.], 2.),
                 ([0., 0., 0.], [0., 0., 0.], 0.),
                 ([4., 0., 0.], [0., 0., 0.], 100.),
                 ([-1., 0., 0.], [1., 1.e-16, 0.], 3.),
                 ([-1., 0., 0.], [1., 1.e-15, 0.], 3.),
                 ([-1., 0., 0.], [1., 0., 0.], -1.)]
        for point, direction, limit in cases:
            with self.subTest(point=point, direction=direction, limit=limit):
                self.equivalent('Ray', tree, point, direction, limit, trace=True)

    def test_seeded_random_box_and_ray_queries_compare_complete_ordered_records(self):
        rng = random.Random(701)
        for batch in range(4):
            rows = []
            for index in range(31):
                point = [rng.uniform(-30., 30.), rng.uniform(-30., 30.),
                         rng.choice([-2., 0., 2.])]
                radius = rng.choice([0., .01, 1., 4.])
                bounds = [[value-radius for value in point],
                          [value+radius for value in point]]
                rows.append(self.row(str(index % 5), point, bounds, [batch, index]))
            rows.extend([rows[0], rows[4], self.row('point-only', [0., 0., 0.])])
            rng.shuffle(rows)
            tree = self.tree(rows)
            for query_index in range(24):
                center = self.field('point', rng.choice(rows))
                radius = rng.choice([0., .001, 2., 20., 100.])
                bounds = [[value-radius for value in center], [value+radius for value in center]]
                with self.subTest(batch=batch, query=query_index):
                    self.equivalent('Box', tree, bounds,
                                    rng.choice([0., 1.e-7, .01]), trace=True)
                    direction = [rng.choice([-1., 0., 1.]) for _ in range(3)]
                    self.equivalent('Ray', tree, center, direction,
                                    rng.choice([0., .5, 5., 100.]), trace=True)

    def test_existing_spatial_tree_layout_produces_same_ordered_queries(self):
        rows = [self.row(str(index), [float(index % 4), float(index//4), 0.],
                        [[float(index % 4), float(index//4), 0.],
                         [float(index % 4)+.1, float(index//4)+.1, 0.]])
                for index in range(31)]
        tree = self.call('EL:SpatialTree', rows, 0)
        for low, high in [([-1., -1., -1.], [50., 50., 1.]),
                          ([1., 1., 0.], [3., 6., 0.])]:
            self.equivalent('Box', tree, [low, high], 0., trace=True)
            self.equivalent('Ray', tree, low, [1., 1., 0.], 50., trace=True)

    def test_large_hit_batch_avoids_recursive_result_copying(self):
        count = 1023
        bounds = [[0., 0., 0.], [1., 1., 1.]]
        tree = self.tree([self.row(str(index), [.5, .5, .5], bounds, index)
                          for index in range(count)])
        originals = {key: self.h.builtins[key] for key in ('APPEND', 'CONS', 'REVERSE')}
        counts = {'append-copied-nodes': 0, 'cons-nodes': 0, 'reverse-nodes': 0}

        def append(*values):
            # APPEND copies each non-final argument in native AutoLISP. These
            # are logical list nodes; the Python host's elapsed time is ignored.
            counts['append-copied-nodes'] += sum(len(seq(value)) for value in values[:-1])
            return originals['APPEND'](*values)

        def cons(first, rest):
            counts['cons-nodes'] += 1
            return originals['CONS'](first, rest)

        def reverse(value):
            counts['reverse-nodes'] += len(seq(value))
            return originals['REVERSE'](value)

        self.h.builtins.update({'APPEND': append, 'CONS': cons, 'REVERSE': reverse})
        try:
            for kind, args in [('Box', (bounds, 0.)),
                               ('Ray', ([-1., .5, .5], [1., 0., 0.], 3.))]:
                for key in counts:
                    counts[key] = 0
                expected = self.call(f'test:LegacySpatial{kind}Query', tree, *args)
                old = counts.copy()
                for key in counts:
                    counts[key] = 0
                actual = self.call(f'EL:Spatial{kind}Query', tree, *args)
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), count)
                self.assertGreater(old['append-copied-nodes'], 4*count)
                self.assertEqual(counts['append-copied-nodes'], 0)
                self.assertEqual(counts['cons-nodes'], 2*count-1)
                self.assertEqual(counts['reverse-nodes'], count)
        finally:
            self.h.builtins.update(originals)


if __name__ == '__main__':
    unittest.main()
