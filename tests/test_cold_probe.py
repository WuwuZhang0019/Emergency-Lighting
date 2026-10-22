"""Date: 2026-10-22. Status: read-only cold probe bounded LISP regression.

Finite CAD adapters exercise the new command flow and the real RecognizeFixed
composition. They do not prove native CAD timing, .NET cold JIT, or the 3 s target.
"""
import copy
from pathlib import Path, PureWindowsPath
import unittest

from autolisp_host import Host, Pair, Symbol, seq, truth


ROOT = Path(__file__).resolve().parents[1]


def field(key, value):
    return Pair(Symbol(key.upper()), value)


class ColdProbeTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for filename in ('common', 'geometry', 'simple', 'diagram-update', 'diagram-commands', 'cold-probe'):
            self.h.load_definitions(ROOT / 'src' / (filename + '.lsp'))
        self.calls = []
        self.written = []
        self.logged = []
        self.ready = False
        self.handshake_response = 'EL_NET_COLD_PROBE_V1/0.1.76'
        self.atom_result = [None]
        self.library_found = True
        self.command_loads = True
        self.command_error = None
        self.main_native = self.native_main
        self.mode = None
        self.panel_pick = ['panel-object', [0.0, 0.0, 0.0]]
        self.pick_starts = True
        self.epoch = 7
        self.owner = 'drawing-owner'
        self.clock = 1000
        self.samples = [['D0', [1.0, 2.0, 0.0], [3.0, 4.0, 0.0]]]
        self.bounds = {'D0': [[1.0, 2.0, 0.0], [3.0, 4.0, 0.0]]}
        self.params = [field('eps_device', 0.01), field('Dmax', 2000.0), field('eps_boundary', 0.1)]
        self.starts = [
            [field('wire', 'W2'), field('end', Symbol('END')), field('point', [0.0, 1.0, 0.0])],
            [field('wire', 'W1'), field('end', Symbol('START')), field('point', [0.0, 0.0, 0.0])],
        ]
        self.base_cfg = [field('params', self.params), field('roles', [['D0', Symbol('DEVICE')]]),
                         field('wire-layers', ['WIRE']), field('panel-layers', ['PANEL']),
                         field('device-layers', ['DEVICE'])]
        self.business_result = [field('sentinel', 'previous-business-result')]
        self.device_result = [field('sentinel', 'previous-device-result')]
        self.h.set(Symbol('*EL:RESULT*'), self.business_result)
        self.h.set(Symbol('*EL:DEVICERESULT*'), self.device_result)
        self.h.set(Symbol('*EL:ROOT*'), 'C:/test-package/')
        self.h.set(Symbol('*EL:FRESHEPOCH*'), self.epoch)
        self.h.set(Symbol('*EL:COLDREPORTS*'), None)
        self.h.builtins.update({
            'INITGET': lambda *args: None,
            'GETKWORD': lambda *args: self.mode,
            'ATOMS-FAMILY': lambda *args: self.atom_result,
            'FINDFILE': lambda path: path if self.library_found else None,
            'COMMAND': self.command,
            'HANDENT': lambda handle: handle if handle in {'P0', 'D0'} else None,
            'ENTGET': lambda entity: [Pair(0, 'INSERT'), Pair(5, 'P0'), Pair(8, 'PANEL')],
            'NAMEDOBJDICT': lambda: self.owner,
            'EL:DRAWINGID': lambda: 'C:/cad/cold-probe.dwg',
            'EL:REQUIRE': self.require,
            'EL:PICKMODEL': self.pick_model,
            'EL:MANAGEDENTITY': lambda entity: None,
            'EL:LOADCONFIG': lambda: self.base_cfg,
            'EL:DEFAULTCONFIG': lambda drawing: copy.deepcopy(self.base_cfg),
            'EL:PRESETCONFIG': lambda cfg: cfg,
            'EL:FIXEDRECOGNITIONPARAMS': lambda cfg: self.get('params', cfg),
            'EL:PRESETREADY': lambda entity, cfg: cfg,
            'EL:PICKCIRCUITSTARTS': self.circuit_starts,
            'EL:CLEARGAPPREVIEW': lambda: self.calls.append(('clear-gap',)),
            'EL:CLEARPICKHIGHLIGHTS': lambda: self.calls.append(('clear-picks',)),
            'EL:TICK': self.tick,
            'EL:PRESETSELECTION': self.selection,
            'EL:PARAM': lambda cfg, key: self.get(str(key), self.get('params', cfg)),
            'ELNETCOLD76': self.native,
            'EL:ENTITYBOUNDS': lambda entity: self.bounds.get(entity),
            'EL:WRITEDATA': self.write_data,
            'EL:LOGEVENT': lambda name, detail: self.logged.append((name, detail)),
            'GETVAR': lambda key: 20261022.1 if key == 'CDATE' else 1000,
            'EL:LOGCALL': lambda name, detail, fn, args: self.h.call(fn, seq(args)),
            'EL:PERFCALL': self.perf_call,
            'EL:PERFBEGIN': lambda *args: None,
            'EL:PERFEND': lambda *args: None,
            'EL:PERFCOUNT': lambda *args: None,
            'EL:PERFSET': lambda *args: None,
            'EL:CURRENTJUNCTIONCONFIG': lambda cfg: cfg,
            'EL:SIMPLECOLLECT': self.collect,
            'EL:STARTSNAPSHOT': lambda snapshot, cfg, panel: snapshot,
            'EL:SIMPLENETWORK': self.network,
            'EL:SPLITNETWORK': self.split,
            'EL:SPLITNATIVENUMBERBRANCHES': lambda result, network, cfg: result,
            'EL:SELECTFIXEDEXITS': lambda result, selection: result,
        })
        # These are drawing writes, configuration/store persistence, or business UI.
        # Diagnostic report writes intentionally use the separate WriteData adapter.
        for name in ('ENTMAKE', 'ENTMAKEX', 'ENTMOD', 'ENTDEL', 'EL:SAVECONFIG', 'EL:STORESAVE',
                     'EL:SAVEDRAWINGSTORE', 'EL:PUBLISHDIAGRAM', 'EL:WRITEPLAN',
                     'EL:ALLCIRCUITCOLORWAIT', 'EL:PREVIEWRESULT', 'EL:RESULTDIALOG'):
            self.h.builtins[name] = self.forbidden(name)

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, name, data):
        return self.call('EL:Get', Symbol(name.upper()), data)

    def require(self, condition, message):
        if not truth(condition):
            raise RuntimeError(message)
        return True

    def forbidden(self, name):
        def reject(*args):
            raise AssertionError('Cold probe called forbidden business side effect: ' + name)
        return reject

    def tick(self):
        self.clock += 10
        return self.clock

    def command(self, *args):
        self.calls.append(('command', args))
        self.assertEqual(args[0], '_.NETLOAD')
        self.assertTrue(args[1].endswith('native/EmergencyLighting.ColdRecognition76.dll'))
        if self.command_error:
            raise RuntimeError(self.command_error)
        if self.command_loads:
            self.ready = True

    def perf_call(self, stage, fn, args):
        self.calls.append(('perf', stage))
        return self.h.call(fn, seq(args))

    def pick_model(self, kind, prompt):
        self.calls.append(('pick-panel', kind))
        return self.panel_pick

    def circuit_starts(self, cfg):
        self.calls.append(('pick-starts',))
        if not self.pick_starts:
            return None
        return self.call('EL:Put', Symbol('CIRCUIT-STARTS'), self.starts, cfg)

    def selection(self, cfg, types, keys):
        self.calls.append(('selection', cfg, types, keys))
        return ['P0', 'W1', 'W2', 'D0']

    def native(self, *args):
        if len(args) == 1:
            self.calls.append(('handshake', args))
            self.assertEqual(args, ('EL_NET_COLD_PING_V1',))
            if not self.ready:
                raise RuntimeError('no function definition: ELNETCOLD76')
            return self.handshake_response
        self.calls.append(('native', args))
        self.assertEqual(len(args), 7)
        if not self.ready:
            raise RuntimeError('no function definition: ELNETCOLD76')
        return self.main_native(*args)

    def native_main(self, *args):
        return ['{"status":"PROTOTYPE_COARSE_ONLY"}', copy.deepcopy(self.samples)]

    def write_data(self, path, report):
        self.written.append((path, copy.deepcopy(report)))
        return True

    def collect(self, cfg):
        self.calls.append(('collect', cfg))
        self.assertTrue(self.h.lookup(Symbol('*EL:NETWORKREUSEDISABLED*')))
        self.assertIsNone(self.h.lookup(Symbol('*EL:COLLECTMEMO*')))
        self.assertIsNone(self.h.lookup(Symbol('*EL:NETWORKMEMO*')))
        self.h.set(Symbol('*EL:COLLECTMEMO*'), [field('cold-created', True)])
        return [field('wires', [[field('id', 'W1')], [field('id', 'W2')]]),
                field('blocks', [[field('id', 'D0')]]), field('signature', 'cold-source')]

    def network(self, snapshot, cfg, panel):
        self.calls.append(('network', panel))
        return [field('snapshot', snapshot), field('wire-ids', ['W1', 'W2']), field('devices', ['D0'])]

    def split(self, network, cfg):
        self.calls.append(('split',))
        return [field('snapshot', self.get('snapshot', network)), field('issues', None),
                field('circuits', [[field('seed-key', ['W1', Symbol('START')]), field('circuit-number', 'ZE1'),
                                    field('devices', ['D0']), field('wires', ['W1', 'W2'])]])]

    def assert_business_preserved(self):
        self.assertIs(self.h.lookup(Symbol('*EL:RESULT*')), self.business_result)
        self.assertIs(self.h.lookup(Symbol('*EL:DEVICERESULT*')), self.device_result)

    def test_root_handles_preserve_pick_order_and_empty_case(self):
        cfg = [field('circuit-starts', self.starts)]
        self.assertEqual(self.call('EL:ColdRootHandles', cfg), 'W2,W1')
        self.assertEqual(self.call('EL:ColdRootHandles', None), '')

    def test_bounds_audit_matching_different_and_missing(self):
        self.assertEqual(self.get('checked', self.call('EL:ColdBoundsAudit', self.samples)), 1)
        self.assertEqual(self.get('different', self.call('EL:ColdBoundsAudit', self.samples)), 0)
        self.samples += [['D0', [1.0, 2.0, 0.0], [3.0, 4.01, 0.0]],
                         ['MISSING', [0.0, 0.0, 0.0], [1.0, 1.0, 0.0]]]
        audit = self.call('EL:ColdBoundsAudit', self.samples)
        self.assertEqual([self.get(key, audit) for key in ('checked', 'missing', 'different')], [3, 1, 1])
        empty = self.call('EL:ColdBoundsAudit', None)
        self.assertEqual([self.get(key, empty) for key in ('checked', 'missing', 'different')], [0, 0, 0])

    def test_legacy_disables_and_restores_all_result_caches(self):
        keys = ('*EL:CollectMemo*', '*EL:NetworkMemo*', '*EL:RecognitionContacts*',
                '*EL:StableSnapshotMemo*', '*EL:StoreReadCache*', '*EL:NetworkReuseDisabled*')
        saved = {}
        for name in keys:
            key = Symbol(name.upper())
            saved[key] = ['previous-value', name]
            self.h.set(key, saved[key])

        def recognize(cfg, panel):
            self.assertEqual(panel, 'P0')
            for name in keys[:-1]:
                self.assertIsNone(self.h.lookup(Symbol(name.upper())), name)
                self.h.set(Symbol(name.upper()), ['temporary-cold-value'])
            self.assertTrue(self.h.lookup(Symbol('*EL:NETWORKREUSEDISABLED*')))
            return ['readonly-result']
        self.h.builtins['EL:RECOGNIZEFIXED'] = recognize
        self.assertEqual(self.call('EL:ColdLegacy', self.base_cfg, 'P0'), ['readonly-result'])
        for key, value in saved.items():
            self.assertIs(self.h.lookup(key), value, key)
        self.assert_business_preserved()

    def test_legacy_scope_restores_caches_after_exception(self):
        saved = ['previous-collect-memo']
        self.h.set(Symbol('*EL:COLLECTMEMO*'), saved)
        def fail(cfg, panel):
            self.assertIsNone(self.h.lookup(Symbol('*EL:COLLECTMEMO*')))
            self.h.set(Symbol('*EL:COLLECTMEMO*'), ['temporary'])
            raise RuntimeError('native-read-failed')
        self.h.builtins['EL:RECOGNIZEFIXED'] = fail
        with self.assertRaisesRegex(RuntimeError, 'native-read-failed'):
            self.call('EL:ColdLegacy', self.base_cfg, 'P0')
        self.assertIs(self.h.lookup(Symbol('*EL:COLLECTMEMO*')), saved)
        self.assert_business_preserved()

    def test_cancelled_panel_does_not_load_select_or_recognize(self):
        self.panel_pick = None
        self.call('EL:ColdRun')
        self.assertEqual([row[0] for row in self.calls], ['pick-panel'])
        self.assertEqual(self.written, [])
        self.assert_business_preserved()

    def test_cancelled_starts_does_not_load_select_or_recognize(self):
        self.pick_starts = False
        self.call('EL:ColdRun')
        self.assertEqual([row[0] for row in self.calls], ['pick-panel', 'pick-starts'])
        self.assertEqual(self.written, [])
        self.assert_business_preserved()

    def test_default_prototype_loads_once_uses_ordered_roots_and_keeps_business_result(self):
        self.call('EL:ColdRun')
        kinds = [row[0] for row in self.calls]
        self.assertEqual(kinds.count('command'), 1)
        self.assertEqual(kinds.count('native'), 1)
        self.assertNotIn('collect', kinds)
        self.assertNotIn('network', kinds)
        self.assertNotIn('split', kinds)
        native = next(row[1] for row in self.calls if row[0] == 'native')
        self.assertEqual(len(native), 7)
        self.assertEqual(native[0], ['P0', 'W1', 'W2', 'D0'])
        self.assertEqual(native[1:6], ('P0', 'W2,W1', 0.01, 2000.0, 0.1))
        self.assertTrue(native[6].endswith('.json'))
        self.assertEqual(len(self.written), 1)
        path, report = self.written[0]
        self.assertTrue(path.endswith('.eld'))
        self.assertEqual(self.get('status', report), Symbol('PROTOTYPE-COARSE-ONLY'))
        self.assertIsNone(self.get('complete-native-recognition', report))
        self.assertEqual(self.get('target-achieved', report), Symbol('UNVERIFIED'))
        self.assertIsNone(self.get('legacy', report))
        self.assertEqual(self.get('mode', report), 'Prototype')
        self.assertEqual(self.get('checked', self.get('bounds-audit', report)), 1)
        self.assertTrue(any(name == 'COLD_PROBE76' for name, _ in self.logged))
        self.assertEqual([row[1] for row in self.calls if row[0] == 'perf'],
                         ['COLD_NATIVE_LOAD', 'COLD_NATIVE_PROBE'])
        registry = self.h.lookup(Symbol('*EL:COLDREPORTS*'))
        self.assertEqual(self.call('EL:Get', self.owner, registry), [native[6], path])
        self.assert_business_preserved()

    def test_already_loaded_native_runs_fresh_each_time_without_loading_again(self):
        self.ready = True
        self.call('EL:ColdRun')
        self.call('EL:ColdRun')
        kinds = [row[0] for row in self.calls]
        self.assertNotIn('command', kinds)
        self.assertEqual(kinds.count('selection'), 2)
        self.assertEqual(kinds.count('native'), 2)
        self.assertGreaterEqual(kinds.count('handshake'), 2)
        self.assertTrue(all(len(row[1]) == 7 for row in self.calls if row[0] == 'native'))
        self.assertEqual(len(self.written), 2)
        self.assert_business_preserved()

    def test_both_executes_real_full_legacy_composition_without_writes_or_preview(self):
        self.mode = 'Both'
        old_memo = ['previous-business-collect']
        old_network = ['previous-business-network']
        self.h.set(Symbol('*EL:COLLECTMEMO*'), old_memo)
        self.h.set(Symbol('*EL:NETWORKMEMO*'), old_network)
        self.call('EL:ColdRun')
        kinds = [row[0] for row in self.calls]
        self.assertEqual([kind for kind in kinds if kind in {'native', 'collect', 'network', 'split'}],
                         ['native', 'collect', 'network', 'split'])
        report = self.written[0][1]
        legacy = self.get('legacy', report)
        self.assertEqual(self.get('status', legacy), Symbol('LEGACY-FULL-READONLY'))
        self.assertEqual(self.get('circuits', legacy), 1)
        rows = self.get('circuits', self.get('result', legacy))
        self.assertEqual(self.get('circuit-number', rows[0]), 'ZE1')
        self.assertEqual(self.get('devices', rows[0]), ['D0'])
        self.assertEqual(self.get('wires', rows[0]), ['W1', 'W2'])
        self.assertGreaterEqual(self.get('legacy-full-ms', report), 0)
        self.assertIs(self.h.lookup(Symbol('*EL:COLLECTMEMO*')), old_memo)
        self.assertIs(self.h.lookup(Symbol('*EL:NETWORKMEMO*')), old_network)
        self.assert_business_preserved()

    def assert_stopped_before_selection(self):
        kinds = [row[0] for row in self.calls]
        self.assertNotIn('selection', kinds)
        self.assertNotIn('native', kinds)
        self.assertNotIn('collect', kinds)
        self.assertNotIn('network', kinds)
        self.assertNotIn('split', kinds)
        self.assertEqual(self.written, [])
        self.assert_business_preserved()

    def test_nil_atom_list_cannot_skip_native_load(self):
        # Real atoms-family can return (nil), which is truthy as a list.
        self.atom_result = [None]
        self.assertTrue(truth(self.atom_result))
        self.call('EL:ColdLoad')
        self.assertEqual([row[0] for row in self.calls].count('command'), 1)
        self.assertEqual([row[0] for row in self.calls].count('handshake'), 2)
        self.assertNotIn('native', [row[0] for row in self.calls])
        names = [name for name, _ in self.logged]
        self.assertEqual(names, ['COLD_NATIVE_HANDSHAKE', 'COLD_NATIVE_LOAD_BEGIN',
                                 'COLD_NATIVE_LOAD_RETURNED', 'COLD_NATIVE_HANDSHAKE'])
        first, last = self.logged[0][1], self.logged[-1][1]
        self.assertFalse(truth(self.get('ready', first)))
        self.assertIn('no function definition', self.get('error', first))
        self.assertTrue(truth(self.get('ready', last)))
        self.assertEqual(self.get('response', last), self.handshake_response)
        self.assertIsNone(self.get('error', last))
        self.assert_business_preserved()

    def test_same_name_variable_without_callable_still_loads_native(self):
        self.atom_result = ['ELNETCOLD76']
        self.h.set(Symbol('ELNETCOLD76'), ['variable-only-not-a-function'])
        self.call('EL:ColdLoad')
        self.assertEqual([row[0] for row in self.calls].count('command'), 1)
        self.assertEqual([row[0] for row in self.calls].count('handshake'), 2)
        self.assertNotIn('native', [row[0] for row in self.calls])

    def test_handshake_is_exact_readonly_call_without_selection_or_recognition(self):
        self.ready = True
        for name in ('ENTGET', 'HANDENT', 'NAMEDOBJDICT', 'EL:ENTITYBOUNDS',
                     'EL:PRESETSELECTION', 'EL:SIMPLECOLLECT', 'EL:SIMPLENETWORK', 'EL:SPLITNETWORK'):
            self.h.builtins[name] = self.forbidden(name)
        self.assertTrue(truth(self.call('EL:ColdNativeReady')))
        self.assertEqual(self.calls, [('handshake', ('EL_NET_COLD_PING_V1',))])
        self.assertEqual([name for name, _ in self.logged], ['COLD_NATIVE_HANDSHAKE'])
        self.assertEqual(self.written, [])
        self.assert_business_preserved()

    def test_single_element_handshake_envelope_is_ready_without_loading(self):
        self.ready = True
        self.handshake_response = ['EL_NET_COLD_PROBE_V1/0.1.76']
        self.call('EL:ColdLoad')
        self.assertNotIn('command', [row[0] for row in self.calls])
        self.assertNotIn('native', [row[0] for row in self.calls])
        self.assertTrue(all(truth(self.get('ready', detail))
                            for name, detail in self.logged if name == 'COLD_NATIVE_HANDSHAKE'))
        self.assert_business_preserved()

    def test_wrong_handshake_token_and_types_are_rejected(self):
        self.ready = True
        for response in ('EL_NET_COLD_PROBE_V1/0.1.75', 'EL_NET_COLD_PROBE_V1/0.1.760',
                         ['EL_NET_COLD_PROBE_V1/0.1.75'],
                         ['EL_NET_COLD_PROBE_V1/0.1.76', 'extra'],
                         [['EL_NET_COLD_PROBE_V1/0.1.76']],
                         [Symbol('EL_NET_COLD_PROBE_V1/0.1.76')],
                         Symbol('EL_NET_COLD_PROBE_V1/0.1.76'), None, True, 76):
            with self.subTest(response=response):
                self.handshake_response = response
                self.assertFalse(truth(self.call('EL:ColdNativeReady')))
                detail = self.logged[-1][1]
                self.assertFalse(truth(self.get('ready', detail)))
                self.assertEqual(self.get('response', detail), response)
                self.assertIsNone(self.get('error', detail))
        self.assertNotIn('command', [row[0] for row in self.calls])
        self.assertNotIn('native', [row[0] for row in self.calls])
        self.assertEqual(self.written, [])
        self.assert_business_preserved()

    def test_netload_returned_without_registration_stops_before_collection(self):
        self.command_loads = False
        with self.assertRaisesRegex(RuntimeError, '握手失败'):
            self.call('EL:ColdRun')
        self.assert_stopped_before_selection()
        names = [name for name, _ in self.logged]
        self.assertIn('COLD_NATIVE_LOAD_RETURNED', names)
        self.assertEqual(names.count('COLD_NATIVE_HANDSHAKE'), 2)
        self.assertTrue(all(not truth(self.get('ready', detail))
                            for name, detail in self.logged if name == 'COLD_NATIVE_HANDSHAKE'))

    def test_wrong_version_after_netload_stops_before_collection(self):
        self.handshake_response = 'EL_NET_COLD_PROBE_V1/0.1.75'
        with self.assertRaisesRegex(RuntimeError, '握手失败'):
            self.call('EL:ColdRun')
        self.assert_stopped_before_selection()
        self.assertEqual([row[0] for row in self.calls].count('command'), 1)
        detail = [detail for name, detail in self.logged if name == 'COLD_NATIVE_HANDSHAKE'][-1]
        self.assertFalse(truth(self.get('ready', detail)))
        self.assertEqual(self.get('response', detail), self.handshake_response)

    def test_cancelled_native_load_stops_before_collection(self):
        self.command_error = 'Function cancelled'
        with self.assertRaisesRegex(RuntimeError, 'Function cancelled'):
            self.call('EL:ColdRun')
        self.assert_stopped_before_selection()
        names = [name for name, _ in self.logged]
        self.assertIn('COLD_NATIVE_LOAD_BEGIN', names)
        self.assertNotIn('COLD_NATIVE_LOAD_RETURNED', names)

    def test_missing_dll_stops_before_netload_and_collection(self):
        self.library_found = False
        with self.assertRaisesRegex(RuntimeError, '缺少只读 .NET 原型 DLL'):
            self.call('EL:ColdRun')
        self.assert_stopped_before_selection()
        self.assertNotIn('command', [row[0] for row in self.calls])
        self.assertNotIn('COLD_NATIVE_LOAD_BEGIN', [name for name, _ in self.logged])

    def test_single_payload_envelope_is_unwrapped_for_bounds_audit(self):
        original = self.main_native
        self.main_native = lambda *args: [original(*args)]
        self.call('EL:ColdRun')
        self.assertEqual([row[0] for row in self.calls].count('native'), 1)
        report = self.written[0][1]
        self.assertEqual(self.get('status', report), Symbol('PROTOTYPE-COARSE-ONLY'))
        self.assertEqual(self.get('checked', self.get('bounds-audit', report)), 1)
        self.assertEqual(self.get('different', self.get('bounds-audit', report)), 0)
        self.assertNotIn('COLD_NATIVE_PROBE_FAILED', [name for name, _ in self.logged])
        self.assert_business_preserved()

    def test_multiple_payload_envelopes_are_rejected_before_audit_and_legacy(self):
        self.mode = 'Both'
        original = self.main_native
        self.main_native = lambda *args: [[original(*args)]]
        with self.assertRaisesRegex(RuntimeError, '只读 .NET 原型失败'):
            self.call('EL:ColdRun')
        self.assertEqual(self.written, [])
        self.assertNotIn('collect', [row[0] for row in self.calls])
        self.assertIn('COLD_NATIVE_PROBE_FAILED', [name for name, _ in self.logged])
        self.assert_business_preserved()

    def test_command_uses_safe_owned_timeline_name_and_preserves_outer_run(self):
        self.h.builtins.update({
            'EL:ENSUREROOT': lambda: True,
            'EL:MEASUREDCATCH': lambda fn, args: None,
            'VL-MKDIR': lambda path: True,
            'FINDFILE': lambda path: None,
        })
        self.h.set(Symbol('*EL:MONITORSTAMP*'), '20261022.120000')
        for owner, initial, expected in (
                (True, 'ELSTAT/ELTRACE/ELPOWER', 'ELCOLD76'),
                (None, 'EXTERNAL-PANEL-RUN', 'EXTERNAL-PANEL-RUN')):
            with self.subTest(owner=owner):
                finished, written = [], []

                def log_start():
                    self.h.set(Symbol('*EL:PERFLOGOWNER*'), owner)
                    self.h.set(Symbol('*EL:PERFCOMMAND*'), initial)

                def monitor_write(path, summary):
                    written.append((path, summary))
                    return True

                def log_finish(status):
                    command = self.h.lookup(Symbol('*EL:PERFCOMMAND*'))
                    finished.append((status, command))
                    summary = [field('command', command)]
                    self.call('EL:MonitorSave', summary, None)

                self.h.builtins['EL:LOGSTART'] = log_start
                self.h.builtins['EL:LOGFINISH'] = log_finish
                self.h.builtins['EL:MONITORWRITE'] = monitor_write
                self.call('C:ELCOLD76')
                self.assertEqual(finished, [(Symbol('COLD-PROBE-FINISHED'), expected)])
                self.assertEqual(len(written), 1)
                path, summary = written[0]
                self.assertEqual(PureWindowsPath(path).name,
                                 'ELMONITOR-20261022.120000-' + expected + '.md')
                self.assertEqual(self.get('command', summary), expected)
                self.assertEqual(self.h.lookup(Symbol('*EL:PERFCOMMAND*')), expected)
                self.assertEqual(self.h.lookup(Symbol('*EL:MONITORPATH*')), path)
                self.assertNotIn('ELSTAT/ELTRACE/ELPOWER', path)
                self.assert_business_preserved()

    def test_source_change_rejects_report_before_legacy(self):
        self.mode = 'Both'
        original = self.main_native
        def changed(*args):
            payload = original(*args)
            self.h.set(Symbol('*EL:FRESHEPOCH*'), self.epoch + 1)
            return payload
        self.main_native = changed
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_CHANGED'):
            self.call('EL:ColdRun')
        self.assertEqual(self.written, [])
        self.assertNotIn('collect', [row[0] for row in self.calls])
        self.assert_business_preserved()

    def test_invalid_native_payload_does_not_enter_legacy_or_publish_report(self):
        self.mode = 'Both'
        self.main_native = lambda *args: ['{"status":"FAILED"}', []]
        with self.assertRaisesRegex(RuntimeError, '只读 .NET 原型失败'):
            self.call('EL:ColdRun')
        self.assertEqual(self.written, [])
        self.assertNotIn('collect', [row[0] for row in self.calls])
        self.assertIn('COLD_NATIVE_PROBE_FAILED', [name for name, _ in self.logged])
        self.assert_business_preserved()

    def test_native_exception_retains_registered_diagnostic_paths(self):
        def fail(*args):
            self.assertEqual(len(self.call('EL:Get', self.owner,
                                           self.h.lookup(Symbol('*EL:COLDREPORTS*')))), 2)
            raise RuntimeError('native-prototype-read-error')
        self.main_native = fail
        with self.assertRaisesRegex(RuntimeError, 'native-prototype-read-error'):
            self.call('EL:ColdRun')
        paths = self.call('EL:Get', self.owner, self.h.lookup(Symbol('*EL:COLDREPORTS*')))
        self.assertTrue(paths[0].endswith('.json'))
        self.assertTrue(paths[1].endswith('.eld'))
        self.assertEqual(self.written, [])
        self.assertNotIn('collect', [row[0] for row in self.calls])
        self.assert_business_preserved()

    def test_change_during_full_legacy_rejects_comparison_and_restores_cache(self):
        self.mode = 'Both'
        original = self.h.builtins['EL:SPLITNETWORK']
        old_memo = ['previous-business-collect']
        self.h.set(Symbol('*EL:COLLECTMEMO*'), old_memo)
        def changed(network, cfg):
            result = original(network, cfg)
            self.h.set(Symbol('*EL:FRESHEPOCH*'), self.epoch + 1)
            return result
        self.h.builtins['EL:SPLITNETWORK'] = changed
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_CHANGED'):
            self.call('EL:ColdRun')
        self.assertIn('split', [row[0] for row in self.calls])
        self.assertEqual(self.written, [])
        self.assertIs(self.h.lookup(Symbol('*EL:COLLECTMEMO*')), old_memo)
        self.assert_business_preserved()


if __name__ == '__main__':
    unittest.main()
