# HLBH 批量编号提示误判修复记录
日期：2026-10-11
状态：修订 2026.10.11.2 已完成，40 项离线检查通过；修复后真实 CAD 复测待完成

## 用户实测证据

用户在 AutoCAD 2020 中运行 `HLPLBH`，框选五根导线并指定文字点后，工具报告未进入预期选线提示，原生命令仍要求选择导线。用户提供的最后一批日志显示：

```text
PROMPT (WIRE "HLBH" "输入要放弃的操作数目或 [自动(A)/控制(C)/开始(BE)/结束(E)/标记(M)/后退(B)] <1>: _Begin HLBH")
COMPLETE nil
```

`CMDNAMES` 已显示 `HLBH`，但 `LASTPROMPT` 保留的是撤销分组命令的历史输出，不能证明 HLBH 没有进入选线。旧版同时把原生执行返回的空结果送入成功分支，在原生命令未退出时执行了结束撤销分组，用户截图随后出现“选择无效，重新选择”。日志没有记录 `CMDACTIVE`，不能确认这次运行的活动状态数值。

## 修复方案

1. 识别普通命令和 ObjectARX 命令状态，并用 HLBH 命令名称补充识别；不再要求活动状态必须包含普通命令位且名称必须同时包含 HLBH。
2. 将 `LASTPROMPT` 作为辅助信息。识别没有刷新、只追加了输入及遗留的 UNDO 输出；保留对新出现的相反交互提示或不支持提示的拦截。
3. 按固定的原生两步流程送入实体/选线点和文字点，以实际新增对象、唯一文字接口、完整编号回读及最终退出状态确认结果。没有生成完整非空结果的批次必须进入失败分支。
4. 失败时有限次数取消本工具刚调用的原生命令，确认没有活动绘图命令或对话框后才执行撤销；不能退出时保留恢复状态，不把 UNDO 参数送进选线提示。
5. 日志补充工具版本、`CMDACTIVE`、`CMDNAMES`、提示前后文本和退出/取消状态。只更新独立 GB2312 `output/HLPLBH.lsp`，不打包。

## 验证安排

旧源码在新增适配测试中可复现用户提供的历史提示导致零条标注，以及原生调用中止返回 nil 后仍向活动命令发送 UNDO 的问题。修订后 40 项检查通过，覆盖 ObjectARX 状态、内部命令名称、提示缺失、选线失败、空或不完整结果、取消未退出和恢复保护。

独立 GB2312 文件已重新导出，并验证严格解码、源码内容一致和全部 36 个顶层 LISP 表达式解析一致。文件为 `output/HLPLBH.lsp`，21103 字节，SHA256 为 `bdbf4b96ed6b69a0ad36ae5e992e1f20b7cc2f8fdab31420f44c17574c5bbd6e`。未生成 ZIP 或完整包。

离线检查不代替真实 AutoCAD/天正验收。修复后应先 Esc 退出旧版留下的命令，重新 APPLOAD 独立文件，确认加载提示含 `2026.10.11.2`。在副本图中按原来的五根线、`ZE1`、一次空白点流程复测；重点确认不再要求逐条手工选择、正确生成五组原生标注并正常退出。`TextString` 接口及原生导线关联仍需实际天正版本验证。

## 接口依据

- [LASTPROMPT：最后回显的命令行文本，包含用户输入](https://help.autodesk.com/cloudhelp/2025/ESP/AutoCAD-LT/files/GUID-6C63005A-A87C-416C-B9FC-D11F609143A9.htm)
- [CMDACTIVE：包含普通命令及 ObjectARX 命令状态](https://help.autodesk.com/cloudhelp/2019/ENU/AutoCAD-Core/files/GUID-18B2E090-6C94-4C24-A70A-F2D6BDD5569C.htm)
- [command-s：活动命令期间使用 UNDO 的限制](https://help.autodesk.com/cloudhelp/2022/ENU/AutoCAD-AutoLISP-Reference/files/GUID-5C9DC003-3DD2-4770-95E7-7E19A4EE19A1.htm)
