"""提取天正用户及系统图库并生成现有 EL_DEVICE_LIBRARY_V1 草稿库。

日期：2026-10-12
源 TK/SLB/DWB 只读；保留原始 DWG 和 SLD，不通过重画图例替代图形。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import uuid
import zipfile


def read_dbf(path: Path) -> list[dict[str, str]]:
    data = path.read_bytes()
    if len(data) < 33:
        raise ValueError("DBF 文件头不完整")
    count = int.from_bytes(data[4:8], "little")
    header, size = struct.unpack_from("<HH", data, 8)
    if not 33 <= header <= len(data) or size < 1:
        raise ValueError("DBF 文件头长度无效")
    fields = []
    pos = 32
    while pos < header and data[pos] != 13:
        raw = data[pos : pos + 32]
        if len(raw) != 32:
            raise ValueError("DBF 字段不完整")
        fields.append((raw[:11].split(b"\0")[0].decode("ascii"), raw[16]))
        pos += 32
    if pos >= header or 1 + sum(n for _, n in fields) != size:
        raise ValueError("DBF 字段与记录长度不一致")
    if header + count * size > len(data):
        raise ValueError("DBF 记录被截断")
    rows = []
    for index in range(count):
        raw = data[header + index * size : header + (index + 1) * size]
        if raw[0] == 42:
            continue
        if raw[0] != 32:
            raise ValueError("DBF 删除标记无效")
        row, offset = {}, 1
        for name, length in fields:
            row[name] = raw[offset : offset + length].rstrip(b" \0").decode("gb18030")
            offset += length
        rows.append(row)
    return rows


def read_archive(path: Path) -> dict[str, bytes]:
    data = path.read_bytes()
    banners = (b"ArchStar DWG  Library 1.0\r\n\x1a", b"AutoCAD Slide Library 1.0\r\n\x1a")
    if not data.startswith(banners):
        raise ValueError(f"图库格式不支持：{path.name}")
    entries, pos = [], 32
    while pos + 36 <= len(data) and data[pos]:
        name = data[pos : pos + 32].split(b"\0")[0].decode("ascii")
        pointer = int.from_bytes(data[pos + 32 : pos + 36], "little")
        if not re.fullmatch(r"[0-9]{8}", name):
            raise ValueError(f"图号无效：{name}")
        entries.append((name, pointer))
        pos += 36
    if pos + 36 > len(data) or not entries:
        raise ValueError("图库索引不完整")
    if len({name for name, _ in entries}) != len(entries):
        raise ValueError("图库内图号重复")
    result = {}
    for i, (name, start) in enumerate(entries):
        end = entries[i + 1][1] if i + 1 < len(entries) else len(data)
        if not pos + 36 <= start < end <= len(data):
            raise ValueError(f"图库指针无效：{name}")
        result[name] = data[start:end]
    return result


def decode_dwg(raw: bytes) -> bytes:
    """AS LZW 1.0：40 字节头，LSB 9-12 位兼容流，精确校验解压长度。"""
    if len(raw) < 42 or not raw.startswith(b"AS LZW 1.0 "):
        raise ValueError("DWG 压缩头不支持")
    size = int.from_bytes(raw[11:15], "little")
    if not 6 <= size <= 64 * 1024 * 1024:
        raise ValueError("DWG 声明长度无效")
    bit, width, next_code = 320, 9, 258
    table = {i: bytes([i]) for i in range(256)}
    previous, output, first = None, bytearray(), True
    while bit + width <= len(raw) * 8:
        offset, shift = divmod(bit, 8)
        code = (int.from_bytes(raw[offset : offset + 3], "little") >> shift) & ((1 << width) - 1)
        bit += width
        if first and code != 256:
            raise ValueError("LZW 缺少初始化标记")
        first = False
        if code == 256:
            table = {i: bytes([i]) for i in range(256)}
            width, next_code, previous = 9, 258, None
            continue
        if code == 257:
            if len(output) != size or not re.match(rb"AC10[0-9]{2}", output):
                raise ValueError("DWG 解压长度或标识校验失败")
            return bytes(output)
        if code in table:
            item = table[code]
        elif code == next_code and previous is not None:
            item = previous + previous[:1]
        else:
            raise ValueError("LZW 引用了不存在的字典项")
        output.extend(item)
        if len(output) > size:
            raise ValueError("DWG 解压结果超出声明长度")
        if previous is not None and next_code < 4096:
            table[next_code] = previous + item[:1]
            next_code += 1
            if next_code == 1 << width and width < 12:
                width += 1
        previous = item
    raise ValueError("LZW 结束标记缺失")


def slide_geometry(raw: bytes) -> tuple[list, list, tuple[int, int]]:
    if len(raw) < 33 or raw[:19] != b"AutoCAD Slide\r\n\x1a\0\x56\x02":
        raise ValueError("SLD 文件头不支持")
    if raw[29:31] not in (b"\x34\x12", b"\x12\x34"):
        raise ValueError("SLD 字节序无效")
    endian = "<" if raw[29:31] == b"\x34\x12" else ">"
    x, y = struct.unpack_from(endian + "HH", raw, 19)
    vectors, polygons, fill, last, color, pos = [], [], None, (0, 0), 7, 31
    while pos + 2 <= len(raw):
        word = struct.unpack_from(endian + "H", raw, pos)[0]
        code, low = word >> 8, word & 255
        if code < 128:
            x1, y1, x2, y2 = struct.unpack_from(endian + "hhhh", raw, pos)
            vectors.append(((x1, y1), (x2, y2), color))
            last, pos = (x1, y1), pos + 8
        elif code == 251:
            dx1 = low if low < 128 else low - 256
            dy1, dx2, dy2 = struct.unpack_from("bbb", raw, pos + 2)
            a = last[0] + dx1, last[1] + dy1
            b = last[0] + dx2, last[1] + dy2
            vectors.append((a, b, color))
            last, pos = a, pos + 5
        elif code == 252:
            if low or fill is not None:
                raise ValueError("SLD 结束标记无效")
            return vectors, polygons, (x + 1, y + 1)
        elif code == 253:
            vx, vy = struct.unpack_from(endian + "hh", raw, pos + 2)
            if low:
                raise ValueError("SLD 填充标记无效")
            if vy < 0:
                if fill is None:
                    fill = []
                else:
                    if len(fill) < 3:
                        raise ValueError("SLD 填充顶点不足")
                    polygons.append((fill, color))
                    fill = None
            elif fill is not None:
                fill.append((vx, vy))
            else:
                raise ValueError("SLD 填充开始标记缺失")
            pos += 6
        elif code == 254:
            dx = low if low < 128 else low - 256
            dy = struct.unpack_from("b", raw, pos + 2)[0]
            end = last[0] + dx, last[1] + dy
            vectors.append((last, end, color))
            last, pos = end, pos + 3
        elif code == 255:
            color, pos = low, pos + 2
        else:
            raise ValueError(f"SLD 指令不支持：{code}")
    raise ValueError("SLD 结束标记缺失")


def slide_checksum(raw: bytes) -> str:
    value = 0
    for byte in raw:
        value = (value * 131 + byte) % 2147483647
    return f"sld-{value}-{len(raw)}"


def render_slide(raw: bytes, size=(160, 160), monochrome=False):
    from PIL import Image, ImageDraw

    vectors, polygons, _ = slide_geometry(raw)
    points = [p for a, b, _ in vectors for p in (a, b)] + [p for group, _ in polygons for p in group]
    if not points:
        raise ValueError("SLD 没有可显示图形")
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    factor = min((size[0] - 8) / max(1, xmax - xmin), (size[1] - 8) / max(1, ymax - ymin))
    result = Image.new("RGB", (size[0] * 3, size[1] * 3), "black")
    draw = ImageDraw.Draw(result)
    palette = {0: "white", 1: "red", 2: "yellow", 3: "#00ff00", 4: "cyan", 5: "blue", 6: "magenta", 7: "white", 8: "#808080", 9: "#c0c0c0"}
    def point(p):
        return ((size[0] / 2 + (p[0] - (xmin + xmax) / 2) * factor) * 3,
                (size[1] / 2 - (p[1] - (ymin + ymax) / 2) * factor) * 3)
    def color(aci):
        return "white" if monochrome else palette.get(aci, "white")
    for vertices, aci in polygons:
        draw.polygon([point(p) for p in vertices], fill=color(aci))
    for a, b, aci in vectors:
        draw.line([point(a), point(b)], fill=color(aci), width=3)
    return result.resize(size, Image.Resampling.LANCZOS)


def lisp_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def make_catalog(selections: list[dict], dwgs: dict, slides: dict, library_id: str) -> str:
    entries = []
    names = set()
    for i, item in enumerate(selections, 1):
        drawing = item["drawing"]
        key = (item.get("source_library", "Equip_U"), drawing)
        if key not in dwgs or key not in slides:
            raise ValueError(f"缺少图形或图例：{drawing}")
        block = item.get("block_name", f'${"equip_U" if key[0] == "Equip_U" else "equip"}${drawing}')
        aliases = item.get("aliases", [])
        for name in [block, *aliases]:
            if name.upper() in names:
                raise ValueError(f"名称重复：{name}")
            names.add(name.upper())
        _, _, size = slide_geometry(slides[key])
        prefix = f"assets/ELDEV{i}/1/"
        fields = [f'(device-id . "ELDEV{i}")', '(revision . 1)',
                  f'(block-name . {lisp_string(block)})',
                  '(aliases ' + ' '.join(lisp_string(name) for name in aliases) + ')',
                  f'(display . {lisp_string(item["display"])})', '(watts)', '(zero-confirmed)',
                  '(is-ground' + (' . T)' if item.get("is_ground", False) else ')'),
                  '(ground-confirmed . T)', '(active)', '(status . draft)', '(asset-revision . 1)',
                  f'(block-file . "{prefix}block.dwg")', f'(legend-file . "{prefix}legend.sld")',
                  f'(legend-size {size[0]} {size[1]})',
                  f'(legend-checksum . "{slide_checksum(slides[key])}")']
        entries.append('    (' + ' '.join(fields) + ')')
    return ('((schema . EL_DEVICE_LIBRARY_V1)\n' + f' (library-id . "{library_id}")\n'
            + f' (revision . {len(entries)}) (next-id . {len(entries)+1})\n (devices\n'
            + '\n'.join(entries) + '\n ))\n')


def build_library(source: Path, selection: Path, destination: Path,
                  system_source: Path | None = None, baseline: Path | None = None) -> dict:
    if destination.exists():
        raise ValueError("目标已存在，请选择新目录；不会覆盖现有设备库")
    chosen = json.loads(selection.read_text(encoding="utf-8"))
    items = [dict(item) for item in chosen["items"]]
    if not items:
        raise ValueError("未选定图块")
    suffix = chosen.get("drawing_block_alias_suffix", "")
    for item in items:
        item.setdefault("source_library", chosen.get("source_library", "Equip_U"))
        if item["source_library"] not in ("Equip_U", "Equip"):
            raise ValueError("只支持 Equip_U 用户库或 Equip 系统库")
        if suffix and item["source_library"] == "Equip_U" and "aliases" not in item:
            block = item.get("block_name", f'$equip_U${item["drawing"]}')
            item["aliases"] = [block + suffix]
    if len({(r["source_library"], r["drawing"]) for r in items}) != len(items):
        raise ValueError("选定图号重复")
    dwgs, slides, source_hashes = {}, {}, {}
    for library in sorted({r["source_library"] for r in items}):
        folder = source if library == "Equip_U" else system_source
        if folder is None:
            raise ValueError("需要 --system-source 指定系统图库目录")
        compressed = read_archive(folder / f"{library}.DWB")
        raw_slides = read_archive(folder / f"{library}.SLB")
        for item in (r for r in items if r["source_library"] == library):
            drawing = item["drawing"]
            if drawing not in compressed or drawing not in raw_slides:
                raise ValueError(f"缺少图形或图例：{library}/{drawing}")
            key = (library, drawing)
            dwgs[key] = decode_dwg(compressed[drawing])
            slides[key] = raw_slides[drawing]
        for extension in ("DWB", "SLB", "TK"):
            path = folder / f"{library}.{extension}"
            if extension != "TK" or path.exists():
                source_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    identity = "LIB-TIANZ-" + uuid.uuid4().hex
    baseline_report = baseline_raw = None
    if baseline is not None:
        baseline_report = json.loads((baseline / "import-manifest.json").read_text(encoding="utf-8"))
        old_items = [dict(item) for item in baseline_report["items"]]
        for item in old_items:
            item.setdefault("source_library", "Equip_U")
        if items[:len(old_items)] != old_items or len(items) <= len(old_items):
            raise ValueError("基准库条目必须保持顺序和资料，仅在末尾新增")
        identity = baseline_report["library_id"]
        baseline_raw = (baseline / "catalog.eld").read_bytes()
        expected = make_catalog(old_items, dwgs, slides, identity).encode("utf-8")
        if baseline_raw != expected:
            raise ValueError("基准库已编辑，保留原库；不能用空功率重建替换")
        for i, item in enumerate(old_items, 1):
            key = (item["source_library"], item["drawing"])
            asset = baseline / "assets" / f"ELDEV{i}" / "1"
            if (asset / "block.dwg").read_bytes() != dwgs[key] or (asset / "legend.sld").read_bytes() != slides[key]:
                raise ValueError("基准库原始资产已变化，停止重建")
    catalog = make_catalog(items, dwgs, slides, identity)
    destination.mkdir(parents=True, exist_ok=False)
    for i, item in enumerate(items, 1):
        asset = destination / "assets" / f"ELDEV{i}" / "1"
        asset.mkdir(parents=True)
        key = (item["source_library"], item["drawing"])
        (asset / "block.dwg").write_bytes(dwgs[key])
        (asset / "legend.sld").write_bytes(slides[key])
    (destination / "history").mkdir()
    if baseline_report is not None:
        shutil.copytree(baseline / "history", destination / "history", dirs_exist_ok=True)
        previous = destination / "history" / f'{baseline_report["count"]}.eld'
        if previous.exists() and previous.read_bytes() != baseline_raw:
            raise ValueError("基准库历史版本冲突")
        previous.write_bytes(baseline_raw)
    (destination / "catalog.eld").write_text(catalog, encoding="utf-8", newline="\n")
    report = {"date": chosen["date"], "library_id": identity, "items": items,
              "count": len(items), "watts": None, "status": "draft",
              "pending_selections": chosen.get("pending", []),
              "source_sha256": source_hashes,
              "assets": [{"drawing": item["drawing"], "source_library": item["source_library"],
                           "dwg_sha256": hashlib.sha256(dwgs[(item["source_library"], item["drawing"])]).hexdigest(),
                           "slide_sha256": hashlib.sha256(slides[(item["source_library"], item["drawing"])]).hexdigest()} for item in items],
              "native_cad_acceptance": "pending"}
    if baseline_report is not None:
        report["baseline_count"] = baseline_report["count"]
        report["baseline_catalog_sha256"] = hashlib.sha256(baseline_raw).hexdigest()
    (destination / "import-manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--system-source", type=Path)
    parser.add_argument("--baseline", type=Path, help="保留未编辑草稿库的身份、顺序和历史；已填功率时拒绝重建")
    parser.add_argument("--zip", type=Path)
    args = parser.parse_args()
    if args.zip and args.zip.exists():
        parser.error("压缩包目标已存在，不覆盖")
    report = build_library(args.source, args.selection, args.destination, args.system_source, args.baseline)
    if args.zip:
        with zipfile.ZipFile(args.zip, "x", compression=zipfile.ZIP_DEFLATED) as package:
            for path in sorted(args.destination.rglob("*")):
                if path.is_file():
                    package.write(path, args.destination.name + "/" + path.relative_to(args.destination).as_posix())
    print(json.dumps({"count": report["count"], "destination": str(args.destination), "watts": None, "native_cad_acceptance": "pending"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
