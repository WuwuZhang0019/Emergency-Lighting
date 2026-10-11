"""Bounded default diagnostics, with precise failure context. Date: 2026-10-11."""
import unittest
from autolisp_host import Symbol
import test_diagnostics as fixtures


class LogVolumeTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DiagnosticTests()
        self.f.setUp()
        self.f.logging()
        self.h = self.f.h
        self.f.call('EL:LogStart')

    def test_default_filters_geometry_details_but_retains_key_events_and_verbose(self):
        stages = ['ENTER INSERT_TRANS', 'LEAVE INSERT_TRANS', 'INSERT_TRANS_RESULT',
                  'INSERT_MATRIX_INPUT', 'ENTER SOLID_TRANS', 'LEAVE SOLID_TRANS',
                  'SOLID_TRANS_RESULT', 'POLYLINE_NORMAL']
        self.h.frames[0]['*EL:LOGVERBOSE*'] = None
        before = self.log_text()
        for stage in stages:
            self.f.call('EL:LogEvent', stage, 'entity-2223')
        self.assertEqual(self.log_text(), before)
        for stage in ['TRANSACTION_START', 'TRANSACTION_ERROR', 'STORE_MISMATCH',
                      'STORE_DXF_READBACK', 'DIAGRAM_OUTPUT_CHECK']:
            self.f.call('EL:LogEvent', stage, 'key evidence')
            self.assertIn(stage, self.log_text())
        self.h.frames[0]['*EL:LOGVERBOSE*'] = True
        for stage in stages:
            self.f.call('EL:LogEvent', stage, 'verbose evidence')
            self.assertIn(stage, self.log_text())

    def test_filtered_call_failure_still_reports_original_entity_and_stack(self):
        self.h.frames[0]['*EL:LOGVERBOSE*'] = None
        def fail():
            raise RuntimeError('matrix failure')
        self.h.builtins['TEST-FAIL'] = fail
        with self.assertRaises(RuntimeError):
            self.f.call('EL:LogCall', 'INSERT_TRANS', 'failed-handle-298B', Symbol('TEST-FAIL'), [])
        self.f.call('EL:LogFailure', 'matrix failure')
        text = self.log_text()
        self.assertIn('failed-handle-298B', text)
        self.assertIn('INSERT_TRANS', text)
        self.assertIn('matrix failure', text)

    def log_text(self):
        return self.f.log.read_text(encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
