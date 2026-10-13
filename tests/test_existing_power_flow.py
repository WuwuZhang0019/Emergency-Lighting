"""Existing-diagram power-only contracts and transaction adapters.

Date: 2026-10-13. Status: finite adapter checks; native CAD acceptance pending.
"""
import copy
import unittest
from pathlib import Path

from autolisp_host import Pair, Symbol, car, cons, truth
import test_diagram_store as store_fixture

ROOT = Path(__file__).resolve().parents[1]


def pair(key, value):
    return cons(Symbol(key.upper()), value)


class PowerOnlyFixture(unittest.TestCase):
    def setUp(self):
        self.f = store_fixture.StoreTests()
        self.f.setUp()
        self.f.install_transaction()
        self.h = self.f.h
        for module in ('geometry', 'panel', 'diagram-commands'):
            self.h.load_definitions(ROOT / 'src' / (module + '.lsp'))

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, value):
        return self.call('EL:Get', Symbol(key.upper()), value)

    def put(self, key, value, record):
        return self.call('EL:Put', Symbol(key.upper()), value, record)

    def circuit(self, number='ZE1', watts=85, source='plane', status='ready'):
        return [pair('circuit-uid', 'uid-' + number), pair('circuit-number', number),
                pair('number-source', Symbol(source.upper())),
                pair('number-status', Symbol(status.upper())), pair('watts', watts)]

    def result(self, circuits=None):
        if circuits is None:
            circuits = [self.circuit(), self.circuit('ZE2', 0)]
        return [pair('panel', 'source'), pair('engine', Symbol('FIXED')),
                pair('can-generate', True), pair('circuits', circuits)]

    def bindings(self):
        return [[pair('number', 'ZE1'), pair('number-handle', 'number-one'),
                 pair('power-handle', 'power-one'), pair('owner', None),
                 pair('mode', Symbol('AUTO'))],
                [pair('number', 'ZE2'), pair('number-handle', 'number-two'),
                 pair('power-handle', 'power-two'), pair('owner', None),
                 pair('mode', Symbol('MANUAL'))]]

    def binding_record(self):
        return [pair('diagram-id', 'existing-one'), pair('source-panel-handle', 'source'),
                pair('engine', Symbol('FIXED')), pair('power-only-target', 'existing-box'),
                pair('power-only-bindings', self.bindings()),
                pair('power-only-scope', ['number-one', 'power-one', 'number-two', 'power-two'])]


class PowerOnlyContractTests(PowerOnlyFixture):
    def test_ready_accepts_verified_plane_numbers_and_zero_power(self):
        self.assertTrue(truth(self.call('EL:PowerOnlyReady', self.result())))

    def test_ready_rejects_auto_legacy_missing_and_conflicting_numbers(self):
        for source, status in (('auto', 'ready'), ('legacy', 'ready'), ('plane', 'missing'),
                               ('plane', 'conflict'), ('plane', 'invalid'), ('plane', 'path-ambiguous')):
            with self.subTest(source=source, status=status):
                self.assertFalse(truth(self.call('EL:PowerOnlyReady',
                    self.result([self.circuit(source=source, status=status)]))))
        for field in ('number-source', 'number-status', 'circuit-number'):
            circuit = [row for row in self.circuit() if row.car != Symbol(field.upper())]
            with self.subTest(missing=field):
                self.assertFalse(truth(self.call('EL:PowerOnlyReady', self.result([circuit]))))

    def test_ready_rejects_duplicate_number_keys_and_invalid_numbers(self):
        for number in ('ZE1', ' ze1 ', 'ze1'):
            with self.subTest(duplicate=number):
                self.assertFalse(truth(self.call('EL:PowerOnlyReady',
                    self.result([self.circuit(), self.circuit(number, 20)]))))
        for number in ('', '   ', 'ZE\\P1', 'ZE\n1', None, 3):
            with self.subTest(invalid=number):
                circuit = self.put('circuit-number', number, self.circuit())
                self.assertFalse(truth(self.call('EL:PowerOnlyReady', self.result([circuit]))))

    def test_ready_rejects_missing_statistics_or_negative_nonnumeric_power(self):
        self.assertFalse(truth(self.call('EL:PowerOnlyReady', self.result([]))))
        self.assertFalse(truth(self.call('EL:PowerOnlyReady', self.put('can-generate', None, self.result()))))
        for watts in (-1, -0.001, '85', None):
            with self.subTest(watts=watts):
                self.assertFalse(truth(self.call('EL:PowerOnlyReady',
                    self.result([self.circuit(watts=watts)]))))

    def test_result_restores_saved_binding_without_changing_statistics(self):
        result = self.result()
        before = copy.deepcopy(result)
        restored = self.call('EL:PowerOnlyResult', result, self.binding_record())
        self.assertEqual(self.get('power-only-target', restored), 'existing-box')
        self.assertEqual(self.get('power-only-bindings', restored), self.bindings())
        self.assertEqual(self.get('power-only-scope', restored),
                         self.get('power-only-scope', self.binding_record()))
        self.assertEqual(self.get('circuits', restored), self.get('circuits', result))
        self.assertEqual(result, before)

    def test_result_explicit_values_and_nil_take_precedence_over_saved_binding(self):
        replacement = [self.bindings()[1]]
        for target, bindings in (('another-box', replacement), (None, None)):
            with self.subTest(target=target):
                result = self.put('power-only-target', target,
                    self.put('power-only-bindings', bindings, self.result()))
                restored = self.call('EL:PowerOnlyResult', result, self.binding_record())
                self.assertEqual(self.get('power-only-target', restored), target)
                self.assertEqual(self.get('power-only-bindings', restored), bindings)

    def test_result_restores_each_missing_field_independently_and_leaves_old_records_usable(self):
        result = self.put('power-only-bindings', None, self.result())
        restored = self.call('EL:PowerOnlyResult', result, self.binding_record())
        self.assertEqual(self.get('power-only-target', restored), 'existing-box')
        self.assertIsNone(self.get('power-only-bindings', restored))
        result = self.result()
        restored = self.call('EL:PowerOnlyResult', result,
            [pair('diagram-id', 'legacy'), pair('source-panel-handle', 'source')])
        self.assertEqual(self.get('circuits', restored), self.get('circuits', result))
        self.assertIsNone(self.get('power-only-target', restored))
        self.assertIsNone(self.get('power-only-bindings', restored))

    def test_binding_fields_roundtrip_in_split_store_without_overwriting_other_record(self):
        self.h.load_definitions(ROOT / 'src/store-split.lsp')
        self.h.frames[0]['*EL:SPLITSTORAGELOADED*'] = True
        record = self.binding_record()
        other = [pair('diagram-id', 'other'), pair('source-panel-handle', 'other-source'),
                 pair('custom-extension', [pair('precise', -1e-280)])]
        store = self.put('diagrams', [record, other], self.call('EL:StoreInitial'))
        context = self.call('EL:TransactionVerifiedStore', Symbol('EL:STOREWRITE'), [store])
        self.assertTrue(truth(self.get('committed', context)))
        for key in ('*EL:SPLITCACHE*', '*EL:STOREREADCACHE*', '*EL:STOREWARMCACHE*'):
            self.h.frames[0][key] = None
        reopened = self.call('EL:StoreRead')
        self.assertEqual(reopened, store)
        saved = self.call('EL:StoreRecord', 'existing-one')
        self.assertEqual(self.call('EL:PowerOnlyResult', self.result(), saved),
                         self.call('EL:PowerOnlyResult', self.result(), record))
        self.assertEqual(self.call('EL:StoreRecord', 'other'), other)


class PowerOnlyMatchTests(PowerOnlyFixture):
    def ref(self, handle, text, x, y, owner=None, angle=0.0, height=2.5):
        data = [Pair(-1, handle), Pair(5, handle), Pair(0, 'TEXT'), Pair(330, owner or 'model-btr'),
                Pair(1, text), Pair(10, [float(x), float(y), 0.0]), Pair(8, 'USER-POWER'),
                Pair(7, 'UserStyle'), Pair(40, height), Pair(41, .83), Pair(50, angle),
                Pair(62, 3), Pair(410, 'Model'), Pair(72, 0), Pair(73, 0)]
        return [pair('handle', handle), pair('data', data), pair('text', text),
                pair('point', [float(x), float(y), 0.0]),
                pair('angle', angle), pair('height', height), pair('owner', owner),
                pair('type', 'TEXT'), pair('parent-data', None), pair('drawing-owner', 'NOD')
                ] + self.call('EL:PowerTextDisplay', text, None)

    def refs(self):
        return [self.ref('number-one', 'ZE1', 0, 10), self.ref('power-one', '12W', 15, 10),
                self.ref('number-two', 'ZE2', 0, 0), self.ref('power-two', '25W', 15, 0)]

    def match(self, result=None, refs=None, bindings=None):
        return self.call('EL:PowerOnlyMatch', self.result() if result is None else result,
                         self.refs() if refs is None else refs, bindings, None)

    def test_match_uses_exact_number_keys_independent_of_circuit_and_selection_order(self):
        refs = self.refs()
        circuits = list(reversed(self.get('circuits', self.result())))
        plan = self.match(self.result(circuits), [refs[3], refs[0], refs[2], refs[1]])
        self.assertEqual({self.get('number', row): self.get('power-handle', row) for row in plan},
                         {'ZE1': 'power-one', 'ZE2': 'power-two'})
        self.assertEqual({self.get('number', row): self.get('mode', row) for row in plan},
                         {'ZE1': Symbol('AUTO'), 'ZE2': Symbol('AUTO')})
        for row in plan:
            ref = self.get('power-ref', row)
            before = [field for field in self.get('data', ref) if field.car != 1]
            after = [field for field in self.get('after', row) if field.car != 1]
            self.assertEqual(after, before)

    def test_duplicate_or_missing_number_text_cannot_be_silently_matched(self):
        for refs in (self.refs()[1:], self.refs() + [self.ref('duplicate-number', ' ze1 ', 0, 25)]):
            with self.subTest(handles=[self.get('handle', ref) for ref in refs]):
                with self.assertRaises(RuntimeError):
                    self.match(refs=refs)

    def test_multiple_same_row_powers_and_one_power_shared_by_two_numbers_are_not_auto_matched(self):
        ambiguous = self.refs() + [self.ref('another-power', '4W', 30, 10)]
        shared = [self.ref('number-one', 'ZE1', 0, 0), self.ref('number-two', 'ZE2', 0, 1),
                  self.ref('shared-power', '4W', 20, .5)]
        for refs in (ambiguous, shared):
            with self.subTest(handles=[self.get('handle', ref) for ref in refs]):
                self.assertIsNone(self.match(refs=refs))

    def test_saved_manual_binding_resolves_ambiguity_but_rechecks_number_and_owner(self):
        refs = self.refs()[:2] + [self.ref('chosen-power', '4W', 30, 10)]
        binding = [pair('number', 'ZE1'), pair('number-handle', 'number-one'),
                   pair('power-handle', 'chosen-power'), pair('owner', None),
                   pair('mode', Symbol('MANUAL'))]
        result = self.result([self.circuit()])
        plan = self.match(result, refs, [binding])
        self.assertEqual(self.get('power-handle', plan[0]), 'chosen-power')
        self.assertEqual(self.get('mode', plan[0]), Symbol('MANUAL'))
        changed_number = [self.ref('number-one', 'ZE9', 0, 10)] + refs[1:]
        changed_owner = refs[:2] + [self.ref('chosen-power', '4W', 30, 10, owner='other-box')]
        for changed in (changed_number, changed_owner):
            with self.subTest(changed=changed):
                with self.assertRaises(RuntimeError):
                    self.match(result, changed, [binding])

    def test_saved_auto_binding_cannot_silently_switch_to_a_different_power(self):
        binding = self.bindings()[0]
        refs = [self.ref('number-one', 'ZE1', 0, 10),
                self.ref('power-one', '12W', 15, 50), self.ref('different-power', '25W', 15, 10)]
        with self.assertRaises(RuntimeError):
            self.match(self.result([self.circuit()]), refs, [binding])


class PowerOnlyTransactionFixture(PowerOnlyFixture):
    ref = PowerOnlyMatchTests.ref
    refs = PowerOnlyMatchTests.refs
    match = PowerOnlyMatchTests.match

    def setUp(self):
        super().setUp()
        self.writes = []
        self.fail_write = None
        self.h.builtins['EL:FRESHRESULT'] = lambda *args: True
        self.h.builtins['EL:DLSUBMISSIONCURRENT'] = lambda *args: True
        self.h.builtins['EL:POWERTEXTREAD'] = self.read_ref
        self.h.builtins['EL:POWERTEXTWRITE'] = self.write_ref
        self.h.builtins['TBLSEARCH'] = lambda *args: [Pair(70, 0), Pair(62, 7)]
        for name in ('EL:SYNCDIAGRAM', 'EL:INVOKECCKK2', 'VLA-INSERTBLOCK',
                     'VLA-MOVE', 'EL:SETDYNAMICVALUE', 'ENTMAKE'):
            self.h.builtins[name] = lambda *args, api=name: self.fail('power-only flow called ' + api)

    def read_ref(self, entity):
        data = self.f.entities.get(entity)
        if data is None:
            return None
        def field(code, default=None):
            return next((row.cdr for row in data if isinstance(row, Pair) and row.car == code), default)
        value = self.ref(entity, field(1, ''), field(10, [0, 0, 0])[0],
                         field(10, [0, 0, 0])[1], owner=field(330) if field(0) == 'ATTRIB' else None,
                         angle=field(50, 0.0), height=field(40, 2.5))
        return self.put('data', copy.deepcopy(data), value)

    def write_ref(self, ref, after):
        self.writes.append(self.get('handle', ref))
        if self.fail_write == len(self.writes):
            raise RuntimeError('native power text write failed')
        self.h.builtins['ENTMOD'](copy.deepcopy(after))
        return True

    def prepare_apply(self):
        refs = self.refs()
        for ref in refs:
            self.f.entities[self.get('handle', ref)] = copy.deepcopy(self.get('data', ref))
        self.f.entities['existing-box'] = [Pair(-1, 'existing-box'), Pair(5, 'existing-box'),
            Pair(0, 'INSERT'), Pair(2, 'UserExistingDiagram'), Pair(8, 'USER-BOX'), Pair(410, 'Model'),
            Pair(330, 'model-btr')]
        self.f.entities['model-btr'] = [Pair(-1, 'model-btr'), Pair(5, 'model-btr'),
            Pair(0, 'BLOCK_RECORD'), Pair(2, '*MODEL_SPACE')]
        self.f.entities['source'] = [Pair(-1, 'source'), Pair(5, 'source'), Pair(0, 'INSERT')]
        record = self.put('custom-extension', [pair('precise', -1e-280)], self.binding_record())
        store = self.put('diagrams', [record], self.call('EL:StoreInitial'))
        self.assertTrue(truth(self.call('EL:StoreWrite', store)))
        result = self.put('power-only-scope', [self.get('handle', ref) for ref in refs],
                         self.put('power-only-target', 'existing-box', self.result()))
        return result, None, None, Symbol('CAP300'), record, store, self.match(result, refs)

    def transaction(self, args):
        return self.call('EL:TransactionVerifiedStore', Symbol('EL:POWERONLYAPPLY'), list(args))

    def state(self):
        return copy.deepcopy((self.f.entities, self.f.dictionary))


class PowerOnlyTransactionTests(PowerOnlyTransactionFixture):
    def test_apply_updates_only_power_content_and_reopens_saved_bindings(self):
        args = self.prepare_apply()
        before = copy.deepcopy(self.f.entities)
        context = self.transaction(args)
        self.assertTrue(truth(self.get('committed', context)))
        self.assertEqual(set(self.writes), {'power-one', 'power-two'})
        self.assertEqual(next(row.cdr for row in self.f.entities['power-one'] if row.car == 1), '85W')
        self.assertEqual(next(row.cdr for row in self.f.entities['power-two'] if row.car == 1), '0W')
        for handle in ('number-one', 'number-two', 'existing-box', 'source'):
            self.assertEqual(self.f.entities[handle], before[handle])
        for handle in ('power-one', 'power-two'):
            self.assertEqual([row for row in self.f.entities[handle] if row.car != 1],
                             [row for row in before[handle] if row.car != 1])
        reopened = self.call('EL:DiagramForPanel', 'source', self.call('EL:StoreRead'))
        self.assertEqual(self.get('custom-extension', reopened), self.get('custom-extension', args[4]))
        self.assertEqual(self.get('power-only-target', reopened), 'existing-box')
        self.assertEqual(self.get('power-only-scope', reopened), self.get('power-only-scope', args[0]))
        bindings = self.get('power-only-bindings', reopened)
        self.assertEqual({self.get('number', row): self.get('power-handle', row) for row in bindings},
                         {'ZE1': 'power-one', 'ZE2': 'power-two'})
        for row in bindings:
            self.assertFalse(any(car(field) in (Symbol('NUMBER-REF'), Symbol('POWER-REF'), Symbol('AFTER'))
                                 for field in row))

    def test_second_power_write_failure_rolls_back_first_power_and_saved_record(self):
        args = self.prepare_apply()
        before = self.state()
        self.fail_write = 2
        context = self.transaction(args)
        self.assertFalse(truth(self.get('outcome', context)))
        self.assertEqual(self.state(), before)
        self.assertEqual(len(self.writes), 2)
        self.assertEqual(set(self.writes), {'power-one', 'power-two'})

    def test_store_failure_after_power_writes_rolls_back_complete_batch(self):
        args = self.prepare_apply()
        before = self.state()
        self.h.builtins['EL:STOREWRITE'] = lambda *args: None
        context = self.transaction(args)
        self.assertFalse(truth(self.get('outcome', context)))
        self.assertEqual(self.state(), before)
        self.assertEqual(set(self.writes), {'power-one', 'power-two'})

    def test_late_write_or_store_callback_mutation_rolls_back_complete_batch(self):
        for callback in ('second-power-write', 'store-write'):
            with self.subTest(callback=callback):
                self.setUp()
                args = self.prepare_apply()
                before = self.state()
                if callback == 'second-power-write':
                    native_write = self.write_ref
                    def write_then_change_earlier(ref, after):
                        native_write(ref, after)
                        if len(self.writes) == 2:
                            earlier = self.writes[0]
                            self.f.entities[earlier] = [Pair(1, '999W') if row.car == 1 else row
                                                       for row in self.f.entities[earlier]]
                        return True
                    self.h.builtins['EL:POWERTEXTWRITE'] = write_then_change_earlier
                else:
                    def store_then_change_number(store):
                        del self.h.builtins['EL:STOREWRITE']
                        answer = self.call('EL:StoreWrite', store)
                        self.f.entities['number-one'] = [Pair(1, 'ZE9') if row.car == 1 else row
                                                        for row in self.f.entities['number-one']]
                        return answer
                    self.h.builtins['EL:STOREWRITE'] = store_then_change_number
                context = self.transaction(args)
                self.assertFalse(truth(self.get('outcome', context)))
                self.assertEqual(self.state(), before)
                self.assertEqual(set(self.writes), {'power-one', 'power-two'})

    def test_changed_reference_or_source_gate_rejects_before_any_power_write(self):
        for change in ('number', 'power', 'source', 'library', 'parent', 'drawing'):
            with self.subTest(change=change):
                self.setUp()
                args = self.prepare_apply()
                if change in ('number', 'power'):
                    handle = 'number-one' if change == 'number' else 'power-one'
                    self.f.entities[handle] = [Pair(1, 'changed-after-review') if row.car == 1 else row
                                              for row in self.f.entities[handle]]
                elif change in ('source', 'library'):
                    api = 'EL:FRESHRESULT' if change == 'source' else 'EL:DLSUBMISSIONCURRENT'
                    self.h.builtins[api] = lambda *args: None
                else:
                    native_read = self.read_ref
                    field = 'parent-data' if change == 'parent' else 'drawing-owner'
                    self.h.builtins['EL:POWERTEXTREAD'] = lambda entity: self.put(
                        field, 'changed-owner-or-parent', native_read(entity))
                before = self.state()
                context = self.transaction(args)
                self.assertFalse(truth(self.get('outcome', context)))
                self.assertEqual(self.state(), before)
                self.assertEqual(self.writes, [])


class PowerOnlyEntryTests(PowerOnlyTransactionFixture):
    def test_first_existing_diagram_pick_without_saved_store_creates_only_memory_record(self):
        self.f.entities['existing-box'] = [Pair(-1, 'existing-box'), Pair(5, 'existing-box'),
            Pair(0, 'INSERT'), Pair(2, 'UserExistingDiagram'), Pair(8, 'USER-BOX'),
            Pair(410, 'Model'), Pair(330, 'model-btr')]
        self.f.entities['model-btr'] = [Pair(-1, 'model-btr'), Pair(5, 'model-btr'),
            Pair(0, 'BLOCK_RECORD'), Pair(2, '*MODEL_SPACE')]
        self.h.builtins['EL:PICKMODEL'] = lambda *args: ['existing-box', [0., 0., 0.]]
        self.h.builtins['EL:STOREWRITE'] = lambda *args: self.fail('selection must not persist')
        before = self.state()
        record = self.call('EL:RepickRecord', 'source', None)
        self.assertEqual(self.get('power-only-target', record), 'existing-box')
        self.assertTrue(self.get('diagram-id', record).startswith('drawing-guid/source/'))
        self.assertEqual(self.get('source-panel-handle', record), 'source')
        self.assertIsNone(self.get('power-only-scope', record))
        self.assertIsNone(self.get('power-only-bindings', record))
        self.assertEqual(self.state(), before)

    def test_repick_resume_preserves_unsaved_power_scope_over_stale_record(self):
        args = self.prepare_apply()
        old = self.put('power-only-target', 'new-unsaved-box', self.put('power-only-scope',
            ['new-number', 'new-power'], self.put('power-only-bindings', [], args[0])))
        self.h.frames[0]['*EL:STARTPICKRESUME*'] = [pair('result', old), pair('powers', None)]
        self.h.builtins['EL:STOREWRITE'] = lambda *args: self.fail('repick resume must not persist')
        before = self.state()
        resumed = self.call('EL:StartPickResumeResult', args[0], None)
        for field in ('power-only-target', 'power-only-scope', 'power-only-bindings'):
            self.assertEqual(self.get(field, resumed), self.get(field, old))
            self.assertEqual(self.get(field, self.get('result', self.h.frames[0]['*EL:DLRESUME*'])),
                             self.get(field, old))
        self.assertEqual(self.state(), before)

    def test_saved_scope_updates_through_real_entry_without_reselection(self):
        args = self.prepare_apply()
        self.h.builtins['SSGET'] = lambda *args: self.fail('saved scope requested another selection')
        self.h.builtins['NENTSEL'] = lambda *args: self.fail('valid saved mapping requested another pick')
        self.assertTrue(truth(self.call('EL:UpdateExistingPower', *args[:4])))
        self.assertEqual(set(self.writes), {'power-one', 'power-two'})
        reopened = self.call('EL:DiagramForPanel', 'source', self.call('EL:StoreRead'))
        self.assertEqual(self.get('power-only-scope', reopened), self.get('power-only-scope', args[0]))

    def test_panel_power_mode_bypasses_template_but_keeps_number_and_power_gates(self):
        closed, errors = [], []
        self.h.builtins.update({
            'EL:PANELSTORESELECTIONS': lambda: True,
            'EL:DLPANELSUBMISSIONREADY': lambda: True,
            'DONE_DIALOG': closed.append,
            'EL:PANELTEXT': lambda tile, message: errors.append((tile, message)),
            'EL:TEMPLATEREADY': lambda *args: self.fail('power-only generation required a template'),
        })
        self.h.frames[0]['*EL:PANELTEMPLATEREADY*'] = None
        result = self.put('power-only-target', 'existing-box', self.result())
        self.h.frames[0]['*EL:PANELDRAFT*'] = result
        self.call('EL:PanelGenerateBody')
        self.assertEqual(closed, [2])
        self.assertEqual(self.h.lookup('*EL:PANELACTION*'), Symbol('GENERATE'))
        for invalid in (self.result([self.circuit(source='auto')]),
                        self.result([self.circuit(status='conflict')]),
                        self.result([self.circuit(watts=-1)]),
                        self.put('can-generate', None, self.result())):
            closed.clear(); errors.clear()
            self.h.frames[0]['*EL:PANELACTION*'] = None
            self.h.frames[0]['*EL:PANELDRAFT*'] = self.put('power-only-target', 'existing-box', invalid)
            self.call('EL:PanelGenerateBody')
            self.assertEqual(closed, [])
            self.assertIsNone(self.h.lookup('*EL:PANELACTION*'))
            self.assertTrue(errors)

    def test_save_draft_keeps_existing_binding_without_updating_power(self):
        args = self.prepare_apply()
        original = {handle: copy.deepcopy(self.f.entities[handle])
                    for handle in ('number-one', 'number-two', 'power-one', 'power-two', 'existing-box')}
        self.h.builtins['EL:TEMPLATEREADY'] = lambda *args: None
        self.assertTrue(truth(self.call('EL:SaveDraft', *args[:4])))
        saved = self.call('EL:DiagramForPanel', 'source', self.call('EL:StoreRead'))
        for key in ('power-only-target', 'power-only-scope', 'power-only-bindings'):
            self.assertEqual(self.get(key, saved), self.get(key, args[4]))
        self.assertEqual(self.get('status', saved), Symbol('STALE'))
        self.assertEqual({handle: self.f.entities[handle] for handle in original}, original)
        self.assertEqual(self.writes, [])


if __name__ == '__main__':
    unittest.main()
