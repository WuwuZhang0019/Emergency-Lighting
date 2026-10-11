"""Storage decode and dependent command regression evidence. Date: 2026-10-11."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from run_checks import RecordingResult
from run_remaining_performance_checks import MODULES as PREVIOUS_MODULES
from test_store_compact import StoreCompactTests
from test_store_decode_cache import StoreDecodeCacheTests

ROOT = Path(__file__).resolve().parents[1]
MODULES = PREVIOUS_MODULES + ('test_store_decode_cache',)


if __name__ == '__main__':
    check_dir = ROOT / 'output/cad2020-perf-check'
    check_dir.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(check_dir)
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordingResult).run(suite)
    files = sorted(list((ROOT / 'src').glob('*.lsp')) +
        [ROOT / 'tools/build_cad2020.py', Path(__file__),
         ROOT / 'tests/autolisp_host.py', ROOT / 'tests/run_checks.py',
         ROOT / 'tests/run_remaining_performance_checks.py'] +
        [ROOT / 'tests' / (name + '.py') for name in MODULES])
    evidence = {
        'date': '2026-10-11', 'package': 94,
        'scope': 'exact command-scoped master-record decode reuse and two-route raw validation, paged atom/template lookup, legacy migration/downgrade, corruption/callback/rollback cases and dependent panel, recognition and update contracts',
        'passed': result.wasSuccessful(), 'test_count': result.testsRun,
        'failure_count': len(result.failures), 'error_count': len(result.errors),
        'tests': sorted(result.records, key=lambda row: row['test']),
        'work_measurements': {
            'same_record_reads': getattr(StoreDecodeCacheTests, 'read_work_evidence', None),
            'changed_record_update': getattr(StoreDecodeCacheTests, 'update_work_evidence', None),
            'cached_read_native_routes': getattr(StoreDecodeCacheTests, 'hit_read_work_evidence', None),
            'atom_pool_lookup': getattr(StoreCompactTests, 'lookup_work_evidence', None),
            'measurement_boundary': 'synthetic adapter call counts and linked-list traversal work only; not native AutoCAD timing',
        },
        'cad_status': 'pending; adapter work counts do not establish native AutoCAD 2020 timing, dynamic blocks, real DWG save/reopen or UNDO/REDO acceptance',
        'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in files if p.is_file()},
    }
    path = ROOT / 'tests/evidence/2026-10-11-performance-decode-094.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
