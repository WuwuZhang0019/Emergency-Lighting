"""Persistent diagnostic/error context regressions. Date: 2026-10-08.

Runs actual LISP with file and CAD adapters; not real AutoCAD acceptance.
"""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Symbol, truth
import test_cad_adapter as adapter

ROOT = adapter.ROOT


class DiagnosticTests(unittest.TestCase):
    setUp = adapter.CadAdapterTests.setUp
    call = adapter.CadAdapterTests.call
    get = adapter.CadAdapterTests.get
    line = adapter.CadAdapterTests.line
    block = adapter.CadAdapterTests.block

    def logging(self):
        self.h.load_definitions(ROOT / 'src/statistics.lsp')
        self.h.load_definitions(ROOT / 'src/main.lsp')
        check_root = ROOT / 'output/cad2020-012-check'
        check_root.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=check_root)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / 'output').mkdir()
        self.log = root / 'output/ELTRACE-debug.log'
        self.h.frames[0]['*EL:ROOT*'] = root.as_posix() + '/'
        self.messages, self.handles = [], []

        def open_file(path, mode, *encoding):
            if mode == 'r' and not Path(path).exists():
                return None
            handle = open(path, mode, encoding='utf-8')
            self.handles.append(handle)
            return handle

        self.h.builtins.update({
            'OPEN': open_file, 'CLOSE': lambda f: f.close(),
            'WRITE-LINE': lambda line, f: f.write(line + '\n'),
            'GETVAR': lambda name: {'CDATE': 20261008.1234, 'MILLISECS': 100}[name],
            'PRINC': lambda *args: self.messages.extend(str(v) for v in args),
            'HANDENT': lambda handle: handle, 'REDRAW': lambda *args: None,
            'GRTEXT': lambda *args: None,
        })

    def test_real_command_failure_captures_nested_panel_context_before_cleanup(self):
        self.logging()
        self.block('BOX', 'P', '1FD6', [0., 0., 0.])
        self.line('1FCD', [1., 0., 0.], [10., 0., 0.], 'W')
        cfg = self.h.lookup('CFG')

        def failed_matrix(entity):
            self.assertEqual(entity, '1FD6')
            raise TypeError('bad argument type: numberp: nil')

        self.h.builtins.update({
            'EL:LOADCONFIG': lambda: cfg,
            'ENTSEL': lambda prompt: ['1FD6' if '配电箱' in prompt else '1FCD', [0., 0., 0.]],
            'EL:INSERTMATRIX': failed_matrix,
        })
        with self.assertRaisesRegex(TypeError, 'numberp: nil') as caught:
            self.h.run('(c:ELSTAT)')
        # The subset host does not automatically dispatch AutoCAD's *error* hook.
        self.call('*ERROR*', str(caught.exception))
        text = self.log.read_text(encoding='utf-8')
        for value in ('BEGIN', '012', 'PICKS', '1FD6', '1FCD', 'PREPARE_BOX',
                      'PANEL_RECORD', 'BLOCK_CONTOUR', 'INSERT_MATRIX', 'ERROR', 'numberp: nil', 'END'):
            self.assertIn(value, text)
        self.assertIn(str(self.log.as_posix()), ''.join(self.messages))
        self.assertIsNone(self.h.lookup('*EL:RESULT*'))
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))
        self.assertIsNone(self.h.lookup('*EL:LOGACTIVE*'))
        self.assertTrue(all(f.closed for f in self.handles))

    def test_success_returns_original_value_and_sessions_append(self):
        self.logging()
        for i in range(2):
            self.h.run('(EL:LogStart)')
            result = self.h.run('(EL:LogCall "CHECK" \'((watts . 172)) \'+ \'(171 1))')
            self.assertEqual(result, 172)
            self.assertFalse(self.h.lookup('*EL:LOGSTACK*'))
            self.h.run('(EL:LogFinish \'result-ready)')
        text = self.log.read_text(encoding='utf-8')
        self.assertEqual(text.count('| BEGIN |'), 2)
        self.assertEqual(text.count('| END |'), 2)
        self.assertTrue(all(f.closed for f in self.handles))

    def test_unwritable_log_does_not_break_recognition(self):
        self.logging()

        def denied(*args):
            raise PermissionError('read-only directory')

        self.h.builtins['OPEN'] = denied
        self.h.run('(EL:LogStart)')
        self.assertEqual(self.h.run('(EL:LogCall "CHECK" nil \'+ \'(171 1))'), 172)
        self.h.run('(EL:LogFailure "numberp: nil")')
        self.assertIn('日志写入失败', ''.join(self.messages))
        self.assertIn('numberp: nil', ''.join(self.messages))
        self.assertFalse(truth(self.h.lookup('*EL:LOGACTIVE*')))

    def test_write_failure_closes_file_and_preserves_original_error(self):
        self.logging()

        def failed_write(*args):
            raise OSError('disk full')

        self.h.builtins['WRITE-LINE'] = failed_write
        self.h.run('(EL:LogStart) (EL:LogFailure "original numberp: nil")')
        self.assertTrue(all(f.closed for f in self.handles))
        self.assertIn('日志写入失败', ''.join(self.messages))


if __name__ == '__main__':
    unittest.main()
