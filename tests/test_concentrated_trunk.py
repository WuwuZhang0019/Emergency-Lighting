"""Concentrated outlet boundary regression. Date: 2026-10-11.

Finite CAD adapters; native AutoCAD acceptance remains pending.
"""
import unittest
from autolisp_host import Pair, Symbol, truth
import test_fixed_diagnostics as diag
import test_post_stat_workflow as workflow


class TrunkTests(unittest.TestCase):
    call = diag.FixedDiagnosticTests.call
    get = diag.FixedDiagnosticTests.get
    line = diag.FixedDiagnosticTests.line
    block = diag.FixedDiagnosticTests.block
    plan = diag.FixedDiagnosticTests.plan
    logging = diag.FixedDiagnosticTests.logging
    def setUp(self):
        diag.FixedDiagnosticTests.setUp(self)
        self.selected = []
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.line('trunk', [10., -15., 0.], [10., 15., 0.], 'W')
        self.line('feed', [1., 0., 0.], [10., 0., 0.], 'W')
        self.selected = ['panel', 'trunk', 'feed']
        for i, y in enumerate((-12., -6., 0., 6., 12.)):
            self.line(f'w{i}', [10., y, 0.], [29., y, 0.], 'W')
            self.block('LAMP', 'D', f'd{i}', [30., y, 0.])
            self.selected += [f'w{i}', f'd{i}']
        self.cfg = self.call('EL:Put', Symbol('CONCENTRATED-TRUNK'), 'trunk', self.cfg)
        self.cfg = self.call('EL:Put', Symbol('AUTO-PANEL'), 'panel', self.cfg)

    def recognize(self):
        return self.call('EL:RecognizeFixed', self.cfg, 'panel')

    def assert_five(self, result):
        circuits = self.get('circuits', result)
        self.assertEqual(len(circuits), 5)
        self.assertEqual(sorted(sorted(self.get('devices', c)) for c in circuits),
                         [[f'd{i}'] for i in range(5)])
        for c in circuits:
            self.assertNotIn('trunk', self.get('wires', c))
            self.assertNotIn('feed', self.get('wires', c))
        self.assertTrue(truth(self.get('complete', result)))

    def test_five_outlets_do_not_merge_at_shared_root(self):
        self.assert_five(self.recognize())

    def test_middle_outlet_and_feeder_can_be_one_entity(self):
        self.selected.remove('feed')
        self.line('w2', [1., 0., 0.], [29., 0., 0.], 'W')
        self.assert_five(self.recognize())

    def test_open_polyline_trunk_and_entity_order_are_supported(self):
        self.entities['trunk'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'trunk'), Pair(8, 'W'),
            Pair(70, 0), Pair(38, 0.), Pair(210, [0., 0., 1.]), Pair(410, 'Model'),
            Pair(10, [10., -15.]), Pair(10, [10., 0.]), Pair(10, [10., 15.])]
        result = self.recognize()
        self.assert_five(result)
        self.selected.reverse()
        second = self.recognize()
        self.assertEqual(self.get('candidate-keys', result), self.get('candidate-keys', second))

    def test_source_freshness_includes_trunk_and_feeder(self):
        result = self.recognize()
        self.assertTrue(truth(self.call('EL:FreshResult', result, self.cfg)))
        self.line('trunk', [10., -16., 0.], [10., 16., 0.], 'W')
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.cfg)))

    def test_different_elevation_is_not_an_outlet(self):
        self.line('upper', [10., 3., 5.], [29., 3., 5.], 'W')
        self.selected.append('upper')
        self.assert_five(self.recognize())

    def test_saved_association_uses_exact_trunk_handle(self):
        store = self.h.run("'((diagrams ((source-panel-handle . \"panel\") (config (concentrated-trunk . \"trunk\")))))")
        self.assertEqual(self.call('EL:TrunkSavedPanel', 'trunk', store), 'panel')
        self.assertIsNone(self.call('EL:TrunkSavedPanel', 'other', store))

    def test_missing_feeder_or_overlapping_wire_stops_instead_of_guessing(self):
        def require(ok, message):
            if not truth(ok):
                raise RuntimeError(message)
            return ok
        self.h.builtins['EL:REQUIRE'] = require
        self.selected.remove('feed')
        with self.assertRaisesRegex(RuntimeError, '唯一'):
            self.recognize()
        self.selected.append('feed')
        self.line('duplicate', [10., -10., 0.], [10., 10., 0.], 'W')
        self.selected.append('duplicate')
        with self.assertRaisesRegex(RuntimeError, '重叠'):
            self.recognize()

    def test_shared_downstream_device_blocks_generation(self):
        self.line('join', [20., -12., 0.], [20., -6., 0.], 'W')
        self.selected.append('join')
        result = self.recognize()
        computed = self.call('EL:PanelCompute', result, self.h.run("'((\"LAMP\" . 5))"), self.cfg)
        self.assertFalse(truth(self.get('can-generate', computed)))

    def test_config_validation_and_native_record_roundtrip(self):
        import test_diagram_store as db
        self.assertTrue(truth(self.call('EL:ConfigValid', self.cfg, 'adapter-fixture.dwg')))
        result = self.recognize()
        fixture = db.StoreTests()
        fixture.setUp()
        fixture.h.load_definitions(db.ROOT/'src/diagram-update.lsp')
        fixture.h.load_definitions(db.ROOT/'src/config.lsp')
        fixture.h.frames[0]['TRUNKCFG'] = self.cfg
        fixture.h.frames[0]['CIRCUITS'] = self.get('circuits', result)
        fixture.h.run('''(setq record (list '(source-panel-handle . "panel")
          (cons 'config trunkcfg) (cons 'draft-circuits circuits)))
          (setq store (EL:Put 'diagrams (list record) (EL:StoreInitial)))''')
        self.assertTrue(truth(fixture.h.run('(EL:StoreWrite store)')))
        self.assertTrue(truth(fixture.h.run('(equal store (EL:StoreRead))')))

    def test_first_pick_and_saved_pick_reach_existing_panel(self):
        picks = iter([['trunk', [10., 0., 0.]], ['panel', [0., 0., 0.]]])
        seen = []
        steps=[]
        self.entities['number']=[Pair(0,'TEXT'),Pair(1,'ZZ-B1ALE(JZ)')]
        def number(prompt): steps.append('number'); return ['number',[0,0,0]]
        self.h.builtins['NENTSEL']=number
        def model(*args): steps.append('model'); return next(picks)
        self.h.builtins['EL:PICKMODEL'] = model
        self.h.builtins['EL:EDITPANEL'] = lambda result, cfg: seen.append((result, cfg))
        self.call('EL:FixedTrunkPick')
        self.assert_five(seen[0][0])
        self.assertEqual(self.get('concentrated-trunk', seen[0][1]), 'trunk')
        store = self.h.run("'((diagrams ((source-panel-handle . \"panel\") (config (concentrated-trunk . \"trunk\")))))")
        self.h.builtins['EL:STOREREAD'] = lambda: store
        picks = iter([['trunk', [10., 0., 0.]]])
        self.call('EL:FixedTrunkPick')
        self.assert_five(seen[1][0])
        self.assertEqual(steps,['model','model','number','model','number'])
        for result,cfg in seen:
            self.assertEqual(self.get('panel-number',result),'ZZ-B1ALE(JZ)')

    def test_trunk_outlets_without_devices_return_feedback_and_log(self):
        self.selected = [x for x in self.selected if not x.startswith('d')]
        picks = iter([['trunk', [10., 0., 0.]], ['panel', [0., 0., 0.]]])
        alerts, returns = [], []
        self.h.builtins.update({'EL:PICKMODEL': lambda *args: next(picks),
            'ALERT': alerts.append, 'EL:PANELSTARTDIALOG': lambda: returns.append(True),
            'EL:EDITPANEL': lambda *args: self.fail('empty result reached editor')})
        self.call('EL:FixedTrunkPick')
        self.assertIn('未识别到连接设备', alerts[0])
        self.assertEqual(returns, [True])
        self.assertEqual(self.writes, [])
        self.assertFalse(truth(self.h.lookup('*EL:RESULT*')))
        self.assertIn('NO_CONNECTED_DEVICES', self.log.read_text(encoding='utf-8'))

    def test_only_trunk_line_preserves_validation_reason_in_log(self):
        self.selected = ['panel', 'trunk']
        self.line('trunk', [1., 0., 0.], [10., 0., 0.], 'W')
        picks = iter([['trunk', [10., 0., 0.]], ['panel', [0., 0., 0.]]])
        self.h.builtins['EL:PICKMODEL'] = lambda *args: next(picks)
        with self.assertRaises(RuntimeError) as caught:
            self.call('EL:FixedTrunkPick')
        self.call('*ERROR*', str(caught.exception))
        self.assertEqual(self.writes, [])
        log = self.log.read_text(encoding='utf-8')
        self.assertIn('VALIDATION_FAILED', log)
        self.assertIn('未找到唯一的箱体到集中干线连接段', log)
        self.assertIn('未找到唯一的箱体到集中干线连接段', ''.join(self.messages))


class TrunkDialogTests(unittest.TestCase):
    call = workflow.PostStatWorkflowTests.call
    get = workflow.PostStatWorkflowTests.get
    line = workflow.PostStatWorkflowTests.line
    block = workflow.PostStatWorkflowTests.block
    plan = workflow.PostStatWorkflowTests.plan
    logging = workflow.PostStatWorkflowTests.logging
    done = workflow.PostStatWorkflowTests.done
    start = workflow.PostStatWorkflowTests.start
    dialog = workflow.PostStatWorkflowTests.dialog
    setUp = workflow.PostStatWorkflowTests.setUp
    def test_trunk_button_dispatches_after_dialog_closes(self):
        seen = []
        self.h.builtins['EL:FIXEDTRUNKPICK'] = lambda: seen.append('trunk')
        self.actions = [lambda: self.done(10)]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(seen, ['trunk'])
        self.assertIsNone(self.h.lookup('*EL:DIALOGID*'))

    def test_existing_panel_can_switch_to_trunk(self):
        self.actions = [lambda: self.done(10)]
        self.assertEqual(self.get('pick-panel', self.dialog()), Symbol('TRUNK'))


if __name__ == '__main__':
    unittest.main()
