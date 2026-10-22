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
        # Date: 2026-10-22. Keep the actual PerfCall body, including its APPLY.
        self.h.functions[Symbol('TEST:REALPERFCALL')] = self.h.functions[Symbol('EL:PERFCALL')]
        self.indirect_calls = []
        self.flow_trace = []
        self.calls = []
        self.written = []
        self.logged = []
        self.ready = False
        self.handshake_response = 'EL_NET_COLD_PROBE_V1/0.1.80'
        self.atom_result = [None]
        self.library_found = True
        self.command_loads = True
        self.command_error = None
        self.main_native = self.native_main
        self.mode = 'Prototype'  # Explicit mode for candidate-only fixtures; Enter is covered below.
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
            'APPLY': self.native_safe_apply,
            'VL-CATCH-ALL-APPLY': self.native_safe_catch,
            'FINDFILE': lambda path: path if self.library_found else None,
            'COMMAND': self.command,
            'HANDENT': lambda handle: handle if handle in {'P0', 'D0'} else None,
            'ENTGET': lambda entity: [Pair(0, 'INSERT'), Pair(5, 'P0'), Pair(8, 'PANEL')],
            'SSLENGTH': lambda selection: len(selection),
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
            'ELNETCOLD80': self.native,
            'EL:ENTITYBOUNDS': lambda entity: self.bounds.get(entity),
            'EL:WRITEDATA': self.write_data,
            'EL:LOGEVENT': self.log_event,
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
        self.flow_trace.append(('command', args[0]))
        self.calls.append(('command', args))
        self.assertEqual(args[0], '_.NETLOAD')
        self.assertTrue(args[1].endswith('native/EmergencyLighting.ColdRecognition80.dll'))
        if self.command_error:
            raise RuntimeError(self.command_error)
        if self.command_loads:
            self.ready = True

    def indirect_target(self, kind, fn):
        self.indirect_calls.append((kind, fn))
        self.flow_trace.append((kind, str(fn)))
        # Date: 2026-10-22. Model the observed target-resolution failure before
        # the catch body. Also reject a registered target as a conservative case;
        # this fixture is not a claim about every native external function.
        if fn == Symbol('ELNETCOLD80'):
            raise RuntimeError('函数错误: ELNETCOLD80')

    def native_safe_apply(self, fn, args):
        self.indirect_target('apply', fn)
        return self.h.call(fn, seq(args))

    def native_safe_catch(self, fn, args):
        self.indirect_target('catch', fn)
        return self.h.catch(fn, args)

    def log_event(self, name, detail):
        self.flow_trace.append(('log', name))
        self.logged.append((name, detail))

    def perf_call(self, stage, fn, args):
        self.calls.append(('perf', stage))
        if stage == 'COLD_NATIVE_LOAD':
            self.assertEqual(fn, Symbol('EL:COLDLOAD'))
        elif stage == 'COLD_NATIVE_PROBE':
            self.assertEqual(fn, Symbol('EL:COLDNATIVEINVOKE'))
        # Execute the production body so a direct external entry hidden behind
        # PerfCall cannot pass through the old shortcut fixture.
        return self.call('TEST:RealPerfCall', stage, fn, args)

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
            self.flow_trace.append(('native', 'handshake'))
            self.calls.append(('handshake', args))
            self.assertEqual(args, ('EL_NET_COLD_PING_V1',))
            if not self.ready:
                raise RuntimeError('no function definition: ELNETCOLD80')
            return self.handshake_response
        self.flow_trace.append(('native', 'main'))
        self.calls.append(('native', args))
        self.assertEqual(len(args), 7)
        if not self.ready:
            raise RuntimeError('no function definition: ELNETCOLD80')
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

    def enable_real_timing(self):
        for name in ('EL:PERFBEGIN', 'EL:PERFEND'):
            self.h.builtins.pop(name, None)
        values = {'*EL:PERFACTIVE*': True, '*EL:PERFDETAIL*': None,
                  '*EL:PERFWAITDEPTH*': 0, '*EL:PERFWAITMS*': 0,
                  '*EL:PERFSERIAL*': 0, '*EL:PERFPENDING*': None,
                  '*EL:PERFSTAGES*': None, '*EL:MONITORROWS*': None}
        for name, value in values.items():
            self.h.set(Symbol(name), value)

    def test_fixture_reproduces_external_target_failure_before_catch(self):
        # The previous implementation passed the external symbol straight to
        # vl-catch-all-apply and later via PerfCall's APPLY. Neither may bypass
        # the dispatch restriction even if the external function is registered.
        for ready in (False, True):
            with self.subTest(ready=ready):
                self.ready = ready
                for entry in ('APPLY', 'VL-CATCH-ALL-APPLY'):
                    with self.assertRaisesRegex(RuntimeError, '函数错误: ELNETCOLD80'):
                        self.call(entry, Symbol('ELNETCOLD80'), ['EL_NET_COLD_PING_V1'])
                with self.assertRaisesRegex(RuntimeError, '函数错误: ELNETCOLD80'):
                    self.call('TEST:RealPerfCall', 'COLD_NATIVE_PROBE', Symbol('ELNETCOLD80'),
                              [['D0'], 'P0', 'W2,W1', 0.01, 2000.0, 0.1, 'probe.json'])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.logged, [])
        self.assertEqual(self.written, [])

    def test_direct_native_wrappers_preserve_protocol_and_all_seven_arguments(self):
        self.ready = True
        self.assertEqual(self.call('EL:ColdNativePing'), self.handshake_response)
        arguments = [['P0', 'W1', 'D0'], 'P0', 'W2,W1', 0.01, 2000.0, 0.1, 'probe.json']
        self.assertEqual(self.call('EL:ColdNativeInvoke', *arguments), self.native_main(*arguments))
        self.assertEqual(self.calls, [('handshake', ('EL_NET_COLD_PING_V1',)),
                                     ('native', tuple(arguments))])
        self.assertEqual(self.indirect_calls, [])
        self.assert_business_preserved()

    def test_unregistered_native_loads_after_caught_ping_then_uses_lisp_dispatch(self):
        self.call('EL:ColdRun')
        self.assertEqual(self.indirect_calls,
                         [('apply', Symbol('EL:COLDLOAD')),
                          ('catch', Symbol('EL:COLDNATIVEPING')),
                          ('catch', Symbol('EL:COLDNATIVEPING')),
                          ('catch', Symbol('EL:PERFCALL')),
                          ('apply', Symbol('EL:COLDNATIVEINVOKE'))])
        first_ping = self.flow_trace.index(('catch', 'EL:COLDNATIVEPING'))
        netload = self.flow_trace.index(('command', '_.NETLOAD'))
        main = self.flow_trace.index(('native', 'main'))
        self.assertLess(self.flow_trace.index(('log', 'COLD_NATIVE_HANDSHAKE_BEGIN')), first_ping)
        self.assertLess(first_ping, netload)
        self.assertLess(netload, self.flow_trace.index(('log', 'COLD_NATIVE_PROBE_BEGIN')))
        self.assertLess(self.flow_trace.index(('log', 'COLD_NATIVE_PROBE_BEGIN')), main)
        self.assertEqual([name for name, _ in self.logged].count('COLD_NATIVE_HANDSHAKE_BEGIN'), 2)
        self.assertNotIn('COLD_NATIVE_PROBE_FAILED', [name for name, _ in self.logged])
        self.assert_business_preserved()

    def test_default_detail_off_records_real_load_and_probe_frames(self):
        self.enable_real_timing()
        original = self.main_native

        def check_frame(*args):
            pending = self.h.lookup(Symbol('*EL:PERFPENDING*'))
            self.assertEqual(len(pending), 1)
            self.assertEqual(self.get('stage', pending[0]), 'COLD_NATIVE_PROBE')
            self.assertEqual(self.get('label', pending[0]), 'EL:COLDNATIVEINVOKE')
            return original(*args)

        self.main_native = check_frame
        self.call('EL:ColdRun')
        stages = self.h.lookup(Symbol('*EL:PERFSTAGES*'))
        for stage in ('COLD_NATIVE_LOAD', 'COLD_NATIVE_PROBE'):
            row = self.call('EL:Get', stage, stages)
            self.assertEqual(self.get('calls', row), 1)
            self.assertEqual(self.get('interrupted', row), 0)
            self.assertGreater(self.get('program-ms', row), 0)
        self.assertIsNone(self.h.lookup(Symbol('*EL:PERFPENDING*')))
        self.assertIsNone(self.h.lookup(Symbol('*EL:PERFDETAIL*')))
        self.assert_business_preserved()

    def test_failed_load_records_interrupted_frame_without_detail(self):
        self.enable_real_timing()
        self.command_loads = False
        outcome = self.call('EL:MeasuredCatch', Symbol('EL:COLDRUN'), None)
        self.assertTrue(truth(self.call('VL-CATCH-ALL-ERROR-P', outcome)))
        self.assertIn('握手失败', self.call('VL-CATCH-ALL-ERROR-MESSAGE', outcome))
        stages = self.h.lookup(Symbol('*EL:PERFSTAGES*'))
        load = self.call('EL:Get', 'COLD_NATIVE_LOAD', stages)
        self.assertEqual(self.get('calls', load), 1)
        self.assertEqual(self.get('interrupted', load), 1)
        self.assertIsNone(self.call('EL:Get', 'COLD_NATIVE_PROBE', stages))
        self.assertIsNone(self.h.lookup(Symbol('*EL:PERFPENDING*')))
        self.assert_stopped_before_selection()

    def test_native_error_is_logged_and_unwinds_only_probe_timing_frame(self):
        self.enable_real_timing()
        self.mode = 'Both'
        outer = self.call('EL:PerfBegin', 'OUTER')
        self.h.builtins['EL:ENTITYBOUNDS'] = self.forbidden('bounds-audit-after-native-error')

        def fail(*args):
            raise RuntimeError('native-prototype-read-error')

        self.main_native = fail
        with self.assertRaisesRegex(RuntimeError, '只读 .NET 原型调用失败：native-prototype-read-error'):
            self.call('EL:ColdRun')
        stages = self.h.lookup(Symbol('*EL:PERFSTAGES*'))
        self.assertEqual(self.get('interrupted', self.call('EL:Get', 'COLD_NATIVE_LOAD', stages)), 0)
        self.assertEqual(self.get('interrupted', self.call('EL:Get', 'COLD_NATIVE_PROBE', stages)), 1)
        self.assertEqual(self.h.lookup(Symbol('*EL:PERFPENDING*')), [outer])
        failed = [detail for name, detail in self.logged if name == 'COLD_NATIVE_PROBE_FAILED']
        self.assertEqual(len(failed), 1)
        self.assertEqual(self.get('error', failed[0]), 'native-prototype-read-error')
        paths = self.call('EL:Get', self.owner, self.h.lookup(Symbol('*EL:COLDREPORTS*')))
        self.assertEqual(self.get('report', failed[0]), paths[0])
        self.assertEqual(self.written, [])
        self.assertNotIn('collect', [row[0] for row in self.calls])
        self.assertNotIn('COLD_PROBE80', [name for name, _ in self.logged])
        self.assert_business_preserved()

    def test_checkpoints_report_inputs_and_explicit_coarse_completion(self):
        self.call('EL:ColdRun')
        checkpoints = [detail for name, detail in self.logged if name == 'COLD_CHECKPOINT']
        phases = [self.get('phase', row) for row in checkpoints]
        self.assertEqual(phases, ['MODE', 'PICK_PANEL', 'LOAD_CONFIG', 'PRESET_READY',
                                 'PICK_STARTS', 'NATIVE_LOAD', 'SELECTION', 'NATIVE_PROBE',
                                 'PAYLOAD_VALIDATE', 'BOUNDS_AUDIT', 'SOURCE_GUARD',
                                 'FINAL_SOURCE_GUARD', 'REPORT_WRITE', 'FINISHED'])
        inputs = self.get('details', checkpoints[7])
        self.assertEqual(self.get('selection-count', inputs), 4)
        context = self.h.lookup(Symbol('*EL:COLDCONTEXT*'))
        self.assertEqual(self.get('diagnostic-revision', context), '2026-10-22-logs1')
        self.assertEqual(self.get('panel', context), 'P0')
        self.assertEqual(self.get('roots', context), 'W2,W1')
        self.assertEqual(self.get('root-count', context), 2)
        self.assertEqual(self.get('mode', context), 'Prototype')
        self.assertIsNone(self.get('legacy-executed', context))
        self.assertIsNone(self.get('complete-native-recognition', context))
        self.assertTrue(truth(self.get('bounds-audit-passed', context)))
        self.assert_business_preserved()

    def test_early_failure_clears_only_current_drawing_previous_report_paths(self):
        other_paths = ['other.json', 'other.eld']
        self.h.set(Symbol('*EL:COLDREPORTS*'), [Pair('other-drawing', other_paths)])
        self.call('EL:ColdRun')
        registry = self.h.lookup(Symbol('*EL:COLDREPORTS*'))
        self.assertTrue(self.call('EL:Get', self.owner, registry))
        self.ready = False
        self.library_found = False
        with self.assertRaisesRegex(RuntimeError, '缺少只读 .NET 原型 DLL'):
            self.call('EL:ColdRun')
        registry = self.h.lookup(Symbol('*EL:COLDREPORTS*'))
        self.assertIsNone(self.call('EL:Get', self.owner, registry))
        self.assertEqual(self.call('EL:Get', 'other-drawing', registry), other_paths)
        self.assert_business_preserved()

    def test_failure_context_identifies_native_dispatch_without_prior_run_data(self):
        self.call('EL:ColdRun')
        self.main_native = lambda *args: (_ for _ in ()).throw(RuntimeError('bridge-broken'))
        with self.assertRaisesRegex(RuntimeError, 'bridge-broken'):
            self.call('EL:ColdRun')
        self.call('EL:ColdFailure', 'bridge-broken')
        event, detail = self.logged[-1]
        self.assertEqual(event, 'COLD_FAILURE')
        context = self.get('context', detail)
        self.assertEqual(self.get('phase', context), 'NATIVE_PROBE')
        self.assertEqual(self.get('selection-count', context), 4)
        self.assertEqual(self.get('roots', context), 'W2,W1')
        self.assertIsNone(self.get('native-return', context))
        self.assertIsNone(self.get('bounds-audit', context))
        self.assertEqual(self.get('error', detail), 'bridge-broken')
        self.assert_business_preserved()

    def test_bounds_samples_keep_exact_differences_and_limit_log_volume(self):
        samples = self.samples * 17 + [['MISSING', [0, 0, 0], [1, 1, 0]]]
        self.bounds['D0'] = [[1.0, 2.0, 0.0], [3.0, 4.01, 0.0]]
        audit = self.call('EL:ColdBoundsAudit', samples)
        rows = [detail for name, detail in self.logged if name == 'COLD_BOUNDS_SAMPLE']
        self.assertEqual(len(rows), 16)
        self.assertEqual(self.get('different', audit), 17)
        self.assertEqual(self.get('missing', audit), 1)
        self.assertEqual(self.get('verdict', rows[0]), Symbol('DIFFERENT'))
        self.assertEqual(self.get('expected', rows[0]), self.samples[0][1:])
        self.assertEqual(self.get('actual', rows[0]), self.bounds['D0'])
        self.assert_business_preserved()

    def test_native_return_log_is_bounded_and_preserves_error_message(self):
        text = '{"status":"ERROR","errors":[{"message":"read-failed"}],"padding":"' + 'x' * 5000 + '"}'
        self.main_native = lambda *args: [text, []]
        with self.assertRaisesRegex(RuntimeError, '只读 .NET 原型失败'):
            self.call('EL:ColdRun')
        row = next(detail for name, detail in self.logged if name == 'COLD_NATIVE_RETURN')
        self.assertEqual(self.get('native-status', row), 'ERROR')
        self.assertEqual(self.get('json-length', row), len(text))
        self.assertEqual(len(self.get('json-prefix', row)), 4096)
        self.assertIn('read-failed', self.get('json-prefix', row))
        self.assertTrue(truth(self.get('json-truncated', row)))
        self.assertEqual(self.get('phase', self.h.lookup(Symbol('*EL:COLDCONTEXT*'))), 'PAYLOAD_VALIDATE')
        self.assert_business_preserved()

    def test_bounds_mismatch_is_explicit_without_changing_recognition_policy(self):
        self.bounds['D0'] = None
        self.call('EL:ColdRun')
        report = self.written[0][1]
        self.assertIsNone(self.get('bounds-audit-passed', report))
        self.assertEqual(self.get('missing', self.get('bounds-audit', report)), 1)
        self.assertEqual(self.get('status', report), Symbol('PROTOTYPE-COARSE-ONLY'))
        self.assert_business_preserved()

    def test_legacy_exception_retains_distinct_stage_and_diagnostic_paths(self):
        self.mode = 'Both'
        self.h.builtins['EL:RECOGNIZEFIXED'] = lambda *args: (_ for _ in ()).throw(RuntimeError('legacy-failed'))
        with self.assertRaisesRegex(RuntimeError, 'legacy-failed'):
            self.call('EL:ColdRun')
        context = self.h.lookup(Symbol('*EL:COLDCONTEXT*'))
        self.assertEqual(self.get('phase', context), 'LEGACY_RECOGNITION')
        self.assertEqual(self.get('mode', context), 'Both')
        self.assertTrue(self.get('native-report', context).endswith('.json'))
        self.assertEqual(self.get('native-status', self.get('native-return', context)), 'PROTOTYPE_COARSE_ONLY')
        self.assertEqual(self.written, [])
        self.assert_business_preserved()

    def test_report_write_failure_retains_stage_without_claiming_completion(self):
        self.h.builtins['EL:WRITEDATA'] = lambda *args: None
        with self.assertRaisesRegex(RuntimeError, '报告写入失败'):
            self.call('EL:ColdRun')
        context = self.h.lookup(Symbol('*EL:COLDCONTEXT*'))
        self.assertEqual(self.get('phase', context), 'REPORT_WRITE')
        self.assertIsNone(self.h.lookup(Symbol('*EL:COLDCOMPLETED*')))
        self.assertNotIn('COLD_PROBE80', [name for name, _ in self.logged])
        self.assert_business_preserved()

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

    def test_explicit_prototype_loads_once_uses_ordered_roots_and_keeps_business_result(self):
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
        self.assertTrue(any(name == 'COLD_PROBE80' for name, _ in self.logged))
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

    def test_enter_defaults_to_both_and_executes_full_legacy_readonly(self):
        prompts = []
        self.h.builtins['GETKWORD'] = lambda prompt: prompts.append(prompt) or None
        self.call('EL:ColdRun')
        self.assertEqual(len(prompts), 1)
        self.assertIn('<Both>', prompts[0])
        self.assertNotIn('<Prototype>', prompts[0])
        kinds = [row[0] for row in self.calls]
        self.assertEqual([kind for kind in kinds if kind in {'native', 'collect', 'network', 'split'}],
                         ['native', 'collect', 'network', 'split'])
        report = self.written[0][1]
        self.assertEqual(self.get('mode', report), 'Both')
        self.assertTrue(truth(self.get('legacy-executed', report)))
        self.assertEqual(self.get('status', self.get('legacy', report)), Symbol('LEGACY-FULL-READONLY'))
        self.assertGreaterEqual(self.get('legacy-full-ms', report), 0)
        self.assertIn('COLD_LEGACY_RETURN', [name for name, _ in self.logged])
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
        self.assertEqual(names, ['COLD_NATIVE_HANDSHAKE_BEGIN', 'COLD_NATIVE_HANDSHAKE',
                                 'COLD_NATIVE_LOAD_BEGIN', 'COLD_NATIVE_LOAD_RETURNED',
                                 'COLD_NATIVE_HANDSHAKE_BEGIN', 'COLD_NATIVE_HANDSHAKE'])
        first, last = [detail for name, detail in self.logged if name == 'COLD_NATIVE_HANDSHAKE']
        self.assertFalse(truth(self.get('ready', first)))
        self.assertIn('no function definition', self.get('error', first))
        self.assertTrue(truth(self.get('ready', last)))
        self.assertEqual(self.get('response', last), self.handshake_response)
        self.assertIsNone(self.get('error', last))
        self.assert_business_preserved()

    def test_same_name_variable_without_callable_still_loads_native(self):
        self.atom_result = ['ELNETCOLD80']
        self.h.set(Symbol('ELNETCOLD80'), ['variable-only-not-a-function'])
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
        self.assertEqual([name for name, _ in self.logged],
                         ['COLD_NATIVE_HANDSHAKE_BEGIN', 'COLD_NATIVE_HANDSHAKE'])
        self.assertEqual(self.written, [])
        self.assert_business_preserved()

    def test_single_element_handshake_envelope_is_ready_without_loading(self):
        self.ready = True
        self.handshake_response = ['EL_NET_COLD_PROBE_V1/0.1.80']
        self.call('EL:ColdLoad')
        self.assertNotIn('command', [row[0] for row in self.calls])
        self.assertNotIn('native', [row[0] for row in self.calls])
        self.assertTrue(all(truth(self.get('ready', detail))
                            for name, detail in self.logged if name == 'COLD_NATIVE_HANDSHAKE'))
        self.assert_business_preserved()

    def test_wrong_handshake_token_and_types_are_rejected(self):
        self.ready = True
        for response in ('EL_NET_COLD_PROBE_V1/0.1.75', 'EL_NET_COLD_PROBE_V1/0.1.78',
                         'EL_NET_COLD_PROBE_V1/0.1.79',
                         'EL_NET_COLD_PROBE_V1/0.1.800',
                         ['EL_NET_COLD_PROBE_V1/0.1.75'],
                         ['EL_NET_COLD_PROBE_V1/0.1.80', 'extra'],
                         [['EL_NET_COLD_PROBE_V1/0.1.80']],
                         [Symbol('EL_NET_COLD_PROBE_V1/0.1.80')],
                         Symbol('EL_NET_COLD_PROBE_V1/0.1.80'), None, True, 77):
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
            'EL:MEASUREDCATCH': lambda fn, args: self.h.set(Symbol('*EL:COLDCOMPLETED*'), True),
            'VL-MKDIR': lambda path: True,
            'FINDFILE': lambda path: None,
        })
        self.h.set(Symbol('*EL:MONITORSTAMP*'), '20261022.120000')
        for owner, initial, expected in (
                (True, 'ELSTAT/ELTRACE/ELPOWER', 'ELCOLD80'),
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
                self.call('C:ELCOLD80')
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

    def test_command_requires_explicit_completed_report_after_nonerror_return(self):
        finished = []
        self.h.builtins.update({
            'EL:ENSUREROOT': lambda: True,
            'EL:LOGSTART': lambda: None,
            'EL:LOGFINISH': lambda status: finished.append(status),
            'EL:LOGFAILURE': lambda message: None,
            # Match output32: validation EXIT did not arrive as a catch error.
            'EL:MEASUREDCATCH': lambda fn, args: None,
        })
        # A prior command's success must not leak into this command.
        self.h.set(Symbol('*EL:COLDCOMPLETED*'), True)
        self.call('C:ELCOLD80')
        self.assertEqual(finished, [Symbol('COLD-PROBE-FAILED')])
        self.assert_business_preserved()

    def test_completion_requires_report_write_and_rejects_native_error(self):
        self.call('EL:ColdRun')
        self.assertTrue(truth(self.h.lookup(Symbol('*EL:COLDCOMPLETED*'))))
        self.main_native = lambda *args: [
            '{"status":"ERROR","errors":[{"message":"SOURCE_CHANGED during the read-only probe."}]}', []]
        with self.assertRaisesRegex(RuntimeError, '只读 .NET 原型失败'):
            self.call('EL:ColdRun')
        self.assertIsNone(self.h.lookup(Symbol('*EL:COLDCOMPLETED*')))
        self.assertEqual(len(self.written), 1)
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
