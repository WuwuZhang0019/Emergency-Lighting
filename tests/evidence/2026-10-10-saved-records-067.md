# 保存记录侧栏检查
日期：2026-10-10
状态：自动检查通过，真实 AutoCAD 2020 待验收

- 右侧加入本图保存记录，显示箱体句柄、实际回路数、状态和当前箱标记。
- 单击记录不写入；按钮在对话框关闭后检查目标、当前源图和保存回读，再以循环打开目标，避免嵌套对话框。
- 切换保存当前草稿并标记待更新，不发布系统图；失败回到原面板，输入保留。
- `test_saved_records`、`test_post_stat_workflow`、`test_fixed_diagnostics` 共 33 项通过。
- `test_saved_records`、`test_post_stat_workflow`、`test_panel`、`test_panel_repairs`、`test_diagram_store`、`test_diagram_update`、`test_source_contracts` 中 106 项通过，临时目录指定到 `output/cad2020-067-check`。
- 上述复核排除 1 项既有失败：`test_panel.PanelTests.test_default_entry_keeps_two_picks_and_opens_real_circuit_panel` 要求两次拾取，当前自动导线入口只拾取一次。通过临时载入 HEAD 原始 panel/diagram-commands 源码复现相同失败，未修改此旧测试。
- 首轮新增失败分支测试缺少 ALERT 适配，补齐后通过；首轮旧配置写入测试遇到沙箱临时目录权限问题，改用工作区临时目录后通过。
- 067 构建检查全部 20 个 LISP/DCL 文件严格 GB2312 往返、ZIP 与解压目录字节一致；另外验证 LISP 解析及 DCL 花括号配对。
- 自动适配器不构成真实 CAD 验收；10 箱切换、原生 DCL 布局、保存重开和 UNDO 尚待原图验证。
