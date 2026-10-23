"""Ordered circuit-start endpoint collection. Date: 2026-10-21.

Status: focused pure-source regression; operation counts are not CAD timings.
"""
from pathlib import Path
import unittest

from autolisp_host import Host, Pair, Symbol, seq

ROOT = Path(__file__).resolve().parents[1]


class StartSnapshotPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'geometry', 'simple', 'diagram-update'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        self.events = []
        self.clock = 0

        def tick(key):
            self.clock += 1
            return self.clock

        def abort():
            raise RuntimeError('native exit')

        self.h.builtins.update({'GETVAR': tick, 'EXIT': abort,
                               'EL:LOGEVENT': lambda stage, detail: self.events.append((stage, detail))})
        # Independent pre-optimization implementation, including validation and
        # excluded source geometry. No calls to the new endpoint construction.
        self.h.run('''(defun test:LegacyStartSnapshot
            (snapshot cfg panel / starts row wire ep ids kept removed ends)
          (setq starts (EL:Get 'circuit-starts cfg))
          (EL:Require (and starts (EL:CircuitStartsValid starts))
            "回路起始端记录无效，请重新拾取。")
          (foreach row starts
            (setq wire (EL:By 'id (EL:Get 'wire row) (EL:Get 'wires snapshot))
              ep (EL:By 'key (list (EL:Get 'wire row) (EL:Get 'end row)) (EL:Get 'ends wire)))
            (EL:Require (and wire ep (not (EL:Get 'issues wire))
              (equal (EL:Get 'point row) (EL:Get 'point ep) (EL:GapEpsilon)))
              "已选回路起始导线缺失、改变图层或起点已移动，请重新拾取。")
            (setq ids (cons (EL:Get 'wire row) ids)))
          (foreach wire (EL:Get 'wires snapshot)
            (if (and (not (member (EL:Get 'id wire) ids))
                (vl-some '(lambda (row)
                  (EL:Touches (EL:Get 'point row) (EL:Get 'segments wire)
                    (EL:Get 'eps_touch (EL:Get 'params cfg)) (EL:GapEpsilon))) starts))
              (setq removed (cons wire removed)) (setq kept (cons wire kept))))
          (setq kept (reverse kept))
          (foreach wire kept (setq ends (append ends (EL:Get 'ends wire))))
          (EL:Put 'circuit-starts starts (EL:Put 'start-boundary-source (reverse removed)
            (EL:Put 'wires kept (EL:Put 'ends ends snapshot)))))''')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, record):
        return self.call('EL:Get', Symbol(key.upper()), record)

    @staticmethod
    def row(**values):
        return [Pair(Symbol((key if key == 'eps_touch' else key.replace('_', '-')).upper()), value)
                for key, value in values.items()]

    def wire(self, name, x, ends=2):
        endpoints = [self.row(key=[name, Symbol('START' if i == 0 else 'END' if i == 1 else f'E{i}')],
                              point=[float(x+i), 0., 0.], extra=f'{name}-end-{i}')
                     for i in range(ends)]
        return self.row(id=name, segments=[[[float(x), 0., 0.], [float(x+10), 0., 0.]]],
                        ends=endpoints or None, extra=[name, 'keep-exact'])

    def fixture(self, wires=None):
        root = self.wire('root', 0)
        source = wires if wires is not None else [self.wire('removed-a', -10), root,
            self.wire('no-ends', 30, 0), self.wire('many-ends', 50, 4),
            self.wire('removed-b', 0), self.wire('tail', 70)]
        start = self.row(wire='root', end=Symbol('START'), point=[0., 0., 0.])
        cfg = self.row(circuit_starts=[start], params=self.row(eps_touch=0.01))
        snapshot = self.row(wires=source, ends=['stale-source-ends'],
                            blocks=[self.row(id='device', extra='keep')],
                            unknown_field=['opaque', self.row(value=17)])
        return snapshot, cfg

    def test_matches_original_order_exclusions_and_unknown_fields(self):
        snapshot, cfg = self.fixture()
        expected = self.call('TEST:LegacyStartSnapshot', snapshot, cfg, 'panel')
        actual = self.call('EL:StartSnapshot', snapshot, cfg, 'panel')
        self.assertEqual(actual, expected)
        self.assertEqual([self.get('id', w) for w in self.get('wires', actual)],
                         ['root', 'no-ends', 'many-ends', 'tail'])
        self.assertEqual([self.get('id', w) for w in self.get('start-boundary-source', actual)],
                         ['removed-a', 'removed-b'])
        self.assertEqual([self.get('extra', ep) for ep in self.get('ends', actual)],
                         ['root-end-0', 'root-end-1', 'many-ends-end-0', 'many-ends-end-1',
                          'many-ends-end-2', 'many-ends-end-3', 'tail-end-0', 'tail-end-1'])
        self.assertEqual(self.get('unknown-field', actual), self.get('unknown-field', snapshot))
        self.assertEqual(self.get('ends', snapshot), ['stale-source-ends'])

    def test_empty_nonroot_end_lists_do_not_create_entries(self):
        snapshot, cfg = self.fixture([self.wire('empty', 30, 0), self.wire('root', 0)])
        actual = self.call('EL:StartSnapshot', snapshot, cfg, 'panel')
        self.assertEqual(actual, self.call('TEST:LegacyStartSnapshot', snapshot, cfg, 'panel'))
        self.assertEqual(len(self.get('ends', actual)), 2)

    def test_invalid_missing_moved_or_issued_start_keeps_original_failure(self):
        snapshot, cfg = self.fixture()
        root = self.get('wires', snapshot)[1]
        cases = [('missing-config', snapshot, self.row(params=self.row(eps_touch=0.01))),
                 ('missing-wire', self.call('EL:Put', Symbol('WIRES'), [self.wire('else', 40)], snapshot), cfg),
                 ('moved-end', self.call('EL:Put', Symbol('WIRES'), [self.wire('root', 1)], snapshot), cfg),
                 ('missing-end', self.call('EL:Put', Symbol('WIRES'), [self.wire('root', 0, 0)], snapshot), cfg),
                 ('issued-wire', self.call('EL:Put', Symbol('WIRES'),
                     [self.call('EL:Put', Symbol('ISSUES'), ['changed-layer'], root)], snapshot), cfg)]
        for label, source, config in cases:
            with self.subTest(case=label):
                reasons = []
                for function in ('TEST:LegacyStartSnapshot', 'EL:StartSnapshot'):
                    self.events.clear()
                    with self.assertRaisesRegex(RuntimeError, 'native exit'):
                        self.call(function, source, config, 'panel')
                    reasons.append(self.events[:])
                self.assertEqual(reasons[0], reasons[1])

    def test_stage_nesting_and_batch_counts_with_no_pending_success_scope(self):
        snapshot, cfg = self.fixture()
        self.call('EL:PerfStart', 'ELSTAT')
        actual = self.call('EL:StartSnapshot', snapshot, cfg, 'panel')
        stages = self.h.lookup('*EL:PERFSTAGES*')
        for name in ('START_SNAPSHOT', 'START_BOUNDARY_FILTER', 'START_ENDS_BUILD'):
            stage = self.call('EL:Get', name, stages)
            self.assertEqual(self.get('calls', stage), 1)
            self.assertEqual(self.get('interrupted', stage), 0)
            if name != 'START_SNAPSHOT':
                self.assertEqual(self.get('parents', stage), ['START_SNAPSHOT'])
        metrics = self.h.lookup('*EL:PERFMETRICS*')
        for key, value in (('source-wires', 6), ('kept-wires', 4), ('removed-wires', 2), ('ends', 8)):
            self.assertEqual(self.call('EL:Get', f'start-snapshot-{key}', metrics), value)
        self.assertIsNone(self.h.lookup('*EL:PERFPENDING*'))
        self.assertEqual(actual, self.call('TEST:LegacyStartSnapshot', snapshot, cfg, 'panel'))

    def test_validation_error_parent_scope_can_be_unwound_without_changing_error(self):
        snapshot, cfg = self.fixture([self.wire('root', 1)])
        self.call('EL:PerfStart', 'ELSTAT')
        with self.assertRaisesRegex(RuntimeError, 'native exit'):
            self.call('EL:StartSnapshot', snapshot, cfg, 'panel')
        self.call('EL:PerfUnwind', None)
        stage = self.call('EL:Get', 'START_SNAPSHOT', self.h.lookup('*EL:PERFSTAGES*'))
        self.assertEqual(self.get('interrupted', stage), 1)
        self.assertIsNone(self.h.lookup('*EL:PERFPENDING*'))

    def test_large_batch_avoids_accumulated_endpoint_prefix_copying(self):
        count = 600
        snapshot, cfg = self.fixture([self.wire('root', 0)] +
                                    [self.wire(f'w{i}', 30+20*i) for i in range(count)])
        original_append = self.h.builtins['APPEND']
        original_cons = self.h.builtins['CONS']
        original_reverse = self.h.builtins['REVERSE']
        operations = {'append-prefix': 0, 'cons': 0, 'reverse-nodes': 0}

        def append(*values):
            # Native APPEND copies non-final list arguments. This counts logical
            # list nodes, not the Python host's list allocation or elapsed time.
            operations['append-prefix'] += sum(len(seq(value)) for value in values[:-1])
            return original_append(*values)

        def cons(a, b):
            operations['cons'] += 1
            return original_cons(a, b)

        def reverse(value):
            operations['reverse-nodes'] += len(seq(value))
            return original_reverse(value)

        self.h.builtins.update({'APPEND': append, 'CONS': cons, 'REVERSE': reverse})
        expected = self.call('TEST:LegacyStartSnapshot', snapshot, cfg, 'panel')
        legacy = operations.copy()
        for key in operations:
            operations[key] = 0
        actual = self.call('EL:StartSnapshot', snapshot, cfg, 'panel')
        self.assertEqual(actual, expected)
        self.assertEqual(len(self.get('ends', actual)), 2*(count+1))
        self.assertGreaterEqual(legacy['append-prefix'], count*(count+1))
        self.assertLess(operations['append-prefix'], 30)
        self.assertLess(sum(operations.values()), 10*(count+1))


if __name__ == '__main__':
    unittest.main()
