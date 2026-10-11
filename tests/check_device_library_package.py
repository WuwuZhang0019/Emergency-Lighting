"""Current package/source checks. Date: 2026-10-12. No native CAD execution."""
import hashlib
import json
from pathlib import Path
import zipfile

from autolisp_host import parse, Symbol
from run_device_library_checks import EVIDENCE_DATE, PACKAGE_NO

ROOT = Path(__file__).resolve().parents[1]
NAME = f'应急照明-{PACKAGE_NO:03d}'
PACKAGE = ROOT / 'output' / NAME
MODULES = ('device-library', 'device-assets', 'device-ui', 'device-recognition', 'device-inputs', 'device-migration')


def definitions(text):
    return {str(form[1]): form for form in parse(text)
            if isinstance(form, list) and len(form) > 1 and form[0] == Symbol('DEFUN')}


def check():
    evidence = json.loads((ROOT / f'tests/evidence/{EVIDENCE_DATE}-device-library-{PACKAGE_NO:03d}.json').read_text(encoding='utf-8'))
    assert evidence['status'] == 'automated_passed' and evidence['failure_count'] == evidence['error_count'] == 0
    for relative, digest in evidence['sha256'].items():
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
            assert Path(relative).name not in ('catalog.eld', '.write-lock')
            if Path(name).suffix.lower() in ('.lsp', '.dcl'):
                text = data.decode('gb2312', errors='strict')
                assert text.encode('gb2312', errors='strict') == data, name
                hashes[relative] = hashlib.sha256(data).hexdigest()
                if Path(name).suffix.lower() == '.lsp': parse(text); parsed.append(relative)
    wanted = {}
    for module in MODULES:
        source = (ROOT / 'src' / f'{module}.lsp').read_text(encoding='utf-8')
        packaged = (PACKAGE / 'src' / f'{module}.lsp').read_bytes().decode('gb2312')
        assert source == packaged
        wanted.update(definitions(source))
    # The source scanner's exact network/geometry checks remain present in every merged loader.
    for module in ('simple', 'geometry', 'topology', 'circuit-number', 'diagram-commands', 'diagram-update'):
        source = (ROOT / 'src' / f'{module}.lsp').read_text(encoding='utf-8')
        assert source == (PACKAGE / 'src' / f'{module}.lsp').read_bytes().decode('gb2312')
        wanted.update(definitions(source))
    panel = definitions((ROOT / 'src/panel.lsp').read_text(encoding='utf-8'))
    for name in ('EL:PANELSTARTINIT', 'EL:PANELSTARTDIALOG', 'EL:HISTORYSELECT', 'EL:HISTORYFILL',
                 'EL:PANELBLOCKPOWERCHANGED', 'EL:PANELDIALOG', 'EL:PANELACCEPT', 'EL:PANELCOMPUTE',
                 'EL:PANELGENERATE', 'EL:PANELGENERATEBODY', 'EL:PANELSTORE', 'EL:PANELTEXT',
                 'EL:SELECTIONSREADY',
                 'EL:THUMBDRAW', 'EL:THUMBCLEANUP', 'EL:THUMBPREPARE', 'EL:THUMBREFRESH',
                 'EL:THUMBCAPTURE', 'EL:THUMBPREPAREROWS'):
        wanted[name] = panel[name]
    update = f'UPDATE-{PACKAGE_NO:03d}.lsp'
    for entry in ('START-CAD2020.lsp', update, 'src/load.lsp'):
        actual = definitions((PACKAGE / entry).read_bytes().decode('gb2312'))
        for name, form in wanted.items(): assert actual.get(name) == form, (entry, name)
        if entry != update:
            startup = actual['EL:STARTUPEMBEDDEDROOT']
            assert 'device-library/catalog.eld' not in str(startup)
    for name in ('13_独立设备库与材料表管理方案.md', '14_独立设备库CAD验证与使用说明.md',
                 '更新记录/2026-10-11-主面板图例联动设备库-102.md',
                 '更新记录/2026-10-11-取消回路地面重复确认-103.md',
                 '更新记录/2026-10-12-主面板简化流程合并-104.md'):
        assert (PACKAGE / 'docs' / name).read_bytes() == (ROOT / 'docs' / name).read_bytes()
    report = {
        'date': EVIDENCE_DATE, 'status': 'passed', 'package': PACKAGE_NO, 'native_cad_status': 'pending_user_validation',
        'regression_test_count': evidence['test_count'], 'strict_gb2312_files': len(hashes),
        'parsed_lisp_files': len(parsed), 'zip_crc_and_complete_byte_match': True,
        'merged_loader_entry_count': 3, 'new_modules': list(MODULES), 'sha256': hashes,
        'boundary': 'package encoding, file equality, actual module definitions and regression inputs only; native assets, UI and speed require CAD validation',
    }
    path = ROOT / f'tests/evidence/{EVIDENCE_DATE}-device-library-package-{PACKAGE_NO:03d}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'gb2312_files': len(hashes), 'parsed_lisp': len(parsed), 'regression_count': evidence['test_count'],
        'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'report': str(path)}, ensure_ascii=False))


if __name__ == '__main__': check()
