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

// Date: 2026-10-09. Eight synchronized rows; real last-column toggles.
el_fixed_exits : dialog {
  label = "已完成识别：核对出线与连接设备";
  : text { label = "默认全选。仅取消明确的进线或非本箱出线；有问题的实际回路仍须保留。"; }
  : list_box { key = "f_exits"; label = "实际出线候选 / 已识别设备数量"; width = 88; height = 6; multiple_select = true; }
  : boxed_column { label = "所选出线设备：图面实景 / 数量";
    : row { : image_button { key = "f_image0"; width = 22; height = 4; fixed_width = true; fixed_height = true; color = 0; } : column { : text { key = "f_count0"; width = 26; } : text { key = "f_hint0"; width = 26; } } }
    : row { : image_button { key = "f_image1"; width = 22; height = 4; fixed_width = true; fixed_height = true; color = 0; } : column { : text { key = "f_count1"; width = 26; } : text { key = "f_hint1"; width = 26; } } }
    : row { : image_button { key = "f_image2"; width = 22; height = 4; fixed_width = true; fixed_height = true; color = 0; } : column { : text { key = "f_count2"; width = 26; } : text { key = "f_hint2"; width = 26; } } }
    : row { : image_button { key = "f_image3"; width = 22; height = 4; fixed_width = true; fixed_height = true; color = 0; } : column { : text { key = "f_count3"; width = 26; } : text { key = "f_hint3"; width = 26; } } }
    : row { : button { key = "f_prev"; label = "上一页"; } : text { key = "f_page"; width = 10; } : button { key = "f_next"; label = "下一页"; } }
  }
  : text { key = "f_status"; width = 88; }
  : button { key = "f_preview"; label = "在图面查看所选回路导线和设备"; }
  : row {
    : button { key = "accept"; label = "确认出线，进入功率表"; is_default = true; }
    : button { key = "cancel"; label = "取消"; is_cancel = true; }
  }
}
// Date: 2026-10-10. Status: implemented; unified block settings table.
el_panel : dialog {
  label = "回路与图块设置";
  : radio_row { key = "p_capacity"; label = "当前配电箱容量档位";
    : radio_button { key = "p_300"; label = "0.3kW"; value = "1"; }
    : radio_button { key = "p_600"; label = "0.6kW"; }
    : radio_button { key = "p_1000"; label = "1kW"; }
  }
  : text { key = "p_capacity_status"; width = 100; }
  : row {
    : boxed_column { label = "回路 / 类型 / 功率 / 状态";
      : row { : text { key = "p_row0"; width = 43; fixed_width = true; } : button { key = "p_select0"; label = "查看"; width = 5; fixed_width = true; } }
      : row { : text { key = "p_row1"; width = 43; fixed_width = true; } : button { key = "p_select1"; label = "查看"; width = 5; fixed_width = true; } }
      : row { : text { key = "p_row2"; width = 43; fixed_width = true; } : button { key = "p_select2"; label = "查看"; width = 5; fixed_width = true; } }
      : row { : text { key = "p_row3"; width = 43; fixed_width = true; } : button { key = "p_select3"; label = "查看"; width = 5; fixed_width = true; } }
      : row { : text { key = "p_row4"; width = 43; fixed_width = true; } : button { key = "p_select4"; label = "查看"; width = 5; fixed_width = true; } }
      : row { : text { key = "p_row5"; width = 43; fixed_width = true; } : button { key = "p_select5"; label = "查看"; width = 5; fixed_width = true; } }
      : row { : text { key = "p_row6"; width = 43; fixed_width = true; } : button { key = "p_select6"; label = "查看"; width = 5; fixed_width = true; } }
      : row { : text { key = "p_row7"; width = 43; fixed_width = true; } : button { key = "p_select7"; label = "查看"; width = 5; fixed_width = true; } }
      : row { : button { key = "p_prev"; label = "上一页"; } : button { key = "p_next"; label = "下一页"; } }
      : button { key = "f_preview"; label = "在图面查看全部回路导线和设备"; }
    }
    : boxed_column { label = "图块表（本箱全部图块）";
      : row {
        : text { label = "图块"; width = 22; fixed_width = true; }
        : text { label = "单个功率(W)"; width = 16; fixed_width = true; }
        : text { label = "是否为地面"; width = 14; fixed_width = true; }
      }
      : row {
        : image_button { key = "f_image0"; width = 22; height = 4; fixed_width = true; fixed_height = true; color = 0; }
        : edit_box { key = "b_watts0"; width = 16; fixed_width = true; edit_width = 10; allow_accept = false; }
        : toggle { key = "b_ground0"; label = "是"; width = 14; fixed_width = true; }
      }
      : row {
        : image_button { key = "f_image1"; width = 22; height = 4; fixed_width = true; fixed_height = true; color = 0; }
        : edit_box { key = "b_watts1"; width = 16; fixed_width = true; edit_width = 10; allow_accept = false; }
        : toggle { key = "b_ground1"; label = "是"; width = 14; fixed_width = true; }
      }
      : row {
        : image_button { key = "f_image2"; width = 22; height = 4; fixed_width = true; fixed_height = true; color = 0; }
        : edit_box { key = "b_watts2"; width = 16; fixed_width = true; edit_width = 10; allow_accept = false; }
        : toggle { key = "b_ground2"; label = "是"; width = 14; fixed_width = true; }
      }
      : row {
        : image_button { key = "f_image3"; width = 22; height = 4; fixed_width = true; fixed_height = true; color = 0; }
        : edit_box { key = "b_watts3"; width = 16; fixed_width = true; edit_width = 10; allow_accept = false; }
        : toggle { key = "b_ground3"; label = "是"; width = 14; fixed_width = true; }
      }
      : row { : button { key = "f_prev"; label = "上一页"; } : text { key = "f_page"; width = 10; } : button { key = "f_next"; label = "下一页"; } }
      : text { label = "点击图块查看实景；功率按图块名统一，按 Tab 记住。"; }
      : text { label = "地面设置随草稿保存。"; }
    }
  }
  : text { key = "p_total"; width = 100; }
  : text { key = "p_template_status"; width = 100; }
  : text { key = "p_error"; width = 100; }
  : row {
    : button { key = "accept"; label = "保存"; is_default = true; }
    : button { key = "p_generate"; label = "生成或更新"; }
    : button { key = "cancel"; label = "取消"; is_cancel = true; }
  }
}
