"""Actual-width contact and supplied rounded ELD replay. Date: 2026-10-11."""
import json
from pathlib import Path
import unittest
from autolisp_host import Pair, Symbol, truth
import test_simple_flow as simple


class WireWidthTests(unittest.TestCase):
    setUp = simple.SimpleFlowTests.setUp
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    line = simple.SimpleFlowTests.line
    block = simple.SimpleFlowTests.block
    network = simple.SimpleFlowTests.network

    def wire(self, points, width=50., widths=None, bulges=None):
        data = [Pair(0, 'LWPOLYLINE'), Pair(5, 'wide'), Pair(8, 'W'), Pair(43, width), Pair(410, 'Model')]
        for i, p in enumerate(points):
            data.append(Pair(10, p[:2]))
            if widths is not None: data.extend([Pair(40, widths[i][0]), Pair(41, widths[i][1])])
            if bulges is not None: data.append(Pair(42, bulges[i]))
        data.append(Pair(38, points[0][2]))
        self.entities['wide'] = data
        return self.call('EL:WireRecord', 'wide', self.cfg)

    def shape(self, a, b):
        return [Pair(Symbol('SEGMENTS'), [[a, b]])]

    def hit(self, wire, shape):
        return truth(self.call('EL:WideDevicePathHit', wire, shape, self.call('EL:StrictDeviceConfig', self.cfg)))

    def test_true_strip_width_and_butt_ends_not_distance_buffer(self):
        wire = self.wire([[0., 0., 0.], [100., 0., 0.]])
        self.assertTrue(self.hit(wire, self.shape([40., 20., 0.], [60., 20., 0.])))
        self.assertFalse(self.hit(wire, self.shape([40., 25.01, 0.], [60., 25.01, 0.])))
        self.assertFalse(self.hit(wire, self.shape([100.01, -10., 0.], [100.01, 10., 0.])))
        self.assertFalse(self.hit(wire, self.shape([40., 20., .01], [60., 20., .01])))

    def test_variable_width_taper_and_explicit_zero_override(self):
        wire = self.wire([[0., 0., 0.], [100., 0., 0.]], widths=[(0., 40.), (0., 0.)])
        self.assertTrue(self.hit(wire, self.shape([89., 15., 0.], [91., 15., 0.])))
        self.assertFalse(self.hit(wire, self.shape([9., 15., 0.], [11., 15., 0.])))
        zero = self.wire([[0., 0., 0.], [100., 0., 0.]], widths=[(0., 0.), (0., 0.)])
        self.assertFalse(self.get('contact-strips', zero))

    def test_scope_includes_device_touched_only_by_actual_width(self):
        self.block('BOX', 'P', 'panel', [-1., 0., 0.])
        self.block('LAMP', 'D', 'a', [50., 20., 0.])
        self.wire([[0., 0., 0.], [100., 0., 0.]])
        self.selected = ['panel', 'a', 'wide']
        self.assertEqual([self.get('id', b) for b in self.get('devices', self.network())], ['a'])

    def test_trunk_piece_does_not_inherit_other_pieces_contact_area(self):
        wire = self.wire([[0., 0., 0.], [100., 0., 0.]])
        piece = self.call('EL:TrunkPiece', wire, [[[50., 0., 0.], [100., 0., 0.]]], 1)
        self.assertTrue(self.hit(piece, self.shape([60., 20., 0.], [70., 20., 0.])))
        self.assertFalse(self.hit(piece, self.shape([10., 20., 0.], [20., 20., 0.])))

    def replay(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/wide-wire-079-snapshot.json').read_text(encoding='utf-8'))
        wires, blocks, shapes = [], [], {}
        for item in fixture['wires']:
            self.entities[item['id']] = [Pair(k, v) for k, v in item['dxf']] + [Pair(8, 'W')]
            wires.append(self.call('EL:WireRecord', item['id'], self.cfg))
        for item in fixture['blocks']:
            blocks.append([Pair(Symbol('ID'), item['id']), Pair(Symbol('BOUNDS'), item['bounds']),
                           Pair(Symbol('WHOLE-BLOCK'), True)])
            if item['shape']:
                shape = [Pair(Symbol(k.upper()), v) for k, v in item['shape'].items()]
                shapes[item['id']] = self.call('EL:PrepareContactBlock', shape)
        self.h.builtins['EL:DEVICECONTACTSHAPE'] = lambda b: shapes.get(self.get('id', b))
        snapshot = [Pair(Symbol('WIRES'), wires), Pair(Symbol('BLOCKS'), blocks),
                    Pair(Symbol('ENDS'), [e for w in wires for e in self.get('ends', w)])]
        return fixture, snapshot, shapes

    def test_recorded_21a6_22c8_centerline_misses_but_actual_width_hits(self):
        _, snapshot, shapes = self.replay()
        wire = next(w for w in self.get('wires', snapshot) if self.get('id', w) == '22C8')
        shape = shapes['21A6']
        self.assertFalse(truth(self.call('EL:ContourPathHit', wire, shape, self.call('EL:StrictDeviceConfig', self.cfg))))
        self.assertTrue(self.hit(wire, shape))

    def test_recorded_network_continues_beyond_first_lamp(self):
        fixture, snapshot, _ = self.replay()
        network = self.call('EL:SimpleNetwork', snapshot, self.cfg, fixture['panel'])
        self.h.load_definitions(Path(__file__).parents[1] / 'src/panel.lsp')
        result = self.call('EL:SplitNetwork', network, self.cfg)
        circuit = self.get('circuits', result)[0]
        self.assertEqual(len(self.get('wires', circuit)), 31)
        self.assertEqual(len(self.get('devices', circuit)), 30)
        self.assertIn('22C8', self.get('wires', circuit))
        for handle in ('21A6', '21AC', '21A9', '21CA', '21D2', '21E6', '220F'):
            self.assertIn(handle, self.get('devices', circuit))
        self.assertEqual(len(self.get('circuits', result)), 5)


if __name__ == '__main__':
    unittest.main()
