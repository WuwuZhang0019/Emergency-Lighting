"""Date: 2026-10-15. Focused v140 exact recognition, freshness and generate/cancel checks."""
import hashlib
import io
import json
from pathlib import Path
import unittest

from run_recognition_checks import SUITES

ROOT = Path(__file__).resolve().parents[1]
SUITES = SUITES + [
    'test_recognition_six',
    'test_cckk_panel_command.PanelCommandTests.test_panel_calls_real_command_places_native_box_and_85w_circuits',
    'test_cckk_panel_command.PanelCommandTests.test_two_circuit_cancel_then_retry_releases_live_guard',
]
SOURCES = ['src/common.lsp', 'src/geometry.lsp', 'src/simple.lsp', 'src/circuit-number.lsp',
           'src/diagram-update.lsp', 'src/panel.lsp', 'ui/power.dcl', 'tests/autolisp_host.py',
           'tests/test_recognition_six.py', 'tests/check_recognition_six_work.py',
           'tests/run_recognition_six_checks.py']


if __name__ == '__main__':
    result = unittest.TextTestRunner(stream=io.StringIO()).run(
        unittest.defaultTestLoader.loadTestsFromNames(SUITES))
    failures = [{'case': case.id(), 'detail': '\n'.join(trace.splitlines()[-12:])}
                for case, trace in result.failures + result.errors]
    report = {'date': '2026-10-15', 'status': 'passed' if result.wasSuccessful() else 'failed',
              'scope': 'Focused Python adapter checks; original-DWG CAD timing remains pending',
              'cases': result.testsRun, 'suites': SUITES, 'failures': failures,
              'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}}
    output = ROOT / 'tests/evidence/2026-10-15-recognition-checks-140.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(not result.wasSuccessful())
