"""Date: 2026-10-15. Finite CAD adapter plus real Windows PowerShell ZIP I/O."""
import base64
import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from autolisp_host import Pair, Symbol, parse
from test_diagram_store import dump
from monitor_io import install_monitor_io
import test_diagnostic_export as diagnostic

ROOT = Path(__file__).resolve().parents[1]
CHECK_ROOT = ROOT / 'output/diagnostic-bundle-145-check'


class DiagnosticBundleTests(unittest.TestCase):
    def setUp(self):
        CHECK_ROOT.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=CHECK_ROOT, prefix="中文 & ' [目录] %TEMP% ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('src', 'output', 'temp'):
            (self.root / name).mkdir()
        shutil.copy2(ROOT / 'src/diagnostic-bundle.ps1', self.root / 'src/diagnostic-bundle.ps1')
        self.f = diagnostic.DiagnosticExportTests()
        self.f.setUp()
        self.h = self.f.h
        self.h.builtins.pop('EL:DIAGNOSTICBUNDLE')
        self.h.load_definitions(ROOT / 'src/startup.lsp')
        self.h.frames[0]['*EL:ROOT*'] = self.root.as_posix() + '/'
        self.h.frames[0]['*EL:PACKAGEMARKER*'] = 'package-145.marker'
        self.h.frames[0][':VLAX-TRUE'] = True
        self.run = [Pair(Symbol('EVENTS'), [[1, 'EXAMPLE', '原始日志' * 5000]])]
        self.h.frames[0]['*EL:DIAGNOSTICRUNS*'] = [Pair('NOD', self.run)]
        self.timeline = self.root / 'output/timeline.md'
        self.timeline.write_text('# 完整时间轴\n日期：2026-10-15\n状态：已记录\n', encoding='utf-8')
        getvar = self.h.builtins['GETVAR']
        variables = {'TEMPPREFIX': (self.root / 'temp').as_posix() + '/',
                     'CDATE': 20261015.123456, 'DWGNAME': '测试图纸.dwg',
                     'DWGPREFIX': 'G:/设计/', 'ACADVER': '23.1'}
        self.processes = []
        self.h.builtins.update({
            'GETVAR': lambda name: variables[name] if name in variables else getvar(name),
            'GETENV': lambda name: os.environ.get(name),
            'OPEN': lambda path, mode, *encoding: open(path, mode, encoding=encoding[0] if encoding else 'gb2312'),
            'READ-LINE': lambda file: (line.rstrip('\r\n') if (line := file.readline()) else None),
            'CLOSE': lambda file: file.close(),
            'PRIN1': lambda value, file: file.write(dump(value)) and value,
            'WRITE-LINE': lambda value, file: file.write(value + '\n'),
            'VL-FILENAME-BASE': lambda path: Path(path).stem,
            'EL:EXPORTDIAGNOSTICRUN': lambda: str(self.timeline),
            'FINDFILE': lambda path: str(path) if Path(path).is_file() else None,
            'VL-FILE-DIRECTORY-P': lambda path: Path(path).is_dir(),
            'VL-MKDIR': lambda path: Path(path).mkdir() or True,
            'VL-FILE-COPY': lambda src, dst: shutil.copyfile(src, dst) and Path(dst).stat().st_size,
            'VL-FILE-SIZE': lambda path: Path(path).stat().st_size,
            'VL-STRING-TRANSLATE': lambda old, new, text: text.translate(str.maketrans(old, new)),
            'VL-STRING-SUBST': lambda new, old, text: text.replace(old, new, 1),
        })
        self.streams = install_monitor_io(self.h)
        create = self.h.builtins['VLAX-CREATE-OBJECT']
        invoke = self.h.builtins['VLAX-INVOKE-METHOD']
        def com_create(name):
            if name == 'ADODB.Stream':
                return create(name)
            self.assertIn(name, ('MSXML2.DOMDocument.6.0', 'WScript.Shell'))
            return {'kind': name}
        def com_invoke(obj, method, *args):
            method = str(method).upper()
            if method == 'CREATEELEMENT':
                return {'kind': 'node'}
            if method == 'READ':
                self.assertEqual(obj['CHARSET'], 'unicode')
                self.assertEqual(obj['TYPE'], 1)
                return (b'\xff\xfe' + obj['text'].encode('utf-16-le'))[obj['POSITION']:]
            if method == 'LOADFROMFILE':
                encoding = 'utf-8-sig' if obj['CHARSET'] == 'utf-8' else obj['CHARSET']
                obj['text'] = Path(args[0]).read_text(encoding=encoding)
                return None
            if method == 'READTEXT':
                self.assertEqual(args, (-1,))
                return obj['text']
            if method == 'RUN':
                self.assertEqual(args[1:], (0, True), 'hidden process must finish before success')
                self.processes.append(args[0])
                return subprocess.run(args[0], capture_output=True, timeout=45,
                                      creationflags=subprocess.CREATE_NO_WINDOW).returncode
            return invoke(obj, method, *args)
        self.h.builtins.update({
            'VLAX-CREATE-OBJECT': com_create,
            'VLAX-INVOKE-METHOD': com_invoke,
            'VLAX-GET-PROPERTY': lambda obj, key: base64.encodebytes(obj['NODETYPEDVALUE']).decode('ascii'),
        })

    def export(self):
        return Path(self.h.run('(EL:DiagnosticExport)'))

    def test_complete_bundle_exact_bytes_special_paths_no_dwg_writes_and_unique_names(self):
        before = self.f.before()
        raw = '历史事件\r\n'.encode('gb2312')
        (self.root / 'output/ELTRACE-debug.log').write_bytes(raw)
        (self.root / 'output/ELPERF.log').write_bytes(b'perf\r\n')
        (self.root / 'temp/ELPERF.log').write_bytes(b'fallback perf\r\n')
        (self.root / 'output/unrelated.dwg').write_bytes(b'not a log')
        zip_path = self.export()
        with zipfile.ZipFile(zip_path) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), {
                'README.md', 'manifest.eld', 'association.eld', 'drawing-store.eld',
                'current-result.eld', 'run.eld', 'timeline.md', 'progress.log', 'runtime-ELTRACE-debug.log',
                'runtime-ELPERF.log', 'temp-ELPERF.log'})
            self.assertEqual(archive.read('runtime-ELTRACE-debug.log'), raw)
            self.assertEqual(archive.read('timeline.md'), self.timeline.read_bytes())
            self.assertIn('原始日志' * 5000, archive.read('run.eld').decode('utf-8-sig'))
            record = self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
            self.assertEqual(archive.read('association.eld').decode('utf-8-sig').strip(),
                             self.h.builtins['VL-PRIN1-TO-STRING'](record))
            progress = archive.read('progress.log').decode('ascii')
            self.assertIn('FILE_DONE drawing-store', progress)
            self.assertIn('FILE_DONE current-result', progress)
            self.assertIn('ZIP_BEGIN', progress)
        self.assertNotIn('/', str(self.h.lookup('*EL:DIAGNOSTICEXPORTPATH*')))
        self.assertFalse(zip_path.with_suffix('').exists(), 'successful snapshot cleanup')
        first_bytes = zip_path.read_bytes()
        second = self.export()
        self.assertNotEqual(second, zip_path)
        self.assertEqual(first_bytes, zip_path.read_bytes())
        self.f.assert_business_unchanged(before)
        self.assertTrue(all(s['closed'] and s['released'] for s in self.streams))

    def test_invalid_association_keeps_logs_and_explains_missing_record(self):
        del self.f.fixture.entities['t0']
        with zipfile.ZipFile(self.export()) as archive:
            self.assertNotIn('association.eld', archive.namelist())
            self.assertIn('timeline.md', archive.namelist())
            self.assertIn('系统图成员缺失', archive.read('README.md').decode('utf-8-sig'))
            self.assertIn('UNAVAILABLE', archive.read('manifest.eld').decode('utf-8-sig'))

    def test_no_run_or_saved_output_still_exports_load_snapshot_with_missing_notes(self):
        self.h.frames[0]['*EL:DIAGNOSTICRUNS*'] = None
        self.h.frames[0]['*EL:RESULT*'] = None
        self.h.builtins['EL:STOREREAD'] = lambda: None
        self.h.builtins['EL:EXPORTDIAGNOSTICRUN'] = lambda: None
        self.h.frames[0]['*EL:MONITORLOADSUMMARY*'] = [Pair(Symbol('COMMAND'), 'APPLOAD')]
        self.h.frames[0]['*EL:MONITORLOADSTAMP*'] = '20261015.120000'
        with zipfile.ZipFile(self.export()) as archive:
            self.assertEqual(set(archive.namelist()), {'README.md', 'manifest.eld', 'load.eld', 'progress.log'})
            self.assertIn('APPLOAD', archive.read('load.eld').decode('utf-8-sig'))
            self.assertIn('run.eld：本次会话没有可用资料', archive.read('README.md').decode('utf-8-sig'))

    def test_zip_failure_retains_snapshot_exposes_folder_and_never_claims_success(self):
        script = self.root / 'src/diagnostic-bundle.ps1'
        script.write_text('exit 7\n', encoding='ascii')
        message = self.h.run('(EL:PanelDiagnosticExport)')
        self.assertIn('诊断压缩失败', message)
        folder = Path(self.h.lookup('*EL:DIAGNOSTICEXPORTPATH*'))
        self.assertTrue((folder / 'association.eld').is_file())
        self.assertFalse(Path(str(folder) + '.zip').exists())
        self.assertEqual(self.h.lookup('*EL:DIAGNOSTICEXPORTMESSAGE*'), message)
        self.assertIn('PowerShell exit code=7', message)
        report = (folder / 'export-error.txt').read_text(encoding='utf-8-sig')
        self.assertIn(message, report)
        self.assertIn('stage: ZIP_EXIT 7', report)
        self.assertIn('package-145.marker', report)

    def test_com_launch_failure_is_saved_and_next_export_clears_old_failure(self):
        create = self.h.builtins['VLAX-CREATE-OBJECT']
        def fail_shell(name):
            if name == 'WScript.Shell':
                raise RuntimeError('Automation Error 80070005: Access denied')
            return create(name)
        self.h.builtins['VLAX-CREATE-OBJECT'] = fail_shell
        message = self.h.run('(EL:PanelDiagnosticExport)')
        folder = Path(self.h.lookup('*EL:DIAGNOSTICEXPORTPATH*'))
        report = (folder / 'export-error.txt').read_text(encoding='utf-8-sig')
        self.assertIn('Automation Error 80070005: Access denied', message)
        self.assertIn('stage: ZIP_LAUNCH', report)
        self.assertIn(message, report)
        self.assertTrue((folder / 'association.eld').is_file())
        self.h.builtins['VLAX-CREATE-OBJECT'] = create
        success = self.h.run('(EL:PanelDiagnosticExport)')
        self.assertIn('已导出诊断包', success)
        self.assertFalse(self.h.lookup('*EL:DIAGNOSTICERROR*'))
        with zipfile.ZipFile(self.h.lookup('*EL:DIAGNOSTICEXPORTPATH*')) as archive:
            self.assertNotIn('export-error.txt', archive.namelist())
        self.assertEqual((folder / 'export-error.txt').read_text(encoding='utf-8-sig'), report)

    def test_encoded_command_failure_keeps_raw_com_error_and_stage(self):
        create = self.h.builtins['VLAX-CREATE-OBJECT']
        def fail_xml(name):
            if name == 'MSXML2.DOMDocument.6.0':
                raise RuntimeError('Class not registered 80040154')
            return create(name)
        self.h.builtins['VLAX-CREATE-OBJECT'] = fail_xml
        message = self.h.run('(EL:PanelDiagnosticExport)')
        folder = Path(self.h.lookup('*EL:DIAGNOSTICEXPORTPATH*'))
        self.assertIn('Class not registered 80040154', message)
        self.assertIn('stage: ZIP_ENCODE', (folder / 'export-error.txt').read_text(encoding='utf-8-sig'))
        self.assertEqual(self.processes, [])

    def test_failure_report_write_error_does_not_replace_original_com_failure(self):
        create = self.h.builtins['VLAX-CREATE-OBJECT']
        write = self.h.builtins['VLAX-INVOKE-METHOD']
        def fail_shell(name):
            if name == 'WScript.Shell':
                raise RuntimeError('original launch error')
            return create(name)
        def fail_report(obj, method, *args):
            if str(method).upper() == 'SAVETOFILE' and str(args[0]).endswith('export-error.txt'):
                raise OSError('secondary report write error')
            return write(obj, method, *args)
        self.h.builtins['VLAX-CREATE-OBJECT'] = fail_shell
        self.h.builtins['VLAX-INVOKE-METHOD'] = fail_report
        message = self.h.run('(EL:PanelDiagnosticExport)')
        self.assertIn('original launch error', message)
        self.assertNotIn('secondary report write error', message)
        self.assertEqual(self.h.lookup('*EL:DIAGNOSTICEXPORTMESSAGE*'), message)
        self.assertIn('original launch error', self.h.lookup('*EL:DIAGNOSTICERROR*'))

    def test_existing_zip_is_never_overwritten_by_helper(self):
        folder = self.root / 'output/ELDIAG-20261015.123456'
        folder.mkdir()
        (folder / 'README.md').write_text('diagnostic', encoding='utf-8')
        target = Path(str(folder) + '.zip')
        target.write_bytes(b'previous archive')
        with self.assertRaises(RuntimeError):
            self.f.fixture.call('EL:DiagnosticZip', str(folder))
        self.assertIn('诊断压缩失败', self.h.lookup('*EL:DIAGNOSTICERROR*'))
        self.assertEqual(target.read_bytes(), b'previous archive')
        self.assertTrue((folder / 'bundle-error.txt').is_file())

    def test_open_location_quotes_windows_path_and_missing_file_does_not_launch(self):
        path = self.export()
        opened = []
        self.h.builtins['STARTAPP'] = lambda *args: opened.append(args) or 33
        self.f.fixture.call('EL:DiagnosticOpenFolder', path.as_posix())
        self.assertEqual(opened, [('explorer.exe', '/select,"' + str(path) + '"')])
        self.f.fixture.call('EL:DiagnosticOpenFolder', str(path) + '.missing')
        self.assertEqual(len(opened), 1)

    def test_large_saved_record_uses_native_file_print_without_building_lisp_print_string(self):
        value = [Pair(Symbol('PAYLOAD'), 'x' * 3_000_000 + '完整中文记录')]
        self.h.builtins['VL-PRIN1-TO-STRING'] = lambda *args: self.fail('whole-record string formatting')
        path = self.root / 'output/large-store.eld'
        self.f.fixture.call('EL:DiagnosticWriteData', str(path), value)
        self.assertEqual(path.read_text(encoding='utf-8-sig').strip(), dump(value))
        self.assertFalse(Path(str(path) + '.native.tmp').exists())

    def test_cad2020_native_gb2312_file_is_converted_to_utf8(self):
        # Exercise the exact source-to-delivery substitution without building a package.
        code = (ROOT / 'src/diagram-commands.lsp').read_text(encoding='utf-8')
        code = code.replace('(open tmp "w" "utf8")', '(open tmp "w")')
        for form in parse(code):
            if isinstance(form, list) and form[:2] == [Symbol('DEFUN'), Symbol('EL:DIAGNOSTICWRITEDATA')]:
                self.h.evaluate(form)
        self.h.builtins['EL:DIAGNOSTICNATIVECHARSET'] = lambda: 'gb2312'
        path = self.root / 'output/gb2312-store.eld'
        value = [Pair(Symbol('NAME'), '应急照明中文记录')]
        self.f.fixture.call('EL:DiagnosticWriteData', str(path), value)
        self.assertEqual(path.read_text(encoding='utf-8-sig').strip(), dump(value))

    def test_live_geometry_and_library_cache_are_not_traversed_or_serialized(self):
        class Poison:
            def __repr__(self):
                raise AssertionError('live geometry/cache must not be printed')
        result = self.h.lookup('*EL:RESULT*')
        result = self.f.fixture.call('EL:Put', Symbol('DEVICE-LIBRARY'), Poison(), result)
        snapshot = [Pair(Symbol('GEOMETRY'), Poison()),
                    Pair(Symbol('WIRES'), ['W1', 'W2']), Pair(Symbol('BLOCKS'), ['B1'])]
        result = self.f.fixture.call('EL:Put', Symbol('SNAPSHOT'), snapshot, result)
        self.h.frames[0]['*EL:RESULT*'] = result
        with zipfile.ZipFile(self.export()) as archive:
            summary = archive.read('current-result.eld').decode('utf-8-sig')
            self.assertIn('BUSINESS-FIELDS', summary)
            self.assertIn('(WIRE-COUNT . 2)', summary)
            self.assertIn('(BLOCK-COUNT . 1)', summary)
            self.assertIn('(PANEL . "source")', summary)
            self.assertIn('association.eld', archive.namelist())
            self.assertIn('drawing-store.eld', archive.namelist())

    def test_interrupted_native_print_closes_file_and_keeps_last_progress_checkpoint(self):
        path = self.root / 'output/interrupted.eld'
        progress = self.root / 'output/progress.log'
        self.h.frames[0]['*EL:DIAGNOSTICPROGRESSPATH*'] = str(progress)
        handles = []
        original_open = self.h.builtins['OPEN']
        def opening(*args):
            file = original_open(*args)
            handles.append(file)
            return file
        def interrupted(value, file):
            file.write('partial')
            raise RuntimeError('cancelled native print')
        self.h.builtins['OPEN'] = opening
        self.h.builtins['PRIN1'] = interrupted
        with self.assertRaises(RuntimeError):
            self.f.fixture.call('EL:DiagnosticWriteData', str(path), [1, 2, 3])
        self.assertTrue(all(file.closed for file in handles))
        self.assertFalse(path.exists())
        self.assertFalse(Path(str(path) + '.native.tmp').exists())
        self.assertIn('FILE_BEGIN interrupted', progress.read_text(encoding='ascii'))
        self.assertNotIn('FILE_DONE interrupted', progress.read_text(encoding='ascii'))

    def test_native_close_failure_cannot_report_a_missing_output_as_completed(self):
        path = self.root / 'output/close-failed.eld'
        def failed_close(file):
            file.close()
            raise OSError('native close failed')
        self.h.builtins['CLOSE'] = failed_close
        with self.assertRaises(RuntimeError):
            self.f.fixture.call('EL:DiagnosticWriteData', str(path), [1, 2, 3])
        self.assertFalse(path.exists())
        self.assertFalse(Path(str(path) + '.native.tmp').exists())


if __name__ == '__main__':
    unittest.main()
