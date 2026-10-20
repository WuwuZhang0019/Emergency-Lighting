"""Command-local exact candidate index. Date: 2026-10-21.

Finite CAD adapters and operation counts; native DWG timing remains pending.
"""
import unittest

from autolisp_host import Pair, Symbol, car, equal, seq, truth
import test_simple_flow as simple


class CandidateDedupTests(unittest.TestCase):
    setUp = simple.SimpleFlowTests.setUp
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    block = simple.SimpleFlowTests.block
    line = simple.SimpleFlowTests.line
    gap_plan = simple.SimpleFlowTests.gap_plan

    def index_scope(self):
        self.h.frames.append({
            '*EL:CANDIDATEINDEX*': None, '*EL:CANDIDATEINDEXOTHER*': None,
            '*EL:CANDIDATEINDEXLOOKUPS*': 0, '*EL:CANDIDATEINDEXSTEPS*': 0,
            '*EL:CANDIDATEINDEXDUPLICATES*': 0})

    def legacy_index(self):
        """The previous candidate MEMBER/CONS logic, with comparison counts."""
        seen, comparisons = [], []

        def add(key):
            for value in seen:
                comparisons.append(1)
                if equal(key, value):
                    return None
            seen.insert(0, key)
            return True

        self.h.builtins['EL:CANDIDATEINDEXADD'] = add
        return comparisons

    def compare_collection_and_network(self):
        snapshot = self.call('EL:SimpleCollect', self.cfg)
        network = self.call('EL:SimpleNetwork', snapshot, self.cfg, 'panel')
        self.legacy_index()
        baseline = self.call('EL:SimpleCollect', self.cfg)
        baseline_network = self.call('EL:SimpleNetwork', baseline, self.cfg, 'panel')
        self.assertEqual(snapshot, baseline)
        self.assertEqual(network, baseline_network)
        return snapshot, network

    def test_exact_ids_keep_prefixes_case_unicode_and_nonstring_fallback(self):
        ids = ['', 'A', 'AB', 'ABC', 'AB0', 'a', '灯1', '灯2', None, 17,
               Symbol('A'), ['A', 'B']]
        self.index_scope()
        try:
            for value in ids:
                self.assertTrue(truth(self.call('EL:CandidateIndexAdd', value)), value)
            for value in reversed(ids):
                self.assertFalse(truth(self.call('EL:CandidateIndexAdd', value)), value)
            self.assertEqual(self.h.lookup('*EL:CANDIDATEINDEXLOOKUPS*'), 2*len(ids))
            self.assertEqual(self.h.lookup('*EL:CANDIDATEINDEXDUPLICATES*'), len(ids))
        finally:
            self.h.frames.pop()

    def test_many_repeated_native_handles_avoid_growing_linear_membership(self):
        # Four passes over 384 native-shaped handles. The legacy comparison
        # count grows with the number of already accepted IDs; trie branch
        # comparisons remain bounded by handle length and hexadecimal digits.
        ids = [f'{i:06X}' for i in range(384)] * 4
        legacy_comparisons = self.legacy_index()
        expected = [truth(self.call('EL:CandidateIndexAdd', key)) for key in ids]
        del self.h.builtins['EL:CANDIDATEINDEXADD']
        original_assoc = self.h.builtins['ASSOC']
        original_compare = self.h.builtins['=']
        branch_comparisons = []

        def assoc(key, rows):
            for row in seq(rows):
                branch_comparisons.append(1)
                if equal(car(row), key):
                    return row
            return None

        def compare(*values):
            branch_comparisons.append(1)
            return original_compare(*values)

        self.h.builtins['ASSOC'] = assoc
        self.h.builtins['='] = compare
        self.index_scope()
        try:
            actual = [truth(self.call('EL:CandidateIndexAdd', key)) for key in ids]
            self.assertEqual(actual, expected)
            self.assertEqual(sum(actual), 384)
            self.assertEqual(self.h.lookup('*EL:CANDIDATEINDEXSTEPS*'), len(ids)*6)
            self.assertLess(len(branch_comparisons)*5, len(legacy_comparisons))
        finally:
            self.h.frames.pop()
            self.h.builtins['ASSOC'] = original_assoc
            self.h.builtins['='] = original_compare

    def test_first_representative_output_and_expansion_order_match_member(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.line('w', [1., 0., 0.], [9., 0., 0.], 'W')
        self.selected = ['panel', 'w']

        def candidate(key, name, x):
            return [Pair(Symbol('KEY'), key), Pair(Symbol('ENTITY'), key+'-entity'),
                    Pair(Symbol('NAME'), name), Pair(Symbol('LAYER'), 'D'),
                    Pair(Symbol('BOUNDS'), [[x-1., -1., 0.], [x+1., 1., 0.]])]

        first = candidate('A', 'FIRST', 10.)
        duplicate = candidate('A', 'SECOND', 100.)
        second = candidate('AB', 'SECOND-ID', 12.)
        third = candidate('B', 'CHAIN-1', 14.)
        fourth = candidate('BA', 'CHAIN-2', 16.)
        self.h.builtins['EL:SIMPLEBLOCKCANDIDATES'] = lambda *args: [first, duplicate, second]
        self.h.builtins['EL:SPATIALBOXQUERY'] = lambda tree, bounds, tolerance: {
            9.: [duplicate, third], 11.: [first, second],
            13.: [third, fourth], 15.: [fourth]}[bounds[0][0]]
        actual = self.call('EL:SimpleCollect', self.cfg)
        self.legacy_index()
        expected = self.call('EL:SimpleCollect', self.cfg)
        self.assertEqual(actual, expected)
        blocks = self.get('blocks', actual)
        self.assertEqual([self.get('id', block) for block in blocks], ['BA', 'B', 'AB', 'A'])
        self.assertEqual(self.get('name', blocks[-1]), 'FIRST')
        self.assertEqual(self.get('bounds', blocks[-1]), self.get('bounds', first))

    def test_touching_device_chain_and_far_wire_candidates_keep_real_network(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        for handle, x, y in [('a', 10., 0.), ('b', 12., 0.), ('c', 14., 0.),
                             ('far', 810., 100.)]:
            self.block('LAMP', 'D', handle, [x, y, 0.])
        self.line('root', [1., 0., 0.], [9., 0., 0.], 'W')
        self.line('far-wire', [800., 100., 0.], [809., 100., 0.], 'W')
        self.selected = ['panel', 'a', 'b', 'c', 'far', 'root', 'far-wire']
        snapshot, network = self.compare_collection_and_network()
        self.assertEqual({self.get('id', block) for block in self.get('blocks', snapshot)},
                         {'panel', 'a', 'b', 'c', 'far'})
        self.assertEqual({self.get('id', block) for block in self.get('devices', network)}, {'a', 'b', 'c'})
        self.assertNotIn('far-wire', self.get('wire-ids', network))

    def test_gap_ray_keeps_obstacle_source_without_creating_false_connection(self):
        self.gap_plan()
        self.block('LAMP', 'D', 'obstacle', [15., 0., 0.])
        self.selected.append('obstacle')
        snapshot, network = self.compare_collection_and_network()
        self.assertIn('obstacle', [self.get('id', block) for block in self.get('blocks', snapshot)])
        self.assertEqual([self.get('id', block) for block in self.get('devices', network)], ['after'])
        self.assertEqual(len(self.get('gap-pairs', network)), 1)
        self.assertNotIn('obstacle', sum(self.get('edges', network), []))

    def test_index_is_fresh_after_return_cancellation_and_drawing_change(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('LAMP', 'D', 'a', [10., 0., 0.])
        self.line('root', [1., 0., 0.], [9., 0., 0.], 'W')
        self.selected = ['panel', 'a', 'root']
        actual = self.call('EL:SimpleCollect', self.cfg)
        for symbol in ('*EL:CANDIDATEINDEX*', '*EL:CANDIDATEINDEXOTHER*'):
            self.assertIsNone(self.h.lookup(symbol))
        original = self.h.functions[Symbol('EL:CANDIDATEINDEXADD')]
        fn = [Symbol('LAMBDA'), original[0], *original[1]]

        def cancelled(key):
            self.h.call(fn, [key])
            raise RuntimeError('Function cancelled')

        self.h.builtins['EL:CANDIDATEINDEXADD'] = cancelled
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.call('EL:SimpleCollect', self.cfg)
        self.assertIsNone(self.h.lookup('*EL:CANDIDATEINDEX*'))
        del self.h.builtins['EL:CANDIDATEINDEXADD']
        self.h.builtins['NAMEDOBJDICT'] = lambda: 'another-drawing-owner'
        self.assertEqual(self.call('EL:SimpleCollect', self.cfg), actual)

    def test_empty_selection_and_batch_stage_metrics_remain_bounded(self):
        starts, ends, counts = [], [], []
        self.h.builtins['EL:PERFBEGIN'] = lambda name: starts.append(name) or name
        self.h.builtins['EL:PERFEND'] = lambda token, outcome: ends.append(token)
        self.h.builtins['EL:PERFCOUNT'] = lambda key, value: counts.append((key, value))
        self.selected = []
        snapshot = self.call('EL:SimpleCollect', self.cfg)
        self.assertFalse(self.get('blocks', snapshot))
        self.assertEqual(starts, ['COLLECT_ENTITY_READ', 'COLLECT_CANDIDATES',
                                 'COLLECT_SPATIAL_TREE', 'COLLECT_CANDIDATE_DEDUP',
                                 'COLLECT_DEVICE_EXPAND'])
        self.assertEqual(ends, ['COLLECT_ENTITY_READ', 'COLLECT_SPATIAL_TREE',
                               'COLLECT_CANDIDATE_DEDUP', 'COLLECT_DEVICE_EXPAND',
                               'COLLECT_CANDIDATES'])
        self.assertEqual([row for row in counts if row[0].startswith('source-candidate-index-')],
                         [('source-candidate-index-lookups', 0),
                          ('source-candidate-index-steps', 0),
                          ('source-candidate-index-duplicates', 0)]*2)
        # Even with real repeated box/ray hits, only the two batch flushes
        # publish metrics. No per-candidate PerfCount/log call is introduced.
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('LAMP', 'D', 'a', [10., 0., 0.])
        self.line('w', [1., 0., 0.], [9., 0., 0.], 'W')
        self.selected = ['panel', 'a', 'w']
        counts.clear()
        self.call('EL:SimpleCollect', self.cfg)
        metrics = [row for row in counts if row[0].startswith('source-candidate-index-')]
        self.assertEqual(len(metrics), 6)
        self.assertGreater(sum(value for key, value in metrics if key.endswith('lookups')), 2)
        self.assertGreater(sum(value for key, value in metrics if key.endswith('duplicates')), 0)


if __name__ == '__main__':
    unittest.main()
