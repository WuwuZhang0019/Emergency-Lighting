"""Verify all 096 CAD2020 loaded assets and entry points. Date: 2026-10-11."""
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
    spec = importlib.util.spec_from_file_location('empty_panel_builder', ROOT / 'tools/build_cad2020.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    assert builder.PACKAGE_NO == 96
    directory = builder.DEST
    regression = ROOT / 'tests/evidence/2026-10-11-empty-panel-096.json'
    evidence = json.loads(regression.read_text(encoding='utf-8'))
    assert evidence['passed'] and not evidence['failure_count'] and not evidence['error_count']
    for relative, expected in evidence['sha256'].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    source = {}
    for relative in ('src/panel.lsp', 'src/diagram-commands.lsp'):
        source.update(definitions((ROOT / relative).read_text(encoding='utf-8')))
    functions = ('EL:HistorySelect', 'EL:HistoryClick', 'EL:HistoryFill',
                 'EL:HistoryOpen', 'EL:PanelStartInit', 'EL:PanelStartDialog', 'EL:FixedStat')
    assets = []
    with zipfile.ZipFile(directory.with_suffix('.zip')) as archive:
        assert archive.testzip() is None
        disk_files = {p.relative_to(directory.parent).as_posix()
                      for p in directory.rglob('*') if p.is_file()}
        zip_files = {name for name in archive.namelist() if not name.endswith('/')}
        assert disk_files == zip_files
        for name in sorted(zip_files):
            raw = archive.read(name)
            assert raw == (directory.parent / name).read_bytes(), name
            if Path(name).suffix.lower() in ('.lsp', '.dcl'):
                text = raw.decode('gb2312', errors='strict')
                assert text.encode('gb2312', errors='strict') == raw
                if Path(name).suffix.lower() == '.lsp':
                    parse(text)
                assets.append({'path': name.split('/', 1)[1],
                               'sha256': hashlib.sha256(raw).hexdigest()})
        for entry in ('START-CAD2020.lsp', 'UPDATE-096.lsp', 'src/load.lsp'):
            packed = definitions(archive.read(builder.NAME + '/' + entry).decode('gb2312'))
            for name in functions:
                assert packed[Symbol(name.upper())] == source[Symbol(name.upper())], (entry, name)
        assert archive.read(builder.NAME + '/tests/evidence/' + regression.name) == regression.read_bytes()
        assert builder.NAME + '/package-096.marker' in zip_files
    report = {
        'date': '2026-10-11', 'package': 96, 'passed': True, 'asset_count': len(assets),
        'verified_regression_inputs': len(evidence['sha256']), 'assets': assets,
        'checks': ['strict GB2312', 'ZIP CRC and complete file-set/byte equality',
                   'all LISP parsing', 'three entry-point function AST comparisons',
                   'passing regression evidence and current source hashes'],
        'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'cad_status': 'pending; native empty-DWG ELSTAT behavior was not tested',
    }
    path = ROOT / 'tests/evidence/2026-10-11-empty-panel-package-096.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'096 package passed: {len(assets)} LISP/DCL assets; {len(functions)} functions in all three entries')
