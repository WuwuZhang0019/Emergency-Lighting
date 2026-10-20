"""Power review and blank annotations. Date: 2026-10-21. Status: adapter regression."""
import copy
import unittest
from autolisp_host import Symbol, truth
import test_device_recognition as recognition
import test_cckk_panel_command as native
from test_cckk_assembly import field


class PowerReviewTests(unittest.TestCase):
    def setUp(self):
        self.f = recognition.DeviceRecognitionTests()
        self.f.setUp()
        self.h, self.call, self.get, self.put = self.f.h, self.f.call, self.f.get, self.f.put
        self.result, self.powers, _ = self.f.model(('Lamp', 'Unknown'))
        self.result = self.call('EL:PanelCompute', self.result, self.powers, None)
        self.tiles, self.lists, self.alerts = {}, {}, []
        def start(key):
            self.list_key = key
            self.lists[key] = []
        self.h.builtins.update({'SET_TILE': lambda k, v: self.tiles.__setitem__(k, v),
            'GET_TILE': lambda k: self.tiles.get(k, ''), 'START_LIST': start,
            'ADD_LIST': lambda s: self.lists[self.list_key].append(s), 'END_LIST': lambda: None,
            'ALERT': self.alerts.append})
        self.h.set('*EL:PANELDRAFT*', self.result)
        self.h.set('*EL:PANELPOWERS*', self.powers)
        self.h.set('*EL:PANELCONFIG*', None)
        self.h.set('*EL:POWERREVIEWROWS*', self.call('EL:PowerReviewRows', self.result, self.powers))
        self.h.set('*EL:POWERREVIEWINDEX*', 0)
        self.h.set('*EL:POWERREVIEWINSTANCE*', 0)
        self.call('EL:PowerReviewFill')

    def forbid_recognition(self):
        for name in ('EL:RECOGNIZEFIXED', 'EL:SIMPLENETWORK', 'EL:SPLITNETWORK', 'EL:COLLECTSNAPSHOT', 'SSGET'):
            self.h.builtins[name] = lambda *args: self.fail('power edit must not repeat recognition')

    def test_missing_first_with_real_number_handle_and_reason(self):
        c = self.get('circuits', self.result)[0]
        c = self.put('number-status', Symbol('READY'), self.put('circuit-number', 'ZE5', c))
        self.h.set('*EL:PANELDRAFT*', self.put('circuits', [c], self.result))
        self.call('EL:PowerReviewFill')
        self.assertIn('Unknown', self.lists['q_rows'][0])
        self.assertIn('待核对', self.lists['q_rows'][0])
        self.assertIn('所在回路：ZE5', self.lists['q_details'])
        self.assertEqual(self.lists['q_instances'], ['D1 / ZE5'])
        self.assertTrue(any('功率未填写' in s or '功率缺失' in s for s in self.lists['q_details']))

    def test_apply_reuses_snapshot_and_updates_only_local_power(self):
        self.forbid_recognition()
        before = copy.deepcopy(self.get('snapshot', self.result))
        catalog = copy.deepcopy(self.f.cat)
        self.tiles['q_watts'] = '7'
        self.assertTrue(truth(self.call('EL:PowerReviewApply')))
        result = self.h.lookup('*EL:PANELDRAFT*')
        self.assertEqual(self.get('snapshot', result), before)
        self.assertEqual(self.f.cat, catalog)
        self.assertEqual(self.get('watts', self.get('circuits', result)[0]), 12)
        self.assertFalse(truth(self.get('power-omitted', self.get('circuits', result)[0])))
        self.assertTrue(truth(self.get('can-generate', result)))
        self.assertIsNone(self.get('library-pending', result))
        self.assertEqual(self.get('watts', self.call('EL:DLOverride', 'Unknown', result)), 7)

    def test_blank_and_explicit_zero_remain_different(self):
        for raw, zero, accepted, omitted in [('bad', '0', False, True), ('0', '0', False, True),
                                            ('0', '1', True, False), ('', '0', True, True)]:
            self.tiles.update(q_watts=raw, q_zero=zero)
            self.assertEqual(truth(self.call('EL:PowerReviewApply')), accepted)
            c = self.get('circuits', self.h.lookup('*EL:PANELDRAFT*'))[0]
            self.assertEqual(truth(self.get('power-omitted', c)), omitted)

    def test_row_switch_retains_unapplied_input(self):
        self.tiles['q_watts'] = '17'
        self.call('EL:PowerReviewSelect', '1')
        self.call('EL:PowerReviewSelect', '0')
        self.assertEqual(self.tiles['q_watts'], '17')
        self.assertIsNone(self.call('EL:Get', 'UNKNOWN', self.h.lookup('*EL:PANELPOWERS*')))

    def test_locate_selected_handle_returns_and_cleans_after_escape(self):
        self.forbid_recognition()
        located, cleanup = [], []
        self.h.builtins.update({'HANDENT': lambda h: h,
            'EL:SIMPLELOCATE': lambda result, row: located.append(self.get('ids', row)),
            'EL:PERFINPUT': lambda *args: (_ for _ in ()).throw(RuntimeError('Function cancelled')),
            'EL:CLEARGAPPREVIEW': lambda: cleanup.append('preview'),
            'EL:CLEARPICKHIGHLIGHTS': lambda: cleanup.append('highlight')})
        self.call('EL:PowerReviewLocate')
        self.assertEqual(located, [['D1']])
        self.assertEqual(cleanup, ['preview', 'highlight'])
        self.assertEqual(self.h.lookup('*EL:PANELDRAFT*'), self.result)

    def test_connection_number_overflow_and_overlimit_are_not_bypassed(self):
        base = self.get('circuits', self.result)[0]
        cases = [self.put('complete', None, base), self.put('number-status', Symbol('CONFLICT'), base),
                 self.put('issues', self.h.run("'(((code . CLOSED_CIRCUIT)))"), base)]
        for c in cases:
            computed = self.call('EL:PanelCompute', self.put('circuits', [c], self.result), self.powers, None)
            self.assertFalse(truth(self.get('can-generate', computed)))
        for watts in (173, 2147483647):
            result = self.call('EL:DLSetOverride', self.result, 'Lamp', Symbol('WATTS-SET'), True)
            result = self.call('EL:DLSetOverride', result, 'Lamp', Symbol('WATTS'), watts)
            computed = self.call('EL:PanelCompute', result, self.powers, None)
            self.assertFalse(truth(self.get('can-generate', computed)))

    def test_dialog_returns_to_parent_with_applied_value_and_same_snapshot(self):
        self.forbid_recognition()
        actions, dialogs = {}, []
        before = copy.deepcopy(self.get('snapshot', self.result))
        self.h.builtins['NEW_DIALOG'] = lambda name, dialog: dialogs.append(name) or True
        self.h.builtins['EL:MONITORACTIONTILE'] = lambda key, code: actions.__setitem__(key, code)
        self.h.builtins['DONE_DIALOG'] = lambda code: code
        def run_dialog():
            self.tiles['q_watts'] = '8'
            self.h.run(actions['q_apply'])
            return self.h.run(actions['cancel'])
        self.h.builtins['START_DIALOG'] = run_dialog
        self.call('EL:PanelPowerReview', 1)
        self.assertEqual(dialogs, ['el_panel_power_review'])
        result = self.h.lookup('*EL:PANELDRAFT*')
        self.assertEqual(self.get('snapshot', result), before)
        self.assertEqual(self.get('watts', self.get('circuits', result)[0]), 13)


class BlankPowerGenerationTests(unittest.TestCase):
    def test_actual_circuit_without_power_keeps_block_number_and_record(self):
        f = native.PanelCommandTests()
        f.setUp()
        f.two_circuits()
        f.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'power-omitted T (car (EL:Get 'circuits result))) (cdr (EL:Get 'circuits result))) result))")
        self.assertTrue(truth(f.invoke()))
        record = f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        rows = f.get('rows', record)
        self.assertEqual(len(rows), 4)
        self.assertTrue(f.get('block-handle', rows[0]))
        self.assertIsNone(f.get('text-handle', rows[0]))
        self.assertIsNone(f.get('watts', rows[0]))
        self.assertTrue(f.get('circuit-number', rows[0]))
        self.assertEqual(f.get('watts', rows[1]), 20)
        self.assertEqual(field(f.entities[f.get('text-handle', rows[1])], 1), '20W')
        self.assertTrue(all(f.get('text-handle', r) is None for r in rows[2:]))
        self.assertEqual(len(f.commands), 5)
