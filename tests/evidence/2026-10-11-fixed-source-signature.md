# 整箱超长快照签名误判修复证据
日期：2026-10-11
状态：定向适配器及隔离交付检查通过；真实 AutoCAD 2020 待复测

## 现场依据
用户日志 ELTRACE-debug (19).log：事件19903只有快照比较失败，19904唯一差异字段SIGNATURE，偏移155613，长度305113/305127；298B RAW附近有错位文本及\000。未把原始DWG或日志复制进仓库。

## 修改与检查
- 整箱签名使用EL_FIXED_SOURCE_V1与StableData的结构化值；完整equal比较，无新增容差。
- 类型化快照各差异字段使用StoreDifference的有界路径和值诊断。
- 两个命令错误弹窗计入PerfInput等待，原提示保留。
- tests/test_fixed_source_signature.py：5项通过（含坐标/RAW/设备删除/图纸/规则及两种弹窗子场景）；超过305127字节的嵌套快照、长打印禁用、原生DXF往返、旧记录升级及无变化更新。
- tests/test_source_difference.py：2项通过；tests/test_panel.py：8项通过；tests/test_performance.py：12项通过。
- tests/test_diagram_update.py：使用HEAD已提交存储实现进行独立验证，45项通过。共享存储优化曾导致一项诊断阶段名测试失败，性能对话已修复并负责统一集成回归。
- 运行tools/build_cad2020.py的build函数，内存覆盖交付变量为091并输出到output/source-signature-validation；未修改或占用最终交付版本。严格GB2312、ZIP/目录字节一致性及19个LISP解析通过。隔离包只供验证，不作为用户最终交付。

## 边界
性能存储改动、builder版本号、统一092交付及其性能结论归另一个对话负责。本证据不能证明原图已在AutoCAD成功；应重新ELSTAT并重复生成、更新与真实改图拦截测试。

## 修复文件SHA256
- src/common.lsp: e5db3ce2026a66bdbcc635095a45058d306a29adf4cb1f357394490ec346a562
- src/panel.lsp: e63c15a0a5281d35ec466cd1e95781f3b228028cdcd3041c057ad8447cd0e03c
- src/diagram-commands.lsp: 93ecf80838ea923fe37a21954ad2e5b95e2ae5842b5ef6e30558037d8cbadeac
- tests/test_fixed_source_signature.py: 71f91aa116f8e4356a3f458a85829eafcaf316ad3504e25cff130f903c5fa922
