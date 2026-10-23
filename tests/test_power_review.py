"""Power review and blank annotations. Date: 2026-10-22. Status: adapter regression."""
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
                 self.put('issues', self.h.run("'(((code . OTHER_PANEL)))"), base)]
        for c in cases:
            computed = self.call('EL:PanelCompute', self.put('circuits', [c], self.result), self.powers, None)
            self.assertFalse(truth(self.get('can-generate', computed)))
        for watts in (173, 2147483647):
            result = self.call('EL:DLSetOverride', self.result, 'Lamp', Symbol('WATTS-SET'), True)
            result = self.call('EL:DLSetOverride', result, 'Lamp', Symbol('WATTS'), watts)
            computed = self.call('EL:PanelCompute', result, self.powers, None)
            self.assertFalse(truth(self.get('can-generate', computed)))

    def closed_result(self, empty=False):
        c = self.get('circuits', self.result)[0]
        issue = self.h.run("'(((code . CLOSED_CIRCUIT) (object . \"111F1\") (detail . \"11B6D\")))")
        c = self.put('issues', issue, self.put('complete', None, c))
        c = self.put('number-status', Symbol('READY'), self.put('circuit-number', 'ZE4', c))
        if empty:
            c = self.put('devices', None, c)
        return self.put('complete', None, self.put('circuits', [c], self.result))

    def test_closed_connection_continues_with_original_evidence_and_blank_power(self):
        original = self.closed_result()
        computed = self.call('EL:PanelCompute', original, self.powers, None)
        c = self.get('circuits', computed)[0]
        self.assertTrue(truth(self.get('can-generate', computed)))
        self.assertFalse(truth(self.get('complete', computed)))
        self.assertFalse(truth(self.get('complete', c)))
        self.assertTrue(truth(self.get('power-omitted', c)))
        self.assertEqual(self.get('issues', c), self.get('issues', self.get('circuits', original)[0]))
        self.assertEqual(self.call('EL:PanelCircuitPowerText', c), '闭合待核对')
        self.h.set('*EL:PANELDRAFT*', computed)
        self.call('EL:PowerReviewFill')
        self.assertTrue(any('闭合连接' in line and '111F1' in line and '11B6D' in line
                            for line in self.lists['q_details']))

    def test_closed_connection_without_recognized_device_also_keeps_output(self):
        computed = self.call('EL:PanelCompute', self.closed_result(empty=True), self.powers, None)
        self.assertTrue(truth(self.get('can-generate', computed)))
        self.assertTrue(truth(self.get('power-omitted', self.get('circuits', computed)[0])))

    def test_closed_warning_does_not_hide_other_circuit_or_snapshot_faults(self):
        original = self.closed_result()
        c = self.get('circuits', original)[0]
        more = self.h.run("'((code . OTHER_PANEL) (object . \"other-box\"))")
        combined = self.put('issues', self.get('issues', c) + [more], c)
        computed = self.call('EL:PanelCompute', self.put('circuits', [combined], original), self.powers, None)
        self.assertFalse(truth(self.get('can-generate', computed)))
        other = self.put('id', 'C2', self.put('issues', [more], copy.deepcopy(c)))
        computed = self.call('EL:PanelCompute', self.put('circuits', [c, other], original), self.powers, None)
        self.assertFalse(truth(self.get('can-generate', computed)))
        snapshot = self.put('issues', [more], self.get('snapshot', original))
        computed = self.call('EL:PanelCompute', self.put('snapshot', snapshot, original), self.powers, None)
        self.assertFalse(truth(self.get('can-generate', computed)))

    def test_generate_with_closed_warning_logs_details_without_alert_or_retrace(self):
        self.forbid_recognition()
        computed = self.call('EL:PanelCompute', self.closed_result(), self.powers, None)
        self.h.set('*EL:PANELDRAFT*', computed)
        self.h.set('*EL:PANELTEMPLATEREADY*', True)
        self.h.set('*EL:PANELCAPACITY*', Symbol('CAP300'))
        closed, logged = [], []
        self.h.builtins.update({'EL:DLPANELSUBMISSIONREADY': lambda: True,
            'EL:PANELCLOSE': closed.append, 'EL:LOGEVENT': lambda *args: logged.append(args),
            'ALERT': lambda *args: self.fail('closed warning must not open an alert')})
        self.call('EL:PanelGenerateBody')
        self.assertEqual(closed, [2])
        self.assertEqual(self.h.lookup('*EL:PANELACTION*'), Symbol('GENERATE'))
        self.assertIn('GENERATION_WITH_WARNINGS', [event[0] for event in logged])

    def reported_problem_result(self):
        base = self.get('circuits', self.result)[0]
        closed = self.put('id', 'R2', self.put('devices', ['D0'], base))
        closed = self.put('wires', ['1449F', '26060'], self.put('complete', None, closed))
        closed = self.put('issues', self.h.run("'(((code . CLOSED_CIRCUIT) (object . \"1449F\") (detail . \"D410\")))"), closed)
        closed = self.put('number-status', Symbol('READY'), self.put('circuit-number', 'ZE2', closed))
        good = self.put('id', 'R3', self.put('devices', ['D1'], self.put('wires', ['GOOD-WIRE'], base)))
        good = self.put('number-status', Symbol('READY'), self.put('circuit-number', 'ZE3', good))
        empty = self.put('id', 'R5', self.put('devices', None, self.put('wires', ['260CE', '260CD'], base)))
        empty = self.put('number-status', Symbol('READY'), self.put('circuit-number', 'ZE4', empty))
        result = self.put('complete', None, self.put('circuits', [closed, good, empty], self.result))
        result = self.call('EL:DLSetOverride', result, 'Unknown', Symbol('WATTS-SET'), True)
        result = self.call('EL:DLSetOverride', result, 'Unknown', Symbol('WATTS'), 1)
        return self.call('EL:PanelCompute', result, self.powers, None)

    def test_all_known_watts_with_closed_and_no_device_circuits_keep_actual_rows(self):
        self.forbid_recognition()
        computed = self.reported_problem_result()
        closed, good, empty = self.get('circuits', computed)
        self.assertTrue(truth(self.get('can-generate', computed)))
        self.assertTrue(truth(self.get('power-values-complete', closed)))
        self.assertEqual([self.call('EL:PanelCircuitPowerText', c) for c in (closed, good, empty)],
                         ['闭合待核对', '1W', '未识别设备'])
        self.assertEqual([truth(self.get('power-omitted', c)) for c in (closed, good, empty)], [True, False, True])
        self.assertIsNone(self.get('library-pending', computed))
        self.assertFalse(truth(self.get('power-complete', empty)))
        self.assertEqual(self.get('wires', empty), ['260CE', '260CD'])
        self.assertEqual(self.get('code', self.get('power-issues', empty)[0]), Symbol('NO_RECOGNIZED_DEVICES'))
        self.h.set('*EL:PANELDRAFT*', computed)
        self.h.set('*EL:POWERREVIEWROWS*', self.call('EL:PowerReviewRows', computed, self.get('effective-powers', computed)))
        self.call('EL:PowerReviewFill')
        details = '\n'.join(self.lists['q_details'])
        for value in ('单个功率已填写', 'ZE2', '闭合连接', '1449F', 'D410', 'ZE4', '260CE', '260CD', '补单个功率无法解决'):
            self.assertIn(value, details)
        self.assertNotIn('其他设备缺项', details)

    def test_power_edit_does_not_clear_connection_warnings_or_require_retrace(self):
        computed = self.reported_problem_result()
        snapshot = copy.deepcopy(self.get('snapshot', computed))
        issues = copy.deepcopy(self.get('issues', self.get('circuits', computed)[0]))
        self.forbid_recognition()
        self.h.set('*EL:PANELDRAFT*', computed)
        self.h.set('*EL:POWERREVIEWROWS*', self.call('EL:PowerReviewRows', computed, self.get('effective-powers', computed)))
        self.call('EL:PowerReviewFill')
        self.tiles['q_watts'] = '7'
        self.assertTrue(truth(self.call('EL:PowerReviewApply')))
        after = self.h.lookup('*EL:PANELDRAFT*')
        self.assertEqual(self.get('snapshot', after), snapshot)
        self.assertEqual(self.get('issues', self.get('circuits', after)[0]), issues)
        self.assertTrue(truth(self.get('can-generate', after)))
        self.assertTrue(truth(self.get('power-omitted', self.get('circuits', after)[0])))
        self.assertTrue(truth(self.get('power-omitted', self.get('circuits', after)[2])))

    def test_no_device_warning_requires_actual_wires_and_unambiguous_complete_path(self):
        computed = self.reported_problem_result()
        empty = self.get('circuits', computed)[2]
        self.assertTrue(truth(self.call('EL:CircuitNoDeviceWarning', empty)))
        fault = self.h.run("'((code . OTHER_PANEL) (object . \"BOX2\"))")
        for changed in (self.put('wires', None, empty), self.put('complete', None, empty),
                        self.put('issues', [fault], empty), self.put('power-issues', [fault], empty)):
            with self.subTest(changed=changed):
                self.assertFalse(truth(self.call('EL:CircuitNoDeviceWarning', changed)))
                self.assertFalse(truth(self.call('EL:PartialPowerCircuitReady', changed)))

    def test_reported_warning_pair_keeps_other_generation_blockers(self):
        computed = self.reported_problem_result()
        fault = self.h.run("'((code . UNSUPPORTED_GEOMETRY) (object . \"W1\"))")
        variants = [self.put('issues', [fault], computed),
                    self.put('snapshot', self.put('issues', [fault], self.get('snapshot', computed)), computed),
                    self.put('box-total-overflow', True, computed),
                    self.put('device-library', self.put('load-error', True, self.get('device-library', computed)), computed)]
        for changed in variants:
            self.assertFalse(truth(self.call('EL:PartialPowerGenerationReady', changed)))
        closed, good, empty = self.get('circuits', computed)
        for circuit in (self.put('number-status', Symbol('CONFLICT'), closed),
                        self.put('devices', ['D0'], good)):
            circuits = [circuit, good, empty] if self.get('id', circuit) == 'R2' else [closed, circuit, empty]
            blocked = self.call('EL:PanelCompute', self.put('circuits', circuits, computed), self.powers, None)
            self.assertFalse(truth(self.get('can-generate', blocked)))
        above_limit = self.call('EL:DLSetOverride', computed, 'Lamp', Symbol('WATTS-SET'), True)
        above_limit = self.call('EL:DLSetOverride', above_limit, 'Lamp', Symbol('WATTS'), 173)
        blocked = self.call('EL:PanelCompute', above_limit, self.powers, None)
        self.assertFalse(truth(self.get('can-generate', blocked)))

    def test_warning_pair_generate_logs_both_real_circuit_numbers_without_alert(self):
        self.forbid_recognition()
        computed = self.reported_problem_result()
        self.h.set('*EL:PANELDRAFT*', computed)
        self.h.set('*EL:PANELTEMPLATEREADY*', True)
        self.h.set('*EL:PANELCAPACITY*', Symbol('CAP300'))
        closed, logs = [], []
        self.h.builtins.update({'EL:DLPANELSUBMISSIONREADY': lambda: True,
            'EL:PANELCLOSE': closed.append, 'EL:LOGEVENT': lambda *args: logs.append(args),
            'ALERT': lambda *args: self.fail('recoverable warnings must not open an alert')})
        self.call('EL:PanelGenerateBody')
        self.assertEqual(closed, [2])
        reasons = self.get('reasons', next(row[1] for row in logs if row[0] == 'GENERATION_WITH_WARNINGS'))
        self.assertEqual(len(reasons), 2)
        for value in ('ZE2', '1449F', 'D410', 'ZE4', '260CE', '260CD', '功率留空'):
            self.assertIn(value, '\n'.join(reasons))
        self.assertEqual(self.h.lookup('*EL:PANELACTION*'), Symbol('GENERATE'))

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

    def test_computed_closed_circuit_generates_both_rows_with_only_good_power_text(self):
        f = native.PanelCommandTests()
        f.setUp()
        f.two_circuits()
        f.h.run("""
          (setq cs (EL:Get 'circuits result))
          (setq first (EL:Put 'devices '("D0") (EL:Put 'complete nil
            (EL:Put 'issues '(((code . CLOSED_CIRCUIT) (object . "111F1") (detail . "11B6D"))) (car cs)))))
          (setq second (EL:Put 'devices '("D1") (EL:Put 'complete T (cadr cs))))
          (setq snapshot '((blocks
            ((id . "D0") (name . "A") (role . device) (identity "A" nil "block-name-v1"))
            ((id . "D1") (name . "B") (role . device) (identity "B" nil "block-name-v1")))))
          (setq result (EL:Put 'snapshot snapshot
            (EL:Put 'complete nil (EL:Put 'circuits (list first second) result))))
          (setq result (EL:PanelCompute result '(("A" . 85) ("B" . 20)) cfg))
        """)
        self.assertTrue(truth(f.get('can-generate', f.h.lookup('RESULT'))))
        self.assertTrue(truth(f.invoke()))
        record = f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        rows = f.get('rows', record)
        self.assertEqual(len(rows), 4)
        self.assertTrue(f.get('block-handle', rows[0]))
        self.assertTrue(f.get('circuit-number', rows[0]))
        self.assertIsNone(f.get('text-handle', rows[0]))
        self.assertIsNone(f.get('watts', rows[0]))
        self.assertEqual(field(f.entities[f.get('text-handle', rows[1])], 1), '20W')

    def test_closed_and_no_device_actual_rows_generate_without_power_or_reserve_replacement(self):
        f = native.PanelCommandTests()
        f.setUp()
        f.two_circuits()
        f.h.run("""
          (setq cs (EL:Get 'circuits result))
          (setq first (EL:Put 'devices '("D0") (EL:Put 'complete nil
            (EL:Put 'issues '(((code . CLOSED_CIRCUIT) (object . "1449F") (detail . "D410"))) (car cs)))))
          (setq second (EL:Put 'devices '("D1") (EL:Put 'complete T (cadr cs))))
          (setq empty (EL:Put 'uid "empty-real-circuit" (EL:Put 'id "R5"
            (EL:Put 'seed-key '("260CD" outlet) (EL:Put 'circuit-number "ZE4"
              (EL:Put 'number-status 'ready (EL:Put 'devices nil
                (EL:Put 'wires '("260CE" "260CD") second))))))))
          (setq empty (EL:Put 'seed '((key "260CD" outlet) (wire . "260CD")) empty))
          (setq snapshot '((blocks
            ((id . "D0") (name . "A") (role . device) (identity "A" nil "block-name-v1"))
            ((id . "D1") (name . "B") (role . device) (identity "B" nil "block-name-v1")))))
          (setq result (EL:Put 'snapshot snapshot
            (EL:Put 'complete nil (EL:Put 'circuits (list first second empty) result))))
          (setq result (EL:PanelCompute result '(("A" . 85) ("B" . 20)) cfg))
        """)
        self.assertTrue(truth(f.get('can-generate', f.h.lookup('RESULT'))))
        self.assertTrue(truth(f.invoke()))
        record = f.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        rows = f.get('rows', record)
        self.assertEqual(len(rows), f.call('EL:FixedOutputCount', 3))
        for index in (0, 2):
            self.assertTrue(f.get('block-handle', rows[index]))
            self.assertTrue(f.get('circuit-number', rows[index]))
            self.assertIsNone(f.get('watts', rows[index]))
            self.assertIsNone(f.get('text-handle', rows[index]))
            self.assertNotEqual(f.get('option', rows[index]), Symbol('RESERVE'))
        self.assertEqual(f.get('circuit-number', rows[2]), 'ZE4')
        self.assertEqual(field(f.entities[f.get('text-handle', rows[1])], 1), '20W')
