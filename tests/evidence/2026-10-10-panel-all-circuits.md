# 面板取消出线筛选
日期：2026-10-10
状态：源码已完成；未打包，真实 CAD 待验收

- 主面板移除出线核对标题、说明、选择列表及确认刷新按钮。
- 拾取回路全部直接纳入功率表；忽略传入结果的旧 excluded-seeds，保存结果清空排除记录。
- 保留设备缩略图、全部回路图面预览、功率编辑及识别异常检查。
- 本次按用户要求不构建交付目录、不生成 ZIP。

## 检查结果

- test_exit_devices、test_panel、test_panel_repairs、test_fixed_diagnostics、test_source_contracts 共 28 项：27 项通过，1 项原有失败。
- 原有失败：test_default_entry_keeps_two_picks_and_opens_real_circuit_panel，拾取提示数量预期 2、实际 1；加载 Git HEAD 的原始 panel.lsp 后同样复现。本次未修改该入口。
- 新增检查覆盖两条回路即使存在旧排除记录也全部纳入；现有检查覆盖预览返回后保留功率。
- 自动检查采用有限 CAD/DCL 适配器，不代表真实 AutoCAD 界面验收。
