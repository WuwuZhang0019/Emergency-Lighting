"""Date: 2026-10-14. GB2312 package and loading-entry parity; no native CAD acceptance."""
import base64
import hashlib
import json
from pathlib import Path
import re
import zipfile

from autolisp_host import parse

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = {
    'common': ['EL:PERFCALL', 'EL:MONITORTITLE'],
    'diagram-commands': ['EL:SAVEDRAFT'],
    'diagram-store': ['EL:STORESTRINGCHUNKS', 'EL:STOREENCODE', 'EL:STOREDECODE'],
    'store-compact': ['EL:COMPACTPROPERLIST', 'EL:COMPACTENCODE'],
    'store-split': ['EL:SPLITWRITE'],
}


def definitions(text):
    return {form[1]: form for form in parse(text)
            if isinstance(form, list) and form[0] == 'DEFUN'}


def check_package(number, functions):
    """Shared full-package check for each storage optimization delivery."""
    package = ROOT / f'output/应急照明-{number:03d}'
    archive_path = package.with_suffix('.zip')
    files = {p.relative_to(package).as_posix(): p for p in package.rglob('*') if p.is_file()}
    parsed, encoded = {}, 0
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        entries = {entry.filename.split('/', 1)[1]: entry
                   for entry in archive.infolist() if not entry.is_dir()}
        assert set(entries) == set(files)
        for relative, path in files.items():
            raw = path.read_bytes()
            assert raw == archive.read(entries[relative]), relative
            if path.suffix.lower() in ('.lsp', '.dcl'):
                assert not raw.startswith(b'\xef\xbb\xbf'), relative
                text = raw.decode('gb2312', errors='strict')
                assert text.encode('gb2312', errors='strict') == raw
                encoded += 1
                if path.suffix.lower() == '.lsp': parsed[relative] = definitions(text)
    checked = []
    for module, names in functions.items():
        source = definitions((ROOT / 'src' / f'{module}.lsp').read_text(encoding='utf-8'))
        for name in names:
            for entry in (f'src/{module}.lsp', 'START-CAD2020.lsp', 'src/load.lsp', f'UPDATE-{number:03d}.lsp'):
                assert source[name] == parsed[entry][name], (entry, name)
            checked.append(name)
    startup = (package / 'START-CAD2020.lsp').read_bytes().decode('gb2312')
    resources = re.findall(r"EL:StartupWriteBase64 \(strcat root \"([^\"]+)\"\)\s*'\((.*?)\)\)",
                           startup, flags=re.S)
    expected = {name for name in files if name.startswith('assets/default-device-library/') or
                name.startswith('ui/') or (name.startswith('src/') and name != 'src/load.lsp')}
    # The embedded load entry is the small module loader generated before the standalone entry.
    assert {name for name, _ in resources} == expected | {'src/load.lsp'}
    for name, literals in resources:
        raw = base64.b64decode(''.join(re.findall(r'"([A-Za-z0-9+/=]*)"', literals)), validate=True)
        if name == 'src/load.lsp':
            assert f'CAD2020 v{number}' in raw.decode('gb2312')
        else:
            assert raw == files[name].read_bytes(), name
    return {'date': '2026-10-14', 'status': 'passed', 'package': number,
              'files': len(files), 'gb2312_lisp_dcl': encoded, 'parsed_lisp': len(parsed),
              'loading_entry_functions': checked, 'embedded_resources': len(resources),
              'archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
              'checks': ['ZIP CRC', 'all archive and extracted bytes match',
                         'strict GB2312 without BOM', 'all LISP parsing',
                         'changed definitions match all three loading entries',
                         'embedded runtime resources match generated delivery modules']}


if __name__ == '__main__':
    result = check_package(137, FUNCTIONS)
    result.update({'focused_regression_cases': 79,
                   'native_cad_status': '137 first-save timing pending; two-second target not yet verified'})
    output = ROOT / 'tests/evidence/2026-10-14-store-write-package-137.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
