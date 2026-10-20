"""Date: 2026-10-20. Original commercial-DXF subset; finite replay, not native CAD."""
import unittest
from pathlib import Path

from autolisp_host import Symbol, parse
from actual_contact_fixture import ActualContactFixture

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/commercial-contact-162.json'


def fixture(legacy=False):
    f = ActualContactFixture(path=FIXTURE)
    f.h.load_definitions(ROOT / 'src/fixed.lsp')
    f.h.step_limit = 100_000_000
    f.h.builtins.update({'CHR': chr, 'SSGET': lambda *a: f.document['selected'],
        'SSLENGTH': len, 'SSNAME': lambda ss, i: ss[i],
        'EL:ENTITYBOUNDS': f.document['bounds'].get,
        'VLAX-ENAME->VLA-OBJECT': lambda e: e,
        'VLAX-PROPERTY-AVAILABLE-P': lambda *a: False,
        'VLA-GET-NAME': lambda e: f.dxf(e, 2)})
    defaults = f.call('EL:PresetDefault')
    for key in ('panel-layers', 'panel-names', 'wire-layers', 'device-layers'):
        f.cfg = f.put(key, f.get(key, defaults), f.cfg)
    catalog = parse((ROOT / 'assets/default-device-library/catalog.eld').read_text('utf-8'))[0]
    names = [name for e in f.get('devices', catalog) if f.get('active', e)
             for name in [f.get('block-name', e), *(f.get('aliases', e) or [])]
             if not legacy or f.get('device-id', e) not in ('ELDEV52', 'ELDEV53')]
    if legacy:
        f.cfg = f.put('device-layers', ['LITE_照明设备_E'], f.cfg)
    for key, item in [('preset-scoped', True), ('device-names', names), ('auto-panel', 'F072')]:
        f.cfg = f.put(key, item, f.cfg)
    starts = []
    for handle, end in f.document['starts']:
        wire = f.call('EL:WireRecord', handle, f.cfg)
        ep = f.call('EL:By', Symbol('KEY'), [handle, Symbol(end)], f.get('ends', wire))
        start = None
        for key, item in [('wire', handle), ('end', Symbol(end)), ('point', f.get('point', ep))]:
            start = f.put(key, item, start)
        starts.append(start)
    f.cfg = f.put('circuit-starts', starts, f.cfg)
    return f


class CommercialContactTests(unittest.TestCase):
    def test_old_filter_reproduces_three_device_log(self):
        f = fixture(legacy=True)
        result = f.call('EL:RecognizeFixed', f.cfg, 'F072')
        self.assertEqual([len(f.get('devices', c) or []) for c in f.get('circuits', result)], [0, 3, 0, 0])

    def test_current_scope_reaches_lamp_and_touching_stair_devices(self):
        f = fixture()
        result = f.call('EL:RecognizeFixed', f.cfg, 'F072')
        ids = {h for c in f.get('circuits', result) for h in f.get('devices', c) or []}
        self.assertIn('1111D', ids)
        self.assertIn('54CB', ids)
        self.assertIn('77C9', ids)
        self.assertIn('784A', ids)
        circuits = f.get('circuits', result)
        self.assertEqual([len(f.get('devices', c) or []) for c in circuits], [0, 3, 3, 16])
        # Original R1 ends 330 mm below the nearest sign: never force a bridge.
        self.assertFalse(f.get('devices', circuits[0]))


class ImportedGraphicsTests(unittest.TestCase):
    def test_original_ellipse_masks_and_other_added_assets_have_supported_contours(self):
        from dxf_contact_fixture import DXFContactFixture, field
        from autolisp_host import Pair
        for identity in (50, 51, 52, 53):
            with self.subTest(identity=identity):
                f = DXFContactFixture(ROOT / f'assets/default-device-library/assets/ELDEV{identity}/1/block.dxf')
                row = next(row for row in f.model if field(row, 0) == 'INSERT')
                handle = field(row, 5)
                if identity == 51:
                    # Actual drawing pose is 500x, not the isolated asset's 1x.
                    f.entities[handle] += [Pair(k, 500.) for k in (41, 42, 43)]
                shape = f.body_shape(handle)
                self.assertFalse(f.get('issues', shape))
                self.assertTrue(f.get('segments', shape) or f.get('curves', shape))
                self.assertLess(len(f.get('segments', shape) or []), 4100)


if __name__ == '__main__':
    unittest.main()
