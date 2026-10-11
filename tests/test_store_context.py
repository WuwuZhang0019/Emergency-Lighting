"""One-operation actual DWG readback reuse. Date: 2026-10-11.

Finite adapter evidence only; native CAD validation remains separate.
"""
import copy
import unittest

import test_diagram_store as db
from autolisp_host import Pair, Symbol, truth


class StoreContextTests(unittest.TestCase):
    def setUp(self):
        db.StoreTests.setUp(self)
        self.h.load_definitions(db.ROOT / 'src' / 'diagram-update.lsp')
        self.undo = []
        self.owner = 'NOD'

        def begin(_):
            self.undo.append(copy.deepcopy((self.entities, self.dictionary)))

        def rollback(*args):
            self.assertEqual(args, ('_.UNDO', '1'))
            self.entities, self.dictionary = copy.deepcopy(self.undo.pop())

        self.h.builtins.update({
            'NAMEDOBJDICT': lambda: self.owner,
            'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda _: 'doc',
            'VLA-STARTUNDOMARK': begin,
            'VLA-ENDUNDOMARK': lambda _: None,
            'DICTREMOVE': lambda _, key: self.dictionary.pop(key, None),
            'ENTDEL': lambda e: self.entities.pop(e, None) and e,
            'COMMAND-S': rollback,
            'REDRAW': lambda: None,
            'GETVAR': lambda name: 1 if name == 'UNDOCTL' else 'drawing-guid',
            'EXIT': lambda: (_ for _ in ()).throw(RuntimeError('LISP exit')),
        })
        self.h.run('(setq store (EL:StoreInitial))')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, row):
        return self.call('EL:Get', Symbol(key.upper()), row)

    def capture(self):
        return self.h.run("(EL:TransactionVerifiedStore 'EL:StoreWrite (list store))")

    def spy_reads(self):
        reads = []
        self.h.functions['TEST:ORIGINALREAD'] = self.h.functions['EL:STOREREAD']

        def read():
            reads.append(True)
            return self.call('TEST:OriginalRead')

        self.h.builtins['EL:STOREREAD'] = read
        return reads

    def replace_payload(self, value):
        entity = self.dictionary['EL_FIXED_V1']
        payload = self.call('EL:StoreEncode', value)
        self.entities[entity] = [p for p in self.entities[entity]
                                 if p.car not in (1, 2, 3, 40, 90, 300)] + payload

    def test_success_reuses_actual_decoded_readback_after_commit(self):
        ctx = self.capture()
        actual = self.get('verified-store', ctx)
        self.assertTrue(truth(self.get('outcome', ctx)))
        self.assertTrue(truth(self.get('committed', ctx)))
        self.assertEqual(actual, self.h.lookup('STORE'))
        self.assertIsNot(actual, self.h.lookup('STORE'))
        reads = self.spy_reads()
        self.assertEqual(self.call('EL:TransactionVerifiedRead', ctx), actual)
        self.assertEqual(reads, [])
        for name in ('*EL:STORECONTEXTACTIVE*', '*EL:STORECONTEXTCANDIDATE*',
                     '*EL:STORECONTEXTCOMMITTED*'):
            self.assertFalse(truth(self.h.lookup(name)))

    def test_direct_write_and_legacy_transaction_keep_original_truth_values(self):
        self.assertIs(self.h.run('(EL:StoreWrite store)'), True)
        self.h.run("(defun TEST:RecordWriter () (EL:StoreWrite store) 'record-result)")
        self.assertEqual(self.h.run("(EL:Transaction 'TEST:RecordWriter nil)"),
                         Symbol('RECORD-RESULT'))
        self.assertFalse(truth(self.h.lookup('*EL:STORECONTEXTCANDIDATE*')))
        ctx = self.h.run("(EL:TransactionVerifiedStore 'TEST:RecordWriter nil)")
        self.assertEqual(self.get('outcome', ctx), Symbol('RECORD-RESULT'))
        self.assertTrue(truth(self.get('committed', ctx)))

    def test_nil_writer_and_exception_discard_candidate_and_rollback(self):
        for body in ('nil', "(EL:StoreWrite store) (exit)"):
            with self.subTest(body=body):
                self.h.run('(defun TEST:BadWriter () ' + body + ')')
                before = copy.deepcopy((self.entities, self.dictionary))
                ctx = self.h.run("(EL:TransactionVerifiedStore 'TEST:BadWriter nil)")
                self.assertFalse(truth(self.get('outcome', ctx)))
                self.assertFalse(truth(self.get('committed', ctx)))
                self.assertFalse(truth(self.get('verified-store', ctx)))
                self.assertEqual((self.entities, self.dictionary), before)

    def test_native_readback_difference_does_not_publish_context(self):
        original = self.h.builtins['ENTGET']

        def corrupt(entity, *apps):
            data = original(entity, *apps)
            if entity == self.dictionary.get('EL_FIXED_V1'):
                return list(data) + [Pair(1, 'unexpected')]
            return data

        self.h.builtins['ENTGET'] = corrupt
        ctx = self.capture()
        self.assertFalse(truth(self.get('outcome', ctx)))
        self.assertFalse(truth(self.get('verified-store', ctx)))
        self.assertEqual(self.dictionary, {})

    def test_failed_end_undo_cannot_commit_verified_readback(self):
        calls = []

        def end(_):
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError('EndUndoMark failure')

        self.h.builtins['VLA-ENDUNDOMARK'] = end
        ctx = self.capture()
        self.assertFalse(truth(self.get('outcome', ctx)))
        self.assertFalse(truth(self.get('committed', ctx)))
        self.assertFalse(truth(self.get('verified-store', ctx)))
        self.assertEqual(self.dictionary, {})

    def test_commit_callback_change_discards_candidate_and_reads_current_dwg(self):
        changed = self.call('EL:Put', Symbol('NOTES'), 'commit callback', self.h.lookup('STORE'))
        self.h.builtins['VLA-ENDUNDOMARK'] = lambda _: self.replace_payload(changed)
        ctx = self.capture()
        self.assertTrue(truth(self.get('outcome', ctx)))
        self.assertFalse(truth(self.get('committed', ctx)))
        reads = self.spy_reads()
        self.assertEqual(self.call('EL:TransactionVerifiedRead', ctx), changed)
        self.assertEqual(reads, [True])

    def test_second_write_failure_cannot_reuse_first_candidate(self):
        self.h.run("""(defun TEST:TwoWrites ()
            (EL:StoreWrite store)
            (EL:StoreWrite '((schema-version . 9))))""")
        ctx = self.h.run("(EL:TransactionVerifiedStore 'TEST:TwoWrites nil)")
        self.assertFalse(truth(self.get('outcome', ctx)))
        self.assertFalse(truth(self.get('verified-store', ctx)))
        self.assertEqual(self.dictionary, {})

    def test_silent_end_undo_that_leaves_group_open_does_not_promote_context(self):
        state = {'undoctl': 1}
        begin = self.h.builtins['VLA-STARTUNDOMARK']

        def start(doc):
            begin(doc)
            state['undoctl'] = 9

        self.h.builtins.update({
            'VLA-STARTUNDOMARK': start,
            'GETVAR': lambda name: state['undoctl'] if name == 'UNDOCTL' else 'drawing-guid',
        })
        ctx = self.capture()
        self.assertTrue(truth(self.get('outcome', ctx)))
        self.assertFalse(truth(self.get('committed', ctx)))
        self.assertFalse(truth(self.get('verified-store', ctx)))

    def test_late_payload_corruption_uses_decoder_failure_instead_of_cached_data(self):
        ctx = self.capture()
        entity = self.dictionary['EL_FIXED_V1']
        self.entities[entity].append(Pair(1, 'unparsed trailing value'))
        reads = self.spy_reads()
        with self.assertRaisesRegex(RuntimeError, 'LISP exit'):
            self.call('EL:TransactionVerifiedRead', ctx)
        self.assertEqual(reads, [True])

    def test_later_write_or_document_switch_requires_fresh_read(self):
        ctx = self.capture()
        changed = self.call('EL:Put', Symbol('NOTES'), 'next operation', self.h.lookup('STORE'))
        self.call('EL:StoreWrite', changed)
        reads = self.spy_reads()
        self.assertEqual(self.call('EL:TransactionVerifiedRead', ctx), changed)
        self.assertEqual(reads, [True])
        ctx = self.capture()
        self.owner = 'OTHER-NOD'
        self.call('EL:TransactionVerifiedRead', ctx)
        self.assertEqual(reads, [True, True])

    def test_unrelated_transaction_and_empty_context_never_reuse_prior_operation(self):
        self.capture()
        self.h.run('(defun TEST:NoStoreWrite () T)')
        ctx = self.h.run("(EL:TransactionVerifiedStore 'TEST:NoStoreWrite nil)")
        self.assertTrue(truth(self.get('outcome', ctx)))
        self.assertFalse(truth(self.get('committed', ctx)))
        reads = self.spy_reads()
        self.call('EL:TransactionVerifiedRead', ctx)
        self.call('EL:TransactionVerifiedRead', None)
        self.assertEqual(reads, [True, True])

    def test_dictionary_association_and_native_only_change_invalidate_context(self):
        ctx = self.capture()
        entity = self.dictionary['EL_FIXED_V1']
        self.entities['replacement'] = [Pair(p.car, 'replacement') if p.car in (-1, 5)
                                         else p for p in self.entities[entity]]
        self.dictionary['EL_FIXED_V1'] = 'replacement'
        self.assertFalse(truth(self.call('EL:StoreContextValid', ctx)))
        self.dictionary['EL_FIXED_V1'] = entity
        original = self.h.builtins['ENTGET']
        self.h.builtins['ENTGET'] = lambda e, *apps: (original(e, *apps) + [Pair(1, 'native-only')]
                                                   if e == entity else original(e, *apps))
        self.assertFalse(truth(self.call('EL:StoreContextValid', ctx)))


if __name__ == '__main__':
    unittest.main()
