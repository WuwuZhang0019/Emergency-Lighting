"""Actual circuit-number functions, bounded DWG adapters. Date: 2026-10-13."""
from pathlib import Path
import copy
import unittest
from autolisp_host import Host, Pair, Symbol, cons, parse, quoted, truth
import test_simple_flow as simple
import test_diagram_update as update
import test_cckk_panel_command as command_fixture
import test_post_stat_workflow as workflow

ROOT = Path(__file__).resolve().parents[1]

def pair(key, value):
    return cons(Symbol(key.upper()), value)

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

    def test_interior_crossing_does_not_extend_number_scope(self):
        self.f.plan()
        self.f.line('cross', [3., -10., 0.], [3., 10., 0.], 'W')
        self.f.block('LAMP', 'D', 'cross-device', [3., 11., 0.])
        self.f.selected += ['cross', 'cross-device']
        network = self.f.network()
        self.assertNotIn('cross', self.get('sources', self.scope(network=network)))
        self.assertNotIn('cross-device', self.get('boundaries', self.scope(network=network)))

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
        # The 0.01 drawing-unit contact tolerance can find the contour slightly
        # before its exact x=4 boundary; a visible larger gap remains excluded.
        self.assertGreaterEqual(first[0], 3.99 - 1.0e-5)
        self.assertLessEqual(first[0], 4.0 + 1.0e-5)

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
                                 (['ZE2', None], ['ZE2', 'ZE1']),
                                 ([None, 'ZE1'], ['ZE2', 'ZE1']),
                                 (['WL1', None], ['WL1', 'ZE1']),
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
        self.assertEqual(self.get('circuit-number', cs[2]), 'ZE1')

    def test_shared_original_source_is_ambiguous_and_read_once(self):
        rows = self.circuits(['ZE1', None])
        rows[1] = self.call('EL:Put', Symbol('NUMBER-SCOPE'), self.get('number-scope', rows[0]), rows[1])
        result = self.call('EL:ResolveCircuitNumbers', [pair('circuits', rows)])
        self.assertEqual(self.reads, ['H1'])
        self.assertTrue(all(self.get('number-status', c) == Symbol('PATH-AMBIGUOUS') for c in self.get('circuits', result)))

    def test_multiple_scope_wires_merge_same_number_and_report_different_numbers(self):
        rows = self.circuits(['ZE1', 'ze1'])
        c = self.call('EL:Put', Symbol('NUMBER-SCOPE'),
                      [pair('status', Symbol('READY')), pair('sources', ['H1', 'H2'])], rows[0])
        result = self.call('EL:ResolveCircuitNumbers', [pair('circuits', [c])])
        self.assertTrue(truth(self.call('EL:CircuitNumbersReady', result)))
        self.assertEqual(self.get('circuit-number', self.get('circuits', result)[0]), 'ZE1')
        self.assertEqual(len(self.get('inputs', self.get('number-evidence', self.get('circuits', result)[0]))), 2)
        self.data['H2'] = [[-3, ['linenum', Pair(1000, 'ZE2')]]]
        result = self.call('EL:ResolveCircuitNumbers', [pair('circuits', [c])])
        current = self.get('circuits', result)[0]
        self.assertEqual(self.get('number-status', current), Symbol('CONFLICT'))
        self.assertIsNone(self.get('circuit-number', current))
        self.assertEqual(self.get('candidates', self.get('number-evidence', current)), ['ZE1', 'ZE2'])

    def test_saved_order_and_uid_are_restored_before_allocation(self):
        self.h.load_definitions(ROOT / 'src/panel.lsp')
        self.h.load_definitions(ROOT / 'src/device-recognition.lsp')
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

class NumberSortTests(unittest.TestCase):
    call = NumberReadTests.call
    get = NumberReadTests.get
    circuits = NumberAllocationTests.circuits

    def setUp(self):
        NumberAllocationTests.setUp(self)
        for name in ('panel', 'device-recognition', 'diagram-update'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')

    def prepare(self, numbers):
        return self.call('EL:PreparedResult', [pair('circuits', self.circuits(numbers))],
                         [pair('diagram-id', 'diagram')])

    def test_numeric_order_keeps_power_devices_uid_and_manual_settings(self):
        rows = self.circuits(['ZE3', 'ZE1', 'ZE10', 'ZE2'])
        for i, row in enumerate(rows, 1):
            for key, value in (('watts', i * 7), ('devices', [f'lamp{i}']),
                               ('is-ground', i % 2 == 0), ('ground-source', Symbol('MANUAL'))):
                row = self.call('EL:Put', Symbol(key.upper()), value, row)
            rows[i - 1] = row
        saved = [[pair('seed-key', self.get('key', self.get('seed', row))),
                  pair('circuit-uid', f'saved-u{i}'), pair('output-order', i),
                  pair('is-ground', i % 2 == 0), pair('ground-source', Symbol('MANUAL'))]
                 for i, row in enumerate(rows, 1)]
        record = [pair('diagram-id', 'diagram'), pair('rows', saved)]
        result = self.call('EL:PreparedResult', [pair('circuits', rows)], record)
        circuits = self.get('circuits', result)
        self.assertEqual([self.get('circuit-number', c) for c in circuits], ['ZE1', 'ZE2', 'ZE3', 'ZE10'])
        for c, original in zip(circuits, [2, 4, 1, 3]):
            self.assertEqual(self.get('circuit-uid', c), f'saved-u{original}')
            self.assertEqual(self.get('output-order', c), original)
            self.assertEqual(self.get('watts', c), original * 7)
            self.assertEqual(self.get('devices', c), [f'lamp{original}'])
            self.assertEqual(truth(self.get('is-ground', c)), original % 2 == 0)
        self.assertEqual(self.call('EL:PreparedResult', result, record), result)

    def test_missing_metadata_default_stays_stable_when_reprepared(self):
        result = self.prepare(['ZE10', None, 'ZE1'])
        expected = ['ZE1', 'ZE2', 'ZE10']
        self.assertEqual([self.get('circuit-number', c) for c in self.get('circuits', result)], expected)
        record = [pair('diagram-id', 'diagram'), pair('rows', self.get('circuits', result))]
        for _ in range(3):
            result = self.call('EL:PreparedResult', result, record)
            self.assertEqual([self.get('circuit-number', c) for c in self.get('circuits', result)], expected)
        self.assertEqual(self.reads, ['H1', 'H2', 'H3'])

    def test_custom_and_unresolved_slots_unchanged_and_equal_numbers_not_dropped(self):
        rows = [[pair('circuit-number', number), pair('number-status', status), pair('circuit-uid', f'u{i}')]
                for i, (number, status) in enumerate([
                    ('ZE10', Symbol('READY')), ('WL7', Symbol('READY')), ('ZE2', Symbol('READY')),
                    ('ZE1', Symbol('CONFLICT')), ('ze02', Symbol('READY')), ('ZE2', Symbol('READY'))])]
        result = self.call('EL:SortCircuitNumbers', [pair('circuits', rows)])
        circuits = self.get('circuits', result)
        self.assertEqual([self.get('circuit-number', c) for c in circuits],
                         ['ZE2', 'WL7', 'ze02', 'ZE1', 'ZE2', 'ZE10'])
        self.assertEqual([self.get('circuit-uid', c) for c in circuits], ['u2', 'u1', 'u4', 'u3', 'u5', 'u0'])
        self.assertEqual(self.get('circuits', self.call('EL:SortCircuitNumbers', [pair('circuits', None)])), None)

class NumberPresentationTests(unittest.TestCase):
    call = NumberReadTests.call
    get = NumberReadTests.get

    def setUp(self):
        self.f = update.UpdateTests()
        self.f.setUp()
        self.h = self.f.h

    def set_numbers(self):
        self.h.run('''(setq cs (list (EL:Put 'circuit-number "WL7" (car cs))
          (EL:Put 'circuit-number "ZE3" (cadr cs))))
          (setq result (EL:Put 'circuits cs result)
            plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))''')

    def test_panel_and_plan_captions_share_numbers_and_reserves_avoid_actuals(self):
        self.set_numbers()
        labels = self.h.run('(EL:CCKKLabels plan)')
        numbers = [self.get('text', row) for row in labels if self.get('kind', row) == Symbol('NUMBER')]
        self.assertEqual(numbers, ['WL7', 'ZE3', 'ZE4', 'ZE5'])
        self.h.run('''(setq *EL:PanelDraft* result *EL:PanelPage* 0 *EL:PanelIndex* 0
          *EL:PanelCapacity* 'cap300 *EL:PanelTemplateReady* T *EL:ThumbRows* '(device))''')
        tiles = {}
        self.h.builtins.update({'SET_TILE': lambda k, v: tiles.__setitem__(k, v),
                               'EL:PANELBLOCKFILL': lambda: None, 'EL:PANELKNOWNTOTAL': lambda: '统计'})
        self.call('EL:PanelFill')
        self.assertTrue(tiles['p_row0'].startswith('WL7 | '))
        self.assertTrue(tiles['p_row1'].startswith('ZE3 | '))
        self.assertEqual(tiles['p_row2'], '预留1')


    def test_conflict_blocks_generate_and_plan_but_keeps_draft(self):
        self.h.run('''(setq result (EL:Put 'circuits (list (EL:Put 'number-status 'conflict
          (EL:Put 'number-evidence '((candidates "ZE1" "ZE2")) (car cs)))) result))
          (setq *EL:PanelDraft* result *EL:PanelTemplateReady* T)''')
        self.assertIsNone(self.h.run("(EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0)"))
        done, tiles, alerts = [], {}, []
        self.h.builtins.update({'EL:PANELSTORESELECTIONS': lambda: True,
                               'SET_TILE': lambda k, v: tiles.__setitem__(k, v),
                               'DONE_DIALOG': done.append, 'ALERT': alerts.append})
        self.call('EL:PanelGenerateBody')
        self.assertEqual(done, [])
        self.assertIn('编号冲突', ''.join(alerts))
        self.assertNotIn('p_error', tiles)
        self.assertTrue(self.h.lookup('*EL:PANELDRAFT*'))

    def test_native_cckk2_panel_dispatch_uses_resolved_numbers(self):
        f = command_fixture.PanelCommandTests()
        f.setUp()
        f.h.run('''(setq result (EL:Put 'circuits (list (EL:Put 'circuit-number "ALE-ZE9" (car cs))) result))''')
        self.assertTrue(truth(f.invoke()))
        record = f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        number = next(row for row in f.get('cckk-labels', record) if f.get('kind', row) == Symbol('NUMBER'))
        self.assertEqual(f.get('text', number), 'ALE-ZE9')
        self.assertEqual(f.get('circuit-number', f.get('rows', f.get('plan', record))[0]), 'ALE-ZE9')

class NumberFreshnessTests(unittest.TestCase):
    call = NumberReadTests.call
    get = NumberReadTests.get

    def setUp(self):
        self.f = simple.SimpleFlowTests()
        self.f.setUp()
        self.f.plan()
        self.h = self.f.h
        self.h.load_definitions(ROOT / 'src/panel.lsp')
        self.h.builtins['GETVAR'] = lambda key: {'DWGNAME': 'number.dwg', 'DWGPREFIX': 'C:/cad/'}.get(key)

    def stamp(self, handle, number):
        self.f.entities[handle] = [row for row in self.f.entities[handle]
                                  if not (isinstance(row, list) and row[0] == -3)]
        if number is not None:
            self.f.entities[handle].append([-3, ['linenum', Pair(1000, number)]])

    def extract(self):
        result = self.call('EL:RecognizeFixed', self.f.cfg, 'panel')
        return self.call('EL:PreparedResult', result, [pair('diagram-id', 'diagram')])

    def test_missing_to_added_is_detected_without_geometry_change(self):
        result = self.extract()
        self.assertTrue(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.stamp('w1', 'ZE9')
        fresh = self.call('EL:FixedFreshSnapshot', self.f.cfg, 'panel')
        self.assertEqual(self.get('signature', fresh), self.get('signature', self.get('snapshot', result)))
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.assertEqual(self.get('circuit-number', self.get('circuits', self.extract())[0]), 'ZE9')

    def test_reprepare_cannot_replace_the_reviewed_baseline(self):
        self.stamp('w1', 'WL1')
        result = self.extract()
        self.stamp('w1', 'WL2')
        prepared = self.call('EL:PreparedResult', result, [pair('diagram-id', 'diagram')])
        self.assertEqual(self.get('circuit-number', self.get('circuits', prepared)[0]), 'WL1')
        self.assertEqual(self.get('number-inputs', prepared), self.get('number-inputs', result))
        self.assertFalse(truth(self.call('EL:NumberInputsCurrent', prepared)))

    def test_changed_cleared_and_raw_whitespace_changes_are_detected(self):
        for after in ('WL2', None, ' ZE9 ', ''):
            with self.subTest(after=after):
                self.stamp('w1', 'ZE9')
                result = self.extract()
                self.stamp('w1', after)
                self.assertFalse(truth(self.call('EL:NumberInputsCurrent', result)))
        self.assertEqual(self.get('circuit-number', self.get('circuits', self.extract())[0]), 'ZE1')

    def test_downstream_metadata_is_excluded_and_source_reads_are_bounded(self):
        self.f.line('w1', [1., 0., 0.], [20., 0., 0.], 'W')
        self.f.block('LAMP', 'D', 'late', [15., 10., 0.])
        self.f.line('late-wire', [15., 0., 0.], [15., 9., 0.], 'W')
        self.f.selected += ['late', 'late-wire']
        result = self.extract()
        self.stamp('late-wire', 'ZE99')
        reads = []
        original = self.h.builtins['ENTGET']
        def entget(entity, apps=None):
            if apps == ['linenum']:
                reads.append(entity)
            return original(entity, apps)
        self.h.builtins['ENTGET'] = entget
        self.h.frames[0]['*EL:FRESHSCOPEENABLED*'] = True
        for _ in range(3):
            self.assertTrue(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.assertEqual(reads, ['w1', 'w2'] * 3)
        self.assertNotIn('late-wire', reads)

    def test_read_failure_is_not_silent_unmarked_fallback(self):
        result = self.extract()
        original = self.h.builtins['ENTGET']
        def entget(entity, apps=None):
            if entity == 'w1' and apps == ['linenum']:
                raise RuntimeError('read failed')
            return original(entity, apps)
        self.h.builtins['ENTGET'] = entget
        self.assertFalse(truth(self.call('EL:NumberInputsCurrent', result)))
        failed = self.extract()
        self.assertEqual(self.get('number-status', self.get('circuits', failed)[0]), Symbol('INVALID'))
        self.assertIsNone(self.get('circuit-number', self.get('circuits', failed)[0]))

    def test_number_change_preserves_manual_gap_pairs_and_geometry_rules(self):
        self.f.gap_plan()
        network = self.f.network()
        pairs = [self.call('EL:Put', Symbol('SOURCE'), Symbol('MANUAL'), p) for p in self.get('gap-pairs', network)]
        self.f.cfg = self.call('EL:Put', Symbol('GAP-PAIRS'), pairs, self.f.cfg)
        result = self.extract()
        before = self.get('signature', self.get('snapshot', result))
        self.stamp('before', 'ZE7')
        after = self.extract()
        self.assertEqual(before, self.get('signature', self.get('snapshot', after)))
        self.assertEqual(self.get('gap-pairs', self.f.cfg), pairs)
        self.assertTrue(truth(self.call('EL:FreshResult', after, self.f.cfg)))


class NumberPersistenceTests(unittest.TestCase):
    call = NumberReadTests.call
    get = NumberReadTests.get

    def setUp(self):
        self.f = update.UpdateTests()
        self.f.setUp()
        self.f.install_sync()
        self.h = self.f.h
        self.stamp('H1', 'WL7')
        self.stamp('H2', 'ZE3')
        rows = []
        for c, handle in zip(self.get('circuits', self.h.lookup('RESULT')), ('H1', 'H2')):
            c = self.call('EL:Put', Symbol('GROUND-SOURCE'), Symbol('MANUAL'), c)
            rows.append(self.call('EL:Put', Symbol('NUMBER-SCOPE'),
                                 [pair('status', Symbol('READY')), pair('sources', [handle])], c))
        self.raw = self.call('EL:Put', Symbol('ENGINE'), Symbol('FIXED'),
                             self.call('EL:Put', Symbol('CIRCUITS'), rows, self.h.lookup('RESULT')))
        self.refresh()

    def stamp(self, handle, text):
        self.f.entities[handle] = [Pair(0, 'LINE'), Pair(5, handle), Pair(410, 'Model'),
                                  [-3, ['linenum', Pair(1000, text)]]]

    def refresh(self):
        self.result = self.call('EL:PreparedResult', self.raw, self.h.lookup('RECORD'))
        self.h.frames[0]['RESULT'] = self.result

    def sync(self):
        return self.h.run("(EL:SyncDiagram result cfg nil 'cap300 nil T)")

    def saved(self):
        return self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')




    def test_corrupt_number_store_readback_rolls_back_graphics_and_records(self):
        self.assertTrue(truth(self.sync()))
        self.stamp('H1', 'ZE8')
        self.refresh()
        original = self.h.builtins['VLA-SETXRECORDDATA']
        before = copy.deepcopy((self.f.entities, self.f.dictionary, self.f.dynamic))
        target = self.f.dictionary['EL_FIXED_V1']
        def corrupt(entity, codes, values):
            original(entity, codes, values)
            if entity == target:
                self.f.entities[entity][-1] = Pair(2, 'BROKEN')
        self.h.builtins['VLA-SETXRECORDDATA'] = corrupt
        self.assertFalse(truth(self.sync()))
        self.assertEqual(before, (self.f.entities, self.f.dictionary, self.f.dynamic))



class NumberWorkflowTests(unittest.TestCase):
    call = NumberReadTests.call
    get = NumberReadTests.get

    def setUp(self):
        self.f = workflow.PostStatWorkflowTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.h = self.f.h

    def five_exits(self, marked=True):
        f = self.f
        f.block('BOX', 'P', 'panel', [0., 0., 0.])
        f.entities['panel'] += [Pair(41, 100.), Pair(42, 100.)]
        f.bounds['panel'] = [[-100., -100., 0.], [100., 100., 0.]]
        f.selected = ['panel']
        for i, y in enumerate((-80., -40., 0., 40., 80.), 1):
            f.block('LAMP', 'D', f'lamp{i}', [1000., y, 0.])
            f.line(f'w{i}', [100., y, 0.], [999., y, 0.], 'W')
            if marked:
                f.entities[f'w{i}'].append([-3, ['linenum', Pair(1000, f'ZE{6-i}')]])
            f.selected += [f'lamp{i}', f'w{i}']
        picks = iter([['panel', [0., 0., 0.]]] +
                     [[f'w{i}', [100., y, 0.]] for i,y in enumerate((-80.,-40.,0.,40.,80.),1)] + [None])
        self.h.builtins['EL:PICKMODEL'] = lambda *args: next(picks)
        self.seen = []

    def capture_panel(self):
        self.seen.append(copy.deepcopy(self.h.lookup('*EL:PANELDRAFT*')))
        self.f.done(0)

    def test_actual_elstat_pick_five_plane_numbers_reach_panel_and_plan(self):
        self.five_exits()
        self.f.actions = [lambda: self.f.done(9), self.capture_panel]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.f.dialogs, ['el_panel', 'el_panel'])
        result = self.seen[0]
        circuits = self.get('circuits', result)
        self.assertEqual(len(circuits), 5)
        self.assertEqual([self.get('circuit-number', c) for c in circuits], [f'ZE{i}' for i in range(1, 6)])
        for index, c in enumerate(circuits):
            source = self.get('sources', self.get('number-scope', c))
            self.assertEqual(len(source), 1)
            expected = 'ZE' + str(6-int(source[0][1:]))
            self.assertEqual(self.get('circuit-number', c), expected)
            self.assertTrue(self.f.tiles[f'p_row{index}'].startswith(expected + ' | '))
            self.assertEqual(self.get('devices', c), ['lamp' + source[0][1:]])
        update.UpdateTests.generation_fixture(self.f)
        self.h.run('''(setq template (EL:Put 'panel (EL:Put 'name "ZYF_Tool_应急照明配电箱图块" (EL:Get 'panel template))
          (EL:Put 'circuit (EL:Put 'name "ZYF_Tool_应急照明配电回路图块" (EL:Get 'circuit template)) template)))''')
        result = self.call('EL:PanelCompute', result, self.f.powers, self.f.cfg)
        self.assertTrue(truth(self.get('can-generate', result)))
        plan = self.call('EL:FixedPlan', result, self.h.lookup('TEMPLATE'), Symbol('CAP300'), [0., 0., 0.], 0., 1.)
        labels = self.call('EL:CCKKLabels', plan)
        actual = [self.get('text', label) for label in labels if self.get('kind', label) == Symbol('NUMBER')][:5]
        self.assertEqual(actual, [self.get('circuit-number', c) for c in circuits])
        self.assertEqual(self.f.writes, [])

    def test_actual_pick_without_plane_numbers_keeps_original_order_defaults(self):
        self.five_exits(marked=False)
        self.f.actions = [self.capture_panel]
        self.call('EL:FixedStatPick')
        circuits = self.get('circuits', self.seen[0])
        self.assertEqual([self.get('circuit-number', c) for c in circuits], [f'ZE{i}' for i in range(1, 6)])
        self.assertEqual([self.get('number-source', c) for c in circuits], [Symbol('AUTO')] * 5)
        self.assertEqual(len(self.get('number-inputs', self.seen[0])), 5)
        self.assertEqual(self.f.writes, [])


    def test_number_change_during_native_placement_aborts_and_rolls_back(self):
        f = command_fixture.PanelCommandTests()
        f.setUp()
        # Date: 2026-10-13. This placement fixture has no drawing config file.
        f.h.builtins['FINDFILE'] = lambda *args: None
        # Date: 2026-10-21. This finite drawing has no native number annotations.
        f.h.builtins['SSGET'] = lambda *args: None
        f.h.builtins.pop('EL:FRESHRESULT')
        f.h.load_definitions(ROOT / 'src/simple.lsp')
        f.entities['H1'] = [Pair(0, 'LINE'), Pair(5, 'H1'), Pair(410, 'Model'),
                            [-3, ['linenum', Pair(1000, 'WL7')]]]
        f.h.run('''(setq cfg (EL:Put 'drawing "fixture" cfg)
          snapshot (EL:CircuitSnapshot '((drawing . "fixture") (wires)) "source"))
          (setq result (EL:Put 'snapshot snapshot (EL:Put 'drawing "fixture"
            (EL:Put 'rules (EL:RecognitionRules cfg) (EL:Put 'engine 'fixed result)))))
          (setq c (car (EL:Get 'circuits result)))
          (setq result (EL:Put 'circuits (list (EL:Put 'ground-source 'manual
            (EL:Put 'number-scope '((status . ready) (sources "H1")) c))) result))
          (setq result (EL:PreparedResult result record))''')
        f.h.builtins['EL:FIXEDFRESHSNAPSHOT'] = lambda *args: f.h.lookup('SNAPSHOT')
        self.assertTrue(truth(f.call('EL:FreshResult', f.h.lookup('RESULT'), f.h.lookup('CFG'))))
        original = f.h.builtins['COMMAND']
        events = []
        f.h.builtins['EL:LOGEVENT'] = lambda name, data: events.append((name, data))
        plane = copy.deepcopy(f.entities['H1'])
        def command(*args):
            original(*args)
            f.entities['H1'][-1] = [-3, ['linenum', Pair(1000, 'WL8')]]
        f.h.builtins['COMMAND'] = command
        self.assertFalse(truth(f.invoke()))
        self.assertEqual(len(f.commands), 1)  # Stop after the box placement, before circuit output.
        self.assertFalse(any(e.startswith('native-') for e in f.entities))
        self.assertEqual(f.entities['H1'], plane)
        self.assertFalse(truth(f.h.lookup('*EL:TRANSACTIONOPEN*')))
        self.assertTrue(any(name == 'SOURCE_NUMBER_CHANGED' for name, _ in events))

    def test_diagnostics_and_counters_are_bounded_to_first_segment_sources(self):
        self.five_exits()
        events = []
        self.h.builtins['EL:LOGEVENT'] = lambda name, data: events.append((name, data))
        self.call('EL:PerfStart', 'NUMBER_CHECK')
        result = self.call('EL:PreparedResult', self.call('EL:RecognizeFixed', self.f.cfg, 'panel'),
                           [pair('diagram-id', 'd1')])
        metrics = self.h.lookup('*EL:PERFMETRICS*')
        self.assertEqual(self.call('EL:Get', 'number-scopes', metrics), 5)
        self.assertEqual(self.call('EL:Get', 'number-source-handles', metrics), 5)
        self.assertEqual(self.call('EL:Get', 'number-source-read-attempts', metrics), 5)
        self.assertEqual(self.call('EL:Get', 'number-problems', metrics), 0)
        numbered = [(name, data) for name, data in events if name.startswith('CIRCUIT_NUMBER_')]
        self.assertEqual(len(numbered), 15)
        self.assertTrue(all(len(update.db.dump(data)) < 1000 for _, data in numbered))
        self.assertEqual(self.get('status', self.get('number-scope', self.get('circuits', result)[0])), Symbol('READY'))

if __name__ == '__main__':
    unittest.main()
