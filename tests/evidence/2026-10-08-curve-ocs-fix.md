# v15 圆及嵌套图块 OCS 转换修复

日期：2026-10-08
状态：源码修复、自动回归及交付编码检查已完成；真实 CAD 原图复测待执行

## v14 真实日志结果

用户提供的 `ELTRACE-debug (2).log` 为 DIAGNOSTICS 014，共 4108 条记录。记录 40—83 表明原箱体 `1FD6` 的多段线 `1DE0` 已返回有效三维顶点并生成四条变换后的线段；本次已进入 COLLECT_SNAPSHOT 的设备采集阶段。这是原多段线修复路径的实测证据，不是整箱统计成功证据。

记录 4103—4107 的新失败对象为设备 INSERT `2037` 内的 CIRCLE `1CE3`：圆心 `(3.63798e-12 0.208333 0)`、半径 `0.208333`、法向量 `(0 0 1)`，外层矩阵为 `(-500 0 0 -500 1193230 399792 0 500)`。进入 CONTOUR_TRANSFORM 时圆的采样线段已全部成为 `(nil nil)`。结合当前源码，可定位为尚未替换的圆／圆弧实体 trans 路径。日志未记录原生 trans 的内部原因，仍不能断言 CAD 为什么对该实体返回 nil。

## 修改

- 将 v14 校验器提取为共用 `EL:OCSTrans`；原多段线函数及原有事件名保留。
- CIRCLE／ARC 经 `EL:CurveSegments` 在 OCS 中按既有误差上限采样，再用法向量转换；不以直弦代替圆弧，不重复施加父块矩阵。
- INSERT 的插入原点、X／Y 轴参考点、Z 位移向量同步采用法向量与返回值校验，覆盖嵌套块中同类实体转换风险。保留块基点、旋转、镜像、非等比缩放及 Z 位移标志。
- 圆采样记录 CURVE_POINTS、CURVE_POINT_COUNT，逐点转换记录 CURVE_TRANS，包含句柄、类型、采样序号、点、法向量、目标坐标系、方法和结果。INSERT_TRANS 区分 origin、x-axis、y-axis、z-axis。无效输入／返回值立即停止；原生异常保留调用栈和原错误。
- 审计 `src/geometry.lsp`，原生 trans 仅保留在共用转换器中；视图 DCS 转换保持原用途。

接口依据为 Autodesk 的 [CIRCLE DXF](https://help.autodesk.com/cloudhelp/2018/ENU/AutoCAD-DXF/files/GUID-8663262B-222C-414D-B133-4A8506A27C18.htm)、[ARC DXF](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-DXF/files/GUID-0B14D8F1-0EBA-44BF-9108-57D8CE614BC8.htm) 和 [INSERT DXF](https://help.autodesk.com/cloudhelp/2018/ENU/AutoCAD-DXF/files/GUID-28FA4CFB-9D5E-4880-9F11-36C97578252F.htm)：组码 10 为 OCS 坐标，210 为法向量且缺省为 +Z。法向量转换接口沿用 v14 已核对的 trans 定义。

## 验证范围

从日志抄录圆及插入参数为 `tests/fixtures/contour-1ce3.json`，块名脱敏；只保留相关圆，不代表整张 DWG，数值为打印舍入值。

先注入对实体 `1CE3` 的 trans 返回 nil，修复前仿射运算失败；修复后得到半径约 104.1665 mm 的闭合采样轮廓。新增测试还验证：跨越零角度的半圆、缺省和负 Z 法向量、非零高程；两级嵌套块的非零基点、镜像、非等比缩放及旋转只应用一次；圆转换 nil／二维返回／原生异常均在首个采样点终止并保留上下文；INSERT 的 Z 位移转换为 nil 时在矩阵运算前终止。

这些是有限 AutoLISP 宿主及 CAD 替代接口检查，不等同于真实 CAD 全流程验收。

`python -X utf8 tests/run_checks.py`：142 项通过，0 失败、0 错误。执行时将进程 TEMP/TMP 指向项目内 `output/cad2020-015-check`。当前源码哈希和逐项结果见 `automated-checks.json`。

`python -X utf8 tools/build_cad2020.py`：生成完整 `output/应急照明-015` 及 ZIP，全部 11 个 LISP/DCL 的严格 GB2312 编码往返及目录／ZIP 内容一致性通过。生成包、目录及临时日志不提交。

## 原图复测

完整解压 `应急照明-015.zip`，APPLOAD `START-CAD2020.lsp` 并选择新包内 `src/load.lsp`，确认 CAD2020 v15 后执行 ELSTAT。若仍失败，发回命令行提示路径的 `ELTRACE-debug.log`，末次会话应为 DIAGNOSTICS 015。保留旧配置时按包内使用说明复制 `.eld`，不要混用 UTF-8 源码和 GB2312 交付文件。
