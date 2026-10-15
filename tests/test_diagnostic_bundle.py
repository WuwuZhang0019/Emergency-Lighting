"""Date: 2026-10-15. Folder export is default; legacy ZIP helpers are checked separately."""
import base64
import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import zipfile

from autolisp_host import Pair, Symbol, parse
from test_diagram_store import dump
from monitor_io import install_monitor_io
import test_diagnostic_export as diagnostic

ROOT = Path(__file__).resolve().parents[1]
CHECK_ROOT = ROOT / 'output/diagnostic-bundle-146-check'


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
        self.h.frames[0]['*EL:PACKAGEMARKER*'] = 'package-146.marker'
        self.h.frames[0][':VLAX-TRUE'] = True
        self.run = [Pair(Symbol('EVENTS'), [[1, 'EXAMPLE', '原始日志' * 5000]])]
        self.h.frames[0]['*EL:DIAGNOSTICRUNS*'] = [Pair('NOD', self.run)]
        self.timeline = self.root / 'output/timeline.md'
        self.timeline.write_text('# 完整时间轴\n日期：2026-10-15\n状态：已记录\n', encoding='utf-8')
        getvar = self.h.builtins['GETVAR']
        variables = {'TEMPPREFIX': (self.root / 'temp').as_posix() + '/',
                     'CDATE': 20261015.123456, 'DWGNAME': '测试图纸.dwg',
                     'DWGPREFIX': 'G:/设计/', 'ACADVER': '23.1', 'CMDECHO': 1}
        self.processes = []
        self.workers = []
        def cleanup_workers():
            for worker in self.workers:
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()
        self.addCleanup(cleanup_workers)
        def startapp(app, arguments):
            self.assertNotIn('/', app)
            self.assertIn('-WindowStyle Hidden', arguments)
            self.processes.append((app, arguments))
            self.workers.append(subprocess.Popen([app, *arguments.split()], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW))
            return 33
        def delay(command, milliseconds):
            self.assertEqual((command, milliseconds), ('_.DELAY', 50))
            self.assertEqual(variables['CMDECHO'], 0)
            time.sleep(milliseconds / 1000)
        self.h.builtins.update({
            'GETVAR': lambda name: variables[name] if name in variables else getvar(name),
            'SETVAR': lambda name, value: variables.__setitem__(name, value) or value,
            'EL:TICK': lambda: int(time.monotonic() * 1000) % 2147483648,
            'STARTAPP': startapp,
            'VL-CMDF': delay,
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
            self.assertEqual(name, 'MSXML2.DOMDocument.6.0', 'export must not create WScript.Shell')
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
            return invoke(obj, method, *args)
        self.h.builtins.update({
            'VLAX-CREATE-OBJECT': com_create,
            'VLAX-INVOKE-METHOD': com_invoke,
            'VLAX-GET-PROPERTY': lambda obj, key: base64.encodebytes(obj['NODETYPEDVALUE']).decode('ascii'),
        })

    def export(self):
        return Path(self.h.run('(EL:DiagnosticExport)'))

    def test_complete_folder_exact_bytes_special_paths_no_dwg_writes_and_unique_names(self):
        before = self.f.before()
        raw = '历史事件\r\n'.encode('gb2312')
        (self.root / 'output/ELTRACE-debug.log').write_bytes(raw)
        (self.root / 'output/ELPERF.log').write_bytes(b'perf\r\n')
        (self.root / 'temp/ELPERF.log').write_bytes(b'fallback perf\r\n')
        (self.root / 'output/unrelated.dwg').write_bytes(b'not a log')
        folder = self.export()
        self.assertTrue(folder.is_dir())
        self.assertEqual({path.name for path in folder.iterdir()}, {
            'README.md', 'manifest.eld', 'association.eld', 'drawing-store.eld',
            'current-result.eld', 'run.eld', 'timeline.md', 'progress.log',
            'runtime-ELTRACE-debug.log', 'runtime-ELPERF.log', 'temp-ELPERF.log'})
        self.assertEqual((folder / 'runtime-ELTRACE-debug.log').read_bytes(), raw)
        self.assertEqual((folder / 'timeline.md').read_bytes(), self.timeline.read_bytes())
        self.assertIn('原始日志' * 5000, (folder / 'run.eld').read_text(encoding='utf-8-sig'))
        progress = (folder / 'progress.log').read_text(encoding='ascii')
        self.assertIn('FILE_DONE drawing-store', progress)
        self.assertIn('BUNDLE_DONE', progress)
        self.assertNotIn('ZIP_', progress)
        first = {path.name: path.read_bytes() for path in folder.iterdir()}
        second = self.export()
        self.assertNotEqual(second, folder)
        self.assertEqual(first, {path.name: path.read_bytes() for path in folder.iterdir()})
        self.f.assert_business_unchanged(before)
        self.assertEqual(self.processes, [])
        self.assertTrue(all(stream['closed'] and stream['released'] for stream in self.streams))

    def test_invalid_association_keeps_logs_and_explains_missing_record(self):
        def invalid(*args):
            raise RuntimeError('invalid association')
        self.h.builtins['EL:DIAGNOSTICRECORDVALID'] = invalid
        folder = self.export()
        self.assertTrue((folder / 'timeline.md').is_file())
        self.assertFalse((folder / 'association.eld').exists())
        self.assertIn('invalid association', (folder / 'README.md').read_text(encoding='utf-8-sig'))
        self.assertIn('关联异常', self.h.lookup('*EL:DIAGNOSTICEXPORTMESSAGE*'))

    def test_no_run_or_saved_output_still_exports_load_snapshot_with_missing_notes(self):
        self.h.set('*EL:DIAGNOSTICRUNS*', None)
        self.h.set('*EL:MONITORLOADSUMMARY*', [Pair(Symbol('COMMAND'), 'APPLOAD')])
        self.h.builtins['EL:STOREREAD'] = lambda: None
        self.h.builtins['EL:EXPORTDIAGNOSTICRUN'] = lambda: None
        folder = self.export()
        self.assertIn('APPLOAD', (folder / 'load.eld').read_text(encoding='utf-8-sig'))
        self.assertIn('run.eld：本次会话没有可用资料', (folder / 'README.md').read_text(encoding='utf-8-sig'))
        self.assertEqual(self.processes, [])

    def test_unavailable_compressor_does_not_prevent_folder_export(self):
        (self.root / 'src/diagnostic-bundle.ps1').unlink()
        self.h.builtins['EL:DIAGNOSTICZIP'] = lambda *args: self.fail('folder export must not compress')
        message = self.h.run('(EL:PanelDiagnosticExport)')
        self.assertIn('已导出诊断资料文件夹', message)
        folder = Path(self.h.lookup('*EL:DIAGNOSTICEXPORTPATH*'))
        self.assertTrue((folder / 'association.eld').is_file())
        self.assertFalse(Path(str(folder) + '.zip').exists())
        self.assertFalse((folder / 'export-error.txt').exists())

    def test_blocked_native_launcher_is_not_called_and_old_export_error_is_cleared(self):
        self.h.builtins['STARTAPP'] = lambda *args: self.fail('must not launch PowerShell')
        self.h.set('*EL:DIAGNOSTICERROR*', 'old launch error')
        self.h.set('*EL:DIAGNOSTICEXPORTMESSAGE*', 'old failure')
        message = self.h.run('(EL:PanelDiagnosticExport)')
        self.assertIn('已导出诊断资料文件夹', message)
        self.assertFalse(self.h.lookup('*EL:DIAGNOSTICERROR*'))
        self.assertTrue(Path(self.h.lookup('*EL:DIAGNOSTICEXPORTPATH*')).is_dir())
        self.assertEqual(self.processes, [])

    def test_unavailable_command_encoder_is_not_needed_for_folder_export(self):
        self.h.builtins['EL:DIAGNOSTICENCODEDCOMMAND'] = lambda *args: self.fail('must not encode a shell command')
        message = self.h.run('(EL:PanelDiagnosticExport)')
        self.assertIn('已导出诊断资料文件夹', message)
        self.assertEqual(self.processes, [])

    def test_failure_report_write_error_does_not_replace_original_collection_failure(self):
        invoke=self.h.builtins['VLAX-INVOKE-METHOD']
        def interrupted(*args):
            folder=self.root/'output/failed-snapshot'
            folder.mkdir()
            self.h.set('*EL:DIAGNOSTICEXPORTPATH*',str(folder))
            raise RuntimeError('original collection error')
        def fail_report(obj,method,*args):
            if str(method).upper()=='SAVETOFILE' and str(args[0]).endswith('export-error.txt'):
                raise OSError('secondary report write error')
            return invoke(obj,method,*args)
        self.h.builtins['EL:DIAGNOSTICBUNDLE']=interrupted
        self.h.builtins['VLAX-INVOKE-METHOD']=fail_report
        message=self.h.run('(EL:PanelDiagnosticExport)')
        self.assertIn('original collection error',message)
        self.assertNotIn('secondary report write error',message)
        self.assertEqual(self.h.lookup('*EL:DIAGNOSTICEXPORTMESSAGE*'),message)

    def test_folder_export_never_waits_for_a_compression_completion_file(self):
        self.h.builtins['EL:DIAGNOSTICWAIT'] = lambda *args: self.fail('folder export must not wait')
        self.h.builtins['STARTAPP'] = lambda *args: self.fail('folder export must not launch a worker')
        folder = self.export()
        self.assertTrue(folder.is_dir())
        self.assertFalse(Path(str(folder) + '.zip.cancel').exists())
        self.assertEqual(self.h.run('(getvar "CMDECHO")'), 1)

    def test_folder_export_does_not_change_cad_echo_or_call_delay(self):
        self.h.builtins['VL-CMDF'] = lambda *args: self.fail('must not delay the CAD command')
        self.assertTrue(self.export().is_dir())
        self.assertEqual(self.h.run('(getvar "CMDECHO")'), 1)

    def test_wait_handles_signed_cad_clock_rollover(self):
        clock = [2147483640]
        self.h.builtins['EL:TICK'] = lambda: clock[0]
        def delay(*args):
            clock[0] += 10000
            if clock[0] > 2147483647:
                clock[0] -= 4294967296
        self.h.builtins['VL-CMDF'] = delay
        self.assertIsNone(self.f.fixture.call('EL:DiagnosticWait', str(self.root / 'missing.status'), 30000))
        self.assertEqual(clock[0], 2147483640 + 30000 - 4294967296)
        self.assertEqual(self.h.run('(getvar "CMDECHO")'), 1)

    def test_native_launcher_nil_or_zero_never_enters_wait(self):
        folder = self.root / 'output/ELDIAG-20261015.123456'
        folder.mkdir()
        self.h.builtins['EL:DIAGNOSTICWAIT'] = lambda *args: self.fail('failed launch must not wait')
        for returned in (None, 0):
            self.h.builtins['STARTAPP'] = lambda *args: returned
            with self.assertRaises(RuntimeError):
                self.f.fixture.call('EL:DiagnosticZip', str(folder))
            self.assertIn('无法启动诊断压缩程序', self.h.lookup('*EL:DIAGNOSTICERROR*'))

    def test_worker_will_not_publish_after_cancellation(self):
        folder = self.root / 'output/ELDIAG-20261015.123456'
        folder.mkdir()
        (folder / 'README.md').write_text('snapshot', encoding='utf-8')
        Path(str(folder) + '.zip.cancel').write_text('CANCEL', encoding='ascii')
        with self.assertRaises(RuntimeError):
            self.f.fixture.call('EL:DiagnosticZip', str(folder))
        self.assertFalse(Path(str(folder) + '.zip').exists())
        self.assertIn('cancelled or timed out', (folder / 'bundle-error.txt').read_text(encoding='utf-8-sig'))

    def test_folder_export_has_no_zip_or_worker_status_artifacts(self):
        folder = self.export()
        self.assertTrue((folder / 'manifest.eld').is_file())
        for suffix in ('.zip', '.zip.status', '.zip.cancel'):
            self.assertFalse(Path(str(folder) + suffix).exists())
        self.assertEqual(self.processes, [])

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
        folder=self.export(); opened=[]
        self.h.builtins['STARTAPP']=lambda app,args:opened.append((app,args)) or 1
        self.f.fixture.call('EL:DiagnosticOpenFolder',str(folder))
        self.assertEqual(opened,[('explorer.exe','"'+str(folder)+'"')])
        file=folder/'README.md'
        self.f.fixture.call('EL:DiagnosticOpenFolder',str(file))
        self.assertEqual(opened[-1],('explorer.exe','/select,"'+str(file)+'"'))
        self.f.fixture.call('EL:DiagnosticOpenFolder',str(folder)+'.missing')
        self.assertEqual(len(opened),2)

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
        folder = self.export()
        summary = (folder / 'current-result.eld').read_text(encoding='utf-8-sig')
        self.assertIn('BUSINESS-FIELDS', summary)
        self.assertIn('(WIRE-COUNT . 2)', summary)
        self.assertIn('(BLOCK-COUNT . 1)', summary)
        self.assertIn('(PANEL . "source")', summary)
        self.assertTrue((folder / 'association.eld').is_file())
        self.assertTrue((folder / 'drawing-store.eld').is_file())

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
