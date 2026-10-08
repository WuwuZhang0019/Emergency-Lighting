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
        check_root = ROOT / 'output/cad2020-022-check'
        check_root.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=check_root)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / 'output').mkdir()
        self.log = root / 'output/ELTRACE-debug.log'
        self.h.frames[0]['*EL:ROOT*'] = root.as_posix() + '/'
        self.h.frames[0]['*EL:LOGVERBOSE*'] = True
        self.messages, self.handles = [], []

        def abort():
            raise RuntimeError('quit / exit abort')

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
            'EXIT': abort,
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
            'EL:ENTITYBOUNDS': failed_matrix,
        })
        with self.assertRaisesRegex(TypeError, 'numberp: nil') as caught:
            self.h.run('(c:ELTRACE)')
        # The subset host does not automatically dispatch AutoCAD's *error* hook.
        self.call('*ERROR*', str(caught.exception))
        text = self.log.read_text(encoding='utf-8')
        for value in ('BEGIN', '022', 'PICKS', '1FD6', '1FCD', 'PREPARE_BOX',
                      'PANEL_RECORD', 'BLOCK_BOUNDS', 'ERROR', 'numberp: nil', 'END'):
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

    def test_nil_entity_trans_uses_normal_and_keeps_complete_contour(self):
        self.logged_contour_fixture()
        calls = []

        def trans(point, source, target, *args):
            calls.append((point, source, target))
            # Reproduce v13: the block-definition entity path returns nil.
            if source == '1DE0':
                return None
            if isinstance(source, list):
                self.assertEqual(source, [0., 0., 1.])
                self.assertEqual(target, 0)
            return point

        self.h.builtins['TRANS'] = trans
        result = self.run_logged_contour()
        edges = self.get('segments', result)
        self.assertEqual(len(edges), 4)
        self.assertFalse(truth(self.get('issues', result)))
        self.assertEqual(edges[-1][1], edges[0][0])
        for edge, expected in zip(edges, [600., 240., 600., 240.]):
            self.assertAlmostEqual(sum((b-a)**2 for a, b in zip(*edge)) ** .5, expected)
        self.assertEqual(sum(isinstance(source, list) for _, source, _ in calls), 8)
        self.assertFalse(any(source == '1DE0' for _, source, _ in calls))

    def test_vertex_trans_failure_retains_point_and_precise_stage(self):
        self.logged_contour_fixture()

        def trans(point, entity, *args):
            if self.h.lookup('*EL:LOGSTACK*')[0][0] == 'POLYLINE_TRANS':
                raise TypeError('bad argument type: numberp: nil')
            return point

        self.h.builtins['TRANS'] = trans
        with self.assertRaisesRegex(TypeError, 'numberp: nil') as error:
            self.run_logged_contour()
        self.call('EL:LogFailure', str(error.exception))
        log = self.log.read_text(encoding='utf-8').split('| ERROR |')[-1]
        for value in ('POLYLINE_TRANS', 'POLYLINE_DATA', '1DE0', '-0.599992', '0.48001'):
            self.assertIn(value, log)

    def test_short_trans_result_stops_before_segments_without_filling_z(self):
        self.logged_contour_fixture()
        self.h.builtins['TRANS'] = lambda point, entity, *args: (
            point[:2] if self.h.lookup('*EL:LOGSTACK*')[0][0] == 'POLYLINE_TRANS' else point)
        with self.assertRaisesRegex(RuntimeError, 'quit / exit abort') as error:
            self.run_logged_contour()
        self.call('EL:LogFailure', str(error.exception))
        log = self.log.read_text(encoding='utf-8').split('| ERROR |')[-1]
        self.assertIn('POLYLINE_TRANS', log)
        self.assertIn('INVALID_POLYLINE_TRANS_RESULT', log)
        self.assertIn('1DE0', log)
        self.assertNotIn('ENTER POLYLINE_SEGMENTS', self.log.read_text(encoding='utf-8'))

    def test_nil_vector_trans_stops_at_first_vertex_with_input_context(self):
        self.logged_contour_fixture()
        self.h.builtins['TRANS'] = lambda point, source, *args: (
            None if self.h.lookup('*EL:LOGSTACK*')[0][0] == 'POLYLINE_TRANS' else point)
        with self.assertRaisesRegex(RuntimeError, 'quit / exit abort') as error:
            self.run_logged_contour()
        self.call('EL:LogFailure', str(error.exception))
        log = self.log.read_text(encoding='utf-8')
        self.assertEqual(log.count('| ENTER POLYLINE_TRANS |'), 1)
        self.assertNotIn('ENTER POLYLINE_SEGMENTS', log)
        for value in ('INVALID_POLYLINE_TRANS_RESULT', 'NORMAL', 'TARGET', 'EXTRUSION-VECTOR', '1DE0'):
            self.assertIn(value, log)
        self.assertIn('未返回有效三维点', ''.join(self.messages))

    def test_polyline_ocs_preserves_elevation_and_negative_normal_bulge(self):
        self.logged_contour_fixture()
        normals = []

        def trans(point, normal, target, *args):
            normals.append(normal)
            self.assertEqual(target, 0)
            # Axis-aligned OCS adapter: -Z reflects X and Z, not Y.
            return [-point[0], point[1], -point[2]] if normal[2] < 0 else point

        self.h.builtins['TRANS'] = trans
        for normal in (None, [0., 0., 1.], [0., 0., -1.]):
            with self.subTest(normal=normal):
                self.entities['WIRE'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'WIRE'),
                    Pair(38, 7.), Pair(10, [2., 3.]), Pair(42, .25),
                    Pair(10, [4., 5.]), Pair(42, 0.)]
                if normal is not None:
                    self.entities['WIRE'].append(Pair(210, normal))
                points, bulges = self.call('EL:PolylineData', 'WIRE')
                sign = -1 if normal and normal[2] < 0 else 1
                self.assertEqual(points, [[sign * 2., 3., sign * 7.], [sign * 4., 5., sign * 7.]])
                self.assertEqual(bulges, [sign * .25, 0.])
                self.assertEqual(normals[-1], normal or [0., 0., 1.])

    def test_invalid_normal_stops_before_native_conversion(self):
        self.logged_contour_fixture()

        def forbidden_trans(*args):
            self.fail('invalid normal must not reach trans')

        self.h.builtins['TRANS'] = forbidden_trans
        self.entities['BAD'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'BAD'),
            Pair(10, [2., 3.]), Pair(210, [0., 0., 0.])]
        with self.assertRaisesRegex(RuntimeError, 'quit / exit abort') as error:
            self.call('EL:PolylineData', 'BAD')
        self.call('EL:LogFailure', str(error.exception))
        self.assertIn('INVALID_POLYLINE_TRANS_INPUT', self.log.read_text(encoding='utf-8'))

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

    def test_summary_logging_keeps_suppressed_failure_context(self):
        self.logging()
        self.h.frames[0]['*EL:LOGVERBOSE*'] = None
        self.h.run('(EL:LogStart)')
        for i in range(512):
            self.call('EL:LogEvent', 'CURVE_TRANS_RESULT', [float(i), 2., 3.])
        self.call('EL:LogFailure', 'cancelled after sample')
        log = self.log.read_text(encoding='utf-8')
        self.assertNotIn('| CURVE_TRANS_RESULT |', log)
        self.assertIn('CURVE_TRANS_RESULT', log.split('| ERROR |')[-1])
        self.assertIn('511.0', log)
        self.assertLess(len(self.handles), 10)


if __name__ == '__main__':
    unittest.main()
