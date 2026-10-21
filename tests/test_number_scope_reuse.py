"""Date: 2026-10-21. Frozen pre-change numbering equivalence and bounded work.

Runs actual LISP in the bounded host; operation counts are not native CAD timing.
"""
from collections import Counter
import copy
import unittest

from autolisp_host import Pair, Symbol
from check_store_read_work import exact
import test_simple_flow as simple


# Frozen from dfe856f, before the local reuse changes. Only the name differs.
LEGACY_SCOPE = r"""
(defun oracle:ExitNumberScopeImpl (seed network cfg / snapshot panel wires edges root start queue visited step id entry wire devices
    next other left right low high link links sources boundaries ranges issues source)
  (setq snapshot (EL:Get 'snapshot network) panel (EL:By 'id (EL:Get 'panel network) (EL:Get 'blocks snapshot))
    wires (EL:Get 'wires snapshot) edges (EL:Get 'edges network)
    root (EL:By 'id (EL:Get 'wire seed) wires) start (EL:NumberRootStation root snapshot cfg panel))
  (if (not start) (setq issues (list (EL:Issue 'NUMBER_EXIT_DIRECTION (EL:Get 'wire seed) nil)))
    (setq queue (list (list (EL:Get 'wire seed) (car start)))))
  (while queue
    (setq step (car queue) queue (cdr queue) id (car step) entry (cadr step))
    (if (not (vl-some '(lambda (old) (and (equal id (car old)) (equal entry (cadr old) (EL:GapEpsilon)))) visited))
      (progn
        (setq visited (cons step visited) wire (EL:By 'id id wires)
          source (cond ((EL:Get 'source-wire wire)) (T id)) sources (cons source sources)
          devices nil)
        (foreach next (EL:Neighbours id edges)
          (if (and (not (equal next (EL:Get 'panel network)))
              (setq other (EL:By 'id next (EL:Get 'blocks snapshot)))) (setq devices (cons other devices))))
        (setq left (EL:NumberFirstDevice wire entry 0.0 devices cfg)
          right (EL:NumberFirstDevice wire entry (EL:NumberPathLength wire) devices cfg)
          low (if left (car left) 0.0) high (if right (car right) (EL:NumberPathLength wire)))
        (if left (setq boundaries (cons (cadr left) boundaries)))
        (if right (setq boundaries (cons (cadr right) boundaries)))
        (setq ranges (cons (list id entry low high) ranges))
        (foreach next (EL:Neighbours id edges)
          (if (setq other (EL:By 'id next wires))
            (progn
              (setq links (EL:NumberLinks wire other network cfg))
              (if (not links) (setq issues (cons (EL:Issue 'NUMBER_CONNECTION_POSITION id next) issues)))
              (foreach link links
                (if (and (if left (> (car link) (+ low (EL:GapEpsilon))) (>= (car link) low))
                    (if right (< (car link) (- high (EL:GapEpsilon))) (<= (car link) high)))
                  (setq queue (append queue (list (list next (cadr link)))))))))))))
  (list (cons 'status (if issues 'path-ambiguous 'ready)) (cons 'sources (EL:Unique (reverse sources)))
    (cons 'boundaries (EL:Unique (reverse boundaries))) (cons 'ranges (reverse ranges)) (cons 'issues issues)))
"""


def pair(key, value):
    return Pair(Symbol(key.upper()), value)


class NumberScopeReuseTests(unittest.TestCase):
    def setUp(self):
        self.f = simple.SimpleFlowTests()
        self.f.setUp()
        self.h = self.f.h
        self.call, self.get = self.f.call, self.f.get
        self.h.run(LEGACY_SCOPE)

    def put(self, key, value, data):
        return self.call('EL:Put', Symbol(key.upper()), value, data)

    def compare(self, wire, network=None):
        network = network if network is not None else self.f.network()
        before = copy.deepcopy(network)
        seed = [pair('wire', wire)]
        old = self.call('oracle:ExitNumberScopeImpl', seed, network, self.f.cfg)
        new = self.call('EL:ExitNumberScopeImpl', seed, network, self.f.cfg)
        self.assertEqual(exact(new), exact(old))
        self.assertEqual(exact(network), exact(before))
        return new

    def test_frozen_full_scope_branches_reverse_ties_and_virtual_sources(self):
        for kind in ('branch', 'reverse', 'tie', 'virtual'):
            with self.subTest(kind=kind):
                self.setUp()
                self.f.plan()
                self.f.line('next', [4., 0., 0.], [9., 0., 0.], 'W')
                self.f.line('w1', [4., 0., 0.] if kind == 'reverse' else [1., 0., 0.],
                            [1., 0., 0.] if kind == 'reverse' else [4., 0., 0.], 'W')
                self.f.selected.append('next')
                if kind == 'branch':
                    self.f.block('LAMP', 'D', 'late', [15., 10., 0.])
                    self.f.line('late-wire', [15., 0., 0.], [15., 9., 0.], 'W')
                    self.f.selected += ['late', 'late-wire']
                if kind == 'tie':
                    self.f.block('LAMP', 'D', 'tie', [10., 0., 0.])
                    self.f.selected.append('tie')
                network = self.f.network()
                if kind == 'virtual':
                    snapshot = self.get('snapshot', network)
                    wires = [self.put('source-wire', 'original', w) if self.get('id', w) == 'w1' else w
                             for w in self.get('wires', snapshot)]
                    network = self.put('snapshot', self.put('wires', wires, snapshot), network)
                self.compare('w1', network)

    def test_frozen_full_scope_gap_stops_crossing_and_missing_direction(self):
        for kind in ('gap', 'early-device', 'crossing', 'ambiguous'):
            with self.subTest(kind=kind):
                self.setUp()
                if kind in ('gap', 'early-device'):
                    self.f.gap_plan()
                    seed = 'before'
                    if kind == 'early-device':
                        self.f.block('LAMP', 'D', 'early', [5., 0., 0.])
                        self.f.selected.append('early')
                else:
                    self.f.plan()
                    seed = 'w1'
                    if kind == 'ambiguous':
                        self.f.line('w1', [-5., 0., 0.], [9., 0., 0.], 'W')
                    else:
                        self.f.line('cross', [3., -10., 0.], [3., 10., 0.], 'W')
                        self.f.selected.append('cross')
                self.compare(seed)

    def chain(self, count=6):
        wires = [[pair('id', f'w{i}'), pair('segments', [[[float(i), 0., 0.], [float(i+1), 0., 0.]]])]
                 for i in range(count)]
        snapshot = [pair('wires', wires), pair('blocks', None),
                    pair('circuit-starts', [[pair('wire', 'w0'), pair('end', Symbol('START'))]])]
        return [pair('snapshot', snapshot), pair('panel', 'panel'),
                pair('edges', [[f'w{i}', f'w{i+1}'] for i in range(count-1)])]

    def observed(self, function, network):
        counts = Counter()
        original = self.h.call
        def observe(name, args):
            if name in ('EL:NEIGHBOURS', 'EL:NUMBERPATHLENGTH'):
                counts[name] += 1
            return original(name, args)
        self.h.call = observe
        try:
            result = self.call(function, [pair('wire', 'w0')], network, self.f.cfg)
        finally:
            self.h.call = original
        return result, counts

    def test_neighbour_and_length_work_halved_with_same_result(self):
        network = self.chain()
        old, old_counts = self.observed('oracle:ExitNumberScopeImpl', network)
        new, new_counts = self.observed('EL:ExitNumberScopeImpl', network)
        visits = len(self.get('ranges', new))
        self.assertGreater(visits, 1)
        self.assertEqual(exact(new), exact(old))
        for operation in ('EL:NEIGHBOURS', 'EL:NUMBERPATHLENGTH'):
            self.assertEqual(old_counts[operation], visits * 2)
            self.assertEqual(new_counts[operation], visits)

    def test_disabled_profile_never_reads_clock_and_enabled_flushes_once(self):
        network = self.chain()
        clock = [2**32 - 2]
        reads = []
        def tick():
            clock[0] = (clock[0] + 1) % 2**32
            reads.append(clock[0])
            return clock[0]
        self.h.builtins['EL:TICK'] = tick
        self.compare('w0', network)
        self.assertEqual(reads, [])
        self.h.frames[0]['*EL:PERFACTIVE*'] = True
        flushed = []
        original = self.h.call
        def observe(name, args):
            # Date: 2026-10-21. Prefix searches now publish their own batches;
            # this assertion counts the six scope-level aggregates only.
            if name == 'EL:PERFCOUNT' and args[0].startswith('number-scope-'):
                flushed.append(args[0])
            return original(name, args)
        self.h.call = observe
        try:
            result = self.call('EL:ExitNumberScopeImpl', [pair('wire', 'w0')], network, self.f.cfg)
        finally:
            self.h.call = original
        self.assertEqual(len(flushed), 6)
        self.assertEqual(len(set(flushed)), 6)
        visits = len(self.get('ranges', result))
        metrics = self.h.lookup('*EL:PERFMETRICS*')
        self.assertEqual(len(reads), visits * 4)
        for key in ('number-scope-visits', 'number-scope-neighbour-scans', 'number-scope-path-lengths',
                    'number-scope-neighbours-ms', 'number-scope-first-device-ms', 'number-scope-links-ms'):
            self.assertEqual(self.call('EL:Get', key, metrics), visits)
        self.assertIsNone(self.h.lookup('*EL:PERFSTAGES*'))
        self.assertIsNone(self.h.lookup('*EL:PERFPENDING*'))

    def test_first_device_failure_still_precedes_path_length_and_is_reported(self):
        seen = []
        def fail(*args):
            seen.append('first-device')
            raise RuntimeError('first-device-test-failure')
        self.h.builtins['EL:NUMBERFIRSTDEVICE'] = fail
        self.h.builtins['EL:NUMBERPATHLENGTH'] = lambda *args: self.fail('length evaluated before left result')
        result = self.call('EL:ExitNumberScope', [pair('wire', 'w0')], self.chain(), self.f.cfg)
        self.assertEqual(seen, ['first-device'])
        self.assertEqual(self.get('status', result), Symbol('INVALID'))
        self.assertEqual(self.get('code', self.get('issues', result)[0]), Symbol('NUMBER_SCOPE_FAILED'))


if __name__ == '__main__':
    unittest.main()
