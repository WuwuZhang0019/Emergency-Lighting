"""Date: 2026-10-22. Status: cross-computer Tianzheng name regression; CAD pending."""
import copy
import unittest
from autolisp_host import Pair, Symbol, truth
import test_device_library as backend
import test_lamp_line_arms as arms

LOCAL = arms.NAME
REMOTE = '$equip_U$00000309(longys)'
CORE = '$EQUIP_U$00000309'


class TianzhengNameTests(unittest.TestCase):
    setUp = backend.DeviceLibraryTests.setUp
    call = backend.DeviceLibraryTests.call
    get = backend.DeviceLibraryTests.get
    put = backend.DeviceLibraryTests.put
    entry = backend.DeviceLibraryTests.entry
    add = backend.DeviceLibraryTests.add

    def snapshot(self):
        return [Pair(Symbol('ROOT'), 'library/'), Pair(Symbol('CATALOG'), self.cat),
                Pair(Symbol('INDEX'), self.call('EL:DLIndex', self.cat))]

    def result(self, names):
        blocks = [[Pair(Symbol('ID'), f'D{i}'), Pair(Symbol('NAME'), name), Pair(Symbol('ROLE'), Symbol('DEVICE')),
                   Pair(Symbol('IDENTITY'), [name, None, 'block-name-v1'])]
                  for i, name in enumerate(names)]
        result = self.h.run("""'((engine . fixed) (complete . T) (panel . "P")
          (circuits ((id . "C1") (complete . T) (ground-source . default))))""")
        result = self.put('snapshot', [Pair(Symbol('BLOCKS'), blocks),
                          Pair(Symbol('SIGNATURE'), 'original-source')], result)
        circuit = self.put('devices', [f'D{i}' for i in range(len(names))], self.get('circuits', result)[0])
        return self.put('circuits', [circuit], result)

    def test_library_matches_other_computer_without_changing_saved_names(self):
        row = self.add(self.entry(LOCAL, watts=5))
        before = copy.deepcopy(self.cat)
        for name in (REMOTE, CORE, '$equip_U$00000309(another-PC)', '$equip_U$00000309（另一台电脑）'):
            with self.subTest(name=name):
                found = self.call('EL:DLPowerEntry', name, self.snapshot())
                self.assertEqual(self.get('device-id', found), self.get('device-id', row))
                self.assertEqual(self.get('watts', found), 5)
                self.assertEqual(self.get('block-name', found), LOCAL)
        self.assertEqual(self.cat, before)
        self.assertEqual(self.call('EL:DLNameKey', REMOTE), REMOTE.upper())

    def test_suffix_rule_preserves_different_types_and_meaningful_ordinary_parentheses(self):
        self.add(self.entry(LOCAL))
        self.add(self.entry('Lamp(10W)', watts=10))
        for name in ('$equip_U$00000316(longys)', '$equip$00000309(longys)',
                     '$equip_U$00000309(longys)-copy', '$equip_U$00000309(a)(b)',
                     '$equip_U$00000309()', 'Lamp(20W)', 'Lamp', ' ' + REMOTE):
            with self.subTest(name=name):
                self.assertIsNone(self.call('EL:DLPowerEntry', name, self.snapshot()))
        self.assertEqual(self.get('watts', self.call('EL:DLPowerEntry', 'lamp(10w)', self.snapshot())), 10)
        self.add(self.entry('$equip$00000690(Zhangyufeng)'))
        self.assertTrue(truth(self.call('EL:DLPowerEntry', '$equip$00000690(longys)', self.snapshot())))

    def test_exact_match_wins_and_ambiguous_other_computer_does_not_guess_power(self):
        events = []
        self.h.builtins['EL:LOGEVENT'] = lambda *args: events.append(args)
        local = self.add(self.entry(LOCAL, watts=5))
        remote = self.add(self.entry(REMOTE, watts=9))
        snap = self.snapshot()
        self.assertEqual(self.call('EL:DLLookup', LOCAL, snap), local)
        self.assertEqual(self.call('EL:DLLookup', REMOTE, snap), remote)
        for name in (CORE, '$equip_U$00000309(third-PC)'):
            self.assertIsNone(self.call('EL:DLPowerEntry', name, snap))
            self.assertIsNone(self.call('EL:DLFindEntry', name, snap))
        self.assertTrue(events)
        self.assertTrue(all(event[0] == 'DEVICE_NAME_SUFFIX_AMBIGUOUS' for event in events))
        self.assertEqual(len(self.get('device-ids', events[0][1])), 2)

    def test_alias_draft_and_deleted_entry_keep_existing_status_rules(self):
        draft = self.put('active', None, self.put('status', Symbol('DRAFT'), self.entry('Custom lamp', watts=7)))
        row = self.add(self.put('aliases', [LOCAL], draft))
        self.assertIsNone(self.call('EL:DLLookup', REMOTE, self.snapshot()))
        self.assertEqual(self.call('EL:DLFindEntry', REMOTE, self.snapshot()), row)
        self.assertEqual(self.get('watts', self.call('EL:DLPowerEntry', REMOTE, self.snapshot())), 7)
        self.cat = self.call('EL:DLDelete', self.cat, self.get('device-id', row))
        self.assertIsNone(self.call('EL:DLPowerEntry', REMOTE, self.snapshot()))
        self.assertIsNone(self.call('EL:DLFindEntry', REMOTE, self.snapshot()))

    def test_exact_draft_or_disabled_entry_does_not_take_another_authors_active_power(self):
        self.add(self.entry(LOCAL, watts=5))
        draft = self.put('active', None, self.put('status', Symbol('DRAFT'), self.entry(REMOTE, watts=8)))
        remote = self.add(draft)
        self.assertEqual(self.call('EL:DLPowerEntry', REMOTE, self.snapshot()), remote)
        remote = self.put('watts', None, remote)
        self.cat = self.call('EL:DLUpsert', self.cat, remote)
        self.assertIsNone(self.call('EL:DLPowerEntry', REMOTE, self.snapshot()))
        self.cat = self.call('EL:DLCatalogInitial', 'LIB-TEST')
        self.add(self.entry(LOCAL, watts=5))
        self.add(self.put('active', None, self.entry(REMOTE, watts=8)))
        self.assertIsNone(self.call('EL:DLPowerEntry', REMOTE, self.snapshot()))

    def test_preset_names_panel_and_junction_match_but_layers_remain_literal(self):
        cfg = self.h.run("""'((preset-scoped . T) (panel-layers "P") (device-layers "D")
          (panel-names "$equip_U$00000398(Zhangyufeng)"))""")
        cfg = self.put('device-names', [LOCAL], cfg)
        for enabled in (None, True):
            self.h.set('*EL:PRESETCACHEENABLED*', enabled)
            self.h.set('*EL:PRESETCACHEREBUILDS*', 0)
            self.h.set('*EL:PRESETCACHEMEMBERHITS*', 0)
            self.h.set('*EL:PRESETCACHEMEMBERMISSES*', 0)
            self.h.set('*EL:PRESETCACHEHITS*', 0)
            self.h.set('*EL:PRESETCACHEMISSES*', 0)
            self.h.set('*EL:PRESETCACHENORMALIZATIONS*', 0)
            for _ in range(2):
                self.assertTrue(truth(self.call('EL:PresetBlockNameAllowed', REMOTE, [Pair(8, 'D')], cfg)))
                self.assertFalse(truth(self.call('EL:PresetBlockNameAllowed', REMOTE, [Pair(8, 'OTHER')], cfg)))
            self.assertEqual(self.call('EL:Role', 'D', REMOTE, cfg), Symbol('DEVICE'))
            self.assertEqual(self.call('EL:Role', 'P', '$equip_U$00000398(longys)', cfg), Symbol('PANEL'))
        cfg = self.put('device-layers', [LOCAL], cfg)
        self.assertFalse(truth(self.call('EL:PresetBlockNameAllowed', REMOTE, [Pair(8, REMOTE)], cfg)))
        cfg = self.call('EL:PutRole', cfg, self.call('EL:FixedBlockIdentity', LOCAL), Symbol('JUNCTION'))
        self.assertTrue(truth(self.call('EL:JunctionName', REMOTE, cfg)))
        self.assertIsNone(self.call('EL:JunctionName', '$equip_U$00000316(longys)', cfg))
        cfg = self.call('EL:PutRole', cfg, self.call('EL:FixedBlockIdentity', REMOTE), Symbol('DEVICE'))
        self.assertIsNone(self.call('EL:JunctionName', REMOTE, cfg))

    def test_mixed_authors_share_library_identity_and_preserve_per_name_manual_power(self):
        self.add(self.entry(LOCAL, watts=5))
        events = []
        self.h.builtins['EL:LOGEVENT'] = lambda *args: events.append(args)
        result = self.result((LOCAL, REMOTE))
        source = copy.deepcopy(self.get('snapshot', result))
        prepared = self.call('EL:DLPrepare', result, None, self.snapshot(), None)
        result, powers = self.get('result', prepared), self.get('powers', prepared)
        computed = self.call('EL:PanelCompute', result, powers, None)
        self.assertEqual(self.get('box-watts', computed), 10)
        suffix = [detail for event, detail in events if event == 'DEVICE_NAME_SUFFIX_MATCH']
        self.assertEqual(len(suffix), 1)
        self.assertEqual(self.get('drawing-name', suffix[0]), REMOTE.upper())
        self.assertEqual(self.get('library-name', suffix[0]), LOCAL)
        self.assertEqual(self.get('device-handles', suffix[0]), ['D1'])
        self.assertIsNone(self.get('library-pending', computed))
        rows = self.call('EL:DLMaterialRows', result, powers)
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.get('count', rows[0]), 2)
        result = self.call('EL:DLSetOverride', result, REMOTE, Symbol('WATTS'), 7)
        result = self.call('EL:DLSetOverride', result, REMOTE, Symbol('WATTS-SET'), True)
        prepared = self.call('EL:DLPrepare', result, powers, self.snapshot(), None)
        result, powers = self.get('result', prepared), self.get('powers', prepared)
        self.assertEqual(self.call('EL:Get', REMOTE.upper(), powers), 7)
        self.assertEqual(self.call('EL:Get', LOCAL.upper(), powers), 5)
        self.assertEqual(self.get('box-watts', self.call('EL:PanelCompute', result, powers, None)), 12)
        self.assertEqual(self.get('snapshot', result), source)
        self.assertTrue(truth(self.call('EL:DLRefsCover', result)))

    def test_default_merge_respects_another_authors_saved_values_and_deleted_entry(self):
        row = self.add(self.entry(REMOTE, watts=11))
        seed = self.entry(LOCAL, watts=5)
        self.assertEqual(self.call('EL:DLDefaultMatch', seed, self.cat), row)
        defaults = self.put('devices', [seed], self.call('EL:DLCatalogInitial', 'DEFAULTS'))
        self.h.builtins['EL:DLDEFAULTASSETSPRESENT'] = lambda *args: True
        merged = self.call('EL:DLDefaultMerge', defaults, 'library/', self.snapshot(), None)
        self.assertEqual(self.get('devices', merged), [row])
        self.cat = self.call('EL:DLDelete', self.cat, self.get('device-id', row))
        deleted = self.get('devices', self.cat)[0]
        self.assertEqual(self.call('EL:DLDefaultMatch', seed, self.cat), deleted)
        self.assertEqual(self.get('watts', deleted), 11)
        merged = self.call('EL:DLDefaultMerge', defaults, 'library/', self.snapshot(), None)
        self.assertEqual(self.get('devices', merged), [deleted])

    def test_other_computers_four_line_tips_reach_lamp_and_load_saved_power(self):
        self.add(self.entry(LOCAL, watts=5))
        for x, y in ((-250., 250.), (250., 250.), (250., -250.), (-250., -250.)):
            with self.subTest(tip=(x, y)):
                f = arms.LampLineArmTests().fixture(x, y)
                f.h.builtins['CHR'] = chr
                f.entities['lamp'] = [Pair(2, REMOTE) if row.car == 2 else row for row in f.entities['lamp']]
                f.blocks[REMOTE] = [Pair(2, REMOTE) if row.car == 2 else row for row in f.blocks[LOCAL]]
                f.cfg = f.call('EL:Put', Symbol('PRESET-SCOPED'), True,
                              f.call('EL:Put', Symbol('DEVICE-NAMES'), [LOCAL], f.cfg))
                result = f.call('EL:RecognizeFixed', f.cfg, 'panel')
                circuits = f.get('circuits', result)
                self.assertEqual([f.get('devices', c) for c in circuits], [['lamp']])
                self.assertTrue(truth(f.get('complete', result)))
                lamp = f.call('EL:By', Symbol('ID'), 'lamp', f.get('blocks', f.get('snapshot', result)))
                self.assertEqual(f.get('name', lamp), REMOTE)
                prepared = f.call('EL:DLPrepare', result, None, self.snapshot(), None)
                computed = f.call('EL:PanelCompute', f.get('result', prepared), f.get('powers', prepared), None)
                self.assertEqual(f.get('box-watts', computed), 5)
                self.assertIsNone(f.get('library-pending', computed))


if __name__ == '__main__':
    unittest.main()
