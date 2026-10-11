"""Native-format legends, source fallback and modal paging. Date: 2026-10-11."""
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

    def test_unknown_library_device_previews_actual_source_and_modal_refresh_reuses_it(self):
        result = self.prepare_setup()
        original = result.copy()
        captured = []
        self.h.builtins['EL:THUMBCAPTURE'] = lambda b: captured.append(self.get('id', b)) or ['source.sld', [1200, 600]]
        self.call('EL:ThumbPrepare', result)
        self.assertEqual(captured, ['D1'])
        self.assertEqual(self.call('EL:Get', 'Lamp', self.h.lookup('*EL:THUMBCACHE*')), ['source.sld', [1200, 600]])
        for api in ('EL:THUMBCAPTURE', 'EL:THUMBCLEANUP', 'COMMAND-S', 'VLA-PUT-VISIBLE', 'VLA-REGEN'):
            self.h.builtins[api] = lambda *args: self.fail('modal refresh must only read or reuse previews')
        self.call('EL:ThumbRefresh', result)
        self.assertEqual(self.call('EL:Get', 'Lamp', self.h.lookup('*EL:THUMBCACHE*')), ['source.sld', [1200, 600]])
        self.assertEqual(result, original)

    def test_ready_library_uses_cached_legend_and_other_library_falls_back_to_source(self):
        result = self.prepare_setup()
        row = self.h.run(''' '((name . "Lamp") (ids "D1") (entry (device-id . "ELDEV1"))
          (library-id . "LIB-A")) ''')
        self.h.builtins['EL:DLMATERIALROWS'] = lambda *args: [row]
        self.h.set('*EL:DLSESSIONSNAPSHOT*', self.h.run("'((catalog (library-id . \"LIB-A\")))"))
        self.h.builtins['EL:DLLEGEND'] = lambda *args: ['library.sld', [800, 600]]
        self.h.builtins['EL:THUMBCAPTURE'] = lambda *args: self.fail('valid library asset must remain read-only')
        self.call('EL:ThumbPrepare', result)
        self.assertEqual(self.call('EL:Get', 'Lamp', self.h.lookup('*EL:THUMBCACHE*')), ['library.sld', [800, 600]])
        self.h.set('*EL:DLSESSIONSNAPSHOT*', self.h.run("'((catalog (library-id . \"LIB-B\")))"))
        self.h.builtins['EL:DLLEGEND'] = lambda *args: self.fail('other library asset must not be read')
        self.h.builtins['EL:THUMBCAPTURE'] = lambda b: ['source.sld', [1200, 600]]
        self.call('EL:ThumbPrepare', result)
        self.assertEqual(self.call('EL:Get', 'Lamp', self.h.lookup('*EL:THUMBCACHE*')), ['source.sld', [1200, 600]])

    def test_corrupt_library_legend_falls_back_and_capture_failure_never_invents_graphic(self):
        result = self.prepare_setup()
        row = self.h.run(''' '((name . "Lamp") (ids "D1") (entry (device-id . "ELDEV1"))
          (library-id . "LIB-A")) ''')
        self.h.builtins['EL:DLMATERIALROWS'] = lambda *args: [row]
        self.h.set('*EL:DLSESSIONSNAPSHOT*', self.h.run("'((catalog (library-id . \"LIB-A\")))"))
        self.call('EL:ThumbPrepare', result)
        self.assertEqual(self.call('EL:Get', 'Lamp', self.h.lookup('*EL:THUMBCACHE*')), ['source.sld', [1200, 600]])
        self.h.set('*EL:THUMBSOURCES*', None)
        self.h.builtins['EL:THUMBCAPTURE'] = lambda *_: (_ for _ in ()).throw(RuntimeError('cancelled'))
        self.call('EL:ThumbPrepare', result)
        self.assertFalse(truth(self.call('EL:Get', 'Lamp', self.h.lookup('*EL:THUMBCACHE*'))))

    def test_paging_uses_prepared_slides_without_cad_commands(self):
        self.h.run('''(setq *EL:ThumbPage* 0 *EL:ThumbCache* '(("A" "a.sld" (1200 600)))
          *EL:ThumbRows* '(((name . "A") (count . 1)) ((name . "B") (count . 2))
          ((name . "C") (count . 3)) ((name . "D") (count . 4)) ((name . "E") (count . 5))))''')
        self.call('EL:ThumbFill')
        self.assertEqual(self.tiles['f_page'], '1 / 2')
        self.assertEqual(self.tiles['f_hint0'], '独立图例，点击定位')
        self.call('EL:ThumbPage', 4)
        self.assertEqual(self.tiles['f_count0'], '数量：5')
        self.assertEqual(self.tiles['f_count1'], '')
        self.assertEqual(self.tiles['f_page'], '2 / 2')
        self.call('EL:ThumbPage', -4)
        self.h.run('(setq *EL:ThumbRows* nil)')
        self.call('EL:ThumbPage', 0)
        self.assertEqual(self.tiles['f_count0'], '')
        self.assertEqual(self.tiles['f_page'], '1 / 1')

    def test_missing_preview_never_draws_approximate_outline(self):
        self.h.run('(setq *EL:ThumbPage* 0 *EL:ThumbCache* nil *EL:ThumbRows* \'(((name . "X") (count . 2))))')
        self.call('EL:ThumbFill')
        self.assertIn('预览失败', self.tiles['f_hint0'])
        self.assertFalse(self.slides)

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

    def test_native_capture_restores_view_and_cleans_files(self):
        self.capture_setup()
        result = self.call('EL:ThumbCapture', self.h.run("'((bounds (0 0 0) (2 2 0)))"))
        self.assertEqual(result, ['unique.sld', [1200, 600]])
        self.assertEqual(self.events, ['isolate', 'zoom', ('_.MSLIDE', 'unique.sld'), 'restore'])
        self.assertEqual(self.variables['FILEDIA'], 1)
        self.assertEqual(self.variables['CMDECHO'], 1)
        self.call('EL:ThumbCleanup')
        self.assertEqual(self.events[-1], ('delete', 'unique.sld'))

    def test_capture_failure_also_restores_view_and_variables(self):
        self.capture_setup(fail=True)
        self.assertIsNone(self.call('EL:ThumbCapture', self.h.run("'((bounds (0 0 0) (2 2 0)))")))
        self.assertEqual(self.events[-1], 'restore')
        self.assertEqual(self.variables['FILEDIA'], 1)
        self.assertEqual(self.variables['CMDECHO'], 1)

    def test_isolation_hides_only_visible_neighbors_and_restores_on_capture_error(self):
        self.capture_setup(fail=True)
        self.h.builtins.pop('EL:THUMBISOLATE')
        visible = {'target': -1, 'wire': -1, 'hidden': 0}
        self.h.builtins.update({
            'HANDENT': lambda handle: handle,
            'ENTGET': lambda entity: self.h.run("'((410 . \"Model\") (8 . \"D\"))"),
            'TBLSEARCH': lambda *args: self.h.run("'((70 . 0))"),
            'SSGET': lambda *args: ['target', 'wire', 'hidden'],
            'SSLENGTH': len,
            'SSNAME': lambda selection, index: selection[index],
            'VLAX-ENAME->VLA-OBJECT': lambda entity: entity,
            'VLA-GET-VISIBLE': lambda obj: visible[obj],
            'VLA-PUT-VISIBLE': lambda obj, value: visible.__setitem__(obj, value),
        })
        def capture(*args):
            self.assertEqual(visible, {'target': -1, 'wire': 0, 'hidden': 0})
            raise RuntimeError('cancelled')
        self.h.builtins['COMMAND-S'] = capture
        self.assertIsNone(self.call('EL:ThumbCapture', self.h.run("'((id . \"target\") (bounds (0 0 0) (2 2 0)))")))
        self.assertEqual(visible, {'target': -1, 'wire': -1, 'hidden': 0})

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
