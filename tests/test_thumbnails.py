"""Thumbnail geometry, pagination and clearing. Date: 2026-10-09."""
import unittest
import test_fixed_diagnostics as diagnostics


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        fixture = diagnostics.FixedDiagnosticTests()
        fixture.setUp()
        self.h, self.tiles = fixture.h, fixture.tiles
        self.call, self.get = fixture.call, fixture.get
        self.lines, self.clears = [], []
        self.h.builtins.update({
            'VECTOR_IMAGE': lambda *args: self.lines.append(args),
            'FILL_IMAGE': lambda *args: self.clears.append(args),
        })

    def test_fit_centers_and_preserves_aspect_ratio(self):
        geometry = [[[[0., 0., 0.], [100., 0., 0.]],
                     [[100., 0., 0.], [100., 50., 0.]]], None]
        self.call('EL:ThumbDraw', 'f_image0', geometry)
        self.assertEqual(self.lines, [(32, 54, 128, 54, 7), (128, 54, 128, 6, 7)])
        self.call('EL:ThumbDraw', 'f_image0', None)
        self.assertEqual(len(self.clears), 2)
        self.assertEqual(len(self.lines), 2)

    def test_paging_cache_and_empty_slots(self):
        calls = []
        def geometry(name):
            calls.append(name)
            return [[[[0., 0., 0.], [1., 1., 0.]]], None]
        self.h.builtins['EL:THUMBGEOMETRY'] = geometry
        self.h.run('''(setq *EL:ThumbPage* 0 *EL:ThumbCache* nil
          *EL:ThumbRows* '(((name . "A") (count . 1)) ((name . "B") (count . 2))
          ((name . "C") (count . 3)) ((name . "D") (count . 4)) ((name . "E") (count . 5))))''')
        self.call('EL:ThumbFill')
        self.assertEqual(self.tiles['f_page'], '1 / 2')
        self.call('EL:ThumbPage', 4)
        self.assertEqual(self.tiles['f_count0'], '数量：5')
        self.assertEqual(self.tiles['f_count1'], '')
        self.assertEqual(self.tiles['f_page'], '2 / 2')
        self.call('EL:ThumbPage', -4)
        self.assertEqual(calls, list('ABCDE'))
        self.h.run('(setq *EL:ThumbRows* nil)')
        self.call('EL:ThumbPage', 0)
        self.assertEqual(self.tiles['f_count0'], '')
        self.assertEqual(self.tiles['f_page'], '1 / 1')

    def test_unsupported_or_failed_geometry_is_explicit(self):
        self.h.run('(setq *EL:ThumbPage* 0 *EL:ThumbCache* nil *EL:ThumbRows* \'(((name . "X") (count . 2))))')
        self.h.builtins['EL:THUMBGEOMETRY'] = lambda name: [None, True]
        self.call('EL:ThumbFill')
        self.assertEqual(self.tiles['f_hint0'], '请在图面查看')

    def test_visible_line_reads_definition_without_nested_expansion(self):
        rows = {'a': [(0, 'LINE'), (10, [0., 0., 0.]), (11, [2., 0., 0.])],
                'b': [(0, 'INSERT')], 'end': [(0, 'ENDBLK')]}
        from autolisp_host import Pair
        self.h.builtins.update({
            'TBLSEARCH': lambda *args: [Pair(-2, 'a')],
            'ENTGET': lambda e: [Pair(k, v) for k, v in rows[e]],
            'ENTNEXT': lambda e: {'a': 'b', 'b': 'end'}[e],
            'VLAX-CURVE-GETSTARTPARAM': lambda e: 0.,
            'VLAX-CURVE-GETENDPARAM': lambda e: 1.,
            'VLAX-CURVE-GETPOINTATPARAM': lambda e, t: [2*t, 0., 0.],
        })
        result = self.call('EL:ThumbGeometry', 'lamp')
        self.assertEqual(result[0], [[[0., 0., 0.], [2., 0., 0.]]])
        self.assertTrue(result[1])


if __name__ == '__main__':
    unittest.main()
