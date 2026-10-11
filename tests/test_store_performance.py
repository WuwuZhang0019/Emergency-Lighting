"""Storage work counts and exact readback checks. Date: 2026-10-11.

Adapter measurements describe copied characters, not native AutoCAD time.
"""
import math
import unittest

from autolisp_host import Pair, Symbol
import test_diagram_store as fixtures


class StorePerformanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.StoreTests()
        self.fixture.setUp()
        self.h = self.fixture.h

    def test_large_native_signature_has_bounded_copy_work_and_exact_contents(self):
        # Approximately the 305k signature seen in the supplied 091 failure.
        signature = ('中文 MixedCase "298B" \\path\n\t\r\x00' * 12000)[:305113]
        parts = [signature[i:i+32] for i in range(0, len(signature), 32)]
        tokens = [Pair(300, 'EL_TYPED_V1'), Pair(2, 'S')]
        tokens += [Pair(1, part) for part in parts] + [Pair(2, 'E')]
        copies = []
        original = self.h.builtins['STRCAT']
        def counted(*args):
            copies.append(sum(map(len, args)))
            return original(*args)
        self.h.builtins['STRCAT'] = counted
        self.assertEqual(self.h.call(Symbol('EL:STOREDECODE'), [tokens]), signature)
        copied = sum(copies)
        self.assertLessEqual(copied, len(signature) * math.ceil(math.log2(len(parts))))
        old_copied = sum(min(32*i, len(signature)) for i in range(1, len(parts)+1))
        self.assertLess(copied, old_copied / 100)

    def test_join_empty_single_odd_chunks_and_order(self):
        for parts in ([], [''], ['中文'], ['', 'A', '中', '尾', '\x00']):
            with self.subTest(parts=parts):
                self.assertEqual(self.h.call(Symbol('EL:STOREJOINSTRINGS'), [parts]), ''.join(parts))

    def test_malformed_native_string_is_still_rejected(self):
        for body in ([Pair(2, 'S'), Pair(2, 'E')],
                     [Pair(2, 'S'), Pair(1, 'x')],
                     [Pair(2, 'S'), Pair(1, 'x'*241), Pair(2, 'E')],
                     [Pair(2, 'S'), Pair(1, 42), Pair(2, 'E')]):
            with self.subTest(body=body), self.assertRaises(RuntimeError):
                self.h.call(Symbol('EL:STOREDECODE'), [[Pair(300, 'EL_TYPED_V1')] + body])

    def test_save_decodes_audited_entry_without_another_dictionary_read(self):
        reads = []
        search = self.h.builtins['DICTSEARCH']
        self.h.builtins['DICTSEARCH'] = lambda *args: (reads.append(args), search(*args))[1]
        self.assertTrue(self.h.run('(EL:StoreWrite (EL:StoreInitial))'))
        # One read locates the write target; one obtains actual readback.
        self.assertEqual(len(reads), 2)
        self.assertEqual(self.h.run('(EL:StoreRead)'), self.h.run('(EL:StoreInitial)'))
        self.assertEqual(len(reads), 3)

    def test_entity_readback_difference_cannot_hide_behind_correct_dictionary(self):
        get = self.h.builtins['ENTGET']
        self.h.builtins['ENTGET'] = lambda *args: get(*args) + [Pair(1, 'unexpected')]
        with self.assertRaises(RuntimeError):
            self.h.run('(EL:StoreWrite (EL:StoreInitial))')


if __name__ == '__main__':
    unittest.main()
