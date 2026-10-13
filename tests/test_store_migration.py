"""V2 migration and current-record legacy downgrade; Date: 2026-10-11."""
import copy
import unittest

import test_diagram_store as store_fixture
from autolisp_host import Pair, Symbol, equal, truth


class StoreMigrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = store_fixture.StoreTests()
        self.fixture.setUp()
        self.h = self.fixture.h
        self.entities = self.fixture.entities
        self.dictionary = self.fixture.dictionary
        self.undo = []
        self.undo_state = 1
        self.messages = []

        def start(_):
            self.undo.append(copy.deepcopy((self.entities, self.dictionary)))
            self.undo_state = 9

        def end(_):
            self.undo_state = 1

        def rollback(*args):
            self.assertEqual(args, ('_.UNDO', '1'))
            entities, dictionary = self.undo.pop()
            self.entities.clear()
            self.entities.update(entities)
            self.dictionary.clear()
            self.dictionary.update(dictionary)
            self.undo_state = 1

        self.h.builtins.update({
            'GETVAR': lambda key: self.undo_state if key == 'UNDOCTL' else
                'drawing-guid' if key == 'FINGERPRINTGUID' else None,
            'VLAX-GET-ACAD-OBJECT': lambda: 'acad',
            'VLA-GET-ACTIVEDOCUMENT': lambda _: 'doc',
            'VLA-STARTUNDOMARK': start, 'VLA-ENDUNDOMARK': end,
            'COMMAND-S': rollback, 'REDRAW': lambda: None,
            'DICTREMOVE': lambda _, key: self.dictionary.pop(key, None),
            'ENTDEL': lambda entity: self.entities.pop(entity, None) and entity,
            'PRINC': lambda *args: self.messages.extend(args),
            'EXIT': lambda: (_ for _ in ()).throw(RuntimeError('LISP exit')),
        })

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, value):
        return self.call('EL:Get', Symbol(key.upper()), value)

    def make_store(self, note='original'):
        store = self.h.run('(EL:StoreInitial)')
        return self.call('EL:Put', Symbol('NOTES'), note, store)

    def seed(self, store, key='EL_FIXED_V1', legacy_text=False):
        if legacy_text:
            text = store_fixture.dump(store)
            payload = [Pair(1, text[index:index + 100]) for index in range(0, len(text), 100)]
        else:
            payload = self.call('EL:StoreEncodeNative', store, 'EL_TYPED_V1')
        entity = self.h.builtins['ENTMAKEX']([
            Pair(0, 'XRECORD'), Pair(100, 'AcDbXrecord'), Pair(280, 1),
            Pair(330, 'NOD')] + payload)
        self.dictionary[key] = entity
        return entity, payload

    def payload(self, key='EL_FIXED_V1'):
        return self.call('EL:StorePayload', self.entities[self.dictionary[key]])

    def marker(self):
        return next(row.cdr for row in self.payload() if row.car == 300)

    def transaction_write(self, store):
        return self.call('EL:Transaction', Symbol('EL:STOREWRITE'), [store])

    def test_ordinary_legacy_read_has_no_migration_or_backup(self):
        for text in (False, True):
            with self.subTest(text=text):
                self.setUp()
                store = self.make_store()
                self.seed(store, legacy_text=text)
                before = copy.deepcopy((self.entities, self.dictionary))
                self.assertTrue(equal(self.call('EL:StoreRead'), store))
                self.assertEqual((self.entities, self.dictionary), before)
                self.assertNotIn('EL_FIXED_V1_LEGACY', self.dictionary)

    def test_v2_updates_to_v3_without_misclassifying_it_as_a_legacy_backup(self):
        store = self.make_store()
        payload = self.call('EL:StoreEncodeNative', self.call('EL:StoreCompact', store), 'EL_COMPACT_TYPED_V2')
        entity = self.h.builtins['ENTMAKEX']([Pair(0, 'XRECORD'), Pair(100, 'AcDbXrecord'), Pair(280, 1)] + payload)
        self.dictionary['EL_FIXED_V1'] = entity
        self.assertTrue(equal(self.call('EL:StoreRead'), store))
        changed = self.make_store('updated')
        self.assertTrue(truth(self.transaction_write(changed)))
        self.assertEqual(self.marker(), 'EL_COMPACT_TYPED_V3')
        self.assertTrue(equal(self.call('EL:StoreRead'), changed))
        self.assertNotIn('EL_FIXED_V1_LEGACY', self.dictionary)

    def test_old_native_and_text_migrate_with_exact_complete_backup(self):
        for text in (False, True):
            with self.subTest(text=text):
                self.setUp()
                store = self.make_store('中文历史草稿')
                entity, original = self.seed(store, legacy_text=text)
                updated = self.call('EL:Put', Symbol('NEW-FIELD'), 1.203456789012345e-98, store)
                self.assertTrue(truth(self.transaction_write(updated)))
                self.assertEqual(self.dictionary['EL_FIXED_V1'], entity)
                self.assertEqual(self.marker(), 'EL_COMPACT_TYPED_V3')
                self.assertEqual(self.payload('EL_FIXED_V1_LEGACY'), original)
                self.assertTrue(equal(self.call('EL:StoreRead'), updated))
                self.assertNotIn('EL_FIXED_TX', self.dictionary)

    def test_backup_persists_once_through_downgrade_and_later_migration(self):
        store = self.make_store()
        self.seed(store)
        self.assertTrue(truth(self.transaction_write(store)))
        backup_before = copy.deepcopy(self.entities[self.dictionary['EL_FIXED_V1_LEGACY']])
        latest = self.call('EL:Put', Symbol('NOTES'), 'latest\n中文', store)
        self.assertTrue(truth(self.transaction_write(latest)))
        self.call('c:ELSTORELEGACY')
        self.assertEqual(self.marker(), 'EL_TYPED_V1')
        self.assertTrue(equal(self.call('EL:StoreRead'), latest))
        self.assertTrue(truth(self.transaction_write(latest)))
        self.assertEqual(self.marker(), 'EL_COMPACT_TYPED_V3')
        self.assertEqual(self.entities[self.dictionary['EL_FIXED_V1_LEGACY']], backup_before)
        self.assertTrue(equal(self.call('EL:StoreRead'), latest))

    def test_conflicting_or_damaged_existing_backup_refuses_and_rolls_back(self):
        for reason in ('future', 'foreign', 'native-difference', 'copy-conflict'):
            with self.subTest(reason=reason):
                self.setUp()
                store = self.make_store()
                self.seed(store)
                backup = self.make_store('different historical data is allowed')
                if reason == 'foreign':
                    backup = self.call('EL:Put', Symbol('DRAWING-UUID'), 'foreign-guid', backup)
                if reason == 'copy-conflict':
                    backup = self.call('EL:Put', Symbol('DIAGRAMS'), self.h.run('''
                      '(((diagram-id . "historical/box/1")
                        (template (version . 1)) (config (template (version . 2)))))'''), backup)
                backup_entity, _ = self.seed(backup, key='EL_FIXED_V1_LEGACY')
                if reason == 'future':
                    self.entities[backup_entity] = [Pair(300, 'EL_FUTURE_V9'), Pair(2, 'N')]
                if reason == 'native-difference':
                    search = self.h.builtins['DICTSEARCH']
                    self.h.builtins['DICTSEARCH'] = lambda owner, key: (
                        search(owner, key) + [Pair(1, 'tampered')]
                        if key == 'EL_FIXED_V1_LEGACY' else search(owner, key))
                before = copy.deepcopy((self.entities, self.dictionary))
                self.assertIsNone(self.transaction_write(store))
                self.assertEqual((self.entities, self.dictionary), before)

    def test_failed_migration_rolls_back_new_backup_and_current_record(self):
        store = self.make_store()
        self.seed(store)
        before = copy.deepcopy((self.entities, self.dictionary))
        replace = self.h.builtins['VLA-SETXRECORDDATA']

        def fail_after_replace(*args):
            replace(*args)
            raise RuntimeError('native replacement failed after changing data')

        self.h.builtins['VLA-SETXRECORDDATA'] = fail_after_replace
        self.assertIsNone(self.transaction_write(self.make_store('new')))
        self.assertEqual((self.entities, self.dictionary), before)
        self.assertNotIn('EL_FIXED_V1_LEGACY', self.dictionary)
        self.assertFalse(truth(self.h.lookup('*EL:TRANSACTIONOPEN*')))

    def test_backup_association_failure_rolls_back_orphan_and_original(self):
        store = self.make_store()
        self.seed(store)
        before = copy.deepcopy((self.entities, self.dictionary))
        add = self.h.builtins['DICTADD']
        self.h.builtins['DICTADD'] = lambda owner, key, entity: (
            None if key == 'EL_FIXED_V1_LEGACY' else add(owner, key, entity))
        self.assertIsNone(self.transaction_write(store))
        self.assertEqual((self.entities, self.dictionary), before)

    def test_failed_legacy_downgrade_rolls_back_current_logical_data(self):
        latest = self.make_store('最新完整数据')
        self.assertTrue(truth(self.transaction_write(latest)))
        before = copy.deepcopy((self.entities, self.dictionary))
        self.h.builtins['VLA-SETXRECORDDATA'] = lambda *args: (_ for _ in ()).throw(RuntimeError('fail'))
        self.call('c:ELSTORELEGACY')
        self.assertEqual((self.entities, self.dictionary), before)
        self.assertTrue(equal(self.call('EL:StoreRead'), latest))

    def test_downgrade_no_record_and_undo_disabled_do_not_write(self):
        before = copy.deepcopy((self.entities, self.dictionary))
        self.call('c:ELSTORELEGACY')
        self.assertEqual((self.entities, self.dictionary), before)
        self.assertTrue(truth(self.transaction_write(self.make_store())))
        before = copy.deepcopy((self.entities, self.dictionary))
        self.undo_state = 0
        self.call('c:ELSTORELEGACY')
        self.assertEqual((self.entities, self.dictionary), before)

    def test_future_and_damaged_v2_reads_refuse_without_rewriting_dwg(self):
        store = self.make_store()
        packed = self.call('EL:StoreCompact', store)
        future = self.call('EL:Put', Symbol('FORMAT-VERSION'), 3, packed)
        damaged = self.call('EL:Put', Symbol('BODY'), [-999999], packed)
        cases = [self.call('EL:StoreEncodeNative', future, 'EL_COMPACT_TYPED_V2'),
                 self.call('EL:StoreEncodeNative', damaged, 'EL_COMPACT_TYPED_V2'),
                 self.call('EL:StoreEncodeNative', packed, 'EL_COMPACT_TYPED_V3')]
        for payload in cases:
            with self.subTest(marker=payload[0].cdr):
                self.setUp()
                entity = self.h.builtins['ENTMAKEX']([Pair(0, 'XRECORD')] + payload)
                self.dictionary['EL_FIXED_V1'] = entity
                before = copy.deepcopy((self.entities, self.dictionary))
                with self.assertRaises(RuntimeError):
                    self.call('EL:StoreRead')
                self.assertEqual((self.entities, self.dictionary), before)

    def test_legacy_writer_requires_its_transaction(self):
        before = copy.deepcopy((self.entities, self.dictionary))
        with self.assertRaises(RuntimeError):
            self.call('EL:StoreWriteLegacy', self.make_store())
        self.assertEqual((self.entities, self.dictionary), before)

    def test_direct_old_migration_refuses_without_creating_backup(self):
        store = self.make_store()
        self.seed(store)
        before = copy.deepcopy((self.entities, self.dictionary))
        with self.assertRaises(RuntimeError):
            self.call('EL:StoreWrite', store)
        self.assertEqual((self.entities, self.dictionary), before)
        self.assertNotIn('EL_FIXED_V1_LEGACY', self.dictionary)

    def test_direct_write_refuses_invalid_existing_v2_or_uuid_without_changes(self):
        store = self.make_store()
        packed = self.call('EL:StoreCompact', store)
        foreign = self.call('EL:Put', Symbol('DRAWING-UUID'), 'foreign-guid', store)
        cases = [self.call('EL:StoreEncodeNative',
                          self.call('EL:Put', Symbol('FORMAT-VERSION'), 3, packed), 'EL_COMPACT_TYPED_V2'),
                 self.call('EL:StoreEncodeNative',
                           self.call('EL:Put', Symbol('BODY'), [-999999], packed), 'EL_COMPACT_TYPED_V2'),
                 self.call('EL:StoreEncode', foreign)]
        for payload in cases:
            with self.subTest(marker=payload[0].cdr):
                self.setUp()
                entity = self.h.builtins['ENTMAKEX']([Pair(0, 'XRECORD')] + payload)
                self.dictionary['EL_FIXED_V1'] = entity
                before = copy.deepcopy((self.entities, self.dictionary))
                with self.assertRaises(RuntimeError):
                    self.call('EL:StoreWrite', store)
                self.assertEqual((self.entities, self.dictionary), before)
                self.assertIsNone(self.transaction_write(store))
                self.assertEqual((self.entities, self.dictionary), before)

    def test_direct_write_refuses_two_native_route_difference(self):
        store = self.make_store()
        self.call('EL:StoreWrite', store)
        entry = self.entities[self.dictionary['EL_FIXED_V1']]
        get = self.h.builtins['ENTGET']
        entity = self.dictionary['EL_FIXED_V1']
        self.h.builtins['ENTGET'] = lambda handle, *args: (
            get(handle, *args) + [Pair(90, 999)] if handle == entity else get(handle, *args))
        before = copy.deepcopy((self.entities, self.dictionary))
        with self.assertRaises(RuntimeError):
            self.call('EL:StoreWrite', self.make_store('new'))
        self.assertEqual((self.entities, self.dictionary), before)

    def test_future_proposed_schema_never_writes(self):
        before = copy.deepcopy((self.entities, self.dictionary))
        future = self.call('EL:Put', Symbol('SCHEMA-VERSION'), 9, self.make_store())
        with self.assertRaises(RuntimeError):
            self.call('EL:StoreWrite', future)
        self.assertEqual((self.entities, self.dictionary), before)

    def test_downgrade_reads_current_after_start_native_callback(self):
        self.assertTrue(truth(self.transaction_write(self.make_store('before callback'))))
        latest = self.make_store('latest from native callback')
        payload = self.call('EL:StoreEncode', latest)
        entity = self.dictionary['EL_FIXED_V1']
        start = self.h.builtins['VLA-STARTUNDOMARK']

        def native_callback(doc):
            start(doc)
            self.entities[entity] = [row for row in self.entities[entity]
                                    if row.car not in (1, 2, 3, 40, 90, 300)] + payload

        self.h.builtins['VLA-STARTUNDOMARK'] = native_callback
        self.call('c:ELSTORELEGACY')
        self.assertEqual(self.marker(), 'EL_TYPED_V1')
        self.assertTrue(equal(self.call('EL:StoreRead'), latest))
        self.assertTrue(any('当前完整草稿已转换' in str(msg) for msg in self.messages))

    def test_post_commit_change_cannot_claim_legacy_success(self):
        for change in ('same-logical-v2', 'other-logical'):
            with self.subTest(change=change):
                self.setUp()
                expected = self.make_store('current')
                self.assertTrue(truth(self.transaction_write(expected)))
                changed = expected if change == 'same-logical-v2' else self.make_store('changed after commit')
                payload = self.call('EL:StoreEncode', changed)
                entity = self.dictionary['EL_FIXED_V1']
                end = self.h.builtins['VLA-ENDUNDOMARK']

                def post_commit(doc):
                    end(doc)
                    self.entities[entity] = [row for row in self.entities[entity]
                                            if row.car not in (1, 2, 3, 40, 90, 300)] + payload

                self.h.builtins['VLA-ENDUNDOMARK'] = post_commit
                self.messages.clear()
                self.call('c:ELSTORELEGACY')
                self.assertFalse(any('当前完整草稿已转换' in str(msg) for msg in self.messages))
                self.assertTrue(any('未确认旧版兼容' in str(msg) for msg in self.messages))
                self.assertTrue(equal(self.call('EL:StoreRead'), changed))

    def test_old_copy_conflict_cannot_be_silently_repaired_and_overwritten(self):
        old = self.h.run('''(EL:Put 'diagrams
            '(((diagram-id . "old/box/1")
              (template (version . 1) (name . "记录模板"))
              (config (template (version . 2) (name . "另一个模板")))))
            (EL:StoreInitial))''')
        proposed = self.h.run('''(EL:Put 'diagrams
            '(((diagram-id . "old/box/1")
              (template (version . 1) (name . "记录模板"))
              (config (template (version . 1) (name . "记录模板")))))
            (EL:StoreInitial))''')
        self.seed(old)
        before = copy.deepcopy((self.entities, self.dictionary))
        with self.assertRaises(RuntimeError):
            self.call('EL:StoreWrite', proposed)
        self.assertEqual((self.entities, self.dictionary), before)
        self.assertIsNone(self.transaction_write(proposed))
        self.assertEqual((self.entities, self.dictionary), before)

    def test_public_native_codec_keeps_non_store_value_roundtrips(self):
        values = [None, True, 2147483647, -2147483648, 1.203456789012345e-98,
                  '中文原样', Symbol('ORIGINAL'), [1, None, 'nested', [2.0]]]
        for value in values:
            with self.subTest(kind=type(value).__name__):
                self.assertTrue(equal(self.call('EL:StoreDecode', self.call('EL:StoreEncode', value)), value))


if __name__ == '__main__':
    unittest.main()
