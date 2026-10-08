# v14 多段线空坐标转换修复

日期：2026-10-08
状态：源码修复、自动回归及交付编码检查已完成；真实 CAD 原图复测待执行

## 实测证据与修复范围

用户提供的 `ELTRACE-debug (1).log` 标记 DIAGNOSTICS 013。记录 40—66 显示箱体 `1FD6` 内部闭合多段线 `1DE0` 的四次 `POLYLINE_TRANS` 均正常返回但结果为 nil；记录 74 的顶点列表为 `(nil nil nil nil)`，记录 81—83 随后在仿射轮廓转换中触发 `numberp: nil`。原始 DXF 顶点、高程和法向量均有值，因此不采用补零坐标或丢弃轮廓的处理。

当前可以确认空值来自实体形式的 trans 调用；无法仅凭日志确定该 CAD 环境为什么返回 nil。v14 改为通过 DXF 210 法向量指定多段线 OCS，绕开该实体解析路径。DXF 210 缺省时使用标准 +Z 法向量；保留 DXF 38 高程以及负 Z 法向量的 bulge 翻转。块内点先转换为所属块的坐标，再由既有 INSERT 矩阵变换一次，不将插入平移或缩放重复叠加。

[Autodesk trans 参考](https://help.autodesk.com/cloudhelp/2022/ENU/AutoCAD-AutoLISP-Reference/files/GUID-1A316343-0B68-4DBE-8F49-B4D601CB8FCC.htm) 明确支持三维 extrusion vector 作为 OCS 参数；这为替换调用提供接口依据，不证明原环境的 nil 返回原因。

`EL:PolylineTrans` 校验输入与返回值。无效输入、nil 返回或缺少 Z 时立即停止识别，不生成残缺线段；`POLYLINE_TRANS` 阶段保留句柄、二维顶点、高程、法向量、目标坐标系和转换方法，异常事件增加完整输入与原返回值。原生 trans 抛出的错误仍保留原错误及调用栈。保留既有逐行 DXF 日志，以便继续排查。

## 回归证据

- 先注入日志观测到的行为：对 `1DE0` 的实体 trans 返回 nil。修复前轮廓仿射计算失败；修复后仅使用向量路径，生成完整闭合的四条边，长度依次为 600、240、600、240。
- 检查无效二维返回和 nil 返回在首个顶点处停止，不进入线段生成，并保留失败上下文。
- 检查显式 +Z、缺省法向量、-Z 与非零高程 7；-Z 时 X/Z 反向且 bulge 翻转。
- 检查零法向量在调用 trans 前停止，保留输入。
- 保留原生转换异常、DXF 异常、日志 I/O 失败和命令清理等回归。

上述测试使用有限 AutoLISP 宿主及替代 CAD 接口。它们证明源码对观测到的返回行为作了修复，不等同于真实 AutoCAD 2020 执行或全流程验收。

`python -X utf8 tests/run_checks.py`：137 项通过，0 失败、0 错误。首次执行有 1 项因沙箱系统临时目录不可写而出错；将进程 TEMP/TMP 指向项目内 `output/cad2020-014-check` 后通过。源码哈希和逐项结果见 `automated-checks.json`。

`python -X utf8 tools/build_cad2020.py`：生成完整 `output/应急照明-014` 和 ZIP；目录及 ZIP 内全部 LISP/DCL 的严格 GB2312 编码往返和字节一致性检查通过。生成物不提交。

## 原图复测

完整解压 `应急照明-014.zip`，APPLOAD `START-CAD2020.lsp` 并选择新包 `src/load.lsp`，确认 CAD2020 v14 后执行 ELSTAT，依次选原箱体及出口导线。成功时应继续进入出口核对；失败时发回命令行提示路径的 `ELTRACE-debug.log`，末次会话应为 DIAGNOSTICS 014。
