# v26 主面板字符串空值与日志修复

日期：2026-10-09
状态：83 项相关自动检查通过；CAD2020 交付编码及内容一致性检查通过；原图实测待完成

## 问题与修复

- 用户截图：`ELSTAT` 拾取箱体 `2223`、导线 `2227` 后，主面板报告 `stringp nil`，没有日志输出。
- 可复现缺陷：旧 `EL:NewRecord` 对 `(getvar "HANDSEED")` 的 nil 返回值直接执行字符串拼接。新回归在修改前触发字符串错误；旧适配器对未知变量返回 `A0`，未覆盖真实空值契约。
- 修复：新建记录以图纸 UUID、来源句柄、查重后的序号分配身份；不依赖 `HANDSEED`，不改写已有记录 ID。UUID/句柄为空时明确停止。
- 日志遗漏：v25 新入口 `EL:FixedStat` 没有启动日志，内层 `EL:EditPanel` 错误处理也未记录上下文。现已补齐日志生命周期、拾取对象、识别、出线核对、记录初始化、主面板准备和填充阶段，错误先记录后清理。
- 日志不可写时保留命令行错误与阶段；独立打开主面板时另起追加会话。

## 自动检查

在 `tests` 目录执行：

```powershell
python -X utf8 -m unittest test_fixed_diagnostics test_panel test_diagram_store test_diagram_update test_diagnostics
python -X utf8 -m unittest test_source_contracts test_fixed test_simple_flow test_root_init
```

- 第一组 40 项通过，包含 7 项本次新增回归。
- 第二组 43 项中，42 项首次通过。`test_atomic_config_write_restores_previous_file_on_failure` 首次因沙箱系统临时目录权限失败，将 `tempfile.tempdir` 指向仓库 `output/cad2020-026-check` 后单项重跑通过；共 83 个不同检查最终通过。
- 覆盖首次实际面板填充、功率未配置、取消不写草稿、旧身份复用、ID 冲突避让、缺图纸标识、主面板和识别异常、日志不可写、已有简化统计和打包加载。
- Python 启动会打印 `Failed to find real location of F:\Python\Python314\python.exe`，检查实际执行并以上述 unittest 结果和退出码判定。

## 交付检查

执行 `python -X utf8 tools/build_cad2020.py` 生成 `output/应急照明-026.zip` 和同名目录。独立复核全部 17 个 LISP/DCL 的严格 GB2312 编码回转、ZIP/目录字节一致性及 ZIP CRC，全部 LISP 语法解析通过；打包测试检查加载结构。源码和文档仍为 UTF-8。

## 实测边界与复查

上述为实际 LISP 函数配合有限 CAD/DCL 适配器检查，未启动 AutoCAD，未证明原图错误仅来自 `HANDSEED`，也不代表系统图生成、真实动态块、UNDO 或保存重开验收。

完整解压 026，在 AutoCAD 2020 APPLOAD `START-CAD2020.lsp`，选择同包 `src/load.lsp`，确认 v26。原图再次运行 `ELSTAT` 并选原箱体与导线。成功应打开主面板；取消后应打印日志路径。若失败，收集原始错误、失败阶段、最后上下文，以及 `output/ELTRACE-debug.log` 末次 `DIAGNOSTICS 026` 会话。
