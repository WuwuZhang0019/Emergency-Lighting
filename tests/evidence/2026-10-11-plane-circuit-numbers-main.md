# 平面回路编号功能合入 main 检查记录

日期：2026-10-11
状态：合并后的聚焦离线检查通过；真实 CAD 待验收，本次不打包

合并前 `main` 为 `e1e939b`，功能分支 `codex/plane-circuit-numbers` 为 `d583593`，共同起点为 `d0703ba`。保留功能分支的六个阶段提交，同时保留 `main` 的空图面板初始化修复与诊断日志。

源码自动合并。`README.md` 与 `docs/03_加载使用与验收说明.md` 的说明冲突已人工整理：保留 v96 的历史交付说明，新增平面编号源码功能说明，章节使用 0.23，明确历史包不包含新编号功能。

使用有限 AutoLISP、CAD 与 DCL 适配器串行执行以下九组检查，全部通过，共 172 项：

| 检查组 | 项数 |
| --- | ---: |
| `test_circuit_number` | 39 |
| `test_empty_panel` | 8 |
| `test_panel` | 8 |
| `test_panel_number` | 6 |
| `test_cckk_panel_command` | 23 |
| `test_diagram_update` | 45 |
| `test_post_stat_workflow` | 24 |
| `test_source_contracts` | 5 |
| `test_root_init.RootInitTests` | 14 |

检查涵盖原生样本编号读取、首段范围、无标号补号、面板与系统图编号一致、旧面板源编号变化拦截、生成及更新的失败回退、空图初始面板和完整模块入口。`test_root_init` 仅执行 `RootInitTests`，未执行会构建交付包的检查类。

另对 19 个源码 LISP 和 1 个 DCL 执行严格 UTF-8 解码、内存内严格 GB2312 往返检查；全部 LISP 通过解析，构建脚本通过 Python 语法解析。未运行构建脚本，未生成交付目录、ZIP 或新启动文件。

合并后的暂存区通过 `git diff --cached --check`，未残留冲突标记。以上检查不代表 AutoCAD 2020 或现场 DWG 验收；仍需按 [原编号功能 CAD 验收清单](2026-10-11-plane-circuit-numbers.md) 验证，并复测 [v96 空图面板场景](../../docs/更新记录/2026-10-11-空图面板初始化-096.md)。AutoCAD 2020 验证前需准备严格 GB2312 加载文件，不能直接加载仓库 UTF-8 源码。
