"""Date: 2026-10-15. Focused placement, rollback and on-demand diagnostics checks."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUITES = [
    'test_placement_finish',
    'test_diagnostic_export',
    'test_post_stat_workflow.SelectionStoreTests',
    'test_log_volume',
    'test_cckk_panel_command.PanelCommandTests.test_two_to_four_creates_new_output_without_changing_placement_view',
    'test_cckk_panel_command.PanelCommandTests.test_first_four_circuit_placement_and_save_keep_current_view',
    'test_cckk_panel_command.PanelCommandTests.test_generation_does_not_call_unavailable_zoom',
    'test_cckk_panel_command.PanelCommandTests.test_two_circuit_generate_click_recovers_memory_and_repeated_update',
    'test_cckk_panel_command.PanelCommandTests.test_two_circuit_cancel_then_retry_releases_live_guard',
    'test_cckk_panel_command.PanelCommandTests.test_power_tag_silent_write_failure_is_read_back_and_rolled_back',
    'test_store_context.StoreContextTests.test_native_readback_difference_does_not_publish_context',
    'test_store_context.StoreContextTests.test_commit_callback_change_discards_candidate_and_reads_current_dwg',
    'test_monitor.MonitorTests.test_report_contains_loading_actions_exit_and_preserves_previous_file',
    'test_monitor.MonitorTests.test_write_failure_closes_file_and_keeps_business_result',
]
SOURCES = ['src/common.lsp', 'src/diagram-commands.lsp', 'src/diagram-store.lsp',
           'src/diagram-update.lsp', 'src/panel.lsp', 'ui/power.dcl',
           'tests/test_placement_finish.py', 'tests/test_cckk_panel_command.py',
           'tests/test_diagnostic_export.py',
           'tests/run_placement_finish_checks.py']

if __name__ == '__main__':
    check_root = ROOT / 'output/placement-finish-142-check'
    check_root.mkdir(exist_ok=True)
    os.environ['TEMP'] = os.environ['TMP'] = tempfile.tempdir = str(check_root)
    result = unittest.TextTestRunner(stream=io.StringIO()).run(
        unittest.defaultTestLoader.loadTestsFromNames(SUITES))
    failures = [{'case': case.id(), 'detail': '\n'.join(trace.splitlines()[-12:])}
                for case, trace in result.failures + result.errors]
    report = {'date': '2026-10-15', 'status': 'passed' if result.wasSuccessful() else 'failed',
              'scope': 'Finite CAD/DCL adapters; original-DWG timing and native dialog acceptance pending',
              'cases': result.testsRun, 'suites': SUITES, 'failures': failures,
              'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}}
    output = ROOT / 'tests/evidence/2026-10-15-placement-finish-checks-142.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'cases': result.testsRun, 'status': report['status'], 'failures': failures}, ensure_ascii=False, indent=2))
    raise SystemExit(not result.wasSuccessful())
