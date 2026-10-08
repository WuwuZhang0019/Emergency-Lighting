"""Pick feedback lifecycle regressions. Date: 2026-10-08.

Runs actual command flow with input/display adapters; no CAD visual acceptance.
"""
import pathlib
import unittest

from autolisp_host import Host, Pair, Symbol, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Cancelled(Exception):
    pass


class PickFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for filename in ('common', 'config', 'geometry', 'main', 'generation'):
            self.h.load_definitions(ROOT / 'src' / f'{filename}.lsp')
        self.entities = {
            name: [Pair(0, typ), Pair(5, name), Pair(8, layer), Pair(2, block), Pair(410, 'Model')]
            for name, typ, layer, block in [('panel', 'INSERT', 'P', 'BOX'),
                                          ('wire', 'LINE', 'W', ''),
                                          ('wire2', 'LINE', 'W', ''),
                                          ('lamp', 'INSERT', 'D', 'LAMP'),
                                          ('text', 'TEXT', 'D', '')]
        }
        self.visible = set()
        self.display_calls = []
        self.messages = []
        self.picks = iter(())
        self.keywords = iter(())
        self.integers = iter(())
        self.samples_seen = []
        self.saved = []
        self.cfg = self.h.run('(EL:DefaultConfig "test.dwg")')
        self.h.builtins.update({
            'EL:LOADCONFIG': lambda: self.cfg,
            'EL:DRAWINGID': lambda: 'test.dwg',
            'EL:SAVECONFIG': lambda cfg: self.saved.append(cfg) or cfg,
            'EL:EFFECTIVENAME': lambda entity: next(row.cdr for row in self.entities[entity] if row.car == 2),
            'ENTSEL': self.pick,
            'ENTGET': lambda entity: self.entities[entity],
            'HANDENT': lambda handle: handle if handle in self.entities else None,
            'REDRAW': self.redraw,
            'GETKWORD': lambda prompt: next(self.keywords),
            'GETSTRING': lambda *args: self.fail('ELSETUP must not request units'),
            'GETINT': self.choice,
            'INITGET': lambda *args: None,
            'PRINC': lambda *args: self.messages.extend(args),
            'GRTEXT': lambda *args: None,
        })

    def redraw(self, entity=None, mode=None):
        self.display_calls.append((entity, mode))
        if entity is None:
            return None
        if entity not in self.entities:
            raise RuntimeError('entity deleted')
        if mode == 3:
            self.visible.add(entity)
        elif mode == 4:
            self.visible.discard(entity)

    def pick(self, prompt):
        self.samples_seen.append(set(self.visible))
        choice = next(self.picks)
        if choice == 'ESC':
            # Trigger the actual local command handler while its frame is active.
            self.h.call(Symbol('*ERROR*'), ['Function cancelled'])
            raise Cancelled()
        return [choice, [0.0, 0.0, 0.0]] if choice else None

    def choice(self, prompt):
        self.assertEqual(self.visible, {'panel', 'wire', 'lamp'})
        choice = next(self.integers)
        if choice == 'ESC':
            self.h.call(Symbol('*ERROR*'), ['Function cancelled'])
            raise Cancelled()
        return choice

    def get(self, key, record):
        return self.h.call(Symbol('EL:GET'), [Symbol(key.upper()), record])

    def test_setup_samples_stay_highlighted_through_next_pick_and_clear_on_completion(self):
        self.picks = iter(['panel', 'wire', 'lamp'])
        self.integers = iter([None, None])
        self.h.run('(c:ELSETUP)')
        self.assertEqual(self.samples_seen, [set(), {'panel'}, {'panel', 'wire'}])
        self.assertEqual(len(self.saved), 1)
        self.assertFalse(truth(self.get('calibrated', self.saved[0])))
        self.assertEqual(self.visible, set())
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))
        for entity in ('panel', 'wire', 'lamp'):
            self.assertEqual(self.display_calls.count((entity, 3)), 1)
            self.assertEqual(self.display_calls.count((entity, 4)), 1)
        self.assertIn('已拾取：LINE；图层：W；句柄：wire', ''.join(self.messages))

    def test_escape_during_parameter_confirmation_clears_samples_without_saving(self):
        self.picks = iter(['panel', 'wire', 'lamp'])
        self.integers = iter([None, 'ESC'])
        with self.assertRaises(Cancelled):
            self.h.run('(c:ELSETUP)')
        self.assertEqual(self.visible, set())
        self.assertEqual(self.saved, [])
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))

    def test_escape_after_first_sample_clears_it_without_saving(self):
        self.picks = iter(['panel', 'ESC'])
        with self.assertRaises(Cancelled):
            self.h.run('(c:ELSETUP)')
        self.assertEqual(self.visible, set())
        self.assertEqual(self.saved, [])
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))
        self.assertIn('拾取亮显已清理', ''.join(self.messages))

    def test_invalid_sample_is_not_saved_and_its_highlight_is_cleared(self):
        self.picks = iter(['text'])
        self.h.run('(c:ELSETUP)')
        self.assertEqual(self.saved, [])
        self.assertEqual(self.visible, set())
        self.assertIn('样本类型错误', ''.join(self.messages))

    def test_repeated_pick_keeps_single_highlight_owner_and_returns_original_point(self):
        self.picks = iter(['wire', 'wire'])
        first = self.h.run('(EL:PickEntity "wire")')
        second = self.h.run('(EL:PickEntity "wire again")')
        self.assertEqual(first, second)
        self.assertEqual(first[1], [0.0, 0.0, 0.0])
        self.assertEqual(self.display_calls.count(('wire', 3)), 1)
        self.h.run('(EL:ClearPickHighlights)')
        self.assertEqual(self.display_calls.count(('wire', 4)), 1)
        self.assertEqual(self.visible, set())

    def test_deleted_entity_does_not_prevent_remaining_cleanup(self):
        self.h.run('(EL:HighlightPick "panel") (EL:HighlightPick "wire")')
        del self.entities['wire']
        self.visible.remove('wire')
        self.h.run('(EL:ClearPickHighlights)')
        self.assertEqual(self.visible, set())
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))
        self.assertIn(('wire', 4), self.display_calls)
        self.assertIn(('panel', 4), self.display_calls)

    def test_trace_retains_confirmed_wire_and_clears_rejected_wire_before_analysis(self):
        self.h.frames[0]['TEST:CFG'] = self.cfg
        self.cfg = self.h.run('''
          (setq test:cfg (EL:Put 'panel-layers '("P") test:cfg))
          (setq test:cfg (EL:Put 'panel-names '("BOX") test:cfg))
          (setq test:cfg (EL:Put 'params (EL:SuggestedParams) test:cfg))
          (EL:Put 'calibrated T test:cfg)''')
        snapshot = [Pair(Symbol('SIGNATURE'), 'snapshot')]
        seeds = [[Pair(Symbol('WIRE'), wire), Pair(Symbol('ID'), wire)] for wire in ('wire', 'wire2')]
        self.picks = iter(['panel', 'wire'])

        def analyze(snapshot, cfg, panel, selected):
            self.assertEqual(self.visible, {'panel', 'wire'})
            self.assertEqual(selected, seeds[:1])
            return [Pair(Symbol('CIRCUITS'), None)]

        self.h.builtins.update({
            'EL:ROLESREADY': lambda cfg: True,
            'EL:CURRENTCONTEXT': lambda cfg, panel: [snapshot, seeds],
            'EL:REVIEWEXITS': lambda rows: [rows[:1]],
            'EL:BLOCKRECORD': lambda *args: [Pair(Symbol('IDENTITY'), ['BOX', None, 'def'])],
            'EL:SAVECONFIG': lambda cfg: cfg,
            'EL:ANALYZESNAPSHOT': analyze,
            'EL:COLLECTENDPOINTSNAPSHOT': lambda cfg: snapshot,
        })
        self.h.run('(c:ELTRACE)')
        self.assertEqual(self.visible, set())
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))

    def test_template_cancellation_cleans_picked_block(self):
        self.h.frames[0]['TEST:CFG'] = self.cfg
        self.cfg = self.h.run("(EL:Put 'params (EL:SuggestedParams) test:cfg)")
        self.picks = iter(['panel'])

        def capture(*args):
            self.h.run('(EL:PickEntity "template")')
            self.assertEqual(self.visible, {'panel'})
            self.h.call(Symbol('*ERROR*'), ['Function cancelled'])
            raise Cancelled()

        self.h.builtins['EL:CAPTURETEMPLATE'] = capture
        with self.assertRaises(Cancelled):
            self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(self.visible, set())
        self.assertEqual(self.saved, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
