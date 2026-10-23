"""Wire inference and explicit starts. Date: 2026-10-21; synthetic CAD, not native acceptance."""
import unittest
from autolisp_host import Pair, Symbol, truth
import test_simple_flow as simple


class AutoWireTests(unittest.TestCase):
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    line = simple.SimpleFlowTests.line
    block = simple.SimpleFlowTests.block
    plan = simple.SimpleFlowTests.plan

    def setUp(self):
        simple.SimpleFlowTests.setUp(self)
        self.plan()
        self.picks = []
        self.highlights = []
        self.h.builtins.update({'PRINC': lambda *a: None, 'HANDENT': lambda e: e,
            'EL:HIGHLIGHTPICK': lambda e: self.highlights.append(e),
            'EL:CLEARPICKHIGHLIGHTS': lambda: None,
            'EL:PICKMODEL': lambda *a: self.fail('Unexpected second pick')})

    def config(self):
        return self.call('EL:PanelWireConfig', 'panel', self.cfg)

    def test_single_style_auto_detects_arbitrary_layer_and_filters_other_linetype(self):
        for name in ('w1', 'w2', 'wr'):
            self.entities[name] = [Pair(8, 'custom-wire') if p.car == 8 else p for p in self.entities[name]]
        self.line('wrong', [5., 0., 0.], [5., -5., 0.], 'custom-wire')
        self.entities['wrong'].append(Pair(6, 'DASHED'))
        self.selected.append('wrong')
        cfg = self.config()
        self.assertEqual(self.get('wire-styles', cfg), [['custom-wire', 'CONTINUOUS']])
        snapshot = self.call('EL:SimpleCollect', cfg)
        self.assertNotIn('wrong', [self.get('id', w) for w in self.get('wires', snapshot)])
        network = self.call('EL:SimpleNetwork', snapshot, cfg, 'panel')
        self.assertEqual(sorted(self.get('wire-ids', network)), ['w1', 'w2'])
        self.assertTrue(truth(self.call('EL:ConfigValid', cfg, 'adapter-fixture.dwg')))

    def test_resolves_bylayer_and_model_space_byblock(self):
        original = self.h.builtins['TBLSEARCH']
        self.h.builtins['TBLSEARCH'] = lambda table, name: [Pair(6, 'Dashed')] if table == 'LAYER' else original(table, name)
        self.assertEqual(self.call('EL:WireStyle', self.entities['w1']), ['W', 'DASHED'])
        self.entities['w1'].append(Pair(6, 'ByBlock'))
        self.assertEqual(self.call('EL:WireStyle', self.entities['w1']), ['W', 'CONTINUOUS'])

    def test_mixed_contacts_highlight_and_require_choice_reject_unrelated_style(self):
        self.line('other', [-1., 0., 0.], [-9., 0., 0.], 'OTHER')
        self.selected.append('other')
        self.line('unrelated', [30., 30., 0.], [40., 30., 0.], 'UNRELATED')
        picks = iter(['unrelated', 'other'])
        def pick(*args):
            e = next(picks)
            self.picks.append(e)
            return [e, [0., 0., 0.]]
        self.h.builtins['EL:PICKMODEL'] = pick
        self.assertEqual(self.get('wire-layers', self.config()), ['OTHER'])
        self.assertEqual(self.picks, ['unrelated', 'other'])
        self.assertEqual(set(self.highlights), {'w1', 'other'})

    def test_cancel_ambiguous_selection_returns_no_config(self):
        self.line('other', [-1., 0., 0.], [-9., 0., 0.], 'W')
        self.entities['other'].append(Pair(6, 'DASHED'))
        self.selected.append('other')
        self.h.builtins['EL:PICKMODEL'] = lambda *a: None
        self.assertIsNone(self.config())

    def test_no_contact_never_chooses_nearest_wire(self):
        self.selected = ['panel', 'wr']
        calls = []
        self.h.builtins['EL:PICKMODEL'] = lambda *a: calls.append(a) or None
        self.assertIsNone(self.config())
        self.assertEqual(len(calls), 1)

    def test_actual_contour_rejects_bbox_corner_and_other_elevation(self):
        # Diamond inside the existing square bounds.
        pts = [[0., -1., 0.], [1., 0., 0.], [0., 1., 0.], [-1., 0., 0.]]
        for i in range(4):
            self.line(f'BOX-edge-{i}', pts[i], pts[(i+1) % 4])
        self.line('corner', [.9, .9, 0.], [5., .9, 0.], 'OTHER')
        self.line('above', [1., 0., 1.], [9., 0., 1.], 'OTHER')
        self.selected += ['corner', 'above']
        found = self.call('EL:PanelWireCandidates', 'panel', self.cfg)
        self.assertEqual([self.get('entity', r) for r in self.get('candidates', found)], ['w1'])
        cfg = self.config()
        # Even a same-style false bbox contact cannot become an outlet.
        self.entities['corner'] = [Pair(8, 'W') if p.car == 8 else p for p in self.entities['corner']]
        snapshot = self.call('EL:SimpleCollect', cfg)
        panel = self.call('EL:By', Symbol('ID'), 'panel', self.get('blocks', snapshot))
        wire = self.call('EL:WireRecord', 'corner', cfg)
        self.assertFalse(truth(self.call('EL:PathBlockHit', wire, panel, cfg)))

    def test_hidden_wire_is_not_an_auto_candidate(self):
        self.entities['w1'].append(Pair(60, 1))
        found = self.call('EL:PanelWireCandidates', 'panel', self.cfg)
        self.assertIsNone(self.get('candidates', found))

    def test_inside_endpoint_and_middle_crossing_count(self):
        for start, end in (([0., 0., 0.], [8., 0., 0.]), ([-5., 0., 0.], [5., 0., 0.])):
            self.line('w1', start, end, 'W')
            found = self.call('EL:PanelWireCandidates', 'panel', self.cfg)
            self.assertEqual([self.get('entity', r) for r in self.get('candidates', found)], ['w1'])

    def test_unsupported_contour_falls_back_to_manual_sample(self):
        self.h.builtins['EL:PANELCONTACTSHAPE'] = lambda *a: None
        self.h.builtins['EL:PICKMODEL'] = lambda *a: ['w1', [1., 0., 0.]]
        cfg = self.config()
        self.assertEqual(self.get('wire-layers', cfg), ['W'])
        self.assertIsNone(self.get('auto-panel', cfg))

    def test_fixed_entry_uses_explicit_start_and_source_change_invalidates_result(self):
        import test_fixed_diagnostics as diag
        fixture = diag.FixedDiagnosticTests()
        fixture.setUp()
        # Date: 2026-10-21. The current entry picks a box, then wire starts;
        # an endless box response would loop instead of modeling Enter.
        picks = []
        answers = iter([['panel', [0., 0., 0.]], ['w1', [1., 0., 0.]], None])
        def pick(*args):
            picks.append(args)
            return next(answers)
        catalog = fixture.call('EL:DLCatalogInitial', 'LIB-AUTO-WIRE')
        entry = fixture.call('EL:DLEntryNew', catalog, 'LAMP')
        for key, value in {'watts': 5, 'ground-confirmed': True, 'active': True,
                           'status': Symbol('READY'), 'asset-revision': 1,
                           'block-file': 'assets/ELDEV1/1/block.dwg',
                           'legend-file': 'assets/ELDEV1/1/legend.sld',
                           'legend-size': [800, 600], 'legend-checksum': 'sld-123-31'}.items():
            entry = fixture.call('EL:Put', Symbol(key.upper()), value, entry)
        catalog = fixture.call('EL:DLUpsert', catalog, entry)
        library = [Pair(Symbol('ROOT'), 'library-fixture/'), Pair(Symbol('CATALOG'), catalog),
                   Pair(Symbol('INDEX'), fixture.call('EL:DLIndex', catalog))]
        fixture.h.builtins.update({'EL:PICKMODEL': pick, 'EL:DLSNAPSHOT': lambda: library})
        fixture.h.run('(EL:FixedStatPick)')
        self.assertEqual([args[0] for args in picks], [Symbol('PANEL'), Symbol('WIRE'), Symbol('WIRE')])
        cfg = fixture.h.lookup('*EL:FIXEDCONFIG*')
        result = fixture.h.lookup('*EL:RESULT*')
        self.assertTrue(truth(fixture.call('EL:FreshResult', result, cfg)))
        fixture.entities['w1'].append(Pair(6, 'DASHED'))
        self.assertFalse(truth(fixture.call('EL:CollectSourceCurrent', cfg, result)))
        # The selected start now fails the recorded style filter. The current
        # explicit-start path aborts safely instead of returning a new network.
        with self.assertRaisesRegex(RuntimeError, 'quit / exit abort'):
            fixture.call('EL:FreshResult', result, cfg)
