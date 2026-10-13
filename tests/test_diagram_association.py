"""Saved-member association and native generation regression checks.

Date: 2026-10-13. Status: finite adapters only; native CAD acceptance pending.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
import test_cckk_panel_command as panel
from test_cckk_assembly import field


class DiagramAssociationTests(unittest.TestCase):
    def setUp(self):
        self.f = panel.PanelCommandTests()
        self.f.setUp()
        self.h = self.f.h
        self.call = self.f.call
        self.get = self.f.get
        # install_sync stubs this guard. Every test below executes its real LISP.
        self.h.builtins.pop('EL:UNIQUEDIAGRAM', None)
        self.assertIn('EL:UNIQUEDIAGRAM', self.h.functions)
        self.scans = []
        self.h.builtins.update({
            'SSGET': self.tag_selection,
            'SSLENGTH': lambda selection: len(selection),
            'SSNAME': lambda selection, index: selection[index],
        })
        self.f.two_circuits()

    def tag_selection(self, *args):
        self.scans.append(args)
        return [entity for entity in self.f.entities
                if self.call('EL:DiagramTag', entity)] or None

    def forbid_whole_drawing_scan(self):
        self.h.builtins['SSGET'] = lambda *args: self.fail(
            'saved-member association must not scan the whole drawing')

    def saved(self):
        store = self.call('EL:StoreRead')
        return store, self.call('EL:DiagramForPanel', 'source', store)

    def generate(self):
        self.assertTrue(truth(self.f.invoke()))
        return self.saved()

    def save_record(self, record, store):
        self.assertTrue(truth(self.call('EL:StoreWrite',
            self.call('EL:StorePutDiagram', record, store))))

    def clone(self, source, handle):
        self.f.entities[handle] = [
            Pair(row.car, handle) if isinstance(row, Pair) and row.car in (-1, 5)
            else copy.deepcopy(row) for row in self.f.entities[source]]
        if source in self.f.dynamic:
            self.f.dynamic[handle] = copy.deepcopy(self.f.dynamic[source])
        return handle

    def unrecorded_objects(self, record, store):
        handles = []
        for index, ref in enumerate(self.call('EL:DiagramOutputRefs', record)):
            if ref[0] and ref[0] in self.f.entities:
                handles.append(self.clone(ref[0], 'copied-' + str(index)))
        # Same diagram ID, different drawing owner, and a valid self handle.
        foreign = self.clone('panel', 'foreign-same-id')
        other_store = self.call('EL:Put', Symbol('DRAWING-UUID'), 'another-drawing', store)
        self.call('EL:TagEntity', foreign, other_store, record, 'panel', 'panel')
        handles.append(foreign)
        return {handle: copy.deepcopy(self.f.entities[handle]) for handle in handles}

    def assert_unrecorded_unchanged(self, snapshot):
        self.assertEqual({handle: self.f.entities.get(handle) for handle in snapshot}, snapshot)

    def state(self):
        return copy.deepcopy((self.f.entities, self.f.dictionary, self.f.dynamic))

    def assert_rejected_without_writes(self, store, record):
        before = self.state()
        commands = len(self.f.commands)
        self.assertFalse(truth(self.call('EL:UniqueDiagram', store, record)))
        with self.assertRaises(RuntimeError):
            self.f.invoke()
        self.assertEqual(self.state(), before)
        self.assertEqual(len(self.f.commands), commands)

    def test_new_generation_ignores_unrecorded_copies_and_foreign_same_id(self):
        store, record = self.saved()
        unrelated = self.unrecorded_objects(record, store)
        self.assertTrue(truth(self.call('EL:UniqueDiagram', store, record)))
        self.forbid_whole_drawing_scan()
        _, generated = self.generate()
        self.assertEqual(self.get('diagram-id', generated), self.get('diagram-id', record))
        self.assertNotIn(self.get('panel-output-handle', generated), unrelated)
        self.assert_unrecorded_unchanged(unrelated)

    def test_existing_update_changes_only_saved_members_without_global_selection(self):
        store, record = self.generate()
        unrelated = self.unrecorded_objects(record, store)
        old_commands = len(self.f.commands)
        self.forbid_whole_drawing_scan()
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'watts 135 "
                   "(car (EL:Get 'circuits result))) (cdr (EL:Get 'circuits result))) result))")
        self.assertTrue(truth(self.f.invoke()))
        _, updated = self.saved()
        self.assertEqual(self.get('panel-output-handle', updated), self.get('panel-output-handle', record))
        self.assertEqual(len(self.f.commands), old_commands)
        power_handle = self.get('text-handle', self.get('rows', updated)[0])
        self.assertEqual(field(self.f.entities[power_handle], 1), '135W')
        self.assert_unrecorded_unchanged(unrelated)

    def test_association_reads_only_saved_handles(self):
        store, record = self.generate()
        self.forbid_whole_drawing_scan()
        refs = self.call('EL:DiagramOutputRefs', record)
        expected = {ref[0] for ref in refs if ref[0]}
        reads = []
        entget = self.h.builtins['ENTGET']
        self.h.builtins['ENTGET'] = lambda entity, apps=None: (
            reads.append(entity), entget(entity, apps))[1]
        self.assertTrue(truth(self.call('EL:UniqueDiagram', store, record)))
        self.assertEqual(set(reads), expected)

    def test_missing_power_text_is_recreated_without_adopting_unrecorded_copy(self):
        store, record = self.generate()
        unrelated = self.unrecorded_objects(record, store)
        row = self.get('rows', record)[0]
        old_text = self.get('text-handle', row)
        self.f.entities.pop(old_text)
        commands = len(self.f.commands)
        self.forbid_whole_drawing_scan()
        self.assertTrue(truth(self.call('EL:UniqueDiagram', store, record)))
        self.assertTrue(truth(self.f.invoke()))
        _, repaired = self.saved()
        new_row = self.get('rows', repaired)[0]
        new_text = self.get('text-handle', new_row)
        self.assertNotEqual(new_text, old_text)
        self.assertNotIn(new_text, unrelated)
        self.assertEqual(field(self.f.entities[new_text], 1), '85W')
        self.assertEqual(self.get('block-handle', new_row), self.get('block-handle', row))
        self.assertEqual(self.get('panel-output-handle', repaired), self.get('panel-output-handle', record))
        self.assertEqual(len(self.f.commands), commands)
        self.assert_unrecorded_unchanged(unrelated)

    def test_full_saved_member_identity_and_native_handle_mismatch_are_rejected(self):
        store, record = self.generate()
        row = self.get('rows', record)[0]
        targets = [self.get('panel-output-handle', record), self.get('block-handle', row),
                   self.get('text-handle', row), self.get('handle', self.get('cckk-labels', record)[0])]
        # The five tag fields are drawing, diagram, member kind, UID, self handle.
        for handle in targets:
            original = copy.deepcopy(self.f.entities[handle])
            for changed in range(7):
                with self.subTest(handle=handle, field=changed):
                    data = copy.deepcopy(original)
                    if changed < 5:
                        xdata = next(item for item in data if isinstance(item, list) and item[0] == -3)
                        xdata[1][changed + 1] = Pair(1000, 'wrong-' + str(changed))
                    else:
                        code, value = (0, 'LINE') if changed == 5 else (5, 'another-native-handle')
                        data = [Pair(code, value) if isinstance(item, Pair) and item.car == code
                                else item for item in data]
                    self.f.entities[handle] = data
                    self.assert_rejected_without_writes(store, record)
                    self.f.entities[handle] = copy.deepcopy(original)

    def test_duplicate_saved_handle_is_rejected_even_with_matching_tag(self):
        store, record = self.generate()
        rows = self.get('rows', record)
        record = self.call('EL:Put', Symbol('ROWS'), rows + [copy.deepcopy(rows[0])], record)
        self.save_record(record, store)
        self.assert_rejected_without_writes(*self.saved())

    def test_duplicate_member_identity_on_different_owned_handles_is_rejected(self):
        store, record = self.generate()
        rows = self.get('rows', record)
        uid = self.get('circuit-uid', rows[0])
        rows[1] = self.call('EL:Put', Symbol('CIRCUIT-UID'), uid, rows[1])
        for key, kind in (('block-handle', 'circuit'), ('text-handle', 'text')):
            self.call('EL:TagEntity', self.get(key, rows[1]), store, record, kind, uid)
        record = self.call('EL:Put', Symbol('ROWS'), rows, record)
        self.save_record(record, store)
        self.assert_rejected_without_writes(*self.saved())

    def test_deleted_original_rebuild_keeps_record_identity_and_never_adopts_copy(self):
        for remove_all in (False, True):
            with self.subTest(remove_all=remove_all):
                self.setUp()
                store, record = self.generate()
                unrelated = self.unrecorded_objects(record, store)
                handles = [ref[0] for ref in self.call('EL:DiagramOutputRefs', record) if ref[0]]
                for handle in handles if remove_all else [self.get('panel-output-handle', record)]:
                    self.f.entities.pop(handle)
                if remove_all:
                    # Native HANDENT may still resolve an erased object's ename.
                    # ENTGET returning nil is the authoritative missing state.
                    handent = self.h.builtins['HANDENT']
                    self.h.builtins['HANDENT'] = lambda handle: (
                        handle if handle in handles else handent(handle))
                old_commands = len(self.f.commands)
                self.forbid_whole_drawing_scan()
                self.assertTrue(truth(self.f.invoke()))
                _, rebuilt = self.saved()
                self.assertEqual(self.get('diagram-id', rebuilt), self.get('diagram-id', record))
                self.assertEqual([self.get('circuit-uid', row) for row in self.get('rows', rebuilt)],
                                 [self.get('circuit-uid', row) for row in self.get('rows', record)])
                new_handles = {ref[0] for ref in self.call('EL:DiagramOutputRefs', rebuilt) if ref[0]}
                self.assertFalse(new_handles.intersection(unrelated))
                self.assertFalse(new_handles.intersection(handles))
                self.assertEqual(self.f.commands[old_commands][-1], 'pause')
                self.assert_unrecorded_unchanged(unrelated)

    def test_cancel_rebuild_rolls_back_old_members_record_and_unrecorded_objects(self):
        store, record = self.generate()
        unrelated = self.unrecorded_objects(record, store)
        self.f.entities.pop(self.get('panel-output-handle', record))
        before = self.state()
        self.f.fail_at = len(self.f.commands) + 3
        self.forbid_whole_drawing_scan()
        self.assertFalse(truth(self.f.invoke()))
        self.assertEqual(self.state(), before)
        self.assertEqual(self.saved()[1], record)
        self.assert_unrecorded_unchanged(unrelated)
        self.assertNotIn('EL_FIXED_TX', self.f.dictionary)
        for suffix in ('OPEN', 'DIRTY', 'RUNNING'):
            self.assertFalse(truth(self.h.lookup('*EL:TRANSACTION' + suffix + '*')))


if __name__ == '__main__':
    unittest.main()
