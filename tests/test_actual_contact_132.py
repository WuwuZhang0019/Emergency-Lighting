"""Replay original DXF tiny contacts and the ZE2 shared endpoint.

Date: 2026-10-14. Status: finite original-DXF subset replay; native CAD pending.
"""
import math
import unittest

from autolisp_host import truth
from actual_contact_fixture import ActualContactFixture


def point_segment_distance(point, segment):
    a, b = segment
    direction = [b[i] - a[i] for i in range(3)]
    length2 = sum(value * value for value in direction)
    fraction = max(0., min(1., sum((point[i] - a[i]) * direction[i]
                                   for i in range(3)) / length2)) if length2 else 0.
    return math.dist(point, [a[i] + fraction * direction[i] for i in range(3)])


class ActualContactTests(unittest.TestCase):
    def setUp(self):
        self.f = ActualContactFixture()

    def device_ids(self, network):
        return sorted(self.f.get('id', block) for block in self.f.get('devices', network) or [])

    def test_fixture_keeps_original_millimetre_gaps_and_native_rotation(self):
        self.assertEqual(self.f.document['units'], 'mm')
        self.assertEqual(self.f.document['source_acadver'], 'AC1032')
        self.assertEqual(self.f.document['source_sha256'],
                         '84d44e91ffc6d19c87d73071388e234f12235a12fd991afdcb164580938e67cd')
        self.assertAlmostEqual(self.f.dxf('F099', 50), 1.5 * math.pi, places=14)
        self.assertEqual(self.f.dxf('F099', 410), 'Model')
        self.assertEqual(self.f.dxf('F097', 43), 50.)
        a = self.f.get('segments', self.f.body_shape('F099'))
        b = self.f.get('segments', self.f.body_shape('84B8'))
        wire_gap = min(point_segment_distance(self.f.dxf('F097', 10), segment) for segment in a)
        body_gap = min(min(*(point_segment_distance(point, second) for point in first),
                           *(point_segment_distance(point, first) for point in second))
                       for first in a for second in b)
        self.assertAlmostEqual(wire_gap, .0038095, places=7)
        self.assertAlmostEqual(body_gap, .005, places=7)
        self.assertGreater(wire_gap, 1.e-7)
        self.assertGreater(body_gap, 1.e-7)

    def test_default_tolerance_replays_complete_original_device_and_gap_chain(self):
        network = self.f.build_case('tiny_device_chain')
        self.assertEqual(self.device_ids(network), ['8267', '84B8', 'F099'])
        self.assertEqual(set(self.f.get('wire-ids', network)), {'F097', 'F159', 'F15A'})
        pairs = [{self.f.get('a', row)[0], self.f.get('b', row)[0]}
                 for row in self.f.get('gap-pairs', network) or []]
        self.assertIn({'F159', 'F15A'}, pairs)
        result = self.f.split(network)
        circuits = self.f.get('circuits', result)
        self.assertEqual(len(circuits), 1)
        self.assertEqual(set(self.f.get('devices', circuits[0])), {'F099', '84B8', '8267'})
        self.assertTrue(truth(self.f.get('complete', result)), self.f.get('issues', circuits[0]))

    def test_explicit_zero_device_tolerance_preserves_strict_missed_contact(self):
        network = self.f.build_case('tiny_device_chain', eps_device=0.)
        self.assertEqual(self.device_ids(network), [])
        self.assertEqual(self.f.get('wire-ids', network), ['F097'])
        self.assertFalse(self.f.get('gap-pairs', network))
        result = self.f.split(network)
        self.assertEqual(len(self.f.get('circuits', result)), 1)
        self.assertFalse(self.f.get('devices', self.f.get('circuits', result)[0]))

    def test_ze2_shared_contact_has_no_false_closed_circuit_and_keeps_real_branch(self):
        network = self.f.build_case('ze2_shared_contact')
        self.assertEqual(self.device_ids(network), ['84A4'])
        self.assertEqual(set(self.f.get('wire-ids', network)), {'F0A6', 'F36C', 'F0FE'})
        result = self.f.split(network)
        circuits = self.f.get('circuits', result)
        self.assertEqual(len(circuits), 1)
        self.assertIn('F0FE', self.f.get('wires', circuits[0]))
        codes = [str(self.f.get('code', issue)) for issue in self.f.get('issues', circuits[0]) or []]
        self.assertNotIn('CLOSED_CIRCUIT', codes)
        self.assertTrue(truth(self.f.get('complete', result)), codes)


if __name__ == '__main__':
    unittest.main()
