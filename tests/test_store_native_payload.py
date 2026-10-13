"""Split native read regression checks. Date: 2026-10-13. Status: adapter evidence only."""
import copy
import unittest
from pathlib import Path

from autolisp_host import Pair, Symbol, truth
import test_diagram_store as store_fixture

ROOT = Path(__file__).resolve().parents[1]


class SplitNativeReadTests(unittest.TestCase):
    def setUp(self):
        self.f = store_fixture.StoreTests()
        self.f.setUp()
        self.h = self.f.h
        self.h.load_definitions(ROOT / 'src/store-split.lsp')
        self.key = 'EL_SPLIT_NATIVE_TEST'
        self.payload = self.call('EL:StoreEncode', self.call(
            'EL:SplitEnvelope', Symbol('BLOB'), [float(i) + .125 for i in range(120)]))
        self.entity = self.h.builtins['ENTMAKEX']([
            Pair(0, 'XRECORD'), Pair(100, 'AcDbXrecord'), Pair(280, 1)] + self.payload)
        self.f.dictionary[self.key] = self.entity
        self.context = self.call('EL:SplitAudit', self.key, self.entry())

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def entry(self):
        return self.h.builtins['DICTSEARCH']('NOD', self.key)

    def test_context_validation_reads_native_entity_once(self):
        reads = []
        native = self.h.builtins['ENTGET']
        self.h.builtins['ENTGET'] = lambda entity: (reads.append(entity), native(entity))[1]
        self.assertTrue(truth(self.call('EL:SplitChunkValid', self.context)))
        self.assertEqual(reads, [self.entity])

    def test_audit_extracts_each_native_payload_once_and_retains_all_fields(self):
        extractions = []
        self.h.functions['TEST:PAYLOAD'] = self.h.functions['EL:STOREPAYLOAD']
        self.h.builtins['EL:STOREPAYLOAD'] = lambda entry: (
            extractions.append(copy.deepcopy(entry)), self.call('TEST:Payload', entry))[1]
        context = self.call('EL:SplitAudit', self.key, self.entry())
        self.assertEqual(len(extractions), 2)
        self.assertEqual(self.call('EL:Get', Symbol('PAYLOAD'), context), self.payload)

    def test_native_only_corruption_still_rejects_validation_and_audit(self):
        native = self.h.builtins['ENTGET']
        self.h.builtins['ENTGET'] = lambda entity: native(entity) + [Pair(40, 987.125)]
        self.assertFalse(truth(self.call('EL:SplitChunkValid', self.context)))
        with self.assertRaises(RuntimeError):
            self.call('EL:SplitAudit', self.key, self.entry())

    def test_missing_native_object_still_rejects_stale_dictionary_entry(self):
        self.h.builtins['ENTGET'] = lambda entity: None
        self.assertFalse(truth(self.call('EL:SplitChunkValid', self.context)))
        with self.assertRaises(RuntimeError):
            self.call('EL:SplitAudit', self.key, self.entry())

    def test_deleted_object_still_invalidates_existing_context(self):
        self.f.entities.pop(self.entity)
        self.assertFalse(truth(self.call('EL:SplitChunkValid', self.context)))
        with self.assertRaises(RuntimeError):
            self.call('EL:SplitAudit', self.key, self.entry())


if __name__ == '__main__':
    unittest.main()
