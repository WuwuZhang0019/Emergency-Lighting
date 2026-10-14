"""Date: 2026-10-15. Exact geometry/order, fresh reads and frozen 138 equivalence."""
import copy
from collections import Counter
import random
import unittest

from autolisp_host import Pair, Symbol
from check_recognition_work import ROOT, fixture
from check_store_read_work import exact


class RecognitionFastpathTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture(3)
        self.h = self.f.h
        self.call, self.get = self.f.call, self.f.get
        self.h.load_definitions(ROOT / 'tests/fixtures/recognition-138-oracle.lsp')

    def put(self, key, value, data):
        return self.call('EL:Put', Symbol(key.upper()), value, data)

    def test_spatial_tree_layout_queries_and_coincident_keys_match_frozen_138(self):
        rng = random.Random(139)
        for size in (0, 1, 2, 17, 65):
            items = []
            for i in range(size):
                point = [float(rng.randrange(-3, 4)), float(rng.randrange(-3, 4)), 0.]
                items.append([Pair(Symbol('KEY'), [str(i % 7), i]), Pair(Symbol('POINT'), point),
                              Pair(Symbol('BOUNDS'), [point, [point[0] + .5, point[1] + .5, 0.]])])
            for axis in (0, 1, 2):
                with self.subTest(size=size, axis=axis):
                    old = self.call('oracle:SpatialTree', items, axis)
                    new = self.call('EL:SpatialTree', items, axis)
                    self.assertEqual(exact(new), exact(old))
                    self.assertEqual(self.call('EL:SpatialBoxQuery', new, [[-1., -1., 0.], [1., 1., 0.]], .01),
                                     self.call('EL:SpatialBoxQuery', old, [[-1., -1., 0.], [1., 1., 0.]], .01))

    def test_collection_reads_wire_once_and_excludes_managed_output(self):
        f = self.f
        f.block('LAMP', 'D', 'managed', [5., 0., 0.])
        f.entities['managed'].append([-3, ['EL_FIXED_V1', Pair(1000, 'managed-output')]])
        f.selected.append('managed')
        # Foreign circuit-label XData must not enter the geometry raw signature.
        f.entities['root-0'].append([-3, ['linenum', Pair(1000, 'ZE1')]])
        reader, reads = self.h.builtins['ENTGET'], []
        self.h.builtins['ENTGET'] = lambda e, apps=None: reads.append((e, apps)) or reader(e, apps)
        before = copy.deepcopy(f.entities)
        snapshot = self.call('EL:SimpleCollect', f.cfg)
        self.assertNotIn('managed', [self.get('id', b) for b in self.get('blocks', snapshot)])
        self.assertEqual([apps for e, apps in reads if e == 'root-0'], [['EL_FIXED_V1']])
        wire = next(w for w in self.get('wires', snapshot) if self.get('id', w) == 'root-0')
        self.assertEqual(exact(wire), exact(self.call('EL:WireRecord', 'root-0', f.cfg)))
        self.assertEqual(f.entities, before)

    def test_effective_names_share_only_one_definition_within_current_collection(self):
        f = self.f
        for index, definition in enumerate(('*U123', '*U456')):
            handle = f'dynamic-{index}'
            f.block(definition, 'D', handle, [12. + index, 0., 0.])
            f.selected.append(handle)
        reads, changed = [], [False]
        def effective(entity):
            definition = next(p.cdr for p in f.entities[entity] if isinstance(p, Pair) and p.car == 2)
            reads.append(definition)
            return ('CHANGED' if changed[0] else 'LAMP') if definition.startswith('*U') else definition
        self.h.builtins['VLA-GET-EFFECTIVENAME'] = effective
        first = self.call('EL:SimpleCollect', f.cfg)
        self.assertEqual(Counter(reads), {'BOX': 1, 'LAMP': 1, '*U123': 1, '*U456': 1})
        self.assertEqual([self.get('name', b) for b in self.get('blocks', first)
                          if self.get('id', b).startswith('dynamic-')], ['LAMP', 'LAMP'])
        changed[0] = True
        reads.clear()
        second = self.call('EL:SimpleCollect', self.put('device-names', ['LAMP', 'CHANGED'], f.cfg))
        self.assertEqual(Counter(reads), {'BOX': 1, 'LAMP': 1, '*U123': 1, '*U456': 1})
        self.assertEqual([self.get('name', b) for b in self.get('blocks', second)
                          if self.get('id', b).startswith('dynamic-')], ['CHANGED', 'CHANGED'])

    def test_joint_number_boundary_matches_frozen_32_steps_holes_widths_reverse_and_ties(self):
        def shape(lo, hi, hole=None):
            ring = self.call('EL:BoundsSegments', [lo, hi])
            holes = [self.call('EL:BoundsSegments', hole)] if hole else None
            return [Pair(Symbol('SEGMENTS'), ring + (holes[0] if holes else [])),
                    Pair(Symbol('REGIONS'), [ring]), Pair(Symbol('HOLES'), holes)]
        shapes = {'first': shape([4., -2., 0.], [6., 2., 0.]),
                  'tie': shape([4., -2., 0.], [6., 2., 0.]),
                  'far': shape([12., -2., 0.], [14., 2., 0.]),
                  'hole': shape([2., -2., 0.], [18., 2., 0.], [[3., -1., 0.], [17., 1., 0.]])}
        self.h.builtins['EL:DEVICECONTACTSHAPE'] = lambda b: shapes[self.get('id', b)]
        for y, start, end, order in ((0., 0., 20., ['far', 'first', 'tie']),
                                   (0., 0., 20., ['tie', 'first', 'far']),
                                   (0., 20., 0., ['first', 'tie', 'far']),
                                   (0., 10., 20., ['hole', 'far']),
                                   (0., 10., 0., ['hole', 'first']),
                                   (3., 0., 20., ['first', 'far']),
                                   (3., 20., 0., ['hole', 'first']),
                                   (0., 10., 10., ['first'])):
            wire = [Pair(Symbol('SEGMENTS'), [[[0., y, 0.], [10., y, 0.]], [[10., y, 0.], [20., y, 0.]]]),
                    Pair(Symbol('WIDTH-PROFILES'), [[[0., y, 0.], [20., y, 0.], 4., 4.]] if y else None)]
            devices = [[Pair(Symbol('ID'), name)] for name in order]
            with self.subTest(y=y, start=start, end=end, order=order):
                expected = self.call('oracle:NumberFirstDevice', wire, start, end, devices, self.f.cfg)
                actual = self.call('EL:NumberFirstDevice', wire, start, end, devices, self.f.cfg)
                self.assertEqual(exact(actual), exact(expected))


if __name__ == '__main__':
    unittest.main()
