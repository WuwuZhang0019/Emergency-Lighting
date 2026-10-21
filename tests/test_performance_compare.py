"""Date: 2026-10-21. Four-mode controlled comparison and session-only controls.

Status: finite adapter equivalence and operation counts, not native CAD timing.
"""
import copy
import hashlib
import unittest

from autolisp_host import Host, Pair, Symbol, truth
from check_store_read_work import exact
import test_collect_read_timing as collect


def controlled_comparison(order=(3, 1, 2, 0, 0, 2, 1, 3)):
    """Fresh identical input/cache per run; reverse the order on the second pass."""
    collect.CollectReadTimingTests.setUpClass()
    rows, expected = [], None
    for mode in order:
        fixture = collect.CollectReadTimingTests()
        fixture.setUp()
        h, call, get = fixture.h, fixture.call, fixture.get
        h.builtins.pop('EL:COLLECTREADDETAILENABLED')
        h.frames[0]['*EL:PERFCOMPAREMODE*'] = mode
        call('EL:PerfStart', 'ELSTAT')
        before = fixture.ticks
        snapshot = call('EL:SimpleCollect', fixture.f.cfg)
        wire = call('EL:By', Symbol('ID'), 'w1', get('wires', snapshot))
        device = call('EL:By', Symbol('ID'), 'a', get('blocks', snapshot))
        assert wire and device
        shape = [Pair(Symbol('SEGMENTS'), call('EL:BoundsSegments', get('bounds', device)))]
        shapes = []
        def read_shape(block):
            shapes.append(get('id', block))
            return shape
        h.builtins['EL:DEVICECONTACTSHAPE'] = read_shape
        original_inputs = exact(copy.deepcopy((snapshot, fixture.f.cfg, shape)))
        boundary = call('EL:NumberFirstDevice', wire, 0., call('EL:NumberPathLength', wire),
                        [device], fixture.f.cfg)
        output = exact((snapshot, boundary, shapes))
        if expected is None:
            expected = output
        assert output == expected, ('business output differs', mode)
        assert exact((snapshot, fixture.f.cfg, shape)) == original_inputs
        metrics = h.lookup('*EL:PERFMETRICS*')
        def metric(key):
            return call('EL:Get', key, metrics)
        stages = h.lookup('*EL:PERFSTAGES*')
        entity_stage = call('EL:Get', 'COLLECT_ENTITY_READ', stages)
        detail, old_single = mode in (1, 3), mode in (2, 3)
        assert metric('recognition-compare-mode') == mode
        assert metric('source-read-profile-enabled') == int(detail)
        assert metric('source-read-profile-clock-reads') == (28 if detail else 0)
        assert metric('number-prefix-single-baseline') == int(old_single)
        assert metric('number-prefix-bounds-builds') == (33 if old_single else 0)
        assert metric('number-prefix-single-bypasses') == (0 if old_single else 33)
        assert metric('number-prefix-exact-tests') == (33 if not old_single else 33-metric('number-prefix-bounds-rejected'))
        assert get('program-ms', entity_stage) == 80
        rows.append({
            'mode': mode, 'detail_enabled': int(detail), 'single_bounds_baseline': int(old_single),
            'profile_clock_reads': metric('source-read-profile-clock-reads'),
            'all_collect_and_prefix_tick_calls': fixture.ticks-before,
            'entity_batch_synthetic_ms': get('program-ms', entity_stage),
            'prefix_builds': metric('number-prefix-bounds-builds'),
            'prefix_exact_tests': metric('number-prefix-exact-tests'),
            'prefix_single_bypasses': metric('number-prefix-single-bypasses'),
            'native_operation_sequence_sha256': hashlib.sha256(repr(exact(fixture.operations)).encode()).hexdigest(),
            'complete_output_sha256': hashlib.sha256(repr(output).encode()).hexdigest(),
            'boundary': boundary,
        })
    assert len({r['complete_output_sha256'] for r in rows}) == 1
    assert len({r['native_operation_sequence_sha256'] for r in rows}) == 1
    return rows


class PerformanceCompareTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        self.h.load_definitions(collect.ROOT / 'src/common.lsp')
        self.lines, self.reports = [], []
        self.h.builtins.update({
            'GETVAR': lambda key: 100 if key == 'MILLISECS' else 20261021.15,
            'PRINC': lambda *args: None,
            'VL-STRING-TRANSLATE': lambda old, new, value: value.translate(str.maketrans(old, new)),
            'EL:PERFREPORT': lambda summary: self.reports.append(summary),
            'EL:MONITORREPORT': lambda summary: None,
        })
        for name in ('ENTMOD', 'ENTMAKE', 'ENTMAKEX', 'ENTDEL', 'DICTADD', 'SETENV'):
            self.h.builtins[name] = lambda *args: self.fail('Comparison controls must not write')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def test_invalid_modes_default_to_optimized_and_flags_are_independent(self):
        for mode in (None, -1, 4, 1., '1', Symbol('BAD')):
            self.h.frames[0]['*EL:PERFCOMPAREMODE*'] = mode
            self.assertEqual(self.call('EL:PerformanceCompareMode'), 0)
        for mode in range(4):
            self.h.frames[0]['*EL:PERFCOMPAREMODE*'] = mode
            self.assertEqual(truth(self.call('EL:CollectReadDetailEnabled')), mode in (1, 3))
            self.assertEqual(truth(self.call('EL:NumberSingleBoundsEnabled')), mode in (2, 3))

    def test_run_mode_is_frozen_and_finish_preserves_it_in_summary(self):
        for mode in range(4):
            self.h.frames[0]['*EL:PERFCOMPAREMODE*'] = mode
            self.call('EL:PerfStart', 'ELSTAT')
            self.h.frames[0]['*EL:PERFCOMPAREMODE*'] = 3-mode
            self.assertEqual(self.call('EL:PerformanceCompareMode'), mode)
            self.assertFalse(truth(self.call('EL:PerfStart', 'nested')))
            self.call('EL:PerfFinish', Symbol('FAILED') if mode == 3 else Symbol('CANCELLED'))
            summary = self.reports[-1]
            metrics = self.call('EL:Get', Symbol('METRICS'), summary)
            self.assertEqual(self.call('EL:Get', 'recognition-compare-mode', metrics), mode)
            self.assertIsNone(self.h.lookup('*EL:PERFCOMPARERUNMODE*'))
            self.assertEqual(self.call('EL:PerformanceCompareMode'), 3-mode)

    def test_command_keeps_choice_on_enter_invalid_cancel_and_active_run(self):
        self.h.frames[0]['*EL:PERFCOMPAREMODE*'] = 2
        for option in (None, -1, 4, '1'):
            self.h.builtins['GETINT'] = lambda prompt, option=option: option
            self.call('C:ELPERFAB')
            self.assertEqual(self.call('EL:PerformanceCompareMode'), 2)
        self.h.builtins['GETINT'] = lambda prompt: 0
        self.call('C:ELPERFAB')
        self.assertEqual(self.call('EL:PerformanceCompareMode'), 0)
        def cancel(prompt):
            raise RuntimeError('Function cancelled')
        self.h.builtins['GETINT'] = cancel
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.call('C:ELPERFAB')
        self.assertEqual(self.call('EL:PerformanceCompareMode'), 0)
        self.call('EL:PerfStart', 'ELSTAT')
        self.h.builtins['GETINT'] = lambda *args: self.fail('No prompt during an active run')
        self.call('C:ELPERFAB')
        self.assertEqual(self.call('EL:PerformanceCompareMode'), 0)

    def test_timeline_labels_recorded_mode_instead_of_current_session_mode(self):
        self.h.frames[0]['*EL:MONITORSTAMP*'] = '20261021.150000'
        self.h.frames[0]['*EL:PERFCOMPAREMODE*'] = 0
        self.h.builtins['EL:MONITORLINE'] = lambda line, stream: self.lines.append(line)
        self.h.builtins['EL:MONITORTABLE'] = lambda *args: None
        summary = [Pair(Symbol(k), v) for k, v in {
            'STATUS':Symbol('COMMAND-FINISHED'), 'LAST-OUTCOME':Symbol('CANCELLED'),
            'COMMAND':'ELSTAT', 'PACKAGE':'test', 'TOTAL-MS':0, 'PROGRAM-MS':0,
            'INTERACTION-MS':0, 'METRICS':[Pair('recognition-compare-mode', 3)]}.items()]
        self.call('EL:MonitorWriteBody', None, summary)
        self.assertIn('识别对照模式：3；实体细分计时及旧单候选粗筛', self.lines)

    def test_four_modes_have_identical_inputs_outputs_and_independent_work_counts(self):
        rows = controlled_comparison()
        self.assertEqual(len(rows), 8)
        for mode in range(4):
            same = [r for r in rows if r['mode'] == mode]
            self.assertEqual(same[0], same[1])
        self.assertEqual(rows[0]['all_collect_and_prefix_tick_calls'] - rows[3]['all_collect_and_prefix_tick_calls'], 28)


if __name__ == '__main__':
    unittest.main()
