"""Focused generation-wait package verification.

Date: 2026-10-13. Status: automated package checks, native CAD pending.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

from autolisp_host import Symbol, parse

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('diagram-store', 'store-split', 'diagram-commands', 'diagram-update')
FUNCTIONS = ('EL:StorePayload', 'EL:SplitAudit', 'EL:SplitChunkValid',
             'EL:EditPanelOnce', 'EL:CCKK2DeferredSource',
             'EL:GenerationSourceCurrent', 'EL:SyncDiagramScoped')


def definitions(text):
    return {form[1]: form for form in parse(text)
            if isinstance(form, list) and form and form[0] == Symbol('DEFUN')}


def check():
    spec = importlib.util.spec_from_file_location('builder', ROOT / 'tools/build_cad2020.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    directory, archive = builder.DEST, builder.DEST.with_suffix('.zip')
    source = {}
    for module in SOURCES:
        source.update(definitions((ROOT / 'src' / f'{module}.lsp').read_text(encoding='utf-8')))
    entries = ('START-CAD2020.lsp', builder.UPDATE_NAME, 'src/load.lsp')
    assets, lisp_count = [], 0
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        files = {p.relative_to(directory.parent).as_posix() for p in directory.rglob('*') if p.is_file()}
        assert files == {name for name in z.namelist() if not name.endswith('/')}
        for name in sorted(files):
            raw = z.read(name)
            assert raw == (directory.parent / name).read_bytes(), name
            if Path(name).suffix.lower() in ('.lsp', '.dcl'):
                text = raw.decode('gb2312', errors='strict')
                assert text.encode('gb2312', errors='strict') == raw, name
                assets.append(name)
                if Path(name).suffix.lower() == '.lsp':
                    parse(text)
                    lisp_count += 1
        for entry in entries:
            packed = definitions(z.read(f'{builder.NAME}/{entry}').decode('gb2312'))
            for name in FUNCTIONS:
                key = Symbol(name.upper())
                assert packed[key] == source[key], (entry, name)
        for module in SOURCES:
            packed = definitions(z.read(f'{builder.NAME}/src/{module}.lsp').decode('gb2312'))
            for name, form in definitions((ROOT / 'src' / f'{module}.lsp').read_text(encoding='utf-8')).items():
                assert packed[name] == form, (module, name)
    report = {'date': '2026-10-13', 'status': 'completed', 'passed': True,
              'package': builder.PACKAGE_NO, 'lisp_dcl_count': len(assets),
              'lisp_parsed': lisp_count, 'checked_entries': entries, 'checked_functions': FUNCTIONS,
              'checks': ['strict GB2312', 'all LISP parsing', 'ZIP CRC', 'all archive/directory bytes equal',
                         'changed definitions equal all three entries and individual modules'],
              'source_sha256': {f'src/{name}.lsp': hashlib.sha256((ROOT / 'src' / f'{name}.lsp').read_bytes()).hexdigest()
                                for name in SOURCES},
              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'native_cad_status': 'pending original DWG timing and acceptance'}
    target = ROOT / 'tests/evidence' / f'2026-10-13-generation-wait-package-{builder.PACKAGE_NO:03d}.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{builder.NAME}: {len(assets)} GB2312 assets, {lisp_count} parsed LISP; all entries match')


if __name__ == '__main__':
    check()
