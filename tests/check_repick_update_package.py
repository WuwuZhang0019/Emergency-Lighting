"""Verify re-pick replacement and native numbered arms. Date: 2026-10-13."""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import unittest
import zipfile

from autolisp_host import Symbol, parse
import test_repick_update as repick

ROOT = Path(__file__).resolve().parents[1]
MODULES = ('test_repick_update', 'test_circuit_number', 'test_concentrated_trunk',
           'test_panel_number', 'test_diagram_update')
FUNCTIONS = ('EL:RecognitionRules', 'EL:NumberBranchCircuits', 'EL:SplitNativeNumberBranches',
             'EL:RecordForResult', 'EL:RepickRecord', 'EL:RepickConfig', 'EL:FixedStatPick',
             'EL:RecognizeFixed', 'EL:EditPanelOnce', 'EL:SaveDraft', 'EL:SyncDiagramScoped', 'EL:ApplyUpdate')


def definitions(text):
    return {form[1]: form for form in parse(text)
            if isinstance(form, list) and form and form[0] == Symbol('DEFUN')}


def check():
    suite = unittest.TestSuite()
    counts = {}
    for name in MODULES:
        tests = unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name))
        counts[name] = tests.countTestCases()
        suite.addTests(tests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    assert result.wasSuccessful(), 'Re-pick and update regression failed'
    spec = importlib.util.spec_from_file_location('repick_builder', ROOT / 'tools/build_cad2020.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    directory = builder.DEST
    archive = directory.with_suffix('.zip')
    source = {}
    for name in ('common', 'circuit-number', 'diagram-store', 'diagram-commands', 'diagram-update'):
        source.update(definitions((ROOT / 'src' / f'{name}.lsp').read_text(encoding='utf-8')))
    entries = ('START-CAD2020.lsp', builder.UPDATE_NAME, 'src/load.lsp')
    assets = []
    scenarios = (
        (repick.NumberedFeederTests, 'test_log_two_shared_feeders_become_six_sorted_numbered_circuits'),
        (repick.NumberedFeederTests, 'test_regular_repick_reaches_panel_with_native_branches_and_saved_target'),
        (repick.RepickTargetTests, 'test_real_sync_writes_replacement_under_same_id_without_new_panel'),
        (repick.RepickTargetTests, 'test_replacement_write_failure_rolls_back_old_output_and_binding'))
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
            for cls, method in scenarios:
                fixture = cls(method)
                fixture.setUp()
                for form in packed.values():
                    fixture.h.evaluate(form)
                try:
                    getattr(fixture, method)()
                finally:
                    fixture.doCleanups()
    report = {'date': '2026-10-13', 'status': 'completed', 'package': builder.PACKAGE_NO,
              'passed': True, 'source_tests_run': result.testsRun, 'module_test_counts': counts,
              'lisp_dcl_count': len(assets), 'checked_entries': entries, 'checked_functions': FUNCTIONS,
              'packaged_scenarios': [method for _, method in scenarios],
              'checks': ['ZIP CRC', 'all archive files equal package directory files',
                         'strict GB2312 roundtrip', 'all LISP parsing',
                         'changed definitions equal source AST', 'four scenarios in three loading entries'],
              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in ('src/common.lsp', 'src/circuit-number.lsp', 'src/diagram-store.lsp',
                                             'src/diagram-commands.lsp', 'src/diagram-update.lsp',
                                             'tests/test_repick_update.py', 'tests/check_repick_update_package.py',
                                             'tests/test_diagram_update.py',
                                             'tools/build_cad2020.py', '.gitignore')},
              'native_cad_status': 'pending; log-derived topology fixtures do not establish original DWG acceptance'}
    path = ROOT / 'tests/evidence' / f'2026-10-13-repick-update-package-{builder.PACKAGE_NO:03d}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{builder.NAME}: {result.testsRun} source tests, {len(assets)} GB2312 assets, 12 packaged scenarios passed')


if __name__ == '__main__':
    check()
