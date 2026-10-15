"""Date: 2026-10-15. Focused persistence, source-change and generation checks."""
import hashlib
import io
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUITES = [
    'test_generation_speed',
    'test_post_stat_workflow.SelectionStoreTests',
    'test_simplified_flow.SimplifiedFlowTests.test_consecutive_generation_keeps_old_entities_and_prunes_history',
    'test_generation_boundaries.FreshCallbackBoundaryTests',
    'test_generation_boundaries.NativePlacementBoundaryTests.test_actual_template_definition_change_during_placement_rolls_back',
    'test_cckk_panel_command.PanelCommandTests.test_panel_calls_real_command_places_native_box_and_85w_circuits',
    'test_cckk_panel_command.PanelCommandTests.test_two_circuit_cancel_then_retry_releases_live_guard',
    'test_store_context.StoreContextTests.test_native_readback_difference_does_not_publish_context',
    'test_store_context.StoreContextTests.test_commit_callback_change_discards_candidate_and_reads_current_dwg',
    'test_store_split.SplitStoreTests.test_changed_native_reference_invalidates_context',
]
SOURCES = ['src/common.lsp', 'src/simple.lsp', 'src/diagram-store.lsp',
           'src/diagram-update.lsp', 'src/diagram-commands.lsp',
           'tests/test_generation_speed.py', 'tests/test_post_stat_workflow.py',
           'tests/check_generation_speed_work.py', 'tests/run_generation_speed_checks.py']

if __name__ == '__main__':
    result = unittest.TextTestRunner(stream=io.StringIO()).run(
        unittest.defaultTestLoader.loadTestsFromNames(SUITES))
    failures = [{'case': case.id(), 'detail': '\n'.join(trace.splitlines()[-15:])}
                for case, trace in result.failures + result.errors]
    report = {'date': '2026-10-15', 'status': 'passed' if result.wasSuccessful() else 'failed',
              'scope': 'Finite CAD adapters; original-DWG timing and placement remain pending',
              'cases': result.testsRun, 'suites': SUITES, 'failures': failures,
              'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}}
    output = ROOT / 'tests/evidence/2026-10-15-generation-speed-checks-141.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'cases': result.testsRun, 'status': report['status'], 'failures': failures}, ensure_ascii=False, indent=2))
    raise SystemExit(not result.wasSuccessful())
