"""Focused P0 checks and revision-bound evidence. Date: 2026-10-11."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from run_checks import RecordingResult

ROOT = Path(__file__).resolve().parents[1]
MODULES = ('test_performance', 'test_diagnostics', 'test_diagram_store',
           'test_diagram_update', 'test_cckk_panel_command', 'test_post_stat_workflow',
           'test_root_init', 'test_source_contracts')


if __name__ == '__main__':
    check_dir = ROOT / 'output/cad2020-perf-check'
    check_dir.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(check_dir)
    evidence_path = ROOT / 'tests/evidence/2026-10-11-performance-p0-091.json'
    previous = None
    names = MODULES
    if sys.argv[1:] == ['--retry-failures']:
        previous = json.loads(evidence_path.read_text(encoding='utf-8'))
        # Retry corrected test inputs only; changed production/build code needs a full run.
        for name, digest in previous['sha256'].items():
            if name.startswith('src/') or name == 'tools/build_cad2020.py':
                if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                    raise SystemExit(f'{name} 已变化，请重新执行完整针对性检查')
        names = [row['test'] for row in previous['tests'] if row['status'] != 'passed']
        if any(name.split('.')[0] not in MODULES or '(' in name for name in names):
            raise SystemExit('失败记录不是可独立复测的用例，请重新执行完整针对性检查')
        if not names:
            raise SystemExit('现有记录没有失败用例')
    elif sys.argv[1:]:
        raise SystemExit('仅支持无参数完整检查或 --retry-failures')
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    records = {row['test']: row for row in (previous['tests'] if previous else [])}
    records.update({row['test']: row for row in result.records})
    history = previous.get('validation_runs', []) if previous else []
    if previous and not history:
        history = [{'kind': 'full', 'test_count': previous['test_count'],
                    'failure_count': previous['failure_count'], 'error_count': previous['error_count'],
                    'failures': [row for row in previous['tests'] if row['status'] != 'passed']}]
    history.append({'kind': 'retry-failures' if previous else 'full', 'test_count': result.testsRun,
                    'failure_count': len(result.failures), 'error_count': len(result.errors),
                    'tests': result.records if previous else []})
    files = ['src/common.lsp', 'src/config.lsp', 'src/generation.lsp', 'src/panel.lsp',
             'src/diagram-commands.lsp', 'src/diagram-store.lsp', 'src/diagram-update.lsp',
             'tests/test_performance.py', 'tests/test_cckk_panel_command.py',
             'tests/run_performance_checks.py', 'tools/build_cad2020.py']
    evidence = {
        'date': '2026-10-11', 'phase': 'P0', 'package': 91,
        'scope': 'command timing, interaction exclusion, logging contrast, actual write-interface counters, existing store/panel/transaction/loading contracts',
        'passed': all(row['status'] == 'passed' for row in records.values()), 'test_count': len(records),
        'failure_count': sum(row['status'] == 'failed' for row in records.values()),
        'error_count': sum(row['status'] == 'error' for row in records.values()),
        'tests': sorted(records.values(), key=lambda row: row['test']), 'validation_runs': history,
        'cad_status': 'pending; synthetic clocks and finite adapters are not native AutoCAD 2020 timing, DWG save/reopen or UNDO acceptance',
        'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sys.exit(0 if evidence['passed'] else 1)
