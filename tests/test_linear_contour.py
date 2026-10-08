"""Linear contour BVH correctness and work budget. Date: 2026-10-08."""
import random
import unittest
from autolisp_host import Symbol, truth
import test_contact_index as contact


class LinearContourTests(unittest.TestCase):
    setUp = contact.ContactIndexTests.setUp
    call = contact.ContactIndexTests.call
    get = contact.ContactIndexTests.get
    polygon = staticmethod(contact.ContactIndexTests.polygon)
    circle = contact.ContactIndexTests.circle

    def test_queries_preserve_all_candidates_including_shuffled_duplicates(self):
        rng = random.Random(18)
        segments = self.circle(128)
        segments += [segments[0], [[-30., 0., 0.], [30., 0., 0.]]]
        rng.shuffle(segments)
        rows = self.call('EL:RingItems', segments)
        tree = self.call('EL:ContourTree', rows)
        for _ in range(30):
            x, y = rng.uniform(-15, 15), rng.uniform(-15, 15)
            bounds = [[x, y, 0.], [x+2., y+2., 0.]]
            expected = sorted(self.get('key', row) for row in rows if truth(
                self.call('EL:BoundsOverlap', self.get('bounds', row), bounds, .1)))
            actual = sorted(self.get('key', row) for row in self.call('EL:SpatialBoxQuery', tree, bounds, .1) or [])
            self.assertEqual(actual, expected)
        self.assertIsNone(self.call('EL:ContourTree', None))
        self.assertIsNone(self.h.lookup('*EL:ContourCursor*'))

    def test_build_cost_scales_linearly_without_sorting(self):
        def forbidden(*args):
            self.fail('Contour construction must not sort')
        self.h.builtins['VL-SORT'] = forbidden
        work = []
        for count in (512, 1024, 6228):
            rows = self.call('EL:RingItems', self.circle(count))
            self.h.steps = 0
            tree = self.call('EL:ContourTree', rows)
            work.append(self.h.steps)
            def node_count(node):
                return 0 if not node else 1+node_count(node[1])+node_count(node[2])
            self.assertEqual(node_count(tree), count)
        self.assertLess(work[1], work[0]*2.1)
        self.assertLess(work[2], work[0]*12.5)

    def test_stream_bounds_match_xyz_extrema_without_append(self):
        def forbidden(*args):
            self.fail('Bounds must not concatenate endpoint lists')
        self.h.builtins['APPEND'] = forbidden
        segments = [[[12., -3., 7.], [-4., 10., -8.]], [[1., 2., 3.], [20., -10., 9.]]]
        self.assertEqual(self.call('EL:SegmentBounds', segments), [[-4., -10., -8.], [20., 10., 9.]])
        self.assertIsNone(self.call('EL:SegmentBounds', None))
