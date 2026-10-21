"""Date: 2026-10-21. Complete source freshness with rooted fine geometry.

Status: bounded source regression; no native AutoCAD timing or acceptance.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
from check_store_read_work import exact
import test_freshness_reuse as fresh
import test_simple_flow as simple
from test_network_proof import native_list_pairs


class RootScopeFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.f = fresh.FreshnessReuseTests()
        self.f.setUp()
        self.h = self.f.h
        self.call = self.f.call
        self.get = self.f.f.get
        self.events = []
        self.h.builtins['EL:LOGEVENT'] = lambda stage, detail: self.events.append((stage, detail))
        self.h.builtins['CHR'] = chr
        self.h.builtins['GETVAR'] = lambda key: {
            'MILLISECS': 100, 'DWGNAME': 'sample.dwg', 'DWGPREFIX': 'C:/cad/'
        }.get(key)
        # These objects cannot become gap candidates merely because Dmax is
        # generous. Their raw facts must nevertheless invalidate stale results.
        self.f.f.block('LAMP', 'D', 'remote', [50010., 0., 0.])
        self.f.f.line('wr', [50001., 0., 0.], [50009., 0., 0.], 'W')
        self.cfg = self.put('auto-panel', 'panel', self.f.f.cfg)
        self.cfg = self.put('circuit-starts', [[Pair(Symbol('WIRE'), 'w1'),
            Pair(Symbol('END'), Symbol('START')), Pair(Symbol('POINT'), [1., 0., 0.])]], self.cfg)
        self.f.f.cfg = self.cfg
        self.call('EL:PerfStart', 'ELSTAT')

    def put(self, key, value, record):
        return self.call('EL:Put', Symbol(key.upper()), value, record)

    def result(self):
        return self.call('EL:RecognizeFixed', self.cfg, 'panel')

    def snapshot(self, result):
        return self.get('snapshot', result)

    def facts(self, result):
        return self.get('source-selection-facts', self.snapshot(result))

    def handle(self, fact):
        return self.call('CDR', self.call('ASSOC', 5, fact[0]))

    def circuit_devices(self, result):
        return sorted(sorted(self.get('devices', circuit) or [])
                      for circuit in self.get('circuits', result) or [])

    def boundary(self):
        self.call('EL:FreshBoundary')

    def test_complete_ordered_raw_facts_survive_fine_scope_and_ignore_managed_outputs(self):
        self.f.f.block('LAMP', 'D', 'managed', [70000., 0., 0.])
        self.f.f.entities['managed'].append([-3, ['EL_FIXED_V1', Pair(1000, 'output')]])
        self.f.f.selected.append('managed')
        result = self.result()
        facts = self.facts(result)
        self.assertTrue(facts)
        self.assertEqual([self.handle(fact) for fact in facts],
                         [handle for handle in self.f.f.selected if handle != 'managed'])
        for fact in facts:
            handle = self.handle(fact)
            self.assertEqual(exact(fact[0]),
                             exact(self.h.builtins['ENTGET'](handle, ['EL_FIXED_V1'])))
            self.assertEqual(exact(fact[1]), exact(self.f.f.bounds.get(handle)))
        self.assertIn('wr', [self.handle(fact) for fact in facts])
        self.assertIn('remote', [self.handle(fact) for fact in facts])
        self.assertEqual(self.circuit_devices(result), [['a', 'b']])

    def test_unrelated_remote_add_delete_and_raw_edits_still_invalidate_source(self):
        for change in ('add', 'delete', 'move', 'width', 'block-move'):
            with self.subTest(change=change):
                self.setUp()
                result = self.result()
                before = exact(self.get('signature', self.snapshot(result)))
                if change == 'add':
                    self.f.f.line('new-remote', [60001., 0., 0.], [60009., 0., 0.], 'W')
                    self.f.f.selected.append('new-remote')
                elif change == 'delete':
                    self.f.f.selected.remove('wr')
                elif change == 'move':
                    self.f.f.line('wr', [50002., 1.e-15, 0.], [50009., 0., 0.], 'W')
                elif change == 'width':
                    self.f.f.entities['wr'].append(Pair(370, 50))
                else:
                    self.f.f.block('LAMP', 'D', 'remote', [50010., 1., 0.])
                self.boundary()
                self.assertFalse(truth(self.call('EL:FreshResult', result, self.cfg)))
                current = self.call('EL:FixedFreshSnapshotFull', self.cfg, 'panel')
                self.assertNotEqual(exact(self.get('signature', current)), before)
                # The source changed, although the selected circuits did not.
                self.assertEqual(self.circuit_devices(self.result()), [['a', 'b']])

    def test_moved_remote_wire_and_device_enter_the_reachable_chain(self):
        result = self.result()
        self.assertEqual(self.circuit_devices(result), [['a', 'b']])
        self.f.f.line('wr', [7., 0., 0.], [7., 9., 0.], 'W')
        self.f.f.block('LAMP', 'D', 'remote', [7., 10., 0.])
        self.boundary()
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.cfg)))
        changed = self.result()
        self.assertEqual(self.circuit_devices(changed), [['a', 'b', 'remote']])
        self.assertIn('wr', [self.get('id', wire)
                             for wire in self.get('wires', self.snapshot(changed))])

    def test_negative_contact_definition_edit_with_unchanged_insert_and_bounds_is_detected(self):
        self.f.f.block('MISS', 'D', 'miss', [8., 3., 0.])
        # Native extents may include attributes. The broad box intersects the
        # source wire, while the original closed square does not.
        self.f.f.bounds['miss'] = [[7., -1., 0.], [9., 4., 0.]]
        self.f.f.selected.append('miss')
        result = self.result()
        self.assertNotIn('miss', sum(self.circuit_devices(result), []))
        before = exact(self.facts(result))
        self.assertIn('miss', str(self.get('device-contact-signature', self.snapshot(result))))
        old_insert = copy.deepcopy(self.f.f.entities['miss'])
        old_bounds = copy.deepcopy(self.f.f.bounds['miss'])
        corners = [[-1., -3., 0.], [1., -3., 0.], [1., 1., 0.], [-1., 1., 0.]]
        for index in range(4):
            self.f.f.line(f'MISS-edge-{index}', corners[index], corners[(index+1) % 4])
        self.boundary()
        self.assertEqual(self.f.f.entities['miss'], old_insert)
        self.assertEqual(self.f.f.bounds['miss'], old_bounds)
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.cfg)))
        changed = self.result()
        self.assertEqual(exact(self.facts(changed)), before)
        self.assertIn('miss', sum(self.circuit_devices(changed), []))
        self.assertNotEqual(exact(self.get('signature', self.snapshot(changed))),
                            exact(self.get('signature', self.snapshot(result))))

    def test_full_fresh_snapshot_without_memos_matches_the_complete_recognition_snapshot(self):
        for gap in (False, True):
            with self.subTest(gap=gap):
                self.setUp()
                if gap:
                    simple.SimpleFlowTests.gap_plan(self.f.f)
                    self.cfg = self.put('circuit-starts', [[Pair(Symbol('WIRE'), 'before'),
                        Pair(Symbol('END'), Symbol('START')),
                        Pair(Symbol('POINT'), [1., 0., 0.])]], self.cfg)
                    self.f.f.cfg = self.cfg
                result = self.result()
                baseline = exact(self.snapshot(result))
                self.call('EL:PerfFinish', Symbol('FINISHED'))
                self.call('EL:PerfStart', 'ELSTAT')
                self.assertIsNone(self.h.lookup('*EL:COLLECTMEMO*'))
                self.assertIsNone(self.h.lookup('*EL:NETWORKMEMO*'))
                fresh_snapshot = self.call('EL:FixedFreshSnapshotFull', self.cfg, 'panel')
                self.assertEqual(exact(fresh_snapshot), baseline)
                self.assertTrue(truth(self.call('EL:FreshResult', result, self.cfg)))

    def test_preview_restore_explicit_visible_keeps_freshness_but_hidden_source_does_not(self):
        for handle in ('w1', 'a'):
            with self.subTest(source=handle):
                self.setUp()
                result = self.result()
                baseline = exact(self.get('signature', self.snapshot(result)))
                self.assertFalse(any(isinstance(row, Pair) and row.car == 60
                                     for row in self.f.f.entities[handle]))
                # Native Visible=False/True preview restoration can materialize
                # the default as DXF 60=0. This must remain the same source.
                self.f.f.entities[handle].append(Pair(60, 0))
                self.boundary()
                self.assertTrue(truth(self.call('EL:FreshResult', result, self.cfg)))
                fresh_snapshot = self.call('EL:FixedFreshSnapshotFull', self.cfg, 'panel')
                self.assertEqual(exact(self.get('signature', fresh_snapshot)), baseline)
                # A real visibility edit is still part of exact source facts.
                self.f.f.entities[handle] = [row for row in self.f.f.entities[handle]
                    if not (isinstance(row, Pair) and row.car == 60)] + [Pair(60, 1)]
                self.boundary()
                self.assertFalse(truth(self.call('EL:FreshResult', result, self.cfg)))
    def test_roundtripped_proof_without_collect_memo_verifies_complete_raw_source(self):
        # Normalize only the native DXF fixture representation; preserve every
        # typed value while exercising the actual StoreEncode/StoreDecode path.
        entget = self.h.builtins['ENTGET']
        self.h.builtins['ENTGET'] = lambda *args: native_list_pairs(entget(*args))
        result = self.result()
        signature = self.get('signature', self.snapshot(result))
        saved = self.call('EL:StoreDecode', self.call('EL:StoreEncode', signature))
        restored_snapshot = self.call('EL:CircuitSnapshot', saved[1], 'panel')
        restored = self.put('snapshot', restored_snapshot, result)
        self.call('EL:PerfFinish', Symbol('FINISHED'))
        self.call('EL:PerfStart', 'ELSTAT')
        self.assertIsNone(self.h.lookup('*EL:COLLECTMEMO*'))
        self.assertTrue(truth(self.call('EL:FreshResult', restored, self.cfg)))
        metrics = self.h.lookup('*EL:PERFMETRICS*')
        self.assertEqual(self.call('EL:Get', 'network-proof-reuses', metrics), 1)
        self.f.f.line('wr', [50001., 1.e-15, 0.], [50009., 0., 0.], 'W')
        self.boundary()
        self.assertFalse(truth(self.call('EL:FreshResult', restored, self.cfg)))
    def test_number_metadata_is_verified_independently_when_geometry_and_raw_facts_match(self):
        result = self.result()
        reviewed = self.call('EL:PreparedResult', result,
                             [Pair(Symbol('DIAGRAM-ID'), 'root-freshness')])
        self.assertTrue(truth(self.get('number-inputs', reviewed)))
        baseline = exact(self.get('signature', self.snapshot(reviewed)))
        self.f.f.entities['w1'].append([-3, ['linenum', Pair(1000, 'ZE9')]])
        self.boundary()
        fresh_snapshot = self.call('EL:FixedFreshSnapshotFull', self.cfg, 'panel')
        # Collect uses only EL_FIXED_V1 XData. LINENUM intentionally belongs to
        # the separately sampled native numbering inputs, not source geometry.
        self.assertEqual(exact(self.get('signature', fresh_snapshot)), baseline)
        self.assertFalse(truth(self.call('EL:NumberInputsCurrent', reviewed)))
        self.assertFalse(truth(self.call('EL:FreshResult', reviewed, self.cfg)))
        self.assertTrue(any(stage == 'SOURCE_NUMBER_CHANGED' for stage, _ in self.events))
        current = self.call('EL:PreparedResult', self.result(),
                            [Pair(Symbol('DIAGRAM-ID'), 'root-freshness')])
        self.assertEqual(self.get('circuit-number', self.get('circuits', current)[0]), 'ZE9')


if __name__ == '__main__':
    unittest.main()