"""Panel number lifecycle checks. Date: 2026-10-11."""
import unittest
import test_diagram_update as update
from autolisp_host import Pair, truth

class PanelNumberTests(unittest.TestCase):
    generation_fixture = update.UpdateTests.generation_fixture
    entity = update.UpdateTests.entity
    setUp = update.UpdateTests.setUp
    call = update.UpdateTests.call
    get = update.UpdateTests.get
    install_transaction = update.UpdateTests.install_transaction

    def test_default_and_plan_caption(self):
        self.assertEqual(self.call('EL:PanelNumber', None), '暂无编号')
        self.h.run('(setq result (EL:Put \'panel-number "ZZ-B1ALE(JZ)" result))')
        self.h.run("(setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))")
        labels=self.h.run('(EL:CCKKLabels plan)')
        self.assertEqual(self.get('text', labels[0]), 'ZZ-B1ALE(JZ)')

    def test_save_readback_and_new_pick_wins(self):
        self.install_transaction()
        self.h.builtins['EL:TEMPLATEREADY']=lambda *args: None
        self.h.run('(setq result (EL:Put \'panel-number "一层-ALE" result))')
        self.assertTrue(truth(self.h.run("(EL:SaveDraft result nil nil 'cap300)")))
        self.h.run('(setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertEqual(self.h.run("(EL:PanelNumber reopened)"), '一层-ALE')
        self.assertEqual(self.h.run("(EL:PanelNumber (EL:PreparedResult nil reopened))"), '一层-ALE')
        self.assertEqual(self.h.run("(EL:PanelNumber (EL:PreparedResult '((panel-number . \"新编号\")) reopened))"), '新编号')

    def test_skip_defaults_and_invalid_pick_retries(self):
        self.h.builtins['NENTSEL']=lambda *args: None
        self.assertEqual(self.call('EL:PickPanelNumber'), '暂无编号')
        picks=iter([['bad',[0,0,0]], ['num',[0,0,0]]])
        self.entities['bad']=[Pair(0,'LINE')]
        self.entities['num']=[Pair(0,'ATTRIB'),Pair(1,' ZZ-B1ALE(JZ) ')]
        self.h.builtins['NENTSEL']=lambda *args: next(picks)
        self.assertEqual(self.call('EL:PickPanelNumber'), 'ZZ-B1ALE(JZ)')

    def test_renumber_updates_existing_caption(self):
        self.h.run('(setq plan (EL:Put \'panel-number "二层-ALE" plan))')
        self.h.run('(EL:SyncCCKKLabels plan record store nil)')
        self.assertIn(('caption-panel-label', '二层-ALE'), self.writes)
        self.assertEqual(self.deleted, [])
