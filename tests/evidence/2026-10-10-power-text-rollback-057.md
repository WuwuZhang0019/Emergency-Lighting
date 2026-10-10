# 首回路功率创建及空返回事务清理
日期：2026-10-10
状态：108 项不同的定向自动检查通过；真实 AutoCAD 2020 待复测

## 现场证据

用户日志 `ELTRACE-debug(9).log`：6977 的 CCKK2 输入为两回路、85/20W；13923—13927 完成箱体与第一条回路块；13928 TX_WRITE 返回 nil，没有第一条完成及第二条开始事件。13929 open/dirty 仍存在，随后恢复并写 MarkStale，截图保留半张系统图。

可确认失败区间是第一条功率文字/关联处理，原日志不足以指明具体 ActiveX 属性或关联写入失败。可确认事务没有按预期撤销，空返回未进入捕获异常分支。修复这两处，不改识别规则或回路功率计算。

## 变更

- 固定功率通过 EL:CCKKText 的原生 entmake，内容来自实际 row.text；显式读取实体内容、字体、图层、字高、宽度和对齐位置。新增和更新缺失功率共用。
- 关联写入增加 TAG_ENTITY 日志和 OwnedEntity 回读。保留 UID，不靠序号/距离/功率猜身份。
- 空返回不依赖 exit 转异常：保留事务标记并进入撤销，清理后验证活动标记消失。撤销失败不执行自动恢复和后续状态写入。

## 定向验证

模块：test_cckk_panel_command、test_diagram_update、test_source_contracts、test_post_stat_workflow、test_cckk_assembly、test_fixed、test_template_choices、test_insert_retry。

107 项组合检查通过，耗时 52.699 秒。最后补充回滚空返回状态判定后，4 项回滚专项检查通过，其中 1 项新增、3 项复核，共 108 项不同检查。

新增覆盖：固定功率禁止经过通用 ActiveX 注释路径；85W/20W 原生 TEXT DXF、对齐与真实回路位置；第一条后返回 nil 能清理半图并重试成功；第二条功率创建失败全部回滚；关联 entmod 假成功的回读拒绝；nil 不通过 exit 转异常；撤销无操作保留标记；撤销返回空值且事务未关闭时不报告清理成功；撤销失败不再自动启动 MarkStale。

交付为完整应急照明-057 目录和 ZIP；严格 GB2312 编码、ZIP/目录一致性及交付 LISP 解析检查。自动适配器不等同原图中的 AutoCAD 鼠标放置、COM、显示、保存重开和 UNDO 验收。
