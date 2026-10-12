"""Empty-DWG ELSTAT initialization. Date: 2026-10-12.

Finite DCL adapters enforce valid list selection; they do not reproduce a
native AutoCAD process crash or establish native dialog acceptance.
"""
import unittest

from autolisp_host import Pair, Symbol, truth
import test_post_stat_workflow as workflow


class EmptyPanelTests(unittest.TestCase):
    call = workflow.PostStatWorkflowTests.call
    get = workflow.PostStatWorkflowTests.get
    line = workflow.PostStatWorkflowTests.line
    block = workflow.PostStatWorkflowTests.block
    plan = workflow.PostStatWorkflowTests.plan
    logging = workflow.PostStatWorkflowTests.logging
    done = workflow.PostStatWorkflowTests.done
    start = workflow.PostStatWorkflowTests.start

    def setUp(self):
        workflow.PostStatWorkflowTests.setUp(self)
        self.entities.clear()
        self.blocks.clear()
        self.bounds.clear()
        self.selected = []
        self.h.run('(setq *EL:Result* nil *EL:PanelDraft* nil)')
        self.items, self.modes, self.unloaded, self.callbacks = [], {}, [], {}
        self.h.builtins.update({
            'ATOI': lambda value: 0 if value == '' else int(value),
            'NAMEDOBJDICT': lambda: 'empty-dwg-nod',
            'DICTSEARCH': lambda *args: None,
            'START_LIST': lambda key: self.items.clear(),
            'ADD_LIST': self.items.append,
            'MODE_TILE': lambda key, mode: self.modes.__setitem__(key, mode),
            'SET_TILE': self.set_tile,
            'UNLOAD_DIALOG': self.unloaded.append,
            'ACTION_TILE': lambda key, code: self.callbacks.__setitem__(key, code),
            'EL:LOADCONFIG': lambda: self.fail('config read before model pick'),
            'EL:PICKMODEL': lambda *args: self.fail('model pick before button click'),
            'HANDENT': lambda handle: self.fail('handle lookup in empty drawing'),
        })
        self.actions = [lambda: self.done(0)]

    def set_tile(self, key, value):
        if key == 'h_records' and value:
            # Documented DCL value is a zero-based index into actual items.
            self.assertTrue(0 <= int(value) < len(self.items),
                            'empty list must not select a nonexistent item')
        self.tiles[key] = value
        return value

    def log_text(self):
        return self.log.read_text(encoding='utf-8')

    def test_unsaved_and_saved_empty_drawings_reach_interaction_without_writes(self):
        getvar = self.h.builtins['GETVAR']
        for titled in (0, 1):
            with self.subTest(titled=titled):
                self.h.builtins['GETVAR'] = lambda key: titled if key == 'DWGTITLED' else getvar(key)
                self.actions = [lambda: self.done(0)]
                self.h.run('(c:ELSTAT)')
                self.assertEqual(self.items, [])
                self.assertEqual(self.tiles['h_records'], '')
                self.assertEqual(self.tiles['h_detail'], '本图暂无保存记录')
                self.assertEqual(self.modes['h_records'], 1)
                self.assertEqual(self.modes['h_open'], 1)
                self.assertEqual(self.modes['accept'], 1)
                self.assertEqual(self.modes['p_generate'], 1)
                self.assertEqual(self.modes['b_library'], 0)
                self.assertEqual(self.modes['b_apply_library'], 1)
                self.assertEqual(self.modes['p_pick'], 0)
                self.assertEqual(self.modes['p_trunk'], 0)
                self.assertEqual(self.writes, [])
                self.assertIsNone(self.h.lookup('*EL:DIALOGID*'))
                self.assertFalse(truth(self.h.lookup('*EL:PERFACTIVE*')))
        self.assertEqual(self.dialogs, ['el_panel', 'el_panel'])
        self.assertEqual(self.unloaded, [1, 1])

    def test_empty_history_callbacks_never_close_dialog_or_lookup_handle(self):
        self.h.run('(setq *EL:HistoryRecords* nil *EL:HistoryIndex* nil)')
        for value in ('', None, '0', '-1', '9'):
            with self.subTest(value=value):
                self.call('EL:HistoryClick', value)
                self.assertIsNone(self.closed)
                self.assertIsNone(self.h.lookup('*EL:HISTORYINDEX*'))
                self.assertEqual(self.modes['h_open'], 1)
                self.assertEqual(self.writes, [])

    def test_empty_panel_can_open_library_then_return_to_initial_panel(self):
        libraries = []
        self.h.builtins['EL:DLUIOPEN'] = lambda: libraries.append(True) or True
        self.actions = [lambda: self.done(11), lambda: self.done(0)]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(libraries, [True])
        self.assertEqual(self.dialogs, ['el_panel', 'el_panel'])
        self.assertEqual(self.writes, [])

    def test_existing_valid_store_with_zero_records_keeps_empty_panel(self):
        payload = self.h.run('(EL:StoreEncode (EL:StoreInitial))')
        entry = [Pair(0, 'XRECORD'), Pair(-1, 'store'), Pair(5, 'store')] + payload
        self.entities['store'] = entry
        self.h.builtins['DICTSEARCH'] = lambda *args: entry
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.items, [])
        self.assertEqual(self.tiles['h_records'], '')
        self.assertEqual(self.tiles['h_detail'], '本图暂无保存记录')
        self.assertEqual(self.writes, [])

    def test_empty_selection_does_not_open_first_existing_record(self):
        records = self.h.run("'(((source-panel-handle . \"present\") (engine . fixed)))")
        self.h.set(Symbol('*EL:HISTORYRECORDS*'), records)
        self.h.builtins['HANDENT'] = lambda handle: handle
        for value in ('', None, '-1', '9'):
            with self.subTest(value=value):
                self.call('EL:HistoryClick', value)
                self.assertIsNone(self.closed)
                self.assertIsNone(self.h.lookup('*EL:HISTORYINDEX*'))
                self.assertEqual(self.modes['h_open'], 1)

    def test_pick_buttons_return_after_initial_dialog_is_unloaded(self):
        for status, function in ((9, 'EL:FIXEDSTATPICK'), (10, 'EL:FIXEDTRUNKPICK')):
            with self.subTest(status=status):
                picked = []
                def pick():
                    self.assertIsNone(self.h.lookup('*EL:DIALOGID*'))
                    picked.append(True)
                self.h.builtins[function] = pick
                self.actions = [lambda: self.done(status)]
                self.h.run('(c:ELSTAT)')
                self.assertEqual(picked, [True])
                self.assertEqual(self.writes, [])

    def test_cancel_logs_initialization_and_status_with_no_error(self):
        self.h.run('(c:ELSTAT)')
        text = self.log_text()
        for stage in ('PANEL_START_LOAD', 'PANEL_START_NEW', 'PANEL_START_INIT',
                      'PANEL_START_BUTTONS', 'PANEL_HISTORY_READ', 'PANEL_HISTORY_EMPTY',
                      'PANEL_START_WAIT', 'PANEL_START_RETURN'):
            self.assertIn(stage, text)
        self.assertNotIn('ERROR', text)
        self.assertFalse(truth(self.h.lookup('*EL:LOGACTIVE*')))

    def test_initialization_error_reports_stage_and_releases_dialog(self):
        def fail():
            # Dispatch while the real command's local *error* is active.
            self.call('*ERROR*', 'button drawing failed')
            raise RuntimeError('button drawing failed')
        self.h.builtins['EL:TRUNKBUTTONDRAW'] = fail
        with self.assertRaisesRegex(RuntimeError, 'button drawing failed'):
            self.h.run('(c:ELSTAT)')
        text = self.log_text()
        for evidence in ('PANEL_START_INIT', 'PANEL_START_BUTTONS', 'button drawing failed', 'ERROR'):
            self.assertIn(evidence, text)
        self.assertEqual(self.unloaded, [1])
        self.assertIsNone(self.h.lookup('*EL:DIALOGID*'))
        self.assertFalse(truth(self.h.lookup('*EL:PERFACTIVE*')))
        self.assertFalse(truth(self.h.lookup('*EL:LOGACTIVE*')))
        self.assertEqual(self.writes, [])

    def test_dialog_load_or_creation_failure_gives_feedback(self):
        alerts = []
        self.h.builtins['ALERT'] = alerts.append
        self.h.builtins['LOAD_DIALOG'] = lambda path: -1
        self.h.run('(c:ELSTAT)')
        self.assertIn('无法加载', alerts[-1])
        self.assertEqual(self.dialogs, [])
        self.assertEqual(self.unloaded, [])
        self.h.builtins['LOAD_DIALOG'] = lambda path: 1
        self.h.builtins['NEW_DIALOG'] = lambda *args: None
        self.h.run('(c:ELSTAT)')
        self.assertIn('无法创建', alerts[-1])
        self.assertEqual(self.unloaded, [1])
        self.assertEqual(self.writes, [])


if __name__ == '__main__':
    unittest.main()
