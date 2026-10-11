"""Focused P1-P3 integration evidence; native CAD remains pending. Date: 2026-10-11."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from run_checks import RecordingResult

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    'test_freshness_reuse', 'test_incremental_updates', 'test_store_context',
    'test_store_compact', 'test_store_migration', 'test_log_volume',
    'test_generation_boundaries', 'test_diagnostic_export',
    'test_performance', 'test_store_performance', 'test_fixed_source_signature',
    'test_diagram_store', 'test_diagram_update', 'test_cckk_panel_command',
    'test_post_stat_workflow', 'test_root_init', 'test_source_contracts',
)


if __name__ == '__main__':
    check_dir = ROOT / 'output/cad2020-perf-check'
    check_dir.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(check_dir)
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordingResult).run(
        unittest.defaultTestLoader.loadTestsFromNames(MODULES))
    files = sorted(list((ROOT / 'src').glob('*.lsp')) +
                   [ROOT / 'tools/build_cad2020.py', Path(__file__)] +
                   [ROOT / 'tests' / (name + '.py') for name in MODULES])
    evidence = {
        'date': '2026-10-11', 'package': 93, 'phases': ['P1', 'P1a', 'P2', 'P2a', 'P3'],
        'scope': 'source freshness boundaries, UID attribute deltas, committed readback context, lossless compact storage and migration/downgrade, explicit diagnostics, bounded default logs, panel/loading and undo contracts',
        'passed': result.wasSuccessful(), 'test_count': result.testsRun,
        'failure_count': len(result.failures), 'error_count': len(result.errors),
        'tests': sorted(result.records, key=lambda row: row['test']),
        'cad_status': 'pending; finite adapters do not establish native AutoCAD 2020 timing, dynamic blocks, real DWG save/reopen or UNDO/REDO acceptance',
        'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in files if p.is_file()},
    }
    path = ROOT / 'tests/evidence/2026-10-11-performance-remaining-093.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
