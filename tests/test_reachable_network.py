"""Explicit-root reachability and exact physical contacts. Date: 2026-10-13.

Finite CAD adapters only; original drawing acceptance remains pending.
"""
import unittest

from autolisp_host import Pair, Symbol
import test_simple_flow as simple


class ReachableNetworkTests(unittest.TestCase):
    setUp = simple.SimpleFlowTests.setUp
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    line = simple.SimpleFlowTests.line
    block = simple.SimpleFlowTests.block

    def put(self, key, value, row):
        return self.call('EL:Put', Symbol(key.upper()), value, row)

    def rooted(self, handle='root', side='start', additional=()):
        """Use the production start validation and boundary removal route."""
        starts = []
        for handle, side in [(handle, side), *additional]:
            wire = self.call('EL:WireRecord', handle, self.cfg)
            endpoint = self.call('EL:By', Symbol('KEY'), [handle, Symbol(side.upper())],
                                 self.get('ends', wire))
            starts.append([Pair(Symbol('WIRE'), handle), Pair(Symbol('END'), Symbol(side.upper())),
                           Pair(Symbol('POINT'), self.get('point', endpoint))])
        self.cfg = self.put('circuit-starts', starts, self.cfg)
        self.cfg = self.put('auto-panel', 'panel', self.cfg)
        snapshot = self.call('EL:StartSnapshot', self.call('EL:SimpleCollect', self.cfg),
                             self.cfg, 'panel')
        return self.call('EL:SimpleNetwork', snapshot, self.cfg, 'panel')

    def shapes(self, forbidden=()):
        params, body = self.h.functions[Symbol('EL:DEVICECONTACTSHAPE')]
        original = [Symbol('LAMBDA'), params, *body]
        calls = []

        def record(block):
            handle = self.get('id', block)
            calls.append(handle)
            if handle in forbidden:
                self.fail(f'Unreachable device contour was read: {handle}')
            return self.h.call(original, [block])

        self.h.builtins['EL:DEVICECONTACTSHAPE'] = record
        return calls

    def ids(self, result):
        return {self.get('id', block) for block in self.get('devices', result) or []}

    def edge(self, result, a, b):
        return self.call('EL:Edge', a, b) in (self.get('edges', result) or [])

    def base(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('LAMP', 'D', 'a', [10., 0., 0.])
        self.line('root', [1., 0., 0.], [9., 0., 0.], 'W')
        self.selected = ['panel', 'a', 'root']

    def test_one_hundred_remote_nodes_keep_source_records_without_reading_contours(self):
        self.base()
        remote_blocks, remote_wires = set(), set()
        for i in range(50):
            x = 10000. + i*100.
            junction, lamp = f'remote-j{i:02}', f'remote-d{i:02}'
            before, after = f'remote-in{i:02}', f'remote-out{i:02}'
            self.block('JBOX', 'J', junction, [x, 100., 0.])
            self.block('SIGN', 'D', lamp, [x+20., 100., 0.])
            self.line(before, [x-10., 100., 0.], [x-1., 100., 0.], 'W')
            self.line(after, [x+1., 100., 0.], [x+19., 100., 0.], 'W')
            self.selected += [junction, lamp, before, after]
            remote_blocks.update((junction, lamp))
            remote_wires.update((before, after))
        self.cfg = self.call('EL:JunctionSamples', self.cfg, ['JBOX'], None)
        reads = self.shapes(remote_blocks)
        result = self.rooted()
        self.assertEqual(self.ids(result), {'a'})
        self.assertEqual(set(self.get('wire-ids', result)), {'root'})
        self.assertEqual(remote_blocks.intersection(reads), set())
        snapshot = self.get('snapshot', result)
        self.assertTrue(remote_blocks.issubset({self.get('id', b) for b in self.get('blocks', snapshot)}))
        self.assertTrue(remote_wires.issubset({self.get('id', w) for w in self.get('wires', snapshot)}))

    def test_bbox_empty_candidate_does_not_open_its_independent_wire_network(self):
        self.base()
        self.block('SIGN', 'D', 'false-candidate', [100., 100., 0.])
        # Text/attribute extents cover the root while the actual symbol is remote.
        self.bounds['false-candidate'] = [[8., -1., 0.], [104., 104., 0.]]
        self.line('remote-wire', [101., 100., 0.], [119., 100., 0.], 'W')
        self.block('OTHER', 'D', 'remote-lamp', [120., 100., 0.])
        self.selected += ['false-candidate', 'remote-wire', 'remote-lamp']
        reads = self.shapes()
        result = self.rooted()
        self.assertEqual(self.ids(result), {'a'})
        self.assertEqual(set(self.get('wire-ids', result)), {'root'})
        self.assertFalse(self.edge(result, 'root', 'false-candidate'))
        self.assertNotIn('remote-lamp', reads)

    def test_t_endpoint_contacts_work_in_both_drawing_directions_but_interiors_do_not_join(self):
        self.base()
        self.line('root', [1., 0., 0.], [19., 0., 0.], 'W')
        self.block('LAMP', 'D', 'a', [20., 0., 0.])
        self.line('north', [10., 0., 0.], [10., 9., 0.], 'W')
        self.line('south', [10., -9., 0.], [10., 0., 0.], 'W')
        self.block('LAMP', 'D', 'north-lamp', [10., 10., 0.])
        self.block('LAMP', 'D', 'south-lamp', [10., -10., 0.])
        self.line('cross', [15., -20., 0.], [15., 20., 0.], 'W')
        self.block('LAMP', 'D', 'cross-lamp', [15., 21., 0.])
        self.selected += ['north', 'south', 'north-lamp', 'south-lamp', 'cross', 'cross-lamp']
        result = self.rooted()
        self.assertEqual(self.ids(result), {'a', 'north-lamp', 'south-lamp'})
        self.assertEqual(set(self.get('wire-ids', result)), {'root', 'north', 'south'})
        self.assertTrue(self.edge(result, 'root', 'north'))
        self.assertTrue(self.edge(result, 'root', 'south'))
        self.assertFalse(self.edge(result, 'root', 'cross'))

    def test_real_device_contact_chain_discovers_onward_wire(self):
        self.base()
        self.block('SIGN', 'D', 'b', [10., 2., 0.])
        self.block('SIGN', 'D', 'c', [10., 4., 0.])
        self.line('onward', [11., 4., 0.], [19., 4., 0.], 'W')
        self.block('SIGN', 'D', 'd', [20., 4., 0.])
        self.selected += ['b', 'c', 'onward', 'd']
        result = self.rooted()
        self.assertEqual(self.ids(result), {'a', 'b', 'c', 'd'})
        self.assertEqual(set(self.get('wire-ids', result)), {'root', 'onward'})
        for a, b in (('a', 'b'), ('b', 'c'), ('c', 'onward'), ('onward', 'd')):
            self.assertTrue(self.edge(result, a, b))

    def test_coincident_selected_roots_cannot_return_through_registered_junction(self):
        self.h.load_definitions(simple.adapter.ROOT / 'src/panel.lsp')
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('JBOX', 'J', 'source-junction', [10., 0., 0.])
        self.line('root', [10., 0., 0.], [19., 10., 0.], 'W')
        self.line('second', [19., -10., 0.], [10., 0., 0.], 'W')
        self.block('LAMP', 'D', 'upper', [20., 10., 0.])
        self.block('LAMP', 'D', 'lower', [20., -10., 0.])
        self.selected = ['panel', 'source-junction', 'root', 'second', 'upper', 'lower']
        self.cfg = self.call('EL:JunctionSamples', self.cfg, ['JBOX'], None)
        result = self.rooted(additional=(('second', 'end'),))
        self.assertEqual(self.ids(result), {'upper', 'lower'})
        self.assertFalse(self.edge(result, 'root', 'source-junction'))
        self.assertFalse(self.edge(result, 'second', 'source-junction'))
        self.assertFalse(self.edge(result, 'root', 'second'))
        split = self.call('EL:SplitNetwork', result, self.cfg)
        self.assertEqual(sorted(sorted(self.get('devices', c) or [])
                                for c in self.get('circuits', split)), [['lower'], ['upper']])

    def test_junction_enters_only_at_endpoints_and_free_gap_continues(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('JBOX', 'J', 'junction', [10., 0., 0.])
        self.line('root', [1., 0., 0.], [9., 0., 0.], 'W')
        self.line('exit', [11., 0., 0.], [20., 0., 0.], 'W')
        self.line('after-gap', [25., 0., 0.], [29., 0., 0.], 'W')
        self.block('LAMP', 'D', 'lamp', [30., 0., 0.])
        self.block('LAMP', 'D', 'gap-obstacle', [22., 0., 0.])
        self.line('cross', [10., -20., 0.], [10., 20., 0.], 'W')
        self.block('LAMP', 'D', 'cross-lamp', [10., 21., 0.])
        self.block('LAMP', 'D', 'touching-junction', [10., -2., 0.])
        self.selected = ['panel', 'junction', 'root', 'exit', 'after-gap', 'lamp',
                         'gap-obstacle', 'cross', 'cross-lamp', 'touching-junction']
        self.cfg = self.call('EL:JunctionSamples', self.cfg, ['JBOX'], None)
        result = self.rooted()
        self.assertEqual(self.ids(result), {'lamp'})
        self.assertEqual(set(self.get('wire-ids', result)), {'root', 'exit', 'after-gap'})
        self.assertTrue(self.edge(result, 'root', 'junction'))
        self.assertTrue(self.edge(result, 'junction', 'exit'))
        self.assertFalse(self.edge(result, 'junction', 'cross'))
        self.assertFalse(self.edge(result, 'junction', 'touching-junction'))
        self.assertEqual(len(self.get('gap-pairs', result)), 1)
        self.assertFalse(self.edge(result, 'gap-obstacle', 'exit'))


if __name__ == '__main__':
    unittest.main()
