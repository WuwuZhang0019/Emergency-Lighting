"""Split-store migration, partial IO and rollback; Date: 2026-10-14."""
import copy
import unittest
from pathlib import Path
from autolisp_host import Symbol, Pair, truth
import test_diagram_store as store_fixture
from test_diagram_store import dump
ROOT = Path(__file__).resolve().parents[1]

class SplitStoreTests(unittest.TestCase):
    def setUp(self):
        store_fixture.StoreTests.setUp(self)
        self.h.load_definitions(ROOT / 'src/geometry.lsp')
        self.h.load_definitions(ROOT / 'src/store-split.lsp')
        store_fixture.StoreTests.install_transaction(self)
        self.h.run('(setq *EL:SplitStorageLoaded* T)')
        self.h.frames[0]['SIG'] = [Symbol('EL_FIXED_SOURCE_V1'), ['中文快照'*60, 1.0000000000000002, Symbol('EXTRA')]]
        self.h.run("""(setq record1 (list '(diagram-id . "one") '(source-panel-handle . "P1")
          '(panel-number . "箱1") '(engine . fixed) '(status . draft)
          '(draft-circuits ((circuit-uid . "UID1") (devices "D1")))
          (cons 'source-signature sig) '(draft-source-signature . formal-source)
          '(custom-extension (precise . 0.12345678901234567))))
        (setq record2 (EL:Put 'diagram-id "two" (EL:Put 'source-panel-handle "P2" record1)))
        (setq store (EL:Put 'diagrams (list record1 record2) (EL:Put 'extra "保留" (EL:StoreInitial))))""")

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def save(self, value=None):
        value = value or self.h.lookup('STORE')
        return self.call('EL:TransactionVerifiedStore', Symbol('EL:STOREWRITE'), [value])

    def get(self, key, value):
        return self.call('EL:Get', Symbol(key.upper()), value)

    def test_legacy_formats_read_without_writes_then_migrate_all_boxes_exactly(self):
        expected = copy.deepcopy(self.h.lookup('STORE'))
        for wire in ('text', 'typed', 'v2', 'v3'):
            with self.subTest(wire=wire):
                self.entities.clear(); self.dictionary.clear()
                self.h.frames[0]['*EL:SPLITCACHE*'] = None
                if wire == 'text': payload = [Pair(1, dump(expected))]
                elif wire == 'typed': payload = self.call('EL:StoreEncodeLegacy', expected)
                elif wire == 'v2': payload = self.call('EL:StoreEncodeNative', self.call('EL:StoreCompact', expected), 'EL_COMPACT_TYPED_V2')
                else: payload = self.call('EL:StoreEncode', expected)
                entity = self.h.builtins['ENTMAKEX']([Pair(0, 'XRECORD'), Pair(100, 'AcDbXrecord'), Pair(280, 1)] + payload)
                self.dictionary['EL_FIXED_V1'] = entity
                before = copy.deepcopy((self.entities, self.dictionary))
                self.assertEqual(self.call('EL:StoreRead'), expected)
                self.assertEqual(self.call('EL:StoreIndex'), expected)
                self.assertEqual((self.entities, self.dictionary), before)
                context = self.save(expected)
                self.assertTrue(truth(self.get('committed', context)))
                self.assertEqual(self.call('EL:StoreRead'), expected)
                backup = self.entities[self.dictionary['EL_FIXED_MONOLITH_BACKUP']]
                self.assertEqual(self.call('EL:StorePayload', backup), payload)
                self.assertEqual(self.get('draft-source-signature', self.call('EL:StoreRecord', 'one')), Symbol('FORMAL-SOURCE'))

    def test_index_and_one_record_do_not_read_other_details(self):
        self.assertTrue(truth(self.get('outcome', self.save())))
        self.h.frames[0]['*EL:SPLITCACHE*'] = None
        reads = []
        search = self.h.builtins['DICTSEARCH']
        self.h.builtins['DICTSEARCH'] = lambda owner, key: reads.append(key) or search(owner, key)
        index = self.call('EL:StoreIndex')
        self.assertEqual(len(self.get('diagrams', index)), 2)
        self.assertEqual(set(reads), {'EL_FIXED_SPLIT_V1'})
        root = self.call('EL:SplitRoot')
        item2 = self.get('items', root)[1]
        reads.clear()
        self.assertEqual(self.call('EL:StoreRecord', 'one'), self.h.lookup('RECORD1'))
        self.assertNotIn(self.get('detail', item2), reads)

    def test_first_save_stages_only_final_records_and_keeps_exact_history_backup(self):
        put = lambda key, value, row: self.call('EL:Put', Symbol(key.upper()), value, row)
        old1 = put('source-signature', ['old snapshot 1', 1.e-98], self.h.lookup('RECORD1'))
        old2 = put('diagram-id', 'older-two', put('source-signature',
                   ['old snapshot 2', 1.0000000000000002], old1))
        other = self.h.lookup('RECORD2')
        old = put('diagrams', [old1, old2, other], self.h.lookup('STORE'))
        self.assertTrue(truth(self.call('EL:StoreWriteMonolithic', old)))
        raw = copy.deepcopy(self.call('EL:StorePayload', self.entities[self.dictionary['EL_FIXED_V1']]))
        current = put('diagram-id', 'new', put('source-signature', ['current', 3.e-97], old1))
        proposed = self.call('EL:StorePutDiagram', current, old)
        builds, blobs = [], []
        original = self.h.call
        def observe(name, args):
            if name == 'EL:SPLITBUILD': builds.append(copy.deepcopy(args[0]))
            if name == 'EL:STOREENCODE' and self.get('chunk-kind', args[0]) == Symbol('BLOB'):
                blobs.append(copy.deepcopy(self.get('chunk-value', args[0])))
            return original(name, args)
        self.h.call = observe
        context = self.save(proposed)
        self.assertTrue(truth(self.get('committed', context)))
        self.assertEqual(builds, [proposed])
        self.assertNotIn(self.get('source-signature', old1), blobs)
        self.assertNotIn(self.get('source-signature', old2), blobs)
        self.assertEqual(blobs.count(self.get('source-signature', current)), 1)
        self.assertEqual(blobs.count(self.get('source-signature', other)), 1)
        self.assertEqual(self.call('EL:StoreRead'), proposed)
        self.assertEqual(self.call('EL:StoreRecord', 'two'), other)
        backup = self.entities[self.dictionary['EL_FIXED_MONOLITH_BACKUP']]
        self.assertEqual(self.call('EL:StorePayload', backup), raw)

    def test_legacy_payload_change_during_final_staging_rejects_publication(self):
        self.assertTrue(truth(self.call('EL:StoreWriteMonolithic', self.h.lookup('STORE'))))
        before = copy.deepcopy((self.entities, self.dictionary))
        original = self.h.call
        def change_before_build(name, args):
            if name == 'EL:SPLITBUILD':
                entity = self.dictionary['EL_FIXED_V1']
                self.entities[entity] = self.entities[entity] + [Pair(1, 'changed while staging')]
            return original(name, args)
        self.h.call = change_before_build
        self.assertFalse(truth(self.get('committed', self.save())))
        self.assertNotIn('EL_FIXED_SPLIT_V1', self.dictionary)
        self.assertEqual((self.entities, self.dictionary), before)

    def test_power_edit_reuses_large_blobs_and_other_box_and_noop_writes_nothing(self):
        self.save()
        root = self.call('EL:SplitRoot')
        old_items = self.get('items', root)
        old_keys = set(self.dictionary)
        changed = self.call('EL:Put', Symbol('POWERS'), [Pair('LIGHT', 5)], self.h.lookup('RECORD1'))
        proposed = self.call('EL:StorePutDiagram', changed, self.call('EL:StoreRead'))
        context = self.save(proposed)
        self.assertTrue(truth(self.get('committed', context)))
        new_items = self.get('items', self.call('EL:SplitRoot'))
        self.assertEqual(old_items[1], new_items[1])
        self.assertEqual(len(set(self.dictionary) - old_keys), 1) # new detail, root replaced
        self.assertEqual(self.call('EL:TransactionVerifiedRead', context), proposed)
        before = copy.deepcopy((self.entities, self.dictionary))
        self.save(proposed)
        self.assertEqual((self.entities, self.dictionary), before)

    def test_failure_before_root_publish_rolls_back_every_chunk(self):
        self.save()
        before = copy.deepcopy((self.entities, self.dictionary))
        replace = self.h.builtins['VLA-SETXRECORDDATA']
        def fail(entity, codes, values):
            if entity == self.dictionary['EL_FIXED_SPLIT_V1']:
                raise RuntimeError('disk-like root failure')
            return replace(entity, codes, values)
        self.h.builtins['VLA-SETXRECORDDATA'] = fail
        proposed = self.call('EL:Put', Symbol('EXTRA'), 'changed', self.h.lookup('STORE'))
        context = self.save(proposed)
        self.assertFalse(truth(self.get('outcome', context)))
        self.assertEqual((self.entities, self.dictionary), before)
        self.assertEqual(self.call('EL:StoreRead'), self.h.lookup('STORE'))

    def test_changed_native_reference_invalidates_context(self):
        context = self.save()
        root = self.call('EL:SplitRoot')
        entity = self.dictionary[self.get('metadata', root)]
        self.entities[entity] = self.entities[entity] + [Pair(1, 'injected')]
        self.assertFalse(truth(self.call('EL:StoreContextValid', context)))
        with self.assertRaises(RuntimeError): self.call('EL:StoreRead')


    def test_legacy_export_uses_latest_view_and_disables_split_authority(self):
        self.save()
        proposed = self.call('EL:Put', Symbol('EXTRA'), 'latest', self.h.lookup('STORE'))
        self.save(proposed)
        self.assertTrue(truth(self.call('EL:StoreDowngrade')))
        self.assertNotIn('EL_FIXED_SPLIT_V1', self.dictionary)
        legacy = self.entities[self.dictionary['EL_FIXED_V1']]
        self.assertEqual(self.call('EL:StorePayload', legacy)[0], Pair(300, 'EL_TYPED_V1'))
        self.assertEqual(self.call('EL:StoreRead'), proposed)
        self.assertTrue(truth(self.get('committed', self.save(proposed))))
        self.assertEqual(self.call('EL:StoreRead'), proposed)

    def test_large_legacy_migration_uses_bounded_creation_and_rolls_back_failure(self):
        create = self.h.builtins['ENTMAKEX']
        sizes = []
        def bounded(data):
            sizes.append(len(data))
            if len(data) > 1024:
                raise RuntimeError('oversized native creation')
            return create(data)
        self.h.builtins['ENTMAKEX'] = bounded
        large = self.call('EL:Put', Symbol('MEASUREMENTS'),
                          [float(i) + 1.e-10 for i in range(1800)], self.h.lookup('RECORD1'))
        expected = self.call('EL:Put', Symbol('DIAGRAMS'), [large, self.h.lookup('RECORD2')],
                             self.h.lookup('STORE'))
        self.assertTrue(truth(self.call('EL:StoreWriteMonolithic', expected)))
        before = copy.deepcopy((self.entities, self.dictionary))
        replace = self.h.builtins['VLA-SETXRECORDDATA']
        def fail(*args):
            raise RuntimeError('interrupted migration payload')
        self.h.builtins['VLA-SETXRECORDDATA'] = fail
        self.assertFalse(truth(self.get('outcome', self.save(expected))))
        self.assertEqual((self.entities, self.dictionary), before)
        self.h.builtins['VLA-SETXRECORDDATA'] = replace
        self.assertTrue(truth(self.get('committed', self.save(expected))))
        self.assertEqual(self.call('EL:StoreRead'), expected)
        self.assertEqual(self.call('EL:StoreRecord', 'one'), large)
        backup = self.entities[self.dictionary['EL_FIXED_MONOLITH_BACKUP']]
        original = before[0][before[1]['EL_FIXED_V1']]
        self.assertEqual(self.call('EL:StorePayload', backup), self.call('EL:StorePayload', original))
        self.assertLessEqual(max(sizes), 1024)

if __name__ == '__main__': unittest.main()
