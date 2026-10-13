"""Native payload extraction work and corruption boundaries.

Date: 2026-10-13. Status: adapter checks, not native CAD timing.
"""
import unittest

from autolisp_host import Pair, Symbol
import test_diagram_store as fixtures


class PayloadTailTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.StoreTests()
        self.f.setUp()
        self.h = self.f.h

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def header(self, flag=1):
        return [Pair(-1, 'entity'), Pair(0, 'XRECORD'), Pair(5, '123'),
                Pair(102, '{ACAD_REACTORS'), Pair(330, 'reactor'), Pair(102, '}'),
                Pair(330, 'NOD'), Pair(100, 'AcDbXrecord'), Pair(280, flag)]

    def test_large_typed_payload_never_uses_per_field_filter(self):
        visits = []
        member = self.h.builtins['MEMBER']
        self.h.builtins['MEMBER'] = lambda key, values: (visits.append(key), member(key, values))[1]
        def reject_filter(*_):
            self.fail('canonical payload used a per-field Lisp predicate')
        self.h.builtins['VL-REMOVE-IF-NOT'] = reject_filter
        payload = [Pair(300, 'EL_TYPED_V1')] + [Pair(40, i + .125) for i in range(20000)]
        for flag in (0, 1, 2, 5):
            with self.subTest(flag=flag):
                visits.clear()
                self.assertEqual(self.call('EL:StorePayload', self.header(flag) + payload), payload)
                self.assertEqual(len(visits), len(self.header(flag)))

    def test_valid_typed_versions_keep_exact_chinese_and_real_roundtrip(self):
        store = self.call('EL:StoreInitial') + [Pair(Symbol('NOTES'), '中文完整记录'),
                                               Pair(Symbol('PRECISE'), -1e-280)]
        payloads = [self.call('EL:StoreEncodeLegacy', store),
                    self.call('EL:StoreEncodeNative', self.call('EL:StoreCompact', store),
                              'EL_COMPACT_TYPED_V2'),
                    self.call('EL:StoreEncode', store)]
        for payload in payloads:
            with self.subTest(marker=payload[0]):
                actual = self.call('EL:StorePayload', self.header() + payload)
                self.assertEqual(actual, payload)
                self.assertEqual(self.call('EL:StoreDecode', actual), store)

    def test_unexpected_fields_inside_typed_payload_are_not_silently_filtered(self):
        payload = self.call('EL:StoreEncode', self.call('EL:StoreInitial'))
        for extra in (Pair(330, 'injected'), Pair(280, 2), Pair(100, 'injected'), Pair(40, 99.0)):
            for offset in (1, len(payload)):
                corrupted = payload[:offset] + [extra] + payload[offset:]
                actual = self.call('EL:StorePayload', self.header() + corrupted)
                self.assertEqual(actual, corrupted)
                with self.assertRaises(RuntimeError):
                    self.call('EL:StoreCheck', payload, actual, Symbol('TEST'))
                with self.assertRaises(RuntimeError):
                    self.call('EL:StoreDecode', actual)

    def test_missing_tail_and_unknown_version_are_rejected_by_decoder(self):
        for payload in ([Pair(300, 'EL_COMPACT_TYPED_V9'), Pair(2, 'N')],
                        [Pair(300, 'EL_TYPED_V1')]):
            actual = self.call('EL:StorePayload', self.header() + payload)
            self.assertEqual(actual, payload)
            with self.assertRaises(RuntimeError):
                self.call('EL:StoreDecode', actual)

    def test_legacy_and_noncanonical_headers_keep_compatible_filter(self):
        payload = self.call('EL:StoreEncode', self.call('EL:StoreInitial'))
        for header in ([], [Pair(0, 'XRECORD')], self.header() + [Pair(330, 'NOD')]):
            self.assertEqual(self.call('EL:StorePayload', header + payload), payload)
        legacy = [Pair(1, 'legacy'), Pair(1, 'text')]
        self.assertEqual(self.call('EL:StorePayload', self.header() + legacy), legacy)
        self.assertIsNone(self.call('EL:StorePayload', None))
        self.assertIsNone(self.call('EL:StorePayload', self.header()))

    def test_data_before_subclass_is_not_hidden_by_later_header(self):
        payload = self.call('EL:StoreEncode', self.call('EL:StoreInitial'))
        entry = [Pair(1, 'unexpected prefix')] + self.header() + payload
        self.assertEqual(self.call('EL:StorePayload', entry), [Pair(1, 'unexpected prefix')] + payload)

    def test_noncanonical_header_cannot_hide_unknown_fields_inside_payload(self):
        payload = self.call('EL:StoreEncode', self.call('EL:StoreInitial'))
        for header in ([], [Pair(0, 'XRECORD')], self.header() + [Pair(330, 'NOD')]):
            corrupted = payload[:1] + [Pair(330, 'injected')] + payload[1:]
            actual = self.call('EL:StorePayload', header + corrupted)
            self.assertEqual(actual, corrupted)
            with self.assertRaises(RuntimeError):
                self.call('EL:StoreDecode', actual)


if __name__ == '__main__':
    unittest.main()
