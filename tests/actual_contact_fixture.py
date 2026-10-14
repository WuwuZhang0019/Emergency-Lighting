"""Independent replay of a minimal original-DXF contact subset.

Date: 2026-10-14. Status: finite CAD adapter; original DWG acceptance pending.
All entity coordinates and angles come from the checked-in JSON fixture. Local
body-contour envelopes are conservative candidate bounds, not native extents.
"""
import json
from pathlib import Path

from autolisp_host import Host, Symbol


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/device-contact-132.json'


class ActualContactFixture:
    def __init__(self, host=None, path=FIXTURE):
        self.document = json.loads(Path(path).read_text(encoding='utf-8'))
        self.h = host or Host()
        if host is None:
            for name in ('common', 'config', 'geometry', 'topology', 'statistics',
                         'device-library', 'device-recognition', 'device-inputs',
                         'circuit-number', 'simple', 'panel', 'diagram-update'):
                self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')
        self.install(self.h)
        self.cfg = self.call('EL:DefaultConfig', 'actual-contact-132.dxf')
        self.cfg = self.put('params', self.call('EL:SuggestedParams'), self.cfg)
        for key, value in (('units', 'mm'), ('wire-layers', ['LITE_应急照明布线_E']),
                           ('device-layers', ['LITE_照明设备_E'])):
            self.cfg = self.put(key, value, self.cfg)
        self.bounds = {}

    def install(self, host):
        cons = host.builtins['CONS']
        self.entities = {handle: [cons(code, value) for code, value in rows]
                         for handle, rows in self.document['native_entget'].items()}
        self.blocks = {name.upper(): [cons(code, value) for code, value in item['tblsearch']]
                       for name, item in self.document['blocks'].items()}
        self.next_entity = self.document['next_entity']
        host.frames[0][':VLAX-TRUE'] = -1
        host.builtins.update({
            'ENTGET': lambda handle, apps=None: self.entities.get(str(handle).upper()),
            'HANDENT': lambda handle: str(handle).upper() if str(handle).upper() in self.entities else None,
            'TBLSEARCH': lambda table, name: self.blocks.get(str(name).upper()) if table.upper() == 'BLOCK' else None,
            'ENTNEXT': lambda handle: self.next_entity.get(str(handle).upper()),
            'TRANS': self.trans,
            'EL:LOGEVENT': lambda *args: None,
            'EL:DRAWINGID': lambda: 'actual-contact-132.dxf',
            'EL:MANAGEDENTITY': lambda handle: None,
            'NAMEDOBJDICT': lambda: 'actual-contact-fixture-NOD',
            'GETVAR': lambda key: {'MILLISECS': 0, 'DWGNAME': 'actual-contact-132.dxf',
                                   'DWGPREFIX': 'fixture/', 'DWGTITLED': 1}.get(key, 0),
        })
        return self

    def trans(self, point, source, target, displacement=None):
        def sign(frame):
            if frame == 0:
                return 1.
            if isinstance(frame, str):
                frame = self.call('CDR', self.call('ASSOC', 210, self.entities[frame.upper()])) or [0., 0., 1.]
            if (not isinstance(frame, list) or len(frame) != 3 or abs(frame[0]) > 1.e-12
                    or abs(frame[1]) > 1.e-12 or abs(abs(frame[2]) - 1.) > 1.e-12):
                raise ValueError('Fixture supports WCS and planar +/-Z OCS only')
            return frame[2]
        factor = sign(source) * sign(target)
        xyz = list(point) + [0.] * (3 - len(point))
        return [factor * xyz[0], xyz[1], factor * xyz[2]]

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, value):
        return self.call('EL:Get', Symbol(key.upper()), value)

    def put(self, key, value, record):
        return self.call('EL:Put', Symbol(key.upper()), value, record)

    def record(self, handle):
        return self.h.builtins['ENTGET'](handle)

    def dxf(self, handle, code):
        return self.call('CDR', self.call('ASSOC', code, self.record(handle)))

    def body_shape(self, handle):
        return self.call('EL:DeviceContour', handle)

    def body_bounds(self, handle):
        if handle not in self.bounds:
            shape = self.body_shape(handle)
            if self.get('issues', shape):
                raise ValueError(f'Unsupported fixture body: {handle}')
            points = [point for segment in self.get('segments', shape) or [] for point in segment]
            for curve in self.get('curves', shape) or []:
                center, radius = curve[:2]
                points.extend([[center[0] - radius, center[1] - radius, center[2]],
                               [center[0] + radius, center[1] + radius, center[2]]])
            if not points:
                raise ValueError(f'Empty fixture body: {handle}')
            self.bounds[handle] = [[min(point[i] for point in points) for i in range(3)],
                                   [max(point[i] for point in points) for i in range(3)]]
        return self.bounds[handle]

    def build(self, wires, devices, root, eps_device=None):
        cfg = self.cfg
        if eps_device is not None:
            cfg = self.put('params', self.put('eps_device', eps_device, self.get('params', cfg)), cfg)
        wire_rows = [self.call('EL:WireRecord', handle, cfg) for handle in wires]
        roots = next(row for row in wire_rows if self.get('id', row) == root[0])
        endpoint = self.call('EL:By', Symbol('KEY'), [root[0], Symbol(root[1].upper())], self.get('ends', roots))
        start = [self.call('CONS', Symbol('WIRE'), root[0]),
                 self.call('CONS', Symbol('END'), Symbol(root[1].upper())),
                 self.call('CONS', Symbol('POINT'), self.get('point', endpoint))]
        cfg = self.put('circuit-starts', [start], self.put('auto-panel', 'fixture-panel', cfg))
        blocks = []
        for handle in devices:
            block = None
            for key, value in (('entity', handle), ('id', handle), ('name', self.dxf(handle, 2)),
                               ('layer', self.dxf(handle, 8)), ('bounds', self.body_bounds(handle)),
                               ('whole-block', True)):
                block = self.put(key, value, block)
            blocks.append(block)
        snapshot = None
        for key, value in (('drawing', 'actual-contact-132.dxf'), ('wires', wire_rows), ('blocks', blocks),
                           ('ends', [ep for wire in wire_rows for ep in self.get('ends', wire) or []]),
                           ('issues', [issue for wire in wire_rows for issue in self.get('issues', wire) or []])):
            snapshot = self.put(key, value, snapshot)
        snapshot = self.call('EL:StartSnapshot', snapshot, cfg, 'fixture-panel')
        self.cfg, self.snapshot = cfg, snapshot
        self.h.frames.append({'*EL:DEVICECONTACTCACHE*': None, '*EL:DEVICETEMPLATECACHE*': None,
                              '*EL:DEVICETEMPLATEENABLED*': True})
        try:
            return self.call('EL:SimpleNetworkBuild', snapshot, cfg, 'fixture-panel')
        finally:
            self.h.frames.pop()

    def build_case(self, name, eps_device=None):
        case = self.document['cases'][name]
        return self.build(case['wires'], case['devices'], case['root'], eps_device)

    def split(self, network):
        return self.call('EL:SplitNetwork', network, self.cfg)
