"""Native-format legends, owned-DWG source fallback and modal paging. Date: 2026-10-12."""
import unittest
from autolisp_host import truth
import test_fixed_diagnostics as diagnostics


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        fixture = diagnostics.FixedDiagnosticTests()
        fixture.setUp()
        self.h, self.tiles = fixture.h, fixture.tiles
        self.call, self.get = fixture.call, fixture.get
        self.slides, self.clears = [], []
        self.h.builtins.update({
            'FINDFILE': lambda p: p,
            'SLIDE_IMAGE': lambda *args: self.slides.append(args) or 'actual.sld',
            'FILL_IMAGE': lambda *args: self.clears.append(args),
        })

    def test_native_slide_keeps_aspect_ratio_and_empty_slot_clears(self):
        self.call('EL:ThumbDraw', 'f_image0', ['actual.sld', [1200, 600]])
        self.assertEqual(self.slides, [(20, 0, 120, 60, 'actual.sld')])
        self.call('EL:ThumbDraw', 'f_image0', None)
        self.assertEqual([args[-1] for args in self.clears], [-15, -2, -15])
        self.assertEqual(len(self.slides), 1)

    def test_failed_slide_draw_clears_dark_area_and_reports_failure(self):
        ended = []
        self.h.builtins['END_IMAGE'] = lambda: ended.append(True)
        for result in (None, RuntimeError('native slide_image failed')):
            with self.subTest(result=result):
                def draw(*args):
                    if isinstance(result, Exception): raise result
                    return result
                self.h.builtins['SLIDE_IMAGE'] = draw
                self.assertFalse(truth(self.call('EL:ThumbDraw', 'dl_image', ['native.sld', [800, 600]])))
                self.assertEqual(self.clears[-1][-1], -15)
        self.assertEqual(len(ended), 2)

    def prepare_setup(self, library=True):
        result = self.h.run(''' '((snapshot (blocks ((id . "D1") (name . "Lamp")
          (bounds (0 0 0) (2 2 0))))) (circuits ((devices "D1")))) ''')
        if library:
            result = self.call('EL:Put', self.h.run("'device-library"),
                              self.h.run("'((items) (load-error))"), result)
        self.h.builtins['EL:THUMBCLEANUP'] = lambda: None
        self.h.builtins['EL:THUMBCAPTURE'] = lambda b: ['source.sld', [1200, 600]]
        self.h.builtins['EL:DLLEGEND'] = lambda *args: None
        return result






    def capture_setup(self, fail=False):
        self.h.builtins.pop('EL:THUMBCAPTURE')
        self.variables = {'FILEDIA': 1, 'CMDECHO': 1, 'SCREENSIZE': [1200, 600]}
        self.events = []
        def command(*args):
            self.events.append(args)
            if fail:
                raise RuntimeError('capture failed')
        self.h.builtins.update({
            'GETVAR': lambda key: self.variables[key],
            'SETVAR': lambda key, value: self.variables.__setitem__(key, value),
            'VL-FILENAME-MKTEMP': lambda *args: 'unique.sld',
            'EL:SIMPLEZOOM': lambda *args: self.events.append('zoom'),
            'VLAX-GET-ACAD-OBJECT': lambda: 'acad',
            'VLA-ZOOMPREVIOUS': lambda app: self.events.append('restore'),
            'COMMAND-S': command,
            'EL:THUMBISOLATE': lambda block: self.events.append('isolate'),
            'VLA-GET-ACTIVEDOCUMENT': lambda app: 'doc',
            'VLA-REGEN': lambda *args: None,
            'VL-FILE-DELETE': lambda path: self.events.append(('delete', path)),
        })




    def test_failed_restore_retains_pending_objects_for_retry(self):
        self.h.run("""(setq *EL:ThumbHidden* '(("wire" -1)))""")
        self.h.builtins['VLA-PUT-VISIBLE'] = lambda *args: None
        self.h.builtins['VLA-GET-VISIBLE'] = lambda obj: 0
        self.assertIsNone(self.call('EL:ThumbRestore'))
        self.assertTrue(self.h.frames[0]['*EL:THUMBHIDDEN*'])
        self.h.builtins['VLA-GET-VISIBLE'] = lambda obj: -1
        self.assertTrue(self.call('EL:ThumbRestore'))






if __name__ == '__main__':
    unittest.main()
