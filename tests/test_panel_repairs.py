"""Reported native panel failures. Date: 2026-10-10."""
import unittest
from pathlib import Path
from autolisp_host import Symbol
import test_exit_devices as exits


class PanelRepairTests(unittest.TestCase):
    def setUp(self):
        fixture = exits.ExitDeviceTests()
        fixture.setUp()
        self.h, self.tiles = fixture.h, fixture.tiles
        self.call, self.get = fixture.call, fixture.get
        self.actions = fixture.actions
        self.result = self.call('EL:RecognizeFixed', fixture.cfg, 'panel')
        self.cfg = fixture.cfg

    def test_circuit_text_is_not_a_button_value_and_reserve_stays_open(self):
        ui = (Path(__file__).resolve().parents[1] / 'ui/power.dcl').read_text(encoding='utf-8')
        self.assertIn(': text { key = "p_row0"', ui)
        self.assertNotIn('p_select', ui)
        self.h.builtins['GET_TILE'] = lambda key: self.tiles.get(key, '')
        self.h.builtins['DONE_DIALOG'] = lambda status: self.fail('reserve must not close panel')
        def start():
            self.assertNotIn('p_select1', self.actions)
            self.assertEqual(self.tiles['p_row1'], '预留1')
            self.assertEqual(self.tiles['b_watts0'], '5')
            return 0
        self.h.builtins['START_DIALOG'] = start
        self.call('EL:PanelDialog', self.result, self.cfg, self.h.run("'((\"LAMP\" . 5))"), None)

    def test_compact_status_wraps_chinese_and_clears_old_lines(self):
        value = '已识别设备合计：170 W；实际回路 5；输出 7；已完整核对回路 170 W'
        self.call('EL:PanelText', 'p_total', value)
        lines = [self.tiles['p_total' + (str(i) if i else '')] for i in range(4)]
        self.assertEqual(''.join(lines), value)
        self.assertTrue(all(sum(2 if ord(c) > 127 else 1 for c in line) <= 44 for line in lines))
        self.call('EL:PanelText', 'p_total', '已保存')
        self.assertEqual(self.tiles['p_total'], '已保存')
        self.assertTrue(all(self.tiles['p_total' + str(i)] == '' for i in range(1, 4)))

    def test_screenshot_counts_total_85_even_when_connection_is_pending(self):
        self.h.run('''(setq *EL:PanelPowers* '(("A" . 5) ("B" . 1) ("C" . 1) ("D" . 1)))''')
        blocks, ids = [], []
        for name, count in [('A', 14), ('B', 7), ('C', 5), ('D', 3)]:
            for i in range(count):
                ident = f'{name}{i}'
                ids.append(ident)
                blocks.append(self.h.run(f'\'((id . "{ident}") (name . "{name}"))'))
        circuit = self.call('EL:Put', Symbol('DEVICES'), ids, None)
        result = self.call('EL:Put', Symbol('CIRCUITS'), [circuit, circuit], None)
        snapshot = self.call('EL:Put', Symbol('BLOCKS'), blocks, None)
        self.h.frames[0]['*EL:PANELDRAFT*'] = self.call('EL:Put', Symbol('SNAPSHOT'), snapshot, result)
        text = self.call('EL:PanelKnownTotal')
        self.assertIn('85 W', text)
        self.assertIn('连接仍待核对', text)
        self.assertNotIn('170', text)

    def test_edit_event_remembers_last_value_reloads_over_old_dwg_draft(self):
        files = {}
        self.h.builtins.update({
            'GET_TILE': lambda key: self.tiles.get(key, ''),
            'EL:WRITEDATA': lambda path, data: files.__setitem__(path, data) or True,
            'EL:READDATA': lambda path: files.get(path),
        })
        def start():
            self.tiles['b_watts0'] = '7'
            self.h.run(self.actions['b_watts0'])
            self.assertIn('已记住', self.tiles['p_error'])
            self.assertIn('14 W', self.tiles['p_total'])
            return 0
        self.h.builtins['START_DIALOG'] = start
        self.call('EL:PanelDialog', self.result, self.cfg, None, None)
        self.assertEqual(len(files), 1)
        self.h.builtins['EL:SIMPLELOADPOWERS'] = lambda: self.h.run("'((version . 1) (powers (\"LAMP\" . 5)))")
        record = self.h.run("'((source-panel-handle . \"panel\") (draft-circuits (old)) (powers (\"LAMP\" . 1)))")
        loaded = self.call('EL:FixedPowers', record)
        self.assertEqual(self.call('EL:Get', 'LAMP', loaded), 7)

    def test_failed_power_write_is_visible_and_draft_remains(self):
        self.h.builtins['GET_TILE'] = lambda key: self.tiles.get(key, '')
        self.h.builtins['EL:WRITEDATA'] = lambda *args: None
        def start():
            self.tiles['b_watts0'] = '8'
            self.h.run(self.actions['b_watts0'])
            self.assertIn('未写入文件', self.tiles['p_error'])
            self.assertEqual(self.tiles['b_watts0'], '8')
            return 0
        self.h.builtins['START_DIALOG'] = start
        self.call('EL:PanelDialog', self.result, self.cfg, None, None)


if __name__ == '__main__':
    unittest.main()
