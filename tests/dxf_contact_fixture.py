"""Date: 2026-10-20. Read-only ASCII DXF contact adapter; native CAD remains separate.

The adapter preserves native numeric precision, converts DXF angles to radians,
and uses body geometry only as conservative candidate bounds. It never writes
the supplied drawing and is not a general DXF editor or native extents oracle.
"""
import math
import re
from pathlib import Path

from actual_contact_fixture import ActualContactFixture


def value(code, text):
    if 10 <= code <= 59 or 110 <= code <= 149 or 210 <= code <= 239 or 1010 <= code <= 1059:
        number = float(text)
        return math.radians(number) if 50 <= code <= 58 else number
    if (60 <= code <= 99 or 160 <= code <= 179 or 270 <= code <= 299
            or 370 <= code <= 389 or 400 <= code <= 409 or 420 <= code <= 459
            or 1060 <= code <= 1071):
        return int(text)
    return re.sub(r'\\U\+([0-9A-Fa-f]{4})', lambda m: chr(int(m[1], 16)), text)


def records(path):
    raw = Path(path).read_bytes()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('gb18030')
    lines = text.splitlines()
    rows, current = [], []
    for i in range(0, len(lines) - 1, 2):
        code = int(lines[i])
        if code == 0 and current:
            rows.append(current)
            current = []
        current.append([code, value(code, lines[i + 1])])
    if current:
        rows.append(current)
    return rows


def field(row, code, default=None):
    return next((v for k, v in row if k == code), default)


def native_row(row):
    result, i = [], 0
    while i < len(row):
        code, item = row[i]
        if 10 <= code <= 18 or 210 <= code <= 218:
            point = [item]
            while i + 1 < len(row) and row[i + 1][0] in (code + 10, code + 20):
                i += 1
                point.append(row[i][1])
            if code != 10 or field(row, 0) != 'LWPOLYLINE':
                point += [0.] * (3 - len(point))
            result.append([code, point])
        else:
            result.append([code, item])
        i += 1
    return result


class DXFContactFixture(ActualContactFixture):
    def __init__(self, path):
        rows = records(path)
        self.raw_records = rows
        self.model = []
        entities, blocks, following = {}, {}, {}
        section, block, previous = None, None, None
        for row in rows:
            kind = field(row, 0)
            if kind == 'SECTION':
                section = field(row, 2)
            elif kind == 'ENDSEC':
                section = None
            if section not in ('BLOCKS', 'ENTITIES'):
                continue
            handle = field(row, 5)
            if not handle:
                continue
            converted = native_row(row)
            if section == 'ENTITIES':
                if kind == 'INSERT' and not field(converted, 410):
                    converted.append([410, 'Model'])
                self.model.append(converted)
            if kind == 'BLOCK':
                block, previous = field(row, 2), None
                blocks[block] = {'tblsearch': converted}
            elif block:
                if previous:
                    following[previous] = handle
                else:
                    blocks[block]['tblsearch'].append([-2, handle])
                previous = handle
            entities[handle] = converted
            if kind == 'ENDBLK':
                block, previous = None, None
        self.document = {'native_entget': entities, 'blocks': blocks, 'next_entity': following}
        from autolisp_host import Host
        self.h = Host()
        self.h.step_limit = 100_000_000
        root = Path(__file__).resolve().parents[1]
        for module in ('common', 'config', 'geometry', 'topology', 'statistics',
                       'device-library', 'device-recognition', 'device-inputs',
                       'circuit-number', 'simple', 'fixed', 'panel', 'diagram-update'):
            self.h.load_definitions(root / 'src' / (module + '.lsp'))
        self.install(self.h)
        self.cfg = self.call('EL:DefaultConfig', Path(path).name)
        self.cfg = self.put('params', self.call('EL:SuggestedParams'), self.cfg)
        self.bounds = {}

    def nearby(self, bounds, layer=None):
        result = []
        for row in self.model:
            if layer and field(row, 8) != layer:
                continue
            point = field(row, 10)
            if point and all(bounds[0][i] <= point[i] <= bounds[1][i] for i in (0, 1)):
                result.append(field(row, 5))
        return result
