"""Check ZE sorting in source and CAD2020 loading entries. Date: 2026-10-13."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import zipfile

from autolisp_host import Symbol, parse
import test_circuit_number as numbering

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ('EL:ZENumberIndex', 'EL:SortCircuitNumbers', 'EL:PreparedResult')


def definitions(text):
    return {form[1]: form for form in parse(text)
            if isinstance(form, list) and form and form[0] == Symbol('DEFUN')}


def check():
    result = unittest.TextTestRunner(verbosity=1).run(
        unittest.defaultTestLoader.loadTestsFromModule(numbering))
    assert result.wasSuccessful(), 'Source numbering regression failed'
    spec = importlib.util.spec_from_file_location('sort_builder', ROOT / 'tools/build_cad2020.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    directory = builder.DEST
    archive = directory.with_suffix('.zip')
    source = {}
    for name in ('circuit-number', 'diagram-update'):
        source.update(definitions((ROOT / 'src' / f'{name}.lsp').read_text(encoding='utf-8')))
    entries = ('START-CAD2020.lsp', builder.UPDATE_NAME, 'src/load.lsp')
    assets = []
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        files = {p.relative_to(directory.parent).as_posix() for p in directory.rglob('*') if p.is_file()}
        assert files == {name for name in z.namelist() if not name.endswith('/')}
        for name in sorted(files):
            data = z.read(name)
            assert data == (directory.parent / name).read_bytes(), name
            if Path(name).suffix.lower() in ('.lsp', '.dcl'):
                text = data.decode('gb2312', errors='strict')
                assert text.encode('gb2312', errors='strict') == data, name
                if Path(name).suffix.lower() == '.lsp':
                    parse(text)
                assets.append(name.split('/', 1)[1])
        for entry in entries:
            packed = definitions(z.read(f'{builder.NAME}/{entry}').decode('gb2312'))
            for name in FUNCTIONS:
                key = Symbol(name.upper())
                assert packed[key] == source[key], (entry, name)
            fixture = numbering.NumberWorkflowTests('test_actual_elstat_pick_five_plane_numbers_reach_panel_and_plan')
            fixture.setUp()
            for form in packed.values():
                fixture.h.evaluate(form)
            try:
                fixture.test_actual_elstat_pick_five_plane_numbers_reach_panel_and_plan()
            finally:
                fixture.doCleanups()
    report = {'date': '2026-10-13', 'status': 'completed', 'package': builder.PACKAGE_NO,
              'passed': True, 'source_tests_run': result.testsRun, 'lisp_dcl_count': len(assets),
              'checked_entries': entries, 'checked_functions': FUNCTIONS,
              'checks': ['ZIP CRC', 'all archive files equal package directory files',
                         'strict GB2312 roundtrip', 'all LISP parsing',
                         'changed definitions equal source AST',
                         'ELSTAT five circuits sorted in panel and system plan in three entries'],
              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in ('src/circuit-number.lsp', 'src/diagram-update.lsp',
                                             'tests/test_circuit_number.py', 'tests/check_circuit_sort_package.py',
                                             'tools/build_cad2020.py', '.gitignore')},
              'native_cad_status': 'pending; bounded adapters do not establish original DWG acceptance'}
    path = ROOT / 'tests/evidence' / f'2026-10-13-circuit-sort-package-{builder.PACKAGE_NO:03d}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{builder.NAME}: {result.testsRun} source tests, {len(assets)} GB2312 assets, 3 entry workflows passed')


if __name__ == '__main__':
    check()
