"""P0 timing/counter and command-flow checks. Date: 2026-10-13.

Synthetic clocks verify accounting only; these are not real CAD performance data.
"""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Host, Symbol, truth
from test_root_init import lisp_data
import test_cckk_panel_command as panel_flow

ROOT = Path(__file__).resolve().parents[1]


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        self.h.load_definitions(ROOT / 'src/common.lsp')
        self.clock = 0
        self.reports = []
        self.h.builtins.update({
            'GETVAR': lambda key: self.clock if key == 'MILLISECS' else 20261011.12,
            'EL:PERFREPORT': lambda summary: self.reports.append(summary),
        })

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, data):
        return self.call('EL:Get', Symbol(key.upper()), data)

    def metric(self, key):
        return self.call('EL:Get', key, self.h.lookup('*EL:PERFMETRICS*'))

    def test_nested_waits_are_a_union_and_stages_remain_inclusive(self):
        self.call('EL:PerfStart', 'ELSTAT')
        self.clock = 10
        outer = self.call('EL:PerfBegin', 'CCKK2')
        self.clock = 20
        wait = self.call('EL:PerfBegin', 'USER_INPUT')
        self.clock = 30
        nested = self.call('EL:PerfBegin', 'USER_INPUT')
        self.clock = 40
        self.call('EL:PerfEnd', nested, Symbol('RETURNED'))
        self.clock = 50
        self.call('EL:PerfEnd', wait, Symbol('RETURNED'))
        self.clock = 60
        self.call('EL:PerfEnd', outer, Symbol('RETURNED'))
        self.clock = 100
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        summary = self.reports[0]
        self.assertEqual(self.get('total-ms', summary), 100)
        self.assertEqual(self.get('interaction-ms', summary), 30)
        self.assertEqual(self.get('program-ms', summary), 70)
        stage = self.call('EL:Get', 'CCKK2', self.get('stages', summary))
        self.assertEqual(self.get('inclusive-ms', stage), 50)
        self.assertEqual(self.get('program-ms', stage), 20)

    def test_log_scope_does_not_reset_or_finish_its_top_command(self):
        self.assertTrue(truth(self.call('EL:PerfStart', 'ELSTAT')))
        self.h.frames[0]['*EL:PERFLOGSOFF*'] = True
        self.call('EL:PerfCount', 'store-read-calls', 2)
        self.clock = 10
        self.call('EL:LogStart')
        self.call('EL:LogFinish', Symbol('PANEL-CANCELLED'))
        self.assertEqual(self.metric('store-read-calls'), 2)
        self.assertTrue(truth(self.h.lookup('*EL:PERFACTIVE*')))
        self.assertEqual(self.reports, [])
        self.clock = 30
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.assertEqual(len(self.reports), 1)
        self.assertEqual(self.get('last-outcome', self.reports[0]), Symbol('PANEL-CANCELLED'))
        self.call('EL:PerfStart', 'ELSTAT')
        self.assertEqual(self.metric('store-read-calls'), 0)

    def test_native_values_nil_and_exceptions_are_preserved(self):
        self.call('EL:PerfStart', 'ELSTAT')
        calls = []
        self.h.builtins['WRITE-NIL'] = lambda *args: calls.append(args) and None
        self.assertIsNone(self.call('EL:PerfWrite', Symbol('WRITE-NIL'), ['e', 'x']))
        self.assertEqual(calls, [('e', 'x')])
        self.assertEqual(self.metric('entity-write-attempts'), 1)
        self.assertEqual(self.metric('entity-write-returned'), 1)

        def fail():
            self.clock = 20
            raise TypeError('original numberp: nil')

        self.h.builtins['WRITE-FAIL'] = fail
        with self.assertRaisesRegex(TypeError, 'original numberp: nil'):
            self.call('EL:PerfCall', 'TX_WRITE', Symbol('EL:PERFWRITE'), [Symbol('WRITE-FAIL'), None])
        self.assertEqual(self.metric('entity-write-attempts'), 2)
        self.assertEqual(self.metric('entity-write-returned'), 1)
        self.call('EL:PerfFinish', Symbol('FAILED'))
        stage = self.call('EL:Get', 'TX_WRITE', self.get('stages', self.reports[0]))
        self.assertEqual(self.get('interrupted', stage), 1)
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))

    def test_caught_cancel_unwinds_wait_before_following_work(self):
        self.call('EL:PerfStart', 'ELSTAT')
        outer = self.call('EL:PerfBegin', 'CCKK2')
        checkpoint = self.h.lookup('*EL:PERFPENDING*')
        self.clock = 10
        self.call('EL:PerfBegin', 'TX_WRITE')
        self.call('EL:PerfBegin', 'PLACEMENT_INPUT')
        self.clock = 100
        self.call('EL:PerfUnwind', checkpoint)
        self.assertEqual(self.h.lookup('*EL:PERFWAITDEPTH*'), 0)
        self.clock = 130
        self.call('EL:PerfEnd', outer, Symbol('RETURNED'))
        self.call('EL:PerfFinish', Symbol('CANCELLED'))
        self.assertEqual(self.get('interaction-ms', self.reports[0]), 90)
        self.assertEqual(self.get('program-ms', self.reports[0]), 40)

    def test_marks_report_after_submit_and_after_placement(self):
        self.call('EL:PerfStart', 'ELSTAT')
        self.clock = 10
        self.call('EL:PerfMark', 'panel-submit')
        self.clock = 20
        waiting = self.call('EL:PerfBegin', 'PLACEMENT_INPUT')
        self.clock = 80
        self.call('EL:PerfEnd', waiting, Symbol('RETURNED'))
        self.call('EL:PerfMark', 'placement-confirmed')
        self.clock = 100
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.assertEqual(self.get('program-ms', self.get('after-submit', self.reports[0])), 30)
        self.assertEqual(self.get('inclusive-ms', self.get('after-placement', self.reports[0])), 20)

    def test_two_preview_escapes_do_not_charge_later_generation_as_user_input(self):
        self.h.load_definitions(ROOT / 'src/panel.lsp')
        def escape(*args):
            self.clock += 100
            raise RuntimeError('Function cancelled')
        self.h.builtins.update({'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda _: 'doc',
            'VLA-STARTUNDOMARK': lambda _: None, 'VLA-ENDUNDOMARK': lambda _: None,
            'EL:COLORPREVIEWCLEANUP': lambda: True, 'GETSTRING': escape,
            'EL:ALLCIRCUITCOLORWAIT': lambda _: self.call('EL:PerfInput', Symbol('GETSTRING'), ['wait'])})
        self.call('EL:PerfStart', 'ELSTAT')
        outer = self.call('EL:PerfBegin', 'PANEL_DIALOG')
        for _ in range(2):
            self.call('EL:AllCircuitColorPreview', None)
            self.assertEqual(self.h.lookup('*EL:PERFWAITDEPTH*'), 0)
        self.call('EL:PerfEnd', outer, Symbol('RETURNED'))
        self.clock += 500
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.assertEqual(self.get('interaction-ms', self.reports[0]), 200)
        self.assertEqual(self.get('program-ms', self.reports[0]), 500)

    def test_signed_tick_rollover_is_not_reported_as_zero(self):
        self.clock = 2147483640
        self.call('EL:PerfStart', 'ELSTAT')
        self.clock = -2147483640
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.assertEqual(self.get('total-ms', self.reports[0]), 16)

    def test_detail_only_enables_selected_fine_stages(self):
        self.call('EL:PerfStart', 'ELSTAT')
        self.call('EL:PerfCall', 'SNAPSHOT_SIGNATURE', Symbol('+'), [1, 2])
        self.assertFalse(truth(self.h.lookup('*EL:PERFSTAGES*')))
        self.h.frames[0]['*EL:PERFDETAIL*'] = True
        self.call('EL:PerfCall', 'SNAPSHOT_SIGNATURE', Symbol('+'), [1, 2])
        self.call('EL:PerfCall', 'POLYLINE_TRANS', Symbol('+'), [1, 2])
        stages = self.h.lookup('*EL:PERFSTAGES*')
        self.assertTrue(truth(self.call('EL:Get', 'SNAPSHOT_SIGNATURE', stages)))
        self.assertIsNone(self.call('EL:Get', 'POLYLINE_TRANS', stages))

    def test_logs_off_still_emits_one_independent_readable_record(self):
        directory = ROOT / 'output/cad2020-perf-check'
        directory.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temp:
            root = Path(temp)
            self.h.builtins.pop('EL:PERFREPORT')
            handles = []

            def open_file(path, mode, *encoding):
                file = open(path, mode, encoding='utf-8')
                handles.append(file)
                return file

            self.h.builtins.update({
                'OPEN': open_file, 'CLOSE': lambda file: file.close(),
                'WRITE-LINE': lambda line, file: file.write(line + '\n'),
                'VL-MKDIR': lambda path: Path(path).mkdir(exist_ok=True),
                'VL-PRIN1-TO-STRING': lisp_data,
            })
            self.h.frames[0]['*EL:ROOT*'] = root.as_posix() + '/'
            self.h.frames[0]['*EL:PERFLOGSOFF*'] = True
            self.call('EL:LogStart')
            self.call('EL:LogCall', 'CCKK2', Symbol('CONTEXT'), Symbol('+'), [1, 2])
            self.call('EL:LogFinish', Symbol('COMMAND-FINISHED'))
            lines = (root / 'output/ELPERF.log').read_text(encoding='utf-8').splitlines()
            self.assertEqual(len(lines), 1)
            summary = self.h.builtins['READ'](lines[0].split(' | ', 1)[1])
            self.assertEqual(self.get('business-logs', summary), Symbol('OFF'))
            self.assertEqual(len(handles), 1)
            self.assertTrue(handles[0].closed)
            self.assertFalse((root / 'output/ELTRACE-debug.log').exists())

    def test_reporting_errors_do_not_replace_the_business_result(self):
        self.call('EL:PerfStart', 'ELSTAT')

        def fail_report(summary):
            raise PermissionError('report denied')

        self.h.builtins['EL:PERFREPORT'] = fail_report
        result = self.call('EL:PerfCall', 'CCKK2', Symbol('+'), [171, 1])
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.assertEqual(result, 172)
        self.assertFalse(truth(self.h.lookup('*EL:PERFACTIVE*')))
        self.assertTrue(truth(self.h.lookup('*EL:PERFLASTSUMMARY*')))


class PerformanceFlowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = panel_flow.PanelCommandTests()
        self.fixture.setUp()
        self.h = self.fixture.h
        self.clock = 0
        self.reports = []
        old_getvar = self.h.builtins['GETVAR']
        self.h.builtins.update({
            'GETVAR': lambda key: self.clock if key == 'MILLISECS' else old_getvar(key),
            'EL:PERFREPORT': lambda summary: self.reports.append(summary),
        })

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, record):
        return self.fixture.get(key, record)

    def test_real_managed_placement_marks_then_reads_and_counts_writes(self):
        command = self.h.builtins['COMMAND']

        def timed_command(*args):
            self.clock += 100 if args[-1] == 'pause' else 5
            return command(*args)

        self.h.builtins['COMMAND'] = timed_command
        self.call('EL:PerfStart', 'ELSTAT')
        self.assertTrue(truth(self.fixture.invoke()))
        mark = self.call('EL:Get', 'placement-confirmed', self.h.lookup('*EL:PERFMARKS*'))
        self.assertEqual(mark[0], 100)
        metrics = self.h.lookup('*EL:PERFMETRICS*')
        # Date: 2026-10-11. P2 confirms the committed actual readback directly.
        self.assertEqual(self.call('EL:Get', 'store-read-calls', metrics), 1)
        self.assertGreater(self.call('EL:Get', 'store-context-reuses', metrics), 0)
        self.assertEqual(self.call('EL:Get', 'master-write-attempts', metrics), 1)
        self.assertGreater(self.call('EL:Get', 'entity-write-attempts', metrics), 1)
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.assertEqual(self.get('interaction-ms', self.reports[0]), 100)

    def test_no_change_update_is_measured_with_zero_entity_and_master_writes(self):
        self.assertTrue(truth(self.fixture.invoke()))
        self.call('EL:PerfStart', 'ELSTAT')
        self.assertTrue(truth(self.fixture.invoke()))
        metrics = self.h.lookup('*EL:PERFMETRICS*')
        self.assertEqual(self.call('EL:Get', 'entity-write-attempts', metrics), 0)
        self.assertEqual(self.call('EL:Get', 'master-write-attempts', metrics), 0)
        self.assertGreater(self.call('EL:Get', 'store-read-calls', metrics), 0)

    def test_caught_native_cancel_stops_interaction_and_preserves_rollback(self):
        self.fixture.fail_at = 1
        command = self.h.builtins['COMMAND']

        def cancelled(*args):
            self.clock = 50
            return command(*args)

        self.h.builtins['COMMAND'] = cancelled
        self.call('EL:PerfStart', 'ELSTAT')
        self.assertFalse(truth(self.fixture.invoke()))
        self.assertEqual(self.h.lookup('*EL:PERFWAITDEPTH*'), 0)
        self.assertEqual(self.fixture.variables, self.fixture.original)
        metrics = self.h.lookup('*EL:PERFMETRICS*')
        self.assertEqual(self.call('EL:Get', 'transaction-failures', metrics), 1)
        self.clock = 80
        self.call('EL:PerfFinish', Symbol('CANCELLED'))
        self.assertEqual(self.get('interaction-ms', self.reports[0]), 50)
        self.assertEqual(self.get('program-ms', self.reports[0]), 30)


if __name__ == '__main__':
    unittest.main()
