# ELSTAT 空值比较修复
日期：2026-10-08
状态：源码回归及 GB2312 交付检查通过，真实 CAD 复测待执行

## 问题与修复

用户截图显示：ELSTAT 拾取配电箱后报 `参数类型错误: numberp: nil`，尚未进入出线确认。

代码中已复现一个匹配此阶段的缺陷：`EL:StableData` 递归遍历对象数据和列表尾部时，对 `(type nil)` 使用 `=`。AutoLISP 的 `(type nil)` 返回 nil，不能作为数字比较参数。此前测试宿主错误地返回 LIST，并允许符号和空值参与部分 `=` 比较，掩盖了问题。

将类型、角色、状态以及可能为空的用户选项改用 `equal`；保留数值运算与数值比较。相同修复覆盖回车接受出线、退出断口预览、首次进入功率表时尚未配置的类别。测试宿主修正空值类型并拒绝不符合文档的比较参数，原有测试中的符号比较同步修正。

语义依据：[Autodesk type](https://help.autodesk.com/cloudhelp/2026/PTB/AutoCAD-LT-AutoLISP-Reference/files/GUID-506C9CC8-B0BD-4A4C-B4C2-006750504509.htm)、[Autodesk =](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-AutoLISP-Reference/files/GUID-3F1959A8-AEC4-47C5-8E9E-80364BCA93B2.htm)。

## 验证

- 修复测试宿主后，原有对象快照回归及新增空列表回归失败；源码修复后通过。
- 新增调用实际 `c:ELSTAT` 的回归：模拟选择箱体、回车接受一条出线，执行真实快照、拓扑、统计和未配置功率行初始化，确认进入功率表并清理高亮。CAD 数据库和界面接口由测试替代。
- `python -X utf8 -m unittest discover -s tests -v`：84 项通过，0 失败、0 错误。TEMP/TMP 指向仓库 `output/check-tmp`；UTF-8 模式避免测试读取源码时使用系统 GBK 默认编码。
- `python -X utf8 tools/build_cad2020.py`：生成 `应急照明-007.zip`。构建时严格转换 GB2312，并检查 ZIP 内全部 LISP/DCL 与解压目录字节一致。

未取得用户 DWG，也未在真实 AutoCAD 中运行；上述证据确认代码缺陷与自动回归，不能据此排除该图纸中的其他问题。

## CAD 复测

解压完整 007 包，在当前 DWG 中 APPLOAD 包根目录的 `UPDATE-007.lsp`。若请求定位目录，选择同一包的 `src/load.lsp`。已有有效采样及校准配置可沿用。运行 ELSTAT 并选择原配电箱，确认进入出线确认；按实际接线选择 Yes/No，再核对功率表。若仍报错，保留从 v7 加载提示到报错的完整命令记录。
