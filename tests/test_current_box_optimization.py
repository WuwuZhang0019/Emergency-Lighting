"""Current-box IO and compatibility. Date: 2026-10-13. Status: automated adapters only."""
import copy
import random
import unittest
from pathlib import Path

from autolisp_host import Host, Pair, Symbol, equal, truth
import test_store_split as split
import test_store_compact as compact
import test_monitor as monitor
import test_cckk_panel_command as panel

ROOT = Path(__file__).resolve().parents[1]


class CurrentBoxTests(unittest.TestCase):
    def setUp(self):
        self.f = split.SplitStoreTests()
        self.f.setUp()
        self.h = self.f.h
        self.call = self.f.call
        self.get = self.f.get
        other = self.call('EL:Put', Symbol('SOURCE-SIGNATURE'),
                          [Symbol('EL_FIXED_SOURCE_V1'), [float(i) + .125 for i in range(120)]],
                          self.h.lookup('RECORD2'))
        self.store = self.call('EL:Put', Symbol('DIAGRAMS'), [self.h.lookup('RECORD1'), other],
                               self.h.lookup('STORE'))
        self.assertTrue(truth(self.get('committed', self.f.save(self.store))))
        self.root = self.call('EL:SplitRoot')
        self.items = self.get('items', self.root)
        detail = self.call('EL:SplitReadChunk', self.get('detail', self.items[1]), Symbol('DETAIL'))
        self.other_blob = self.get('source-signature', self.get('blobs', detail))
        self.h.frames[0]['*EL:SPLITCACHE*'] = None

    def view(self):
        return self.call('EL:StoreForResult', [Pair(Symbol('PANEL'), 'P1')])

    def test_read_hydrates_only_current_box_and_write_retains_other_blobs(self):
        reads = []
        native = self.h.builtins['DICTSEARCH']
        self.h.builtins['DICTSEARCH'] = lambda owner, key: (reads.append(key), native(owner, key))[1]
        view = self.view()
        self.assertNotIn(self.get('detail', self.items[1]), reads)
        self.assertNotIn(self.other_blob, reads)
        self.assertEqual(self.get('diagrams', view)[0], self.get('diagrams', self.store)[0])
        decodes = []
        self.h.functions['TEST:DECODE'] = self.h.functions['EL:STOREDECODE']
        self.h.builtins['EL:STOREDECODE'] = lambda payload: (
            decodes.append(copy.deepcopy(payload)), self.call('TEST:Decode', payload))[1]
        other_payload = self.call('EL:StorePayload', self.f.entities[self.f.dictionary[self.other_blob]])
        records = self.get('diagrams', view)
        changed = self.call('EL:Put', Symbol('PANEL-NUMBER'), '仅改当前箱', records[0])
        proposed = self.call('EL:Put', Symbol('DIAGRAMS'), [changed, records[1]], view)
        context = self.f.save(proposed)
        self.assertTrue(truth(self.get('committed', context)))
        self.assertNotIn(other_payload, decodes)
        latest = self.call('EL:SplitRoot')
        self.assertEqual(self.get('items', latest)[1], self.items[1])
        self.assertEqual(self.call('EL:TransactionVerifiedRead', context), proposed)
        expected = self.call('EL:Put', Symbol('DIAGRAMS'),
                             [changed, self.get('diagrams', self.store)[1]], self.store)
        self.assertTrue(equal(self.call('EL:StoreRead'), expected))
        self.assertIsNone(self.get('split-view', self.call('EL:StoreRead')))

    def test_changed_root_rejects_stale_view_without_overwriting_latest_record(self):
        old_view = self.view()
        latest = self.call('EL:Put', Symbol('EXTRA'), '较新的保存', self.store)
        self.assertTrue(truth(self.get('committed', self.f.save(latest))))
        before = copy.deepcopy((self.f.entities, self.f.dictionary))
        rejected = self.f.save(old_view)
        self.assertFalse(truth(self.get('committed', rejected)))
        self.assertEqual((self.f.entities, self.f.dictionary), before)
        self.assertEqual(self.call('EL:StoreRead'), latest)

    def test_forged_lazy_record_and_changed_owner_are_rejected(self):
        view = self.view()
        records = self.get('diagrams', view)
        tampered = self.call('EL:Put', Symbol('PANEL-NUMBER'), '不得覆盖另一箱', records[1])
        proposed = self.call('EL:Put', Symbol('DIAGRAMS'), [records[0], tampered], view)
        before = copy.deepcopy((self.f.entities, self.f.dictionary))
        self.assertFalse(truth(self.get('committed', self.f.save(proposed))))
        wrong_owner = self.call('EL:Put', Symbol('DRAWING-UUID'), '另一个图纸', view)
        self.assertFalse(truth(self.get('committed', self.f.save(wrong_owner))))
        self.assertEqual((self.f.entities, self.f.dictionary), before)

    def test_preverified_new_chunks_are_not_decoded_again_during_stage_validation(self):
        self.h.frames[0]['*EL:SPLITCACHE*'] = None
        view = self.view()
        records = self.get('diagrams', view)
        changed = self.call('EL:Put', Symbol('SOURCE-SIGNATURE'),
                            [Symbol('EL_FIXED_SOURCE_V1'), [float(i) + .25 for i in range(140)]], records[0])
        proposed = self.call('EL:Put', Symbol('DIAGRAMS'), [changed, records[1]], view)
        decodes = []
        self.h.functions['TEST:DECODE'] = self.h.functions['EL:STOREDECODE']
        self.h.builtins['EL:STOREDECODE'] = lambda payload: (
            decodes.append(copy.deepcopy(payload)), self.call('TEST:Decode', payload))[1]
        self.assertTrue(truth(self.get('committed', self.f.save(proposed))))
        item = self.get('items', self.call('EL:SplitRoot'))[0]
        detail = self.call('EL:SplitReadChunk', self.get('detail', item), Symbol('DETAIL'))
        key = self.get('source-signature', self.get('blobs', detail))
        payload = self.call('EL:StorePayload', self.f.entities[self.f.dictionary[key]])
        self.assertEqual(decodes.count(payload), 1)

    def test_unchanged_partial_save_keeps_root_and_chunks_unchanged(self):
        view = self.view()
        before = copy.deepcopy((self.f.entities, self.f.dictionary))
        context = self.f.save(view)
        self.assertTrue(truth(self.get('committed', context)))
        self.assertEqual((self.f.entities, self.f.dictionary), before)

    def test_post_commit_audits_retained_other_box_payload(self):
        view = self.view()
        records = self.get('diagrams', view)
        changed = self.call('EL:Put', Symbol('PANEL-NUMBER'), '提交检查', records[0])
        proposed = self.call('EL:Put', Symbol('DIAGRAMS'), [changed, records[1]], view)
        entity = self.f.dictionary[self.other_blob]
        self.h.builtins['VLA-ENDUNDOMARK'] = lambda _: self.f.entities[entity].append(Pair(40, 99.0))
        context = self.f.save(proposed)
        self.assertTrue(truth(self.get('outcome', context)))
        self.assertFalse(truth(self.get('committed', context)))

    def test_corruption_before_save_cannot_hide_in_an_unchanged_other_box_reference(self):
        view = self.view()
        entity = self.f.dictionary[self.other_blob]
        self.f.entities[entity].append(Pair(40, 99.0))
        before = copy.deepcopy((self.f.entities, self.f.dictionary))
        context = self.f.save(view)
        self.assertFalse(truth(self.get('outcome', context)))
        self.assertEqual((self.f.entities, self.f.dictionary), before)

    def test_unknown_other_payload_is_decoded_once_then_reused_after_full_raw_audit(self):
        view = self.view()
        self.h.frames[0]['*EL:SPLITVERIFIEDPAYLOADS*'] = None
        self.h.frames[0]['*EL:SPLITCACHE*'] = None
        decodes = []
        self.h.functions['TEST:DECODE'] = self.h.functions['EL:STOREDECODE']
        self.h.builtins['EL:STOREDECODE'] = lambda payload: (
            decodes.append(copy.deepcopy(payload)), self.call('TEST:Decode', payload))[1]
        payload = self.call('EL:StorePayload', self.f.entities[self.f.dictionary[self.other_blob]])
        self.assertTrue(truth(self.get('committed', self.f.save(view))))
        self.assertEqual(decodes.count(payload), 1)
        for _ in range(2):
            self.h.frames[0]['*EL:SPLITCACHE*'] = None
            self.assertTrue(truth(self.get('committed', self.f.save(self.view()))))
            self.assertEqual(decodes.count(payload), 1)


class TapeAndEntryTests(unittest.TestCase):
    def test_compact_format_reduces_legacy_fields_and_preserves_exact_values(self):
        f = compact.StoreCompactTests()
        f.setUp()
        store = f.put('numeric-snapshot', [float(i) + .125 for i in range(300)] +
                      [1.0000000000000002, -1e-280, 2147483647, Pair(Symbol('UNKNOWN'), '中文扩展')],
                      f.fixture())
        old = f.call('EL:StoreEncodeLegacy', store)
        current = f.call('EL:StoreEncode', store)
        self.assertEqual(current[0], Pair(300, 'EL_COMPACT_TYPED_V3'))
        self.assertTrue(equal(f.call('EL:StoreDecode', old), store))
        self.assertTrue(equal(f.call('EL:StoreDecode', current), store))
        self.assertLess(len(current), len(old))
        self.__class__.field_counts = {'legacy_v1': len(old), 'compact_v3': len(current)}
        for invalid in (current[:-1], current + [Pair(40, 9.0)]):
            with self.subTest(invalid=invalid[-1]):
                with self.assertRaises(RuntimeError): f.call('EL:StoreDecode', invalid)

    def test_reload_closes_old_command_before_resetting_monitor_clock(self):
        f = monitor.MonitorTests()
        f.setUp()
        reports = []
        f.h.builtins['EL:MONITORREPORT'] = lambda summary: reports.append(
            (copy.deepcopy(summary), copy.deepcopy(f.h.lookup('*EL:MONITORROWS*'))))
        f.call('EL:PerfStart', 'ELSTAT')
        f.clock = 100
        f.call('EL:PerfBegin', 'STORE_DECODE')
        f.clock = 5000
        f.call('EL:MonitorLoadBegin', 4990)
        self.assertEqual(f.get('command', reports[0][0]), 'ELSTAT')
        self.assertEqual(f.get('total-ms', reports[0][0]), 5000)
        f.clock = 5020
        f.call('EL:MonitorLoadEnd', Symbol('LOAD-FINISHED'))
        self.assertEqual(f.get('command', reports[1][0]), 'APPLOAD')
        self.assertEqual(f.get('total-ms', reports[1][0]), 30)
        self.assertTrue(all(f.get('parent-id', row) == 0 for row in reports[1][1]))
        self.assertTrue(all(f.get('elapsed-ms', row) <= 30 for row in reports[1][1]))

    def test_native_repeated_generation_uses_latest_split_current_box_view(self):
        f = panel.PanelCommandTests()
        f.setUp()
        f.two_circuits()
        f.h.load_definitions(ROOT / 'src/store-split.lsp')
        f.h.run('(setq *EL:SplitStorageLoaded* T)')
        self.assertTrue(truth(f.invoke()))
        f.assert_two_circuit_output()
        count = len(f.commands)
        old=f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertTrue(truth(f.invoke()))
        self.assertEqual(len(f.commands), count*2)
        f.assert_two_circuit_output()
        current=f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertNotEqual(f.get('diagram-id',old),f.get('diagram-id',current))
        self.assertEqual(f.call('EL:StoreRecord',f.get('diagram-id',old)),old)
        view=f.h.run('(EL:StoreForResult (list (cons \'panel "source")))')
        records=f.get('diagrams',view)
        self.assertEqual(len(records),2)
        self.assertTrue(f.get('split-reference',records[0]))
        self.assertFalse(f.get('split-reference',records[1]))


class ComponentIndexTests(unittest.TestCase):
    def test_index_keeps_exact_legacy_visit_order_with_duplicates_cycles_and_isolates(self):
        h = Host()
        h.load_definitions(ROOT / 'src/common.lsp')
        h.load_definitions(ROOT / 'src/topology.lsp')
        def legacy(start, edges):
            queue, visited = [start], []
            while queue:
                node = queue.pop(0)
                if node not in visited:
                    visited.insert(0, node)
                    neighbours = []
                    for a, b in edges:
                        if node == a: neighbours.insert(0, b)
                        elif node == b: neighbours.insert(0, a)
                    for other in dict.fromkeys(neighbours):
                        if other not in visited: queue.insert(0, other)
            return visited
        randomizer = random.Random(127)
        nodes = [f'{i:04X}' for i in range(90)] + ['中文节点']
        edges = [[nodes[i], nodes[i + 1]] for i in range(70)]
        edges += [randomizer.sample(nodes, 2) for _ in range(140)]
        edges += edges[:12] + [['0001', '0001']]
        for start in (nodes[0], nodes[65], '中文节点', 'isolated'):
            with self.subTest(start=start):
                self.assertEqual(h.call(Symbol('EL:COMPONENT'), [start, edges]), legacy(start, edges))
        h.builtins['GETVAR'] = lambda _: 0
        h.call(Symbol('EL:PERFSTART'), ['ELSTAT'])
        h.call(Symbol('EL:COMPONENT'), [nodes[0], edges])
        metrics = h.lookup('*EL:PERFMETRICS*')
        self.assertEqual(h.call(Symbol('EL:GET'), ['component-edge-scans', metrics]), len(edges))
        self.assertEqual(h.call(Symbol('EL:GET'), ['component-index-builds', metrics]), 1)


if __name__ == '__main__':
    unittest.main()
