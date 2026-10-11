"""Actual circuit-number functions, bounded DWG adapters. Date: 2026-10-11."""
from pathlib import Path
import copy
import unittest
from autolisp_host import Host, Pair, Symbol, cons, parse, quoted, truth
import test_simple_flow as simple
import test_diagram_update as update
import test_cckk_panel_command as command_fixture

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

    def test_renumber_updates_existing_caption_handles_without_moving(self):
        self.set_numbers()
        before = [p for p in self.f.entities['caption-number/u1'] if isinstance(p, Pair) and p.car in (10, 11)]
        self.h.run('(EL:SyncCCKKLabels plan record store nil)')
        self.assertIn(('caption-number/u1', 'WL7'), self.f.writes)
        self.assertIn(('caption-number/u2', 'ZE3'), self.f.writes)
        self.assertEqual(self.f.deleted, [])
        self.assertEqual(before, [p for p in self.f.entities['caption-number/u1'] if isinstance(p, Pair) and p.car in (10, 11)])

    def test_conflict_blocks_generate_and_plan_but_keeps_draft(self):
        self.h.run('''(setq result (EL:Put 'circuits (list (EL:Put 'number-status 'conflict
          (EL:Put 'number-evidence '((candidates "ZE1" "ZE2")) (car cs)))) result))
          (setq *EL:PanelDraft* result *EL:PanelTemplateReady* T)''')
        self.assertIsNone(self.h.run("(EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0)"))
        done, tiles = [], {}
        self.h.builtins.update({'EL:PANELSTORESELECTIONS': lambda: True,
                               'SET_TILE': lambda k, v: tiles.__setitem__(k, v), 'DONE_DIALOG': done.append})
        self.call('EL:PanelGenerateBody')
        self.assertEqual(done, [])
        self.assertIn('编号冲突', tiles['p_error'])
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

    def test_formal_fields_exact_readback_noop_and_plane_is_readonly(self):
        plane = copy.deepcopy({h: self.f.entities[h] for h in ('H1', 'H2')})
        self.assertTrue(truth(self.sync()))
        record = self.saved()
        actual = self.get('rows', record)[:2]
        self.assertEqual([self.get('circuit-number', c) for c in actual], ['WL7', 'ZE3'])
        self.assertEqual([self.get('number-source', c) for c in actual], [Symbol('PLANE')] * 2)
        self.assertEqual(self.get('number-inputs', record), self.get('number-inputs', self.result))
        before = copy.deepcopy(self.f.entities)
        self.assertTrue(truth(self.sync()))
        self.assertEqual(before, self.f.entities)
        self.assertEqual(plane, {h: self.f.entities[h] for h in ('H1', 'H2')})

    def test_renumber_preserves_uid_output_handles_and_manual_caption_position(self):
        self.assertTrue(truth(self.sync()))
        old = self.saved()
        self.call('EL:MoveManaged', 'caption-number/u1', [77., 88., 0.])
        point = self.call('EL:TextPoint', 'caption-number/u1')
        self.stamp('H1', 'ALE-ZE8')
        self.refresh()
        self.assertTrue(truth(self.sync()))
        new = self.saved()
        self.assertEqual([self.get('circuit-uid', c) for c in self.get('rows', old)],
                         [self.get('circuit-uid', c) for c in self.get('rows', new)])
        self.assertEqual([self.get('block-handle', c) for c in self.get('rows', old)],
                         [self.get('block-handle', c) for c in self.get('rows', new)])
        self.assertEqual(point, self.call('EL:TextPoint', 'caption-number/u1'))
        self.assertEqual(self.get('circuit-number', self.get('rows', new)[0]), 'ALE-ZE8')

    def test_conflicting_draft_is_saved_separately_from_last_formal_inputs(self):
        self.assertTrue(truth(self.sync()))
        old = self.saved()
        old_labels = copy.deepcopy({k: v for k, v in self.f.entities.items() if k.startswith('caption-')})
        self.stamp('H2', 'WL7')
        self.refresh()
        self.h.builtins['EL:TEMPLATEREADY'] = lambda *args: None
        self.assertTrue(truth(self.h.run("(EL:SaveDraft result cfg nil 'cap300)")))
        saved = self.saved()
        self.assertEqual(self.get('status', saved), Symbol('STALE'))
        self.assertEqual(self.get('number-inputs', saved), self.get('number-inputs', old))
        self.assertEqual(self.get('draft-number-inputs', saved), self.get('number-inputs', self.result))
        self.assertEqual(self.get('number-status', self.get('draft-circuits', saved)[0]), Symbol('CONFLICT'))
        self.assertEqual(old_labels, {k: v for k, v in self.f.entities.items() if k.startswith('caption-')})

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

if __name__ == '__main__':
    unittest.main()
