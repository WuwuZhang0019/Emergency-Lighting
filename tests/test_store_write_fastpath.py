"""Date: 2026-10-14. Exact DXF boundaries and compact grammar; no CAD timing claim."""
import unittest

from autolisp_host import Pair, Symbol, truth
import test_store_compact as compact
import test_fallback_uuid_mbcs as mbcs


def legacy_chunks(text, unicode):
    """Independent byte/character boundary reference for the existing wire format."""
    codes = list(map(ord, text)) if unicode else list(mbcs.encoded(text))
    chunks = []
    start = 0
    while start < len(codes):
        end = start
        while end < len(codes) and end - start < 32:
            lead = codes[end]
            end += 1
            if not unicode and 128 <= lead <= 255 and end < len(codes):
                end += 1
        block = codes[start:end]
        chunks.append(Pair(1, ''.join(map(chr, block)) if unicode else mbcs.decoded(bytes(block))))
        start = end
    return chunks or [Pair(1, '')]


class StoreWriteFastpathTests(unittest.TestCase):
    def test_string_segments_match_legacy_for_ascii_chinese_and_both_engines(self):
        texts = ['', '短中文', 'A' * 32, '1 -2147483648 2147483647 ' * 50,
                 '中文' * 40, 'a' * 31 + '中文' * 30, 'a' * 32 + '中文',
                 '1' * 31 + '中' + '2' * 32, '\n\t\\"' * 20, 'é' * 40]
        for unicode in (False, True):
            f = compact.StoreCompactTests() if unicode else mbcs.FallbackUUIDTests()
            f.setUp()
            if unicode:
                f.h.builtins['GETVAR'] = lambda _: 1
            for text in texts:
                with self.subTest(unicode=unicode, text=text[:40]):
                    actual = f.h.call(Symbol('EL:STORESTRINGCHUNKS'), [text])
                    self.assertEqual(actual, legacy_chunks(text, unicode))
                    self.assertEqual(''.join(p.cdr for p in actual), text)

    def test_integer_tape_and_short_strings_do_not_expand_into_character_lists(self):
        f = compact.StoreCompactTests(); f.setUp()
        f.h.builtins['VL-STRING->LIST'] = lambda *_: self.fail('unnecessary character walk')
        for text in ('', '中文短文本', '0123456789 -' * 100, 'A' * 32):
            chunks = f.call('EL:StoreStringChunks', text)
            self.assertEqual(''.join(p.cdr for p in chunks), text)
            self.assertTrue(all(len(p.cdr) <= 32 for p in chunks))

    def test_proper_dotted_and_nested_lists_keep_exact_compact_types(self):
        f = compact.StoreCompactTests(); f.setUp()
        for expression, proper in [("nil", True), ("'(a b)", True), ("'(a . b)", False),
                                   ("'((a . b) 1.0)", True), ("3", False)]:
            with self.subTest(expression=expression):
                value = f.h.run(expression)
                self.assertEqual(truth(f.call('EL:CompactProperList', value)), proper)
                store = f.put('extension', value, f.fixture())
                wire = f.call('EL:StoreEncode', store)
                self.assertEqual(f.call('EL:StoreDecode', wire), store)


if __name__ == '__main__':
    unittest.main()
