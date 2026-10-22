# 只读 .NET 冷路径性能原型
日期：2026-10-22
状态：v0.1.82跨电脑名识别修复试用；真实CAD验收待核对

目标是每个新箱体首次完整识别在 3000 ms 内。当前原型用于验证编译执行批量读取、建树和候选发现能减少多少首次处理成本，尚未迁移精确接触、断口规则、编号、源图证明和预览，因此不能用当前阶段低于 3000 ms 宣布完整目标达成。

每次 `ELNETCOLD82` 调用均新建采集、几何、索引及追踪容器，没有预热调用和上次结果缓存。程序集加载/JIT会由外层 LISP 计时覆盖；其他新箱体的每次调用仍重新读取和计算。生产 `ELSTAT` 继续使用原识别路径。

## 输入与结果

`ELNETCOLD82` 接收七个扁平参数：原 `EL:PresetSelection` 选择集、箱体 ENAME、逗号分隔的起点导线句柄、设备容差、Dmax、边界容差、JSON 报告绝对路径。返回 `(jsonText ((handle minPoint maxPoint) ...))`，最多抽查 16 个块边界。

选择集保持原 Model/预设范围与输入顺序；原型尚未应用业务层的块名、角色、导线配色及线型过滤，因此候选为选择集上界，不能与正式连通设备数直接比较。宽线、弧段和 OCS 数据只参与保守宽筛；精确连通判定仍属于后续迁移工作。保守追踪并不构成完整性的证明。

只使用 `OpenMode.ForRead`，不提交事务、不保存统计、不修改实体或 Xrecord。期间监测源对象事件、当前文档和 DBMOD；对象读取、边界缺失、源变化或候选展开达到显式限额均返回 `ERROR`，不得作为业务结果继续处理。报告只写入插件 `output` 目录。

## 构建与回归

离线构建：`python -B -X utf8 tools/build_cold_recognition.py`。

核心回归：`python -B -X utf8 tools/build_cold_recognition.py --test`。测试以现有 LISP 查询顺序为固定对照，覆盖三轴树、退化边界、射线、重复键拒绝及独立调用。当前签名只接受 ASCII，避免猜测 CAD 2020 的非 ASCII 排序。

目标 `.NET Framework 4.7 / x64 / AutoCAD 2020 API 23.1.0.0`。构建脚本使用本机引用程序集，不下载依赖，不把 Autodesk 程序集装入交付包。可用 `--framework-dir`、`--acmgd`、`--accoremgd`、`--acdbmgd` 覆盖路径。

## 原图测试

加载交付包的 `ELCOLD82.lsp`，运行 `ELCOLD82`，模式默认 `Both`，直接回车即在候选阶段之后对同次拾取输入另跑完整旧路径的只读识别，报告保留编号及业务字段，不打开结果面板，不写入图纸。如需仅测候选阶段，手动选择 `Prototype`。运行 `ELDIAG` 导出 `cold-probe.json`、`cold-comparison.eld` 和现有性能日志。

从新开 CAD 的第一次调用开始记录，至少测试两个不同新箱体。`prototype-pick-to-return-ms` 包含拾取结束后的清理、首次 DLL 加载、选择、桥接、写 JSON 和 COM 边界抽查。`legacy-full-ms` 是完整旧识别的单独对照；两者计算范围不同，不能相减作为完整识别提速。

包围盒抽查应 `missing=0 / different=0`；这只验证抽样边界，不代表全部业务规则等价。本机编译和有限宿主回归不能代替真实 AutoCAD/original DWG 验收。


## v0.1.82 天正图块跨电脑名识别修复
日期：2026-10-22
状态：有限回放已复现并修复；原生CAD验收待完成

统计面板请 APPLOAD `ELFULL82.lsp` 后运行 `ELFULL82`。天正设备名称的末尾电脑标记按统一设备编号匹配，例如 `(longys)` 与 `(Zhangyufeng)`，并读取同一库项功率；原始名称精确匹配优先，多个匹配项不猜值。此次修改位于完整LISP路径的名称筛选和库查询，保持实际图形接触、原始块定义缓存及只读候选算法。

内部181，DLL为 `EmergencyLighting.ColdRecognition82.dll`，原生入口 `ELNETCOLD82`，握手 `EL_NET_COLD_PROBE_V1/0.1.82`。ELCOLD82仍不打开面板。下面保留各历史版本当时的诊断状态；v0.1.81尚未复现的名称筛选差异已由本版回归定位，真实原图仍需重新拾取验收。

## v0.1.81 本地诊断与生成修复

日期：2026-10-22
状态：本地测试包；原始B灯四角回放通过，用户最新现场漏判尚未复现

面板与生成请 APPLOAD `ELFULL81.lsp` 后运行 `ELFULL81`；只读对照为 `ELCOLD81`，Both仍不打开面板。内部180，DLL为 `EmergencyLighting.ColdRecognition81.dll`，握手 `EL_NET_COLD_PROBE_V1/0.1.81`；候选算法未改变。

本包包含此前源码中的面板生命周期、回路汇总、闭合边诊断和空功率生成修复。新增 `DEVICE_WIRE_MISS_DETAILS`，仅在计时和业务日志开启且候选通过粗筛后细判仍失败时记录，每轮最多8项、设备最多32条线段、导线最多8条线段，省略标记可见。仅使用已读取的几何，不增加CAD/COM读取；此日志不会覆盖被图层/名称或粗筛排除的对象。

项目已保存的原始B灯四个LINE外端均能通过完整识别回放，现场新图仍需最小DWG/DXF定位差异。本版不将截图等同于原生验收，不放宽接触规则，不用包围盒代替实际几何。下面保留各历史版本当时的状态记录；其中面板/生成源码补充已经纳入v0.1.81。

## v0.1.80 默认完整旧路径对照

日期：2026-10-22
状态：测试交付；原图对照及完整识别3秒目标待验收

模式提示默认值和空输入处理均改为 `Both`。按回车后先执行.NET候选阶段，再执行完整旧路径只读对照；手动选择 `Prototype` 仍只运行候选。对照不会打开统计面板、保存统计或修改图纸。报告应有 `mode=Both`、`legacy-executed=T` 和单独的 `legacy-full-ms`；候选阶段与完整旧路径的时间继续分别记录。

入口为 `ELCOLD80` / `ELNETCOLD80`，DLL为 `EmergencyLighting.ColdRecognition80.dll`，精确握手为 `EL_NET_COLD_PROBE_V1/0.1.80`，内部179（`runtime-179` / `package-179.marker`）。既有候选算法和诊断标记 `2026-10-22-logs1` 保持。旧版交付物保留。每轮结束或报错后立即 `ELDIAG`，提供诊断输出及完整命令行；正式面板入口为 `ELFULL80.lsp → ELFULL80`。

## 面板入口与完整旧路径诊断补充

日期：2026-10-22
状态：源码已补充，未打包；新增诊断待原图复测

用户已明确本次现象是“没有打开统计面板”。`output (35).zip` 中运行的是 `ELCOLD80 / Both`，这是只读性能对照，完成候选和旧路径识别后不会调用统计面板；本次记录没有证明发生面板创建异常。测试统计面板应在已有v0.1.80交付目录内 APPLOAD `ELFULL80.lsp`，再运行 `ELFULL80`，由该入口初始化当前完整代码并调用 `ELSTAT`。不要直接加载仓库UTF-8源码。

本轮新增 `legacy-diagnostic-revision=2026-10-22-legacy2`，原.NET诊断标记继续使用 `2026-10-22-logs1`：

- `COLD_PANEL_ROUTE` 和对照ELD的 `panel-route` 明确记录 `panel-requested=nil`、只读策略以及面板入口文件/命令。命令开始即显示不打开面板和正确入口，Both/Prototype均保持原有只读边界。
- 正式 `ELSTAT` 入口及 `EL:PanelDialogWork` 新增 `panel-*` 性能字段，记录目录确认、DCL路径/加载返回码、对话框名称/位置及 `new_dialog` 返回、开始等待次数、返回状态/动作、失败前最后阶段和原始报错。业务日志开启时另记录 `PANEL_LIFECYCLE`。这些字段使用现有内存计数和延迟导出，不新增逐步写盘；DCL加载或创建失败会保留本轮导出上下文，防止旧成功记录遮蔽失败。正常关闭返回0与未进入等待明确区分；`new_dialog`成功只代表创建接口返回，不能证明原生窗口已可见。
- `COLD_LEGACY_CIRCUIT` 记录每条回路的实际起点、编号、完成状态、导线/设备数和回路问题。`COLD_LEGACY_SUMMARY` 区分整体返回、业务完成、顶层/快照/回路问题和零设备数量，随对照ELD的 `legacy.summary` 一起保留。命令行直接列出问题回路和对象句柄。汇总最多32条回路、每条10项问题，省略数明确记录；原有完整业务诊断仍保留。
- 仅在 `EL:ColdLegacy` 的动态作用域启用 `CIRCUIT_CLOSED_EDGE`，记录触发闭合判定的from/to/parent、实际起点、两侧树路径、邻居及已采集的对象几何摘要，不重新调用CAD/COM或展开设备轮廓。每轮最多20条闭合边，路径最多32节点、邻居最多16项、几何线段最多8段，省略数/截断标记可见。退出或报错后恢复开关；正常ELSTAT路径默认不启用额外图证据。

附件另有独立的识别观测：Both返回5条回路，完整旧路径21266 ms、候选阶段2735 ms；原生候选错误数0、源保护通过、16项边界抽查一致。业务结果 `complete=nil`：R2含 `CLOSED_CIRCUIT`，对象 `1449F`、关联 `D410`，37个设备；R5包含2条导线但0个设备，其他三条回路设备数分别为11、3、3。顶层 `issues` 为空而回路内部有问题，新增汇总用于展示这一差异。这些观测不是本次未打开面板的原因；零设备不自动当作故障，闭合判定需新增边证据和原图核对。

本次不改变连接、闭合判定、设备数量、功率或是否允许生成，未生成新的交付包、未重新发布或覆盖已有v0.1.80文件。78项定向回归通过，覆盖入口不调用面板、DCL失败、创建失败、正常关闭、失败导出上下文、既有展开/收起及位置保留、嵌套问题汇总、上限、开关恢复和图追踪结果等价。5个修改的LISP源码通过语法解析及严格GB2312可编码检查；这些结果不代替CAD验收。记录见 `tests/evidence/2026-10-22-legacy-business-diagnostics.json`。

## v0.1.79 诊断补充（历史记录）

日期：2026-10-22
状态：v0.1.79 诊断测试包；新增日志待原图复测

v0.1.78 的原图资料 `output (33).zip` 已得到 `PROTOTYPE_COARSE_ONLY`，`error-count=0`、源保护原因列表为空，DBMOD 为 21→21；LISP 边界抽查 16 项，缺失和差异均为 0。拾取结束至候选原型返回 1922 ms，包含本次加载/握手 1672 ms；托管阶段最终报告写盘前为 208.6376 ms。模式为 `Prototype`，`legacy` 为空，因此附件没有执行完整旧路径识别、编号或统计面板，不能从这次候选阶段返回判断完整流程已修复。

本次版本更正为 v0.1.79，入口为 `ELCOLD79` / `ELNETCOLD79`，DLL 为 `EmergencyLighting.ColdRecognition79.dll`，内部178（`runtime-178` / `package-178.marker`）。候选规则保持，诊断修订标记为 `2026-10-22-logs1`：

- `ELTRACE-debug.log` 新增 `COLD_CHECKPOINT`，区分配置、预设、拾取、加载、选择集、原型调用、返回校验、COM 抽查、源图复核、完整旧路径对照及报告写入；同时记录模式、箱体/起点句柄、起点端部、预设图层、容差、选择集数量和报告路径。`COLD_FAILURE` 保留本轮最后阶段及上下文，清理预览后也可查；日志写入失败时命令行仍输出失败上下文。
- `COLD_NATIVE_RETURN` 保存返回类型、原型状态、JSON 长度及最多 4096 字符前缀，截断会明确标记，完整内容仍以 JSON 为准。`COLD_BOUNDS_SAMPLE` 最多记录 16 个句柄的预期/实际边界及判定，`COLD_BOUNDS_AUDIT` 保存总数；命令行同步显示缺失与差异数量。抽查差异只增加诊断标记，不改变本次原有候选判定。
- 原型 JSON 新增 `diagnostic-revision`、`assembly`、`stages`、`last-phase`、`root-diagnostics` 和 `error-groups`。DLL 身份包含名称、版本、实际加载位置和 `module-version-id`；批次检查点最多 48 条、根导线摘要最多 32 条，不逐对象写盘。异常细节最多保留 10 条，包括句柄、实体类型、读取子步骤、原始消息、`HResult`、CAD `ErrorStatus`、最多 4096 字符栈及三层内部异常；分组总数记录同类错误数量。
- 最外层桥接/序列化异常保留实际原因，尽量回写原 JSON，失败时在命令行输出阶段及原始异常。对照 ELD 增加 `diagnostic-revision`、`legacy-executed` 和 `bounds-audit-passed`，明确候选完成与完整识别的执行范围。

每轮开始清除当前图纸上一轮的原型报告关联，避免拾取、配置或 NETLOAD 提前失败时 `ELDIAG` 误带旧报告；其他图纸的关联仍保留。必要检查：41 项 LISP 定向回归、21 组 .NET 核心回归（其中新增异常诊断 4 组）通过，AutoCAD 2020 API 23.1 引用离线编译无警告、无错误。上述检查不代表新增日志已在真实 CAD 中验收。

下一次使用包含这些源码的 GB2312 交付文件，在新开的 AutoCAD 中运行 `ELCOLD79`。先按本次 2604F 箱体和五个起点复测；若要检查完整旧路径，模式选择 `Both`。结束或报错后立即运行 `ELDIAG`，一并提供 `ELTRACE-debug.log`、`cold-probe.json`、`cold-comparison.eld` 及命令行。核对两侧 `diagnostic-revision` 为 `2026-10-22-logs1`，可排除仍在运行旧文件；测试时加载包内 GB2312 文件，不直接加载仓库 UTF-8 源码。

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
