"""096 empty-DWG and existing-panel regressions. Date: 2026-10-11."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from run_checks import RecordingResult

ROOT = Path(__file__).resolve().parents[1]
MODULES = ('test_empty_panel', 'test_saved_records', 'test_post_stat_workflow',
           'test_panel', 'test_panel_repairs', 'test_fixed_diagnostics',
           'test_source_contracts', 'test_root_init', 'test_performance',
           'test_log_volume')


if __name__ == '__main__':
    # Keep default tempfile users within the writable workspace as well.
    temporary_root = ROOT / 'output/cad2020-empty-panel-check'
    temporary_root.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temporary_root)
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordingResult).run(suite)
    paths = sorted((ROOT / 'src').glob('*.lsp')) + sorted((ROOT / 'ui').glob('*.dcl'))
    paths += [ROOT / 'tests' / (name + '.py') for name in MODULES]
    paths += [ROOT / name for name in (
        'tests/autolisp_host.py', 'tests/run_empty_panel_checks.py',
        'tests/check_empty_panel_package.py', 'tools/build_cad2020.py', '.gitignore')]
    evidence = {
        'date': '2026-10-11', 'package': 96,
        'scope': 'actual ELSTAT/DCL functions with empty-DWG and finite CAD adapters',
        'passed': result.wasSuccessful(), 'test_count': result.testsRun,
        'failure_count': len(result.failures), 'error_count': len(result.errors),
        'tests': result.records,
        'sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in paths},
        'cad_status': 'pending; invalid empty-list selection was reproduced by a contract adapter, '
                      'not a native AutoCAD crash; native empty-DWG ELSTAT must be retested',
    }
    path = ROOT / 'tests/evidence/2026-10-11-empty-panel-096.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
