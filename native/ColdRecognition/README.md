# 只读 .NET 冷路径性能原型
日期：2026-10-22
状态：v0.1.78源图身份检查修复；原图成功返回及完整首次3秒目标待验收

目标是每个新箱体首次完整识别在 3000 ms 内。当前原型用于验证编译执行批量读取、建树和候选发现能减少多少首次处理成本，尚未迁移精确接触、断口规则、编号、源图证明和预览，因此不能用当前阶段低于 3000 ms 宣布完整目标达成。

每次 `ELNETCOLD78` 调用均新建采集、几何、索引及追踪容器，没有预热调用和上次结果缓存。程序集加载/JIT会由外层 LISP 计时覆盖；其他新箱体的每次调用仍重新读取和计算。生产 `ELSTAT` 继续使用原识别路径。

## 输入与结果

`ELNETCOLD78` 接收七个扁平参数：原 `EL:PresetSelection` 选择集、箱体 ENAME、逗号分隔的起点导线句柄、设备容差、Dmax、边界容差、JSON 报告绝对路径。返回 `(jsonText ((handle minPoint maxPoint) ...))`，最多抽查 16 个块边界。

选择集保持原 Model/预设范围与输入顺序；原型尚未应用业务层的块名、角色、导线配色及线型过滤，因此候选为选择集上界，不能与正式连通设备数直接比较。宽线、弧段和 OCS 数据只参与保守宽筛；精确连通判定仍属于后续迁移工作。保守追踪并不构成完整性的证明。

只使用 `OpenMode.ForRead`，不提交事务、不保存统计、不修改实体或 Xrecord。期间监测源对象事件、当前文档和 DBMOD；对象读取、边界缺失、源变化或候选展开达到显式限额均返回 `ERROR`，不得作为业务结果继续处理。报告只写入插件 `output` 目录。

## 构建与回归

离线构建：`python -B -X utf8 tools/build_cold_recognition.py`。

核心回归：`python -B -X utf8 tools/build_cold_recognition.py --test`。测试以现有 LISP 查询顺序为固定对照，覆盖三轴树、退化边界、射线、重复键拒绝及独立调用。当前签名只接受 ASCII，避免猜测 CAD 2020 的非 ASCII 排序。

目标 `.NET Framework 4.7 / x64 / AutoCAD 2020 API 23.1.0.0`。构建脚本使用本机引用程序集，不下载依赖，不把 Autodesk 程序集装入交付包。可用 `--framework-dir`、`--acmgd`、`--accoremgd`、`--acdbmgd` 覆盖路径。

## 原图测试

加载交付包的 `ELCOLD78.lsp`，运行 `ELCOLD78`。`Prototype` 只测原型；`Both` 在同次拾取输入上另跑完整旧路径的只读识别，报告保留编号及业务字段，不打开结果面板，不写入图纸。运行 `ELDIAG` 导出 `cold-probe.json`、`cold-comparison.eld` 和现有性能日志。

从新开 CAD 的第一次调用开始记录，至少测试两个不同新箱体。`prototype-pick-to-return-ms` 包含拾取结束后的清理、首次 DLL 加载、选择、桥接、写 JSON 和 COM 边界抽查。`legacy-full-ms` 是完整旧识别的单独对照；两者计算范围不同，不能相减作为完整识别提速。

包围盒抽查应 `missing=0 / different=0`；这只验证抽样边界，不代表全部业务规则等价。本机编译和有限宿主回归不能代替真实 AutoCAD/original DWG 验收。


## v0.1.78 源图身份检查修复

日期：2026-10-22
状态：源图身份检查修复测试版；原图成功返回、COM边界抽查及完整首次3秒目标待验收

output (32)已成功NETLOAD和握手，内部采集158.947毫秒、建树50.2154毫秒、候选追踪14.0508毫秒；最终仅报 `SOURCE_CHANGED`，对象变化事件0、DBMOD为20→20。旧检查使用托管 `ReferenceEquals` 比较文档及数据库；同一原生对象可能对应不同托管包装，旧报告未区分具体哪一项不相同。

本版以调用开始/结束的非零 `Document.UnmanagedObject`、`Database.UnmanagedObject` 判断底层身份；包装引用是否相同仅记入诊断。源对象事件和DBMOD仍参与拦截，缺失、已释放、不可读或零身份也失败。`source-guard`报告记录各项状态与独立原因，而不是只给出笼统SOURCE_CHANGED。该身份只限单次调用使用，不建立跨次缓存。源保护单列 `source-guard-ms`；`source-guard.started/completed/reasons`、文档/数据库身份有效性及 `native-same` 分项说明保护是否完整执行，`wrapper-same`仅作诊断。参考Autodesk[DisposableWrapper说明](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_Runtime_DisposableWrapper.html)。

本版DLL为 `EmergencyLighting.ColdRecognition78.dll`，入口 `ELNETCOLD78`，健康响应 `EL_NET_COLD_PROBE_V1/0.1.78`，内部177。只修复源身份判定和诊断，不调整候选或生产识别算法。LISP命令另以本轮对照报告已成功写出的完成标志校验归档状态，修正原型ERROR却记为COLD-PROBE-FINISHED的问题；该标志每轮隔离，不从上轮继承。首次加载/JIT仍在拾取后的外层计时内，主调用每次重新采集建树；只读事务、事件检测与失败拒绝保留。

output (32)最后拾取至失败返回2.047秒，其中加载/握手1.703秒、桥接0.250秒。失败后没有执行LISP COM抽查及报告，内部230.4161毫秒总计也不含最终报告写盘；这些不代表完整首次识别已到3秒。v78先以2604F五起点复测：原型状态应为PROTOTYPE_COARSE_ONLY、源保护原因列表为空，COM抽查missing/different均0；每轮立即ELDIAG，再测其他新箱体并单独保留报告。

本轮44项LISP定向回归通过，耗时3.231秒（冷原型33项、冷入口8项、完整入口3项）；.NET共17组回归通过（空间树9组、源身份8组），AutoCAD 2020 API 23.1引用DLL编译0警告、0错误。回归证据：`tests/evidence/2026-10-22-v0.1.78-source-identity-repair.json`。这些结果不代替原生CAD成功返回及原图耗时验收。

## v0.1.77 外部函数调用与默认计时修复

日期：2026-10-22
状态：源码修复；真实CAD桥接与首次性能待复测

output (31)在第一次握手处报 `函数错误: ELNETCOLD76`，没有握手结果、NETLOAD开始或JSON。总22.922秒含20.188秒交互；最后拾取结束到失败仅0.094秒，尚未进入.NET采集。输入为2604F箱体加五起点，与历史F072四起点不同。

LISP不再把外部入口直接作为 `vl-catch-all-apply` 目标。`EL:ColdNativePing`和`EL:ColdNativeInvoke`由defun定义，函数体直接调用 `ELNETCOLD77`；catch/PerfCall接收这些明确的LISP封装。首次入口未注册错误在封装内部捕获后，才继续NETLOAD并复验版本。正常七参业务分支同样保护。官方[vl-catch-all-apply说明](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-MAC-AutoLISP-Reference/files/GUID-E08CC2A6-787A-422F-8BD3-18812996794C.htm)列出的目标为defun函数或lambda。

新增 `COLD_NATIVE_HANDSHAKE_BEGIN`、`COLD_NATIVE_PROBE_BEGIN` 及桥接异常记录。v76虽有加载/业务PerfCall调用，却漏了默认粗计时白名单；v77补上 `COLD_NATIVE_LOAD`、`COLD_NATIVE_PROBE` 白名单及中文标签，并用真实默认计时路径回归。

C#仅递增导出函数及程序集版本至77，算法不变。健康请求仍为 `EL_NET_COLD_PING_V1`，响应为 `EL_NET_COLD_PROBE_V1/0.1.77`；健康分支不读图、开事务或建立几何容器。七参主调用每次新建状态；握手/JIT和首次加载继续计入拾取后的外层时间。完整首次识别3秒尚未验收。

本版内部176，DLL为 `EmergencyLighting.ColdRecognition77.dll`。先复测本次2604F五起点，历史F072四起点另记报告；每轮立即ELDIAG。下面保留历史实现记录，v76默认计时遗漏以本节更正为准。

## v0.1.76 加载握手修复

日期：2026-10-22
状态：源码修复完成；真实CAD重新加载与性能待验收

v0.1.75原图在进入 .NET 前失败：`atoms-family` 对未定义函数返回 `(nil)`，整个列表仍为真，旧就绪判断因此跳过NETLOAD。测试桩先前用nil表示未加载，漏掉真实返回形态。

v0.1.76改为实际调用同一 `ELNETCOLD76` 入口，参数 `EL_NET_COLD_PING_V1`。精确响应 `EL_NET_COLD_PROBE_V1/0.1.76`（或ResultBuffer封装的单元素字符串列表）才就绪；此分支不取活动文档、不创建事务/CallState、不采集实体或建立缓存。先握手，未就绪则NETLOAD，再握手；失败不得进入选择/计算。首次握手/JIT和加载仍在拾取后的总时间内，不是提前预热。

记录 `COLD_NATIVE_HANDSHAKE`、`COLD_NATIVE_LOAD_BEGIN/RETURNED`、加载/原型批次计时及失败业务payload。业务ResultBuffer最多拆一层外封装，深层嵌套或错误状态拒绝。新DLL/命令使用76，包内部175，保留旧75包。

[Autodesk atoms-family参考](https://help.autodesk.com/cloudhelp/2022/ENU/AutoCAD-AutoLISP-Reference/files/GUID-0B35850D-9E62-446B-BAA2-0598A4BDE3D7.htm)给出了未定义项保留nil占位的示例；有限宿主的就绪判断回归按该语义模拟。


截图中伴随的“全过程文档写入失败”也已处理：本命令原先沿用 `ELSTAT/ELTRACE/ELPOWER` 通用计时名，直接拼入Windows文件名含有斜杠。现在仅对本命令自己创建的计时运行使用 `ELCOLD76`，成功/失败时间轴可按合法文件名归档，外部已有运行名称保留。
