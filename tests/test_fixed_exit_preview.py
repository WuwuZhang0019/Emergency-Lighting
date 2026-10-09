"""Whole-circuit preview and cleanup regression. Date: 2026-10-09."""
import unittest
from autolisp_host import Symbol
import test_exit_devices as exits
import test_simple_flow as simple


class FixedExitPreviewTests(unittest.TestCase):
    call = exits.ExitDeviceTests.call
    get = exits.ExitDeviceTests.get
    line = exits.ExitDeviceTests.line
    block = exits.ExitDeviceTests.block
    plan = exits.ExitDeviceTests.plan
    logging = exits.ExitDeviceTests.logging

    def setUp(self):
        exits.ExitDeviceTests.setUp(self)
        for name in ('EL:CLEARGAPPREVIEW', 'EL:CLEARPICKHIGHLIGHTS'):
            self.h.builtins.pop(name, None)
        self.visible, self.overlays, self.zooms = set(), [], []
        self.modal = False
        self.h.builtins.update({'REDRAW': self.redraw, 'GRTEXT': lambda *args: None,
            'GRDRAW': self.draw, 'EL:SIMPLEZOOM': self.zoom,
            'GETVAR': lambda key: 150. if key == 'VIEWSIZE' else 100.,
            'GETSTRING': lambda *args: '',
            'VL-CATCH-ALL-ERROR-MESSAGE': lambda error: str(error.exception)})
        for name in ('ENTMOD', 'ENTMAKE', 'ENTMAKEX', 'ENTDEL'):
            self.h.builtins[name] = lambda *args: self.fail('Preview must not modify DWG')

    def redraw(self, entity=None, mode=None):
        self.assertFalse(self.modal)
        if entity is None:
            self.overlays.clear()
        elif mode == 3:
            self.visible.add(entity)
        elif mode == 4:
            self.visible.discard(entity)

    def draw(self, *args):
        self.assertFalse(self.modal)
        self.overlays.append(args)

    def zoom(self, lo, hi):
        self.assertFalse(self.modal)
        self.assertEqual(self.overlays, [])
        self.zooms.append((lo, hi))

    def recognize(self):
        return self.call('EL:RecognizeFixed', self.cfg, 'panel')

    def test_full_branch_and_devices_drawn_without_other_system(self):
        self.call('EL:FixedExitHighlight', self.recognize(), '0')
        self.assertEqual(self.visible, {'w1', 'w2', 'a', 'b'})
        self.assertEqual(len([x for x in self.overlays if x[2] == 2]), 2)
        self.assertEqual(len([x for x in self.overlays if x[2] == 4]), 8)
        self.assertEqual(self.zooms, [([1., -1., 0.], [11., 7., 0.])])

    def test_gap_downstream_path_is_shown_without_drawing_fake_connection(self):
        self.entities.clear()
        simple.SimpleFlowTests.gap_plan(self)
        self.call('EL:FixedExitHighlight', self.recognize(), '0')
        self.assertEqual(self.visible, {'before', 'after-wire', 'after'})
        yellow = [(x[0], x[1]) for x in self.overlays if x[2] == 2]
        self.assertEqual(len(yellow), 2)
        self.assertNotIn(([10., 0., 0.], [20., 0., 0.]), yellow)

    def test_switching_candidates_previews_only_the_chosen_circuit(self):
        self.block('SIGN', 'D', 'c', [0., 10., 0.])
        self.line('out2', [0., 1., 0.], [0., 9., 0.], 'W')
        self.selected += ['c', 'out2']
        result = self.recognize()
        self.call('EL:FixedExitHighlight', result, '0')
        self.assertEqual(self.visible, {'out2', 'c'})
        self.call('EL:FixedExitHighlight', result, '1')
        self.assertEqual(self.visible, {'w1', 'w2', 'a', 'b'})
        self.assertEqual(len(self.overlays), 10)

    def test_multiselect_deduplicates_and_empty_selection_clears_previous_preview(self):
        result = self.recognize()
        circuit = self.get('circuits', result)[0]
        result = self.call('EL:Put', Symbol('CIRCUITS'), [circuit, circuit], result)
        self.call('EL:FixedExitHighlight', result, '0 1')
        self.assertEqual(len(self.overlays), 10)
        self.call('EL:FixedExitHighlight', result, '')
        self.assertEqual(self.visible, set())
        self.assertEqual(self.overlays, [])
        self.assertEqual(len(self.zooms), 1)

    def test_dialog_closes_before_drawing_and_reopens_with_same_selection(self):
        paused = []
        def pause(*args):
            self.assertFalse(self.modal)
            paused.append(set(self.visible))
            return ''
        def done(status):
            self.modal = False
            return status
        def start():
            self.modal = True
            if not paused:
                return self.h.run(self.actions['f_preview'])
            self.assertEqual(self.visible, set())
            self.assertEqual(self.overlays, [])
            self.assertEqual(self.tiles['f_exits'], '0 ')
            return self.h.run(self.actions['cancel'])
        self.h.builtins.update({'GETSTRING': pause, 'START_DIALOG': start, 'DONE_DIALOG': done})
        self.assertIsNone(self.call('EL:ReviewFixedExits', self.recognize(), None))
        self.assertEqual(paused, [{'w1', 'w2', 'a', 'b'}])
        self.assertEqual(self.dialogs, ['el_fixed_exits', 'el_fixed_exits'])
        self.assertEqual(self.writes, [])

    def test_escape_clears_paths_and_devices_before_error_propagates(self):
        def cancel(*args):
            self.assertEqual(self.visible, {'w1', 'w2', 'a', 'b'})
            raise RuntimeError('Function cancelled')
        self.h.builtins['GETSTRING'] = cancel
        with self.assertRaises(Exception):
            self.call('EL:FixedExitPreview', self.recognize(), '0')
        self.assertEqual(self.visible, set())
        self.assertEqual(self.overlays, [])
        self.assertIn('Function cancelled', ''.join(self.messages))


if __name__ == '__main__':
    unittest.main()
