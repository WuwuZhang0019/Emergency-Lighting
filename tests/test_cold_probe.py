"""Date: 2026-10-22. Status: read-only cold probe bounded LISP regression.

Finite CAD adapters exercise the new command flow and the real RecognizeFixed
composition. They do not prove native CAD timing, .NET cold JIT, or the 3 s target.
"""
import copy
from pathlib import Path
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
            'ATOMS-FAMILY': lambda *args: ['ELNETCOLD75'] if self.ready else None,
            'FINDFILE': lambda path: path,
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
            'ELNETCOLD75': self.native,
            'EL:ENTITYBOUNDS': lambda entity: self.bounds.get(entity),
            'EL:WRITEDATA': self.write_data,
            'EL:LOGEVENT': lambda name, detail: self.logged.append((name, detail)),
            'GETVAR': lambda key: 20261022.1 if key == 'CDATE' else 1000,
            'EL:LOGCALL': lambda name, detail, fn, args: self.h.call(fn, seq(args)),
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
        self.ready = True

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
        self.calls.append(('native', args))
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
        self.assertTrue(any(name == 'COLD_PROBE75' for name, _ in self.logged))
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

    def test_source_change_rejects_report_before_legacy(self):
        self.mode = 'Both'
        original = self.h.builtins['ELNETCOLD75']
        def changed(*args):
            payload = original(*args)
            self.h.set(Symbol('*EL:FRESHEPOCH*'), self.epoch + 1)
            return payload
        self.h.builtins['ELNETCOLD75'] = changed
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_CHANGED'):
            self.call('EL:ColdRun')
        self.assertEqual(self.written, [])
        self.assertNotIn('collect', [row[0] for row in self.calls])
        self.assert_business_preserved()

    def test_invalid_native_payload_does_not_enter_legacy_or_publish_report(self):
        self.mode = 'Both'
        self.h.builtins['ELNETCOLD75'] = lambda *args: ['{"status":"FAILED"}', []]
        with self.assertRaisesRegex(RuntimeError, '只读 .NET 原型失败'):
            self.call('EL:ColdRun')
        self.assertEqual(self.written, [])
        self.assertNotIn('collect', [row[0] for row in self.calls])
        self.assert_business_preserved()

    def test_native_exception_retains_registered_diagnostic_paths(self):
        def fail(*args):
            self.assertEqual(len(self.call('EL:Get', self.owner,
                                           self.h.lookup(Symbol('*EL:COLDREPORTS*')))), 2)
            raise RuntimeError('native-prototype-read-error')
        self.h.builtins['ELNETCOLD75'] = fail
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
