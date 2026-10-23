"""Date: 2026-10-23. Shared picked start-link exclusion; finite CAD replay only."""
import copy
import json
import math
from pathlib import Path
import unittest

from autolisp_host import Pair, Symbol, truth
import test_circuit_starts as starts


ROOT = Path(__file__).resolve().parents[1]
HOTEL = json.loads((ROOT / 'tests/fixtures/hotel-shared-start-link-20261023.json').read_text(encoding='utf-8'))


class SharedStartLinkTests(unittest.TestCase):
    def fixture(self):
        f = starts.CircuitStartTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.h.step_limit = 4_000_000
        f.h.builtins['ALERT'] = lambda *a: self.fail('classification must not prompt')
        return f

    def trunk_roots(self, f):
        return f.starts(('trunk', 'start'), *[(f'w{i}', 'start') for i in range(5)])

    def test_shared_link_is_not_an_extra_circuit_and_source_edits_still_invalidate(self):
        f = self.fixture(); f.trunk(); self.trunk_roots(f)
        original = copy.deepcopy(f.cfg)
        result = f.recognize()
        self.assertEqual(len(f.get('circuits', result)), 5)
        self.assertEqual(f.devices(result), [[f'd{i}'] for i in range(5)])
        self.assertEqual(f.cfg, original)
        link = f.get('start-link-exclusions', result)[0]
        self.assertEqual(f.get('wire', link), 'trunk')
        self.assertEqual(len(f.get('supported-starts', link)), 5)
        self.assertEqual(len(f.get('candidate-keys', result)), 6)
        self.assertTrue(truth(f.call('EL:FreshResult', result, f.cfg)))
        f.line('trunk', [10., -20., 0.], [10., 21., 0.], 'W')
        self.assertFalse(truth(f.call('EL:FreshResult', result, f.cfg)))

    def test_link_orientation_and_endpoint_order_do_not_determine_exclusion(self):
        for angle in (math.pi / 2, math.pi / 4):
            with self.subTest(angle=angle):
                f = self.fixture(); f.trunk()
                c, s = math.cos(angle), math.sin(angle)
                for entity in f.entities.values():
                    for row in entity:
                        if isinstance(row, Pair) and row.car in (10, 11) and isinstance(row.cdr, list):
                            x, y, z = row.cdr
                            row.cdr[:] = [c*x-s*y, s*x+c*y, z]
                self.trunk_roots(f)
                result = f.recognize()
                self.assertEqual(len(f.get('circuits', result)), 5)
                self.assertEqual(f.get('wire', f.get('start-link-exclusions', result)[0]), 'trunk')
        f = self.fixture(); f.trunk()
        f.line('trunk', [10., 20., 0.], [10., -20., 0.], 'W')
        self.trunk_roots(f)
        self.assertEqual(len(f.get('circuits', f.recognize())), 5)

    def test_a_picked_wire_with_its_own_device_is_preserved(self):
        f = self.fixture(); f.trunk()
        f.block('LAMP', 'D', 'own-device', [10., 20., 0.]); f.selected.append('own-device')
        self.trunk_roots(f)
        result = f.recognize()
        self.assertEqual(len(f.get('circuits', result)), 6)
        self.assertFalse(f.get('start-link-exclusions', result))
        self.assertTrue(any('own-device' in (f.get('devices', c) or []) for c in f.get('circuits', result)))

    def test_a_wire_with_downstream_continuation_is_preserved(self):
        f = self.fixture(); f.trunk()
        f.line('tail', [10., 20., 0.], [29., 20., 0.], 'W')
        f.block('LAMP', 'D', 'tail-device', [30., 20., 0.])
        f.selected += ['tail', 'tail-device']; self.trunk_roots(f)
        result = f.recognize()
        self.assertEqual(len(f.get('circuits', result)), 6)
        self.assertFalse(f.get('start-link-exclusions', result))

    def test_an_ordinary_empty_picked_branch_is_not_silently_removed(self):
        f = self.fixture()
        f.line('empty', [50., 50., 0.], [60., 50., 0.], 'W'); f.selected.append('empty')
        f.starts(('w1', 'start'), ('empty', 'start'))
        result = f.recognize()
        self.assertEqual(len(f.get('circuits', result)), 2)
        self.assertFalse(f.get('start-link-exclusions', result))
        self.assertTrue(any(f.get('wires', c) == ['empty'] for c in f.get('circuits', result)))

    def test_collinear_coincident_and_disconnected_ports_are_not_proof_of_a_link(self):
        for points in (([10., 0., 0.], [10., 0., 0.]),
                       ([11., -6., 0.], [11., 6., 0.]),
                       ([10., -6., 1.], [10., 6., 1.])):
            f = self.fixture(); f.trunk()
            f.line('p0', points[0], [30., points[0][1], points[0][2]], 'W')
            f.line('p1', points[1], [30., points[1][1], points[1][2]], 'W')
            rows = f.starts(('trunk', 'start'), ('p0', 'start'), ('p1', 'start'))
            wire_rows = [f.call('EL:WireRecord', h, f.cfg) for h in ('trunk', 'p0', 'p1')]
            snapshot = [Pair(Symbol('WIRES'), wire_rows)]
            support = f.call('EL:StartLinkSupports', wire_rows[0], rows, snapshot, f.cfg)
            self.assertLess(len(support or []), 2)
        f = self.fixture(); f.trunk()
        f.line('p0', [10., -6., 0.], [10., -4., 0.], 'W')
        f.line('p1', [10., 6., 0.], [10., 8., 0.], 'W')
        rows = f.starts(('trunk', 'start'), ('p0', 'start'), ('p1', 'start'))
        wire_rows = [f.call('EL:WireRecord', h, f.cfg) for h in ('trunk', 'p0', 'p1')]
        self.assertFalse(f.call('EL:StartLinkSupports', wire_rows[0], rows, [Pair(Symbol('WIRES'), wire_rows)], f.cfg))

    def test_panel_reentry_preserves_exclusion_candidates_and_surviving_row_values(self):
        f = self.fixture(); f.trunk(); self.trunk_roots(f)
        result = f.recognize()
        rows = f.get('circuits', result)
        for index, row in enumerate(rows):
            rows[index] = f.call('EL:Put', Symbol('CIRCUIT-UID'), f'keep-{index}',
                f.call('EL:Put', Symbol('WATTS'), index+7, row))
        before = copy.deepcopy(result)
        for _ in range(2):
            result = f.call('EL:SelectFixedExits', result, None)
        self.assertEqual(f.get('circuits', result), f.get('circuits', before))
        self.assertEqual(f.get('candidate-keys', result), f.get('candidate-keys', before))
        self.assertEqual(f.get('start-link-exclusions', result), f.get('start-link-exclusions', before))
        self.assertEqual(f.get('excluded-seeds', result), [['trunk', Symbol('OUTLET')]])

    def test_hotel_c874_exact_six_wire_subset_has_four_independent_roots(self):
        f = self.fixture()
        for handle, data in HOTEL['entities'].items():
            f.entities[handle] = [Pair(code, value) for code, value in data]
        f.starts(*[(handle, side.lower()) for handle, side in HOTEL['starts']])
        original = copy.deepcopy(f.cfg)
        wire_rows = [f.call('EL:WireRecord', handle, f.cfg) for handle in HOTEL['entities']]
        snapshot = [Pair(Symbol('WIRES'), wire_rows), Pair(Symbol('BLOCKS'), None),
                    Pair(Symbol('ENDS'), [ep for row in wire_rows for ep in f.get('ends', row)])]
        snapshot = f.call('EL:StartSnapshot', snapshot, f.cfg, 'panel')
        network = f.call('EL:SimpleNetworkBuild', snapshot, f.cfg, 'panel')
        raw = f.call('EL:SplitNetwork', network, f.cfg)
        self.assertEqual(len(f.get('circuits', raw)), 5)
        result = f.call('EL:SelectFixedExits', f.call('EL:ClassifyStartLinks', raw, f.cfg), None)
        self.assertEqual(len(f.get('circuits', result)), 4)
        self.assertEqual([f.get('wire', f.get('seed', c)) for c in f.get('circuits', result)], HOTEL['expected_kept'])
        link = f.get('start-link-exclusions', result)[0]
        self.assertEqual(f.get('wire', link), 'C874')
        self.assertEqual(len(f.get('supported-starts', link)), 4)
        self.assertEqual(f.cfg, original)


if __name__ == '__main__':
    unittest.main()
