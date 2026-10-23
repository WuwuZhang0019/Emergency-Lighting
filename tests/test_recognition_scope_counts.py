"""Date: 2026-10-21. Raw selection, candidates and connected counts are distinct.

Status: frozen-source adapter regression; no native CAD speed acceptance.
"""
import copy
from pathlib import Path
import subprocess
import unittest

from autolisp_host import Pair, Symbol, parse
from check_store_read_work import exact
import test_simple_flow as simple
import test_freshness_reuse as fresh

ROOT = Path(__file__).resolve().parents[1]


def frozen(h, module, name, alias):
    text = subprocess.check_output(['git', 'show', f'f16fa0c:src/{module}.lsp'], cwd=ROOT).decode('utf-8')
    form = next(f for f in parse(text) if isinstance(f, list) and f[:2] == [Symbol('DEFUN'), Symbol(name.upper())])
    h.evaluate([form[0], Symbol(alias.upper()), *form[2:]])


class RecognitionScopeCountsTests(unittest.TestCase):
    def setUp(self):
        self.f = simple.SimpleFlowTests()
        self.f.setUp()
        self.f.plan()
        self.h, self.call, self.get = self.f.h, self.f.call, self.f.get
        self.h.builtins['CHR'] = chr
        self.cfg = self.call('EL:Put', Symbol('PRESET-SCOPED'), True, self.f.cfg)
        self.h.builtins['GETVAR'] = lambda key: 10 if key == 'MILLISECS' else 20261021.17
        self.events, self.native = [], []
        self.h.builtins['EL:LOGEVENT'] = lambda key, value: self.events.append((key, value))
        for name in ('ENTGET', 'EL:ENTITYBOUNDS'):
            original = self.h.builtins[name]
            def call(*args, name=name, original=original):
                self.native.append((name, copy.deepcopy(args)))
                return original(*args)
            self.h.builtins[name] = call
        frozen(self.h, 'simple', 'EL:SimpleCollect', 'oracle:ScopeCollect71')

    def metric(self, key):
        return self.call('EL:Get', key, self.h.lookup('*EL:PERFMETRICS*'))

    def collect(self, function='EL:SimpleCollect'):
        self.h.frames[0]['*EL:PERFACTIVE*'] = None
        self.call('EL:PerfStart', 'ELSTAT')
        self.events.clear()
        self.native.clear()
        return self.call(function, self.cfg)

    def test_selection_counts_and_native_order_match_frozen_complete_snapshot(self):
        expected = self.collect('oracle:ScopeCollect71')
        native = exact(self.native)
        actual = self.collect()
        self.assertEqual(exact(actual), exact(expected))
        self.assertEqual(exact(self.native), native)
        self.assertEqual(self.metric('source-selection-entities'), 7)
        self.assertEqual(self.metric('source-selection-inserts'), 4)
        self.assertEqual(self.metric('source-selection-lines'), 3)
        self.assertEqual(self.metric('source-selection-polylines'), 0)
        self.assertEqual(self.metric('source-selection-other'), 0)
        self.assertEqual(self.metric('source-candidate-blocks'), len(self.get('blocks', actual)))
        event = next(value for name, value in self.events if name == 'SOURCE_SELECTION_SCOPE')
        self.assertEqual(self.get('scope', event), Symbol('MODEL-SELECTION'))
        self.assertEqual(self.get('selected', event), 7)
        self.assertEqual(self.get('accepted-wire-records', event), 3)

    def test_polyline_is_one_native_object_and_rejections_remain_in_raw_selection(self):
        self.f.entities['poly'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'poly'), Pair(8, 'W'), Pair(70, 0),
                                  Pair(10, [200., 0.]), Pair(10, [210., 0.]), Pair(10, [210., 10.]),
                                  Pair(210, [0., 0., 1.]), Pair(410, 'Model')]
        self.f.block('WALL', 'ARCH', 'wall', [1000., 0., 0.])
        self.f.block('LAMP', 'D', 'managed', [2000., 0., 0.])
        self.f.entities['managed'].append([-3, ['EL_FIXED_V1', Pair(1000, 'output')]])
        self.f.line('wrong-layer', [3000., 0., 0.], [3010., 0., 0.], 'ARCH')
        # The finite selector intentionally returns a broader set than native _X.
        self.f.entities['text'] = [Pair(0, 'TEXT'), Pair(5, 'text'), Pair(8, 'ARCH')]
        self.f.selected += ['poly', 'wall', 'managed', 'wrong-layer', 'text']
        expected = self.collect('oracle:ScopeCollect71')
        native = exact(self.native)
        actual = self.collect()
        self.assertEqual(exact(actual), exact(expected))
        self.assertEqual(exact(self.native), native)
        for key, count in [('source-selection-entities', 12), ('source-selection-inserts', 6),
                           ('source-selection-lines', 4), ('source-selection-polylines', 1),
                           ('source-selection-other', 1), ('source-selection-managed-outputs', 1),
                           ('source-rejected-block-inserts', 1), ('source-wire-record-reads', 4)]:
            self.assertEqual(self.metric(key), count, key)
        poly = self.call('EL:By', Symbol('ID'), 'poly', self.get('wires', actual))
        self.assertEqual(len(self.get('segments', poly)), 2)
        self.assertEqual(self.metric('source-selection-polylines'), 1)
        self.assertEqual(self.metric('source-block-bounds-reads'), 4)

    def test_connected_result_counts_exclude_remote_candidates_without_changing_result(self):
        f = fresh.FreshnessReuseTests()
        f.setUp()
        frozen(f.h, 'diagram-update', 'EL:RecognizeFixed', 'oracle:ScopeRecognize71')
        f.h.builtins['GETVAR'] = lambda key: 10 if key == 'MILLISECS' else None
        f.call('EL:PerfStart', 'ELSTAT')
        before = f.call('oracle:ScopeRecognize71', f.f.cfg, 'panel')
        f.h.frames[0]['*EL:PERFACTIVE*'] = None
        f.call('EL:PerfStart', 'ELSTAT')
        after = f.result()
        self.assertEqual(exact(after), exact(before))
        metrics = f.h.lookup('*EL:PERFMETRICS*')
        value = lambda key: f.call('EL:Get', key, metrics)
        self.assertEqual(value('source-selection-entities'), 7)
        self.assertEqual(value('wire-count'), 3)
        self.assertEqual(value('block-count'), 4)
        self.assertEqual(value('recognized-connected-wires'), 2)
        self.assertEqual(value('recognized-connected-devices'), 2)
        self.assertEqual(value('source-read-profile-clock-reads'), 0)

    def test_counters_are_only_aggregates_and_add_no_per_entity_clocks(self):
        ticks = []
        original = self.h.functions[Symbol('EL:TICK')]
        self.h.functions[Symbol('TEST:SCOPE-TICK')] = original
        self.h.builtins['EL:TICK'] = lambda: ticks.append(1) or self.call('TEST:Scope-Tick')
        self.collect('oracle:ScopeCollect71')
        before = len(ticks)
        ticks.clear()
        self.collect()
        self.assertEqual(len(ticks), before)
        self.h.frames[0]['*EL:PERFACTIVE*'] = None
        ticks.clear()
        self.call('EL:SimpleCollect', self.cfg)
        self.assertEqual(ticks, [])


if __name__ == '__main__':
    unittest.main()
