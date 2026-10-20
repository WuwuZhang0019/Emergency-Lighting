"""日期：2026-10-20。只读提取本次授权的四个设备定义，生成独立 DXF 和 SLD。

依赖 ezdxf；不转换或伪造 DWG，不复制原图其他模型空间内容。
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'output/dxf-runtime'), str(ROOT / 'tests')]
from autolisp_host import Pair, Symbol, parse
from test_diagram_store import dump
from import_tianz_library import slide_checksum, slide_geometry

SPECS = [
    ('ELDEV50', 'f', 'f', '单向地面疏散标志灯', 1, True, []),
    ('ELDEV51', '$equip_U$00000719(Zhangyufeng)', '$equip_U$00000719', '双向地面疏散标志灯', 1, True,
     ['$equip_U$00000719(Zhangyufeng)']),
    ('ELDEV52', '$equip$00003228', '$equip$00003228', '应急灯（专用回路）', 5, False, []),
    ('ELDEV53', '$equip_U$00000601(zhangyuf)', '$equip_U$00000601', '楼层标志灯', 1, False,
     ['$equip_U$00000601(zhangyuf)']),
]


def get(key, data):
    row = next((r for r in data if (r.car if isinstance(r, Pair) else r[0]) == Symbol(key.upper())), None)
    return row.cdr if isinstance(row, Pair) else row[1:] if row else None


def set_value(key, item, data):
    key = Symbol(key.upper())
    rows = [r for r in data if (r.car if isinstance(r, Pair) else r[0]) != key]
    return rows + [Pair(key, item)]


def slide(block, header):
    from ezdxf.path import make_path
    paths, fills = [], []
    for entity in block:
        kind = entity.dxftype()
        if kind in ('ATTDEF', 'TEXT', 'MTEXT', 'WIPEOUT', 'POINT'):
            continue
        if kind == 'SOLID':
            fills.append([(p.x, p.y) for p in entity.wcs_vertices()])
            continue
        path = list(make_path(entity).flattening(0.001))
        paths.append([(p.x, p.y) for p in path])
    points = [p for path in paths + fills for p in path]
    xmin, ymin = map(min, zip(*points)); xmax, ymax = map(max, zip(*points))
    scale = min(1500 / (xmax - xmin), 900 / (ymax - ymin))
    def xy(point):
        return round(800 + scale * (point[0] - (xmin + xmax) / 2)), round(500 + scale * (point[1] - (ymin + ymax) / 2))
    data = bytearray(header[:31])
    struct.pack_into('<HH', data, 19, 1599, 999)
    data.extend(struct.pack('<H', 0xFF07))
    for poly in fills:
        data.extend(struct.pack('<Hhh', 0xFD00, 0, -1))
        for point in poly:
            data.extend(struct.pack('<Hhh', 0xFD00, *xy(point)))
        data.extend(struct.pack('<Hhh', 0xFD00, 0, -1))
    for path in paths:
        for a, b in zip(path, path[1:]):
            data.extend(struct.pack('<hhhh', *xy(a), *xy(b)))
    data.extend(struct.pack('<H', 0xFC00))
    slide_geometry(data)
    return bytes(data)


def main():
    import ezdxf
    from ezdxf.addons import Importer
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--only', help='只追加指定设备 ID，禁止覆盖已登记设备')
    args = parser.parse_args()
    source = ezdxf.readfile(args.source)
    destination = ROOT / 'assets/default-device-library'
    catalog = parse((destination / 'catalog.eld').read_text('utf-8'))[0]
    rows = get('devices', catalog)
    specs = [s for s in SPECS if not args.only or s[0] == args.only]
    if not specs:
        raise ValueError('没有匹配的设备 ID')
    if any(get('device-id', row) in {spec[0] for spec in specs} for row in rows):
        raise ValueError('目标设备已经登记，拒绝覆盖资产')
    header = (destination / 'assets/ELDEV22/1/legend.sld').read_bytes()
    report_path = destination / 'dxf-additions.json'
    additions = json.loads(report_path.read_text('utf-8'))['additions'] if args.only and report_path.exists() else []
    for identity, definition, name, display, watts, ground, aliases in specs:
        block = source.blocks.get(definition)
        target = ezdxf.new('R2018')
        importer = Importer(source, target)
        imported = importer.import_block(definition, rename=False)
        importer.finalize()
        # Importer intentionally omits wipeouts. Preserve the actual mask entity
        # from this isolated definition; no neighboring source geometry is copied.
        for entity in block:
            if entity.dxftype() == 'WIPEOUT':
                target.blocks.get(imported).add_entity(entity.copy())
        target.modelspace().add_blockref(imported, (0, 0, 0))
        actual = Counter(e.dxftype() for e in target.blocks.get(imported))
        expected = Counter(e.dxftype() for e in block)
        if actual != expected:
            raise ValueError(f'定义实体不一致：{definition}: {expected} / {actual}')
        folder = destination / 'assets' / identity / '1'
        folder.mkdir(parents=True, exist_ok=False)
        graphic = folder / 'block.dxf'
        target.saveas(graphic)
        loaded = ezdxf.readfile(graphic)
        if len(loaded.modelspace()) != 1 or Counter(e.dxftype() for e in loaded.blocks.get(imported)) != expected:
            raise ValueError('图块文件回读不一致')
        raw = slide(block, header)
        (folder / 'legend.sld').write_bytes(raw)
        prefix = f'assets/{identity}/1/'
        fields = dict(device_id=identity, revision=1, block_name=name, aliases=aliases, display=display,
                      watts=watts, zero_confirmed=None, is_ground=True if ground else None,
                      ground_confirmed=True, active=True, status=Symbol('READY'), asset_revision=1,
                      block_file=prefix + 'block.dxf', legend_file=prefix + 'legend.sld',
                      legend_size=list(slide_geometry(raw)[2]), legend_checksum=slide_checksum(raw))
        entry = [Pair(Symbol(k.replace('_', '-').upper()), Symbol('T') if v is True else v) for k, v in fields.items()]
        rows.append(entry)
        additions.append(dict(device_id=identity, source_block=definition, display=display, watts=watts,
                              is_ground=ground, source_types=dict(expected),
                              graphic_sha256=hashlib.sha256(graphic.read_bytes()).hexdigest(),
                              legend_sha256=hashlib.sha256(raw).hexdigest()))
    catalog = set_value('devices', rows, catalog)
    catalog = set_value('next-id', max(int(get('device-id', row)[5:]) for row in rows) + 1, set_value('revision', get('revision', catalog) + 1, catalog))
    (destination / 'catalog.eld').write_text(dump(catalog) + '\n', 'utf-8')
    report = dict(date='2026-10-20', status='isolated DXF and SLD readback passed; native CAD pending',
                  source_filename=args.source.name, source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
                  additions=additions, existing_assets_unchanged=True)
    (destination / 'dxf-additions.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
