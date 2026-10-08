"""CAD record boundary checks with entget-shaped data. Date: 2026-10-08.

Runs source geometry and topology, with database calls replaced by fixtures.
These checks are not real AutoCAD acceptance.
"""
import pathlib
import unittest

from autolisp_host import Host, Pair, Symbol, equal, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CadAdapterTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'config', 'geometry', 'topology'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        self.entities = {}
        self.blocks = {}
        self.next_entity = {}
        self.selected = []
        self.h.frames[0][':VLAX-TRUE'] = -1
        self.h.builtins.update({
            'ENTGET': lambda entity: self.entities[entity],
            'TBLSEARCH': lambda table, name: self.blocks.get(name) if table == 'BLOCK' else [Pair(2, name)],
            'ENTNEXT': lambda entity: self.next_entity.get(entity),
            'TRANS': lambda point, *args: point,
            'SSGET': lambda *args: self.selected or None,
            'SSLENGTH': len,
            'SSNAME': lambda ss, index: ss[index],
            'VLAX-ENAME->VLA-OBJECT': lambda entity: entity,
            'VLAX-PROPERTY-AVAILABLE-P': lambda *args: None,
            'VLA-GET-ISDYNAMICBLOCK': lambda entity: 0,
            'EL:DRAWINGID': lambda: 'adapter-fixture.dwg',
        })
        self.h.run('''
          (setq cfg (EL:DefaultConfig "adapter-fixture.dwg"))
          (setq cfg (EL:Put 'params (EL:SuggestedParams) cfg))
          (setq cfg (EL:Put 'panel-layers '("P") cfg))
          (setq cfg (EL:Put 'panel-names '("BOX") cfg))
          (setq cfg (EL:Put 'device-layers '("D") cfg))
          (setq cfg (EL:Put 'device-names '("LAMP") cfg))
          (setq cfg (EL:Put 'wire-layers '("W") cfg))''')

    def call(self, function, *args):
        return self.h.call(Symbol(function.upper()), list(args))

    def get(self, key, record):
        return self.call('EL:Get', Symbol(key.upper()), record)

    def line(self, name, a, b, layer='0', visibility=None):
        # Like Autodesk's entget LINE example: optional code 60 is absent.
        self.entities[name] = [Pair(0, 'LINE'), Pair(5, name), Pair(8, layer),
                               Pair(10, a), Pair(11, b), Pair(210, [0.0, 0.0, 1.0]), Pair(410, 'Model')]
        if visibility is not None:
            self.entities[name].append(Pair(60, visibility))

    def block(self, name, layer, handle, position, visibility=None):
        self.entities[handle] = [Pair(0, 'INSERT'), Pair(5, handle), Pair(8, layer),
                                 Pair(2, name), Pair(10, position), Pair(410, 'Model')]
        corners = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)]
        children = [f'{name}-edge-{i}' for i in range(4)]
        self.blocks[name] = [Pair(2, name), Pair(10, [0.0, 0.0, 0.0]), Pair(70, 0), Pair(-2, children[0])]
        for i, child in enumerate(children):
            self.line(child, list(corners[i]), list(corners[(i+1) % 4]), visibility=visibility)
            self.next_entity[child] = children[i+1] if i < 3 else f'{name}-end'
        self.entities[f'{name}-end'] = [Pair(0, 'ENDBLK')]
        return handle

    def contour(self, handle):
        return self.call('EL:BlockContour', handle, [1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0], 0.1, None)

    def test_host_rejects_nil_numeric_comparison_but_equal_can_test_absence(self):
        with self.assertRaisesRegex(TypeError, 'numberp: nil'):
            self.h.run('(= nil 1)')
        self.assertFalse(truth(self.h.run('(equal nil 1)')))

    def test_visible_block_without_optional_visibility_code_has_contour(self):
        handle = self.block('BOX', 'P', 'panel', [10.0, 20.0, 0.0])
        result = self.contour(handle)
        self.assertEqual(len(self.get('segments', result)), 4)
        self.assertIsNone(self.get('issues', result))
        self.assertEqual(self.get('segments', result)[0][0], [9.0, 21.0, 0.0])

    def test_explicit_visible_block_has_same_contour(self):
        handle = self.block('BOX', 'P', 'panel', [10.0, 20.0, 0.0])
        implicit = self.contour(handle)
        self.block('BOX', 'P', 'panel', [10.0, 20.0, 0.0], visibility=0)
        self.assertTrue(equal(self.contour(handle), implicit))

    def test_invisible_geometry_is_excluded(self):
        handle = self.block('BOX', 'P', 'panel', [10.0, 20.0, 0.0], visibility=1)
        result = self.contour(handle)
        self.assertIsNone(self.get('segments', result))
        self.assertIn(Symbol('EMPTY_CONTOUR'), [self.get('code', issue) for issue in self.get('issues', result)])

    def test_two_command_shared_snapshot_and_topology_accept_ordinary_blocks(self):
        panel = self.block('BOX', 'P', 'panel', [0.0, 0.0, 0.0])
        lamp = self.block('LAMP', 'D', 'lamp', [12.0, 0.0, 0.0])
        self.line('wire', [1.0, 0.0, 0.0], [11.0, 0.0, 0.0], layer='W')
        self.selected = [panel, lamp, 'wire']
        cfg = self.h.lookup('CFG')
        snapshot = self.call('EL:CollectEndpointSnapshot', cfg)
        self.assertEqual(len(self.get('blocks', snapshot)), 2)
        self.assertEqual(len(self.get('wires', snapshot)), 1)
        self.assertEqual(len(self.get('ends', snapshot)), 2)
        self.assertIsNone(self.get('issues', snapshot))
        preview = self.call('EL:BuildPhysical', snapshot, cfg, None)
        self.call('EL:FindGapCandidates', self.get('snapshot', preview), cfg)
        physical = self.call('EL:BuildPhysical', snapshot, cfg, panel)
        seeds = self.call('EL:SeedCandidates', self.get('snapshot', physical), cfg, panel)
        self.assertEqual(len(seeds), 1)
        result = self.call('EL:AnalyzeSnapshot', snapshot, cfg, panel, seeds)
        self.assertEqual(self.get('devices', self.get('circuits', result)[0]), ['lamp'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
