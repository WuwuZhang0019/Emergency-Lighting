"""Focused device-library delivery evidence. Date: 2026-10-11. Native CAD pending."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from run_checks import RecordingResult

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    'test_device_library', 'test_device_assets', 'test_device_ui', 'test_device_migration',
    'test_device_recognition', 'test_source_contracts', 'test_empty_panel', 'test_block_table', 'test_exit_devices',
    'test_fixed_diagnostics', 'test_post_stat_workflow', 'test_diagram_store', 'test_diagram_update',
    'test_incremental_updates', 'test_performance', 'test_root_init', 'test_box',
    'test_network_reuse', 'test_freshness_reuse', 'test_generation_boundaries',
    'test_saved_records', 'test_panel_repairs',
)


def run():
    checks = ROOT / 'output/device-library-check'
    checks.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(checks)
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordingResult).run(suite)
    files = sorted(list((ROOT / 'src').glob('*.lsp')) + list((ROOT / 'ui').glob('*.dcl')) +
        [ROOT / 'tools/build_cad2020.py', Path(__file__), ROOT / 'tests/autolisp_host.py',
         ROOT / 'tests/run_checks.py', ROOT / 'tests/test_cad_adapter.py',
         ROOT / 'tests/check_device_library_package.py'] +
        [ROOT / 'tests' / (name + '.py') for name in MODULES])
    evidence = {
        'date': '2026-10-11', 'status': 'automated_passed' if result.wasSuccessful() else 'automated_failed',
        'package': 97, 'native_cad_status': 'pending_user_validation',
        'scope': 'device catalog, immutable assets, CRUD, legacy drafts, name matching and manual values; dependent save/update, source freshness and network reuse regressions',
        'test_count': result.testsRun, 'failure_count': len(result.failures), 'error_count': len(result.errors),
        'tests': sorted(result.records, key=lambda row: row['test']),
        'sha256': {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        'boundary': 'Python AutoLISP/CAD adapters and static source checks; no native WBlock, SLD, DCL, real DWG reopen or timing acceptance',
    }
    path = ROOT / 'tests/evidence/2026-10-11-device-library-097.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if not result.wasSuccessful(): raise SystemExit(1)
    print(f'{result.testsRun} checks passed: {path}')


if __name__ == '__main__': run()
