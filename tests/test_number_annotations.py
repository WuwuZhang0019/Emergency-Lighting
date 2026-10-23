"""Date: 2026-10-21. Native owner links, bounded reads and freshness evidence."""
import copy
import json
import unittest
from pathlib import Path
from autolisp_host import Host, Pair, Symbol, entity_data, truth
import test_circuit_number as number_tests
import test_diagram_store as store_tests
from test_circuit_number import pair

ROOT = Path(__file__).resolve().parents[1]


class NumberAnnotationTests(unittest.TestCase):
    call = number_tests.NumberReadTests.call
    get = number_tests.NumberReadTests.get

    def setUp(self):
        self.h = Host()
        for name in ('common', 'geometry', 'circuit-number'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        self.entities = {}
        self.texts = {}
        self.scans = 0
        self.text_reads = []
        self.events = []
        self.fail_scan = False
        self.h.builtins.update({
            'SSGET': self.select,
            'SSLENGTH': len,
            'SSNAME': lambda selection, index: selection[index],
            'HANDENT': lambda handle: handle if handle in self.entities else None,
            'ENTGET': lambda entity, apps=None: entity_data(self.entities.get(entity), apps),
            'VLAX-ENAME->VLA-OBJECT': lambda entity: entity,
            'VLAX-PROPERTY-AVAILABLE-P': lambda entity, prop: entity in self.texts,
            'VLAX-GET-PROPERTY': self.read_text,
            'EL:LOGEVENT': lambda event, values: self.events.append((event, values)),
        })
        self.wire('A1')
        self.wire('A2', 'ZE2')

    def select(self, mode, filter):
        self.scans += 1
        self.assertEqual(mode, '_X')
        self.assertEqual(filter, [Pair(0, 'TCH_WIREDIM2')])
        if self.fail_scan:
            raise RuntimeError('native scan failed')
        return [handle for handle, data in self.entities.items()
                if next(row.cdr for row in data if isinstance(row, Pair) and row.car == 0) == 'TCH_WIREDIM2'] or None

    def read_text(self, entity, prop):
        self.text_reads.append(entity)
        self.assertEqual(prop, Symbol('TEXTSTRING'))
        text = self.texts[entity]
        if isinstance(text, Exception):
            raise text
        return text

    def wire(self, handle, text=None):
        self.entities[handle] = [Pair(0, 'LWPOLYLINE'), Pair(5, handle)]
        if text is not None:
            self.entities[handle].append([-3, ['linenum', Pair(1000, text)]])

    def annotation(self, handle='B1', owner='A1', text='ZE1', number=None):
        data = [Pair(0, 'TCH_WIREDIM2'), Pair(5, handle),
                [-3, ['TG_DIMWIRE_TYPE', Pair(1000, 'WireNameOnly')],
                 ['KeyOwnWireId', Pair(1000, 'KeyOwnWireId'), Pair(1005, owner)]]]
        if number is not None:
            data[-1].append(['linenum', Pair(1000, number)])
        self.entities[handle] = data
        if text is not None:
            self.texts[handle] = text

    def circuits(self, sources=('A1', 'A2')):
        return [[pair('id', f'R{i}'), pair('circuit-uid', f'uid{i}'), pair('watts', 7*i),
                 pair('number-scope', [pair('status', Symbol('READY')), pair('sources', [handle])])]
                for i, handle in enumerate(sources, 1)]

    def result(self, sources=('A1', 'A2')):
        return self.call('EL:ResolveCircuitNumbers', [pair('circuits', self.circuits(sources))])

    def test_explicit_owner_reads_native_text_once_per_batch_and_preserves_source(self):
        self.annotation()
        self.annotation('B2', 'A2', 'ZE2')
        self.annotation('B3', 'C1', 'other')
        self.wire('C1')
        result = self.result()
        self.assertEqual(self.scans, 1)
        self.assertEqual(self.text_reads, ['B1', 'B2'])
        circuits = self.get('circuits', result)
        self.assertEqual([self.get('circuit-number', c) for c in circuits], ['ZE1', 'ZE2'])
        self.assertEqual([self.get('number-source', c) for c in circuits], [Symbol('PLANE')]*2)
        inputs = self.get('number-inputs', result)
        evidence = self.get('annotations', inputs[0])[0]
        self.assertEqual(self.get('handle', evidence), 'B1')
        self.assertEqual(self.get('owners', evidence), ['A1'])
        before = copy.deepcopy(self.entities)
        self.assertTrue(truth(self.call('EL:NumberInputsCurrent', result)))
        self.assertEqual(self.scans, 2)
        self.assertEqual(before, self.entities)

    def test_conflict_and_unreadable_associated_text_are_never_auto(self):
        for native, annotation_text, metadata, expected in (
            ('ZE2', 'ZE1', None, 'CONFLICT'),
            (None, 'ZE1', 'ZE9', 'CONFLICT'),
            (None, None, None, 'INVALID'),
            (None, '', None, 'INVALID'),
            (None, RuntimeError('COM read failed'), None, 'INVALID'),
        ):
            with self.subTest(native=native, annotation_text=annotation_text):
                self.setUp()
                self.wire('A1', native)
                self.annotation(text=annotation_text, number=metadata)
                circuit = self.get('circuits', self.result())[0]
                self.assertEqual(self.get('number-status', circuit), Symbol(expected))
                self.assertFalse(truth(self.call('EL:CircuitNumbersReady', [pair('circuits', [circuit])])))

    def test_associated_linenum_can_be_read_when_textstring_unavailable(self):
        self.annotation(text=None, number='ZE1')
        circuit = self.get('circuits', self.result())[0]
        self.assertEqual(self.get('circuit-number', circuit), 'ZE1')
        self.assertEqual(self.get('number-source', circuit), Symbol('PLANE'))
        self.assertEqual(self.get('number-status', circuit), Symbol('READY'))

    def test_missing_owner_does_not_rebind_nearby_wire_or_claim_plane_number(self):
        self.annotation(owner='DEAD', text='ZE9')
        result = self.result()
        circuit = self.get('circuits', result)[0]
        self.assertEqual(self.get('circuit-number', circuit), 'ZE1')
        self.assertEqual(self.get('number-source', circuit), Symbol('AUTO'))
        self.assertEqual(self.text_reads, [])
        event = next(values for name, values in self.events if name == 'CIRCUIT_NUMBER_ANNOTATION_ORPHAN')
        self.assertEqual(self.get('annotation', event), 'B1')
        self.assertEqual(self.get('owner', event), 'DEAD')

    def test_new_deleted_changed_and_reassigned_annotations_invalidate_baseline(self):
        for mutation in ('add', 'delete', 'rename', 'owner', 'raw-owner', 'error'):
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation != 'add':
                    self.annotation()
                baseline = self.result()
                if mutation == 'add': self.annotation()
                elif mutation == 'delete': del self.entities['B1']
                elif mutation == 'rename': self.texts['B1'] = 'ZE9'
                elif mutation == 'owner': self.annotation(owner='A2')
                elif mutation == 'raw-owner': self.annotation(owner='a1')
                elif mutation == 'error': self.fail_scan = True
                self.assertFalse(truth(self.call('EL:NumberInputsCurrent', baseline)))
                # Reprepare cannot replace the reviewed annotation evidence.
                self.assertEqual(self.get('number-inputs', self.call('EL:ResolveCircuitNumbers', baseline)),
                                 self.get('number-inputs', baseline))

    def test_ambiguous_owner_is_explicit_invalid_and_enumeration_order_is_stable(self):
        self.annotation()
        self.annotation('B2', 'A1', 'ZE1')
        baseline = self.result()
        self.entities = dict(reversed(list(self.entities.items())))
        self.assertTrue(truth(self.call('EL:NumberInputsCurrent', baseline)))
        self.entities['B1'][-1][-1].append(Pair(1005, 'A2'))
        self.assertFalse(truth(self.call('EL:NumberInputsCurrent', baseline)))
        self.assertFalse(truth(self.call('EL:CircuitNumbersReady', self.result())))

    def test_source_read_failure_and_bad_annotation_metadata_remain_explicit(self):
        self.annotation()
        self.entities['B1'][-1][-1].append(Pair(1070, 7))
        result = self.result()
        self.assertEqual(self.get('number-status', self.get('circuits', result)[0]), Symbol('INVALID'))
        del self.entities['A1']
        result = self.result()
        self.assertEqual(self.get('number-status', self.get('circuits', result)[0]), Symbol('INVALID'))

    def test_smallest_free_slot_preserves_native_custom_numbers_identity_and_power(self):
        for handle, text in [('A1', 'ZE2'), ('A2', 'ZE3'), ('A3', 'ZE4'), ('A4', None)]:
            self.wire(handle, text)
        result = self.result(('A1', 'A2', 'A3', 'A4'))
        result = self.call('EL:SortCircuitNumbers', result)
        circuits = self.get('circuits', result)
        self.assertEqual([self.get('circuit-number', c) for c in circuits], ['ZE1', 'ZE2', 'ZE3', 'ZE4'])
        self.assertEqual([self.get('circuit-uid', c) for c in circuits], ['uid4', 'uid1', 'uid2', 'uid3'])
        self.assertEqual([self.get('watts', c) for c in circuits], [28, 7, 14, 21])

    def test_annotation_evidence_survives_draft_and_formal_xrecord_roundtrip(self):
        self.annotation()
        result = self.result()
        record = [pair('diagram-id', 'number-evidence'), pair('user-setting', 'keep')]
        draft = self.call('EL:RecordNumberInputs', record, result, True)
        self.assertEqual(self.get('draft-number-inputs', draft), self.get('number-inputs', result))
        formal = self.call('EL:RecordNumberInputs', draft, result, None)
        self.assertEqual(self.get('user-setting', formal), 'keep')
        self.assertEqual(self.get('number-inputs', formal), self.get('number-inputs', result))
        fixture = store_tests.StoreTests()
        fixture.setUp()
        def call(name, *args):
            return fixture.h.call(Symbol(name.upper()), list(args))
        for saved in (draft, formal):
            store = call('EL:Put', Symbol('DIAGRAMS'), [saved], call('EL:StoreInitial'))
            self.assertTrue(truth(call('EL:StoreWrite', store)))
            restored = call('EL:StoreRead')
            self.assertEqual(call('EL:Get', Symbol('DIAGRAMS'), restored), [saved])

    def test_original_dxf_orphan_evidence_does_not_assert_current_dwg_link(self):
        fixture = json.loads((ROOT / 'tests/fixtures/commercial-number-owner-170.json').read_text(encoding='utf-8'))
        rows = fixture['entities']
        self.assertIn([1005, '13415'], rows['2227C'])
        self.assertIn('13415', fixture['missing_handles'])
        self.assertIn('24A49', fixture['missing_handles'])
        self.assertFalse(any(code >= 1000 for code, value in rows['23867']))
        for annotation, owner in [('2227D', '1346F'), ('2227E', '13417'), ('2227F', '1341D')]:
            self.assertIn([1005, owner], rows[annotation])
        self.assertEqual(len(fixture['sha256']), 64)


if __name__ == '__main__':
    unittest.main()
