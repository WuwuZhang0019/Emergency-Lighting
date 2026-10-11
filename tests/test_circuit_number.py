"""Actual circuit-number functions, bounded DWG adapters. Date: 2026-10-11."""
from pathlib import Path
import unittest
from autolisp_host import Host, Pair, Symbol, parse, quoted, truth

ROOT = Path(__file__).resolve().parents[1]

def pair(key, value):
    return Pair(Symbol(key.upper()), value)

class NumberReadTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'circuit-number'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, row):
        return self.call('EL:Get', Symbol(key.upper()), row)

    def read(self, data):
        return self.call('EL:ParseWireNumberData', quoted(parse(data)[0]))

    def test_native_fixture_and_application_isolation(self):
        fixture = quoted(parse((ROOT / 'tests/fixtures/tianz-circuit-number.eld').read_text(encoding='utf-8'))[0])
        annotation = self.get('annotation', fixture)
        wire = self.get('wire', fixture)
        self.assertEqual(self.get('status', self.call('EL:ParseWireNumberData', annotation)), Symbol('MISSING'))
        result = self.call('EL:ParseWireNumberData', wire)
        self.assertEqual(self.get('values', result), ['ZE1'])
        self.assertEqual(self.get('status', result), Symbol('READY'))

    def test_missing_empty_duplicates_and_case(self):
        for data in ('((0 . "LINE"))', '((-3 ("linenum" (1000 . "  "))))'):
            self.assertEqual(self.get('status', self.read(data)), Symbol('MISSING'))
        result = self.read('((-3 ("linenum" (1000 . " ZE1 ") (1000 . "ze1"))))')
        self.assertEqual(self.get('values', result), ['ZE1'])
        self.assertEqual(self.get('status', result), Symbol('READY'))

    def test_multiple_groups_and_custom_text_are_preserved(self):
        result = self.read('((-3 ("linenum" (1000 . "ALE(JZ)-ZE01"))) (-3 ("LINENUM" (1000 . "中文回路1"))))')
        self.assertEqual(self.get('status', result), Symbol('CONFLICT'))
        self.assertEqual(self.get('values', result), ['ALE(JZ)-ZE01', '中文回路1'])
        text = 'WL-' + 'A' * 200
        self.assertEqual(self.get('values', self.read(f'((-3 ("linenum" (1000 . "{text}"))))')), [text])

    def test_malformed_and_control_strings_are_not_missing(self):
        for data in ('((-3 ("linenum")))', '((-3 ("linenum" (1000 . 7))))',
                     '((-3 ("linenum" (1005 . "2227"))))',
                     '((-3 ("linenum" (1000 . "ZE\\n1"))))',
                     '((-3 ("linenum" (1000 . "ZE\\\\P1"))))', '((-3 . 3))'):
            with self.subTest(data=data):
                self.assertEqual(self.get('status', self.read(data)), Symbol('INVALID'))

    def test_native_reader_is_selective_and_keeps_raw_changes(self):
        data = quoted(parse('((0 . "LINE") (5 . "W") (-3 ("linenum" (1000 . "ZE1"))))')[0])
        calls = []
        self.h.builtins['HANDENT'] = lambda handle: 'entity' if handle == 'W' else None
        def entget(entity, apps):
            calls.append((entity, apps))
            self.assertEqual(apps, ['linenum'])
            return data
        self.h.builtins['ENTGET'] = entget
        result = self.call('EL:ReadWireNumberData', 'W')
        self.assertEqual(self.get('values', result), ['ZE1'])
        self.assertEqual(calls, [('entity', ['linenum'])])
        self.assertEqual(self.get('status', self.call('EL:ReadWireNumberData', 'gone')), Symbol('INVALID'))
        self.h.builtins['ENTGET'] = lambda *args: (_ for _ in ()).throw(RuntimeError('CAD read failure'))
        self.assertEqual(self.get('reason', self.call('EL:ReadWireNumberData', 'W')), Symbol('READ_FAILED'))

if __name__ == '__main__':
    unittest.main()
