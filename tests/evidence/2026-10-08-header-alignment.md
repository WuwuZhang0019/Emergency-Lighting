# v23 设备表头对齐
日期：2026-10-08
状态：布局实现、33 项专项检查及交付编码检查完成；真实 CAD 显示待复测

用户截图显示数据的数量和功率位于表头左侧。v22 用三个独立 text 控件作为表头，其字体宽度及 row 间距与数据 list_box 的等宽字体、制表位不一致。

v23 将表头和数据改为继承同一 `el_device_columns` 定义的列表，共用宽度 85、等宽字体和 `54 64` 制表位。表头为固定单行、不可选择的列表，内容与数据一样用制表符分列；滚动设备列表不会移走表头。设备行索引、选择、功率和识别逻辑不变。

接口属性依据：[Autodesk list_box](https://help.autodesk.com/cloudhelp/2022/ENU/AutoCAD-AutoLISP-Reference/files/GUID-C01592FC-3A6B-48A2-952C-15307F0DAC5F.htm)。这说明属性可用，不代表真实 CAD 视觉验收。

本次运行现有源码约束、设备表交互／保存及加载打包专项检查，33 项通过；结果和当前文件哈希写入同目录 `2026-10-08-header-alignment.json`。`automated-checks.json` 是 v22 的全量历史记录。023 交付中 12 个 LISP/DCL 严格转换 GB2312，ZIP 与解压目录字节一致性检查通过。

升级时完整解压 023，复制旧包的 `config/block-powers.eld`，APPLOAD 新包启动文件并选择新包 `src/load.lsp`。仅更新内存 LISP、继续使用旧目录的 DCL 不能应用此次布局修复。
