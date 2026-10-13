"""Exact fresh-network equivalence and work counts. Date: 2026-10-13.

Finite CAD adapters, not native AutoCAD timing or acceptance.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
import test_simple_flow as simple
import test_freshness_reuse as fresh


class NetworkReuseTests(unittest.TestCase):
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    block = simple.SimpleFlowTests.block
    line = simple.SimpleFlowTests.line
    network = simple.SimpleFlowTests.network
    plan = simple.SimpleFlowTests.plan
    gap_plan = simple.SimpleFlowTests.gap_plan

    def setUp(self):
        simple.SimpleFlowTests.setUp(self)
        self.h.builtins['GETVAR'] = lambda key: 0
        self.h.builtins['EL:PERFREPORT'] = lambda summary: None
        self.call('EL:PerfStart', 'ELSTAT')
        self.plan()

    def metric(self, name):
        return self.call('EL:Get', name, self.h.lookup('*EL:PERFMETRICS*')) or 0

    def oracle(self):
        self.h.frames.append({'*EL:NETWORKREUSEDISABLED*': True})
        try:
            return self.network()
        finally:
            self.h.frames.pop()

    def test_five_scans_read_source_and_geometry_but_build_once(self):
        expected = self.oracle()
        self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        self.call('EL:PerfStart', 'ELSTAT')
        for _ in range(5):
            self.call('EL:FreshBoundary')
            self.assertEqual(self.network(), expected)
        self.assertEqual(self.metric('source-collect-calls'), 5)
        self.assertEqual(self.metric('network-build-calls'), 1)
        self.assertEqual(self.metric('network-verified-reuses'), 4)
        self.assertGreater(self.metric('network-geometry-checks'), 0)
        self.assertGreaterEqual(self.metric('device-contour-reads'), 5)
        type(self).work_evidence = {
            'source_collections': 5, 'original_network_builds': 5,
            'optimized_network_builds': 1, 'verified_reuses': 4,
            'fresh_geometry_checks': self.metric('network-geometry-checks'),
            'native_contour_reads': self.metric('device-contour-reads'),
            'equal_full_network_results': True,
        }

    def test_changed_definition_with_same_name_bounds_and_count_rebuilds(self):
        before = self.network()
        self.line('LAMP-edge-0', [-.5, -.5, 0.], [.5, -.5, 0.])
        self.call('EL:FreshBoundary')
        changed = self.network()
        self.assertEqual(self.metric('network-build-calls'), 2)
        self.assertNotEqual(before, changed)
        self.assertEqual(changed, self.oracle())

    def test_output_template_change_reuses_verified_network(self):
        expected = self.network()
        self.cfg = self.call('EL:Put', Symbol('TEMPLATE'), 'dialog-output-template', self.cfg)
        self.call('EL:FreshBoundary')
        actual = self.network()
        self.assertEqual(actual, expected)
        self.assertEqual(self.metric('network-build-calls'), 1)
        self.assertEqual(self.metric('network-verified-reuses'), 1)
        self.assertGreater(self.metric('network-geometry-checks'), 0)
        self.assertEqual(actual, self.oracle())

    def test_add_delete_move_wire_and_changed_rules_match_full_build(self):
        for change in ('add', 'delete', 'move-wire', 'rules', 'new-block', 'rotation'):
            with self.subTest(change=change):
                self.setUp()
                self.network()
                if change == 'add':
                    self.line('new', [5., 0., 0.], [9., 0., 0.], 'W')
                    self.selected.append('new')
                elif change == 'delete':
                    self.selected.remove('w1')
                elif change == 'move-wire':
                    self.line('w1', [1., 0., 0.], [8., 0., 0.], 'W')
                elif change == 'new-block':
                    self.block('UNREGISTERED', 'OTHER', 'new', [7., 0., 0.])
                    self.selected.append('new')
                elif change == 'rotation':
                    self.entities['a'].append(Pair(50, .5))
                else:
                    self.cfg = self.call('EL:Put', Symbol('PARAMS'),
                        self.call('EL:Put', Symbol('DMAX'), 5., self.get('params', self.cfg)), self.cfg)
                changed = self.network()
                self.assertEqual(self.metric('network-build-calls'), 2)
                self.assertEqual(changed, self.oracle())

    def test_gap_blocker_and_crossing_still_use_complete_candidate_set(self):
        self.gap_plan()
        self.network()
        self.line('cross', [15., -5., 0.], [15., 5., 0.], 'W')
        self.selected.append('cross')
        crossed = self.network()
        self.assertNotIn('cross', self.get('wire-ids', crossed))
        self.assertEqual(crossed, self.oracle())
        self.block('UNREGISTERED', 'OTHER', 'blocker', [15., 0., 0.])
        self.selected.append('blocker')
        blocked = self.network()
        self.assertFalse(self.get('devices', blocked))
        self.assertEqual(blocked, self.oracle())

    def test_end_error_reload_and_document_switch_do_not_reuse(self):
        self.network()
        self.call('EL:PerfFinish', Symbol('FAILED'))
        self.assertIsNone(self.h.lookup('*EL:NETWORKMEMO*'))
        self.call('EL:PerfStart', 'ELSTAT')
        self.network()
        self.assertEqual(self.metric('network-build-calls'), 1)
        self.h.builtins['NAMEDOBJDICT'] = lambda: 'different-document'
        self.network()
        self.assertEqual(self.metric('network-build-calls'), 2)
        # load_definitions excludes top-level setq; inspect real reload reset separately.
        source = (simple.adapter.ROOT / 'src/simple.lsp').read_text(encoding='utf-8')
        self.assertIn('(setq *EL:NetworkMemo* nil)', source)

    def test_cancelled_geometry_validation_leaves_no_memo(self):
        self.network()
        def cancelled(*args):
            raise RuntimeError('cancelled')
        self.h.builtins['EL:DEVICECONTACTSHAPE'] = cancelled
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.network()
        self.assertIsNone(self.h.lookup('*EL:NETWORKMEMO*'))

    def test_boundary_during_geometry_read_rejects_and_discards(self):
        self.network()
        original = self.h.functions[Symbol('EL:DEVICECONTACTSHAPE')]
        def callback(block):
            self.call('EL:FreshBoundary')
            return self.h.call([Symbol('LAMBDA'), original[0], *original[1]], [block])
        self.h.builtins['EL:DEVICECONTACTSHAPE'] = callback
        self.h.builtins['EXIT'] = lambda: (_ for _ in ()).throw(RuntimeError('quit / exit abort'))
        with self.assertRaisesRegex(RuntimeError, 'quit / exit abort'):
            self.network()
        self.assertIsNone(self.h.lookup('*EL:NETWORKMEMO*'))

    def test_nested_definition_visibility_is_checked_again(self):
        self.block('INNER', 'D', 'inner-definition-insert', [0., 0., 0.])
        self.entities['LAMP-edge-0'] = [Pair(0, 'INSERT'), Pair(5, 'LAMP-edge-0'),
            Pair(2, 'INNER'), Pair(8, '0'), Pair(10, [0., 0., 0.])]
        before = self.network()
        self.assertEqual(self.network(), before)
        self.assertEqual(self.metric('network-verified-reuses'), 1)
        self.entities['INNER-edge-0'].append(Pair(60, 1))
        self.call('EL:FreshBoundary')
        changed = self.network()
        self.assertNotEqual(changed, before)
        self.assertEqual(changed, self.oracle())

    def test_anonymous_curved_definition_is_not_validated_by_name_or_bounds(self):
        self.block('*U2', 'D', 'curved', [10., 0., 0.])
        self.selected.append('curved')
        self.entities['*U2-edge-0'] = [Pair(0, 'CIRCLE'), Pair(5, '*U2-edge-0'),
            Pair(8, 'D'), Pair(10, [0., 0., 0.]), Pair(40, 1.)]
        for index in range(1, 4):
            self.entities[f'*U2-edge-{index}'].append(Pair(60, 1))
        before = self.network()
        self.assertEqual(self.network(), before)
        self.entities['*U2-edge-0'][-1] = Pair(40, .9)
        changed = self.network()
        self.assertNotEqual(changed, before)
        self.assertEqual(changed, self.oracle())

    def test_input_and_write_callbacks_recheck_definition_and_undo(self):
        for boundary in ('EL:PerfInput', 'EL:PerfWrite'):
            with self.subTest(boundary=boundary):
                self.setUp()
                before = self.network()
                old = copy.deepcopy(self.entities)
                def callback():
                    self.network()  # A sample inside a callback is not proof after return.
                    self.line('LAMP-edge-0', [-.5, -.5, 0.], [.5, -.5, 0.])
                    return True
                self.h.builtins['TEST:CALLBACK'] = callback
                self.call(boundary, Symbol('TEST:CALLBACK'), [])
                self.assertNotEqual(self.network(), before)
                self.entities.clear(); self.entities.update(old)
                self.call('EL:FreshBoundary')  # Simulated undo restores exact source data.
                self.assertEqual(self.network(), before)


class FreshNetworkSignatureTests(unittest.TestCase):
    setUp = fresh.FreshnessReuseTests.setUp
    call = fresh.FreshnessReuseTests.call
    result = fresh.FreshnessReuseTests.result
    def test_verified_network_keeps_full_source_signature_and_detects_definition_edit(self):
        self.h.builtins['EL:PERFREPORT'] = lambda summary: None
        self.call('EL:PerfStart', 'ELSTAT')
        result = self.result()
        self.assertTrue(truth(self.call('EL:FreshResult', result, self.f.cfg)))
        self.f.line('LAMP-edge-0', [-.5, -.5, 0.], [.5, -.5, 0.])
        self.call('EL:FreshBoundary')
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.f.cfg)))

    def test_trunk_snapshot_and_unregistered_devices_match_full_recognition(self):
        import test_concentrated_trunk as trunk
        f = trunk.TrunkTests(); f.setUp()
        f.h.builtins['EL:PERFREPORT'] = lambda summary: None
        f.call('EL:PerfStart', 'ELSTAT')
        result = f.recognize()
        baseline = f.get('snapshot', result)
        for _ in range(3):
            f.call('EL:FreshBoundary')
            self.assertEqual(f.call('EL:FixedFreshSnapshot', f.cfg, 'panel'), baseline)
        metrics = f.h.lookup('*EL:PERFMETRICS*')
        self.assertEqual(f.call('EL:Get', 'network-build-calls', metrics), 1)
        self.assertEqual(f.call('EL:Get', 'network-verified-reuses', metrics), 3)
        f.line('trunk', [10., -16., 0.], [10., 16., 0.], 'W')
        f.call('EL:FreshBoundary')
        self.assertFalse(truth(f.call('EL:FreshResult', result, f.cfg)))


class ScanGenerationIntegrationTests(unittest.TestCase):
    def test_new_power_update_and_noop_keep_verified_store_and_uid(self):
        # Two finite CAD surfaces: source reads execute real collect/network,
        # output/store execute real SyncDiagram/transactions/readback.
        import test_cckk_panel_command as native
        sf = simple.SimpleFlowTests(); sf.setUp(); sf.plan()
        sf.entities['source'] = [Pair(5, 'source') if isinstance(p, Pair) and p.car == 5 else p
            for p in sf.entities.pop('panel')]
        sf.bounds['source'] = sf.bounds.pop('panel')
        sf.selected = ['source' if e == 'panel' else e for e in sf.selected]
        sf.h.load_definitions(simple.adapter.ROOT / 'src/panel.lsp')
        sf.h.builtins['HANDENT'] = lambda e: e if e in sf.entities else None
        sf.h.builtins['EL:MANAGEDENTITY'] = lambda e: None
        sf.h.builtins['GETVAR'] = lambda key: 0
        sf.h.builtins['EL:PERFREPORT'] = lambda summary: None
        sf.call('EL:PerfStart', 'ELSTAT')
        source = sf.call('EL:FixedFreshSnapshot', sf.cfg, 'source')
        f = native.PanelCommandTests(); f.setUp()
        f.h.builtins.pop('EL:FRESHRESULT')
        f.h.builtins['EL:FIXEDFRESHSNAPSHOT'] = lambda *args: sf.call('EL:FixedFreshSnapshot', sf.cfg, 'source')
        f.h.builtins['EL:PERFREPORT'] = lambda summary: None
        f.h.frames[0]['SOURCE-SAMPLE'] = source
        f.h.frames[0]['SOURCE-CONFIG'] = sf.cfg
        f.h.run("""(setq cfg (EL:Put 'template template SOURCE-CONFIG))
            (setq result (EL:Put 'drawing (EL:Get 'drawing cfg) result))
            (setq result (EL:Put 'capacity-source 'default (EL:Put 'engine 'fixed
            (EL:Put 'snapshot SOURCE-SAMPLE (EL:Put 'rules (EL:RecognitionRules cfg) result)))))
            (setq result (EL:Put 'circuits (mapcar '(lambda (c)
                (EL:Put 'ground-source 'manual (EL:Put 'is-ground nil c)))
                (EL:Get 'circuits result)) result))""")
        evidence = []
        for scenario in ('new', 'power', 'noop'):
            if scenario == 'power':
                f.h.run("(setq result (EL:Put 'circuits (list (EL:Put 'watts 95 (car (EL:Get 'circuits result)))) result))")
            f.call('EL:PerfStart', 'ELSTAT')
            sf.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
            sf.call('EL:PerfStart', 'ELSTAT')
            before = copy.deepcopy(f.entities)
            self.assertTrue(truth(f.invoke()))
            saved = f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
            rows = f.get('rows', saved)
            if scenario == 'new':
                output = f.get('panel-output-handle', saved)
                uids = [f.get('circuit-uid', r) for r in rows]
            self.assertEqual(f.get('panel-output-handle', saved), output)
            self.assertEqual([f.get('circuit-uid', r) for r in rows], uids)
            self.assertEqual(f.get('watts', rows[0]), 85 if scenario == 'new' else 95)
            metrics = f.h.lookup('*EL:PERFMETRICS*')
            store_writes = f.call('EL:Get', 'store-write-calls', metrics)
            if scenario == 'noop':
                self.assertEqual(store_writes, 0)
                self.assertEqual(f.entities, before)
            else:
                self.assertEqual(store_writes, 1)
                self.assertTrue(f.call('EL:Get', 'store-context-reuses', metrics))
            sm = sf.h.lookup('*EL:PERFMETRICS*')
            evidence.append({'scenario': scenario,
                'collections': sf.call('EL:Get', 'source-collect-calls', sm),
                'network_builds': sf.call('EL:Get', 'network-build-calls', sm),
                'verified_reuses': sf.call('EL:Get', 'network-verified-reuses', sm),
                'master_writes': store_writes, 'stable_uids': True,
                'actual_store_readback': scenario != 'noop'})
            f.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
        type(self).integration_evidence = evidence


if __name__ == '__main__':
    unittest.main()
