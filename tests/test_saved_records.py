"""Saved-record navigation with finite CAD adapters. Date: 2026-10-13."""
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

    def initial_store(self):
        labels = []
        store = self.call('EL:Put', Symbol('DIAGRAMS'), self.records * 2, None)
        self.h.builtins['EL:STOREREAD'] = lambda: store
        self.h.builtins['ADD_LIST'] = labels.append
        self.call('EL:HistoryRememberStore', store)
        return labels

    def test_first_open_does_not_load_records_pick_or_write(self):
        labels = self.initial_store()
        self.h.builtins['EL:STOREREAD'] = lambda: self.fail('initial frame read the full store')
        self.h.builtins['EL:PICKMODEL'] = lambda *args: self.fail('unexpected pick')
        self.actions = [lambda: self.done(0)]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(labels, [])
        self.assertEqual(self.tiles['h_load'], '加载保存记录')
        self.assertIn('点击加载', self.tiles['h_detail'])
        self.assertEqual(self.saved, [])
        self.assertEqual(self.writes, [])

    def test_first_open_can_open_record_without_saving_empty_draft(self):
        self.initial_store()
        opened = []
        self.h.builtins['EL:EDITPANEL'] = lambda result, cfg: opened.append((result, cfg))
        self.h.builtins['EL:FRESHRESULT'] = lambda *args: self.fail('empty draft checked')
        self.actions = [lambda: self.done(13)]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(len(opened), 1)
        self.assertEqual(self.get('name', opened[0][1]), 'other')
        self.assertEqual(self.saved, [])
        self.assertEqual(self.writes, [])

    def test_first_open_recognition_error_returns_to_records(self):
        labels = self.initial_store()
        self.h.builtins['EL:RECOGNIZEFIXED'] = lambda *args: (_ for _ in ()).throw(RuntimeError('failed'))
        self.actions = [lambda: self.done(13), lambda: self.done(0)]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(len(labels), 2)
        self.assertEqual(self.saved, [])

    def test_load_button_opens_first_record_without_second_click(self):
        self.initial_store()
        callbacks, opened = {}, []
        self.h.builtins['ACTION_TILE'] = lambda key, code: callbacks.__setitem__(key, code)
        self.h.builtins['EL:EDITPANEL'] = lambda result, cfg: opened.append((result, cfg))
        self.h.builtins['EL:PANELSTORE'] = lambda: self.fail('empty draft must not be stored')
        self.actions = [lambda: self.h.run(callbacks['h_load'])]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(len(opened), 1)
        self.assertEqual(self.get('name', opened[0][1]), 'other')
        self.assertEqual(self.saved, [])

    def test_single_click_from_panel_keeps_edited_power_before_switch(self):
        self.initial_store()
        callbacks = {}
        self.h.builtins['ACTION_TILE'] = lambda key, code: callbacks.__setitem__(key, code)
        def click():
            self.tiles['b_watts0'] = '7'
            self.h.run(callbacks['h_records'].replace('$value', '"0"'))
        self.actions = [click]
        edited = self.dialog()
        self.assertTrue(self.get('switch-result', edited))
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.call('EL:Get', 'LAMP', self.saved[0][2]), 7)

    def test_click_does_not_leave_panel_for_invalid_power_or_missing_target(self):
        self.h.builtins['EL:PANELSTORE'] = lambda: None
        self.call('EL:HistoryClick', '0')
        self.assertIsNone(self.closed)
        self.h.builtins['HANDENT'] = lambda value: None
        self.h.builtins['EL:PANELSTORE'] = lambda: self.fail('missing target must not store')
        self.call('EL:HistoryClick', '0')
        self.assertIsNone(self.closed)
        self.assertEqual(self.saved, [])

    def test_click_current_record_does_not_reload_or_save(self):
        self.h.set(Symbol('*EL:PANELDRAFT*'), self.call('EL:Put', Symbol('PANEL'), 'other', self.result))
        self.h.builtins['EL:PANELSTORE'] = lambda: self.fail('current record must stay open')
        self.call('EL:HistoryClick', '0')
        self.assertIsNone(self.closed)
        self.assertEqual(self.saved, [])

    def test_switch_saves_current_as_stale_and_returns_target(self):
        edited = self.call('EL:HistoryOpen')
        self.assertEqual(self.get('switch-result', edited),
                         self.call('EL:Put', Symbol('HISTORY-OPENED'), True, self.result))
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
        self.assertIn('暂无编号', self.tiles['h_detail'])

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
        self.call('EL:HistoryRememberStore', store)
        self.call('EL:HistoryFill')
        self.assertEqual(len(labels), 10)
        self.assertIn('[当前]', labels[4])
        self.assertEqual(self.tiles['h_records'], '4')

    def test_list_repaint_uses_session_data_without_reading_the_store(self):
        labels = self.initial_store()
        self.h.builtins['EL:STOREREAD'] = lambda: self.fail('list repaint read the full store')
        self.call('EL:HistoryFill')
        self.call('EL:HistoryFill')
        self.assertEqual(len(labels), 4)
        self.h.builtins['NAMEDOBJDICT'] = lambda: 'other-drawing'
        self.call('EL:HistoryFill')
        self.assertFalse(self.h.lookup('*EL:HISTORYRECORDS*'))
        self.assertEqual(self.tiles['h_load'], '加载保存记录')

    def test_failed_initial_load_returns_to_usable_pick_buttons(self):
        self.h.builtins['EL:STOREREAD'] = lambda: (_ for _ in ()).throw(RuntimeError('read failed'))
        picks = []
        self.h.builtins['EL:FIXEDSTATPICK'] = lambda: picks.append(True)
        self.actions = [lambda: self.done(13), lambda: self.done(9)]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(picks, [True])
        self.assertEqual(self.saved, [])

    def test_refresh_records_keeps_current_power_without_saving_or_relocating(self):
        self.initial_store()
        callbacks = {}
        self.h.builtins['ACTION_TILE'] = lambda key, code: callbacks.__setitem__(key, code)
        self.h.builtins['GETSTRING'] = lambda *args: self.fail('refresh must not locate in the drawing')
        def refresh():
            self.tiles['b_watts0'] = '7'
            self.h.run(callbacks['h_load'])
        def returned():
            self.assertEqual(self.tiles['b_watts0'], '7')
            self.done(0)
        self.actions = [refresh, returned]
        self.assertFalse(self.dialog())
        self.assertEqual(self.saved, [])
        self.assertEqual(self.writes, [])

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


class SavedRecordRestoreTests(unittest.TestCase):
    """Restore the stored baseline without geometry reads. Date: 2026-10-13."""

    def setUp(self):
        self.fixture = workflow.PostStatWorkflowTests()
        self.fixture.setUp()
        self.h = self.fixture.h
        self.call, self.get = self.fixture.call, self.fixture.get
        self.result, self.cfg = self.fixture.result, self.fixture.cfg
        self.record = None
        values = {
            'source-panel-handle': 'panel', 'engine': Symbol('FIXED'),
            'config': self.cfg, 'panel-circuits': self.get('circuits', self.result),
            'source-signature': self.get('signature', self.get('snapshot', self.result)),
            'rows': self.get('circuits', self.result), 'panel-number': '测试箱',
            'number-policy-version': self.get('number-policy-version', self.result),
            'number-inputs': self.get('number-inputs', self.result),
        }
        for key, value in values.items():
            self.record = self.call('EL:Put', Symbol(key.upper()), value, self.record)
        self.h.set(Symbol('*EL:PANELDRAFT*'), None)
        self.h.set(Symbol('*EL:HISTORYINDEX*'), 0)
        self.h.set(Symbol('*EL:HISTORYRECORDS*'), [self.record])

    def forbid_recognition(self):
        for name in ('EL:RECOGNIZEFIXED', 'EL:SIMPLECOLLECT', 'EL:SIMPLENETWORK',
                     'EL:NUMBERSOURCEINPUTS'):
            self.h.builtins[name] = lambda *args: self.fail('saved content reread source geometry')

    def test_formal_record_opens_with_circuits_devices_and_exact_saved_signature(self):
        self.forbid_recognition()
        self.h.builtins['EL:FRESHRESULT'] = lambda *args: self.fail('opening must not run freshness')
        opened = self.get('switch-result', self.call('EL:HistoryOpen'))
        self.assertTrue(self.get('history-restored', opened))
        self.assertEqual(self.get('signature', self.get('snapshot', opened)),
                         self.get('source-signature', self.record))
        prepared = self.call('EL:PreparedResult', opened, self.record)
        computed = self.call('EL:PanelCompute', prepared, self.fixture.powers, self.cfg)
        self.h.set(Symbol('*EL:PANELDRAFT*'), computed)
        self.h.set(Symbol('*EL:PANELPOWERS*'), self.fixture.powers)
        self.assertTrue(self.call('EL:PanelBlockRows'))
        self.assertEqual(self.get('circuits', prepared), self.get('circuits', self.result))
        self.assertGreater(self.get('box-watts', computed), 0)
        self.assertEqual(self.get('panel-number', prepared), '测试箱')

    def test_draft_restores_its_own_signature_and_circuits(self):
        draft = self.call('EL:Put', Symbol('DRAFT-CIRCUITS'),
                          self.get('circuits', self.result), self.record)
        draft = self.call('EL:Put', Symbol('DRAFT-SOURCE-SIGNATURE'),
                          self.get('source-signature', self.record), draft)
        draft = self.call('EL:Put', Symbol('SOURCE-SIGNATURE'), 'older formal baseline', draft)
        draft = self.call('EL:Put', Symbol('DRAFT-NUMBER-POLICY-VERSION'), 1, draft)
        draft = self.call('EL:Put', Symbol('DRAFT-NUMBER-INPUTS'),
                          self.get('number-inputs', self.result), draft)
        self.forbid_recognition()
        restored = self.call('EL:HistoryRestore', draft)
        self.assertEqual(self.get('signature', self.get('snapshot', restored)),
                         self.get('draft-source-signature', draft))
        self.assertEqual(self.get('number-inputs', restored), self.get('draft-number-inputs', draft))
        missing = self.call('EL:Put', Symbol('DRAFT-SOURCE-SIGNATURE'), None, draft)
        self.assertFalse(self.call('EL:HistoryRestore', missing))
        reference = self.call('EL:Put', Symbol('SOURCE-SIGNATURE'),
                              self.get('source-signature', self.record), draft)
        reference = self.call('EL:Put', Symbol('DRAFT-SOURCE-SIGNATURE'), Symbol('FORMAL-SOURCE'), reference)
        self.assertEqual(self.get('signature', self.get('snapshot', self.call('EL:HistoryRestore', reference))),
                         self.get('source-signature', self.record))

    def test_legacy_output_rows_rebuild_once_instead_of_showing_empty_devices(self):
        legacy = self.call('EL:Put', Symbol('PANEL-CIRCUITS'), None, self.record)
        self.h.set(Symbol('*EL:HISTORYRECORDS*'), [legacy])
        calls = []
        self.h.builtins['EL:RECOGNIZEFIXED'] = lambda *args: calls.append(args) or self.result
        restored = self.get('switch-result', self.call('EL:HistoryOpen'))
        self.call('EL:HistoryOpen')
        self.assertEqual(calls, [(self.cfg, 'panel')])
        self.assertEqual(restored, self.call('EL:Put', Symbol('HISTORY-OPENED'), True, self.result))
        changed = self.call('EL:Put', Symbol('PANEL-NUMBER'), '新编号', legacy)
        self.h.set(Symbol('*EL:HISTORYRECORDS*'), [changed])
        self.call('EL:HistoryOpen')
        self.assertEqual(len(calls), 2)

    def test_saved_baseline_still_rejects_live_changes_on_submission(self):
        restored = self.call('EL:HistoryRestore', self.record)
        self.assertTrue(self.call('EL:FreshResult', restored, self.cfg))
        changed = self.call('EL:Put', Symbol('SIGNATURE'), 'changed live drawing',
                            self.get('snapshot', self.result))
        scans = []
        self.h.builtins['EL:FIXEDFRESHSNAPSHOT'] = lambda *args: scans.append(args) or changed
        self.assertFalse(self.call('EL:FreshResult', restored, self.cfg))
        self.assertEqual(scans, [(self.cfg, 'panel')])

    def test_closing_saved_record_does_not_mark_stale_or_write(self):
        record = self.call('EL:Put', Symbol('PANEL-OUTPUT-HANDLE'), 'existing-output', self.record)
        store = self.call('EL:Put', Symbol('DIAGRAMS'), [record], None)
        self.h.builtins['EL:STOREREAD'] = lambda: store
        self.h.builtins['EL:PANELDIALOG'] = lambda *args: None
        self.h.builtins['EL:MARKSTALE'] = lambda *args: self.fail('closing history must not write')
        self.h.builtins['EL:STOREWRITE'] = lambda *args: self.fail('closing history must not write')
        opened = self.get('switch-result', self.call('EL:HistoryOpen'))
        self.assertFalse(self.call('EL:EditPanelOnce', opened, self.cfg))


if __name__ == '__main__':
    unittest.main()
