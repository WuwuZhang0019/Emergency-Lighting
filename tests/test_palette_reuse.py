"""Palette equivalence, call-local layer reads and bounded initialization timing.

Date: 2026-10-21. Status: focused host regression; native CAD acceptance pending.
The oracle retains every repeated source RGB and the previous candidate order.
"""
from pathlib import Path
import unittest

from autolisp_host import Host, Pair, Symbol, truth
import test_panel_library_toggle as layouts


ROOT = Path(__file__).resolve().parents[1]
BASE_COLORS = [4, 2, 5, 30, 190, 140, 40, 180, 150, 160, 31, 41,
               51, 131, 141, 151, 161, 171, 181, 191, 32, 42, 52, 132]


def field(key, data, default=None):
    return next((item.cdr for item in (data or []) if item.car == key), default)


class PaletteReuseTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'panel'):
            self.h.load_definitions(ROOT / 'src' / (name + '.lsp'))
        self.entities, self.layers, self.layer_reads = {}, {}, []
        self.h.builtins.update({
            'HANDENT': lambda key: key if key in self.entities else None,
            'ENTGET': lambda key: self.entities.get(key),
            'TBLSEARCH': self.table,
            'GETVAR': lambda key: 0 if key == 'MILLISECS' else 20261021.12,
        })

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def table(self, kind, name):
        self.assertEqual(kind, 'LAYER')
        self.layer_reads.append(name)
        return self.layers.get(name.upper() if name else None)

    def entity(self, identity, layer='wire', aci=None, rgb=None):
        data = [Pair(0, 'LINE'), Pair(5, identity), Pair(8, layer)]
        if aci is not None:
            data.append(Pair(62, aci))
        if rgb is not None:
            data.append(Pair(420, rgb))
        self.entities[identity] = data

    def result(self, ids, source_ids=None, fallback=False):
        if fallback:
            return [Pair(Symbol('CIRCUITS'),
                         [[Pair(Symbol('WIRES'), ids[:2])],
                          [Pair(Symbol('WIRES'), ids[2:])]])]
        wires = []
        for index, identity in enumerate(ids):
            wire = [Pair(Symbol('ID'), identity)]
            if source_ids is not None:
                wire.append(Pair(Symbol('SOURCE-WIRE'), source_ids[index]))
            wires.append(wire)
        return [Pair(Symbol('SNAPSHOT'), [Pair(Symbol('WIRES'), wires)])]

    def legacy_rgb(self, identity):
        """Prior uncached entity/layer selection, independent of the new helpers."""
        data = self.entities.get(identity)
        if not data:
            return None
        color = field(62, data, 256)
        if field(420, data) is None and color == 256:
            layer = field(8, data)
            data = self.layers.get(layer.upper() if layer else None)
        rgb = field(420, data)
        if rgb is not None:
            return [(rgb // 65536) & 255, (rgb // 256) & 255, rgb & 255]
        return self.call('EL:ACIColorRGB', abs(field(62, data, 7)))

    def legacy_palette(self, identities):
        # Keep repeats, including two handles with identical RGB: no RGB set/cache.
        colors = [rgb for identity in dict.fromkeys(identities)
                  if (rgb := self.legacy_rgb(identity)) is not None]
        palette, used = [], []
        for candidate in BASE_COLORS + list(range(30, 60)) + list(range(130, 200)):
            rgb = self.call('EL:ACIColorRGB', candidate)
            if rgb not in used and not any(sum((a-b)**2 for a, b in zip(rgb, source)) < 10000
                                          for source in colors):
                palette.append(candidate)
                used.append(rgb)
        return palette

    def metric(self, key):
        return self.call('EL:Get', key, self.h.lookup('*EL:PERFMETRICS*'))

    def test_mixed_sources_keep_exact_legacy_palette_and_source_colors(self):
        self.layers.update({'WIRE': [Pair(62, -30)],
                            'TRUE': [Pair(62, 1), Pair(420, 0x00FFFF)]})
        cases = [('aci', 'wire', 5, None), ('negative', 'wire', -30, None),
                 ('true', 'wire', 1, 0x00FFFF), ('true-zero', 'wire', 256, 0),
                 ('layer', 'wire', 256, None), ('layer-default', 'WIRE', None, None),
                 ('true-layer', 'true', 256, None), ('byblock', 'wire', 0, None),
                 ('missing-layer', 'absent', None, None), ('white', 'wire', 7, None)]
        for case in cases:
            self.entity(*case)
        ids = [case[0] for case in cases] + ['deleted', 'layer', 'true']
        expected = self.legacy_palette(ids)
        self.assertEqual(self.call('EL:PreviewPalette', self.result(ids)), expected)
        for identity in ids:
            self.assertEqual(self.call('EL:PreviewEntityRGB', identity), self.legacy_rgb(identity))

    def test_rgb_duplicates_and_layer_reads_are_counted_once_per_batch(self):
        self.layers['WIRE'] = [Pair(62, 4)]
        for index in range(24):
            self.entity(str(index), 'wire' if index % 2 else 'WIRE', 256)
        self.entity('same-true', rgb=0x00FFFF)
        ids = [str(index) for index in range(24)] + ['same-true', 'deleted', '0']
        self.call('EL:PerfStart', 'ELSTAT')
        self.assertEqual(self.call('EL:PreviewPalette', self.result(ids)), self.legacy_palette(ids))
        self.assertEqual([name.upper() for name in self.layer_reads], ['WIRE'])
        self.assertEqual(self.metric('preview-source-ids'), 26)
        self.assertEqual(self.metric('preview-source-color-reads'), 25)
        self.assertEqual(self.metric('preview-source-rgb-duplicates'), 24)
        self.assertEqual(self.metric('preview-source-rgb-unique'), 1)
        self.assertEqual(self.metric('preview-layer-color-reads'), 1)
        self.assertEqual(self.metric('preview-layer-color-cache-hits'), 23)
        rows = self.h.lookup('*EL:MONITORROWS*')
        self.assertEqual(len(rows), 2, 'one row per batch, never per entity')
        self.assertFalse(truth(self.h.lookup('*EL:PREVIEWLAYERCACHEENABLED*')))
        self.assertFalse(truth(self.h.lookup('*EL:PREVIEWLAYERCACHE*')))

    def test_missing_layer_is_cached_without_changing_white_fallback(self):
        for identity in ('a', 'b', 'c'):
            self.entity(identity, 'absent', 256)
        self.assertEqual(self.call('EL:PreviewPalette', self.result(['a', 'b', 'c'])),
                         self.legacy_palette(['a', 'b', 'c']))
        self.assertEqual(self.layer_reads, ['absent'])
        self.assertEqual(self.call('EL:PreviewEntityRGB', 'a'), [255, 255, 255])
        self.assertEqual(self.layer_reads, ['absent', 'absent'])

    def test_standalone_reads_remain_fresh_before_and_after_palette(self):
        self.entity('a', aci=256)
        self.layers['WIRE'] = [Pair(62, 4)]
        self.assertEqual(self.call('EL:PreviewEntityRGB', 'a'), [0, 255, 255])
        self.call('EL:PreviewPalette', self.result(['a']))
        self.layers['WIRE'] = [Pair(420, 0xFFAA00)]
        self.assertEqual(self.call('EL:PreviewEntityRGB', 'a'), [255, 170, 0])
        self.assertEqual(self.layer_reads, ['wire', 'wire', 'wire'])

    def test_next_call_observes_layer_changes_and_same_handles_in_other_drawing(self):
        self.entity('a', aci=256)
        self.layers['WIRE'] = [Pair(62, 4)]
        result = self.result(['a'])
        before = self.call('EL:PreviewPalette', result)
        self.layers['WIRE'] = [Pair(62, 5)]
        after = self.call('EL:PreviewPalette', result)
        self.assertNotEqual(before, after)
        self.assertEqual(after, self.legacy_palette(['a']))
        # A new DWG can reuse both handle and layer name with different facts.
        self.entities = {'a': [Pair(8, 'wire'), Pair(62, 256)]}
        self.layers = {'WIRE': [Pair(420, 0xFFAA00)]}
        self.assertEqual(self.call('EL:PreviewPalette', result), self.legacy_palette(['a']))
        self.assertEqual(len(self.layer_reads), 3)

    def test_fallback_circuits_and_virtual_wire_handles_keep_legacy_selection(self):
        self.entity('a', aci=4)
        self.entity('b', aci=5)
        self.entity('unrecognized', aci=30)
        for result, ids in ((self.result(['a', 'b', 'a'], fallback=True), ['a', 'b', 'a']),
                            (self.result(['piece1', 'piece2', 'unrecognized'],
                                         ['a', 'a', 'unrecognized']), ['a', 'a', 'unrecognized'])):
            self.assertEqual(self.call('EL:PreviewPalette', result), self.legacy_palette(ids))

    def test_empty_result_keeps_original_candidate_order(self):
        self.assertEqual(self.call('EL:PreviewPalette', None), self.legacy_palette([]))

    def test_panel_initialization_batches_keep_real_dialog_and_exclude_input_wait(self):
        f, callbacks, _, _ = layouts.PanelLibraryToggleTests.fixture(self, False)
        self.addCleanup(f.doCleanups)
        self.h = f.h
        clock = [0]
        getvar = self.h.builtins['GETVAR']
        self.h.builtins['GETVAR'] = lambda key: clock[0] if key == 'MILLISECS' else getvar(key)
        costs = {'EL:SELECTFIXEDEXITS': 11, 'EL:PANELCOMPUTE': 17,
                 'EL:PREVIEWPALETTECOLORS': 13, 'EL:PREVIEWPALETTECHOICES': 19}
        for name, cost in costs.items():
            alias = Symbol('TEST:' + name[3:])
            self.h.functions[alias] = self.h.functions[Symbol(name)]

            def measured(*args, alias=alias, cost=cost):
                clock[0] += cost
                return self.call(alias, *args)

            self.h.builtins[name] = measured

        def cancel():
            clock[0] += 101
            f.invoke_action(callbacks, 'cancel')

        f.actions = [cancel]
        self.call('EL:PerfStart', 'ELSTAT')
        self.assertIsNone(f.dialog())
        self.assertEqual(f.dialogs, ['el_panel_compact'])
        for name, cost in (('PANEL_SELECT_EXITS', 11), ('PANEL_COMPUTE', 17),
                           ('PREVIEW_SOURCE_COLORS', 13), ('PREVIEW_PALETTE_FILTER', 19),
                           ('PANEL_PREVIEW_PALETTE', 32)):
            stage = self.call('EL:Get', name, self.h.lookup('*EL:PERFSTAGES*'))
            self.assertEqual(self.call('EL:Get', Symbol('CALLS'), stage), 1, name)
            self.assertEqual(self.call('EL:Get', Symbol('INCLUSIVE-MS'), stage), cost, name)
        self.assertEqual(self.call('EL:PerfWaiting'), 101)
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))


if __name__ == '__main__':
    unittest.main()
