# v13 箱体轮廓错误定位

日期：2026-10-08
状态：真实日志已分析，诊断细化及宿主回归已完成；根因未确认，原图复测待执行

## 已确认范围

用户提供的 `ELTRACE-debug.log` 为 v12 实际 CAD 运行记录：选箱体 INSERT `1FD6` 和导线 LWPOLYLINE `1FCD` 后，在 `PREPARE_BOX → PANEL_RECORD → BLOCK_CONTOUR` 中报 `参数类型错误: numberp: nil`。最后实体为块内闭合多段线 `1DE0`，不是导线样本。

`INSERT_MATRIX` 已正常返回。块表基点为三维零点，标志为 2；外层矩阵为 `(0 -500 500 0 1193370 401489 0 500)`，容差 0.1。轮廓含四个二维 DXF 顶点，高程 0，法向量 `(0 0 1)`，各段 bulge 为 0。`CONFIG` 初始参数为空，但后续 `PICKS` 已记录有效默认参数；不能仅凭最早 CONFIG 行认定容差为空。

尚未取得 DWG。日志中的数值经过打印舍入，且实体日志过滤过部分组码，不等同于完整 CAD 数据库快照。

## 回放及诊断调整

从日志抄录轮廓和 INSERT 数值到 `tests/fixtures/contour-1de0.json`，保留句柄、宽度、高程、闭合标志、缩放、旋转；块名用 LOG_PANEL 代替，去除用户路径。修改前的源码在宿主回放该数据时成功生成四条边，没有复现 `numberp: nil`；不据此编造根因或静默补零。

v13 增加：

- `CONTOUR_FILTER_INPUT` 记录可见性、类型和法向量。
- `POLYLINE_DATA`／`POLYLINE_TRANS` 调用栈和完整 DXF 输入、当前 DXF 行、顶点转换输入／输出、法向量、组装结果。
- `POLYLINE_SEGMENTS` 阶段及每段的起终点、bulge 和离散误差。
- `CONTOUR_TRANSFORM` 调用栈、原始线段和矩阵、变换结果；不合格点／矩阵记录 `INVALID_AFFINE_INPUT` 后保留原运算行为。
- `CONTOUR_NEXT` 区分几何处理完成后访问下一实体的错误。

沿用每条关闭日志文件、保留原错误和调用栈、日志 I/O 失败不阻断识别的机制。逐行日志会增加 I/O，此版本用于定位错误，不能作为大图性能验收依据。

## 验证

新增四项宿主回归：日志中四边轮廓得到 600／240／600／240 长度、闭合且 Z=0；注入顶点 trans 失败保留精确阶段及顶点；注入缺少 Z 的转换结果保留仿射输入且不补零；注入无效 DXF 组码保留原数值错误和当前行。后三项均是诊断机制测试，不是声称真实图纸存在这些异常。

`python -X utf8 tests/run_checks.py`：133 项通过，0 失败、0 错误。实际源文件哈希及用例结果见 `automated-checks.json`。执行环境为有限 AutoLISP 宿主及 CAD 替代接口，其中 trans 并非 AutoCAD 实现；真实 CAD 复测仍必需。

`python -X utf8 tools/build_cad2020.py` 生成 `output/应急照明-013.zip`。目录及 ZIP 内全部 11 个 LISP/DCL 使用严格 GB2312，逐文件校验编码往返和字节一致性。仅提交源码、测试、文档和构建器，生成包不入 Git。

## 下一步

在原图加载完整 013 包，确认 v13 后重新执行 ELSTAT，发回命令行提示路径下的 ELTRACE-debug.log。新日志应含 DIAGNOSTICS 013。取得具体失败运算及输入后再修复根因；本次交付是细化诊断，未标记真实 CAD 错误已解决。
