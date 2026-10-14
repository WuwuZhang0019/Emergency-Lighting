"""Date: 2026-10-14. Lossless integer tape packing; native CAD timing remains unmeasured."""
import unittest
import re
from autolisp_host import Pair, Symbol, equal
from test_store_compact import StoreCompactTests


class StoreIntegerTapeTests(unittest.TestCase):
    def setUp(self):
        StoreCompactTests.setUp(self)
        # Native ATOI accepts a numeric prefix; canonical validation rejects the remainder.
        self.h.builtins['ATOI'] = lambda s: int(m.group()) if (m := re.match(r'^[+-]?\d+', s)) else 0
    call = StoreCompactTests.call
    get = StoreCompactTests.get
    put = StoreCompactTests.put
    fixture = StoreCompactTests.fixture

    def test_integer_limits_mixed_reals_and_short_runs_roundtrip(self):
        body = [-2147483648, 2147483647, -1, 0, 1] * 80 + [1.203456789012345e-98, 0, -0.00345678901234567]
        packed = self.call('EL:CompactPackIntegers', body)
        self.assertEqual(self.call('EL:CompactUnpackIntegers', packed), body)
        self.assertEqual(packed[-3:], body[-3:])
        self.assertTrue(all(len(x) <= 224 for x in packed if isinstance(x, str)))
        self.assertLess(len(packed), len(body) // 10)

    def test_bad_integer_chunks_rejected_without_evaluation(self):
        self.h.builtins['EVAL'] = lambda *_: self.fail('integer tape must not execute EVAL')
        for chunks in [['1'], [''], [' '], ['+1 '], ['01 '], ['1.0 '], ['-0 '],
                       ['1  2 '], ['2147483648 '], ['-2147483649 '], ['(exit) '],
                       ['1 ' * 113], [Symbol('BAD')]]:
            with self.subTest(chunks=chunks), self.assertRaises(RuntimeError):
                self.call('EL:CompactUnpackIntegers', chunks)

    def test_non_integer_alphabet_is_rejected_before_native_reader(self):
        reads = []
        self.h.builtins['READ'] = lambda text: reads.append(text)
        for chunk in ('(exit) ', '1) (exit) (2 ', '+1 ', '1.0 ', '1e2 ',
                      '1\n2 ', '1\t2 ', '1\x002 ', 'nil ', '中文 ', '1;2 ', '1\\2 ', "'1 "):
            with self.subTest(chunk=chunk), self.assertRaises(RuntimeError):
                self.call('EL:CompactUnpackIntegers', [chunk])
        self.assertEqual(reads, [], 'unsafe text reached native reader')

    def test_native_reader_is_bounded_and_real_fields_never_enter_text_path(self):
        reader = self.h.builtins['READ']
        reads = []
        def bounded(text):
            reads.append(text)
            self.assertLessEqual(len(text), 225)
            self.assertTrue(text.startswith('(') and text.endswith(')'))
            self.assertFalse(set(text[1:-1]) - set(' -0123456789'))
            return reader(text)
        self.h.builtins['READ'] = bounded
        body = [-2147483648, 2147483647, -1, 0, 1] * 80 + [1.e-98, -0.0, 1.0000000000000002]
        packed = self.call('EL:CompactPackIntegers', body)
        self.assertEqual(self.call('EL:CompactUnpackIntegers', packed), body)
        self.assertEqual(len(reads), sum(type(value) is str for value in packed))
        self.assertLess(len(reads), len(body) // 10)

    def test_native_reader_error_partial_result_and_overflow_are_rejected(self):
        def fail(*_): raise RuntimeError('native reader failed')
        for reader in (fail, lambda _: [1], lambda _: [1, 2147483648], lambda _: [1, 2.0],
                       lambda _: [1, Symbol('BAD')]):
            self.h.builtins['READ'] = reader
            with self.subTest(reader=reader), self.assertRaises(RuntimeError):
                self.call('EL:CompactUnpackIntegers', ['1 2 '])

    def test_public_store_codec_keeps_all_types_and_legacy_v2_readability(self):
        data = self.h.run("'" + '''((tiny . 1.203456789012345e-98) (int -2147483648 2147483647)
          (empty) (flag . T) (text . "中文\\nMiXeD") (pair x . y))''')
        store = self.put('extra', data, self.fixture())
        original = self.call('EL:StoreEncodeNative', self.call('EL:StoreCompact', store), 'EL_COMPACT_TYPED_V2')
        current = self.call('EL:StoreEncode', store)
        self.assertEqual(current[0], Pair(300, 'EL_COMPACT_TYPED_V3'))
        self.assertTrue(equal(self.call('EL:StoreDecode', original), store))
        self.assertTrue(equal(self.call('EL:StoreDecode', current), store))
        self.assertIn(Pair(40, 1.203456789012345e-98), current)

    def test_repeated_geometry_fixture_reduces_native_fields_without_dropping_data(self):
        row = self.h.run("'" + '''((id . "A1") (layer . "照明设备") (name . "灯具")
            (points (0.0 1.0 0.0) (200.0 1.0 0.0))
            (members "W1" "W2" "W3" "D1" "D2") (complete . T) (excluded))''')
        store = self.put('large-snapshot', [row] * 100, self.fixture())
        old = self.call('EL:StoreEncodeNative', self.call('EL:StoreCompact', store), 'EL_COMPACT_TYPED_V2')
        new = self.call('EL:StoreEncode', store)
        self.assertTrue(equal(self.call('EL:StoreDecode', new), store))
        self.assertLess(len(new), len(old) * .65)
        print(f'\nInteger tape fixture: {len(old)} -> {len(new)} DXF fields')


if __name__ == '__main__':
    unittest.main()
