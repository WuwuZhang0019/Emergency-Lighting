"""Date: 2026-10-22. Status: finite cold entry and DLL extraction regression.

APPLOAD registration and binary stream behavior are tested without native CAD.
"""
import base64
import io
from pathlib import Path
import sys
import unittest

from autolisp_host import Host, Symbol, truth

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_cad2020 as builder


class ColdEntryTests(unittest.TestCase):
    def fixture(self, failure=None):
        h = Host()
        calls = []
        command = builder.COLD_TEST_COMMAND
        marker = f'package-{builder.PACKAGE_NO:03d}.marker'
        h.builtins.update({
            'PROBE': lambda: calls.append('probe'),
            'C:ELSTAT': lambda: self.fail('cold entry opened ELSTAT'),
            'LOAD': lambda *args: self.fail('cold wrapper depends on another LOAD'),
        })
        def initialize():
            calls.append('initialize')
            if failure == 'exception':
                raise RuntimeError('runtime extraction failed')
            return True if failure != 'failed' else None
        h.builtins['INITIALIZE-COLD'] = initialize
        h.set(Symbol('*EL:MONITORLOADREADY*'), True)
        h.set(Symbol('*EL:PACKAGEMARKER*'), marker)
        h.set(Symbol('*EL:ROOT*'), 'C:/old-package/')
        startup = f"""
(if (INITIALIZE-COLD)
  (progn
    (defun c:{command} () (PROBE))
    (setq *EL:Root* "C:/current-package/"
      *EL:MonitorLoadReady* T
      *EL:PackageMarker* "{marker if failure != 'old-marker' else 'package-old.marker'}")))
"""
        raw = builder.cold_test_entry(startup)
        self.assertIsInstance(raw, bytes)
        text = raw.decode('gb2312', errors='strict')
        for token in ('@COMMAND@', '@STARTUP@', '@MARKER@', '@VERSION@'):
            self.assertNotIn(token, text)
        h.run(text)
        return h, calls

    def test_appload_only_registers_then_initializes_and_dispatches_module_command(self):
        h, calls = self.fixture()
        self.assertEqual(calls, [])
        h.call(Symbol('C:' + builder.COLD_TEST_COMMAND), [])
        self.assertEqual(calls, ['initialize', 'probe'])
        self.assertEqual(h.lookup(Symbol('*EL:ROOT*')), 'C:/current-package/')
        h.call(Symbol('C:' + builder.COLD_TEST_COMMAND), [])
        self.assertEqual(calls, ['initialize', 'probe', 'probe'])

    def test_failed_initializer_never_dispatches_stale_ready_state(self):
        for failure in ('failed', 'exception'):
            with self.subTest(failure=failure):
                h, calls = self.fixture(failure)
                h.call(Symbol('C:' + builder.COLD_TEST_COMMAND), [])
                self.assertEqual(calls, ['initialize'])
                self.assertFalse(truth(h.lookup(Symbol('*EL:MONITORLOADREADY*'))))

    def test_old_marker_does_not_dispatch_probe(self):
        h, calls = self.fixture('old-marker')
        h.call(Symbol('C:' + builder.COLD_TEST_COMMAND), [])
        self.assertEqual(calls, ['initialize'])


class ColdDllExtractionTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for module in ('common', 'startup'):
            self.h.load_definitions(ROOT / 'src' / (module + '.lsp'))
        self.files = {}
        self.calls = []
        self.stream = io.BytesIO()
        self.node = {'kind': 'node'}
        self.xml = {'kind': 'xml'}
        self.locked = False
        self.corrupt_final_read = False
        self.reads = 0
        self.h.builtins.update({
            'EL:DLMKDIR': lambda path: True,
            'VL-FILENAME-DIRECTORY': lambda path: str(Path(path).parent),
            'VL-FILENAME-EXTENSION': lambda path: Path(path).suffix,
            'FINDFILE': lambda path: path if path in self.files else None,
            'EL:STOREJOINSTRINGS': lambda chunks: ''.join(chunks or []),
            'VLAX-CREATE-OBJECT': self.create,
            'VLAX-PUT-PROPERTY': self.put_property,
            'VLAX-GET-PROPERTY': self.get_property,
            'VLAX-INVOKE-METHOD': self.invoke,
            'VLAX-SAFEARRAY->LIST': lambda *args: self.fail('binary payload expanded into a LISP byte list'),
        })

    def create(self, name):
        if name == 'MSXML2.DOMDocument.6.0':
            return self.xml
        self.assertEqual(name, 'ADODB.Stream')
        return self.stream

    def put_property(self, obj, key, value):
        key = str(key).upper()
        if obj is self.node:
            if key == 'TEXT':
                obj['BYTES'] = base64.b64decode(value, validate=True)
                obj['TEXT'] = value
            elif key == 'NODETYPEDVALUE':
                obj['BYTES'] = bytes(value)
                obj['TEXT'] = base64.encodebytes(bytes(value)).decode('ascii')
            else:
                obj[key] = value
        elif obj is self.stream:
            if key == 'POSITION':
                self.calls.append(('POSITION', value))
                self.stream.seek(value)
            elif key != 'TYPE':
                self.fail('unexpected stream property: ' + key)

    def get_property(self, obj, key):
        self.assertIs(obj, self.node)
        key = str(key).upper()
        return obj['BYTES'] if key == 'NODETYPEDVALUE' else obj[key]

    def invoke(self, obj, method, *args):
        method = str(method).upper()
        self.calls.append((method, *args))
        if method == 'CREATEELEMENT':
            self.assertIs(obj, self.xml)
            self.assertEqual(args, ('binary',))
            return self.node
        self.assertIs(obj, self.stream)
        if method == 'OPEN':
            self.assertEqual(args, (None, 0, -1, '', ''))
        elif method == 'LOADFROMFILE':
            self.stream.seek(0)
            self.stream.truncate()
            self.stream.write(self.files[args[0]])
            self.stream.seek(0)
        elif method == 'READ':
            self.assertEqual(args, (-1,))
            self.reads += 1
            data = self.stream.read()
            if self.corrupt_final_read and self.reads >= 2:
                return data + b'corrupt'
            return data
        elif method == 'SETEOS':
            self.stream.truncate()
        elif method == 'WRITE':
            self.stream.write(bytes(args[0]))
        elif method == 'SAVETOFILE':
            if self.locked:
                raise RuntimeError('loaded DLL cannot be overwritten')
            self.assertEqual(args[1], 2)
            self.files[args[0]] = self.stream.getvalue()
        else:
            self.fail('unexpected stream method: ' + method)

    def run_payload(self, path, data):
        encoded = base64.b64encode(data).decode('ascii')
        chunks = [encoded[i:i + 192] for i in range(0, len(encoded), 192)]
        return self.h.call(Symbol('EL:STARTUPBINARYWORK'), [path, chunks])

    def test_identical_existing_dll_only_reads_even_when_loaded_file_is_locked(self):
        path = 'C:/package/native/Cold75.DLL'
        expected = bytes(range(256)) * 11
        self.files[path] = expected
        self.locked = True
        self.assertTrue(truth(self.run_payload(path, expected)))
        kinds = [row[0] for row in self.calls]
        self.assertEqual(kinds.count('LOADFROMFILE'), 2)
        self.assertEqual(kinds.count('READ'), 2)
        for forbidden in ('WRITE', 'SAVETOFILE', 'SETEOS'):
            self.assertNotIn(forbidden, kinds)
        self.assertEqual(self.files[path], expected)

    def test_different_existing_dll_resets_stream_then_strictly_writes_and_reads_back(self):
        path = 'C:/package/native/Cold75.dll'
        expected = b'new-dll-bytes'
        self.files[path] = b'old much longer DLL bytes that must be truncated'
        self.assertTrue(truth(self.run_payload(path, expected)))
        kinds = [row[0] for row in self.calls]
        sequence = [kind for kind in kinds if kind in {'LOADFROMFILE', 'READ', 'POSITION', 'SETEOS', 'WRITE', 'SAVETOFILE'}]
        self.assertEqual(sequence, ['LOADFROMFILE', 'READ', 'POSITION', 'SETEOS', 'WRITE', 'SAVETOFILE', 'LOADFROMFILE', 'READ'])
        self.assertIn(('POSITION', 0), self.calls)
        self.assertEqual(self.files[path], expected)

    def test_absent_dll_keeps_normal_write_and_final_readback(self):
        path = 'C:/package/native/Cold75.dll'
        expected = b'new-library'
        self.assertTrue(truth(self.run_payload(path, expected)))
        kinds = [row[0] for row in self.calls]
        self.assertEqual([kind for kind in kinds if kind in {'LOADFROMFILE', 'READ', 'WRITE', 'SAVETOFILE'}],
                         ['WRITE', 'SAVETOFILE', 'LOADFROMFILE', 'READ'])
        self.assertNotIn('SETEOS', kinds)
        self.assertEqual(self.files[path], expected)

    def test_non_dll_existing_same_bytes_retains_original_write_path(self):
        path = 'C:/package/assets/seed.dwg'
        expected = b'drawing-seed'
        self.files[path] = expected
        self.assertTrue(truth(self.run_payload(path, expected)))
        kinds = [row[0] for row in self.calls]
        self.assertEqual([kind for kind in kinds if kind in {'LOADFROMFILE', 'READ', 'WRITE', 'SAVETOFILE'}],
                         ['WRITE', 'SAVETOFILE', 'LOADFROMFILE', 'READ'])
        self.assertNotIn('SETEOS', kinds)
        self.assertEqual(self.files[path], expected)

    def test_identical_dll_still_requires_final_exact_readback(self):
        path = 'C:/package/native/Cold75.dll'
        expected = b'expected-dll'
        self.files[path] = expected
        self.corrupt_final_read = True
        self.assertFalse(truth(self.run_payload(path, expected)))
        self.assertNotIn('SAVETOFILE', [row[0] for row in self.calls])


if __name__ == '__main__':
    unittest.main()
