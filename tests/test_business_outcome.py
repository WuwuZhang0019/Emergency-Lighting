"""Date: 2026-10-21. Business outcomes and association scope; native CAD pending."""
import copy
from pathlib import Path
import unittest

from autolisp_host import Host, Pair, Symbol

ROOT = Path(__file__).resolve().parents[1]


class BusinessOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        self.h.load_definitions(ROOT / 'src/common.lsp')
        self.h.load_definitions(ROOT / 'src/diagram-commands.lsp')
        self.reports = []
        self.h.builtins.update({
            'GETVAR': lambda name: 0 if name == 'MILLISECS' else 20261021.123456,
            'NAMEDOBJDICT': lambda: 'drawing-a',
            'EL:PERFREPORT': lambda summary: self.reports.append(summary),
            'EL:MONITORREPORT': lambda summary: None,
            'EL:ENSUREROOT': lambda: True,
            'EL:LOGATTACH': lambda: None,
            'EL:CLEARGAPPREVIEW': lambda: None,
            'EL:CLEARPICKHIGHLIGHTS': lambda: None,
            'EL:STARTPICKRETURN': lambda: None,
            'PRINC': lambda *args: None,
        })
        self.h.set('*EL:PERFLOGSOFF*', True)

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, data):
        return self.call('EL:Get', Symbol(key.upper()), data)

    def finish(self, status='COMMAND-FINISHED'):
        self.call('EL:PerfFinish', Symbol(status))
        return self.h.lookup('*EL:PERFLASTSUMMARY*')

    def run_pick_error(self, message):
        def interrupted():
            self.call('EL:PerfBegin', 'SIMPLE_NETWORK')
            raise RuntimeError(message)
        self.h.builtins['EL:STARTPICKRUN'] = interrupted
        self.call('EL:PerfStart', 'ELSTAT')
        self.h.set('*EL:DIAGNOSTICSDEFERRED*', True)
        self.call('EL:FixedStartPick')
        return self.finish()

    def test_actual_caught_cancel_then_native_return_keeps_cancelled(self):
        summary = self.run_pick_error('函数已取消')
        self.assertEqual(self.get('status', summary), Symbol('COMMAND-FINISHED'))
        self.assertEqual(self.get('command-status', summary), Symbol('COMMAND-FINISHED'))
        self.assertEqual(self.get('business-outcome', summary), Symbol('CANCELLED'))
        self.assertEqual(self.get('last-outcome', summary), Symbol('CANCELLED'))
        run = self.call('EL:Get', 'drawing-a', self.h.lookup('*EL:DIAGNOSTICRUNS*'))
        self.assertEqual(self.get('error', run), '函数已取消')
        self.assertEqual(self.get('summary', run), summary)
        self.assertEqual(self.get('status', self.get('rows', run)[0]), Symbol('INTERRUPTED'))

    def test_actual_caught_failure_then_native_return_keeps_failed(self):
        summary = self.run_pick_error('bad argument type: numberp nil')
        self.assertEqual(self.get('last-outcome', summary), Symbol('FAILED'))
        self.assertEqual(self.get('status', summary), Symbol('COMMAND-FINISHED'))

    def test_known_native_cancel_messages_and_validation_abort_differ(self):
        for message in ('Function cancelled', '*Function canceled*', 'Console break', '函数已取消'):
            self.assertTrue(self.call('EL:CancelledMessage', message), message)
        self.assertFalse(self.call('EL:CancelledMessage', 'quit / exit abort'))
        self.assertFalse(self.call('EL:CancelledMessage', 'cancel setting is invalid'))

    def test_native_return_without_business_evidence_is_not_success(self):
        self.call('EL:PerfStart', 'ELSTAT')
        self.call('EL:LogFinish', Symbol('COMMAND-FINISHED'))
        self.assertEqual(self.get('last-outcome', self.finish()), Symbol('NOT-RECORDED'))

    def test_explicit_failure_after_a_successful_stage_is_failed(self):
        self.call('EL:PerfStart', 'ELGEN')
        self.call('EL:LogFinish', Symbol('RESULT-READY'))
        self.assertEqual(self.get('last-outcome', self.finish('FAILED')), Symbol('FAILED'))

    def test_cancelled_is_preserved_by_a_generic_failed_error_wrapper(self):
        self.call('EL:PerfStart', 'ELSTAT')
        self.call('EL:LogFailure', 'Function cancelled')
        self.assertEqual(self.get('last-outcome', self.finish('FAILED')), Symbol('CANCELLED'))

    def remember_success(self):
        record = [Pair(Symbol('DIAGRAM-ID'), 'old-diagram'),
                  Pair(Symbol('SOURCE-PANEL-HANDLE'), 'old-box')]
        self.call('EL:PerfStart', 'ELSTAT')
        self.h.set('*EL:DIAGNOSTICSDEFERRED*', True)
        self.call('EL:RememberDiagramDiagnostic', record, None)
        return record, self.finish()

    def test_successful_association_is_scoped_to_its_exact_run(self):
        record, summary = self.remember_success()
        metadata = self.call('EL:DiagnosticRunMetadata', record,
                             [Pair(Symbol('SUMMARY'), summary)])
        self.assertEqual(self.get('association-scope', metadata), Symbol('CURRENT-RUN-GENERATED'))
        self.assertTrue(self.get('association-current-run', metadata))
        self.assertEqual(self.get('association-run-id', metadata), self.get('run-id', summary))
        self.assertEqual(self.get('run-business-outcome', metadata), Symbol('DIAGRAM-GENERATED'))

    def test_old_verified_association_does_not_become_cancelled_runs_output(self):
        record, old_summary = self.remember_success()
        before = copy.deepcopy(self.h.lookup('*EL:DIAGRAMDIAGNOSTICS*'))
        summary = self.run_pick_error('函数已取消')
        # Both synthetic runs start at the same clock/CDATE. The sequence must distinguish them.
        self.assertNotEqual(self.get('run-id', summary), self.get('run-id', old_summary))
        metadata = self.call('EL:DiagnosticRunMetadata', record,
                             [Pair(Symbol('SUMMARY'), summary)])
        self.assertEqual(self.get('run-business-outcome', metadata), Symbol('CANCELLED'))
        self.assertEqual(self.get('association-scope', metadata), Symbol('RECENT-SUCCESS-OR-SELECTED'))
        self.assertFalse(self.get('association-current-run', metadata))
        self.assertEqual(self.get('association-run-id', metadata), self.get('run-id', old_summary))
        self.assertEqual(self.h.lookup('*EL:DIAGRAMDIAGNOSTICS*'), before)

    def test_old_unidentified_and_missing_associations_never_claim_current_run(self):
        self.call('EL:PerfStart', 'ELSTAT')
        summary = self.finish()
        for record, scope in (([Pair(Symbol('DIAGRAM-ID'), 'selected')], 'RECENT-SUCCESS-OR-SELECTED'),
                              (None, 'UNAVAILABLE')):
            metadata = self.call('EL:DiagnosticRunMetadata', record,
                                 [Pair(Symbol('SUMMARY'), summary)])
            self.assertEqual(self.get('association-scope', metadata), Symbol(scope))
            self.assertFalse(self.get('association-current-run', metadata))
            self.assertFalse(self.get('association-run-id', metadata))


    def test_bundle_manifest_labels_old_association_separately_from_cancelled_run(self):
        record, _ = self.remember_success()
        summary = self.run_pick_error('函数已取消')
        data, texts = {}, {}
        variables = {'CDATE': 20261021.123456, 'TEMPPREFIX': 'temp/',
                     'DWGNAME': 'test.dwg', 'DWGPREFIX': 'drawings/', 'ACADVER': '23.1'}
        self.h.builtins.update({
            'GETVAR': lambda name: variables[name],
            'EL:DIAGNOSTICFOLDER': lambda: 'snapshot',
            'EL:DIAGNOSTICWINDOWSPATH': lambda path: path,
            'EL:DIAGNOSTICPROGRESS': lambda *args: None,
            'EL:DIAGNOSTICWRITEDATA': lambda path, value: data.__setitem__(path, value),
            'EL:DIAGNOSTICWRITETEXT': lambda path, value: texts.__setitem__(path, value),
            'FINDFILE': lambda path: None,
        })
        self.h.set('*EL:ROOT*', 'root/')
        self.call('EL:DiagnosticBundle', record, None, None, None)
        metadata = data['snapshot/manifest.eld']
        self.assertEqual(self.get('association-status', metadata), Symbol('VERIFIED'))
        self.assertEqual(self.get('run-business-outcome', metadata), Symbol('CANCELLED'))
        self.assertEqual(self.get('run-command-status', metadata), Symbol('COMMAND-FINISHED'))
        self.assertEqual(self.get('association-scope', metadata), Symbol('RECENT-SUCCESS-OR-SELECTED'))
        self.assertFalse(self.get('association-current-run', metadata))
        self.assertEqual(data['snapshot/association.eld'], record)
        self.assertEqual(self.get('summary', data['snapshot/run.eld']), summary)
        self.assertIn('VERIFIED 不证明本轮识别或生成成功', texts['snapshot/README.md'])


if __name__ == '__main__':
    unittest.main()
