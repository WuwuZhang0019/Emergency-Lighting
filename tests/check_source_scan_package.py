"""Verify the complete 095 CAD2020 artifact. Date: 2026-10-11."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

from autolisp_host import Symbol, parse

ROOT = Path(__file__).resolve().parents[1]


def definitions(text):
    return {form[1]: form for form in parse(text)
        if isinstance(form, list) and form and form[0] == Symbol('DEFUN')}


if __name__ == '__main__':
    spec = importlib.util.spec_from_file_location('scan_builder', ROOT / 'tools/build_cad2020.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    assert builder.PACKAGE_NO == 95
    directory = builder.DEST
    archive = directory.with_suffix('.zip')
    regression = ROOT / 'tests/evidence/2026-10-11-source-scan-095.json'
    data = json.loads(regression.read_text(encoding='utf-8'))
    assert data['passed'] and not data['failure_count'] and not data['error_count']
    post_checks = data.get('post_test_checked_inputs', {})
    assert set(post_checks).issubset({'.gitignore'})
    if post_checks:
        rules = (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
        for rule in ('/output/cad2020-source-scan-check/', '/output/应急照明-095/', '/output/应急照明-095.zip'):
            assert rule in rules
    for relative, expected in data['sha256'].items():
        expected = post_checks.get(relative, {}).get('sha256', expected)
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    functions = (
        'EL:SimpleCollect', 'EL:DeviceContactShape', 'EL:NetworkGeometryCurrent',
        'EL:SimpleNetwork', 'EL:SimpleNetworkBuild',
        'EL:PerfStart', 'EL:PerfCall', 'EL:PerfFinish',
    )
    source = {}
    for path in (ROOT / 'src/simple.lsp', ROOT / 'src/common.lsp'):
        source.update(definitions(path.read_text(encoding='utf-8')))
    assets = []
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        disk_files = {p.relative_to(directory.parent).as_posix()
            for p in directory.rglob('*') if p.is_file()}
        zip_files = {name for name in z.namelist() if not name.endswith('/')}
        assert disk_files == zip_files
        for name in sorted(zip_files):
            raw = z.read(name)
            assert raw == (directory.parent / name).read_bytes(), name
            if Path(name).suffix.lower() in ('.lsp', '.dcl'):
                text = raw.decode('gb2312', errors='strict')
                assert text.encode('gb2312', errors='strict') == raw
                if Path(name).suffix.lower() == '.lsp':
                    parse(text)
                assets.append({'path': name.split('/', 1)[1],
                    'sha256': hashlib.sha256(raw).hexdigest()})
        for entry in ('START-CAD2020.lsp', 'UPDATE-095.lsp', 'src/load.lsp'):
            raw = z.read(builder.NAME + '/' + entry)
            packed = definitions(raw.decode('gb2312'))
            for name in functions:
                assert packed[Symbol(name.upper())] == source[Symbol(name.upper())], (entry, name)
            assert '(setq *EL:NetworkMemo* nil)' in raw.decode('gb2312')
        evidence = 'tests/evidence/' + regression.name
        assert z.read(builder.NAME + '/' + evidence) == regression.read_bytes()
        assert builder.NAME + '/package-095.marker' in zip_files
    report = {
        'date': '2026-10-11', 'package': 95, 'passed': True,
        'asset_count': len(assets), 'verified_regression_inputs': len(data['sha256']),
        'checks': ['strict GB2312', 'ZIP CRC', 'ZIP/directory file-set and byte equality',
            'all LISP parsing', 'three combined entries match source function AST',
            'network memo reset in each entry', 'passing regression evidence and matching source hashes'],
        'assets': assets,
        'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'post_test_artifact_checks': data.get('post_test_checked_inputs', {}),
        'cad_status': 'pending; package verification does not establish native CAD timing or DWG acceptance',
    }
    path = ROOT / 'tests/evidence/2026-10-11-source-scan-package-095.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'095 package checks passed: {len(assets)} LISP/DCL assets, {len(data["sha256"])} regression inputs')
