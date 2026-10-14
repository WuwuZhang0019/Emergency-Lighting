"""Date: 2026-10-14. Exact cold decoding and malformed numeric-list boundaries."""
import copy
import unittest

from autolisp_host import Pair, Symbol, equal, truth
import test_store_compact as compact
import test_diagram_store as db


class StoreReadFastpathTests(unittest.TestCase):
    def setUp(self):
        self.f = compact.StoreCompactTests(); self.f.setUp()
        self.h = self.f.h

    def test_mixed_native_real_runs_keep_types_order_and_nested_structure(self):
        values = self.h.run("'" + '''((0.0 -0.0 1.203456789012345e-98)
            (1.0000000000000002 0 1 -2147483648 2147483647 T nil)
            ((0.0 . real-tail) (0.0 (1.5 2.5) 3.5) "中文" SYM "SYM"))''')
        store = self.f.put('extension', values * 40, self.f.fixture())
        packed = self.f.call('EL:StoreCompact', store)
        for wire in (self.f.call('EL:StoreEncodeNative', packed, 'EL_COMPACT_TYPED_V2'),
                     self.f.call('EL:StoreEncode', store)):
            restored = self.f.call('EL:StoreDecode', wire)
            self.assertTrue(equal(restored, store))
            extension = self.f.get('extension', restored)
            self.assertTrue(all(type(item) is float for item in extension[0]))
            self.assertIs(type(extension[1][1]), int)
            self.assertIs(extension[1][-2], True)
            self.assertIsNone(extension[1][-1])

    def test_real_fast_path_does_not_hide_truncated_invalid_or_trailing_tokens(self):
        packed = self.f.call('EL:StoreCompact', self.f.fixture())
        for tokens in ([10, 1.e-98], [10, 1.e-98, 5], [10, 0.0, -999999],
                       [11, 0.0, 2, 2147483647], [9, 0.0, 0],
                       [10, 0.0, 3, 0, 0], [2147483647, 0.0]):
            with self.subTest(tokens=tokens), self.assertRaises(RuntimeError):
                self.f.call('EL:StoreExpand', self.f.put('body', tokens, packed))
        self.assertTrue(equal(self.f.call('EL:StoreExpand', packed), self.f.fixture()))

    def test_empty_and_dotted_pools_keep_validation_after_single_pass_counting(self):
        packed = self.f.call('EL:StoreCompact', self.f.fixture())
        self.assertEqual(self.f.call('EL:CompactPoolLength', None), 0)
        for key in ('body', 'atoms', 'templates'):
            for value in (Pair(0.0, 'broken'), 1.0, 'broken'):
                with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                    self.f.call('EL:StoreExpand', self.f.put(key, value, packed))

    def test_cold_monolithic_read_preserves_all_records_and_writes_nothing(self):
        f = db.StoreTests(); f.setUp(); f.install_transaction()
        f.h.load_definitions(db.ROOT / 'src/store-split.lsp')
        f.h.run('''(setq *EL:SplitStorageLoaded* T store (EL:StoreInitial)
          store (EL:Put 'diagrams
            '(((diagram-id . "one") (source-panel-handle . "P1")
               (source-signature EL_FIXED_SOURCE_V1 ((points (0.0 1.e-98 1.0000000000000002)))))
              ((diagram-id . "two") (source-panel-handle . "P2") (unknown . "完整保留"))) store))
          (EL:StoreWriteMonolithic store)
          (setq *EL:StoreReadCache* nil *EL:StoreWarmCache* nil)
          (EL:PerfStart "ELSTAT")''')
        before = copy.deepcopy((f.entities, f.dictionary))
        self.assertTrue(truth(f.h.run('(equal store (EL:StoreIndex))')))
        self.assertEqual((f.entities, f.dictionary), before)
        self.assertEqual(f.h.run('(EL:Get "master-write-attempts" *EL:PerfMetrics*)'), 0)
        self.assertTrue(truth(f.h.run('(equal store (EL:StoreRead))')))
        self.assertEqual(f.h.run('(EL:Get "store-read-cache-misses" *EL:PerfMetrics*)'), 1)


if __name__ == '__main__':
    unittest.main()
