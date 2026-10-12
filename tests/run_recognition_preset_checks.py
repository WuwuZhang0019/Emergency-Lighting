"""Focused first-use recognition evidence. Date: 2026-10-12. Native CAD pending."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from run_checks import RecordingResult
from run_device_library_checks import EVIDENCE_DATE, PACKAGE_NO

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    'test_recognition_preset', 'test_auto_wire', 'test_concentrated_trunk',
    'test_fixed_diagnostics', 'test_empty_panel', 'test_pick_feedback',
    'test_source_contracts', 'test_root_init', 'test_performance',
)


def run():
    checks = ROOT / f'output/recognition-preset-{PACKAGE_NO:03d}-check'
    checks.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(checks)
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordingResult).run(suite)
    files = sorted(list((ROOT / 'src').glob('*.lsp')) + list((ROOT / 'ui').glob('*.dcl')) +
        [ROOT / 'tools/build_cad2020.py', ROOT / 'tests/autolisp_host.py',
         ROOT / 'tests/run_checks.py', ROOT / 'tests/run_device_library_checks.py',
         ROOT / 'tests/test_cad_adapter.py', ROOT / 'tests/test_simple_flow.py',
         ROOT / 'tests/test_panel.py', ROOT / 'tests/test_post_stat_workflow.py',
         ROOT / 'tests/test_diagnostics.py', ROOT / 'tests/test_cckk_panel_command.py',
         ROOT / 'tests/check_device_library_package.py', Path(__file__)] +
        [ROOT / 'tests' / (name + '.py') for name in MODULES])
    diagnostic_files = [path for path in sorted(checks.glob('input-*.log')) if path.is_file()]
    evidence = {
        'date': EVIDENCE_DATE, 'package': PACKAGE_NO,
        'status': 'automated_passed' if result.wasSuccessful() else 'automated_failed',
        'native_cad_status': 'pending_user_validation',
        'scope': 'first-use device registration in both ELSTAT pick entries, same panel and number continuation, Enter/Esc without DWG writes, persisted names, strict preset filters, wire/trunk geometry, empty/saved panel entry, and interaction accounting',
        'test_count': result.testsRun, 'failure_count': len(result.failures), 'error_count': len(result.errors),
        'tests': sorted(result.records, key=lambda row: row['test']),
        'sha256': {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        'diagnostic_inputs': {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in diagnostic_files},
        'boundary': 'Python AutoLISP/CAD adapters and source checks; no native AutoCAD 2020 DCL, original DWG, or real performance acceptance',
    }
    path = ROOT / f'tests/evidence/{EVIDENCE_DATE}-recognition-preset-{PACKAGE_NO:03d}.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    if not result.wasSuccessful(): raise SystemExit(1)
    print(f'{result.testsRun} checks passed: {path}')


if __name__ == '__main__': run()
