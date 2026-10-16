"""Date: 2026-10-15. Input-only placement and explicit diagnostic export.

Finite CAD/DCL adapters, not native AutoCAD timing evidence.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
from check_store_read_work import exact
import test_cckk_panel_command as native
import test_post_stat_workflow as panel
import test_monitor as monitor


class PlacementFinishTests(unittest.TestCase):
    def setUp(self):
        self.f = native.PanelCommandTests()
        self.f.setUp()
        self.f.two_circuits()
        self.h = self.f.h
        self.h.run("(setq result (EL:Put 'engine 'fixed result))")
        self.events, self.exports = [], []
        self.complete = False
        self.saved = None
        self.h.builtins.update({
            'EL:PANELDIALOG': lambda *args: [
                Pair(Symbol('RESULT'), self.h.frames[0]['RESULT']),
                Pair(Symbol('CONFIG'), self.h.frames[0]['CFG']),
                Pair(Symbol('GENERATE'), True), Pair(Symbol('CAPACITY'), Symbol('CAP300'))],
            'EL:FIXEDPOWERS': lambda *args: None,
            'EL:DLSNAPSHOT': lambda: self.f.call('EL:Put', Symbol('ROOT'), 'library-fixture/',
                self.f.call('EL:Put', Symbol('CATALOG'), self.f.call('EL:DLCatalogInitial', 'LIB-CCKK'), None)),
            'EL:REMEMBERPANELPOWERS': lambda *args: True,
            'EL:SAVENAMEPOWERS': lambda *args: True,
            'EL:TEMPLATEREADY': lambda *args: True,
            'EL:CURRENTJUNCTIONCONFIG': lambda cfg: cfg,
            'EL:CLEARPICKHIGHLIGHTS': lambda: None,
            'EL:FRESHRESULT': self.fresh,
            'EL:STOREWRITE': self.save,
            'EL:ENSUREROOT': lambda: True,
            'EL:PERFREPORT': lambda *args: self.fail('automatic performance file'),
            'EL:MONITORREPORT': lambda *args: self.fail('automatic timeline file'),
            'EL:WRITEDATA': lambda *args: self.exports.append(args) or True,
            'VLA-REGEN': lambda *args: self.fail('whole-drawing regeneration'),
            'EL:SIMPLEZOOM': lambda *args: self.fail('automatic zoom'),
        })
        self.h.frames[0]['*EL:ROOT*'] = 'root/'
        self.h.frames[0]['*EL:LOGACTIVE*'] = True
        self.h.frames[0]['*EL:LOGSEQUENCE*'] = 0
        self.command = self.h.builtins['COMMAND']
        self.h.builtins['COMMAND'] = self.insert
        self.h.builtins['EL:PERFMARK'] = self.mark

    def actual(self, name, *args):
        override = self.h.builtins.pop(name, None)
        try:
            return self.f.call(name, *args)
        finally:
            if override is not None:
                self.h.builtins[name] = override

    def insert(self, *args):
        self.assertFalse(self.complete)
        self.events.append(('insert', len(self.f.commands)))
        return self.command(*args)

    def fresh(self, *args):
        self.assertFalse(self.complete, 'source scan after final text')
        self.events.append(('source', len(self.f.commands)))
        return True

    def save(self, store):
        self.assertFalse(self.complete, 'store write after final text')
        self.assertEqual(self.f.commands, [], 'input must be saved before mouse placement')
        self.events.append(('save', 0))
        self.saved = copy.deepcopy(store)
        return self.actual('EL:STOREWRITE', store)

    def mark(self, key):
        if key == 'graphics-complete':
            self.complete = True
        return self.actual('EL:PERFMARK', key)

    def generate(self):
        self.complete = False
        self.f.call('EL:PerfStart', 'ELSTAT')
        self.h.frames[0]['*EL:DIAGNOSTICSDEFERRED*'] = True
        self.h.run('(EL:EditPanel result cfg)')
        self.f.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))

    def output(self):
        return self.h.run("(EL:Get 'record (EL:Get (namedobjdict) *EL:DiagramDiagnostics*))")

    def test_six_actual_two_reserve_finish_without_store_scan_zoom_or_export_tail(self):
        first = self.f.get('circuits', self.h.lookup('RESULT'))[0]
        circuits = []
        for i in range(6):
            row = first
            for key, value in [('id', f'R{i+1}'), ('circuit-uid', f'U{i+1}'), ('watts', 10+i),
                               ('output-order', i+1),
                               ('seed-key', [f'W{i+1}', Symbol('OUTLET')]),
                               ('seed', [[Symbol('KEY'), f'W{i+1}', Symbol('OUTLET')]]),
                               ('circuit-number', f'ZE{i+1}'), ('number-status', Symbol('READY'))]:
                row = self.f.call('EL:Put', Symbol(key.upper()), value, row)
            circuits.append(row)
        self.h.frames[0]['RESULT'] = self.f.call('EL:Put', Symbol('CIRCUITS'), circuits, self.h.lookup('RESULT'))
        self.generate()
        self.assertTrue(self.complete)
        self.assertEqual([e for e in self.events if e[0] == 'save'], [('save', 0)])
        self.assertEqual([e for e in self.events if e[0] == 'source'], [('source', 1)])
        self.assertEqual(len(self.f.commands), 9)
        rows = self.f.get('rows', self.output())
        self.assertEqual([self.f.get('watts', row) for row in rows[:6]], list(range(10, 16)))
        self.assertEqual([self.f.get('mode', row) for row in rows[6:]], [Symbol('RESERVE')] * 2)
        self.assertTrue(all(self.f.get('text-handle', row) is None for row in rows[6:]))
        self.assertEqual(exact(self.h.run('(EL:StoreRead)')), exact(self.saved))
        reopened = self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertFalse(self.f.get('panel-output-handle', reopened))
        self.assertEqual(len(self.f.get('draft-circuits', reopened)), 6)
        self.assertEqual(self.exports, [])
        self.assertNotIn('EL_FIXED_TX', self.f.dictionary)
        self.assertEqual(self.f.variables, self.f.original)
        summary = self.h.lookup('*EL:PERFLASTSUMMARY*')
        self.assertIsNotNone(self.f.get('after-graphics', summary))
        self.assertTrue(self.h.run('(EL:Get (namedobjdict) *EL:DiagnosticRuns*)'))

    def test_cancel_mid_creation_retains_inputs_and_retry_preserves_previous_entities(self):
        self.f.fail_at = 3
        self.generate()
        self.assertIsNone(self.output())
        self.assertFalse(any(e.startswith('native-') for e in self.f.entities))
        self.assertEqual(exact(self.h.run('(EL:StoreRead)')), exact(self.saved))
        self.f.fail_at = None
        self.f.commands.clear()
        self.generate()
        first = copy.deepcopy(self.output())
        first_entities = {r[0]: copy.deepcopy(self.f.entities[r[0]])
                          for r in self.f.call('EL:DiagramOutputRefs', first)}
        self.f.commands.clear()
        # The finite command adapter needs unique handles across repeated invocations.
        self.command = lambda *args: self.native_again(*args)
        self.generate()
        self.assertNotEqual(self.f.get('diagram-id', first), self.f.get('diagram-id', self.output()))
        for handle, data in first_entities.items():
            self.assertEqual(self.f.entities[handle], data)

    def native_again(self, *args):
        self.f.commands.append(args)
        self.f.last = 'native-repeat-' + str(len(self.f.commands))
        point = self.f.placement if hasattr(self.f, 'placement') else [100., 200., 0.]
        self.f.entity(self.f.last, 'INSERT', point if args[-1] == 'pause' else args[-1])
        self.f.entities[self.f.last].append(Pair(2, args[1]))

    def test_changed_source_at_click_rolls_back_before_circuit_insertion(self):
        self.h.builtins['EL:FRESHRESULT'] = lambda *args: self.fresh(*args) and False
        self.generate()
        self.assertEqual(len(self.f.commands), 1)
        self.assertFalse(any(e.startswith('native-') for e in self.f.entities))
        self.assertEqual(exact(self.h.run('(EL:StoreRead)')), exact(self.saved))
        self.assertIsNone(self.output())

    def test_explicit_export_reads_session_associations_without_dwg_write(self):
        self.generate()
        before = copy.deepcopy((self.f.entities, self.f.dictionary))
        self.h.builtins['EL:EXPORTDIAGNOSTICRUN'] = lambda: 'root/output/ELMONITOR-run.md'
        self.h.builtins['EL:DIAGNOSTICBUNDLE'] = lambda record, *args: self.exports.append(('bundle.zip', record)) or 'bundle.zip'
        self.assertTrue(truth(self.f.call('EL:DiagnosticExport')))
        self.assertEqual(len(self.exports), 1)
        self.assertEqual(exact(self.exports[0][1]), exact(self.output()))
        self.assertEqual((self.f.entities, self.f.dictionary), before)
        self.assertIn('已导出', self.h.lookup('*EL:DIAGNOSTICEXPORTMESSAGE*'))

    def test_export_rejects_erased_or_retagged_output_and_never_uses_other_drawing_cache(self):
        self.generate()
        self.h.builtins['EL:EXPORTDIAGNOSTICRUN'] = lambda: None
        bundles = []
        self.h.builtins['EL:DIAGNOSTICBUNDLE'] = lambda *args: bundles.append(args) or 'bundle.zip'
        handle = self.f.get('block-handle', self.f.get('rows', self.output())[0])
        del self.f.entities[handle]
        self.f.call('EL:DiagnosticExport')
        self.assertEqual(self.exports, [])
        self.assertIsNone(bundles[-1][0])
        self.assertIn('系统图成员缺失', bundles[-1][3])
        self.h.builtins['NAMEDOBJDICT'] = lambda: 'OTHER-DWG'
        self.h.builtins['EL:STOREREAD'] = lambda: None
        self.assertTrue(truth(self.f.call('EL:DiagnosticExport')))
        self.assertEqual(self.exports, [])
        self.assertEqual(bundles[-1], (None, None, None, None))


class DiagnosticButtonTests(unittest.TestCase):
    def test_button_returns_to_panel_with_capacity_and_library_edits_preserved(self):
        f = panel.PostStatWorkflowTests()
        f.setUp()
        panel.install_library_files(f, self)
        callbacks, exports, opens = {}, [], []
        path = 'C:\\中文 目录\\ELDIAG-20261015.123456.zip'
        f.h.builtins['ACTION_TILE'] = lambda key, action: callbacks.__setitem__(key, action)
        def export():
            exports.append(True)
            f.h.set('*EL:DIAGNOSTICEXPORTPATH*', path)
            f.h.set('*EL:DIAGNOSTICEXPORTSUCCEEDED*', True)
            return '诊断已导出'
        f.h.builtins['EL:PANELDIAGNOSTICEXPORT'] = export
        f.h.builtins['EL:DIAGNOSTICOPENFOLDER'] = lambda value: opens.append(value) or '已打开诊断文件所在位置。'
        f.actions = [lambda: (f.tiles.__setitem__('dl_display', '保留输入'),
                              f.call('EL:PanelCapacity', 'p_600'),
                              f.invoke_action(callbacks, 'p_diagnostic')),
                     lambda: f.invoke_action(callbacks, 'cancel')]
        f.dialog()
        self.assertEqual(exports, [True])
        self.assertEqual(f.dialogs, ['el_panel', 'el_panel'])
        self.assertEqual(opens, [path])
        self.assertNotIn('p_diagnostic_path', f.tiles)
        self.assertEqual(f.tiles['p_capacity'], 'p_600')
        self.assertEqual(f.get('display', f.call('EL:DLUIEntry')), '保留输入')
        self.assertNotIn('p_diagnostic_status', f.tiles)
        self.assertNotIn('cancel', callbacks)

    def test_failed_export_does_not_open_partial_folder_and_retry_preserves_export_result(self):
        f = panel.PostStatWorkflowTests()
        f.setUp()
        callbacks, exports, opens, alerts = {}, [], [], []
        folder = 'C:\\中文 目录\\ELDIAG-20261015.123456'
        path = folder + '-1.zip'
        f.h.builtins['ACTION_TILE'] = lambda key, action: callbacks.__setitem__(key, action)
        f.h.builtins['ALERT'] = alerts.append
        def export():
            exports.append(True)
            self.assertIsNone(f.h.lookup('*EL:DIAGNOSTICEXPORTPATH*'))
            self.assertIsNone(f.h.lookup('*EL:DIAGNOSTICEXPORTSUCCEEDED*'))
            f.h.set('*EL:DIAGNOSTICEXPORTPATH*', folder if len(exports) == 1 else path)
            f.h.set('*EL:DIAGNOSTICEXPORTSUCCEEDED*', None if len(exports) == 1 else True)
            notice = '诊断导出失败：模拟收集错误' if len(exports) == 1 else '诊断已导出'
            f.h.set('*EL:DIAGNOSTICEXPORTMESSAGE*', notice)
            return notice
        f.h.builtins['EL:PANELDIAGNOSTICEXPORT'] = export
        f.h.builtins['EL:DIAGNOSTICOPENFOLDER'] = lambda value: opens.append(value) or '无法打开文件夹'
        def retry():
            self.assertEqual(alerts, ['诊断导出失败：模拟收集错误'])
            self.assertEqual(opens, [])
            self.assertEqual(f.h.lookup('*EL:DIAGNOSTICEXPORTMESSAGE*'), alerts[0])
            f.invoke_action(callbacks, 'p_diagnostic')
        f.actions = [lambda: f.invoke_action(callbacks, 'p_diagnostic'),
                     retry,
                     lambda: f.invoke_action(callbacks, 'cancel')]
        f.dialog()
        self.assertEqual(len(exports), 2)
        self.assertEqual(opens, [path])
        self.assertEqual(f.h.lookup('*EL:DIAGNOSTICEXPORTMESSAGE*'), '诊断已导出')
        self.assertIn('无法打开文件夹', alerts[-1])
        self.assertIn(path, alerts[-1])

    def test_failed_export_without_new_path_never_opens_a_previous_result(self):
        f = panel.PostStatWorkflowTests()
        f.setUp()
        alerts, opens = [], []
        f.h.set('*EL:DIAGNOSTICEXPORTPATH*', 'C:/previous-export')
        f.h.set('*EL:DIAGNOSTICEXPORTSUCCEEDED*', True)
        f.h.builtins.update({
            'EL:PANELDIAGNOSTICEXPORT': lambda: '诊断导出失败：模拟启动错误',
            'EL:DIAGNOSTICOPENFOLDER': lambda path: opens.append(path),
            'ALERT': alerts.append,
        })
        f.call('EL:PanelDiagnosticExportOpen')
        self.assertEqual(opens, [])
        self.assertEqual(alerts, ['诊断导出失败：模拟启动错误'])
        self.assertIsNone(f.h.lookup('*EL:DIAGNOSTICEXPORTPATH*'))


class DeferredRunTests(unittest.TestCase):
    def test_export_uses_completed_timeline_and_keeps_new_panel_timer(self):
        f = monitor.MonitorTests()
        f.setUp()
        f.h.builtins['NAMEDOBJDICT'] = lambda: 'DWG-A'
        f.h.builtins['EL:MONITORREPORT'] = lambda *args: self.fail('automatic export')
        f.call('EL:PerfStart', 'ELSTAT')
        f.h.frames[0]['*EL:DIAGNOSTICSDEFERRED*'] = True
        f.h.frames[0]['*EL:LOGACTIVE*'] = True
        f.h.frames[0]['*EL:LOGSEQUENCE*'] = 0
        f.clock = 10
        f.call('EL:PerfMark', 'panel-submit')
        f.call('EL:LogEvent', 'EXAMPLE', '保留中文日志')
        f.clock = 50
        f.call('EL:PerfMark', 'graphics-complete')
        f.clock = 52
        f.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        saved = copy.deepcopy(f.h.run('(EL:Get (namedobjdict) *EL:DiagnosticRuns*)'))
        f.clock = 100
        f.call('EL:PerfStart', 'ELSTAT')
        f.h.frames[0]['*EL:DIAGNOSTICSDEFERRED*'] = True
        f.h.builtins['EL:REQUIRE'] = lambda condition, message: self.assertTrue(truth(condition), message)
        text = []
        def save(summary, fallback):
            f.h.frames[-1]['*EL:MONITORLINES*'] = None
            f.call('EL:MonitorWriteBody', None, summary)
            text.extend(reversed(f.h.lookup('*EL:MONITORLINES*')))
            return 'timeline.md'
        f.h.builtins['EL:MONITORSAVE'] = save
        self.assertEqual(f.call('EL:ExportDiagnosticRun'), 'timeline.md')
        self.assertTrue(truth(f.h.lookup('*EL:PERFACTIVE*')))
        self.assertEqual(f.h.lookup('*EL:PERFSTARTED*'), 100)
        self.assertIn('收尾：0.002 秒', ''.join(text))
        self.assertIn('保留中文日志', ''.join(text))
        f.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.assertEqual(f.h.run('(EL:Get (namedobjdict) *EL:DiagnosticRuns*)'), saved)


if __name__ == '__main__':
    unittest.main()
