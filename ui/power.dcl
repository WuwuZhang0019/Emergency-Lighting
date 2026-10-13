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
  : row {
    : column {
  : row {
    : row { fixed_width = true; alignment = left;
      : image_button { key = "p_pick"; width = 14; height = 1.8; fixed_width = true; fixed_height = true; color = 3; is_tab_stop = true; }
      : image_button { key = "p_trunk"; width = 28; height = 1.8; fixed_width = true; fixed_height = true; color = 3; is_tab_stop = true; }
    }
    : spacer { width = 1; }
  }
  // Date: 2026-10-11. Number belongs to the current source panel.
  : text { key = "p_number"; label = "配电箱编号：暂无编号"; width = 46; fixed_width = true; }
  : radio_row { key = "p_capacity"; label = "当前配电箱容量档位"; fixed_width = true; alignment = left;
    : radio_button { key = "p_300"; width = 10; fixed_width = true; label = "0.3kW"; value = "1"; }
    : radio_button { key = "p_600"; width = 10; fixed_width = true; label = "0.6kW"; }
    : radio_button { key = "p_1000"; width = 10; fixed_width = true; label = "1kW"; }
  }
  : column { fixed_width = true;
    : text { key = "p_capacity_status"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
    : text { key = "p_capacity_status1"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
  }
    : boxed_column { label = "回路编号 / 功率";
      : boxed_row { : text { label = "回路1"; width = 7; fixed_width = true; } : text { key = "p_row0"; width = 16; fixed_width = true; height = 1.8; fixed_height = true; } }
      : boxed_row { : text { label = "回路2"; width = 7; fixed_width = true; } : text { key = "p_row1"; width = 16; fixed_width = true; height = 1.8; fixed_height = true; } }
      : boxed_row { : text { label = "回路3"; width = 7; fixed_width = true; } : text { key = "p_row2"; width = 16; fixed_width = true; height = 1.8; fixed_height = true; } }
      : boxed_row { : text { label = "回路4"; width = 7; fixed_width = true; } : text { key = "p_row3"; width = 16; fixed_width = true; height = 1.8; fixed_height = true; } }
      : boxed_row { : text { label = "回路5"; width = 7; fixed_width = true; } : text { key = "p_row4"; width = 16; fixed_width = true; height = 1.8; fixed_height = true; } }
      : boxed_row { : text { label = "回路6"; width = 7; fixed_width = true; } : text { key = "p_row5"; width = 16; fixed_width = true; height = 1.8; fixed_height = true; } }
      : boxed_row { : text { label = "回路7"; width = 7; fixed_width = true; } : text { key = "p_row6"; width = 16; fixed_width = true; height = 1.8; fixed_height = true; } }
      : boxed_row { : text { label = "回路8"; width = 7; fixed_width = true; } : text { key = "p_row7"; width = 16; fixed_width = true; height = 1.8; fixed_height = true; } }
      : button { key = "f_preview"; label = "查看全部回路"; }
    }
  : column { fixed_width = true;
    : text { key = "p_total"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
    : text { key = "p_total1"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
    : text { key = "p_total2"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
    : text { key = "p_total3"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
  }
  : column { fixed_width = true;
    : text { key = "p_template_status"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
    : text { key = "p_template_status1"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
  }
  : column { fixed_width = true;
    : text { key = "p_error"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
    : text { key = "p_error1"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
    : text { key = "p_error2"; width = 46; fixed_width = true; height = 1; fixed_height = true; }
  }
  : column {
    : button { key = "accept"; label = "保存"; is_default = true; }
    : button { key = "p_generate"; label = "生成或更新"; }
    // Date: 2026-10-13. Existing drawings can keep all layout and captions.
    : button { key = "p_existing"; label = "关联原图功率"; }
    : button { key = "cancel"; label = "取消"; is_cancel = true; }
  }
    }
  : boxed_column { label = "保存记录（本图）";
    // Date: 2026-10-13. Load records separately after the first usable frame.
    : button { key = "h_load"; label = "加载保存记录"; }
    : list_box { key = "h_records"; width = 30; fixed_width = true; height = 36; multiple_select = false; }
    : text { key = "h_detail"; width = 30; fixed_width = true; }
    // Date: 2026-10-11. A single click opens the selected record.
    : text { label = "单击打开；[当前] 为已打开箱。"; }
    : text { label = "切换保存草稿，不更新系统图。"; }
    : text { label = "关闭图纸前请保存 DWG。"; }
    : button { key = "h_open"; label = "保存当前并打开"; }
  }
    : boxed_column { label = "图例表（点击图形编辑设备库）";
      // Date: 2026-10-10. Fixed-height table prevents stretched row gaps.
      : column { fixed_height = true; alignment = top;
      : boxed_row { fixed_height = true;
        : text { label = "图块"; width = 18; fixed_width = true; }
        : text { label = "单个功率(W)"; width = 12; fixed_width = true; }
        : text { label = "地面"; width = 7; fixed_width = true; }
        : text { label = "排除"; width = 4; fixed_width = true; }
      }
      : boxed_row { fixed_height = true;
        : column { fixed_height = true;
          : text { key = "b_label0"; width = 18; fixed_width = true; height = 1; fixed_height = true; }
          : image_button { key = "f_image0"; width = 18; height = 1.6; fixed_width = true; fixed_height = true; color = 0; }
        }
        : edit_box { key = "b_watts0"; width = 12; fixed_width = true; edit_width = 7; allow_accept = false; }
        : toggle { key = "b_ground0"; label = "是"; width = 7; fixed_width = true; }
        : button { key = "b_remove0"; label = "×"; width = 4; fixed_width = true; }
      }
      : boxed_row { fixed_height = true;
        : column { fixed_height = true;
          : text { key = "b_label1"; width = 18; fixed_width = true; height = 1; fixed_height = true; }
          : image_button { key = "f_image1"; width = 18; height = 1.6; fixed_width = true; fixed_height = true; color = 0; }
        }
        : edit_box { key = "b_watts1"; width = 12; fixed_width = true; edit_width = 7; allow_accept = false; }
        : toggle { key = "b_ground1"; label = "是"; width = 7; fixed_width = true; }
        : button { key = "b_remove1"; label = "×"; width = 4; fixed_width = true; }
      }
      : boxed_row { fixed_height = true;
        : column { fixed_height = true;
          : text { key = "b_label2"; width = 18; fixed_width = true; height = 1; fixed_height = true; }
          : image_button { key = "f_image2"; width = 18; height = 1.6; fixed_width = true; fixed_height = true; color = 0; }
        }
        : edit_box { key = "b_watts2"; width = 12; fixed_width = true; edit_width = 7; allow_accept = false; }
        : toggle { key = "b_ground2"; label = "是"; width = 7; fixed_width = true; }
        : button { key = "b_remove2"; label = "×"; width = 4; fixed_width = true; }
      }
      : boxed_row { fixed_height = true;
        : column { fixed_height = true;
          : text { key = "b_label3"; width = 18; fixed_width = true; height = 1; fixed_height = true; }
          : image_button { key = "f_image3"; width = 18; height = 1.6; fixed_width = true; fixed_height = true; color = 0; }
        }
        : edit_box { key = "b_watts3"; width = 12; fixed_width = true; edit_width = 7; allow_accept = false; }
        : toggle { key = "b_ground3"; label = "是"; width = 7; fixed_width = true; }
        : button { key = "b_remove3"; label = "×"; width = 4; fixed_width = true; }
      }
      : boxed_row { fixed_height = true;
        : column { fixed_height = true;
          : text { key = "b_label4"; width = 18; fixed_width = true; height = 1; fixed_height = true; }
          : image_button { key = "f_image4"; width = 18; height = 1.6; fixed_width = true; fixed_height = true; color = 0; }
        }
        : edit_box { key = "b_watts4"; width = 12; fixed_width = true; edit_width = 7; allow_accept = false; }
        : toggle { key = "b_ground4"; label = "是"; width = 7; fixed_width = true; }
        : button { key = "b_remove4"; label = "×"; width = 4; fixed_width = true; }
      }
      : boxed_row { fixed_height = true;
        : column { fixed_height = true;
          : text { key = "b_label5"; width = 18; fixed_width = true; height = 1; fixed_height = true; }
          : image_button { key = "f_image5"; width = 18; height = 1.6; fixed_width = true; fixed_height = true; color = 0; }
        }
        : edit_box { key = "b_watts5"; width = 12; fixed_width = true; edit_width = 7; allow_accept = false; }
        : toggle { key = "b_ground5"; label = "是"; width = 7; fixed_width = true; }
        : button { key = "b_remove5"; label = "×"; width = 4; fixed_width = true; }
      }
      : boxed_row { fixed_height = true;
        : column { fixed_height = true;
          : text { key = "b_label6"; width = 18; fixed_width = true; height = 1; fixed_height = true; }
          : image_button { key = "f_image6"; width = 18; height = 1.6; fixed_width = true; fixed_height = true; color = 0; }
        }
        : edit_box { key = "b_watts6"; width = 12; fixed_width = true; edit_width = 7; allow_accept = false; }
        : toggle { key = "b_ground6"; label = "是"; width = 7; fixed_width = true; }
        : button { key = "b_remove6"; label = "×"; width = 4; fixed_width = true; }
      }
      : boxed_row { fixed_height = true;
        : column { fixed_height = true;
          : text { key = "b_label7"; width = 18; fixed_width = true; height = 1; fixed_height = true; }
          : image_button { key = "f_image7"; width = 18; height = 1.6; fixed_width = true; fixed_height = true; color = 0; }
        }
        : edit_box { key = "b_watts7"; width = 12; fixed_width = true; edit_width = 7; allow_accept = false; }
        : toggle { key = "b_ground7"; label = "是"; width = 7; fixed_width = true; }
        : button { key = "b_remove7"; label = "×"; width = 4; fixed_width = true; }
      }
      : row { fixed_height = true; : button { key = "f_prev"; label = "上一页"; } : text { key = "f_page"; width = 10; } : button { key = "f_next"; label = "下一页"; } }
      : row { : button { key = "b_library"; label = "完整设备库"; } : button { key = "b_apply_library"; label = "应用当前库值"; } }
      // Date: 2026-10-12. Keep inline editing and the unchecked non-ground default.
      : text { label = "地面：勾选是，不勾选就是非地面。"; }
      : text { label = "× 排除本箱同类图块，不计数量和功率。"; }
      : row { fixed_height = true; : text { key = "b_excluded"; width = 24; } : button { key = "b_restore"; label = "恢复排除"; } }
      }
      : spacer { height = 0; }
    }
    // Date: 2026-10-11. Shared library drafts beside the legend table.
    : boxed_column { label = "设备库资料"; fixed_width = true; width = 36;
      : column { fixed_height = true; alignment = top;
        : text { label = "点击左侧图例，编辑对应库资料。"; }
        : image { key = "dl_image"; width = 34; height = 6; fixed_width = true; fixed_height = true; color = 0; }
        : text { key = "dl_asset"; width = 36; fixed_width = true; }
        : text { key = "dl_asset1"; width = 36; fixed_width = true; }
        : text { label = "图块名"; }
        : edit_box { key = "dl_block"; edit_width = 34; fixed_width = true; allow_accept = false; }
        : text { label = "设备名"; }
        : edit_box { key = "dl_display"; edit_width = 34; fixed_width = true; allow_accept = false; }
        : text { label = "别名（用分号分隔）"; }
        : edit_box { key = "dl_aliases"; edit_width = 34; fixed_width = true; allow_accept = false; }
        : toggle { key = "dl_keep_old"; label = "改名保留原图块名为别名"; value = "1"; }
        : edit_box { key = "dl_watts"; label = "库默认功率 W"; edit_width = 8; allow_accept = false; }
        : toggle { key = "dl_zero"; label = "明确确认此设备为 0W"; }
        : popup_list { key = "dl_ground"; label = "是否地面"; }
        : toggle { key = "dl_active"; label = "启用名称匹配"; }
        : button { key = "dl_save"; label = "保存到设备库"; }
        : row {
          : button { key = "dl_delete"; label = "删除库设备"; }
          : button { key = "dl_restore"; label = "恢复库设备"; }
        }
        : button { key = "dl_locate"; label = "在图中查看选中设备"; }
        : button { key = "dl_pick"; label = "打开设备库拾取入库"; }
        : button { key = "dl_repair"; label = "打开设备库修复图例"; }
        : text { key = "dl_status"; width = 36; fixed_width = true; }
        : text { key = "dl_status1"; width = 36; fixed_width = true; }
        : text { key = "dl_status2"; width = 36; fixed_width = true; }
        : text { label = "缺资料可保存为草稿，补齐后启用。"; }
        : text { label = "图例功率自动存入库，同类图块沿用。"; }
      }
      : spacer { height = 0; }
    }
  }
}
