"""Saved-record navigation with finite CAD adapters. Date: 2026-10-10."""
import unittest
import test_post_stat_workflow as workflow
from autolisp_host import Symbol


class SavedRecordsTests(unittest.TestCase):
    call = workflow.PostStatWorkflowTests.call
    get = workflow.PostStatWorkflowTests.get
    line = workflow.PostStatWorkflowTests.line
    block = workflow.PostStatWorkflowTests.block
    plan = workflow.PostStatWorkflowTests.plan
    logging = workflow.PostStatWorkflowTests.logging
    done = workflow.PostStatWorkflowTests.done
    start = workflow.PostStatWorkflowTests.start
    dialog = workflow.PostStatWorkflowTests.dialog

    def setUp(self):
        workflow.PostStatWorkflowTests.setUp(self)
        self.records = self.h.run("'(((source-panel-handle . \"other\") (engine . fixed) (status . stale) (config (name . \"other\"))))")
        self.h.run('(setq *EL:HistoryIndex* 0)')
        self.h.set(Symbol('*EL:HISTORYRECORDS*'), self.records)
        self.h.set(Symbol('*EL:PANELDRAFT*'), self.result)
        self.h.set(Symbol('*EL:PANELCONFIG*'), self.cfg)
        self.h.set(Symbol('*EL:PANELPOWERS*'), self.powers)
        self.h.set(Symbol('*EL:PANELCAPACITY*'), Symbol('CAP300'))
        self.saved = []
        self.h.builtins.update({
            'ALERT': lambda message: None,
            'HANDENT': lambda value: value,
            'EL:RECOGNIZEFIXED': lambda cfg, panel: self.result,
            'EL:FRESHRESULT': lambda *args: True,
            'EL:REMEMBERPANELPOWERS': lambda *args: True,
            'EL:SAVEDRAFT': lambda *args: self.saved.append(args) or True,
        })

    def test_switch_saves_current_as_stale_and_returns_target(self):
        edited = self.call('EL:HistoryOpen')
        self.assertEqual(self.get('switch-result', edited), self.result)
        self.assertEqual(self.get('name', self.get('switch-config', edited)), 'other')
        self.assertEqual(len(self.saved), 1)
        self.assertFalse(self.get('can-generate', self.saved[0][0]))
        self.assertEqual(self.get('panel', self.saved[0][0]), 'panel')

    def test_missing_target_never_saves_current(self):
        self.h.builtins['HANDENT'] = lambda value: None
        with self.assertRaises(Exception):
            self.call('EL:HistoryOpen')
        self.assertEqual(self.saved, [])

    def test_changed_source_never_saves_current(self):
        self.h.builtins['EL:FRESHRESULT'] = lambda *args: None
        with self.assertRaises(Exception):
            self.call('EL:HistoryOpen')
        self.assertEqual(self.saved, [])

    def test_failed_save_does_not_return_switch(self):
        self.h.builtins['EL:SAVEDRAFT'] = lambda *args: None
        with self.assertRaises(Exception):
            self.call('EL:HistoryOpen')

    def test_select_is_read_only_and_missing_target_disabled(self):
        modes = []
        self.h.builtins['MODE_TILE'] = lambda *args: modes.append(args)
        self.h.builtins['HANDENT'] = lambda value: None
        self.call('EL:HistorySelect', '0')
        self.assertEqual(modes[-1], ('h_open', 1))
        self.assertEqual(self.saved, [])
        self.assertIn('other', self.tiles['h_detail'])

    def test_navigation_loop_uses_target_config(self):
        calls = []
        target_cfg = self.get('config', self.records[0])
        next_value = self.call('EL:HistoryOpen')
        def once(result, cfg):
            calls.append((result, cfg))
            return next_value if len(calls) == 1 else None
        self.h.builtins['EL:EDITPANELONCE'] = once
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1], target_cfg)

    def test_ten_records_are_listed_and_current_is_selected(self):
        records = [self.call('EL:Put', Symbol('SOURCE-PANEL-HANDLE'),
                            'panel' if i == 4 else str(i), self.records[0])
                   for i in range(10)]
        store = self.call('EL:Put', Symbol('DIAGRAMS'), records, None)
        labels = []
        self.h.builtins['EL:STORERead'.upper()] = lambda: store
        self.h.builtins['ADD_LIST'] = labels.append
        self.call('EL:HistoryFill')
        self.assertEqual(len(labels), 10)
        self.assertIn('[当前]', labels[4])
        self.assertEqual(self.tiles['h_records'], '4')

    def test_failed_switch_returns_same_dialog_and_keeps_input(self):
        self.h.builtins['EL:HISTORYOPEN'] = lambda: (_ for _ in ()).throw(RuntimeError('save failed'))
        self.h.builtins['GETSTRING'] = lambda *args: self.fail('unexpected locate prompt')
        def first():
            self.tiles['b_watts0'] = '7'
            self.call('EL:PanelStore')
            self.done(8)
        def second():
            self.assertEqual(self.tiles['b_watts0'], '7')
            self.done(0)
        self.actions = [first, second]
        self.assertFalse(self.dialog())
        self.assertEqual(len(self.dialogs), 2)


if __name__ == '__main__':
    unittest.main()
