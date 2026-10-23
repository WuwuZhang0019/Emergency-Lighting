"""Date: 2026-10-22. Status: original B-lamp line-arm regression and miss diagnostics.

The existing commercial DXF subset contains this B symbol. Replays prove that
fixture only; the user's latest DWG and new wires have not been supplied.
"""
import json
from pathlib import Path
import unittest

from autolisp_host import Pair, Symbol, truth
import test_simple_flow as simple

ROOT = Path(__file__).resolve().parents[1]
SOURCE = json.loads((ROOT / 'tests/fixtures/commercial-contact-162.json').read_text(encoding='utf-8'))
NAME = '$equip_U$00000309(Zhangyufeng)'


class LampLineArmTests(unittest.TestCase):
    def fixture(self, x=-250., y=250., gap=0.):
        f = simple.SimpleFlowTests()
        f.setUp()
        f.h.load_definitions(ROOT / 'src/panel.lsp')
        sx, sy = 1 if x > 0 else -1, 1 if y > 0 else -1
        center = [2000. + 4*x, 4*y, 0.]
        start = [center[0]-sx, center[1]-sy, 0.]
        f.block('BOX', 'P', 'panel', center)
        f.block(NAME, 'D', 'lamp', [2000., 0., 0.])
        f.bounds['lamp'] = [[1750., -250., 0.], [2375., 250., 0.]]
        f.entities['lamp'] += [Pair(41, 500.), Pair(42, 500.), Pair(43, 500.)]
        f.blocks[NAME] = [Pair(k, v) for k, v in SOURCE['blocks'][NAME]['tblsearch']]
        child = next(v for k, v in SOURCE['blocks'][NAME]['tblsearch'] if k == -2)
        while child:
            f.entities[child] = [Pair(k, v) for k, v in SOURCE['native_entget'][child]]
            f.next_entity[child] = SOURCE['next_entity'].get(child)
            child = SOURCE['next_entity'].get(child)
        f.line('wire', start, [2000.+x+sx*gap, y+sy*gap, 0.], 'W')
        f.selected = ['panel', 'lamp', 'wire']
        selected_start = [Pair(Symbol('WIRE'), 'wire'), Pair(Symbol('END'), Symbol('START')),
                          Pair(Symbol('POINT'), start)]
        f.cfg = f.call('EL:Put', Symbol('AUTO-PANEL'), 'panel',
            f.call('EL:Put', Symbol('CIRCUIT-STARTS'), [selected_start], f.cfg))
        return f

    def test_original_four_corner_line_tips_reach_lamp_in_complete_recognition(self):
        for x, y in ((-250., 250.), (250., 250.), (250., -250.), (-250., -250.)):
            with self.subTest(tip=(x, y)):
                f = self.fixture(x, y)
                result = f.call('EL:RecognizeFixed', f.cfg, 'panel')
                circuits = f.get('circuits', result)
                self.assertEqual(len(circuits), 1)
                self.assertEqual(f.get('devices', circuits[0]), ['lamp'])
                self.assertTrue(truth(f.get('complete', result)))
                shape = f.call('EL:DeviceContour', 'lamp')
                p = [2000.+x, y, 0.]
                self.assertTrue(any(p in seg for seg in f.get('segments', shape)))
                # The circle radius is 125; the wire touches only the outer line tip.
                self.assertGreater((x*x+y*y)**.5, 125.)

    def test_stopping_short_of_each_line_tip_does_not_bridge_the_gap(self):
        for x, y in ((-250., 250.), (250., 250.), (250., -250.), (-250., -250.)):
            with self.subTest(tip=(x, y)):
                f = self.fixture(x, y, gap=.02)
                result = f.call('EL:RecognizeFixed', f.cfg, 'panel')
                self.assertEqual([f.get('devices', c) for c in f.get('circuits', result)], [None])

    def test_real_miss_details_are_bounded_and_do_not_read_cad_or_modify_geometry(self):
        f = self.fixture()
        shape = f.call('EL:DeviceContour', 'lamp')
        segment = f.get('segments', shape)[0]
        shape = f.call('EL:Put', Symbol('SEGMENTS'), [segment]*40, shape)
        block = [Pair(Symbol('ID'), 'lamp'), Pair(Symbol('NAME'), NAME),
                 Pair(Symbol('BOUNDS'), f.bounds['lamp'])]
        wire = [Pair(Symbol('ID'), 'wire'), Pair(Symbol('SEGMENTS'), [segment]*10)]
        events = []
        f.h.set('*EL:PERFACTIVE*', True)
        f.h.set('*EL:LOGACTIVE*', True)
        f.h.set('*EL:PERFMETRICS*', None)
        f.h.builtins['EL:LOGEVENT'] = lambda *args: events.append(args)
        for api in ('ENTGET', 'ENTNEXT', 'TBLSEARCH', 'EL:DEVICECONTOUR', 'EL:ENTITYBOUNDS'):
            f.h.builtins[api] = lambda *args: self.fail('miss logging must use existing geometry')
        for _ in range(10):
            f.call('EL:DeviceWireMissDetails', wire, block, shape, f.cfg)
        self.assertEqual(len(events), 8)
        detail = events[0][1]
        self.assertEqual(f.get('device-name', detail), NAME)
        self.assertEqual(f.get('phase', detail), Symbol('FINE-CONTACT-AFTER-BOUNDS'))
        self.assertEqual(len(f.get('device-segments', detail)), 32)
        self.assertEqual(len(f.get('wire-segments', detail)), 8)
        self.assertTrue(truth(f.get('device-segments-truncated', detail)))
        self.assertTrue(truth(f.get('wire-truncated', detail)))
        self.assertEqual(f.get('segments', shape), [segment]*40)
        f.h.set('*EL:LOGACTIVE*', None)
        f.call('EL:DeviceWireMissDetails', wire, block, shape, f.cfg)
        self.assertEqual(len(events), 8)


if __name__ == '__main__':
    unittest.main()
