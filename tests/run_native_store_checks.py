"""Focused native-XRecord codec evidence; no native CAD acceptance. Date: 2026-10-09."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from run_checks import RecordingResult

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULES = ('test_diagram_store', 'test_diagram_update', 'test_post_stat_workflow',
           'test_fixed_diagnostics', 'test_signature_depth', 'test_source_contracts',
           'test_kernel', 'test_root_init')

if __name__ == '__main__':
    check_dir = ROOT / 'output/cad2020-045-check'
    check_dir.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(check_dir)
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    files = ['src/diagram-store.lsp', 'tests/autolisp_host.py', 'tests/test_diagram_store.py',
             'tests/test_diagram_update.py', 'tests/run_native_store_checks.py',
             'tools/build_cad2020.py']
    evidence = {
        'date': '2026-10-09', 'package': 45,
        'scope': 'native DXF doubles and strings, legacy V1 reads and migration, strict mismatch diagnostics, real draft/sync functions, rollback and loading',
        'passed': result.wasSuccessful(), 'test_count': result.testsRun,
        'failure_count': len(result.failures), 'error_count': len(result.errors),
        'tests': result.records,
        'cad_status': 'pending; finite adapters do not establish native AutoCAD 2020, real DWG save/reopen or UNDO acceptance',
        'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
    }
    (ROOT / 'tests/evidence/2026-10-09-native-store-045.json').write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
