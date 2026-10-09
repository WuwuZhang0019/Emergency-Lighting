# v46 DWG 草稿回读诊断补全
日期：2026-10-09
状态：70 项存储与流程检查、20 项加载检查通过；原图故障根因和真实 CAD 导出仍待验证

## 现场事实

用户 `ELTRACE-debug(6).log` 的 SHA-256：`3b87b4294833dd8b7afe6b74d37193ddb9c25803599a65ee5b4c385cf08bc848`。

日志 6548–6551 显示 `STORE_SERIALIZE`、5318 个字段的 `STORE_PARSE` 均返回 LIST；6552 进入 `STORE_READBACK`，6553 以 `quit / exit abort` 退出。截图先出现解析错误提示，再出现统一的“主记录损坏或版本不兼容”。本次通过写前编解码与相等检查，失败于写入后的 DWG 回读解析；事务报告撤销。生成前草稿未保存成功，因此尚未进入系统图插入。

原日志没有原始回读字段，不能证明图纸原有数据损坏，也不能指明哪个字段被改变或为何改变。原测试适配器直接保存并返回输入字段，没有证明真实 CAD 会原样返回字段。

[Autodesk XRecord 定义](https://help.autodesk.com/cloudhelp/2020/ENU/AutoCAD-DXF/files/GUID-24668FAF-AE03-41AE-AFA4-276C3692827F.htm) 允许普通对象数据组码和任意顺序的数据；不能仅凭失败认定 2/3/40/90 等组码不合法。

## 诊断改进

- 解码前分别比较 `dictsearch`、`entget` 回读字段与写入字段。`STORE_DXF_READBACK` 记录对象类型、句柄、数量及相等结果；`STORE_DXF_MISMATCH` 记录首个差异序号、组码、类型、值、长度及相邻字段，字符串片段最多 96 字符。
- `STORE_PARSE_ERROR` 在退出前记录阶段、解析位置、当前及下一字段，避免退出时丢失上下文。
- `STORE_DECODE_ERROR` 保留底层异常；`STORE_SCHEMA_ERROR` 区分已解码但必需字段不符。统一“损坏或版本不兼容”提示改为具体阶段提示。
- 保留完整相等检查、存储格式、回滚和关联身份。本次是诊断改进，没有证据宣称原图导出已经修复；不自动删除主记录、不重建草稿、不跳过校验。

## 检查与复测

运行 `python -X utf8 tests/run_store_readback_checks.py`，结果见 [JSON 明细](2026-10-09-store-readback-046.json)。故障注入覆盖写入后标记改变、仅字典接口多出字段、模式校验失败和长字段诊断上限；不表示现场确实发生某种注入情形。既有检查覆盖草稿保存、同步、损坏撤销、长记录和 GB2312 字符边界。

另运行 `python -X utf8 -m unittest discover -s tests -p test_root_init.py` 检查加载与交付。执行 `python -X utf8 tools/build_cad2020.py`，检查实际解压副本、ZIP 与构建目录全部 LISP/DCL 的严格 GB2312 解码、内容一致及 LISP 解析。

完整解压 `应急照明-046.zip`，APPLOAD 同包 `START-CAD2020.lsp`，定位时选择同包 `src/load.lsp`，确认 v46。运行 `ELSTAT` 并点击生成；若仍失败，保留完整的 `应急照明-046/output/ELTRACE-debug.log`。重点查看 `STORE_DXF_MISMATCH`、`STORE_PARSE_ERROR`、`STORE_DECODE_ERROR`。无需先删除主记录或改变导线、图块。真实 CAD 导出、DWG 保存重开和原生 UNDO 尚待现场验证。
