"""Junction endpoint connection and branching. Date: 2026-10-13.
Bounded DWG adapters; original AutoCAD drawing acceptance remains pending.
"""
import copy
import unittest
from autolisp_host import Pair, Symbol, truth
import test_simple_flow as simple


class JunctionTests(unittest.TestCase):
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    line = simple.SimpleFlowTests.line
    block = simple.SimpleFlowTests.block
    network = simple.SimpleFlowTests.network

    def setUp(self):
        simple.SimpleFlowTests.setUp(self)
        self.h.load_definitions(simple.adapter.ROOT / 'src/panel.lsp')
        self.h.builtins['PRINC'] = lambda *args: None
        self.h.builtins['CHR'] = chr

    def put(self, key, value, row):
        return self.call('EL:Put', Symbol(key.upper()), value, row)

    def register(self):
        self.cfg = self.call('EL:JunctionSamples', self.cfg, ['JBOX'], None)

    def plan(self, branch=False, shared_point=False):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('JBOX', 'J', 'j', [10., 0., 0.])
        self.line('in', [1., 0., 0.], [10. if shared_point else 9., 0., 0.], 'W')
        self.line('east', [10. if shared_point else 11., 0., 0.], [19., 0., 0.], 'W')
        self.block('LAMP', 'D', 'a', [20., 0., 0.])
        self.line('east2', [21., 0., 0.], [29., 0., 0.], 'W')
        self.block('LAMP', 'D', 'b', [30., 0., 0.])
        self.selected = ['panel', 'j', 'in', 'east', 'a', 'east2', 'b']
        if branch:
            self.line('north', [10., 0. if shared_point else 1., 0.], [10., 9., 0.], 'W')
            self.block('LAMP', 'D', 'c', [10., 10., 0.])
            self.line('north2', [10., 11., 0.], [10., 19., 0.], 'W')
            self.block('LAMP', 'D', 'd', [10., 20., 0.])
            self.line('north3', [10., 21., 0.], [10., 29., 0.], 'W')
            self.block('LAMP', 'D', 'e', [10., 30., 0.])
            self.selected += ['north', 'c', 'north2', 'd', 'north3', 'e']
        self.register()

    def split(self, network=None):
        result = self.call('EL:SplitNetwork', network or self.network(), self.cfg)
        return self.call('EL:SelectFixedExits', result, None)

    def codes(self, circuit):
        return [self.get('code', i) for i in self.get('issues', circuit) or []]

    def test_two_sides_continue_without_junction_load_or_source_edits(self):
        self.plan()
        entities = copy.deepcopy(self.entities)
        network = self.network()
        self.assertEqual({self.get('id', b) for b in self.get('devices', network)}, {'a', 'b'})
        result = self.split(network)
        circuit = self.get('circuits', result)[0]
        self.assertTrue(truth(self.get('complete', result)), self.codes(circuit))
        self.assertIn('j', self.get('objects', circuit))
        self.assertNotIn('j', self.get('devices', circuit))
        stats = self.call('EL:PanelCompute', result, [Pair('LAMP', 5)], self.cfg)
        self.assertEqual(self.get('box-watts', stats), 10)
        self.assertEqual(self.get('count', self.get('counts', self.get('circuits', stats)[0])[0]), 2)
        refs = self.call('EL:DLPrepare', result, None, [Pair(Symbol('CATALOG'), None)], None)
        self.assertEqual([self.get('key', r) for r in self.get('items', self.get('device-library', self.get('result', refs)))], ['LAMP'])
        self.assertEqual(self.entities, entities)
        for key in (['in', Symbol('END')], ['east', Symbol('START')]):
            end = self.call('EL:By', Symbol('KEY'), key, self.get('ends', self.get('snapshot', network)))
            self.assertTrue(truth(self.get('occupied', end)))
            self.assertFalse(truth(self.call('EL:GapEligible', end)))

    def test_five_lamps_on_two_branches_remain_one_complete_circuit(self):
        self.plan(branch=True)
        result = self.split()
        circuits = self.get('circuits', result)
        self.assertEqual(len(circuits), 1)
        self.assertTrue(truth(self.get('complete', result)), self.codes(circuits[0]))
        self.assertEqual(set(self.get('devices', circuits[0])), {'a', 'b', 'c', 'd', 'e'})
        stats = self.call('EL:PanelCompute', result, [Pair('LAMP', 5)], self.cfg)
        self.assertEqual(self.get('box-watts', stats), 25)

    def test_coincident_endpoints_use_junction_without_false_cycle(self):
        self.plan(branch=True, shared_point=True)
        network = self.network()
        self.assertNotIn(['east', 'in'], self.get('edges', network))
        circuit = self.get('circuits', self.split(network))[0]
        self.assertEqual(len(self.get('devices', circuit)), 5)
        self.assertTrue(truth(self.get('complete', circuit)), self.codes(circuit))

    def test_crossing_wire_and_touching_block_do_not_join_junction(self):
        self.plan(shared_point=True)
        self.line('cross', [10., -20., 0.], [10., 20., 0.], 'W')
        self.block('OTHER', 'D', 'touching', [10., -2., 0.])
        self.selected += ['cross', 'touching']
        network = self.network()
        self.assertNotIn(['cross', 'j'], self.get('edges', network))
        self.assertNotIn(['j', 'touching'], self.get('edges', network))
        self.assertNotIn('cross', self.get('wire-ids', network))

    def test_bbox_empty_area_other_elevation_and_visible_gap_do_not_attach(self):
        for end in ([10.8, .8, 0.], [9., 0., 2.], [8.8, 0., 0.]):
            with self.subTest(end=end):
                self.setUp(); self.plan()
                # Triangle occupies only the lower-left half of the square bounds.
                if end[1]:
                    points = [[-1., -1., 0.], [1., -1., 0.], [-1., 1., 0.]]
                    for i, p in enumerate(points):
                        self.line(f'JBOX-edge-{i}', p, points[(i + 1) % 3])
                        self.next_entity[f'JBOX-edge-{i}'] = f'JBOX-edge-{i+1}' if i < 2 else 'JBOX-end'
                self.line('in', [1., end[1], end[2]], end, 'W')
                network = self.network()
                self.assertNotIn(['in', 'j'], self.get('edges', network) or [])

    def test_single_port_is_incomplete_and_locatable(self):
        self.plan()
        self.selected = ['panel', 'j', 'in']
        circuit = self.get('circuits', self.split())[0]
        self.assertFalse(truth(self.get('complete', circuit)))
        issue = self.call('EL:By', Symbol('CODE'), Symbol('JUNCTION_INCOMPLETE'), self.get('issues', circuit))
        self.assertEqual(self.get('object', issue), 'j')
        self.assertIn('接线盒', self.call('EL:GenerationIssueText', issue))

    def test_selected_exits_conflict_before_device_exclusion_and_recompute(self):
        self.plan()
        self.line('second', [0., 1., 0.], [10., 1., 0.], 'W')
        self.selected.append('second')
        result = self.split()
        self.assertEqual(len(self.get('circuits', result)), 2)
        for circuit in self.get('circuits', result):
            self.assertIn(Symbol('CIRCUIT_OWNERSHIP_CONFLICT'), self.codes(circuit))
        excluded = self.put('excluded-devices', ['a', 'b'], result)
        stats = self.call('EL:PanelCompute', excluded, None, self.cfg)
        self.assertFalse(truth(self.get('can-generate', stats)))
        key = self.get('key', self.get('seed', self.get('circuits', result)[1]))
        one = self.call('EL:SelectFixedExits', result, [key])
        self.assertTrue(truth(self.get('complete', one)), self.get('circuits', one))

    def test_true_closed_path_still_rejected(self):
        self.plan()
        # Return from lamp a to a different junction endpoint, a genuine cycle.
        self.entities['return'] = [Pair(0, 'LWPOLYLINE'), Pair(5, 'return'), Pair(8, 'W'),
            Pair(410, 'Model'), Pair(90, 4), Pair(70, 0), Pair(38, 0.), Pair(210, [0., 0., 1.])] + [
            Pair(10, p) for p in ([20., -1.], [20., -5.], [10., -5.], [10., -1.])]
        self.selected.append('return')
        circuit = self.get('circuits', self.split())[0]
        self.assertIn(Symbol('CLOSED_CIRCUIT'), self.codes(circuit))

    def test_device_handles_are_deduplicated_after_multiple_contacts(self):
        self.plan()
        result = self.split()
        circuit = self.get('circuits', result)[0]
        duplicate = self.put('devices', ['a', 'a', 'b', 'b'], circuit)
        rows = self.call('EL:CountRows', duplicate, self.get('blocks', self.get('snapshot', result)), None)
        self.assertEqual(self.get('count', rows[0]), 2)

    def test_registered_names_on_other_layers_survive_preset_filter(self):
        self.plan()
        cfg = self.put('preset-scoped', True, self.cfg)
        self.assertTrue(truth(self.call('EL:PresetBlockAllowed', 'j', self.entities['j'], cfg)))
        self.assertFalse(truth(self.call('EL:PresetBlockAllowed', 'j', self.entities['j'], self.put('roles', None, cfg))))
        filters = []
        original = self.h.builtins['SSGET']
        self.h.builtins['SSGET'] = lambda *args: filters.append(args) or self.selected
        self.call('EL:SimpleCollect', cfg)
        self.h.builtins['SSGET'] = original
        self.assertIn(Pair(0, 'INSERT'), filters[0][1])
        self.cfg = cfg
        self.assertTrue(truth(self.get('complete', self.split())))

    def command_storage(self, action=None):
        files = {'config-fixture': copy.deepcopy(self.cfg)}
        writes = []
        def write(path, data):
            files[path] = copy.deepcopy(data); writes.append(data); return True
        self.h.builtins.update({'EL:ENSUREROOT': lambda: True,
            'EL:CONFIGPATH': lambda *args: 'config-fixture',
            'FINDFILE': lambda p: p if p in files else None,
            'EL:READDATA': lambda p: copy.deepcopy(files.get(p)), 'EL:WRITEDATA': write,
            'INITGET': lambda *args: None, 'GETKWORD': lambda *args: action})
        return files, writes

    def test_command_saves_reloads_then_removes_classification(self):
        self.plan()
        self.cfg = self.put('roles', None, self.cfg)
        files, writes = self.command_storage()
        self.selected = ['j']
        self.call('c:ELJBOX')
        loaded = self.call('EL:LoadConfig')
        self.assertTrue(truth(self.call('EL:ConfigValid', loaded, 'adapter-fixture.dwg')))
        self.assertTrue(truth(self.call('EL:JunctionName', 'JBOX', loaded)))
        self.assertEqual(len(writes), 1)
        self.h.builtins['GETKWORD'] = lambda *args: 'Remove'
        self.call('c:ELJBOX')
        self.assertFalse(truth(self.call('EL:JunctionName', 'JBOX', self.call('EL:LoadConfig'))))
        self.assertEqual(len(writes), 2)

    def test_cancel_or_no_samples_leaves_saved_config_unchanged(self):
        self.plan()
        files, writes = self.command_storage()
        saved = copy.deepcopy(files)
        self.selected = []
        self.call('c:ELJBOX')
        self.h.builtins['SSGET'] = lambda *args: (_ for _ in ()).throw(RuntimeError('Function cancelled'))
        self.call('c:ELJBOX')
        self.assertEqual(files, saved)
        self.assertEqual(writes, [])

    def test_all_same_type_instances_and_panel_priority(self):
        self.plan()
        self.block('JBOX', 'J', 'j2', [40., 0., 0.])
        self.line('to-second', [31., 0., 0.], [39., 0., 0.], 'W')
        self.line('tail', [41., 0., 0.], [49., 0., 0.], 'W')
        self.block('LAMP', 'D', 'last', [50., 0., 0.])
        self.selected += ['j2', 'to-second', 'tail', 'last']
        network = self.network()
        self.assertEqual({self.get('id', b) for b in self.get('devices', network)}, {'a', 'b', 'last'})
        for block in self.get('blocks', self.get('snapshot', network)):
            if self.get('id', block) in ('j', 'j2'):
                self.assertEqual(self.get('role', block), Symbol('JUNCTION'))
        self.assertEqual(self.call('EL:FixedBlockRole', self.get('blocks', self.get('snapshot', network))[0],
            self.get('id', self.get('blocks', self.get('snapshot', network))[0]), self.cfg), Symbol('PANEL'))

    def test_classification_changes_invalidate_rules_and_freshness_uses_same_role(self):
        self.plan()
        result = self.split()
        # Actual interactive and freshness collection/network/snapshot routes.
        fresh = self.call('EL:FixedFreshSnapshot', self.cfg, 'panel')
        self.assertTrue(truth(self.call('EL:SourceCurrent', result, self.cfg, fresh)))
        old = self.call('EL:JunctionSamples', self.cfg, ['JBOX'], True)
        self.assertFalse(truth(self.call('EL:SourceCurrent', result, old, fresh)))
        rules = self.get('rules', result)
        legacy = [r for r in rules if (r.car if isinstance(r, Pair) else r[0]) != Symbol('JUNCTION-POLICY')]
        self.assertFalse(truth(self.call('EL:SourceCurrent', self.put('rules', legacy, result), self.cfg, fresh)))

    def test_actual_elstat_reaches_panel_and_system_plan_with_five_lamps(self):
        import test_post_stat_workflow as workflow
        import test_diagram_update as update
        self.plan(branch=True, shared_point=True)
        f = workflow.PostStatWorkflowTests()
        f.setUp(); self.addCleanup(f.doCleanups)
        for name in ('entities', 'blocks', 'bounds', 'next_entity', 'selected', 'cfg'):
            setattr(f, name, copy.deepcopy(getattr(self, name)))
        # Keep any package entry definitions loaded by the verifier.
        for name, definition in self.h.functions.items():
            f.h.functions[name] = definition
        # Date: 2026-10-13. Main now asks for the directional circuit start.
        picks = iter([['panel', [0., 0., 0.]], ['in', [1., 0., 0.]], None])
        f.h.builtins['EL:PICKMODEL'] = lambda *args: next(picks)
        seen = []
        def capture():
            seen.append(copy.deepcopy(f.h.lookup('*EL:PANELDRAFT*'))); f.done(0)
        f.actions = [lambda: f.done(9), capture]
        f.h.run('(c:ELSTAT)')
        result = seen[0]
        circuit = f.get('circuits', result)[0]
        self.assertEqual(len(f.get('circuits', result)), 1)
        self.assertEqual(set(f.get('devices', circuit)), {'a', 'b', 'c', 'd', 'e'})
        self.assertEqual(f.get('watts', circuit), 25)
        self.assertEqual(f.get('circuit-number', circuit), 'ZE1')
        self.assertTrue(truth(f.get('can-generate', result)), circuit)
        update.UpdateTests.generation_fixture(f)
        f.h.run('''(setq template (EL:Put 'panel (EL:Put 'name "ZYF_Tool_应急照明配电箱图块" (EL:Get 'panel template))
          (EL:Put 'circuit (EL:Put 'name "ZYF_Tool_应急照明配电回路图块" (EL:Get 'circuit template)) template)))''')
        plan = f.call('EL:FixedPlan', result, f.h.lookup('TEMPLATE'), Symbol('CAP300'), [0., 0., 0.], 0., 1.)
        labels = f.call('EL:CCKKLabels', plan)
        self.assertEqual([f.get('text', r) for r in labels if f.get('kind', r) == Symbol('NUMBER')][0], 'ZE1')
        power_labels = [f.get('text', r) for r in f.get('rows', plan) if f.get('mode', r) != Symbol('RESERVE')]
        self.assertEqual(power_labels, ['25W'])
        self.assertEqual(f.writes, [])

    def test_saved_system_config_uses_current_classification_and_detects_removal(self):
        self.plan(branch=True)
        files, writes = self.command_storage()
        self.h.frames[0]['*EL:ROOT*'] = 'package/'
        self.h.builtins['GETVAR'] = lambda *args: None
        old = self.put('roles', None, self.cfg)
        result = self.call('EL:RecognizeFixed', old, 'panel')
        self.assertEqual(len(self.get('devices', self.get('circuits', result)[0])), 5)
        self.assertIn('j', self.get('objects', self.get('circuits', result)[0]))
        self.assertTrue(truth(self.call('EL:FreshResult', result, old)))
        files['config-fixture'] = self.call('EL:JunctionSamples', self.cfg, ['JBOX'], True)
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.cfg)))
        current = self.call('EL:CurrentJunctionConfig', self.cfg)
        self.assertFalse(truth(self.call('EL:JunctionName', 'JBOX', current)))
        self.assertEqual(writes, [])

    def test_invalid_current_config_cannot_silently_reuse_saved_junction_role(self):
        self.plan()
        files, _ = self.command_storage()
        self.h.frames[0]['*EL:ROOT*'] = 'package/'
        files['config-fixture'] = [Pair(Symbol('VERSION'), 999)]
        self.h.builtins['EXIT'] = lambda: (_ for _ in ()).throw(RuntimeError('invalid-config'))
        with self.assertRaisesRegex(RuntimeError, 'invalid-config'):
            self.call('EL:RecognizeFixed', self.cfg, 'panel')


if __name__ == '__main__':
    unittest.main()
