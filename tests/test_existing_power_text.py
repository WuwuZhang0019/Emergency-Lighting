"""Existing power text adapters; not native CAD acceptance. Date: 2026-10-13."""
import copy
import math
from pathlib import Path
import unittest

from autolisp_host import Host, Pair, Symbol, entity_data, truth

ROOT = Path(__file__).resolve().parents[1]


def field(data, key):
    return next((p.cdr for p in data or [] if isinstance(p, Pair) and p.car == key), None)


def replace(data, key, value):
    return [Pair(key, value) if isinstance(p, Pair) and p.car == key else p for p in data]


class ExistingPowerTextTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'diagram-update', 'existing-power-text'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        self.entities = {
            'MODEL': [Pair(0, 'BLOCK_RECORD'), Pair(2, '*Model_Space')],
            'DEFINITION': [Pair(0, 'BLOCK_RECORD'), Pair(2, 'BOX')],
        }
        self.layers = {'NORMAL': [Pair(70, 0), Pair(62, 7)]}
        self.blocks = {'BOX': [Pair(70, 2)]}
        self.next = {}
        self.writes = []
        self.refreshes = []
        self.fields = {}
        self.h.builtins.update({
            'ENTGET': lambda e, apps=None: copy.deepcopy(entity_data(self.entities.get(e), apps)),
            'HANDENT': lambda e: e if e in self.entities else None,
            'TBLSEARCH': lambda table, name: (self.layers if table == 'LAYER' else self.blocks).get(name),
            'NAMEDOBJDICT': lambda: 'NOD',
            'DICTSEARCH': lambda dictionary, key: self.fields.get((dictionary, key)),
            'TRANS': lambda point, source, target, displacement=None: copy.deepcopy(point),
            'ENTNEXT': lambda e: self.next.get(e),
            'ENTMOD': self.modify,
            'ENTUPD': lambda e: self.refreshes.append(e) or e,
            'GETVAR': lambda name: 1 if name == 'LISPSYS' else None,
            'EL:LOGEVENT': lambda *args: None,
        })
        self.h.frames[0]['*EL:TRANSACTIONOPEN*'] = True

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, value):
        return self.call('EL:Get', Symbol(key.upper()), value)

    def modify(self, data):
        entity = field(data, -1)
        self.writes.append(entity)
        self.entities[entity] = copy.deepcopy(data)
        return data

    def insert(self, name='box'):
        self.entities[name] = [Pair(-1, name), Pair(0, 'INSERT'), Pair(5, name),
            Pair(330, 'MODEL'), Pair(410, 'Model'), Pair(8, 'NORMAL'), Pair(2, 'BOX'),
            Pair(66, 1), Pair(10, [100., 200., 0.])]
        return name

    def text(self, text='40W', entity='text', kind='TEXT', owner='MODEL'):
        data = [Pair(-1, entity), Pair(0, kind), Pair(5, entity), Pair(330, owner),
            Pair(100, 'AcDbEntity'), Pair(410, 'Model'), Pair(8, 'NORMAL'),
            Pair(100, 'AcDbMText' if kind == 'MTEXT' else 'AcDbText'),
            Pair(10, [10., 20., 0.]), Pair(40, 350.), Pair(50, .2), Pair(1, text),
            Pair(7, '宋体'), Pair(62, 256), [-3, ['CUSTOM', Pair(1000, 'unchanged')]]]
        if kind == 'ATTRIB':
            data.extend([Pair(100, 'AcDbAttribute'), Pair(2, 'POWER'), Pair(70, 0), Pair(74, 0)])
        self.entities[entity] = data
        return entity

    def read(self, entity='text'):
        return self.call('EL:PowerTextRead', entity)

    def replacement(self, ref, watts=44, bare=None):
        return self.call('EL:PowerTextReplacement', ref, watts, bare)

    def raw(self, data):
        return self.call('EL:PowerTextRaw', data)

    def test_read_preserves_full_data_and_reports_wcs_anchor(self):
        self.text('85W')
        self.entities['text'] = [Pair(102, '{ACAD_REACTORS'), Pair(330, 'DEFINITION'), Pair(102, '}')] + self.entities['text']
        self.entities['text'].extend([Pair(72, 1), Pair(11, [30., 40., 0.])])
        calls = []
        def trans(point, source, target, displacement=None):
            calls.append((point, displacement))
            return point if displacement else [point[0] + 100, point[1] + 200, point[2]]
        self.h.builtins['TRANS'] = trans
        ref = self.read()
        self.assertEqual(self.get('data', ref), entity_data(self.entities['text'], ['*']))
        self.assertEqual(self.get('point', ref), [130., 240., 0.])
        self.assertAlmostEqual(self.get('angle', ref), .2)
        self.assertEqual(self.get('visible', ref), '85W')
        self.assertEqual(self.get('height', ref), 350.)
        self.assertIsNone(self.get('owner', ref))
        self.assertEqual(len(calls), 2)

    def test_modelspace_visibility_and_lock_gate_excludes_shared_definitions(self):
        for key, value in ((330, 'DEFINITION'), (410, 'Layout1'), (67, 1), (60, 1)):
            with self.subTest(key=key):
                self.text()
                if field(self.entities['text'], key) is None:
                    self.entities['text'].append(Pair(key, value))
                else:
                    self.entities['text'] = replace(self.entities['text'], key, value)
                self.assertIsNone(self.read())
        for flags, color in ((4, 7), (1, 7), (0, -7)):
            self.text()
            self.layers['NORMAL'] = [Pair(70, flags), Pair(62, color)]
            self.assertIsNone(self.read())
        self.layers['NORMAL'] = [Pair(70, 0), Pair(62, 7)]
        self.text(kind='ATTDEF')
        self.assertIsNone(self.read())

    def test_attribute_uses_instance_owner_and_only_invisible_flag(self):
        self.insert()
        self.text(kind='ATTRIB', owner='box')
        for flags in (0, 2, 4, 8, 14):
            self.entities['text'] = replace(self.entities['text'], 70, flags)
            ref = self.read()
            self.assertEqual(self.get('owner', ref), 'box')
            self.assertEqual(self.get('parent-data', ref), self.entities['box'])
        self.entities['text'] = replace(self.entities['text'], 70, 1)
        self.assertIsNone(self.read())
        self.entities['text'] = replace(self.entities['text'], 70, 0)
        for flags in (4, 8, 16):
            self.blocks['BOX'] = [Pair(70, flags)]
            self.assertIsNone(self.read())
        self.blocks['BOX'] = [Pair(70, 2)]
        self.entities['box'] = replace(self.entities['box'], 330, 'DEFINITION')
        self.assertIsNone(self.read())

    def test_field_and_multiline_attribute_are_not_write_candidates(self):
        for raw in ('%<\\AcExpr (4)>% W', '44W %<object>%'):
            self.text(raw)
            self.assertIsNone(self.read())
        self.text()
        self.entities['text'].extend([Pair(102, '{ACAD_XDICTIONARY'), Pair(360, 'DICT'), Pair(102, '}')])
        self.fields['DICT', 'ACAD_FIELD'] = [Pair(0, 'DICTIONARY')]
        self.assertIsNone(self.read())
        self.insert()
        self.text(kind='ATTRIB', owner='box')
        self.entities['text'].append(Pair(101, 'Embedded Object'))
        self.assertIsNone(self.read())

    def test_collect_includes_instance_attributes_and_deduplicates(self):
        self.insert()
        self.text('ZE1', 'number', 'ATTRIB', 'box')
        self.text('40W', 'power', 'ATTRIB', 'box')
        self.text('30W', 'standalone', 'MTEXT')
        self.entities['seqend'] = [Pair(0, 'SEQEND')]
        self.next.update({'box': 'number', 'number': 'power', 'power': 'seqend'})
        refs = self.call('EL:PowerTextCollect', ['box', 'power', 'standalone', 'box'])
        self.assertEqual([self.get('handle', r) for r in refs], ['number', 'power', 'standalone'])

    def test_replacement_changes_only_power_digits(self):
        for before, after in (('功率 40 W', '功率 44 W'), ('P=0.05 kW/备用', 'P=0.044 kW/备用'),
                              ('P=0.050Kw；回路2', 'P=0.044Kw；回路2'), ('+40w', '44w')):
            with self.subTest(before=before):
                self.text(before)
                ref = self.read()
                # A compound W/... unit is deliberately unsupported.
                if before.endswith('/备用'):
                    self.assertIsNone(self.replacement(ref))
                    continue
                expected = replace(self.entities['text'], 1, after)
                self.assertEqual(self.replacement(ref), expected)
        self.text('0.05 kW')
        self.assertEqual(self.raw(self.replacement(self.read(), 0)), '0 kW')

    def test_bare_numbers_require_explicit_mode_and_ambiguous_units_fail(self):
        self.text(' 40 ')
        self.assertIsNone(self.replacement(self.read()))
        self.assertEqual(self.raw(self.replacement(self.read(), bare=True)), ' 44 ')
        for value in ('10W + 20W', '1,000W', '1e3W', 'ABC10W', '2kWh', '2MW', '2W/m',
                      '2W /m2', '2kW\t / m2', '1..2W'):
            self.text(value)
            self.assertIsNone(self.replacement(self.read()), value)

    def test_mtext_formatting_and_chunked_content_survive(self):
        raw = '{\\f宋体|b0|i0;\\C3;功率：0.05\\H0.8x;kW} '
        self.text(raw, kind='MTEXT')
        self.entities['text'].append(Pair(11, [0., 1., 0.]))
        ref = self.read()
        self.assertEqual(self.get('visible', ref), '功率：0.05kW ')
        self.assertAlmostEqual(self.get('angle', ref), math.pi / 2)
        self.assertEqual(self.raw(self.replacement(ref)), raw.replace('0.05', '0.044'))
        raw = '中' * 249 + '40W' + '尾' * 270
        self.text('', kind='MTEXT')
        self.entities['text'] = self.call('EL:PowerTextData', self.entities['text'], raw)
        result = self.replacement(self.read())
        self.assertEqual(self.raw(result), raw.replace('40W', '44W'))
        self.assertTrue(all(len(p.cdr) <= 250 for p in result if isinstance(p, Pair) and p.car in (1, 3)))

    def test_complex_mtext_and_control_inside_digits_are_rejected(self):
        for raw in ('{40W', '\\S40/50;W', '\\U+0034W', '\\zfoo;40W'):
            self.text(raw, kind='MTEXT')
            self.assertIsNone(self.read(), raw)
        self.text('4\\C3;0W', kind='MTEXT')
        self.assertTrue(self.read())
        self.assertIsNone(self.replacement(self.read()))

    def test_watts_format_is_exact_for_current_integral_statistics(self):
        self.text('40W')
        for watts, expected in ((0, '0W'), (44.0, '44W'), (2147483647, '2147483647W')):
            self.assertEqual(self.raw(self.replacement(self.read(), watts)), expected)
        for watts in (-1, 0.25, 2147483648, '44'):
            self.assertIsNone(self.replacement(self.read(), watts))
        self.text('0kW')
        self.assertEqual(self.raw(self.replacement(self.read(), 1001)), '1.001kW')

    def test_write_requires_transaction_and_exact_unchanged_target(self):
        self.text()
        ref = self.read()
        after = self.replacement(ref)
        self.h.frames[0]['*EL:TRANSACTIONOPEN*'] = None
        with self.assertRaises(RuntimeError):
            self.call('EL:PowerTextWrite', ref, after)
        self.h.frames[0]['*EL:TRANSACTIONOPEN*'] = True
        self.entities['text'] = replace(self.entities['text'], 1, '41W')
        with self.assertRaises(RuntimeError):
            self.call('EL:PowerTextWrite', ref, after)
        self.assertEqual(self.writes, [])

    def test_write_rejects_extra_changes_and_verifies_actual_readback(self):
        self.text()
        ref = self.read()
        after = self.replacement(ref)
        for changed in (replace(after, 7, 'other-style'), replace(after, 1, '44kW')):
            with self.assertRaises(RuntimeError):
                self.call('EL:PowerTextWrite', ref, changed)
        self.assertEqual(self.writes, [])
        def corrupted(data):
            self.modify(replace(data, 40, 99.))
            return data
        self.h.builtins['ENTMOD'] = corrupted
        with self.assertRaises(RuntimeError):
            self.call('EL:PowerTextWrite', ref, after)
        self.assertEqual(self.writes, ['text'])  # The enclosing transaction owns rollback.

    def test_attribute_refreshes_owner_and_parent_change_blocks_write(self):
        self.insert()
        self.text(kind='ATTRIB', owner='box')
        ref = self.read()
        self.assertTrue(truth(self.call('EL:PowerTextWrite', ref, self.replacement(ref))))
        self.assertEqual(self.refreshes, ['box'])
        ref = self.read()
        self.entities['box'] = replace(self.entities['box'], 10, [1000., 2000., 0.])
        with self.assertRaises(RuntimeError):
            self.call('EL:PowerTextWrite', ref, self.replacement(ref, 50))
        self.assertEqual(self.writes, ['text'])

    def test_noop_skips_writes_and_native_derived_alignment_change_is_allowed(self):
        self.text('44W')
        ref = self.read()
        self.assertTrue(truth(self.call('EL:PowerTextWrite', ref, self.replacement(ref))))
        self.assertEqual(self.writes, [])
        self.entities['text'].extend([Pair(72, 1), Pair(11, [30., 40., 0.])])
        ref = self.read()
        def aligned(data):
            self.modify(replace(data, 10, [25., 40., 0.]))
            return data
        self.h.builtins['ENTMOD'] = aligned
        self.assertTrue(truth(self.call('EL:PowerTextWrite', ref, self.replacement(ref, 100))))
        self.assertEqual(field(self.entities['text'], 11), [30., 40., 0.])

    def test_batch_recheck_catches_later_change_to_previously_written_item(self):
        self.text()
        ref = self.read()
        after = self.replacement(ref)
        self.assertTrue(truth(self.call('EL:PowerTextWrite', ref, after)))
        self.assertTrue(truth(self.call('EL:PowerTextWrittenP', ref, after)))
        self.entities['text'] = replace(self.entities['text'], 1, '999W')
        self.assertFalse(truth(self.call('EL:PowerTextWrittenP', ref, after)))
        self.assertFalse(truth(self.call('EL:PowerTextLocalInsertP', None)))


if __name__ == '__main__':
    unittest.main()
