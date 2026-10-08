"""Persistent diagnostic/error context regressions. Date: 2026-10-08.

Runs actual LISP with file and CAD adapters; not real AutoCAD acceptance.
"""
from pathlib import Path
import tempfile
import json
import unittest

from autolisp_host import Pair, Symbol, truth
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
        check_root = ROOT / 'output/cad2020-013-check'
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
        for value in ('BEGIN', '013', 'PICKS', '1FD6', '1FCD', 'PREPARE_BOX',
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

    def logged_contour_fixture(self):
        self.logging()
        fixture = json.loads((ROOT / 'tests/fixtures/contour-1de0.json').read_text(encoding='utf-8'))
        self.entities['1FD6'] = [Pair(*row) for row in fixture['panel']]
        self.entities['1DE0'] = [Pair(*row) for row in fixture['contour']]
        self.blocks['LOG_PANEL'] = [Pair(*row) for row in fixture['block_table']]
        self.h.run('(EL:LogStart)')

    def run_logged_contour(self):
        return self.call('EL:LogCall', 'BLOCK_CONTOUR', None, Symbol('EL:BLOCKCONTOUR'),
                         ['1FD6', [1., 0., 0., 1., 0., 0., 0., 1.], .1, None])

    def test_user_log_contour_data_has_four_transformed_edges(self):
        self.logged_contour_fixture()
        result = self.run_logged_contour()
        edges = self.get('segments', result)
        self.assertEqual(len(edges), 4)
        self.assertFalse(truth(self.get('issues', result)))
        self.assertEqual(edges[-1][1], edges[0][0])
        self.assertAlmostEqual(edges[0][0][0], 1193610.0046941193, places=6)
        self.assertAlmostEqual(edges[0][0][1], 401788.9962447126, places=6)
        for edge, expected_length in zip(edges, [600., 240., 600., 240.]):
            length = sum((b-a)**2 for a, b in zip(*edge)) ** .5
            self.assertAlmostEqual(length, expected_length, places=6)
            self.assertTrue(all(len(p) == 3 and p[2] == 0. for p in edge))
        self.assertFalse(truth(self.h.lookup('*EL:LOGSTACK*')))
        self.call('EL:LogFinish', Symbol('RESULT-READY'))
        log = self.log.read_text(encoding='utf-8')
        for stage in ('CONTOUR_FILTER_INPUT', 'POLYLINE_DATA', 'POLYLINE_DXF_ROW',
                      'POLYLINE_TRANS_RESULT', 'POLYLINE_DATA_RESULT', 'POLYLINE_SEGMENTS',
                      'CONTOUR_TRANSFORM_RESULT', 'CONTOUR_NEXT'):
            self.assertIn(stage, log)
        self.assertNotIn('INVALID_AFFINE_INPUT', log)

    def test_vertex_trans_failure_retains_point_and_precise_stage(self):
        self.logged_contour_fixture()

        def trans(point, entity, *args):
            if entity == '1DE0':
                raise TypeError('bad argument type: numberp: nil')
            return point

        self.h.builtins['TRANS'] = trans
        with self.assertRaisesRegex(TypeError, 'numberp: nil') as error:
            self.run_logged_contour()
        self.call('EL:LogFailure', str(error.exception))
        log = self.log.read_text(encoding='utf-8').split('| ERROR |')[-1]
        for value in ('POLYLINE_TRANS', 'POLYLINE_DATA', '1DE0', '-0.599992', '0.48001'):
            self.assertIn(value, log)

    def test_short_trans_result_reports_affine_input_without_filling_z(self):
        self.logged_contour_fixture()
        self.h.builtins['TRANS'] = lambda point, entity, *args: point[:2] if entity == '1DE0' else point
        with self.assertRaises(TypeError) as error:
            self.run_logged_contour()
        self.call('EL:LogFailure', str(error.exception))
        log = self.log.read_text(encoding='utf-8').split('| ERROR |')[-1]
        self.assertIn('CONTOUR_TRANSFORM', log)
        self.assertIn('INVALID_AFFINE_INPUT', log)
        self.assertIn('1DE0', log)

    def test_invalid_dxf_row_keeps_original_numeric_error_context(self):
        self.logged_contour_fixture()
        self.entities['1DE0'].append(Pair(None, 'injected-invalid-group-code'))
        with self.assertRaisesRegex(TypeError, 'numberp: nil') as error:
            self.run_logged_contour()
        self.call('EL:LogFailure', str(error.exception))
        log = self.log.read_text(encoding='utf-8').split('| ERROR |')[-1]
        for value in ('POLYLINE_DATA', 'POLYLINE_DXF_ROW', 'injected-invalid-group-code'):
            self.assertIn(value, log)

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
