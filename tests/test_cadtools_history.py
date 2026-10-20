"""Date: 2026-10-20. Replay quick-reference regressions against generated lite LISP.

Uses finite CAD adapters, never writes a delivery or claims native CAD acceptance.
The cases retain their original assertions; only the LISP definition source changes.
"""
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from autolisp_host import Host, Symbol, parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import cadtools_lite as lite
import build_cad2020 as full
import test_cadtools_lite as lite_fixture


# Quick-reference sections and their still-applicable behavior, not old UI routes.
CASES = {
    '03_04': (
        'test_cad_adapter.CadAdapterTests.test_host_rejects_nil_numeric_comparison_but_equal_can_test_absence',
        'test_cad_adapter.CadAdapterTests.test_nil_type_and_snapshot_signature_match_autolisp',
        'test_cad_adapter.CadAdapterTests.test_contour_polyline_missing_flags_matches_explicit_zero',
        'test_cad_adapter.CadAdapterTests.test_gap_command_missing_polyline_flags_previews_and_cleans_up',
    ),
    '05_06': (
        'test_ocs_transforms.OcsTransformTests.test_user_circle_keeps_radius_and_closure_when_entity_trans_returns_nil',
        'test_ocs_transforms.OcsTransformTests.test_nested_circle_applies_bases_mirror_scales_rotation_and_ocs_once',
        'test_ocs_transforms.OcsTransformTests.test_bad_curve_results_stop_before_affine_and_keep_sample_context',
        'test_signature_depth.SignatureDepthTests.test_long_geometry_list_preserves_all_items_without_recursive_tail',
    ),
    '07_10': (
        'test_sample_layer.SampleLayerTests.test_downstream_sample_opens_actual_exits_and_cancel_does_not_rescan',
        'test_simple_flow.SimpleFlowTests.test_free_gap_ends_reconnect_when_opposite_ends_touch_panel_and_device',
        'test_simple_flow.SimpleFlowTests.test_multiple_breaks_continue_past_middle_device_and_t_branch',
        'test_simple_flow.SimpleFlowTests.test_gap_does_not_jump_to_parallel_other_elevation_or_out_of_range_wire',
        'test_simple_flow.SimpleFlowTests.test_other_wire_layer_and_bare_crossing_do_not_merge_systems',
    ),
    '08_18': (
        'test_circuit_colors.CircuitColorTests.test_same_circuit_wires_and_exploded_device_share_color',
        'test_circuit_colors.CircuitColorTests.test_escape_restores_sources_and_removes_all_copies',
    ),
    '14_16': (
        'test_fixed_diagnostics.FixedDiagnosticTests.test_empty_device_rows_do_not_call_native_sort',
        'test_fixed_diagnostics.FixedDiagnosticTests.test_new_record_avoids_existing_ids_and_retains_existing_record',
        'test_template_choices.TemplateChoiceTests.test_allowed_values_unwrap_each_variant_and_preserve_numbers',
        'test_template_choices.TemplateChoiceTests.test_capacity_whitespace_and_fixed_buried_alias_are_automatic',
        'test_template_choices.TemplateChoiceTests.test_capture_returns_template_without_saving_config',
    ),
    '21_24_30': (
        'test_device_branches.DeviceBranchTests.test_three_wire_device_branch_counts_downstream_and_allows_generation',
        'test_device_branches.DeviceBranchTests.test_loop_and_other_panel_still_block',
        'test_device_branches.PhysicalBranchTests.test_three_verified_contacts_are_not_abnormal',
        'test_insert_retry.RetryTests.test_cancelled_first_insert_keeps_accepted_config_and_draft_before_retry',
        'test_post_stat_workflow.SelectionStoreTests.test_draft_confirmation_and_shared_template_roundtrip_through_xrecord',
        'test_post_stat_workflow.SelectionStoreTests.test_missing_capacity_and_ground_use_defaults_without_marking_stale',
    ),
    '26_37': (
        'test_cckk_panel_command.PanelCommandTests.test_panel_calls_real_command_places_native_box_and_85w_circuits',
        'test_cckk_panel_command.PanelCommandTests.test_two_circuit_generate_click_recovers_memory_and_repeated_update',
        'test_cckk_panel_command.PanelCommandTests.test_two_circuit_cancel_then_retry_releases_live_guard',
        'test_cckk_panel_command.PanelCommandTests.test_nil_after_first_row_rolls_back_without_recovery_then_retry_succeeds',
        'test_cckk_panel_command.PanelCommandTests.test_power_uses_cckk_entmake_not_the_activex_annotation_path',
        'test_cckk_panel_command.PanelCommandTests.test_power_tag_silent_write_failure_is_read_back_and_rolled_back',
        'test_cckk_panel_command.PanelCommandTests.test_rollback_failure_does_not_start_stale_record_write_or_recovery',
        'test_cckk_panel_command.PanelCommandTests.test_caption_creation_failure_rolls_back_instead_of_silent_omission',
        'test_cckk_panel_command.PanelCommandTests.test_escape_restores_variables_and_undoes_partial_native_objects',
    ),
    '29_31_32': (
        'test_diagram_store.StoreTests.test_large_signature_save_reopen_and_rewrite_with_bounded_read',
        'test_diagram_store.StoreTests.test_native_doubles_preserve_low_digits_tiny_values_and_signed_coordinates',
        'test_diagram_store.StoreTests.test_native_strings_bypass_printer_reader_escapes_and_keep_case',
        'test_diagram_store.StoreTests.test_74_legacy_fields_are_replaced_even_when_entmod_would_retain_them',
        'test_diagram_store.StoreTests.test_corrupt_store_and_serialization_mismatch_never_modify_dwg',
    ),
    '39_40': (
        'test_cckk_panel_command.PanelCommandTests.test_first_four_circuit_placement_and_save_keep_current_view',
        'test_cckk_panel_command.PanelCommandTests.test_deleted_four_circuit_output_record_is_pruned_when_new_one_is_placed',
        'test_cckk_panel_command.PanelCommandTests.test_cancel_rebuild_restores_remnants_and_old_association',
    ),
    '41_43': (
        'test_contact_reuse.ContactReuseTests.test_twelve_translated_instances_expand_and_find_rings_once',
        'test_contact_reuse.ContactReuseTests.test_holes_and_elevation_translate_and_each_pass_reloads_geometry',
        'test_contact_reuse.ContactReuseTests.test_native_extents_skip_contact_bounds_scan_but_do_not_prove_contact',
        'test_panel_number.PanelNumberTests.test_saved_number_reopens_consistently',
        'test_panel.PanelTests.test_free_terminal_without_candidates_does_not_block_generation',
        'test_panel.PanelTests.test_rejected_and_ambiguous_gap_evidence_still_blocks',
    ),
    '44_46': (
        'test_fixed_source_signature.FixedSourceSignatureTests.test_no_large_printer_call_and_repeated_freshness_passes',
        'test_fixed_source_signature.FixedSourceSignatureTests.test_exact_changes_still_fail_and_log_bounded_leaf_evidence',
        'test_fixed_source_signature.FixedSourceSignatureTests.test_native_dxf_roundtrip_preserves_typed_signature',
    ),
    '47': (
        'test_actual_contact_132.ActualContactTests.test_default_tolerance_replays_complete_original_device_and_gap_chain',
        'test_panel_library_toggle.PanelLibraryToggleTests.test_declared_cancel_receiver_closes_home_and_result_in_both_layouts',
        'test_panel_library_toggle.PanelLibraryToggleTests.test_exit_always_closes_and_keeps_valid_or_invalid_editor_input_for_reopening',
    ),
}


class LiteHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = lite.runtime_files()
        cls.definitions = {
            name: [form for form in parse(data.decode('gb2312'))
                   if isinstance(form, list) and form and form[0] == 'DEFUN']
            for name, data in cls.files.items() if name.startswith('src/') and name != 'src/load.lsp'
        }
        entry = lite_fixture.LiteTests('runTest')
        entry.files = cls.files
        host, *_ = entry.fixture()
        if not host.run('(EL:LiteLoad)'):
            raise AssertionError('generated lite entry did not initialize')
        cls.effective = host.functions.copy()

    def test_business_expressions_match_full_except_explicit_path_plumbing(self):
        def normalize(form):
            if isinstance(form, Symbol) and form == '*EL:LITEDATAROOT*':
                return Symbol('*EL:ROOT*')
            return [normalize(x) for x in form] if isinstance(form, list) else form
        allowed_config = {'EL:ROOTVALID', 'EL:ENSUREROOT', 'EL:CONFIGPATH'}
        for name, forms in self.definitions.items():
            source = ROOT / name
            baseline = [form for form in parse(full.cad2020_bytes(source).decode('gb2312'))
                        if isinstance(form, list) and form and form[0] == 'DEFUN']
            old = {form[1]: form for form in baseline}
            new = {form[1]: form for form in forms}
            self.assertEqual(set(old), set(new), name)
            for key in old:
                if name == 'src/config.lsp' and key in allowed_config:
                    continue
                self.assertTrue(normalize(new[key]) == old[key], f'{name}: {key}')
        for source in (ROOT / 'ui').glob('*.dcl'):
            self.assertEqual(self.files['ui/' + source.name], full.cad2020_bytes(source))

    def replay(self, identity):
        original = Host.load_definitions
        original_call = Host.call
        loaded = []
        def generated(host, path):
            path = Path(path).resolve()
            if path.parent == ROOT / 'src':
                # Historical fixtures often loaded a subset of modules. Real lite
                # installs define all modules, including later storage overrides.
                if not getattr(host, '_lite_history_loaded', False):
                    host.functions.update(self.effective)
                    host._lite_history_loaded = True
                key = 'src/' + path.name
                loaded.append(key)
                if key == 'src/load.lsp':
                    return  # Already defined by the guarded entry above.
                self.assertTrue(key in self.definitions, key)
                for form in self.definitions[key]:
                    host.evaluate(form)
            else:
                original(host, path)
        def initialized_call(host, name, values):
            # These fixtures bypass APPLOAD and manage their own temporary data
            # paths. Bind its already-selected fixture root as their data root;
            # read-only installation isolation is covered by LiteTests separately.
            root = host.lookup('*EL:ROOT*')
            if root and not host.lookup('*EL:LITEDATAROOT*'):
                host.set('*EL:LITEDATAROOT*', root)
            return original_call(host, name, values)
        module_name, class_name, method = identity.split('.')
        case = getattr(importlib.import_module(module_name), class_name)(method)
        result = unittest.TestResult()
        with patch.object(Host, 'load_definitions', generated), patch.object(Host, 'call', initialized_call):
            case.run(result)
        details = '\n'.join(detail for _, detail in result.errors + result.failures)
        self.assertTrue(result.wasSuccessful(), identity + '\n' + details[:1800] + details[-700:])
        self.assertTrue(loaded, identity + ': no generated lite definitions exercised')
        self.assertEqual(result.skipped, [])


def history_case(identity):
    def run(self):
        self.replay(identity)
    run.__doc__ = identity
    return run


for sections, cases in CASES.items():
    for index, identity in enumerate(cases, 1):
        setattr(LiteHistoryTests, f'test_sections_{sections}_{index:02d}', history_case(identity))


if __name__ == '__main__':
    unittest.main()
