"""Date: 2026-10-21. Reproducible four-mode recognition operation comparison.

Status: finite same-input adapter evidence, never native AutoCAD wall-clock proof.
"""
import argparse
import hashlib
import json
from pathlib import Path

from test_performance_compare import controlled_comparison

ROOT = Path(__file__).resolve().parents[1]


def check():
    rows = controlled_comparison()
    sources = ['src/common.lsp', 'src/simple.lsp', 'src/geometry.lsp', 'src/circuit-number.lsp',
               'tests/test_collect_read_timing.py', 'tests/test_number_prefix_bounds.py',
               'tests/test_performance_compare.py', 'tests/run_recognition_ab_checks.py']
    return {
        'date': '2026-10-21', 'status': 'passed', 'frozen_baseline_commit': '730c9bd',
        'kind': 'finite-adapter same-input two-pass operation comparison',
        'modes': {'0':'batch clocks and single exact path',
                  '1':'detailed entity clocks and single exact path',
                  '2':'batch clocks and v70 single bounds path',
                  '3':'detailed entity clocks and v70 single bounds path'},
        'order': [r['mode'] for r in rows],
        'controlled_conditions': [
            'same source, seven native entity fixtures, configuration and selected order',
            'fresh identical host and cache for each run',
            'same collection, wire and one device geometry',
            'synthetic clock starts at same wrap boundary with same native operation costs',
            'opposite mode order on the second pass',
            'both complete output and native operation sequence compare exactly'],
        'rows': rows,
        'original_log_operation_projection': {
            'source': 'output (25).zip / 7850 entities, 3320 bounds, 3067 wire records',
            'formula': '2 * (7850 + 3320 + 3067)',
            'detailed_clock_reads': 28474, 'default_detailed_clock_reads': 0,
            'scope': 'operation projection only, not a replay of the original DWG'},
        'frozen_algorithm_checks': {
            'collection': 'test_collect_read_timing: frozen730c9bd complete output, native order and batch frames',
            'single_candidate': 'test_number_prefix_bounds: frozen730c9bd / default / forced baseline',
            'single_candidate_prefix_builds': [33, 0],
            'single_candidate_native_bounds_validations': [34, 0],
            'optimized_single_candidate_slices_and_exact_tests': 33,
            'two_candidate_convergence_prefix_builds': [33, 2]},
        'existing_exclusion': {
            'test': 'test_performance.PerformanceFlowTests.test_no_change_update_is_measured_with_zero_entity_and_master_writes',
            'current_and_frozen730c9bd': '20 != 0 entity writes',
            'reason': 'existing fixture expects no-change update while invocation creates a new diagram; unchanged by this task'},
        'source_sha256': {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        'native_cad_status': 'pending; original-DWG seconds, preview, generation, save/reopen and Undo require native testing',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check()
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
        print(args.output)
        for row in result['rows'][:4]:
            print('mode', row['mode'], 'detail clocks', row['profile_clock_reads'],
                  'prefix builds', row['prefix_builds'], 'exact', row['prefix_exact_tests'],
                  'boundary', row['boundary'])
    else:
        print(text, end='')
