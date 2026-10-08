el_exits : dialog {
  label = "整箱出口集中核对";
  : text { label = "请选择全部出线；进线及非出线不选。确认后才建立回路。"; }
  : list_box { key = "exits"; width = 88; height = 14; multiple_select = true; }
  : text { key = "scope_info"; width = 88; }
  : toggle { key = "scope_exclude"; label = "已核对：明确排除上述未纳入图层的箱边导线"; }
  : button { key = "exit_all"; label = "全选出线（请取消进线）"; }
  : button { key = "add_wire"; label = "补充导线图层"; }
  ok_cancel;
}
el_power : dialog {
  label = "应急照明设备功率表（整数瓦）";
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
