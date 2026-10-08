# 断口预览默认参数与搜索上限交互
日期：2026-10-08
状态：源码及交付检查通过，真实 CAD 新交互待复测

## 修改

- ELGAPTEST 无已保存参数时直接采用默认值，已有参数直接沿用，不再在入口逐项请求回车。
- 新增 Range（输入 R），只修改 Dmax 并重查当前端点；其他参数保持原值，超出约束的输入重新询问。
- Params 只在用户主动选择时逐项输入，基于当前参数修改，修复回车把自定义值恢复为建议值的问题。
- 菜单显示中文说明、当前搜索上限和预览参数不保存的提示。Next、Swap、Locate、Details、Exit 保留原行为。
- 默认 200 mm 仅为候选搜索范围；扩大范围仍经过原有几何检查，不自动保存连接或修改正式统计参数。

## 验证

- `python -X utf8 -m unittest discover -s tests -p test_cad_adapter.py -v`：16 项通过。新增覆盖自动默认值、350 mm 断口由 200 扩大到 500 后匹配且不重新拾取、非法上限与回车保留、高级参数沿用自定义值。
- `python -X utf8 -m unittest discover -s tests -p test_source_contracts.py -v`：5 项通过。首次运行临时目录受沙箱限制，改为仓库 `output/check-tmp` 后通过；没有改动测试断言。
- `python -X utf8 tools/build_cad2020.py`：生成 `应急照明-009.zip` 及同名目录，全部 LISP/DCL 严格转换 GB2312，ZIP 和目录文件字节一致。
- `git diff-files --check`：通过。

用户提供的 v8 截图显示已进入断口预览菜单；它不构成 v9 新交互或真实断口匹配的验收证据。上述命令回归使用数据库与界面适配器，不运行 AutoCAD。

## 复测

解压完整 009 包，APPLOAD 根目录的 UPDATE-009.lsp，确认显示 CAD2020 v9 后运行 ELGAPTEST。首次无配置时选择导线层样本后应直接进入断口拾取，不再要求确认 7 个参数。对超过 200 mm 的断口输入 R，再输入能覆盖实际长度的上限，核对原端点预览结果。正式统计在 ELSETUP 中设置同样上限并核对。
