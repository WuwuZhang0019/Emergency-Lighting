"""Date: 2026-10-22. Status: bounded panel-route diagnostic regression.

Uses the actual panel and finite declared DCL controls. Native visibility,
AutoCAD error dispatch and screen placement still need original-DWG testing.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol
import test_panel_library_toggle as toggle


class PanelLifecycleTests(unittest.TestCase):
    def fixture(self, home=True, expanded=False):
        f, callbacks, catalog, opened = toggle.PanelLibraryToggleTests.fixture(self, expanded)
        if home:
            f.result = None
        f.call('EL:PerfStart', 'ELSTAT')
        f.h.set('*EL:LOGACTIVE*', None)
        stages = []
        f.h.functions[Symbol('TEST:PANELLIFECYCLE')] = f.h.functions[Symbol('EL:PANELLIFECYCLE')]
        def lifecycle(stage, details):
            stages.append(stage)
            return f.call('TEST:PanelLifecycle', stage, details)
        f.h.builtins['EL:PANELLIFECYCLE'] = lifecycle
        return f, callbacks, catalog, opened, stages

    def metric(self, f, key):
        return f.call('EL:Get', 'panel-' + key, f.h.lookup('*EL:PERFMETRICS*'))

    def test_cancel_has_start_return_and_zero_status_in_both_layouts(self):
        for home in (True, False):
            for expanded in (False, True):
                with self.subTest(home=home, expanded=expanded):
                    f, callbacks, catalog, opened, stages = self.fixture(home, expanded)
                    before = copy.deepcopy(f.result)
                    catalog_before = catalog.read_bytes()
                    f.actions = [lambda: f.invoke_action(callbacks, 'cancel')]
                    self.assertIsNone(f.dialog())
                    self.assertEqual(stages, ['prepare', 'dcl-load-requested', 'dcl-load-returned',
                        'new-dialog-requested', 'new-dialog-returned', 'fill-requested',
                        'start-dialog-requested', 'start-dialog-returned', 'dialog-cleanup'])
                    self.assertEqual(opened[0][0], 'el_panel' if expanded else 'el_panel_compact')
                    self.assertEqual(self.metric(f, 'home'), True if home else None)
                    self.assertEqual(self.metric(f, 'return-status'), 0)
                    self.assertEqual(self.metric(f, 'final-status'), 0)
                    self.assertEqual(self.metric(f, 'start-dialog-count'), 1)
                    self.assertIsNone(self.metric(f, 'not-shown-reason'))
                    self.assertFalse(f.log.exists(), 'diagnostics enabled a business log before LogStart')
                    self.assertEqual(f.result, before)
                    self.assertEqual(catalog.read_bytes(), catalog_before)

    def test_failed_dcl_load_records_path_and_code_without_create_or_start(self):
        for code in (-1, -2):
            with self.subTest(code=code):
                f, _, _, opened, stages = self.fixture()
                f.h.builtins['LOAD_DIALOG'] = lambda path: code
                f.h.builtins['START_DIALOG'] = lambda: self.fail('started after DCL load failure')
                self.assertIsNone(f.dialog())
                self.assertEqual(opened, [])
                self.assertEqual(stages, ['prepare', 'dcl-load-requested', 'dcl-load-returned', 'dialog-cleanup'])
                self.assertEqual(self.metric(f, 'dialog-id'), code)
                self.assertEqual(self.metric(f, 'dcl-path'), f.h.lookup('*EL:ROOT*') + 'ui/power.dcl')
                self.assertEqual(self.metric(f, 'not-shown-reason'), 'dcl-load-failed')
                self.assertIsNone(self.metric(f, 'return-status'))
                self.assertIsNone(self.metric(f, 'start-dialog-count'))

    def test_failed_new_dialog_is_distinct_and_still_unloads_resource(self):
        f, _, _, _, stages = self.fixture()
        unloaded = []
        f.h.builtins['NEW_DIALOG'] = lambda *args: None
        f.h.builtins['UNLOAD_DIALOG'] = unloaded.append
        f.h.builtins['START_DIALOG'] = lambda: self.fail('started after new_dialog failure')
        self.assertIsNone(f.dialog())
        self.assertEqual(self.metric(f, 'not-shown-reason'), 'new-dialog-failed')
        self.assertEqual(self.metric(f, 'dialog-name'), 'el_panel_compact')
        self.assertIsNone(self.metric(f, 'new-dialog-ready'))
        self.assertIsNone(self.metric(f, 'start-dialog-count'))
        self.assertEqual(self.metric(f, 'final-status'), 0)
        self.assertEqual(unloaded, [1])
        self.assertNotIn('fill-requested', stages)

    def test_successful_retry_clears_the_previous_not_shown_reason(self):
        f, callbacks, _, _, _ = self.fixture()
        f.h.builtins['LOAD_DIALOG'] = lambda path: -1
        f.dialog()
        self.assertEqual(self.metric(f, 'not-shown-reason'), 'dcl-load-failed')
        f.h.builtins['LOAD_DIALOG'] = lambda path: 1
        f.actions = [lambda: f.invoke_action(callbacks, 'cancel')]
        f.dialog()
        self.assertIsNone(self.metric(f, 'not-shown-reason'))
        self.assertEqual(self.metric(f, 'dialog-id'), 1)
        self.assertEqual(self.metric(f, 'return-status'), 0)

    def test_elstat_root_failure_records_reason_without_panel_dispatch(self):
        f, _, _, opened, stages = self.fixture()
        f.h.builtins['EL:ENSUREROOT'] = lambda: None
        f.h.builtins['EL:PANELDIALOG'] = lambda *args: self.fail('dispatched without root')
        f.call('EL:FixedStat')
        self.assertEqual(opened, [])
        self.assertEqual(stages, ['command-entry', 'root-unavailable'])
        self.assertEqual(self.metric(f, 'entry'), 'ELSTAT')
        self.assertEqual(self.metric(f, 'not-shown-reason'), 'root-unavailable')

    def test_elstat_native_failures_replace_stale_export_context_and_keep_other_drawings(self):
        for reason in ('dcl-load-failed', 'new-dialog-failed'):
            with self.subTest(reason=reason):
                f, _, _, _, _ = self.fixture()
                owner = f.call('namedobjdict')
                previous = [Pair(Symbol('SUMMARY'), 'older-success')]
                other = [Pair(Symbol('SUMMARY'), 'other-drawing-success')]
                f.h.set('*EL:DIAGNOSTICRUNS*', [Pair(owner, previous), Pair('other-drawing', other)])
                f.h.set('*EL:PERFACTIVE*', None)
                if reason == 'dcl-load-failed':
                    f.h.builtins['LOAD_DIALOG'] = lambda path: -1
                else:
                    f.h.builtins['NEW_DIALOG'] = lambda *args: None
                f.call('EL:FixedStat')
                runs = f.h.lookup('*EL:DIAGNOSTICRUNS*')
                record = f.call('EL:Get', owner, runs)
                metrics = f.get('metrics', f.get('summary', record))
                self.assertEqual(f.call('EL:Get', 'panel-not-shown-reason', metrics), reason)
                self.assertEqual(f.call('EL:Get', 'other-drawing', runs), other)
                self.assertFalse(f.log.exists())

    def test_elstat_error_retains_last_panel_stage_and_original_message(self):
        f, _, _, _, stages = self.fixture()
        def fail_fill():
            raise TypeError('bad argument type: numberp: nil')
        f.h.builtins['EL:PANELHOMEFILL'] = fail_fill
        f.h.builtins['EL:RELEASEPOWERUI'] = lambda: None
        with self.assertRaisesRegex(TypeError, 'numberp: nil') as caught:
            f.call('EL:FixedStat')
        self.assertEqual(stages[-1], 'fill-requested')
        # The finite host requires explicit dispatch of AutoCAD's native error hook.
        f.call('*ERROR*', str(caught.exception))
        summary = f.h.lookup('*EL:PERFLASTSUMMARY*')
        metrics = f.get('metrics', summary)
        self.assertEqual(f.call('EL:Get', 'panel-error-at', metrics), 'fill-requested')
        self.assertEqual(f.call('EL:Get', 'panel-error', metrics), str(caught.exception))
        self.assertIsNone(f.call('EL:Get', 'panel-start-dialog-count', metrics))
        self.assertEqual(f.get('status', summary), Symbol('FAILED'))
        self.assertFalse(f.log.exists())


if __name__ == '__main__':
    unittest.main()
