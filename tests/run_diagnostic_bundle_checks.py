"""Date: 2026-10-15. Focused diagnostics ZIP, UI and placement regression checks."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUITES = ['test_diagnostic_bundle', 'test_diagnostic_export', 'test_placement_finish',
          'test_log_volume']
SOURCES = ['src/diagram-commands.lsp', 'src/diagnostic-bundle.ps1', 'src/config.lsp',
           'src/common.lsp', 'src/panel.lsp', 'ui/power.dcl', 'tools/build_cad2020.py',
           'tests/test_diagnostic_bundle.py', 'tests/test_diagnostic_export.py',
           'tests/test_placement_finish.py', 'tests/run_diagnostic_bundle_checks.py']

if __name__ == '__main__':
    check_root = ROOT / 'output/diagnostic-bundle-143-check'
    check_root.mkdir(exist_ok=True)
    os.environ['TEMP'] = os.environ['TMP'] = tempfile.tempdir = str(check_root)
    result = unittest.TextTestRunner(stream=io.StringIO()).run(
        unittest.defaultTestLoader.loadTestsFromNames(SUITES))
    failures = [{'case': case.id(), 'detail': '\n'.join(trace.splitlines()[-18:])}
                for case, trace in result.failures + result.errors]
    report = {'date': '2026-10-15', 'status': 'passed' if result.wasSuccessful() else 'failed',
              'scope': 'Finite CAD/DCL adapters and real Windows PowerShell compression; native CAD pending',
              'cases': result.testsRun, 'suites': SUITES, 'failures': failures,
              'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}}
    output = ROOT / 'tests/evidence/2026-10-15-diagnostic-bundle-checks-143.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'cases': result.testsRun, 'status': report['status'], 'failures': failures},
                     ensure_ascii=False, indent=2))
    raise SystemExit(not result.wasSuccessful())
