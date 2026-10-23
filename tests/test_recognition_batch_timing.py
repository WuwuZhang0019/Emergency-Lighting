"""Recognition preparation batch timings. Date: 2026-10-21.

Status: finite adapter accounting and output equivalence, not native CAD speed.
"""
import unittest

from autolisp_host import Symbol, truth
import test_simple_flow as simple


class RecognitionBatchTimingTests(unittest.TestCase):
    stages = ('NETWORK_ROLE_PREPARE', 'NETWORK_WIRE_INDEX', 'NETWORK_BLOCK_INDEX',
              'NETWORK_JUNCTION_INDEX', 'NETWORK_END_INDEX', 'NETWORK_GAP_INDEX',
              'NETWORK_ROOT_LINKS')

    def prepare(self, gap=False):
        self.f = simple.SimpleFlowTests()
        self.f.setUp()
        self.h, self.call, self.get = self.f.h, self.f.call, self.f.get
        self.f.gap_plan() if gap else self.f.plan()
        self.snapshot = self.call('EL:SimpleCollect', self.f.cfg)
        self.clock = 0
        old_getvar = self.h.builtins.get('GETVAR', lambda key: 0)
        self.h.builtins['GETVAR'] = lambda key: self.clock if key == 'MILLISECS' else old_getvar(key)
        for name, cost in (('EL:SpatialTree', 3), ('EL:FixedBlockRole', 2)):
            original = Symbol('TEST:BATCH-' + name.split(':')[1].upper())
            self.h.functions[original] = self.h.functions[Symbol(name.upper())]

            def measured(*args, function=original, advance=cost):
                self.clock += advance
                return self.h.call(function, list(args))

            self.h.builtins[name.upper()] = measured

    def build(self):
        self.h.frames[0]['*EL:DEVICECONTACTCACHE*'] = None
        self.h.frames[0]['*EL:DEVICETEMPLATECACHE*'] = None
        return self.call('EL:PerfCall', 'NETWORK_BUILD', Symbol('EL:SIMPLENETWORKBUILD'),
                         [self.snapshot, self.f.cfg, 'panel'])

    def assert_batch(self, gap):
        self.prepare(gap)
        baseline = self.build()
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))
        self.call('EL:PerfStart', 'ELSTAT')
        measured = self.build()
        self.assertEqual(measured, baseline)
        records = self.h.lookup('*EL:MONITORROWS*')
        parent = next(row for row in records if self.get('stage', row) == 'NETWORK_CANDIDATE_SCOPE')
        children = [row for row in records if self.get('parent-id', row) == self.get('id', parent)]
        self.assertEqual([self.get('stage', row) for row in reversed(children)], list(self.stages))
        self.assertEqual(len(children), 7)
        for row in children:
            self.assertEqual(self.get('status', row), Symbol('RETURNED'))
            self.assertGreaterEqual(self.get('program-ms', row), 0)
        role = next(row for row in children if self.get('stage', row) == 'NETWORK_ROLE_PREPARE')
        self.assertEqual(self.get('elapsed-ms', role), 2 * len(self.get('blocks', self.snapshot)))
        for stage in ('NETWORK_WIRE_INDEX', 'NETWORK_BLOCK_INDEX', 'NETWORK_JUNCTION_INDEX',
                      'NETWORK_END_INDEX', 'NETWORK_GAP_INDEX'):
            row = next(row for row in children if self.get('stage', row) == stage)
            self.assertEqual(self.get('elapsed-ms', row), 3, stage)
        self.assertEqual(bool(self.get('gap-pairs', measured)), gap)
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))

    def test_preparation_batches_preserve_t_branch_and_remote_source_records(self):
        self.assert_batch(False)

    def test_preparation_batches_preserve_real_virtual_gap_and_blocker_index(self):
        self.assert_batch(True)

    def test_failed_index_keeps_context_until_normal_error_unwind(self):
        self.prepare()
        original = self.h.builtins['EL:SPATIALTREE']
        calls = [0]

        def broken(*args):
            calls[0] += 1
            if calls[0] == 2:
                raise RuntimeError('fixture index failure')
            return original(*args)

        self.h.builtins['EL:SPATIALTREE'] = broken
        self.call('EL:PerfStart', 'ELSTAT')
        with self.assertRaisesRegex(RuntimeError, 'fixture index failure'):
            self.build()
        pending = self.h.lookup('*EL:PERFPENDING*')
        self.assertEqual([self.get('stage', row) for row in pending],
                         ['NETWORK_BLOCK_INDEX', 'NETWORK_CANDIDATE_SCOPE', 'NETWORK_BUILD'])
        self.call('EL:PerfUnwind', None)
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))
        failed = [row for row in self.h.lookup('*EL:MONITORROWS*')
                  if self.get('status', row) == Symbol('INTERRUPTED')]
        self.assertEqual(len(failed), 3)


if __name__ == '__main__':
    unittest.main()
