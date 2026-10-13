"""Record targeted large-XRecord save checks. Date: 2026-10-13."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from run_checks import RecordingResult

ROOT=Path(__file__).resolve().parents[1]
MODULES=('test_large_xrecord_create','test_diagram_store','test_store_migration',
    'test_store_context','test_store_compact','test_store_integer_tape','test_store_performance',
    'test_fixed_diagnostics','test_gap_cross_circuit',
    'test_diagram_update.UpdateTests.test_large_template_draft_recovers_saves_and_reopens_with_bounded_read',
    'test_diagram_update.UpdateTests.test_existing_undo_group_saves_capacity_and_powers_with_real_transaction',
    'test_diagram_update.UpdateTests.test_draft_then_sync_keep_low_real_digits_and_default_capacity',
    'test_diagram_update.UpdateTests.test_draft_requires_store_readback_not_only_success_flag',
    'test_diagram_update.UpdateTests.test_save_recovers_inline_and_continues_without_separate_command',
    'test_post_stat_workflow.PostStatWorkflowTests.test_default_capacity_generates_without_extra_confirmation',
    'test_post_stat_workflow.PostStatWorkflowTests.test_filled_power_generates_without_touching_non_ground_checkbox',
    'test_post_stat_workflow.SelectionStoreTests.test_draft_confirmation_and_shared_template_roundtrip_through_xrecord')

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=1,resultclass=RecordingResult).run(
        unittest.defaultTestLoader.loadTestsFromNames(MODULES))
    spec=importlib.util.spec_from_file_location('builder',ROOT/'tools/build_cad2020.py')
    builder=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    paths=('src/diagram-store.lsp','tests/test_large_xrecord_create.py','tests/run_large_xrecord_checks.py',
           'tools/build_cad2020.py','tests/test_store_migration.py')
    report={'date':'2026-10-13','status':'completed' if result.wasSuccessful() else 'failed',
        'package':builder.PACKAGE_NO,'passed':result.wasSuccessful(),'tests_run':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'tests':result.records,'modules':MODULES,
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
        'fault_boundary':'ENTMAKEX argument over 1024 fields is a conservative injected fault, not a measured native limit',
        'source_log':{'name':'ELTRACE-debug (27).log','last_stage':'LEAVE STORE_PARSE',
            'last_sequence':120102,'serialized_fields':219138,'native_fault_site':'not recorded'},
        'baseline_report':'2026-10-13-large-xrecord-baseline.json',
        'remaining_baseline_failures':6,
        'native_cad_status':'pending; no running AutoCAD or original DWG available'}
    path=ROOT/'tests/evidence'/f'2026-10-13-large-xrecord-{builder.PACKAGE_NO:03d}.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
