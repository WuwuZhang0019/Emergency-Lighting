// EL_BOX_UI_011
el_exits : dialog {
  label = "整箱出口集中核对";
  : text { label = "点选后返回图面查看出线，按 Enter 返回；进线及非出线不选。"; }
  : list_box { key = "exits"; width = 88; height = 14; multiple_select = true; }
  : text { key = "scope_info"; width = 88; }
  : toggle { key = "scope_exclude"; label = "已核对：明确排除上述未纳入图层的箱边导线"; }
  : toggle { key = "role_recheck"; label = "重新核对已知设备角色（需要修正分类时勾选）"; }
  : button { key = "exit_preview"; label = "查看选中出线（返回图面）"; }
  : button { key = "exit_all"; label = "全选出线（请取消进线）"; }
  : button { key = "add_wire"; label = "补充导线图层"; }
  ok_cancel;
}
el_power : dialog {
  label = "应急照明设备功率表（整数瓦）";
  : list_box { key = "circuit_rows"; label = "回路 / 出口 / 数量 / 功率 / 识别状态"; width = 110; height = 6; }
  : toggle { key = "save_library"; label = "将本次明确确认的功率同时保存到设备库"; }
  : list_box { key = "rows"; label = "图块 / 本箱数量 / 各回路数量"; width = 88; height = 12; }
  : text { key = "source"; width = 80; }
  : popup_list { key = "category"; label = "确认类别"; }
  : edit_box { key = "display"; label = "显示名称"; edit_width = 40; }
  : edit_box { key = "watts"; label = "单个功率 W（整数）"; edit_width = 12; }
  : toggle { key = "zero"; label = "明确确认本行 0W 用途"; }
  : text { key = "error"; width = 80; }
  : row {
    : button { key = "save_row"; label = "保存此行"; }
    : button { key = "locate"; label = "定位图块"; }
  }
  : text { label = "先保存每个修改行；数量来自识别，不能直接手改。未知类别请明确选择。"; }
  ok_cancel;
}

el_roles : dialog {
  label = "连接图块按身份集中分类";
  : toggle { key = "role_library"; label = "将已确认角色同时保存到设备库"; }
  : list_box { key = "role_rows"; width = 88; height = 12; }
  : popup_list { key = "role_choice"; label = "角色"; }
  : text { key = "role_status"; width = 80; }
  : row {
    : button { key = "role_apply"; label = "确认本类角色"; }
    : button { key = "role_locate"; label = "定位全部实例"; }
  }
  : text { label = "未确认的类型保留为未知，不参与导通或负载计算。"; }
  ok_cancel;
}

// Date: 2026-10-08. Header and data share font, tabs and list-box insets.
el_device_columns : list_box {
  width = 85;
  fixed_width_font = true;
  tabs = "54 64";
  tab_truncate = true;
}

// Date: 2026-10-08. Simple device table: two picks, no role/exit review.
el_devices : dialog {
  label = "设备数量与功率";
  : text { label = "点选设备可在图面查看，按 Enter 返回；功率按图块名自动记住。"; }
  : el_device_columns { key = "s_header"; height = 1.5; fixed_height = true; is_enabled = false; is_tab_stop = false; }
  : el_device_columns { key = "s_names"; height = 13; }
  : text { key = "s_selected"; width = 85; }
  : edit_box { key = "s_edit"; label = "单个功率（W）"; edit_width = 12; }
  : text { key = "s_status"; width = 85; }
  : button { key = "s_locate"; label = "在图上查看该设备"; }
  : row {
    : button { key = "accept"; label = "保存并关闭"; is_default = true; }
    : button { key = "cancel"; label = "取消"; is_cancel = true; }
  }
}
