"""Current package/source checks. Date: 2026-10-12. No native CAD execution."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zipfile

from autolisp_host import parse, Symbol, Host, truth
from run_device_library_checks import EVIDENCE_DATE, PACKAGE_NO

ROOT = Path(__file__).resolve().parents[1]
NAME = f'应急照明-{PACKAGE_NO:03d}'
PACKAGE = ROOT / 'output' / NAME
MODULES = ('device-library', 'device-assets', 'device-defaults', 'device-ui', 'device-recognition', 'device-inputs', 'device-migration')


def definitions(text):
    return {str(form[1]): form for form in parse(text)
            if isinstance(form, list) and len(form) > 1 and form[0] == Symbol('DEFUN')}


def check(evidence_prefix='device-library'):
    assert evidence_prefix in ('device-library', 'recognition-preset')
    evidence_path = ROOT / f'tests/evidence/{EVIDENCE_DATE}-{evidence_prefix}-{PACKAGE_NO:03d}.json'
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    assert evidence['status'] == 'automated_passed' and evidence['failure_count'] == evidence['error_count'] == 0
    assert evidence['package'] == PACKAGE_NO and evidence['date'] == EVIDENCE_DATE
    for relative, digest in evidence['sha256'].items():
        # This validator runs after the regression suite; record its live hash separately.
        if relative == 'tests/check_device_library_package.py': continue
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest, relative
    archive = PACKAGE.with_suffix('.zip')
    hashes, parsed = {}, []
    expected = {path.relative_to(PACKAGE.parent).as_posix() for path in PACKAGE.rglob('*') if path.is_file()}
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist()))
        actual = {name for name in z.namelist() if not name.endswith('/')}
        assert actual == expected, (actual ^ expected)
        for name in sorted(actual):
            data = z.read(name)
            assert data == (PACKAGE.parent / name).read_bytes(), name
            relative = Path(name).relative_to(NAME).as_posix()
            assert not relative.startswith(('device-library/', 'drawing-inputs/'))
            assert Path(relative).name != '.write-lock'
            if Path(relative).name == 'catalog.eld':
                assert relative == 'assets/default-device-library/catalog.eld'
            if Path(name).suffix.lower() in ('.lsp', '.dcl'):
                text = data.decode('gb2312', errors='strict')
                assert text.encode('gb2312', errors='strict') == data, name
                hashes[relative] = hashlib.sha256(data).hexdigest()
                if Path(name).suffix.lower() == '.lsp': parse(text); parsed.append(relative)
        assert z.read(f'{NAME}/tests/evidence/{evidence_path.name}') == evidence_path.read_bytes()
    wanted = {}
    config = (ROOT / 'src/config.lsp').read_text(encoding='utf-8')
    config = config.replace('(open path "r" "utf8")', '(open path "r")').replace('(open tmp "w" "utf8")', '(open tmp "w")')
    assert config == (PACKAGE / 'src/config.lsp').read_bytes().decode('gb2312')
    wanted.update(definitions(config))
    for module in MODULES:
        source = (ROOT / 'src' / f'{module}.lsp').read_text(encoding='utf-8')
        packaged = (PACKAGE / 'src' / f'{module}.lsp').read_bytes().decode('gb2312')
        assert source == packaged
        wanted.update(definitions(source))
    # The source scanner's exact network/geometry checks remain present in every merged loader.
    for module in ('main', 'simple', 'geometry', 'topology', 'circuit-number', 'diagram-commands', 'diagram-update'):
        source = (ROOT / 'src' / f'{module}.lsp').read_text(encoding='utf-8')
        assert source == (PACKAGE / 'src' / f'{module}.lsp').read_bytes().decode('gb2312')
        wanted.update(definitions(source))
    panel = definitions((ROOT / 'src/panel.lsp').read_text(encoding='utf-8'))
    for name in ('EL:PANELSTARTINIT', 'EL:PANELSTARTDIALOG', 'EL:HISTORYSELECT', 'EL:HISTORYFILL',
                 'EL:PANELBLOCKPOWERCHANGED', 'EL:PANELDIALOG', 'EL:PANELACCEPT', 'EL:PANELCOMPUTE',
                 'EL:PANELGENERATE', 'EL:PANELGENERATEBODY', 'EL:PANELSTORE', 'EL:PANELTEXT',
                 'EL:SELECTIONSREADY',
                 'EL:THUMBDRAW', 'EL:THUMBCLEANUP', 'EL:THUMBPREPARE', 'EL:THUMBREFRESH',
                 'EL:THUMBCAPTURE', 'EL:THUMBPREPAREROWS', 'EL:THUMBBATCHNEXT', 'EL:THUMBBATCHRESUME',
                 'EL:GENERATIONMISSING', 'EL:GENERATIONPROBLEMS', 'EL:PANELGENERATIONFOCUS', 'EL:PANELGENERATIONBLOCKED'):
        wanted[name] = panel[name]
    update = f'UPDATE-{PACKAGE_NO:03d}.lsp'
    for entry in ('START-CAD2020.lsp', update, 'src/load.lsp'):
        actual = definitions((PACKAGE / entry).read_bytes().decode('gb2312'))
        for name, form in wanted.items(): assert actual.get(name) == form, (entry, name)
        if entry != update:
            startup = actual['EL:STARTUPEMBEDDEDROOT']
            embedded = {}
            def binaries(form):
                if not isinstance(form, list): return
                if len(form) == 3 and form[0] == Symbol('EL:STARTUPWRITELINES'):
                    assert form[1][:2] == [Symbol('STRCAT'), Symbol('ROOT')]
                    assert form[1][2].startswith(('src/', 'ui/'))
                if len(form) == 3 and form[0] == Symbol('EL:STARTUPWRITEBASE64'):
                    assert form[1][:2] == [Symbol('STRCAT'), Symbol('ROOT')]
                    relative = form[1][2]
                    assert relative.startswith('assets/default-device-library/')
                    chunks = form[2][1]
                    assert all(isinstance(c, str) and len(c) <= 192 for c in chunks)
                    embedded[relative] = base64.b64decode(''.join(chunks), validate=True)
                for child in form: binaries(child)
            binaries(startup)
            expected_defaults = {p.relative_to(ROOT).as_posix(): p.read_bytes()
                for p in (ROOT / 'assets/default-device-library').rglob('*') if p.is_file()}
            assert embedded == expected_defaults, entry
    for name in ('13_独立设备库与材料表管理方案.md', '14_独立设备库CAD验证与使用说明.md',
                 '更新记录/2026-10-11-主面板图例联动设备库-102.md',
                 '更新记录/2026-10-11-取消回路地面重复确认-103.md',
                 '更新记录/2026-10-12-主面板简化流程合并-104.md',
                 '更新记录/2026-10-12-105-识别预设与设备拾取.md',
                 '更新记录/2026-10-12-106-首次设备登记引导修复.md',
                 '更新记录/2026-10-12-107-设备拾取入库与图例生成提示修复.md',
                 '16_天正设备库圈选图块导入说明.md',
                 '更新记录/2026-10-12-108-默认设备库随包初始化.md'):
        assert (PACKAGE / 'docs' / name).read_bytes() == (ROOT / 'docs' / name).read_bytes()
    h = Host()
    for path in (ROOT / 'src').glob('*.lsp'): h.load_definitions(path)
    h.builtins['EL:LOGEVENT'] = lambda *a: None
    h.builtins['EXIT'] = lambda: (_ for _ in ()).throw(AssertionError('invalid default catalog'))
    catalog = h.call('EL:DLPARSE', [(PACKAGE / 'assets/default-device-library/catalog.eld').read_text(encoding='utf-8-sig')])
    assert truth(catalog)
    get = lambda key, row: h.call('EL:GET', [Symbol(key.upper()), row])
    rows = get('devices', catalog)
    assert len(rows) == 49
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('tianz', ROOT / 'tools/import_tianz_library.py')
    tianz = module_from_spec(spec); spec.loader.exec_module(tianz)
    default_hashes = {}
    for source in (ROOT / 'assets/default-device-library').rglob('*'):
        if source.is_file():
            relative = source.relative_to(ROOT).as_posix()
            assert (PACKAGE / relative).read_bytes() == source.read_bytes(), relative
            default_hashes[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    original_evidence = json.loads((ROOT / 'tests/evidence/2026-10-12-tianz-system-library-import.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'assets/default-device-library/import-manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['items']) == 49
    assert manifest['source_sha256'] == original_evidence['source_sha256']
    source_evidence = json.loads((ROOT / 'tests/evidence/2026-10-12-default-library-source.json').read_text(encoding='utf-8'))
    assert source_evidence['status'] == 'original_import_bytes_verified' and source_evidence['count'] == 49
    assert source_evidence['source_package_sha256'] == original_evidence['package_sha256']
    for relative, digest in source_evidence['seed_sha256'].items():
        assert default_hashes['assets/default-device-library/' + relative] == digest
    assert len(source_evidence['seed_sha256']) == 99
    com_path = ROOT / f'tests/evidence/{EVIDENCE_DATE}-default-library-com-{PACKAGE_NO:03d}.json'
    com_evidence = json.loads(com_path.read_text(encoding='utf-8'))
    assert com_evidence['status'] == 'windows_com_passed' and com_evidence['utf8_with_and_without_bom']
    assert com_evidence['binary_file_count'] == len(default_hashes)
    for relative, digest in com_evidence['default_sha256'].items():
        assert default_hashes['assets/default-device-library/' + relative] == digest
    assert (PACKAGE / 'tests/evidence' / com_path.name).read_bytes() == com_path.read_bytes()
    for row, asset_hashes in zip(rows, manifest['assets'], strict=True):
        assert get('watts', row) is None and get('zero-confirmed', row) is None
        assert not truth(get('active', row)) and get('status', row) == Symbol('DRAFT')
        assert truth(h.call('EL:DLENTRYASSETS', [row]))
        dwg = (PACKAGE / 'assets/default-device-library' / get('block-file', row)).read_bytes()
        slide = (PACKAGE / 'assets/default-device-library' / get('legend-file', row)).read_bytes()
        assert dwg.startswith(b'AC10')
        assert tianz.slide_checksum(slide) == get('legend-checksum', row)
        assert list(tianz.slide_geometry(slide)[2]) == get('legend-size', row)
        # Import evidence hashes are tied to the user's original DWB/SLB extraction.
        for key, hash_key in (('block-file', 'dwg_sha256'), ('legend-file', 'slide_sha256')):
            relative = get(key, row)
            assert default_hashes['assets/default-device-library/' + relative] == asset_hashes[hash_key]
    report = {
        'date': EVIDENCE_DATE, 'status': 'passed', 'package': PACKAGE_NO, 'native_cad_status': 'pending_user_validation',
        'regression_test_count': evidence['test_count'], 'strict_gb2312_files': len(hashes),
        'parsed_lisp_files': len(parsed), 'zip_crc_and_complete_byte_match': True,
        'merged_loader_entry_count': 3, 'new_modules': list(MODULES), 'sha256': hashes,
        'evidence_prefix': evidence_prefix,
        'bundled_default_count': 49, 'default_watts_blank': True,
        'default_asset_original_byte_match': True, 'embedded_default_byte_match': True,
        'default_sha256': default_hashes,
        'validator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'validator_sha256_at_regression': evidence['sha256']['tests/check_device_library_package.py'],
        'boundary': 'package encoding, file equality, config/recognition/module definitions and regression inputs only; native assets, UI and speed require CAD validation',
    }
    path = ROOT / f'tests/evidence/{EVIDENCE_DATE}-{evidence_prefix}-package-{PACKAGE_NO:03d}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'gb2312_files': len(hashes), 'parsed_lisp': len(parsed), 'regression_count': evidence['test_count'],
        'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'report': str(path)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-prefix', choices=('device-library', 'recognition-preset'), default='device-library')
    check(parser.parse_args().evidence_prefix)
