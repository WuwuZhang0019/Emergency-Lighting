"""Explicit diagnostic export is read-only. Date: 2026-10-15.

These finite DWG checks are not native AutoCAD acceptance.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
import test_diagram_update as updates
import test_cckk_panel_command as panel_flow
from test_diagram_store import dump


class DiagnosticExportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = updates.UpdateTests()
        self.fixture.setUp()
        self.fixture.install_sync()
        self.h = self.fixture.h
        getvar = self.h.builtins['GETVAR']
        self.exports, self.events, self.messages, self.reports = [], [], [], []
        self.h.builtins.update({
            'GETVAR': lambda name: 1 if name == 'TILEMODE' else 2 if name == 'CVPORT' else getvar(name),
            'GETPOINT': lambda *args: [100., 200., 0.],
            'TRANS': lambda point, *args: point,
            'EL:ENSUREROOT': lambda: True,
            'EL:PICKENTITY': lambda prompt: ['panel', [0., 0., 0.]],
            'EL:WRITEDATA': lambda path, data: self.exports.append((path, data)) or True,
            'EL:LOGEVENT': lambda name, context: self.events.append((name, context)),
            'EL:PERFREPORT': lambda data: self.reports.append(data),
            'EL:CLEARPICKHIGHLIGHTS': lambda: None,
            'PRINC': lambda value='': self.messages.append(value) or value,
        })
        self.h.frames[0]['*EL:ROOT*'] = 'root/'
        self.h.frames[0]['*EL:RESULT*'] = self.h.lookup('RESULT')
        self.h.frames[0]['*EL:PERFLOGSOFF*'] = True

    def get(self, key, data):
        return self.fixture.get(key, data)

    def before(self):
        return copy.deepcopy((self.fixture.entities, self.fixture.dictionary, self.fixture.dynamic,
                              self.h.lookup('*EL:RESULT*')))

    def assert_business_unchanged(self, before):
        self.assertEqual((self.fixture.entities, self.fixture.dictionary, self.fixture.dynamic,
                          self.h.lookup('*EL:RESULT*')), before)
        self.assertEqual(self.fixture.undo, [])

    def test_normal_successful_update_and_noop_do_not_write_diagnostic_file(self):
        self.assertTrue(truth(self.h.run("(EL:SyncDiagram result nil nil 'cap600 T nil)")))
        self.assertTrue(truth(self.h.run("(EL:SyncDiagram result nil nil 'cap600 T nil)")))
        self.assertEqual(self.exports, [])

    def test_first_native_generation_does_not_automatically_export(self):
        native = panel_flow.PanelCommandTests()
        native.setUp()
        exports = []
        native.h.builtins['EL:WRITEDATA'] = lambda *args: exports.append(args) or True
        self.assertTrue(truth(native.invoke()))
        self.assertEqual(exports, [])

    def test_current_result_exports_complete_expanded_record_once(self):
        before = self.before()
        self.h.builtins['EL:PICKENTITY'] = lambda prompt: self.fail('current panel must take priority')
        self.assertTrue(truth(self.h.run('(EL:DiagnosticExport)')))
        record = self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        expected = 'root/output/diagram-' + self.fixture.call('EL:Hash', 'd1') + '.eld'
        self.assertEqual(self.exports, [(expected, record)])
        self.assertIn(expected, ''.join(self.messages))
        self.assert_business_unchanged(before)

    def test_selected_owned_caption_exports_its_record_without_result(self):
        self.h.frames[0]['*EL:RESULT*'] = None
        self.h.builtins['EL:PICKENTITY'] = lambda prompt: ['caption-label/u1', [0., 0., 0.]]
        before = self.before()
        self.assertTrue(truth(self.h.run('(EL:DiagnosticExport)')))
        self.assertEqual(self.get('diagram-id', self.exports[0][1]), 'd1')
        self.assert_business_unchanged(before)

    def test_failed_export_does_not_change_business_or_mark_source_stale(self):
        before = self.before()
        self.h.builtins['EL:WRITEDATA'] = lambda *args: None
        self.h.builtins['EL:MARKSTALE'] = lambda *args: self.fail('diagnostic failure must not mark source stale')
        self.assertFalse(truth(self.h.run('(EL:DiagnosticExport)')))
        self.assertTrue(any(name == 'DIAGNOSTIC_EXPORT_FAILED' for name, _ in self.events))
        self.assert_business_unchanged(before)

    def test_command_catches_export_exception_and_preserves_error_context(self):
        before = self.before()
        def failed(*args):
            raise RuntimeError('diagnostic file access denied')
        self.h.builtins['EL:WRITEDATA'] = failed
        self.h.builtins['EL:MARKSTALE'] = lambda *args: self.fail('diagnostic failure must not mark source stale')
        self.h.run('(c:ELDIAG)')
        self.assertTrue(any(name == 'ERROR' and self.get('message', context) == 'diagnostic file access denied'
                            for name, context in self.events))
        self.assertFalse(truth(self.h.lookup('*EL:PERFACTIVE*')))
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))
        self.assert_business_unchanged(before)

    def test_selected_copy_or_foreign_object_is_rejected_before_export(self):
        self.h.frames[0]['*EL:RESULT*'] = None
        copied = copy.deepcopy(self.fixture.entities['b0'])
        self.fixture.entities['copied'] = [Pair(p.car, 'copied') if isinstance(p, Pair) and p.car in (-1, 5)
                                          else p for p in copied]
        self.h.builtins['EL:PICKENTITY'] = lambda prompt: ['copied', [0., 0., 0.]]
        before = self.before()
        self.h.run('(c:ELDIAG)')
        self.assertEqual(self.exports, [])
        self.assertTrue(any(name == 'ERROR' for name, _ in self.events))
        self.assert_business_unchanged(before)

    def test_incomplete_or_foreign_member_is_rejected_even_with_current_result(self):
        del self.fixture.entities['t0']
        before = self.before()
        self.h.run('(c:ELDIAG)')
        self.assertEqual(self.exports, [])
        self.assertTrue(any(name == 'ERROR' for name, _ in self.events))
        self.assert_business_unchanged(before)

    def test_command_records_export_stage_and_zero_business_writes(self):
        before = self.before()
        self.h.run('(c:ELDIAG)')
        self.assertEqual(len(self.exports), 1)
        self.assertEqual(len(self.reports), 1)
        summary = self.reports[0]
        self.assertEqual(self.get('command', summary), 'ELDIAG')
        metrics = self.get('metrics', summary)
        self.assertEqual(self.fixture.call('EL:Get', 'master-write-attempts', metrics), 0)
        self.assertEqual(self.fixture.call('EL:Get', 'entity-write-attempts', metrics), 0)
        stages = self.get('stages', summary)
        self.assertEqual(self.get('calls', self.fixture.call('EL:Get', 'DIAGNOSTIC_EXPORT', stages)), 1)
        self.assert_business_unchanged(before)

    def test_locked_layers_do_not_prevent_read_only_diagnostic_export(self):
        self.h.builtins['TBLSEARCH'] = lambda table, name: [Pair(70, 4)]
        before = self.before()
        self.assertTrue(truth(self.h.run('(EL:DiagnosticExport)')))
        self.assert_business_unchanged(before)

    def test_legacy_diagnostic_read_never_migrates_the_dwg_master(self):
        store = self.h.run('(EL:StoreRead)')
        entity = self.fixture.dictionary['EL_FIXED_V1']
        self.fixture.entities[entity] = [Pair(-1, entity), Pair(5, entity), Pair(0, 'XRECORD'),
                                         Pair(100, 'AcDbXrecord'), Pair(1, dump(store))]
        before = self.before()
        self.assertTrue(truth(self.h.run('(EL:DiagnosticExport)')))
        self.assertEqual(self.exports[0][1], self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))'))
        self.assert_business_unchanged(before)


if __name__ == '__main__':
    unittest.main()
