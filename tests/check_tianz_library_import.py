"""日期：2026-10-12。检查实际图库提取、LISP 数据契约及 ZIP 字节一致性。"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import zipfile

import test_device_assets as assets
import test_device_library as backend
from autolisp_host import Symbol, truth

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import import_tianz_library as importer


def check(source: Path, library: Path, package: Path, system_source: Path | None = None) -> dict:
    report = json.loads((library / 'import-manifest.json').read_text(encoding='utf-8'))
    compressed, slides, decoded_counts = {}, {}, {}
    for source_library in {i.get('source_library', 'Equip_U') for i in report['items']}:
        folder = source if source_library == 'Equip_U' else system_source
        assert folder is not None, '缺少系统图库目录'
        compressed[source_library] = importer.read_archive(folder / f'{source_library}.DWB')
        slides[source_library] = importer.read_archive(folder / f'{source_library}.SLB')
    # 对整个 DWB 检查位宽和清表兼容性；仅选定项写入设备库。
    for source_library, entries in compressed.items():
        for value in entries.values():
            importer.decode_dwg(value)
        decoded_counts[source_library] = len(entries)
    for name, expected in report['source_sha256'].items():
        folder = source if name.startswith('Equip_U.') else system_source
        assert folder is not None
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected, name

    test = backend.DeviceLibraryTests(); test.setUp()
    root = test.fs(library); assets.DeviceAssetsTests.binary(test)
    snapshot = test.call('EL:DLSnapshotLoad', root)
    assert snapshot, test.h.lookup('*EL:DLERROR*')
    catalog = test.get('catalog', snapshot)
    assert truth(test.call('EL:DLCatalogValid', catalog))
    assert test.get('library-id', catalog) == report['library_id']
    rows = test.get('devices', catalog)
    assert len(rows) == len(report['items']) == report['count']
    assert test.get('next-id', catalog) == len(rows) + 1
    assert not truth(test.call('EL:DLIndex', catalog))
    names = test.call('EL:DLRecognitionNames', snapshot)
    assert len(names) == sum(1 + len(item.get('aliases', [])) for item in report['items'])
    for row, item, hashes in zip(rows, report['items'], report['assets'], strict=True):
        assert item['drawing'] == hashes['drawing']
        dwg = (library / test.get('block-file', row)).read_bytes()
        slide = (library / test.get('legend-file', row)).read_bytes()
        source_library = item.get('source_library', 'Equip_U')
        assert dwg == importer.decode_dwg(compressed[source_library][item['drawing']])
        assert slide == slides[source_library][item['drawing']]
        assert hashlib.sha256(dwg).hexdigest() == hashes['dwg_sha256']
        assert hashlib.sha256(slide).hexdigest() == hashes['slide_sha256']
        assert test.get('display', row) == item['display']
        assert (test.get('aliases', row) or []) == item.get('aliases', [])
        assert test.get('watts', row) is None
        assert test.get('active', row) is None
        assert test.get('zero-confirmed', row) is None
        assert test.get('status', row) == Symbol('DRAFT')
        assert truth(test.get('ground-confirmed', row))
        assert truth(test.get('is-ground', row)) == item.get('is_ground', False)
        assert truth(test.call('EL:DLDWGValid', str(library / test.get('block-file', row))))
        assert truth(test.call('EL:DLLegend', row, snapshot))
        assert test.get('legend-checksum', row) == importer.slide_checksum(slide)
        for name in test.call('EL:DLEntryNames', row):
            assert test.call('EL:DLFindEntry', name, snapshot) == row
            assert test.call('EL:DLLookup', name, snapshot) is None

    if 'baseline_count' in report:
        old_count = report['baseline_count']
        old_raw = (library / 'history' / f'{old_count}.eld').read_bytes()
        assert hashlib.sha256(old_raw).hexdigest() == report['baseline_catalog_sha256']
        old_catalog = test.call('EL:DLParse', old_raw.decode('utf-8'))
        assert test.get('library-id', old_catalog) == test.get('library-id', catalog)
        assert test.get('devices', old_catalog) == rows[:old_count]
        assert test.get('revision', catalog) > test.get('revision', old_catalog)

    files = {library.name + '/' + p.relative_to(library).as_posix(): p
             for p in library.rglob('*') if p.is_file()}
    with zipfile.ZipFile(package) as zipped:
        assert zipped.testzip() is None
        assert len(zipped.namelist()) == len(files)  # 同时拒绝重复成员。
        assert set(zipped.namelist()) == set(files)
        for name, path in files.items():
            assert zipped.read(name) == path.read_bytes(), name
    result = {'date': '2026-10-12', 'status': 'automated_checks_passed',
            'imported_count': len(rows), 'panel_count': sum(i['role'] == 'panel' for i in report['items']),
            'device_count': sum(i['role'] == 'device' for i in report['items']),
            'pending_selections': report['pending_selections'], 'watts_all_blank': True,
            'native_dwg_assets': len(rows), 'original_slide_assets': len(rows),
            'source_dwb_decoded_count': sum(decoded_counts.values()), 'source_dwb_decoded_counts': decoded_counts,
            'zip_file_count': len(files),
            'source_sha256': report['source_sha256'], 'package_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
            'checks': ['all DWB streams decoded with exact declared length and DWG magic',
                       'selected DWG bytes match decoded source; SLD bytes match original source',
                       'current EL:DLCatalogValid, draft recognition names and exact aliases',
                       'all powers blank, zero confirmation unset and entries inactive drafts',
                       'current EL:DLDWGValid, EL:DLLegend and checksum validation',
                       'source hashes unchanged; ZIP CRC, file set and bytes equal directory'],
            'native_cad_acceptance': 'pending'}
    if 'baseline_count' in report:
        result.update(baseline_count=report['baseline_count'], baseline_rows_preserved=True,
                      library_identity_preserved=True, catalog_history_preserved=True)
        result['checks'].append('baseline library identity, existing rows and catalog history preserved')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--system-source', type=Path)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--installed', type=Path, help='同时核对已安装库与迁移目录的完整文件集合及字节')
    args = parser.parse_args()
    result = check(args.source, args.library, args.zip, args.system_source)
    if args.installed:
        def contents(folder):
            return {p.relative_to(folder).as_posix(): p.read_bytes()
                    for p in folder.rglob('*') if p.is_file()}
        installed = contents(args.installed)
        assert installed == contents(args.library), '默认库与迁移库不一致'
        result.update(installed_default_root=str(args.installed.resolve()), installed_file_count=len(installed),
                      installed_bytes_equal_portable_library=True)
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: result[k] for k in ('imported_count', 'panel_count', 'device_count',
                      'source_dwb_decoded_count', 'zip_file_count', 'native_cad_acceptance')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
