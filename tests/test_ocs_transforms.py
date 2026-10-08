"""OCS contour regressions from v14 CAD log. Date: 2026-10-08.

Uses the subset host and explicit coordinate adapters, not real CAD acceptance.
"""
import json
import math
import unittest

from autolisp_host import Pair, Symbol, truth
import test_diagnostics as diagnostics

ROOT = diagnostics.ROOT


class OcsTransformTests(unittest.TestCase):
    setUp = diagnostics.DiagnosticTests.setUp
    call = diagnostics.DiagnosticTests.call
    get = diagnostics.DiagnosticTests.get
    logging = diagnostics.DiagnosticTests.logging

    def circle_fixture(self):
        self.logging()
        fixture = json.loads((ROOT / 'tests/fixtures/contour-1ce3.json').read_text(encoding='utf-8'))
        self.entities['2037'] = [Pair(*row) for row in fixture['insert']]
        self.entities['1CE3'] = [Pair(*row) for row in fixture['circle']]
        self.blocks['LOG_CIRCLE'] = [Pair(*row) for row in fixture['block_table']]
        self.h.run('(EL:LogStart)')

    def contour(self, handle='2037'):
        return self.call('EL:BlockContour', handle, [1., 0., 0., 1., 0., 0., 0., 1.], .1, None)

    def test_user_circle_keeps_radius_and_closure_when_entity_trans_returns_nil(self):
        self.circle_fixture()
        calls = []

        def trans(point, source, target, *args):
            calls.append(source)
            return None if source == '1CE3' else point

        self.h.builtins['TRANS'] = trans
        result = self.contour()
        edges = self.get('segments', result)
        self.assertFalse(truth(self.get('issues', result)))
        self.assertGreater(len(edges), 4)
        theta = 3.14159
        center = [1193230. + 500. * (3.63798e-12 * math.cos(theta) - .208333 * math.sin(theta)),
                  399792. + 500. * (3.63798e-12 * math.sin(theta) + .208333 * math.cos(theta)), 0.]
        for edge in edges:
            for point in edge:
                self.assertEqual(point[2], 0.)
                self.assertAlmostEqual(math.dist(point, center), .208333 * 500., places=6)
        self.assertLess(math.dist(edges[0][0], edges[-1][1]), 1e-7)
        self.assertNotIn('1CE3', calls)
        log = self.log.read_text(encoding='utf-8')
        for stage in ('CURVE_SEGMENTS', 'CURVE_POINTS', 'CURVE_POINT_COUNT', 'CURVE_TRANS_RESULT'):
            self.assertIn(stage, log)

    @staticmethod
    def axis_ocs(point, normal, target, displacement=None):
        if not isinstance(normal, list):
            return None  # No usable entity-name conversion in this adapter.
        return [-point[0], point[1], -point[2]] if normal[2] < 0 else point

    def test_arc_crossing_zero_preserves_direction_elevation_and_negative_normal(self):
        self.logging()
        self.h.builtins['TRANS'] = self.axis_ocs
        for normal in (None, [0., 0., 1.], [0., 0., -1.]):
            with self.subTest(normal=normal):
                data = [Pair(0, 'ARC'), Pair(5, 'ARC'), Pair(10, [2., 3., 7.]),
                        Pair(40, 2.), Pair(50, math.pi * 1.5), Pair(51, math.pi * .5)]
                if normal is not None:
                    data.append(Pair(210, normal))
                edges = self.call('EL:CurveSegments', data, .01)
                sign = -1 if normal and normal[2] < 0 else 1
                self.assertLess(math.dist(edges[0][0], [2.*sign, 1., 7.*sign]), 1e-9)
                self.assertLess(math.dist(edges[-1][1], [2.*sign, 5., 7.*sign]), 1e-9)
                middle = edges[len(edges)//2][0]
                self.assertLess(math.dist(middle, [4.*sign, 3., 7.*sign]), 1e-9)
                for edge in edges:
                    self.assertAlmostEqual(math.dist(edge[0], [2.*sign, 3., 7.*sign]), 2.)

    def test_nested_circle_applies_bases_mirror_scales_rotation_and_ocs_once(self):
        self.circle_fixture()
        self.entities['2037'] = [Pair(0, 'INSERT'), Pair(5, '2037'), Pair(2, 'LOG_CIRCLE'),
            Pair(10, [2., 3., 4.]), Pair(41, 2.), Pair(42, 3.), Pair(43, 4.),
            Pair(50, math.pi/2), Pair(210, [0., 0., -1.])]
        self.blocks['LOG_CIRCLE'] = [Pair(70, 0), Pair(10, [.25, -.5, .75]), Pair(-2, '1CE3')]
        self.entities['OUTER'] = [Pair(0, 'INSERT'), Pair(5, 'OUTER'), Pair(2, 'OUTER_DEF'),
            Pair(10, [10., 20., 30.]), Pair(41, -2.), Pair(42, 5.), Pair(43, 3.), Pair(50, math.pi/2)]
        self.blocks['OUTER_DEF'] = [Pair(70, 0), Pair(10, [1., -1., 2.]), Pair(-2, '2037')]
        self.h.builtins['TRANS'] = self.axis_ocs
        result = self.contour('OUTER')
        self.assertFalse(truth(self.get('issues', result)))
        edges = self.get('segments', result)

        def expected(point):
            # Independent analytic 90-degree transforms with nonzero block bases.
            x, y, z = point
            child = [-(2. - 3.*(y + .5)), 3. + 2.*(x - .25), -(4. + 4.*(z - .75))]
            return [10. - 5.*(child[1] + 1.), 20. - 2.*(child[0] - 1.), 30. + 3.*(child[2] - 2.)]

        for i in (0, len(edges)//4, len(edges)//2, len(edges)-1):
            angle = math.tau*i/len(edges)
            local = [3.63798e-12 + .208333*math.cos(angle), .208333 + .208333*math.sin(angle), 0.]
            self.assertLess(math.dist(edges[i][0], expected(local)), 1e-8)
        log = self.log.read_text(encoding='utf-8')
        self.assertIn('INSERT_TRANS', log)
        self.assertIn('DISPLACEMENT', log)
        self.assertIn('Z-AXIS', log)

    def test_bad_curve_results_stop_before_affine_and_keep_sample_context(self):
        self.circle_fixture()
        for bad in (None, [1., 2.], 'native-error'):
            with self.subTest(result=bad):
                self.h.run('(EL:LogStart)')

                def trans(point, normal, target, *args):
                    if self.h.lookup('*EL:LOGSTACK*')[0][0] == 'CURVE_TRANS':
                        if bad == 'native-error':
                            raise TypeError('native trans failure')
                        return bad
                    return point

                self.h.builtins['TRANS'] = trans
                with self.assertRaises((RuntimeError, TypeError)) as error:
                    self.contour()
                self.call('EL:LogFailure', str(error.exception))
                log = self.log.read_text(encoding='utf-8').split('| BEGIN |')[-1]
                for token in ('1CE3', 'CIRCLE', 'CURVE_TRANS', 'NORMAL', 'SAMPLE', 'EXTRUSION-VECTOR'):
                    self.assertIn(token, log)
                self.assertEqual(log.count('| ENTER CURVE_TRANS |'), 1)
                self.assertNotIn('ENTER CONTOUR_TRANSFORM', log)
                if bad != 'native-error':
                    self.assertIn('INVALID_CURVE_TRANS_RESULT', log)

    def test_nil_insert_axis_stops_before_matrix_arithmetic(self):
        self.circle_fixture()

        def trans(point, normal, target, displacement=None):
            return None if displacement else point

        self.h.builtins['TRANS'] = trans
        with self.assertRaisesRegex(RuntimeError, 'quit / exit abort') as error:
            self.contour()
        self.call('EL:LogFailure', str(error.exception))
        log = self.log.read_text(encoding='utf-8').split('| ERROR |')[-1]
        for token in ('INVALID_INSERT_TRANS_RESULT', '2037', 'Z-AXIS', 'DISPLACEMENT'):
            self.assertIn(token, log)
        self.assertNotIn('ENTER CURVE_SEGMENTS', self.log.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
