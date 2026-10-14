"""Verify the reachable-circuit AutoCAD 2020 package 131.

Date: 2026-10-13. Status: automated package checks; native CAD pending.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

from autolisp_host import Symbol, parse


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NO = 131
SOURCES = ('simple', 'geometry', 'diagram-update')
COMMON_FUNCTIONS = ('EL:RecognitionRules', 'EL:MonitorTitle')
ENTRIES = ('START-CAD2020.lsp', 'UPDATE-131.lsp', 'src/load.lsp')
REPORT = ROOT / 'tests/evidence/2026-10-13-reachable-package-131.json'


def definitions(text):
    return {form[1]: form for form in parse(text)
            if isinstance(form, list) and form and form[0] == Symbol('DEFUN')}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check():
    spec = importlib.util.spec_from_file_location('reachable_package_builder', ROOT / 'tools/build_cad2020.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    directory, archive = builder.DEST, builder.DEST.with_suffix('.zip')
    source_paths = [ROOT / 'src' / f'{name}.lsp' for name in (*SOURCES, 'common')]
    report = {
        'date': '2026-10-13', 'status': 'running', 'passed': False,
        'package': PACKAGE_NO, 'checkcount': 0,
        'source_sha256': {path.relative_to(ROOT).as_posix(): sha256(path) for path in source_paths},
        'builder_sha256': sha256(ROOT / 'tools/build_cad2020.py'),
        'archive_sha256': sha256(archive) if archive.is_file() else None,
        'checked_entries': ENTRIES, 'checked_source_modules': SOURCES,
        'checked_common_functions': COMMON_FUNCTIONS,
        'checks': ['strict GB2312 roundtrip for every LISP/DCL', 'parse every packaged LISP',
                   'ZIP CRC', 'exact archive/directory file set and file bytes',
                   'all changed module DEFUNs equal source and all three loading entries',
                   'selected common DEFUNs equal source, individual module and loading entries'],
        'native_cad_status': 'pending original DWG timing and acceptance',
    }

    def verify(condition, detail):
        if not condition:
            raise AssertionError(detail)
        report['checkcount'] += 1

    try:
        verify(builder.PACKAGE_NO == PACKAGE_NO, 'builder package must be 131')
        verify(builder.NAME == '应急照明-131', 'builder directory name must identify package 131')
        verify(builder.UPDATE_NAME == ENTRIES[1], 'builder update entry must be UPDATE-131.lsp')
        verify(directory.is_dir() and archive.is_file(), 'build package 131 before running this check')
        source = {module: definitions((ROOT / 'src' / f'{module}.lsp').read_text(encoding='utf-8'))
                  for module in SOURCES}
        common = definitions((ROOT / 'src/common.lsp').read_text(encoding='utf-8'))
        selected_common = {Symbol(name.upper()): common[Symbol(name.upper())] for name in COMMON_FUNCTIONS}
        assets, parsed, definitions_count = [], 0, 0
        with zipfile.ZipFile(archive) as packed:
            verify(packed.testzip() is None, 'ZIP CRC failure')
            archive_files = [name for name in packed.namelist() if not name.endswith('/')]
            verify(len(archive_files) == len(set(archive_files)), 'duplicate ZIP file entries')
            directory_files = {path.relative_to(directory.parent).as_posix()
                               for path in directory.rglob('*') if path.is_file()}
            verify(directory_files == set(archive_files), 'archive/directory file sets differ')
            packaged_definitions = {}
            for name in sorted(directory_files):
                raw = packed.read(name)
                verify(raw == (directory.parent / name).read_bytes(), f'archive/directory byte mismatch: {name}')
                suffix = Path(name).suffix.lower()
                if suffix not in ('.lsp', '.dcl'):
                    continue
                text = raw.decode('gb2312', errors='strict')
                verify(text.encode('gb2312', errors='strict') == raw, f'GB2312 roundtrip mismatch: {name}')
                assets.append(name)
                if suffix == '.lsp':
                    packaged_definitions[name] = definitions(text)
                    report['checkcount'] += 1  # Successful full LISP parse.
                    parsed += 1
            verify(bool(assets) and parsed > 0, 'package contains no LISP/DCL assets')
            expected = dict(selected_common)
            for module, forms in source.items():
                module_key = f'{builder.NAME}/src/{module}.lsp'
                forms_packed = packaged_definitions[module_key]
                verify(set(forms_packed) == set(forms), f'DEFUN set mismatch: src/{module}.lsp')
                for name, form in forms.items():
                    verify(forms_packed[name] == form, f'DEFUN mismatch: src/{module}.lsp {name}')
                    definitions_count += 1
                    if name in expected:
                        verify(expected[name] == form, f'conflicting source DEFUN: {name}')
                    expected[name] = form
            packed_common = packaged_definitions[f'{builder.NAME}/src/common.lsp']
            for name, form in selected_common.items():
                verify(packed_common.get(name) == form, f'common DEFUN mismatch: {name}')
            for entry in ENTRIES:
                forms_packed = packaged_definitions[f'{builder.NAME}/{entry}']
                for name, form in expected.items():
                    verify(forms_packed.get(name) == form, f'entry DEFUN mismatch: {entry} {name}')
        report.update({'status': 'completed', 'passed': True,
                       'archive_file_count': len(directory_files), 'lisp_dcl_count': len(assets),
                       'lisp_parsed': parsed, 'source_defun_count': definitions_count,
                       'entry_function_count': len(expected)})
    except Exception as exc:
        report.update({'status': 'failed', 'failure': f'{type(exc).__name__}: {exc}'})
        raise
    finally:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{builder.NAME}: {report["checkcount"]} checks passed; '
          f'{report["lisp_dcl_count"]} GB2312 assets, {report["lisp_parsed"]} parsed LISP')


if __name__ == '__main__':
    check()
