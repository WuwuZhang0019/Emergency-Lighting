"""Actual circuit-number functions, bounded DWG adapters. Date: 2026-10-11."""
from pathlib import Path
import unittest
from autolisp_host import Host, Pair, Symbol, parse, quoted, truth
import test_simple_flow as simple

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

class NumberScopeTests(unittest.TestCase):
    call = NumberReadTests.call
    get = NumberReadTests.get

    def setUp(self):
        self.f = simple.SimpleFlowTests()
        self.f.setUp()
        self.h = self.f.h
        self.h.load_definitions(ROOT / 'src/panel.lsp')

    def scope(self, wire='w1', network=None):
        network = network or self.f.network()
        scope = self.call('EL:ExitNumberScope', [pair('wire', wire)], network, self.f.cfg)
        self.assertEqual(self.get('status', scope), Symbol('READY'), self.get('issues', scope))
        return scope

    def test_branches_before_first_device_and_statistics_remain_complete(self):
        self.f.plan()
        self.f.block('LAMP', 'D', 'late', [15., 10., 0.])
        self.f.line('w1', [1., 0., 0.], [20., 0., 0.], 'W')
        self.f.line('late-wire', [15., 0., 0.], [15., 9., 0.], 'W')
        self.f.selected += ['late', 'late-wire']
        network = self.f.network()
        scope = self.scope(network=network)
        self.assertEqual(set(self.get('sources', scope)), {'w1', 'w2'})
        self.assertEqual(set(self.get('boundaries', scope)), {'a', 'b'})
        result = self.call('EL:SplitNetwork', network, self.f.cfg)
        circuit = self.get('circuits', result)[0]
        self.assertIn('late', self.get('devices', circuit))
        self.assertIn('late-wire', self.get('wires', circuit))
        self.assertEqual(self.get('number-scope', circuit), scope)

    def test_multiple_source_segments_and_reversed_direction(self):
        self.f.plan()
        self.f.line('w1', [1., 0., 0.], [4., 0., 0.], 'W')
        self.f.line('next', [4., 0., 0.], [9., 0., 0.], 'W')
        self.f.selected += ['next']
        self.assertEqual(set(self.get('sources', self.scope())), {'w1', 'next', 'w2'})
        self.f.line('w1', [4., 0., 0.], [1., 0., 0.], 'W')
        self.assertEqual(set(self.get('sources', self.scope())), {'w1', 'next', 'w2'})

    def test_accepted_gaps_only_and_stop_before_downstream_gap(self):
        self.f.gap_plan()
        self.assertEqual(set(self.get('sources', self.scope('before'))), {'before', 'after-wire'})
        self.f.block('LAMP', 'D', 'early', [5., 0., 0.])
        self.f.selected += ['early']
        self.assertEqual(self.get('sources', self.scope('before')), ['before'])

    def test_missing_root_direction_is_an_explicit_problem(self):
        self.f.plan()
        self.f.line('w1', [-5., 0., 0.], [9., 0., 0.], 'W')
        scope = self.call('EL:ExitNumberScope', [pair('wire', 'w1')], self.f.network(), self.f.cfg)
        self.assertEqual(self.get('status', scope), Symbol('PATH-AMBIGUOUS'))
        self.assertFalse(self.get('sources', scope))

    def test_virtual_segment_keeps_true_source_handle(self):
        self.f.plan()
        network = self.f.network()
        snapshot = self.get('snapshot', network)
        wires = self.get('wires', snapshot)
        replaced = [self.call('EL:Put', Symbol('SOURCE-WIRE'), 'original', w)
                    if self.get('id', w) == 'w1' else w for w in wires]
        network = self.call('EL:Put', Symbol('SNAPSHOT'),
                            self.call('EL:Put', Symbol('WIRES'), replaced, snapshot), network)
        self.assertEqual(set(self.get('sources', self.scope(network=network))), {'original', 'w2'})

    def test_hole_and_width_contacts_use_actual_shape(self):
        # No database geometry shortcut: real ContourPathHit / WideDevicePathHit run.
        self.h.run('''(setq ring (EL:BoundsSegments '((4.0 -2.0 0.0) (8.0 2.0 0.0)))
          hole (EL:BoundsSegments '((5.0 -1.0 0.0) (7.0 1.0 0.0))))
          (setq shape (list (cons 'segments (append ring hole)) (cons 'regions (list ring))
            (cons 'holes (list hole))))
          (setq wire '((segments ((5.5 0.0 0.0) (6.5 0.0 0.0)))))''')
        shape = self.h.lookup('SHAPE')
        wire = self.h.lookup('WIRE')
        self.assertFalse(truth(self.call('EL:NumberShapeHit', wire, shape, self.f.cfg)))
        self.h.run('''(setq wide '((segments ((0.0 3.0 0.0) (10.0 3.0 0.0)))
          (width-profiles ((0.0 3.0 0.0) (10.0 3.0 0.0) 4.0 4.0))))''')
        wide = self.h.lookup('WIDE')
        self.h.builtins['EL:DEVICECONTACTSHAPE'] = lambda block: shape
        first = self.call('EL:NumberFirstDevice', wide, 0., 10., [[pair('id', 'device')]], self.f.cfg)
        self.assertAlmostEqual(first[0], 4., places=5)

class NumberAllocationTests(unittest.TestCase):
    call = NumberReadTests.call
    get = NumberReadTests.get

    def setUp(self):
        NumberReadTests.setUp(self)
        self.h.load_definitions(ROOT / 'src/geometry.lsp')
        self.data = {}
        self.reads = []
        def reader(handle):
            self.reads.append(handle)
            return self.call('EL:Put', Symbol('HANDLE'), handle,
                             self.call('EL:ParseWireNumberData', self.data[handle]))
        self.h.builtins['EL:READWIRENUMBERDATA'] = reader

    def circuits(self, numbers):
        rows = []
        for i, value in enumerate(numbers, 1):
            values = value if isinstance(value, list) else [value] if value is not None else []
            self.data[f'H{i}'] = [[-3, ['linenum', *[Pair(1000, v) for v in values]]]] if values else []
            rows.append([pair('id', f'R{i}'), pair('circuit-uid', f'u{i}'), pair('watts', 10),
                         pair('output-order', i), pair('seed', [pair('key', [f'H{i}', Symbol('OUTLET')])]),
                         pair('number-scope', [pair('status', Symbol('READY')), pair('sources', [f'H{i}'])])])
        return rows

    def resolve(self, numbers):
        return self.call('EL:ResolveCircuitNumbers', [pair('circuits', self.circuits(numbers))])

    def test_default_mixed_prefix_and_reserved_later_plane_numbers(self):
        for source, expected in (([None, None, None], ['ZE1', 'ZE2', 'ZE3']),
                                 (['ZE3', None, 'ZE1'], ['ZE3', 'ZE2', 'ZE1']),
                                 (['ZE2', None], ['ZE2', 'ZE3']),
                                 ([None, 'ZE1'], ['ZE2', 'ZE1']),
                                 (['WL1', None], ['WL1', 'ZE2']),
                                 (['ZE01', None], ['ZE01', 'ZE2'])):
            with self.subTest(source=source):
                result = self.resolve(source)
                self.assertEqual([self.get('circuit-number', c) for c in self.get('circuits', result)], expected)
                self.assertTrue(truth(self.call('EL:CircuitNumbersReady', result)))

    def test_conflict_keeps_native_number_and_blocks_ready_state(self):
        for numbers in (['ZE1', 'ze1'], [['ZE1', 'ZE2'], None]):
            result = self.resolve(numbers)
            self.assertFalse(truth(self.call('EL:CircuitNumbersReady', result)))
            self.assertEqual(self.get('number-status', self.get('circuits', result)[0]), Symbol('CONFLICT'))
            self.assertIn('编号冲突', self.call('EL:NumberProblemText', result))
        result = self.resolve(['ZE1', 'ZE1'])
        self.assertEqual([self.get('circuit-number', c) for c in self.get('circuits', result)], ['ZE1', 'ZE1'])

    def test_missing_is_auto_but_invalid_scope_or_metadata_is_not(self):
        rows = self.circuits([7, None, None])
        rows[1] = self.call('EL:Put', Symbol('NUMBER-SCOPE'), [pair('status', Symbol('PATH-AMBIGUOUS'))], rows[1])
        result = self.call('EL:ResolveCircuitNumbers', [pair('circuits', rows)])
        cs = self.get('circuits', result)
        self.assertEqual([self.get('number-status', c) for c in cs],
                         [Symbol('INVALID'), Symbol('PATH-AMBIGUOUS'), Symbol('READY')])
        self.assertIsNone(self.get('circuit-number', cs[0]))
        self.assertIsNone(self.get('circuit-number', cs[1]))
        self.assertEqual(self.get('circuit-number', cs[2]), 'ZE3')

    def test_shared_original_source_is_ambiguous_and_read_once(self):
        rows = self.circuits(['ZE1', None])
        rows[1] = self.call('EL:Put', Symbol('NUMBER-SCOPE'), self.get('number-scope', rows[0]), rows[1])
        result = self.call('EL:ResolveCircuitNumbers', [pair('circuits', rows)])
        self.assertEqual(self.reads, ['H1'])
        self.assertTrue(all(self.get('number-status', c) == Symbol('PATH-AMBIGUOUS') for c in self.get('circuits', result)))

    def test_saved_order_and_uid_are_restored_before_allocation(self):
        self.h.load_definitions(ROOT / 'src/panel.lsp')
        self.h.load_definitions(ROOT / 'src/diagram-update.lsp')
        rows = self.circuits(['ZE3', None])
        saved = [[pair('seed-key', self.get('key', self.get('seed', rows[0]))), pair('circuit-uid', 'old-u1'), pair('output-order', 2)],
                 [pair('seed-key', self.get('key', self.get('seed', rows[1]))), pair('circuit-uid', 'old-u2'), pair('output-order', 1)]]
        prepared = self.call('EL:PreparedResult', [pair('circuits', rows)], [pair('diagram-id', 'diagram'), pair('rows', saved)])
        cs = self.get('circuits', prepared)
        self.assertEqual([self.get('circuit-uid', c) for c in cs], ['old-u2', 'old-u1'])
        self.assertEqual([self.get('circuit-number', c) for c in cs], ['ZE1', 'ZE3'])
        self.assertEqual([self.get('watts', c) for c in cs], [10, 10])

    def test_legacy_rows_and_independent_panels_keep_defaults(self):
        for _ in range(2):
            result = self.resolve(['ZE1'])
            self.assertTrue(truth(self.call('EL:CircuitNumbersReady', result)))
        result = self.call('EL:ResolveCircuitNumbers', [pair('circuits', [[pair('id', 'old')]])])
        c = self.get('circuits', result)[0]
        self.assertEqual(self.get('number-source', c), Symbol('LEGACY'))
        self.assertEqual(self.get('circuit-number', c), 'ZE1')

if __name__ == '__main__':
    unittest.main()
