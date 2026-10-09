"""Post-statistics setup and explicit selection gates. Date: 2026-10-09.

Runs actual command/dialog functions with finite CAD/DCL adapters.
"""
import unittest
import test_fixed_diagnostics as diag
import test_diagram_store as db
from autolisp_host import Symbol, truth


class PostStatWorkflowTests(unittest.TestCase):
    call = diag.FixedDiagnosticTests.call
    get = diag.FixedDiagnosticTests.get
    line = diag.FixedDiagnosticTests.line
    block = diag.FixedDiagnosticTests.block
    plan = diag.FixedDiagnosticTests.plan
    logging = diag.FixedDiagnosticTests.logging

    def setUp(self):
        diag.FixedDiagnosticTests.setUp(self)
        self.capture_calls, self.actions = [], []
        self.closed = None
        self.h.builtins.update({'GET_TILE': lambda key: self.tiles.get(key, ''),
                               'DONE_DIALOG': self.done,
                               'START_DIALOG': self.start})
        self.result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        record = self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial'))
        self.result = self.call('EL:PreparedResult', self.result, record)
        self.powers = self.h.run("'((\"LAMP\" . 5))")

    def done(self, status):
        self.closed = status

    def start(self):
        self.closed = None
        self.actions.pop(0)()
        self.assertIsNotNone(self.closed, 'test action must close the dialog')
        return self.closed

    def confirm(self):
        self.call('EL:PanelCapacity', 'p_600')

    def dialog(self):
        return self.call('EL:PanelDialog', self.result, self.cfg, self.powers, None)

    def test_statistics_without_template_open_panel_without_setup_or_publication(self):
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = lambda cfg: self.fail('setup before generation')
        self.h.builtins['EL:PUBLISHDIAGRAM'] = lambda *args: self.fail('must not publish before review')
        self.actions = [lambda: self.done(0)]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.tiles['p_capacity'], 'p_300')
        self.assertNotIn('待核对',self.tiles['p_capacity_status'])
        self.assertIn('/普通', self.tiles['p_row0'])
        self.assertIn('点击生成时设置', self.tiles['p_template_status'])
        self.assertEqual(self.writes, [])

    def test_default_capacity_generates_without_extra_confirmation(self):
        self.h.builtins['EL:TEMPLATEREADY']=lambda *args:True
        def action():
            self.call('EL:PanelGenerate')
            self.assertEqual(self.closed,2)
            self.assertTrue(truth(self.call('EL:SelectionsReady',self.h.lookup('*EL:PANELDRAFT*'),Symbol('CAP300'))))
        self.actions = [action]
        edited = self.dialog()
        self.assertEqual(self.get('capacity',edited),Symbol('CAP300'))
        self.assertEqual(self.get('capacity-source',self.get('result',edited)),Symbol('DEFAULT'))
        self.assertTrue(truth(self.get('generate',edited)))
        self.assertEqual(self.writes, [])

    def test_save_records_all_pages_without_changing_checkbox_values(self):
        def action():
            self.h.run("(setq cs (EL:Get 'circuits *EL:PanelDraft*) c (car cs) n 2) (repeat 9 (setq cs (append cs (list (EL:Put 'id (strcat \"R\" (itoa n)) c))) n (1+ n))) (setq *EL:PanelDraft* (EL:Put 'circuits cs *EL:PanelDraft*))")
            self.call('EL:PanelGround', 0, '1')
            self.call('EL:PanelPage', 8)
            self.call('EL:PanelGround', 8, '1')
            self.call('EL:PanelAccept')
        self.actions = [action]
        edited = self.dialog()
        circuits = self.get('circuits', self.get('result', edited))
        self.assertGreater(len(circuits), 8)
        self.assertTrue(all(self.get('ground-source', c) == Symbol('MANUAL') for c in circuits))
        self.assertTrue(truth(self.get('is-ground', circuits[0])))
        self.assertTrue(truth(self.get('is-ground', circuits[8])))
        self.assertFalse(truth(self.get('is-ground', circuits[1])))

    def test_cancelled_setup_returns_to_same_draft_without_saving(self):
        def capture(cfg):
            self.capture_calls.append(cfg)
            return None
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = capture
        def first():
            self.tiles['p_watts'] = '7'
            self.confirm()
            self.call('EL:PanelGenerate')
        def second():
            self.assertEqual(self.tiles['p_watts'], '7')
            self.assertEqual(self.tiles['p_capacity'], 'p_600')
            self.assertIn('/普通', self.tiles['p_row0'])
            self.done(1)
        self.actions = [first, second]
        edited = self.dialog()
        self.assertEqual(len(self.capture_calls), 1)
        self.assertEqual(len(self.dialogs), 2)
        self.assertEqual(self.call('EL:Get', 'LAMP', self.get('powers', edited)), 7)
        self.assertIsNone(self.get('template', self.get('config', edited)))
        self.assertEqual(self.writes, [])

    def test_escape_during_setup_returns_to_panel_and_preserves_draft(self):
        def capture(cfg):
            raise RuntimeError('Function cancelled')
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = capture
        self.actions = [lambda: (self.confirm(), self.call('EL:PanelGenerate')), lambda: self.done(0)]
        self.assertIsNone(self.dialog())
        self.assertEqual(len(self.dialogs), 2)
        self.assertIn('返回统计面板', ''.join(self.messages))
        self.assertEqual(self.writes, [])

    def test_successful_setup_returns_new_config_for_generation_without_repick(self):
        template = self.h.run("'((template-test . \"new\"))")
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = lambda cfg: template
        self.actions = [lambda: (self.confirm(), self.call('EL:PanelGenerate'))]
        edited = self.dialog()
        self.assertTrue(truth(self.get('generate', edited)))
        self.assertEqual(self.get('template', self.get('config', edited)), template)
        self.assertEqual(len(self.dialogs), 1)
        self.assertEqual(self.writes, [])

    def test_valid_template_is_reused_without_setup(self):
        self.h.builtins['EL:TEMPLATEREADY'] = lambda *args: True
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = lambda cfg: self.fail('valid template must be reused')
        self.actions = [lambda: (self.confirm(), self.call('EL:PanelGenerate'))]
        self.assertTrue(truth(self.get('generate', self.dialog())))

    def test_captured_config_reaches_sync_with_confirmed_choices(self):
        template = self.h.run("'((template-test . \"captured\"))")
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = lambda cfg: template
        self.h.builtins['EL:TEMPLATEREADY'] = lambda value, cfg: value == template
        self.h.builtins['EL:SIMPLELOADPOWERS'] = lambda: self.h.run("'((version . 1) (powers (\"LAMP\" . 5)))")
        self.h.builtins['EL:FRESHRESULT'] = lambda *args: True
        synced = []
        commands = []
        def cckk2():
            commands.append(self.h.lookup('*EL:CCKK2REQUEST*'))
            del self.h.builtins['C:CCKK2']
            try:
                return self.h.run('(c:CCKK2)')
            finally:
                self.h.builtins['C:CCKK2']=cckk2
        self.h.builtins['C:CCKK2']=cckk2
        self.h.builtins['EL:SYNCDIAGRAM'] = lambda *args: synced.append(args) or True
        self.h.builtins['EL:SAVEDRAFT'] = lambda *args: True
        self.h.builtins['EL:SAVENAMEPOWERS'] = lambda *args: True
        self.actions = [lambda: (self.confirm(), self.call('EL:PanelGenerate'))]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(len(synced), 1)
        self.assertEqual(len(commands),1)
        self.assertIsNone(self.h.lookup('*EL:CCKK2REQUEST*'))
        result, cfg, powers, capacity, generate, interactive = synced[0]
        self.assertEqual(self.get('template', cfg), template)
        self.assertEqual(capacity, Symbol('CAP600'))
        self.assertTrue(truth(self.call('EL:SelectionsReady', result, capacity)))
        self.assertTrue(truth(generate))

    def test_capacity_and_manual_no_restore_from_saved_draft(self):
        self.h.frames[0]['RESULT'] = self.result
        self.h.run("(setq saved (EL:Put 'ground-source 'manual (car (EL:Get 'circuits result))))")
        saved = self.h.lookup('SAVED')
        record = self.h.run("'((diagram-id . \"d\") (draft-capacity . cap600) (draft-capacity-source . manual))")
        record = self.call('EL:Put', Symbol('DRAFT-CIRCUITS'), [saved], record)
        record = self.call('EL:Put', Symbol('ROWS'), [saved], record)
        fresh = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        prepared = self.call('EL:PreparedResult', fresh, record)
        self.assertEqual(self.get('capacity-source', prepared), Symbol('MANUAL'))
        self.assertEqual(self.get('ground-source', self.get('circuits', prepared)[0]), Symbol('MANUAL'))
        self.assertFalse(truth(self.get('is-ground', self.get('circuits', prepared)[0])))

    def test_save_capacity_then_recognize_same_panel(self):
        persisted = [None]
        def write(value):
            persisted[0] = value
            return True
        self.h.builtins.update({
            'EL:STOREREAD': lambda: persisted[0],
            'EL:STOREWRITE': write,
            'EL:TRANSACTION': lambda fn, args: self.h.call(fn, args),
            'EL:SAVENAMEPOWERS': lambda *args: True,
        })
        for tile,capacity,source in ((None,'CAP300','DEFAULT'),('p_600','CAP600','MANUAL'),('p_1000','CAP1000','MANUAL')):
            with self.subTest(capacity=capacity):
                def accept():
                    if tile:self.call('EL:PanelCapacity',tile)
                    self.call('EL:PanelAccept')
                self.actions=[accept]
                self.call('EL:EditPanel',self.result,self.cfg)
                record=self.call('EL:DiagramForPanel','panel',persisted[0])
                self.assertEqual(self.get('draft-capacity',record),Symbol(capacity))
                self.assertEqual(self.get('draft-capacity-source',record),Symbol(source))
                fresh=self.call('EL:RecognizeFixed',self.cfg,'panel')
                self.actions=[lambda:self.done(0)]
                self.call('EL:EditPanel',fresh,self.cfg)
                self.assertEqual(self.tiles['p_capacity'],tile or 'p_300')

    def test_save_complete_statistics_without_template_still_saves_draft(self):
        self.h.builtins['EL:SIMPLELOADPOWERS'] = lambda: self.h.run("'((version . 1) (powers (\"LAMP\" . 5)))")
        self.h.builtins['EL:FRESHRESULT'] = lambda *args: True
        stored = []
        self.h.builtins['EL:SAVEDRAFT'] = lambda *args: stored.append(args) or True
        self.h.builtins['EL:SAVENAMEPOWERS'] = lambda *args: True
        self.h.builtins['EL:SYNCDIAGRAM'] = lambda *args: self.fail('missing template cannot sync')
        self.actions = [lambda: self.done(1)]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0][3],Symbol('CAP300'))

    def test_shared_sync_rejects_unconfirmed_fixed_result(self):
        self.h.builtins['EL:STOREREAD'] = lambda: None
        self.h.builtins['EL:MARKSTALE'] = lambda *args: None
        self.h.builtins['EL:TRANSACTION'] = lambda *args: self.fail('unconfirmed result cannot mutate DWG')
        result = self.call('EL:PanelCompute', self.result, self.powers, self.cfg)
        self.assertIsNone(self.call('EL:SyncDiagram', result, self.cfg, self.powers, Symbol('CAP300'), True, True))
        self.assertIn('尚未确认', ''.join(self.messages))

    def test_legacy_generation_retains_capacity_fallback_without_fixed_review(self):
        self.h.frames[0]['*EL:RESULT*'] = self.call('EL:Put', Symbol('ENGINE'), Symbol('LEGACY'), self.result)
        self.h.builtins['EL:BOXSTATISTICS'] = lambda result, *args: result
        self.h.builtins['EL:LOADLIBRARY'] = lambda: None
        self.h.builtins['EL:EDITPANEL'] = lambda *args: self.fail('legacy path must remain separate')
        synced = []
        self.h.builtins['EL:SYNCDIAGRAM'] = lambda *args: synced.append(args)
        self.h.run('(c:ELGEN)')
        self.assertEqual(len(synced), 1)
        self.assertEqual(synced[0][3], Symbol('CAP300'))

    def test_prepared_record_template_is_reused_for_same_box(self):
        template = self.h.run("'((test-template . \"saved\"))")
        record = self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial'))
        record = self.call('EL:Put', Symbol('CONFIG'), self.call('EL:Put', Symbol('TEMPLATE'), template, self.cfg), record)
        store = self.call('EL:StorePutDiagram', record, self.call('EL:StoreInitial'))
        self.h.builtins['EL:STOREREAD'] = lambda: store
        self.h.builtins['EL:TEMPLATEREADY'] = lambda value, cfg: value == template
        self.actions = [lambda: self.done(0)]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertIn('模板已验证', self.tiles['p_template_status'])

    def test_drawing_template_cache_is_reused_for_other_box(self):
        template = self.h.run("'((test-template . \"drawing-cache\"))")
        store = self.call('EL:Put', Symbol('FIXED-TEMPLATE'), template, self.call('EL:StoreInitial'))
        self.h.builtins['EL:STOREREAD'] = lambda: store
        self.h.builtins['EL:TEMPLATEREADY'] = lambda value, cfg: value == template
        self.actions = [lambda: self.done(0)]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertIn('模板已验证', self.tiles['p_template_status'])

    def test_cancelled_review_preserves_old_choices_and_marks_output_unupdated(self):
        record = self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial'))
        record = self.call('EL:Put', Symbol('PANEL-OUTPUT-HANDLE'), 'old-output', record)
        record = self.call('EL:Put', Symbol('CAPACITY-OPTION'), Symbol('CAP300'), record)
        store = self.call('EL:StorePutDiagram', record, self.call('EL:StoreInitial'))
        self.h.builtins['EL:STOREREAD'] = lambda: store
        self.h.builtins['EL:TRANSACTION'] = lambda fn, args: self.h.call(fn, args)
        self.h.builtins['EL:SYNCDIAGRAM'] = lambda *args: self.fail('cancel must not change output')
        self.actions = [lambda: (self.confirm(), self.done(0))]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(len(self.writes), 1)
        stored = self.call('EL:DiagramForPanel', 'panel', self.writes[0])
        self.assertEqual(self.get('capacity-option', stored), Symbol('CAP300'))
        self.assertEqual(self.get('panel-output-handle', stored), 'old-output')
        self.assertEqual(self.get('stale-reason', stored), Symbol('REVIEW-CANCELLED'))
        self.assertIsNone(self.get('draft-capacity', stored))


class SelectionStoreTests(unittest.TestCase):
    def setUp(self):
        db.StoreTests.setUp(self)
        for name in ('config', 'geometry', 'topology', 'statistics', 'generation', 'fixed', 'panel', 'diagram-update', 'diagram-commands'):
            self.h.load_definitions(db.ROOT / 'src' / f'{name}.lsp')
        self.h.builtins['EL:TRANSACTION'] = lambda fn, args: self.h.call(fn, args)
        self.h.builtins['EL:TEMPLATEREADY'] = lambda template, cfg: truth(template)

    def test_draft_confirmation_and_shared_template_roundtrip_through_xrecord(self):
        self.h.run('''(setq cfg '((template (name . "captured"))))
          (setq result '((panel . "source") (engine . fixed) (capacity-source . manual) (can-generate . T)
            (circuits ((id . "R1") (seed (key "wire" outlet)) (circuit-uid . "u1")
              (seed-key "wire" outlet) (is-ground) (ground-source . manual)))))
          (EL:SaveDraft result cfg nil 'cap600)
          (setq result nil cfg nil)
          (setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))''')
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity reopened)"), Symbol('CAP600'))
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity-source reopened)"), Symbol('MANUAL'))
        self.assertEqual(self.h.run("(EL:Get 'ground-source (car (EL:Get 'draft-circuits reopened)))"), Symbol('MANUAL'))
        self.assertIsNone(self.h.run("(EL:Get 'is-ground (car (EL:Get 'draft-circuits reopened)))"))
        self.assertEqual(self.h.run("(EL:Get 'name (EL:Get 'fixed-template (EL:StoreRead)))"), 'captured')

    def test_missing_capacity_defaults_but_unconfirmed_types_remain_stale(self):
        self.h.run('''(EL:SaveDraft '((panel . "source") (engine . fixed) (can-generate . T)
          (circuits ((id . "R1") (seed-key "wire" outlet) (ground-source . default)))) nil nil nil)
          (setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))''')
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity reopened)"),Symbol('CAP300'))
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity-source reopened)"),Symbol('DEFAULT'))
        self.assertEqual(self.h.run("(EL:Get 'status reopened)"), Symbol('STALE'))


if __name__ == '__main__':
    unittest.main()
