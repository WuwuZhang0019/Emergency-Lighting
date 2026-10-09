# 单窗口功率编辑检查
日期：2026-10-09
状态：自动检查通过；真实 CAD 待验收。

覆盖模块：test_exit_devices、test_fixed_diagnostics、test_fixed_exit_preview、test_panel、test_post_stat_workflow、test_diagram_store、test_diagram_update、test_source_contracts、test_root_init。

82 项检查通过。覆盖 ELSTAT 单窗口展示、同窗刷新不关闭、功率草稿保留、空选择保存阻断、预览返回、备用标识稳定性与 XRecord 持久化、模板和容量流程、源码及 DCL 回调约束、旧目录拒绝和打包加载。

检查使用有限 AutoLISP/CAD/DCL 适配器，不启动真实 AutoCAD。Python 使用 -X utf8；临时目录放在仓库 output 下以避免沙箱默认临时目录权限问题。
