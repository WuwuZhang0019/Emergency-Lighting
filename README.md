# 应急照明回路统计与系统图生成

日期：2026-10-05。状态：P01—P05 源码和 40 项自动检查完成；真实 DWG 基线、动态块适配及集中 CAD 验收待完成。

从模型空间拾取应急照明配电箱，按独立出线识别回路，统计设备，确认整数瓦功率，检查每回路不超过 172W，再用用户真实动态块排布系统图。图层采样、断口试查／配对、跨层引线、功率 DCL、模板采集、预览和生成均已提供源码。

## 加载与使用

目标：Windows AutoCAD 2021+，LISPSYS=1/2。保留整个仓库目录，在可信、可写的位置加载 `src/load.lsp`。详细路径设置、命令顺序和支持边界见 [03 加载使用与验收说明](docs/03_加载使用与验收说明.md)。

基本流程：`ELSETUP` → `ELGAPTEST` → `ELSTAT` → `ELTEMPLATE` → `ELGEN`。不完整、功率缺项、归属冲突、超限或源图变化均禁用正式生成；统计可先用 `ELSAVERESULT` 独立保存。

## 方案与进度

- [01 应急照明回路统计与系统图生成方案](docs/01_应急照明回路统计与系统图生成方案.md)
- [02 断线导线几何续接算法方案](docs/02_断线导线几何续接算法方案.md)
- [逐阶段实施状态及证据映射](tests/evidence/implementation-status.md)
- [集中 CAD 验收清单（未执行）](tests/evidence/cad-acceptance.md)
- [原始参考 LSP](参考/FAS_topological_graphV2%20-%20副本.lsp)（保留原样，无 XFTJ 依赖）

## 验证

```bash
python3 tests/fixtures/generate_fixture.py
python3 tests/run_checks.py
```

40 项检查已通过，证据保存在 [automated-checks.json](tests/evidence/automated-checks.json)。测试解释实际 LSP 纯函数并检查源码／替代接口，不代表 AutoCAD 编译或实操通过。

[合成 CAD 样图](tests/fixtures/cad-plan.dxf) 包含三出线、混合导线类型、设备边界、断口与横穿线；[人工规则预期](tests/fixtures/cad-plan.expected.json) 为 10W／2W／5W、总计 17W。该 DXF 未在本环境导入 CAD，也不包含真实动态块。

## 目录

- `src/`：配置、几何、拓扑、统计、生成与命令入口。
- `ui/`：设备功率 DCL；`config/`：运行时配置；`output/`：统计／生成记录。
- `templates/`：真实模板采集字段说明，实际动态块待提供。
- `tests/fixtures/`：JSON／DXF 合成基线；`tests/evidence/`：自动结果与待执行 CAD 清单。
- `docs/`：方案、状态和使用说明；`参考/`：原参考代码。

按 P00—P06 每阶段单独提交，运行 `git log --reverse --oneline 366c05a..HEAD` 查看。P00 真实样图校准、P05 动态块实际适配及 P06 CAD 退出条件仍保留；弧形断口自动延续、外参、跨 DWG 和大图性能未验收。
