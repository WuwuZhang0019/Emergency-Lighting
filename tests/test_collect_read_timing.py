"""Date: 2026-10-21. Collection-only aggregate read timing and scope.

Synthetic clocks check accounting; they do not measure native CAD speed.
"""
import unittest
from autolisp_host import Symbol, truth
import test_simple_flow as simple


class CollectReadTimingTests(unittest.TestCase):
    def setUp(self):
        self.f = simple.SimpleFlowTests()
        self.f.setUp()
        self.f.plan()
        self.h, self.call, self.get = self.f.h, self.f.call, self.f.get
        self.clock, self.ticks = 2**32 - 4, 0
        self.h.builtins['GETVAR'] = lambda key: self.clock if key == 'MILLISECS' else 20261021.14
        original_tick = self.h.functions[Symbol('EL:TICK')]
        self.h.functions[Symbol('TEST:TICK')] = original_tick
        def tick():
            self.ticks += 1
            return self.call('TEST:Tick')
        self.h.builtins['EL:TICK'] = tick
        reader = self.h.builtins['ENTGET']
        def read(*args):
            self.clock = (self.clock + 7) % 2**32
            return reader(*args)
        self.h.builtins['ENTGET'] = read
        self.h.builtins.pop('EL:ENTITYBOUNDS')
        def box(entity, lo, hi):
            self.clock = (self.clock + 4) % 2**32
            bounds = self.f.bounds[entity]
            self.h.set(lo, bounds[0])
            self.h.set(hi, bounds[1])
        self.h.builtins['VLA-GETBOUNDINGBOX'] = box
        self.h.builtins['VLAX-SAFEARRAY->LIST'] = lambda value: value
        self.h.functions[Symbol('TEST:SEGMENTS')] = self.h.functions[Symbol('EL:POLYLINESEGMENTS')]
        def segments(*args):
            self.clock = (self.clock + 5) % 2**32
            return self.call('TEST:Segments', *args)
        self.h.builtins['EL:POLYLINESEGMENTS'] = segments

    def metric(self, name):
        return self.call('EL:Get', name, self.h.lookup('*EL:PERFMETRICS*'))

    def test_actual_collect_output_and_aggregate_costs_match_with_clock_wrap(self):
        baseline = self.call('EL:SimpleCollect', self.f.cfg)
        self.assertEqual(self.ticks, 0)
        self.call('EL:PerfStart', 'ELSTAT')
        actual = self.call('EL:SimpleCollect', self.f.cfg)
        self.assertEqual(actual, baseline)
        self.assertEqual(self.metric('source-native-dxf-ms'), 7*len(self.f.selected))
        self.assertEqual(self.metric('source-block-bounds-ms'), 4*4)
        self.assertEqual(self.metric('source-wire-record-ms'), 5*3)
        self.assertEqual(self.metric('source-read-profile-clock-reads'), 2*(7+4+3))
        for name in ('READPROFILE', 'DXFMS', 'BOUNDSMS', 'WIREMS', 'PROFILEREADS'):
            self.assertIsNone(self.h.lookup('*EL:COLLECT'+name+'*'))
        before = self.metric('source-block-bounds-ms')
        self.call('EL:EntityBounds', 'panel')
        self.assertEqual(self.metric('source-block-bounds-ms'), before)

    def test_disabled_collection_does_not_read_profile_clock_or_leak_scope(self):
        self.call('EL:SimpleCollect', self.f.cfg)
        self.assertEqual(self.ticks, 0)
        self.assertIsNone(self.h.lookup('*EL:PERFMETRICS*'))
        self.assertIsNone(self.h.lookup('*EL:COLLECTREADPROFILE*'))

    def test_native_read_exception_keeps_original_failure_and_restores_scope(self):
        self.call('EL:PerfStart', 'ELSTAT')
        self.h.builtins['ENTGET'] = lambda *args: (_ for _ in ()).throw(RuntimeError('native read failed'))
        with self.assertRaisesRegex(RuntimeError, 'native read failed'):
            self.call('EL:SimpleCollect', self.f.cfg)
        self.assertIsNone(self.h.lookup('*EL:COLLECTREADPROFILE*'))
        self.assertIsNone(self.h.lookup('*EL:COLLECTDXFMS*'))
        self.call('EL:PerfUnwind', None)
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))


if __name__ == '__main__':
    unittest.main()
