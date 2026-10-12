"""日期：2026-10-12。图库解压、原始资产及现有目录契约；不代替真实 CAD 验收。"""
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest

import test_device_assets as assets
import test_device_library as backend
from autolisp_host import Symbol, truth

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import import_tianz_library as importer


def packed_codes(codes):
    """独立按给定宽度打包，测试不通过另一份解码器制造预期结果。"""
    value = offset = 0
    for code, width in codes:
        value |= code << offset
        offset += width
    return value.to_bytes((offset + 7) // 8, 'little')


def packet(payload, codes):
    header = b'AS LZW 1.0 ' + struct.pack('<I', len(payload))
    return header.ljust(40, b'\0') + packed_codes(codes)


def literal_packet(parts):
    # 独立已知边界：第 256、768、1792 个字面量改用 10、11、12 位。
    def width(index):
        return 9 if index < 255 else 10 if index < 767 else 11 if index < 1791 else 12
    codes = [(256, 9)]
    for index, part in enumerate(parts):
        codes.extend((byte, width(n)) for n, byte in enumerate(part))
        codes.append((257 if index == len(parts) - 1 else 256, width(len(part))))
    return packet(b''.join(parts), codes)


def archive(banner, entries):
    pointer = 32 + 36 * (len(entries) + 1)
    index, contents = bytearray(banner.ljust(32, b'\0')), bytearray()
    for name, data in entries:
        index.extend(name.encode('ascii').ljust(32, b'\0') + struct.pack('<I', pointer))
        contents.extend(data)
        pointer += len(data)
    return bytes(index + bytes(36) + contents)


class TianzCompressionTests(unittest.TestCase):
    def test_literal_dictionary_reference_and_special_next_code(self):
        for code, tail in ((258, b'AC'), (263, b'55')):
            payload = b'AC1015' + tail
            codes = [(c, 9) for c in [256, *b'AC1015', code, 257]]
            self.assertEqual(importer.decode_dwg(packet(payload, codes)), payload)

    def test_every_width_dictionary_full_and_clear_restart(self):
        for length in (254, 255, 256, 767, 768, 1791, 1792, 4098, 4600):
            with self.subTest(length=length):
                payload = (b'AC1015' + bytes(range(256)) * 20)[:length]
                self.assertEqual(importer.decode_dwg(literal_packet([payload])), payload)
        parts = [b'AC1015' + b'x' * 4500, b'y' * 900, b'z' * 8]
        self.assertEqual(importer.decode_dwg(literal_packet(parts)), b''.join(parts))

    def test_corruption_fails_instead_of_returning_partial_dwg(self):
        valid = literal_packet([b'AC1015'])
        bad_size = bytearray(valid)
        bad_size[11:15] = struct.pack('<I', 7)
        invalid_reference = [(c, 9) for c in [256, *b'AC1015', 400, 257]]
        missing_clear = [(c, 9) for c in [*b'AC1015', 257]]
        for raw in (b'bad', valid[:40], valid[:-2], bytes(bad_size),
                    packet(b'AC1015x', invalid_reference), packet(b'AC1015', missing_clear),
                    literal_packet([b'NOTDWG'])):
            with self.subTest(raw=raw[:15]), self.assertRaises(ValueError):
                importer.decode_dwg(raw)

    def test_archive_keeps_original_bytes_and_rejects_duplicate_and_bad_pointer(self):
        banner = b'AutoCAD Slide Library 1.0\r\n\x1a'
        entries = [('00000398', b'first'), ('00000309', b'second')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'test.SLB')
            path.write_bytes(archive(banner, entries))
            self.assertEqual(importer.read_archive(path), dict(entries))
            path.write_bytes(archive(banner, [entries[0], entries[0]]))
            with self.assertRaises(ValueError):
                importer.read_archive(path)
            malformed = bytearray(archive(banner, entries))
            malformed[64:68] = struct.pack('<I', 35)
            path.write_bytes(malformed)
            with self.assertRaises(ValueError):
                importer.read_archive(path)

    def test_slide_documented_offsets_and_checksum_match_existing_lisp(self):
        vectors, polygons, size = importer.slide_geometry(assets.AUTODESK_VECTOR_SLIDE)
        self.assertEqual(size, (573, 293))
        self.assertEqual(polygons, [])
        self.assertEqual(vectors, [((572, 292), (0, 0), 7), ((15, 50), (15, 19), 3),
            ((33, 25), (33, 0), 1), ((33, 25), (0, 25), 1),
            ((0, 25), (0, 0), 1), ((0, 0), (33, 0), 1)])
        test = backend.DeviceLibraryTests(); test.setUp()
        with tempfile.TemporaryDirectory() as directory:
            test.fs(directory)
            assets.DeviceAssetsTests.binary(test)
            path = Path(directory, 'legend.sld'); path.write_bytes(assets.AUTODESK_VECTOR_SLIDE)
            self.assertEqual(importer.slide_checksum(path.read_bytes()),
                             test.call('EL:DLChecksum', str(path)))


class TianzCatalogTests(unittest.TestCase):
    setUp = backend.DeviceLibraryTests.setUp
    call = backend.DeviceLibraryTests.call
    get = backend.DeviceLibraryTests.get
    fs = backend.DeviceLibraryTests.fs
    binary = assets.DeviceAssetsTests.binary

    def test_utf8_catalog_blank_power_exact_aliases_and_original_assets(self):
        selection = {'date': '2026-10-12', 'drawing_block_alias_suffix': '(Zhangyufeng)',
            'items': [{'drawing': '00000398', 'display': '配电箱 "A"\\原图', 'role': 'panel'},
                      {'drawing': '00000329', 'display': '地面灯', 'is_ground': True}],
            'pending': [{'drawing': '00001198', 'source_library': 'Equip'}]}
        dwg = b'AC1015original-block'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'source'); source.mkdir()
            for name, banner, content in (
                ('Equip_U.DWB', b'ArchStar DWG  Library 1.0\r\n\x1a', literal_packet([dwg])),
                ('Equip_U.SLB', b'AutoCAD Slide Library 1.0\r\n\x1a', assets.AUTODESK_VECTOR_SLIDE)):
                Path(source, name).write_bytes(archive(banner, [(i['drawing'], content) for i in selection['items']]))
            Path(source, 'Equip_U.TK').write_bytes(b'unchanged source')
            chosen = Path(directory, 'chosen.json'); chosen.write_text(json.dumps(selection), encoding='utf-8')
            target = Path(directory, 'library')
            report = importer.build_library(source, chosen, target)
            root = self.fs(target); self.binary()
            snap = self.call('EL:DLSnapshotLoad', root)
            catalog = self.get('catalog', snap)
            self.assertTrue(truth(self.call('EL:DLCatalogValid', catalog)))
            self.assertEqual(self.get('next-id', catalog), 3)
            rows = self.get('devices', catalog)
            self.assertEqual(self.get('display', rows[0]), selection['items'][0]['display'])
            self.assertEqual(report['count'], 2)
            self.assertEqual(report['pending_selections'], selection['pending'])
            self.assertIsNone(self.call('EL:DLIndex', catalog))
            self.assertEqual(len(self.call('EL:DLRecognitionNames', snap)), 4)
            for row in rows:
                self.assertIsNone(self.get('watts', row))
                self.assertIsNone(self.get('active', row))
                self.assertIsNone(self.get('zero-confirmed', row))
                self.assertEqual(self.get('status', row), Symbol('DRAFT'))
                self.assertTrue(truth(self.get('ground-confirmed', row)))
                self.assertTrue(truth(self.call('EL:DLLegend', row, snap)))
                self.assertEqual(Path(target, self.get('block-file', row)).read_bytes(), dwg)
                self.assertEqual(Path(target, self.get('legend-file', row)).read_bytes(), assets.AUTODESK_VECTOR_SLIDE)
            self.assertFalse(truth(self.get('is-ground', rows[0])))
            self.assertTrue(truth(self.get('is-ground', rows[1])))

    def test_existing_target_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, 'library'); target.mkdir()
            existing = target / 'catalog.eld'; existing.write_bytes(b'original')
            with self.assertRaisesRegex(ValueError, '目标已存在'):
                importer.build_library(Path('missing'), Path('missing'), target)
            self.assertEqual(existing.read_bytes(), b'original')

    def test_system_library_append_preserves_identity_rows_history_and_entered_power(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'user'); source.mkdir()
            system = Path(directory, 'system'); system.mkdir()
            for folder, prefix, numbers, dwg in (
                (source, 'Equip_U', ['00000398'], b'AC1015user'),
                (system, 'Equip', ['00000398', '00001198'], b'AC1015system')):
                Path(folder, prefix + '.DWB').write_bytes(archive(b'ArchStar DWG  Library 1.0\r\n\x1a',
                    [(number, literal_packet([dwg])) for number in numbers]))
                Path(folder, prefix + '.SLB').write_bytes(archive(b'AutoCAD Slide Library 1.0\r\n\x1a',
                    [(number, assets.AUTODESK_VECTOR_SLIDE) for number in numbers]))
            selection = {'date': '2026-10-12', 'drawing_block_alias_suffix': '(Zhangyufeng)',
                         'items': [{'drawing': '00000398', 'display': '明装箱', 'role': 'panel'}]}
            chosen = Path(directory, 'chosen.json')
            chosen.write_text(json.dumps(selection), encoding='utf-8')
            baseline = Path(directory, 'baseline')
            first = importer.build_library(source, chosen, baseline)
            old_raw = (baseline / 'catalog.eld').read_bytes()
            old_catalog = self.call('EL:DLParse', old_raw.decode('utf-8'))
            selection['items'].extend([
                {'drawing': '00000398', 'display': '系统同号图块', 'source_library': 'Equip', 'role': 'device'},
                {'drawing': '00001198', 'display': '专用线路事故照明灯', 'source_library': 'Equip', 'role': 'device'}])
            chosen.write_text(json.dumps(selection), encoding='utf-8')
            target = Path(directory, 'extended')
            result = importer.build_library(source, chosen, target, system, baseline)
            self.assertEqual(first['library_id'], result['library_id'])
            self.assertEqual((target / 'history/1.eld').read_bytes(), old_raw)
            root = self.fs(target); self.binary()
            snapshot = self.call('EL:DLSnapshotLoad', root)
            rows = self.get('devices', self.get('catalog', snapshot))
            self.assertEqual(self.get('devices', old_catalog), rows[:1])
            self.assertEqual(self.get('block-name', rows[0]), '$equip_U$00000398')
            self.assertEqual(self.get('block-name', rows[1]), '$equip$00000398')
            self.assertEqual(self.get('block-name', rows[2]), '$equip$00001198')
            self.assertIsNone(self.get('aliases', rows[2]))
            self.assertIsNone(self.get('watts', rows[2]))
            self.assertEqual(Path(target, self.get('block-file', rows[0])).read_bytes(), b'AC1015user')
            self.assertEqual(Path(target, self.get('block-file', rows[1])).read_bytes(), b'AC1015system')
            # 用户已填功率时重建必须拒绝，不能以新草稿覆盖原库。
            edited = old_raw.replace(b'(watts)', b'(watts . 9)', 1)
            (baseline / 'catalog.eld').write_bytes(edited)
            rejected = Path(directory, 'rejected')
            with self.assertRaisesRegex(ValueError, '基准库已编辑'):
                importer.build_library(source, chosen, rejected, system, baseline)
            self.assertFalse(rejected.exists())
            self.assertEqual((baseline / 'catalog.eld').read_bytes(), edited)

    def test_system_selection_requires_system_source_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            chosen = Path(directory, 'chosen.json')
            chosen.write_text(json.dumps({'date': '2026-10-12', 'items': [
                {'drawing': '00001198', 'display': '系统灯', 'source_library': 'Equip'}]}), encoding='utf-8')
            target = Path(directory, 'library')
            with self.assertRaisesRegex(ValueError, 'system-source'):
                importer.build_library(Path('missing'), chosen, target)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
