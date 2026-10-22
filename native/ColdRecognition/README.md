# 只读 .NET 冷路径性能原型
日期：2026-10-22
状态：原型已实现；原图性能与 AutoCAD 接口实测待完成

目标是每个新箱体首次完整识别在 3000 ms 内。当前原型用于验证编译执行批量读取、建树和候选发现能减少多少首次处理成本，尚未迁移精确接触、断口规则、编号、源图证明和预览，因此不能用当前阶段低于 3000 ms 宣布完整目标达成。

每次 `ELNETCOLD76` 调用均新建采集、几何、索引及追踪容器，没有预热调用和上次结果缓存。程序集加载/JIT会由外层 LISP 计时覆盖；其他新箱体的每次调用仍重新读取和计算。生产 `ELSTAT` 继续使用原识别路径。

## 输入与结果

`ELNETCOLD76` 接收七个扁平参数：原 `EL:PresetSelection` 选择集、箱体 ENAME、逗号分隔的起点导线句柄、设备容差、Dmax、边界容差、JSON 报告绝对路径。返回 `(jsonText ((handle minPoint maxPoint) ...))`，最多抽查 16 个块边界。

选择集保持原 Model/预设范围与输入顺序；原型尚未应用业务层的块名、角色、导线配色及线型过滤，因此候选为选择集上界，不能与正式连通设备数直接比较。宽线、弧段和 OCS 数据只参与保守宽筛；精确连通判定仍属于后续迁移工作。保守追踪并不构成完整性的证明。

只使用 `OpenMode.ForRead`，不提交事务、不保存统计、不修改实体或 Xrecord。期间监测源对象事件、当前文档和 DBMOD；对象读取、边界缺失、源变化或候选展开达到显式限额均返回 `ERROR`，不得作为业务结果继续处理。报告只写入插件 `output` 目录。

## 构建与回归

离线构建：`python -B -X utf8 tools/build_cold_recognition.py`。

核心回归：`python -B -X utf8 tools/build_cold_recognition.py --test`。测试以现有 LISP 查询顺序为固定对照，覆盖三轴树、退化边界、射线、重复键拒绝及独立调用。当前签名只接受 ASCII，避免猜测 CAD 2020 的非 ASCII 排序。

目标 `.NET Framework 4.7 / x64 / AutoCAD 2020 API 23.1.0.0`。构建脚本使用本机引用程序集，不下载依赖，不把 Autodesk 程序集装入交付包。可用 `--framework-dir`、`--acmgd`、`--accoremgd`、`--acdbmgd` 覆盖路径。

## 原图测试

加载交付包的 `ELCOLD76.lsp`，运行 `ELCOLD76`。`Prototype` 只测原型；`Both` 在同次拾取输入上另跑完整旧路径的只读识别，报告保留编号及业务字段，不打开结果面板，不写入图纸。运行 `ELDIAG` 导出 `cold-probe.json`、`cold-comparison.eld` 和现有性能日志。

从新开 CAD 的第一次调用开始记录，至少测试两个不同新箱体。`prototype-pick-to-return-ms` 包含拾取结束后的清理、首次 DLL 加载、选择、桥接、写 JSON 和 COM 边界抽查。`legacy-full-ms` 是完整旧识别的单独对照；两者计算范围不同，不能相减作为完整识别提速。

包围盒抽查应 `missing=0 / different=0`；这只验证抽样边界，不代表全部业务规则等价。本机编译和有限宿主回归不能代替真实 AutoCAD/original DWG 验收。


## v0.1.76 加载握手修复

日期：2026-10-22
状态：源码修复完成；真实CAD重新加载与性能待验收

v0.1.75原图在进入 .NET 前失败：`atoms-family` 对未定义函数返回 `(nil)`，整个列表仍为真，旧就绪判断因此跳过NETLOAD。测试桩先前用nil表示未加载，漏掉真实返回形态。

v0.1.76改为实际调用同一 `ELNETCOLD76` 入口，参数 `EL_NET_COLD_PING_V1`。精确响应 `EL_NET_COLD_PROBE_V1/0.1.76`（或ResultBuffer封装的单元素字符串列表）才就绪；此分支不取活动文档、不创建事务/CallState、不采集实体或建立缓存。先握手，未就绪则NETLOAD，再握手；失败不得进入选择/计算。首次握手/JIT和加载仍在拾取后的总时间内，不是提前预热。

记录 `COLD_NATIVE_HANDSHAKE`、`COLD_NATIVE_LOAD_BEGIN/RETURNED`、加载/原型批次计时及失败业务payload。业务ResultBuffer最多拆一层外封装，深层嵌套或错误状态拒绝。新DLL/命令使用76，包内部175，保留旧75包。

[Autodesk atoms-family参考](https://help.autodesk.com/cloudhelp/2022/ENU/AutoCAD-AutoLISP-Reference/files/GUID-0B35850D-9E62-446B-BAA2-0598A4BDE3D7.htm)给出了未定义项保留nil占位的示例；有限宿主的就绪判断回归按该语义模拟。


截图中伴随的“全过程文档写入失败”也已处理：本命令原先沿用 `ELSTAT/ELTRACE/ELPOWER` 通用计时名，直接拼入Windows文件名含有斜杠。现在仅对本命令自己创建的计时运行使用 `ELCOLD76`，成功/失败时间轴可按合法文件名归档，外部已有运行名称保留。
