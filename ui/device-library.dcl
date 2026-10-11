// Date: 2026-10-11. Status: implemented; native layout acceptance pending.
el_device_library : dialog {
  label = "独立设备库";
  : text { key = "dl_root"; width = 104; }
  : row {
    : column {
      : edit_box { key = "dl_query"; label = "搜索图块名 / 设备名"; edit_width = 28; }
      : toggle { key = "dl_deleted"; label = "同时显示已删除设备"; }
      : list_box { key = "dl_rows"; label = "图块名 / 设备名 / 状态"; width = 48; height = 19; }
      : row {
        : button { key = "dl_new"; label = "新增"; }
        : button { key = "dl_delete"; label = "删除"; }
        : button { key = "dl_restore"; label = "恢复"; }
      }
      : row {
        : button { key = "dl_refresh"; label = "刷新列表"; }
        : button { key = "dl_reload"; label = "重载选中项"; }
        : button { key = "dl_directory"; label = "更改库目录"; }
      }
      : button { key = "dl_import"; label = "导入旧图块功率 / 设备资料"; }
    }
    : boxed_column {
      label = "设备资料";
      : image { key = "dl_image"; width = 44; height = 8; fixed_width = true; fixed_height = true; color = 0; }
      : text { key = "dl_asset"; width = 50; }
      : edit_box { key = "dl_block"; label = "图块名"; edit_width = 30; }
      : edit_box { key = "dl_aliases"; label = "别名（用分号分隔）"; edit_width = 30; }
      : toggle { key = "dl_keep_old"; label = "改名时保留原图块名为别名"; value = "1"; }
      : edit_box { key = "dl_display"; label = "设备名"; edit_width = 30; }
      : edit_box { key = "dl_watts"; label = "单个功率（整数 W）"; edit_width = 12; }
      : toggle { key = "dl_zero"; label = "明确确认此设备为 0W"; }
      : popup_list { key = "dl_ground"; label = "是否地面"; }
      : toggle { key = "dl_active"; label = "启用名称匹配"; value = "1"; }
      : button { key = "dl_pick"; label = "从 CAD 拾取 / 更换图块图形"; }
      : button { key = "dl_repair"; label = "从库内图形修复图例"; }
      : button { key = "dl_save"; label = "保存设备"; is_default = true; }
      : text { label = "资料完整后参与识别；缺资料时保存为草稿。"; }
    }
  }
  : text { key = "dl_status"; width = 104; }
  : text { label = "重新统计时刷新库默认值，保留手填值；原系统图在保存或更新后才变化。"; }
  : row {
    : button { key = "dl_close"; label = "关闭（保留未保存输入）"; is_cancel = true; }
  }
}
el_device_import : dialog {
  label = "导入旧资料";
  : text { label = "选择要导入的资料；同名不同参数必须只选一种。"; }
  : list_box { key = "di_rows"; width = 104; height = 16; multiple_select = true; }
  : text { key = "di_backup"; width = 104; }
  : text { key = "di_status"; width = 104; }
  : text { label = "仅创建待补资料的编辑草稿；原文件保留，不推断地面属性。"; }
  : row {
    : button { key = "di_accept"; label = "导入选中项"; is_default = true; }
    : button { key = "di_cancel"; label = "取消"; is_cancel = true; }
  }
}
