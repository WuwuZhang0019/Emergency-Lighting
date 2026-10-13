"""Source and CAD2020 junction package checks. Date: 2026-10-13."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import zipfile
from autolisp_host import Symbol, parse
import test_junction_box as junction
import test_simple_flow as simple
import test_gap_cross_circuit as gaps
import test_recognition_preset as preset
import test_circuit_number as numbering

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('common', 'config', 'simple', 'topology', 'panel', 'diagram-commands', 'diagram-update')
FUNCTIONS = ('EL:RecognitionRules', 'EL:RoleShape', 'EL:FixedBlockIdentity', 'EL:JunctionName',
             'EL:FixedBlockRole', 'EL:JunctionSamples', 'EL:CurrentJunctionConfig',
             'EL:JunctionCommandWork', 'c:ELJBOX', 'EL:PresetBlockAllowed', 'EL:PresetSelection',
             'EL:SimpleDevicePathHit', 'EL:JunctionTree', 'EL:JunctionAtPoint', 'EL:SimpleNetworkBuild',
             'EL:TraceCircuit', 'EL:CircuitSnapshot', 'EL:FixedOwnership', 'EL:SelectFixedExits',
             'EL:GenerationIssueText', 'EL:FixedStatPick', 'EL:FixedTrunkPick',
             'EL:RecognizeFixed', 'EL:FixedFreshSnapshot', 'EL:FreshResult')


def definitions(text):
    return {form[1]: form for form in parse(text)
            if isinstance(form, list) and form and form[0] == Symbol('DEFUN')}


def report_path(kind):
    return ROOT / 'tests/evidence' / f'2026-10-13-junction-{kind}-122.json'


def source_checks():
    loader = unittest.defaultTestLoader
    selected = []
    for test in loader.loadTestsFromTestCase(simple.SimpleFlowTests):
        if test._testMethodName != 'test_dialog_preview_restores_current_row_and_unsaved_values':
            selected.append(test)
    suite = unittest.TestSuite([
        loader.loadTestsFromModule(junction), unittest.TestSuite(selected),
        loader.loadTestsFromModule(gaps), loader.loadTestsFromTestCase(preset.PresetTests),
        loader.loadTestsFromModule(numbering)])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    assert result.wasSuccessful(), 'Focused source checks failed'
    data = {'date': '2026-10-13', 'passed': True, 'tests_run': result.testsRun,
            'junction_tests': loader.loadTestsFromModule(junction).countTestCases(),
            'scope': ['junction connection/branch/ownership/config/ELSTAT/plan',
                      'existing simple geometry and gaps', 'preset collection', 'circuit numbers'],
            'excluded': {'test_dialog_preview_restores_current_row_and_unsaved_values':
                         'unchanged baseline also fails: adapter lacks WCMATCH; unrelated dialog preview',
                         'SimplePersistenceTests': 'unchanged power file IO; outside junction scope'},
            'native_cad_status': 'pending original DWG acceptance'}
    report_path('source').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return data


def package_checks():
    spec = importlib.util.spec_from_file_location('junction_builder', ROOT / 'tools/build_cad2020.py')
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    archive = builder.DEST.with_suffix('.zip')
    baseline = {}
    for name in SOURCES:
        baseline.update(definitions((ROOT / 'src' / f'{name}.lsp').read_text(encoding='utf-8')))
    entries = ('START-CAD2020.lsp', builder.UPDATE_NAME, 'src/load.lsp')
    assets = []; lisp_count = 0
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        files = {p.relative_to(builder.DEST.parent).as_posix() for p in builder.DEST.rglob('*') if p.is_file()}
        assert files == {name for name in z.namelist() if not name.endswith('/')}
        for name in sorted(files):
            data = z.read(name)
            assert data == (builder.DEST.parent / name).read_bytes(), name
            if Path(name).suffix.lower() in ('.lsp', '.dcl'):
                text = data.decode('gb2312', errors='strict')
                assert text.encode('gb2312', errors='strict') == data, name
                if Path(name).suffix.lower() == '.lsp':
                    parse(text); lisp_count += 1
                assets.append(name)
        for entry in entries:
            packed = definitions(z.read(f'{builder.NAME}/{entry}').decode('gb2312'))
            for name in FUNCTIONS:
                key = Symbol(name.upper())
                assert packed[key] == baseline[key], (entry, name)
            for method in ('test_actual_elstat_reaches_panel_and_system_plan_with_five_lamps',
                           'test_command_saves_reloads_then_removes_classification',
                           'test_selected_exits_conflict_before_device_exclusion_and_recompute'):
                fixture = junction.JunctionTests(method); fixture.setUp()
                for form in packed.values():
                    fixture.h.evaluate(form)
                try:
                    getattr(fixture, method)()
                finally:
                    fixture.doCleanups()
    data = {'date': '2026-10-13', 'package': builder.PACKAGE_NO, 'passed': True,
            'lisp_dcl_count': len(assets), 'lisp_parsed': lisp_count, 'entries': entries,
            'entry_scenarios': 9, 'definition_count': len(FUNCTIONS),
            'checks': ['ZIP CRC', 'all archive/directory bytes equal', 'all strict GB2312 roundtrip',
                       'all LISP parsing', 'source definitions equal three entries',
                       'ELSTAT five-lamp panel/system plan', 'ELJBOX save/remove', 'shared junction conflict'],
            'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'source_sha256': {f'src/{name}.lsp': hashlib.sha256((ROOT / 'src' / f'{name}.lsp').read_bytes()).hexdigest()
                              for name in SOURCES},
            'native_cad_status': 'pending original DWG acceptance'}
    report_path('package').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{builder.NAME}: {len(assets)} GB2312 assets, {lisp_count} parsed LISP, 9 entry scenarios passed')


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--source-only', action='store_true')
    options = args.parse_args()
    if options.source_only:
        source_checks()
    else:
        package_checks()
