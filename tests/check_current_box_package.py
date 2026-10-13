"""Focused CAD2020 delivery checks. Date: 2026-10-13. Native CAD acceptance pending."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

from autolisp_host import Symbol, parse
from test_current_box_optimization import CurrentBoxTests, TapeAndEntryTests

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('common', 'topology', 'diagram-store', 'store-split', 'diagram-update', 'diagram-commands')
FUNCTIONS = ('EL:MonitorLoadBegin', 'EL:PerfCall', 'EL:MonitorTitle',
             'EL:StoreReadCacheRemember', 'EL:StoreReadCachedScope', 'EL:CCKK2CreateDiagram',
             'EL:CreateDiagram', 'EL:StoreForResult', 'EL:SplitViewP', 'EL:SplitMetadata',
             'EL:SplitViewFromRoot', 'EL:SplitAuditReachable', 'EL:SplitCheckView', 'EL:SplitNewChunk',
             'EL:SplitBuild', 'EL:SplitWrite', 'EL:SplitVerifiedPayload', 'EL:SplitRememberVerified',
             'EL:ComponentIndex', 'EL:ComponentIndexTake',
             'EL:ComponentNeighbours', 'EL:Component', 'EL:PickStartPanel', 'EL:SyncDiagramScoped')


def definitions(text):
    return {form[1]: form for form in parse(text)
            if isinstance(form, list) and form and form[0] == Symbol('DEFUN')}


def check():
    spec = importlib.util.spec_from_file_location('builder', ROOT / 'tools/build_cad2020.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    directory, archive = builder.DEST, builder.DEST.with_suffix('.zip')
    evidence = ROOT / 'tests/evidence' / f'2026-10-13-current-box-source-{builder.PACKAGE_NO:03d}.json'
    regression = json.loads(evidence.read_text(encoding='utf-8'))
    assert regression['passed'] and not regression['errors'] and not regression['failures']
    for name, digest in regression['source_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    source = {}
    for module in SOURCES:
        source.update(definitions((ROOT / 'src' / f'{module}.lsp').read_text(encoding='utf-8')))
    entries = ('START-CAD2020.lsp', builder.UPDATE_NAME, 'src/load.lsp')
    assets, lisp_count, scenarios = [], 0, 0
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
        assert z.read(f'{builder.NAME}/tests/evidence/{evidence.name}') == evidence.read_bytes()
        for entry in entries:
            packed = definitions(z.read(f'{builder.NAME}/{entry}').decode('gb2312'))
            for name in FUNCTIONS:
                key = Symbol(name.upper())
                assert packed[key] == source[key], (entry, name)
            for cls, method in (
                    (CurrentBoxTests, 'test_read_hydrates_only_current_box_and_write_retains_other_blobs'),
                    (TapeAndEntryTests, 'test_native_generation_and_update_with_split_current_box_view')):
                fixture = cls(method)
                fixture.setUp()
                host = fixture.h if hasattr(fixture, 'h') else None
                if host:
                    for form in packed.values():
                        host.evaluate(form)
                # TapeAndEntryTests creates its host inside the test: intercept definition loading.
                if host:
                    getattr(fixture, method)()
                else:
                    from unittest.mock import patch
                    from autolisp_host import Host
                    original = Host.load_definitions
                    def load(instance, path):
                        original(instance, path)
                        for form in packed.values():
                            instance.evaluate(form)
                    with patch.object(Host, 'load_definitions', load):
                        getattr(fixture, method)()
                fixture.doCleanups()
                scenarios += 1
    report = {'date': '2026-10-13', 'status': 'completed', 'passed': True,
              'package': builder.PACKAGE_NO, 'regression_tests_run': regression['tests_run'],
              'lisp_dcl_count': len(assets), 'lisp_parsed': lisp_count, 'entry_scenarios': scenarios,
              'checked_entries': entries, 'checked_functions': FUNCTIONS,
              'checks': ['strict GB2312', 'all LISP parsing', 'ZIP CRC', 'all archive/directory bytes equal',
                         'changed source definitions equal all three entries', 'current box and generation entry scenarios'],
              'source_sha256': {f'src/{name}.lsp': hashlib.sha256((ROOT / 'src' / f'{name}.lsp').read_bytes()).hexdigest()
                                for name in SOURCES},
              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'native_cad_status': 'pending original DWG acceptance'}
    target = ROOT / 'tests/evidence' / f'2026-10-13-current-box-package-{builder.PACKAGE_NO:03d}.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{builder.NAME}: {len(assets)} GB2312 assets, {lisp_count} parsed LISP, {scenarios} entry scenarios passed')


if __name__ == '__main__':
    check()
