# 124 交付隔离及并行改动记录

日期：2026-10-13
状态：本任务已提交；并行工作目录保持原状

本任务工作树为 `C:\Users\Zyf\.codex\worktrees\circuit-start-pick\Emergency-Lighting`，分支为 `codex/circuit-start-pick`。功能提交为 `91088ca`，随后的交付编号调整为 124。本任务开始时原目录及新工作树均干净；功能提交后复核，原目录出现另一并行任务的存储拆分和网络复用变更。

以下为当时原目录 `G:\rust\AI画CAD\Emergency-Lighting` 的剩余变更快照。归属为其他并行工作，具体操作者未确认；不属于本次拾取任务，全部保留，不在本工作树暂存或提交。并行任务可能继续修改，本文不是该目录的实时状态。

## 合并冲突

- `.gitignore`
- `src/diagram-store.lsp`

## 其他已跟踪及新增改动

- `docs/17_存储拆分与按变化范围计算实施方案.md`
- `docs/更新记录/117-监控计时与UTF8输出.md`
- `docs/更新记录/118-按箱拆分存储与兼容迁移.md`
- `docs/更新记录/122-按变化回路计算与网络复用.md`
- `src/common.lsp`
- `src/config.lsp`
- `src/device-inputs.lsp`
- `src/diagram-commands.lsp`
- `src/diagram-update.lsp`
- `src/load.lsp`
- `src/panel.lsp`
- `src/simple.lsp`
- `src/statistics.lsp`
- `src/store-split.lsp`
- `tests/monitor_io.py`
- `tests/test_change_scope.py`
- `tests/test_monitor.py`
- `tests/test_network_proof.py`
- `tests/test_root_init.py`
- `tests/test_saved_records.py`
- `tests/test_shared_panel_power.py`
- `tests/test_store_split.py`
- `tools/build_cad2020.py`

本工作树的 `output/应急照明-122/`、`output/应急照明-122.zip` 为先前生成的本分支检查包，`output/应急照明-124/`、`output/应急照明-124.zip` 为最终交付包。它们及既有测试临时目录按精确规则忽略、不提交；此次新增源码、测试、证据、文档和构建脚本均纳入本任务提交。
