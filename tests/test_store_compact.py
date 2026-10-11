"""Lossless compact-envelope checks; no native CAD acceptance. Date: 2026-10-11."""
import copy
import pathlib
import unittest

from autolisp_host import Host, Pair, Symbol, car, cdr, cons, equal, parse, seq
from test_diagram_store import dump

ROOT = pathlib.Path(__file__).resolve().parents[1]


class StoreCompactTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for module in ('common', 'diagram-store', 'store-compact'):
            self.h.load_definitions(ROOT / 'src' / f'{module}.lsp')
        self.h.builtins.update({'VL-PRIN1-TO-STRING': dump, 'GETVAR': lambda _: None})

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, data):
        return self.call('EL:Get', Symbol(key.upper()), data)

    def put(self, key, value, data):
        return self.call('EL:Put', Symbol(key.upper()), value, data)

    def native_encode(self, value, marker):
        if 'EL:STOREENCODENATIVE' in self.h.functions:
            return self.call('EL:StoreEncodeNative', value, marker)
        return self.call('EL:StoreEncode', value)

    def native_decode(self, tokens, marker):
        if 'EL:STOREDECODENATIVE' in self.h.functions:
            return self.call('EL:StoreDecodeNative', tokens, marker)
        return self.call('EL:StoreDecode', tokens)

    def fixture(self):
        return parse('''((schema-version . 1) (drawing-uuid . "中文图纸")
            (fixed-template (panel (name . "箱") (choices "当前" "预留"))
              (circuit (name . "回路")) (step 0.0 -200.0 0.0))
            (diagrams ((diagram-id . "stable/box/1")
              (config (template (panel (name . "箱") (choices "当前" "预留"))
                (circuit (name . "回路")) (step 0.0 -200.0 0.0)))
              (template (panel (name . "箱") (choices "当前" "预留"))
                (circuit (name . "回路")) (step 0.0 -200.0 0.0))
              (source-signature EL_FIXED_SOURCE_V1
                ((wires ((id . "A1") (layer . "布线") (points (0.0 1.0 0.0)))
                        ((id . "A2") (layer . "布线") (points (2.0 3.0 0.0)))))))))''')[0]

    def roundtrip(self, store):
        before = copy.deepcopy(store)
        packed = self.call('EL:StoreCompact', store)
        native = self.native_encode(packed, 'EL_COMPACT_TYPED_V2')
        decoded = self.native_decode(native, 'EL_COMPACT_TYPED_V2')
        restored = self.call('EL:StoreExpand', decoded)
        self.assertTrue(equal(before, store))
        self.assertTrue(equal(before, restored))
        return packed, native

    def test_empty_new_store_roundtrip(self):
        self.roundtrip(parse('((schema-version . 1) (drawing-uuid . "新图") (diagrams))')[0])

    def test_full_template_copies_pool_once_and_preserve_structure(self):
        store = self.fixture()
        packed, native = self.roundtrip(store)
        self.assertEqual(len(self.get('templates', packed)), 1)
        self.assertLess(len(native), len(self.native_encode(store, 'EL_TYPED_V1')))

    def test_multiple_exact_templates_and_historical_global_version(self):
        store = self.fixture()
        record = self.get('diagrams', store)[0]
        other_template = self.put('revision', 2, self.get('template', record))
        other_config = self.put('template', other_template, self.get('config', record))
        other = self.put('template', other_template, self.put('config', other_config, record))
        store = self.put('diagrams', [record, other], store)
        historical = self.put('revision', 0, self.get('fixed-template', store))
        store = self.put('fixed-template', historical, store)
        packed, _ = self.roundtrip(store)
        self.assertEqual(len(self.get('templates', packed)), 3)

    def test_conflicting_copies_fail_before_compaction(self):
        store = self.fixture()
        record = self.get('diagrams', store)[0]
        changed = self.put('revision', 3, self.get('template', record))
        record = self.put('template', changed, record)
        store = self.put('diagrams', [record], store)
        with self.assertRaises(RuntimeError):
            self.call('EL:StoreCompact', store)

    def test_explicit_empty_template_and_missing_copy_are_preserved(self):
        store = self.fixture()
        record = self.get('diagrams', store)[0]
        record = self.put('template', None, record)
        store = self.put('diagrams', [record], self.put('fixed-template', None, store))
        packed, _ = self.roundtrip(store)
        restored = self.call('EL:StoreExpand', packed)
        self.assertIsNone(self.get('fixed-template', restored))
        self.assertTrue(any(car(row) == Symbol('FIXED-TEMPLATE') for row in restored))
        self.assertIsNone(self.get('template', self.get('diagrams', restored)[0]))
        self.assertTrue(equal(self.get('config', record),
                              self.get('config', self.get('diagrams', restored)[0])))

    def test_unknown_fields_controls_small_real_and_int_limits_stay_exact(self):
        store = self.put('unknown-future',
            [Pair(Symbol('TINY'), 1.203456789012345e-98),
             Pair(Symbol('NEGATIVE'), -0.00345678901234567),
             Pair(Symbol('LARGEST'), 2147483647),
             Pair(Symbol('SMALLEST'), -2147483648),
             Pair(Symbol('TRUE'), True),
             cons(Symbol('EMPTY'), None),
             Pair(Symbol('CONTROL'), '中文\t\n\r\x00\x1b"\\尾'),
             Pair(Symbol('DOTTED'), Pair('car', Pair('next', 'tail'))),
             Pair(Symbol('EXACT-SYMBOL'), Symbol('SAME')),
             Pair(Symbol('EXACT-STRING'), 'SAME')], self.fixture())
        _, native = self.roundtrip(store)
        self.assertTrue(all(len(p.cdr) <= 33 for p in native if p.car == 1))

    def test_dictionary_bucket_collisions_use_whole_content_identity(self):
        # Same length and first/last character deliberately share one bucket.
        # Symbol identity also remains different from a same-spelled string.
        values = ['AaA', 'AbA', 'AaA', 'AcA', 'AbA', Symbol('ABA'), 'ABA']
        packed, _ = self.roundtrip(self.put('collision-values', values, self.fixture()))
        atoms = self.get('atoms', packed)
        self.assertEqual(sum(equal(value, 'AaA') for value in atoms), 1)
        self.assertEqual(sum(equal(value, 'AbA') for value in atoms), 1)
        self.assertTrue(any(equal(value, Symbol('ABA')) for value in atoms))
        self.assertTrue(any(equal(value, 'ABA') for value in atoms))

    def test_long_repeated_strings_keep_bounded_native_segments(self):
        text = ('中文\t"\\\n' * 300) + '\x1b尾'
        packed, native = self.roundtrip(self.put('long-strings', [text, text, text], self.fixture()))
        self.assertEqual(sum(equal(value, text) for value in self.get('atoms', packed)), 1)
        self.assertTrue(all(len(row.cdr) <= 33 for row in native if row.car == 1))

    def test_future_format_and_codec_rejected(self):
        packed, _ = self.roundtrip(self.fixture())
        for key, value in [('format-version', 3), ('codec', Symbol('FUTURE'))]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.call('EL:StoreExpand', self.put(key, value, packed))

    def test_corrupt_and_out_of_range_tokens_rejected(self):
        packed, _ = self.roundtrip(self.fixture())
        for tape in (None, [-999999], [4, 999999], [4, -1], [2], [2, 1.0],
                     [9], [8], [5], ['invalid'], [0, 0], [3, 0, 0]):
            with self.subTest(tape=tape), self.assertRaises(RuntimeError):
                self.call('EL:StoreExpand', self.put('body', tape, packed))

    def test_malformed_pool_or_envelope_rejected(self):
        packed, _ = self.roundtrip(self.fixture())
        for changed in (packed + [Pair(Symbol('CODEC'), Symbol('EL_COMPACT_V1'))],
                        self.put('atoms', [1], packed),
                        self.put('templates', ['bad'], packed),
                        self.put('atoms', Pair('bad', 'tail'), packed)):
            with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                self.call('EL:StoreExpand', changed)

    def test_tampered_valid_template_reference_detects_copy_conflict(self):
        store = self.fixture()
        global_template = self.put('revision', 7, self.get('fixed-template', store))
        packed, _ = self.roundtrip(self.put('fixed-template', global_template, store))
        body = list(self.get('body', packed))
        # The global reference is 0; replace exactly one record reference 1.
        for index, token in enumerate(body[:-1]):
            if token == 4 and body[index + 1] == 1:
                body[index + 1] = 0
                break
        with self.assertRaises(RuntimeError):
            self.call('EL:StoreExpand', self.put('body', body, packed))

    def test_large_atom_pool_lookup_work_is_bounded_and_contents_stay_exact(self):
        values = [f'设备-{index:04d}-尾\\"' for index in range(650)] * 4
        store = self.put('lookup-work-sample', values, self.fixture())
        packed = self.call('EL:StoreCompact', store)
        visits = []
        original = self.h.builtins['NTH']

        def counted(index, rows):
            # AutoLISP NTH walks linked list cells; the Python host otherwise
            # uses a list index and cannot measure this algorithmic cost.
            visits.append(index + 1)
            return original(index, rows)

        self.h.builtins['NTH'] = counted
        restored = self.call('EL:StoreExpand', packed)
        old_visits = sum(-token for token in self.get('body', packed)
                         if isinstance(token, int) and token < 0)
        self.assertTrue(equal(store, restored))
        self.assertLess(sum(visits), old_visits / 5)
        self.__class__.lookup_work_evidence = {
            'atom_pool_count': len(self.get('atoms', packed)),
            'body_tokens': len(self.get('body', packed)),
            'flat_atom_reference_list_visits': old_visits,
            'paged_atom_and_template_reference_list_visits': sum(visits),
            'ratio_to_flat_atom_reference_visits': sum(visits) / old_visits,
            'logical_equal': True,
        }

    def test_many_template_versions_cross_page_boundaries_without_identity_loss(self):
        store = self.fixture()
        original = self.get('diagrams', store)[0]
        records = []
        for index in range(70):
            template = self.put('revision', index, self.get('template', original))
            record = self.put('template', template, original)
            record = self.put('config', self.put('template', template,
                self.get('config', record)), record)
            records.append(self.put('diagram-id', f'diagram/{index}', record))
        store = self.put('diagrams', records, store)
        packed, _ = self.roundtrip(store)
        self.assertEqual(len(self.get('templates', packed)), 71)


if __name__ == '__main__':
    unittest.main()
