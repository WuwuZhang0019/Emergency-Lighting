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
