"""Shared physical contacts must not create entity triangles. Date: 2026-10-22. Status: current.

The 84A4 fixture preserves source DXF coordinates and all visible primitives.
Finite adapters only; original AutoCAD acceptance remains pending.
"""
import unittest

from autolisp_host import Pair, Symbol, truth
import test_simple_flow as simple


class ContactJunctionCycleTests(unittest.TestCase):
    setUp = simple.SimpleFlowTests.setUp
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    line = simple.SimpleFlowTests.line
    block = simple.SimpleFlowTests.block

    def polyline(self, handle, points, width=0.):
        self.entities[handle] = [Pair(0, 'LWPOLYLINE'), Pair(5, handle), Pair(8, 'W'),
            Pair(410, 'Model'), Pair(90, len(points)), Pair(70, 0), Pair(38, 0.),
            Pair(43, width), Pair(210, [0., 0., 1.])] + [Pair(10, list(p)) for p in points]

    def snapshot(self, wires, devices):
        records = [self.call('EL:WireRecord', handle, self.cfg) for handle in wires]
        blocks = [[Pair(Symbol('ID'), handle), Pair(Symbol('ENTITY'), handle),
            Pair(Symbol('ROLE'), Symbol('DEVICE')), Pair(Symbol('BOUNDS'), self.bounds[handle])]
            for handle in devices]
        return [Pair(Symbol('WIRES'), records), Pair(Symbol('BLOCKS'), blocks)]

    def edges(self, *pairs):
        return sorted(self.call('EL:Edge', *pair) for pair in pairs)

    def trace(self, snapshot, edges, wire='a'):
        seed = [Pair(Symbol('ID'), 'R1'), Pair(Symbol('WIRE'), wire)]
        return self.call('EL:TraceCircuit', seed, snapshot, edges, None)

    def codes(self, circuit):
        return [self.get('code', issue) for issue in self.get('issues', circuit) or []]

    def normalize(self, snapshot, edges):
        return self.call('EL:NormalizeContactEdges', snapshot, edges, self.cfg)

    def test_plain_serial_wires_share_one_device_contact_without_a_cycle(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.line('a', [1., 0., 0.], [10., 0., 0.], 'W')
        self.line('b', [10., 0., 0.], [19., 0., 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))
        normalized = self.normalize(snapshot, raw)
        self.assertEqual(normalized, self.edges(('a', 'lamp'), ('b', 'lamp')))
        self.assertTrue(truth(self.get('complete', self.trace(snapshot, normalized))))
        self.assertEqual(normalized, self.normalize(snapshot, normalized))

    def diagnostic_triangle(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.line('a', [1., 0., 0.], [10., 0., 0.], 'W')
        self.line('b', [10., 0., 0.], [19., 0., 0.], 'W')
        return self.snapshot(['a', 'b'], ['lamp']), self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))

    def test_closed_edge_diagnostic_preserves_result_and_records_existing_paths(self):
        snapshot, edges = self.diagnostic_triangle()
        baseline = self.trace(snapshot, edges)
        events = []
        self.h.builtins['EL:LOGEVENT'] = lambda name, detail: events.append((name, detail))
        self.h.set(Symbol('*EL:TRACEDIAGNOSTICS*'), True)
        self.h.set(Symbol('*EL:TRACEDIAGNOSTICCOUNT*'), 0)
        self.h.set(Symbol('*EL:TRACEDIAGNOSTICOMITTED*'), 0)
        actual = self.trace(snapshot, edges)
        self.assertEqual(actual, baseline)
        rows = [row for name, row in events if name == 'CIRCUIT_CLOSED_EDGE']
        self.assertTrue(rows)
        issue = self.get('issues', actual)[0]
        row = rows[0]
        self.assertEqual(self.get('from', row), self.get('object', issue))
        self.assertEqual(self.get('to', row), self.get('detail', issue))
        self.assertIn(self.get('to', row), self.get('from-neighbours', row))
        for side in ('from', 'to'):
            path = self.get(side + '-path', row)
            self.assertEqual(self.get('nodes', path)[0], 'a')
            self.assertEqual(self.get('nodes', path)[-1], self.get(side, row))
            self.assertFalse(truth(self.get('truncated', path)))
            self.assertEqual(self.get('handle', self.get(side + '-object', row)), self.get(side, row))

    def test_closed_edge_logging_stays_off_for_normal_recognition(self):
        snapshot, edges = self.diagnostic_triangle()
        events = []
        self.h.builtins['EL:LOGEVENT'] = lambda *args: events.append(args)
        self.h.set(Symbol('*EL:TRACEDIAGNOSTICS*'), None)
        result = self.trace(snapshot, edges)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(result))
        self.assertEqual(events, [])

    def test_closed_edge_diagnostic_limit_and_path_truncation_are_explicit(self):
        snapshot, edges = self.diagnostic_triangle()
        events = []
        self.h.builtins['EL:LOGEVENT'] = lambda *args: events.append(args)
        self.h.set(Symbol('*EL:TRACEDIAGNOSTICS*'), True)
        self.h.set(Symbol('*EL:TRACEDIAGNOSTICCOUNT*'), 20)
        self.h.set(Symbol('*EL:TRACEDIAGNOSTICOMITTED*'), 0)
        self.trace(snapshot, edges)
        self.assertEqual(events, [])
        self.assertGreater(self.h.lookup(Symbol('*EL:TRACEDIAGNOSTICOMITTED*')), 0)
        parents = [Pair('N' + str(i), 'N' + str(i - 1) if i else None) for i in range(40)]
        path = self.call('EL:TraceDiagnosticPath', 'N39', parents)
        self.assertEqual(len(self.get('nodes', path)), 32)
        self.assertTrue(truth(self.get('truncated', path)))

    def actual_dxf_fixture(self):
        name = '$equip_U$00000309(Zhangyufeng)'
        center = [324688.8776853233, 220168.0749259102, 0.]
        self.block(name, 'D', '84A4', center)
        self.entities['84A4'].extend([Pair(41, 500.), Pair(42, 500.), Pair(43, 500.)])
        self.bounds['84A4'] = [[center[0]-250., center[1]-250., 0.],
                               [center[0]+250., center[1]+250., 0.]]
        solids = [
            ('3390', [(-.2165063509528409, -.125), (.216506350938289, -.125), (-.25, 0.), (.25, 0.)]),
            ('3391', [(-.2165063509528409, .125), (.216506350938289, .125), (-.25, 0.), (.25, 0.)]),
            ('3395', [(-.125, -.2165063509455649), (.125, -.2165063509455649),
                      (-.2165063509528409, -.125), (.216506350938289, -.125)]),
            ('3396', [(0., -.25), (0., -.25), (-.125, -.2165063509455649), (.125, -.2165063509455649)]),
            ('3397', [(-.125, .2165063509457923), (.125, .2165063509457923),
                      (-.2165063509528409, .125), (.216506350938289, .125)]),
            ('3398', [(0., .25), (0., .25), (-.125, .2165063509457923), (.125, .2165063509457923)]),
        ]
        for handle, points in solids:
            self.entities[handle] = [Pair(0, 'SOLID'), Pair(5, handle), Pair(8, '0')] + [
                Pair(code, [*point, 0.]) for code, point in zip((10, 11, 12, 13), points)]
        self.line('3392', [.5, .5, 0.], [-.5, -.5, 0.])
        self.line('3393', [-.5, .5, 0.], [.5, -.5, 0.])
        self.entities['3394'] = [Pair(0, 'CIRCLE'), Pair(5, '3394'), Pair(8, '0'),
                                 Pair(10, [0., 0., 0.]), Pair(40, .25)]
        children = ['3390', '3391', '3392', '3393', '3394', '3395', '3396', '3397', '3398']
        self.blocks[name] = [Pair(2, name), Pair(10, [0., 0., 0.]), Pair(70, 2), Pair(-2, children[0])]
        for i, handle in enumerate(children):
            self.next_entity[handle] = children[i+1] if i < len(children)-1 else '339C'
        self.entities['339C'] = [Pair(0, 'ENDBLK'), Pair(5, '339C')]
        self.polyline('F0A6', [(324985.4294986096, 216421.245288766),
                              (324985.4294986096, 219818.2652282007),
                              (324938.8776853233, 219918.0749259102)], 50.)
        self.polyline('F36C', [(324938.8776853233, 219918.0749259102),
                              (328350.7930638891, 219918.0749259102),
                              (328350.7930638891, 215479.4061474785)], 50.)
        self.polyline('F0FE', [(323145.5832074438, 219141.8044829311),
                              (324438.8776853233, 219141.8044829311),
                              (324438.8776853233, 219918.0749259102)], 50.)
        return self.snapshot(['F0A6', 'F36C', 'F0FE'], ['84A4'])

    def test_actual_ze2_shared_corner_keeps_the_other_real_device_port(self):
        snapshot = self.actual_dxf_fixture()
        raw = self.edges(('F0A6', 'F36C'), ('84A4', 'F0A6'), ('84A4', 'F36C'), ('84A4', 'F0FE'))
        old = self.trace(snapshot, raw, 'F0A6')
        issue = self.get('issues', old)[0]
        self.assertEqual((self.get('code', issue), self.get('object', issue), self.get('detail', issue)),
                         (Symbol('CLOSED_CIRCUIT'), '84A4', 'F36C'))
        normalized = self.normalize(snapshot, raw)
        self.assertNotIn(self.call('EL:Edge', 'F0A6', 'F36C'), normalized)
        result = self.trace(snapshot, normalized, 'F0A6')
        self.assertTrue(truth(self.get('complete', result)), self.get('issues', result))
        self.assertEqual(set(self.get('wires', result)), {'F0A6', 'F36C', 'F0FE'})
        self.assertEqual(self.get('devices', result), ['84A4'])
        shape = self.call('EL:DeviceContactShape', self.get('blocks', snapshot)[0])
        self.assertEqual((len(self.get('segments', shape)), len(self.get('curves', shape))), (24, 1))

    def test_true_return_join_outside_device_still_reports_a_cycle(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.line('a', [9., 0., 0.], [20., 10., 0.], 'W')
        self.line('b', [20., 10., 0.], [11., 0., 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        normalized = self.normalize(snapshot, raw)
        self.assertEqual(normalized, raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, normalized)))

    def test_two_separate_common_device_ports_still_report_a_cycle(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.polyline('a', [(9., 0.), (20., 0.), (20., 10.), (11., 0.)])
        self.polyline('b', [(9., 0.), (20., -10.), (11., 0.)])
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))

    def test_a_wire_returning_from_another_device_port_is_not_hidden(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.polyline('a', [(9., 0.), (5., -5.), (15., -5.), (11., 0.)])
        self.line('b', [11., 0., 0.], [20., 0., 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))

    def test_a_wire_with_another_interior_device_contact_is_not_hidden(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.polyline('a', [(0., -5.), (9., 0.), (5., 5.), (15., 5.), (11., 0.)])
        self.line('b', [11., 0., 0.], [20., 0., 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))

    def test_one_straight_segment_with_two_separate_device_contact_regions_keeps_cycle(self):
        self.block('U-SHAPED', 'D', 'lamp', [0., 0., 0.])
        points = [(-1., -1.), (11., -1.), (11., 1.), (9., 1.),
                  (9., 0.), (1., 0.), (1., 1.), (-1., 1.)]
        self.entities['U-SHAPED-edge-0'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'U-SHAPED-edge-0'),
            Pair(70, 1)] + [Pair(10, list(p)) for p in points]
        self.next_entity['U-SHAPED-edge-0'] = 'U-SHAPED-end'
        self.bounds['lamp'] = [[-1., -1., 0.], [11., 1., 0.]]
        self.line('a', [-5., .5, 0.], [10., .5, 0.], 'W')
        self.line('b', [10., .5, 0.], [15., .5, 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))

    def test_revisiting_the_same_device_joint_along_a_wire_keeps_cycle(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.polyline('a', [(10., 0.), (20., 10.), (20., -10.), (10., 0.), (1., 0.)])
        self.line('b', [10., 0., 0.], [30., 0., 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))

    def test_nearly_tangential_ray_can_reach_a_remote_port_within_device_tolerance(self):
        self.block('C-SHAPED', 'D', 'lamp', [0., 0., 0.])
        points = [(-2., -1.), (0., -1.), (0., 1.), (-1., 1.),
                  (-1., 9.), (0., 9.), (0., 11.), (-2., 11.)]
        self.entities['C-SHAPED-edge-0'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'C-SHAPED-edge-0'),
            Pair(70, 1)] + [Pair(10, list(p)) for p in points]
        self.next_entity['C-SHAPED-edge-0'] = 'C-SHAPED-end'
        self.bounds['lamp'] = [[-2., -1., 0.], [0., 11., 0.]]
        self.line('a', [0., 0., 0.], [.001, 20., 0.], 'W')
        self.line('b', [0., 0., 0.], [10., 0., 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))

    def test_immediate_return_to_the_same_joint_keeps_cycle_evidence(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.polyline('a', [(10., 0.), (20., 10.), (10., 0.), (1., 0.)])
        self.line('b', [10., 0., 0.], [30., 0., 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))

    def test_wire_only_loop_is_retained(self):
        self.line('a', [0., 0., 0.], [10., 0., 0.], 'W')
        self.line('b', [10., 0., 0.], [5., 10., 0.], 'W')
        self.line('c', [5., 10., 0.], [0., 0., 0.], 'W')
        snapshot = self.snapshot(['a', 'b', 'c'], [])
        raw = self.edges(('a', 'b'), ('b', 'c'), ('c', 'a'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))

    def test_remote_virtual_gap_return_keeps_the_pair_edge(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.polyline('a', [(10., 0.), (0., 0.), (0., 10.), (5., 10.)])
        self.polyline('b', [(10., 0.), (20., 0.), (20., 10.), (15., 10.)])
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        gap = [Pair(Symbol('A'), ['a', Symbol('END')]), Pair(Symbol('B'), ['b', Symbol('END')])]
        snapshot = self.call('EL:Put', Symbol('GAP-PAIRS'), [gap], snapshot)
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(self.trace(snapshot, raw)))

    def test_device_contact_chain_keeps_all_real_handle_edges(self):
        self.block('LAMP', 'D', 'first', [10., 0., 0.])
        self.block('SIGN', 'D', 'second', [10., 2., 0.])
        self.line('a', [1., 0., 0.], [9., 0., 0.], 'W')
        self.line('b', [11., 2., 0.], [20., 2., 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['first', 'second'])
        raw = self.edges(('a', 'first'), ('first', 'second'), ('second', 'b'))
        self.assertEqual(self.normalize(snapshot, raw), raw)
        result = self.trace(snapshot, raw)
        self.assertTrue(truth(self.get('complete', result)))
        self.assertEqual(set(self.get('devices', result)), {'first', 'second'})

    def test_other_elevation_cannot_prove_a_shared_device_contact(self):
        self.block('LAMP', 'D', 'lamp', [10., 0., .01])
        self.line('a', [1., 0., 0.], [10., 0., 0.], 'W')
        self.line('b', [10., 0., 0.], [19., 0., 0.], 'W')
        snapshot = self.snapshot(['a', 'b'], ['lamp'])
        raw = self.edges(('a', 'b'), ('a', 'lamp'), ('b', 'lamp'))
        self.assertEqual(self.normalize(snapshot, raw), raw)


if __name__ == '__main__':
    unittest.main()
