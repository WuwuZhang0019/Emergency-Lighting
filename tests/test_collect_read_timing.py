"""Date: 2026-10-21. Collection-only aggregate read timing and scope.

Synthetic clocks check accounting; they do not measure native CAD speed.
"""
import subprocess
import unittest
from pathlib import Path

from autolisp_host import Symbol, parse, truth
import test_simple_flow as simple


ROOT = Path(__file__).resolve().parents[1]


class CollectReadTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Frozen v0.1.70 path, without checking out or rewriting any source.
        source = subprocess.check_output(
            ['git', 'show', '730c9bd:src/simple.lsp'], cwd=ROOT).decode('utf-8')
        cls.legacy_collect = next(form for form in parse(source)
                                  if isinstance(form, list)
                                  and form[:2] == [Symbol('DEFUN'), Symbol('EL:SIMPLECOLLECT')])

    def setUp(self):
        self.f = simple.SimpleFlowTests()
        self.f.setUp()
        self.f.plan()
        self.h, self.call, self.get = self.f.h, self.f.call, self.f.get
        self.h.evaluate([self.legacy_collect[0], Symbol('ORACLE:COLLECT70'), *self.legacy_collect[2:]])
        self.detail = False
        self.operations = []
        # Common's four-mode selection has its own integration regression.
        self.h.builtins['EL:COLLECTREADDETAILENABLED'] = lambda: self.detail
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
            self.operations.append(("entget", args))
            self.clock = (self.clock + 7) % 2**32
            return reader(*args)
        self.h.builtins['ENTGET'] = read
        self.h.builtins.pop('EL:ENTITYBOUNDS')
        def box(entity, lo, hi):
            self.operations.append(("bounds", entity))
            self.clock = (self.clock + 4) % 2**32
            bounds = self.f.bounds[entity]
            self.h.set(lo, bounds[0])
            self.h.set(hi, bounds[1])
        self.h.builtins['VLA-GETBOUNDINGBOX'] = box
        self.h.builtins['VLAX-SAFEARRAY->LIST'] = lambda value: value
        self.h.functions[Symbol('TEST:SEGMENTS')] = self.h.functions[Symbol('EL:POLYLINESEGMENTS')]
        def segments(*args):
            self.operations.append(("segments", args))
            self.clock = (self.clock + 5) % 2**32
            return self.call('TEST:Segments', *args)
        self.h.builtins['EL:POLYLINESEGMENTS'] = segments

    def metric(self, name):
        return self.call('EL:Get', name, self.h.lookup('*EL:PERFMETRICS*'))

    def test_actual_collect_output_and_aggregate_costs_match_with_clock_wrap(self):
        baseline = self.call('EL:SimpleCollect', self.f.cfg)
        self.assertEqual(self.ticks, 0)
        self.detail = True
        self.call('EL:PerfStart', 'ELSTAT')
        actual = self.call('EL:SimpleCollect', self.f.cfg)
        self.assertEqual(actual, baseline)
        self.assertEqual(self.metric('source-read-profile-enabled'), 1)
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
        self.detail = True
        self.call('EL:SimpleCollect', self.f.cfg)
        self.assertEqual(self.ticks, 0)
        self.assertIsNone(self.h.lookup('*EL:PERFMETRICS*'))
        self.assertIsNone(self.h.lookup('*EL:COLLECTREADPROFILE*'))

    def test_default_and_detail_match_frozen_v70_native_operations_and_batch_frames(self):
        rows = []
        for function, detail in (('ORACLE:Collect70', False),
                                 ('EL:SimpleCollect', True), ('EL:SimpleCollect', False)):
            self.detail = detail
            self.h.frames[0]['*EL:PERFACTIVE*'] = None
            self.call('EL:PerfStart', 'ELSTAT')
            self.operations.clear()
            before = self.ticks
            result = self.call(function, self.f.cfg)
            rows.append((result, list(self.operations), self.ticks-before,
                         self.h.lookup('*EL:PERFSTAGES*')))
            if function == 'EL:SimpleCollect':
                self.assertEqual(self.metric('source-read-profile-enabled'), int(detail))
                self.assertEqual(self.metric('source-read-profile-clock-reads'), 28 if detail else 0)
                if not detail:
                    for metric in ('source-native-dxf-ms', 'source-block-bounds-ms',
                                   'source-wire-record-ms'):
                        self.assertEqual(self.metric(metric), 0)
                stage = self.call('EL:Get', 'COLLECT_ENTITY_READ', self.h.lookup('*EL:PERFSTAGES*'))
                self.assertEqual(self.get('calls', stage), 1)
                self.assertEqual(self.get('program-ms', stage), 80)
        for row in rows[1:]:
            self.assertEqual(row[:2], rows[0][:2])
            self.assertEqual(row[3], rows[0][3])
        self.assertEqual(rows[0][2], rows[1][2])
        self.assertEqual(rows[0][2] - rows[2][2], 28)
        self.assertGreater(rows[2][2], 0, 'batch stage clocks must remain active')

    def test_native_read_exception_keeps_original_failure_and_restores_scope(self):
        for detail in (False, True):
            with self.subTest(detail=detail):
                self.detail = detail
                self.h.frames[0]['*EL:PERFACTIVE*'] = None
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
