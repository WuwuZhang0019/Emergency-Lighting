"""Exact command-scoped DWG decode reuse. Date: 2026-10-13.

Finite native adapters measure work counts, not real AutoCAD timing.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, equal, truth
import test_diagram_store as db


class StoreDecodeCacheTests(unittest.TestCase):
    def setUp(self):
        self.fixture = db.StoreTests()
        self.fixture.setUp()
        self.fixture.install_transaction()
        self.h = self.fixture.h
        self.owner = 'NOD'
        self.h.builtins.update({
            'NAMEDOBJDICT': lambda: self.owner,
            'EL:PERFREPORT': lambda _: None,
        })
        self.store = self.h.run('(EL:StoreInitial)')
        self.call('EL:StoreWrite', self.store)
        self.decodes = []
        self.h.functions['TEST:DECODE'] = self.h.functions['EL:STOREDECODE']

        def decode(payload):
            self.decodes.append(copy.deepcopy(payload))
            return self.call('TEST:Decode', payload)

        self.h.builtins['EL:STOREDECODE'] = decode
        self.start()

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def start(self):
        self.call('EL:PerfStart', 'ELSTAT')

    def metric(self, key):
        return self.call('EL:Get', key, self.h.lookup('*EL:PERFMETRICS*'))

    def replace(self, store, marker='EL_COMPACT_TYPED_V2'):
        entity = self.fixture.dictionary['EL_FIXED_V1']
        payload = (self.call('EL:StoreEncode', store) if marker == 'EL_COMPACT_TYPED_V2'
                   else self.call('EL:StoreEncodeNative', store, marker))
        self.fixture.entities[entity] = [p for p in self.fixture.entities[entity]
            if p.car not in (1, 2, 3, 40, 90, 300)] + payload

    def changed(self, note='current native data'):
        return self.call('EL:Put', Symbol('NOTES'), note, self.store)

    def test_six_reads_decode_once_without_business_writes(self):
        before = copy.deepcopy((self.fixture.entities, self.fixture.dictionary))
        for _ in range(6):
            self.assertTrue(equal(self.call('EL:StoreRead'), self.store))
        self.assertEqual(len(self.decodes), 1)
        self.assertEqual(self.metric('store-read-calls'), 6)
        self.assertEqual(self.metric('store-read-cache-hits'), 5)
        self.assertEqual(self.metric('master-write-attempts'), 0)
        self.assertEqual((self.fixture.entities, self.fixture.dictionary), before)
        self.__class__.read_work_evidence = {
            'business_reads': 6, 'store_decode_calls': len(self.decodes),
            'cache_hits': self.metric('store-read-cache-hits'), 'master_writes': 0,
        }

    def test_changed_payload_decodes_current_data_and_never_old_value(self):
        self.call('EL:StoreRead')
        latest = self.changed()
        self.replace(latest)
        self.assertTrue(equal(self.call('EL:StoreRead'), latest))
        self.assertEqual(len(self.decodes), 2)
        self.assertTrue(equal(self.call('EL:StoreRead'), latest))
        self.assertEqual(len(self.decodes), 2)

    def test_entget_only_difference_disables_reuse_and_write_still_refuses(self):
        self.call('EL:StoreRead')
        native = self.h.builtins['ENTGET']
        entity = self.fixture.dictionary['EL_FIXED_V1']
        self.h.builtins['ENTGET'] = lambda e, *args: (
            native(e, *args) + [Pair(1, 'native-only change')]
            if e == entity else native(e, *args))
        self.call('EL:StoreRead')
        self.assertEqual(len(self.decodes), 2)
        self.assertFalse(truth(self.h.lookup('*EL:STOREREADCACHE*')))
        before = copy.deepcopy((self.fixture.entities, self.fixture.dictionary))
        with self.assertRaises(RuntimeError):
            self.call('EL:StoreWrite', self.changed())
        self.assertEqual((self.fixture.entities, self.fixture.dictionary), before)

    def test_dictsearch_only_difference_cannot_hit(self):
        self.call('EL:StoreRead')
        lookup = self.h.builtins['DICTSEARCH']
        latest = self.changed('dictionary differs from entget')
        payload = self.call('EL:StoreEncode', latest)
        self.h.builtins['DICTSEARCH'] = lambda owner, key: (
            [p for p in lookup(owner, key) if p.car not in (1, 2, 3, 40, 90, 300)] + payload
            if key == 'EL_FIXED_V1' else lookup(owner, key))
        self.assertTrue(equal(self.call('EL:StoreRead'), latest))
        self.assertEqual(len(self.decodes), 2)
        self.assertFalse(truth(self.h.lookup('*EL:STOREREADCACHE*')))

    def test_owner_replacement_deletion_and_undo_redo_invalidate(self):
        self.call('EL:StoreRead')
        self.owner = 'different NOD'
        self.call('EL:StoreRead')
        self.assertEqual(len(self.decodes), 2)
        old_entity = self.fixture.dictionary['EL_FIXED_V1']
        clone = self.h.builtins['ENTMAKEX']([p for p in self.fixture.entities[old_entity]
                                          if p.car not in (-1, 5)])
        self.fixture.dictionary['EL_FIXED_V1'] = clone
        self.call('EL:StoreRead')
        self.assertEqual(len(self.decodes), 3)
        self.fixture.dictionary.pop('EL_FIXED_V1')
        self.assertIsNone(self.call('EL:StoreRead'))
        self.assertFalse(truth(self.h.lookup('*EL:STOREREADCACHE*')))
        self.fixture.dictionary['EL_FIXED_V1'] = old_entity
        self.call('EL:StoreRead')
        self.assertEqual(len(self.decodes), 4)
        self.replace(self.changed('redo'))
        self.call('EL:StoreRead')
        self.replace(self.store)
        self.assertTrue(equal(self.call('EL:StoreRead'), self.store))
        self.assertEqual(len(self.decodes), 6)

    def test_finish_cancel_error_and_new_command_have_no_shared_cache(self):
        for outcome in ('COMMAND-FINISHED', 'CANCELLED', 'FAILED'):
            with self.subTest(outcome=outcome):
                self.call('EL:StoreRead')
                previous = self.h.lookup('*EL:STOREREADCACHE*')
                self.call('EL:PerfFinish', Symbol(outcome))
                self.assertFalse(truth(self.h.lookup('*EL:STOREREADCACHE*')))
                count = len(self.decodes)
                self.call('EL:StoreRead')
                self.assertEqual(len(self.decodes), count + 1)
                self.start()
                entry = self.h.builtins['DICTSEARCH'](self.owner, 'EL_FIXED_V1')
                self.assertFalse(truth(self.call('EL:StoreReadCacheValid', entry, previous)))
                self.call('EL:StoreRead')
                self.assertEqual(len(self.decodes), count + 2)

    def test_input_callback_can_reuse_only_when_full_stored_data_matches(self):
        self.call('EL:StoreRead')
        self.h.builtins['TEST:INPUT'] = lambda: self.replace(self.changed('input callback'))
        self.call('EL:PerfInput', Symbol('TEST:INPUT'), None)
        self.assertTrue(equal(self.call('EL:StoreRead'), self.changed('input callback')))
        self.assertEqual(len(self.decodes), 2)

    def test_exact_native_readback_reuses_prewrite_decode_then_followup_reuses_it(self):
        self.call('EL:StoreRead')
        latest = self.changed()
        result = self.call('EL:TransactionVerifiedStore', Symbol('EL:STOREWRITE'), [latest])
        self.assertTrue(truth(self.call('EL:Get', Symbol('COMMITTED'), result)))
        # Initial read and prewrite roundtrip; both native readbacks still compare every field.
        self.assertEqual(len(self.decodes), 2)
        self.assertEqual(self.metric('store-readback-decode-reuses'), 1)
        self.assertTrue(equal(self.call('EL:StoreRead'), latest))
        self.assertEqual(len(self.decodes), 2)
        stages = self.h.lookup('*EL:PERFSTAGES*')
        decode_stage = self.call('EL:Get', 'STORE_DECODE', stages)
        self.assertEqual(self.call('EL:Get', Symbol('CALLS'), decode_stage), 1)
        self.__class__.update_work_evidence = {
            'store_decode_calls': self.call('EL:Get', Symbol('CALLS'), decode_stage),
            'prewrite_roundtrip_calls': 1, 'fresh_postwrite_readbacks': 1,
            'cache_hits': self.metric('store-read-cache-hits'),
        }

    def test_corrupt_future_or_changed_schema_cannot_hide_in_cache(self):
        for payload in ([Pair(300, 'EL_FUTURE_V9'), Pair(2, 'N')],
                        [Pair(300, 'EL_COMPACT_TYPED_V2'), Pair(2, 'L')],
                        self.call('EL:StoreEncodeNative',
                            self.call('EL:Put', Symbol('SCHEMA-VERSION'), 9, self.store), 'EL_TYPED_V1')):
            with self.subTest(payload=payload[:2]):
                self.replace(self.store)
                self.call('EL:StoreRead')
                entity = self.fixture.dictionary['EL_FIXED_V1']
                self.fixture.entities[entity] = [p for p in self.fixture.entities[entity]
                    if p.car not in (1, 2, 3, 40, 90, 300)] + payload
                with self.assertRaises(RuntimeError):
                    self.call('EL:StoreRead')
                self.assertFalse(truth(self.h.lookup('*EL:STOREREADCACHE*')))

    def test_reentry_uses_fresh_decoder_without_publishing_inner_value(self):
        self.call('EL:StoreRead')
        native = self.h.builtins['ENTGET']
        nested = []

        def callback(entity, *args):
            if not nested:
                nested.append(True)
                self.assertTrue(equal(self.call('EL:StoreRead'), self.store))
            return native(entity, *args)

        self.h.builtins['ENTGET'] = callback
        self.assertTrue(equal(self.call('EL:StoreRead'), self.store))
        self.assertEqual(len(self.decodes), 2)
        self.assertFalse(truth(self.h.lookup('*EL:STOREREADBUSY*')))

    def test_decode_callback_change_cannot_publish_old_data(self):
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.start()
        original = self.h.builtins['EL:STOREDECODE']

        def changed_during_decode(payload):
            value = original(payload)
            self.replace(self.changed('during decode'))
            return value

        self.h.builtins['EL:STOREDECODE'] = changed_during_decode
        self.call('EL:StoreRead')
        self.assertFalse(truth(self.h.lookup('*EL:STOREREADCACHE*')))
        self.h.builtins['EL:STOREDECODE'] = original
        self.assertTrue(equal(self.call('EL:StoreRead'), self.changed('during decode')))

    def test_end_undo_callback_change_is_read_instead_of_reusing_written_value(self):
        self.call('EL:StoreRead')
        proposed = self.changed('proposed')
        actual = self.changed('commit callback')
        self.h.builtins['VLA-ENDUNDOMARK'] = lambda _: self.replace(actual)
        context = self.call('EL:TransactionVerifiedStore', Symbol('EL:STOREWRITE'), [proposed])
        self.assertFalse(truth(self.call('EL:Get', Symbol('COMMITTED'), context)))
        self.assertTrue(equal(self.call('EL:TransactionVerifiedRead', context), actual))
        self.assertTrue(equal(self.call('EL:StoreRead'), actual))

    def test_cache_check_stage_is_reported_without_detail_mode(self):
        self.call('EL:StoreRead')
        self.call('EL:StoreRead')
        stage = self.call('EL:Get', 'STORE_CACHE_CHECK', self.h.lookup('*EL:PERFSTAGES*'))
        self.assertGreater(self.call('EL:Get', Symbol('CALLS'), stage), 0)

    def test_hit_reads_each_native_route_once_without_an_extra_dictionary_lookup(self):
        self.call('EL:StoreRead')
        lookup = self.h.builtins['DICTSEARCH']
        native = self.h.builtins['ENTGET']
        reads = {'dictsearch': 0, 'entget': 0}

        def dictionary(*args):
            reads['dictsearch'] += 1
            return lookup(*args)

        def entity(*args):
            reads['entget'] += 1
            return native(*args)

        self.h.builtins.update({'DICTSEARCH': dictionary, 'ENTGET': entity})
        self.assertTrue(equal(self.call('EL:StoreRead'), self.store))
        self.assertEqual(reads, {'dictsearch': 1, 'entget': 1})
        self.assertEqual(len(self.decodes), 1)
        self.__class__.hit_read_work_evidence = reads

    def test_callback_starting_next_command_cannot_publish_old_scope(self):
        original = self.h.builtins['EL:STOREDECODE']

        def next_command(payload):
            value = original(payload)
            self.call('EL:PerfFinish', Symbol('CANCELLED'))
            self.start()
            return value

        self.h.builtins['EL:STOREDECODE'] = next_command
        self.call('EL:StoreRead')
        self.assertFalse(truth(self.h.lookup('*EL:STOREREADCACHE*')))

    def test_failed_transaction_clears_cache_and_restores_old_store(self):
        self.call('EL:StoreRead')
        latest = self.changed()
        self.h.frames[0]['LATEST'] = latest
        self.h.run('(defun TEST:BadWrite () (EL:StoreWrite latest) nil)')
        self.assertIsNone(self.call('EL:Transaction', Symbol('TEST:BADWRITE'), None))
        self.assertFalse(truth(self.h.lookup('*EL:STOREREADCACHE*')))
        self.assertTrue(equal(self.call('EL:StoreRead'), self.store))

    def test_legacy_read_is_readonly_and_migration_keeps_fresh_backup_checks(self):
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.replace(self.store, marker='EL_TYPED_V1')
        before = copy.deepcopy((self.fixture.entities, self.fixture.dictionary))
        self.start()
        self.call('EL:StoreRead')
        self.call('EL:StoreRead')
        self.assertEqual(len(self.decodes), 1)
        self.assertEqual((self.fixture.entities, self.fixture.dictionary), before)
        latest = self.changed()
        self.assertTrue(truth(self.call('EL:Transaction', Symbol('EL:STOREWRITE'), [latest])))
        self.assertIn('EL_FIXED_V1_LEGACY', self.fixture.dictionary)
        self.assertTrue(equal(self.call('EL:StoreRead'), latest))
        # Initial old read, encode-check and fresh historical backup; exact readback reuses decode.
        self.assertEqual(len(self.decodes), 3)


if __name__ == '__main__':
    unittest.main()
