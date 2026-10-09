# v27 模板候选值读取与中文选择菜单

日期：2026-10-09
状态：99 项相关自动检查通过；交付编码及内容一致性检查通过；真实 CAD 验收待执行

## 现象及修复

用户在 `ELTEMPLATE` 中看到 `可见性1 (#<variant 8 0.3kW> ...)`，不知道序号含义，输入重复对应后模板未保存。旧代码只解开候选数组外层，内部 VARIANT 仍参与比较、打印和保存校验，名称相同也无法自动识别。

`EL:DynamicValueData` 递归展开 VARIANT、SAFEARRAY 和数组元素，`EL:AllowedValues` 返回普通候选列表。状态仍保留字符串或数字类型，共用动态属性写入和模板运行时校验复用同一入口。

`EL:FixedCapture` 对唯一匹配的属性和同名状态自动对应并显示结果；自定义状态采用含目标含义、选项编号和名称的中文菜单。超范围重选；回车取消；已分配值及其他目标的明确名称从手选菜单排除。只读、空值或不足三种不同有效状态的属性不成为选项。模板采集不写样本块，未完成不保存配置；写入失败不报告成功。

## 验证

在 `tests` 目录运行：

```powershell
python -X utf8 -m unittest test_template_choices test_fixed test_kernel test_diagram_update test_diagnostics test_fixed_diagnostics
python -X utf8 -m unittest test_root_init
```

80 项通过，其中 `test_template_choices` 新增 12 项：逐元素转换、保留数值类型、截图同名六档不询问编号且通过配置校验、动态属性写入回读、自定义名称菜单、非法编号重试、歧义属性选择、两类回车取消、只读/空/重复值拒绝、部分同名状态保留、配置写入失败提示。

另有 19 项根目录与交付加载检查通过，共 99 项。本次没有重跑全量套件。Python 启动仍打印既有路径定位提示，但检查实际执行且退出码为 0。

有限适配器模拟外层 VARIANT、SAFEARRAY、内部 VARIANT。旧代码在同名样本上错误进入 `GETINT`，转换及动态属性写入测试失败；修复后通过。适配器替换 COM、拾取与配置写入边界，执行真实命令、候选解析、状态对应、模板及配置校验函数。

## 交付与实测

构建命令：`python -X utf8 tools/build_cad2020.py`。交付为 `output/应急照明-027.zip` 与同名解压目录；源码 UTF-8，交付全部 LISP/DCL 严格 GB2312。

交付复核：17 个 LISP/DCL 严格 GB2312 解码及回编码通过，ZIP CRC、ZIP 与目录逐文件字节一致性通过，全部交付 LISP 语法解析通过。历史 v25/v26 证据保留其原日期与版本含义。

未启动真实 AutoCAD，未获得用户 DWG 的动态块属性切换、模板保存重开或系统图生成验收。复测：APPLOAD 新包 `START-CAD2020.lsp`，选择同包 `src/load.lsp`，确认 v27，重新执行 `ELTEMPLATE` 并选择原箱体、回路样本。同名档位应自动对应；自定义状态按当前菜单选择，成功时显示“模板设置已保存”。
