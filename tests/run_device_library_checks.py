"""Focused device-library delivery evidence. Date: 2026-10-12. Native CAD pending."""
import hashlib
import json
import re
from pathlib import Path
import tempfile
import unittest

from run_checks import RecordingResult

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DATE = '2026-10-12'
PACKAGE_NO = int(re.search(r'^PACKAGE_NO = (\d+)$',
    (ROOT / 'tools/build_cad2020.py').read_text(encoding='utf-8'), re.M)[1])
MODULES = (
    'test_default_device_library', 'test_tianz_library_import',
    'test_device_library', 'test_device_assets', 'test_device_ui', 'test_device_pick', 'test_device_migration', 'test_thumbnails',
    'test_recognition_preset', 'test_auto_wire', 'test_concentrated_trunk', 'test_generation_reasons',
    'test_device_recognition', 'test_source_contracts', 'test_empty_panel', 'test_block_table', 'test_exit_devices',
    'test_fixed_diagnostics', 'test_post_stat_workflow', 'test_diagram_store', 'test_diagram_update',
    'test_incremental_updates', 'test_performance', 'test_root_init', 'test_box',
    'test_network_reuse', 'test_freshness_reuse', 'test_generation_boundaries',
    'test_saved_records', 'test_panel_repairs',
    'test_circuit_number', 'test_panel', 'test_panel_number', 'test_cckk_panel_command',
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
         ROOT / 'tests/check_device_library_package.py', ROOT / 'tools/import_tianz_library.py',
         ROOT / 'tools/check_default_library_com.ps1',
         ROOT / 'tests/evidence/2026-10-12-default-library-source.json',
         ROOT / 'config/tianz-selected-devices.json'] +
        [path for path in (ROOT / 'assets/default-device-library').rglob('*') if path.is_file()] +
        [ROOT / 'tests' / (name + '.py') for name in MODULES])
    evidence = {
        'date': EVIDENCE_DATE, 'status': 'automated_passed' if result.wasSuccessful() else 'automated_failed',
        'package': PACKAGE_NO, 'native_cad_status': 'pending_user_validation',
        'scope': '49 bundled defaults, first-open installation, user values and deletion preservation, interrupted-copy recovery, UTF-8 BOM and root-switch failures; direct multi-pick, presets, geometry, power, numbering, save/reopen and transaction regressions',
        'test_count': result.testsRun, 'failure_count': len(result.failures), 'error_count': len(result.errors),
        'tests': sorted(result.records, key=lambda row: row['test']),
        'sha256': {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        'boundary': 'Python AutoLISP/CAD adapters and static source checks; no native WBlock, SLD, DCL, real DWG reopen or timing acceptance',
    }
    path = ROOT / f'tests/evidence/{EVIDENCE_DATE}-device-library-{PACKAGE_NO:03d}.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    if not result.wasSuccessful(): raise SystemExit(1)
    print(f'{result.testsRun} checks passed: {path}')


if __name__ == '__main__': run()
