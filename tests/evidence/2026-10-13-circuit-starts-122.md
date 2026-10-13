# 122 回路起始端拾取验证记录

日期：2026-10-13
状态：本次定向检查通过；关联测试有 7 项既有失败；原生 CAD 待验收

## 本次必要检查

- `test_circuit_starts.py`：19 项通过，覆盖搜索边界、连续拾取、方向、取消、保存配置、重选及草稿保留。
- `test_fixed_diagnostics.FixedDiagnosticTests.test_recognition_failure_returns_to_pick_panel_with_context`：通过，识别失败返回初始面板且保留箱体上下文。
- `test_panel.PanelTests.test_pick_phase_collects_explicit_start_and_opens_real_circuit_panel`：通过，选择箱体和编号后进入导线连续选择，完成后打开原面板。
- 上述最终定向复测共 21 项，0 失败、0 错误。
- `tools/build_cad2020.py`：生成 122 包；交付编码、字节一致性和加载入口检查由 `check_circuit_starts_package.py` 记录在同目录 `2026-10-13-circuit-starts-package-122.json`。

## 关联回归及分支起点对照

本次执行 `test_concentrated_trunk`、`test_circuit_number`、`test_fixed_diagnostics`、`test_post_stat_workflow`、`test_simple_flow` 共 123 项，初次结果为 115 通过、8 未通过。

其中 1 项诊断测试原先要求异常向外抛出；新交互会捕获识别异常并返回面板，已按新行为调整，并在最终定向复测中通过。

其余 7 项用 `git show HEAD:src/...` 只读装载当时分支起点 `5a73d5f` 的未修改源码复核，均以相同原因复现。本次不修改这些既有问题，也不宣称全套关联测试通过：

| 测试 | 起点及本次相同的失败原因 |
| --- | --- |
| `test_failed_save_returns_to_panel_with_input_for_retry` | 适配器期望保存动作关闭对话框，但未关闭 |
| `test_locked_library_save_persists_local_draft_without_generation` | 适配器期望保存返回 1，实际为空 |
| `test_save_returns_to_same_page_with_values_and_preview_without_picking` | 适配器期望保存动作关闭对话框，但未关闭 |
| `test_inline_legend_selection_preserves_box_values_and_navigation` | 适配器缺少 `WCMATCH` |
| `test_inline_saved_default_refresh_preserves_manual_box_watts` | 适配器缺少 `WCMATCH` |
| `test_recover_library_return_and_save_preserve_input_and_reuse_preview` | 适配器缺少 `WCMATCH` |
| `test_dialog_preview_restores_current_row_and_unsaved_values` | 适配器缺少 `WCMATCH` |

前 6 项位于 `test_post_stat_workflow`，最后 1 项位于 `test_simple_flow`。这组起点对照仅用于判定失败是否由本次修改引入，不构成保存功能的原生 CAD 验收。

## 验收边界

未运行原生 AutoCAD 2020，也未在用户原图上验证。原图需要复核：两个按钮文字、箱号后自动进入连续选择、集中干线无箱侧连接段、箭头方向、取消输入保留、保存 DWG 后重开及系统图生成。详细操作见 122 更新记录。
