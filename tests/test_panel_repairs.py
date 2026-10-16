"""Reported native panel failures. Date: 2026-10-16."""
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


    def test_compact_status_wraps_chinese_and_clears_old_lines(self):
        value = '已识别设备合计：170 W；实际回路 5；输出 7；已完整核对回路 170 W'
        self.call('EL:PanelText', 'p_total', value)
        lines = [self.tiles['p_total' + (str(i) if i else '')] for i in range(4)]
        self.assertEqual(''.join(lines), value)
        self.assertTrue(all(sum(2 if ord(c) > 127 else 1 for c in line) <= 44 for line in lines))
        self.call('EL:PanelText', 'p_total', '已保存')
        self.assertEqual(self.tiles['p_total'], '已保存')
        self.assertTrue(all(self.tiles['p_total' + str(i)] == '' for i in range(1, 4)))

    def test_status_wrap_preserves_gb2312_pairs_in_cad2020(self):
        # Model the legacy byte-indexed primitives, including split byte slices.
        encode = lambda s: s.encode('gb2312', errors='surrogateescape')
        def substr(s, start, count):
            return encode(s)[start - 1:start - 1 + count].decode('gb2312', errors='surrogateescape')
        self.h.builtins.update({'STRLEN': lambda s: len(encode(s)),
                               'SUBSTR': substr, 'ASCII': lambda s: encode(s)[0]})
        values = [
            ('p_capacity_status', '默认 0.3kW；可按需要调整为 0.6kW 或 1kW。', 2),
            ('p_total', '已识别设备合计：170 W；连接仍待核对；实际回路 5；输出 7；已完整核对回路 80 W', 4),
        ]
        for key, value, count in values:
            with self.subTest(key=key):
                self.call('EL:PanelText', key, value)
                lines = [self.tiles[key + (str(i) if i else '')] for i in range(count)]
                self.assertEqual(''.join(lines), value)
                for line in lines:
                    self.assertEqual(encode(line).decode('gb2312'), line)
                    self.assertLessEqual(len(encode(line)), 44)
        self.call('EL:PanelText', 'p_total', '')
        self.assertTrue(all(self.tiles['p_total' + (str(i) if i else '')] == '' for i in range(4)))
        messages = []
        self.h.builtins['PRINC'] = lambda *args: messages.extend(args)
        self.call('EL:PanelText', 'p_error', 'A' * 43 + '中文提示')
        self.assertNotIn('p_error', self.tiles)
        self.assertIn('A' * 43 + '中文提示', ''.join(messages))

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




if __name__ == '__main__':
    unittest.main()
