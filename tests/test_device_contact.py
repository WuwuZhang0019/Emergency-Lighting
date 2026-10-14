"""Device contact connectivity. Date: 2026-10-10; synthetic CAD only."""
import unittest
import test_simple_flow as simple
import test_cad_adapter as adapter
from autolisp_host import Pair


class DeviceContactTests(unittest.TestCase):
    setUp = simple.SimpleFlowTests.setUp
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    line = simple.SimpleFlowTests.line
    block = simple.SimpleFlowTests.block
    network = simple.SimpleFlowTests.network

    def fixture(self, position=(10., 2., 0.)):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('LAMP', 'D', 'a', [10., 0., 0.])
        self.block('SIGN', 'D', 'b', list(position))
        self.line('w', [1., 0., 0.], [9., 0., 0.], 'W')
        self.selected = ['panel', 'a', 'b', 'w']

    def ids(self, result):
        return sorted(self.get('id', b) for b in self.get('devices', result) or [])

    def test_touch_chain_reaches_device_and_onward_wire_once(self):
        self.fixture()
        self.block('SIGN', 'D', 'c', [10., 4., 0.])
        self.block('SIGN', 'D', 'd', [20., 4., 0.])
        self.line('w2', [11., 4., 0.], [19., 4., 0.], 'W')
        self.selected += ['c', 'd', 'w2']
        result = self.network()
        self.assertEqual(self.ids(result), ['a', 'b', 'c', 'd'])
        self.assertEqual(len(self.get('edges', result)), 6)
        self.h.load_definitions(adapter.ROOT / 'src/panel.lsp')
        split = self.call('EL:SplitNetwork', result, self.cfg)
        circuits = self.get('circuits', split)
        self.assertEqual(len(circuits), 1)
        self.assertEqual(sorted(self.get('devices', circuits[0])), ['a', 'b', 'c', 'd'])

    def test_corner_overlap_and_containment_connect(self):
        for pos in ((12., 2., 0.), (11., 1., 0.), (10., 0., 0.)):
            with self.subTest(pos=pos):
                self.setUp()
                self.fixture(pos)
                self.assertEqual(self.ids(self.network()), ['a', 'b'])

    def test_gap_and_different_elevation_do_not_connect(self):
        for pos in ((10., 2.0101, 0.), (10., 2., 0.01), (100., 100., 0.)):
            with self.subTest(pos=pos):
                self.setUp()
                self.fixture(pos)
                self.assertEqual(self.ids(self.network()), ['a'])

    def test_touching_panel_does_not_create_device_connection(self):
        self.fixture((0., 2., 0.))
        self.assertEqual(self.ids(self.network()), ['a'])

    def test_disconnected_touching_pair_stays_outside_circuit(self):
        self.fixture((100., 100., 0.))
        self.block('SIGN', 'D', 'c', [100., 102., 0.])
        self.selected.append('c')
        self.assertEqual(self.ids(self.network()), ['a'])

    def test_overlapping_bounds_without_real_contact_are_not_connected(self):
        self.fixture((13., 3., 0.))
        # A text/attribute extent can overlap both the other lamp and its wire.
        self.bounds['b'] = [[8., -1., 0.], [15., 4., 0.]]
        self.assertEqual(self.ids(self.network()), ['a'])

    def test_circle_bounds_overlap_but_circles_do_not_touch(self):
        self.fixture((11.5, 1.5, 0.))
        for name in ('LAMP', 'SIGN'):
            first = f'{name}-edge-0'
            self.entities[first] = [Pair(0, 'CIRCLE'), Pair(5, first),
                                    Pair(10, [0., 0., 0.]), Pair(40, 1.)]
            self.next_entity[first] = f'{name}-end'
        self.assertEqual(self.ids(self.network()), ['a'])

    def test_near_wire_outside_actual_device_is_not_counted(self):
        self.fixture((5., 1.01, 0.))
        self.assertEqual(self.ids(self.network()), ['a'])

    def test_changed_geometry_with_same_bounds_changes_signature(self):
        self.fixture()
        before = self.get('device-contact-signature', self.get('snapshot', self.network()))
        self.line('SIGN-edge-0', [-0.5, -0.5, 0.], [0.5, -0.5, 0.])
        after = self.get('device-contact-signature', self.get('snapshot', self.network()))
        self.assertNotEqual(before, after)
