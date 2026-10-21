"""Command-local layer linetype reuse. Date: 2026-10-21.

Status: focused adapter regression; CAD timing and acceptance remain pending.
"""
import unittest

from autolisp_host import Pair, Symbol, truth
import test_simple_flow as simple


class WireLayerCacheTests(unittest.TestCase):
    setUp = simple.SimpleFlowTests.setUp
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    line = simple.SimpleFlowTests.line
    block = simple.SimpleFlowTests.block
    plan = simple.SimpleFlowTests.plan

    def layers(self):
        self.layer_values = {'W': 'Continuous', 'D': 'DASHED'}
        self.reads, self.metrics = [], []
        self.clock = 0
        original = self.h.builtins['TBLSEARCH']

        def table(kind, name):
            if kind != 'LAYER':
                return original(kind, name)
            self.reads.append(name)
            self.clock += 3
            return [Pair(2, name), Pair(6, self.layer_values[name])] if name in self.layer_values else None

        self.h.builtins.update({'TBLSEARCH': table,
                               'GETVAR': lambda key: self.clock if key == 'MILLISECS' else 0,
                               'EL:PERFCOUNT': lambda key, value: self.metrics.append((key, value))})
        # Original pre-cache algorithm, independent of the new layer helper.
        self.h.run('''(defun test:LegacyWireStyle (d / layer lt)
          (setq layer (cdr (assoc 8 d)) lt (strcase (cond ((cdr (assoc 6 d))) (T "BYLAYER"))))
          (if (equal lt "BYLAYER")
            (setq lt (strcase (cond ((cdr (assoc 6 (tblsearch "LAYER" layer)))) (T "CONTINUOUS")))))
          (if (equal lt "BYBLOCK") (setq lt "CONTINUOUS"))
          (list layer lt))''')

    def assert_unbound(self):
        for key in ('*EL:WIRELAYERCACHEENABLED*', '*EL:WIRELAYERSTYLES*', '*EL:WIRELAYERCACHEEPOCH*'):
            self.assertIsNone(self.h.lookup(key), key)

    def wires(self, count=64):
        for i in range(count):
            self.line(f'w{i}', [float(i), 0., 0.], [float(i)+1., 0., 0.], 'W')
        self.selected = [f'w{i}' for i in range(count)]
        self.cfg = self.call('EL:Put', Symbol('WIRE-STYLES'), [['W', 'CONTINUOUS']], self.cfg)

    def test_bylayer_explicit_byblock_and_missing_layer_keep_old_results(self):
        self.layers()
        for layer, lt in (('W', None), ('D', 'ByLayer'), ('missing', None),
                          ('W', 'byblock'), ('W', 'dashed'), ('D', 'Continuous')):
            with self.subTest(layer=layer, lt=lt):
                data = [Pair(8, layer)] + ([Pair(6, lt)] if lt is not None else [])
                self.assertEqual(self.call('EL:WireStyle', data), self.call('TEST:LegacyWireStyle', data))
        self.assert_unbound()

    def test_full_collect_matches_old_records_and_reduces_native_layer_reads(self):
        self.layers()
        self.wires()
        actual = self.call('EL:SimpleCollect', self.cfg)
        optimized_reads = len(self.reads)
        metrics = dict(self.metrics)
        self.assertEqual(metrics['source-wire-layer-reads'], 1)
        self.assertEqual(metrics['source-wire-layer-cache-hits'], 63)
        self.assertEqual(metrics['source-wire-layer-read-ms'], 3)
        self.assert_unbound()
        self.reads.clear()
        self.h.builtins['EL:WIRESTYLE'] = lambda data: self.call('TEST:LegacyWireStyle', data)
        expected = self.call('EL:SimpleCollect', self.cfg)
        self.assertEqual(actual, expected)
        self.assertEqual(len(self.reads)-optimized_reads, 63)

    def test_real_network_is_identical_to_old_layer_resolution(self):
        self.layers()
        self.plan()
        self.cfg = self.call('EL:Put', Symbol('WIRE-STYLES'), [['W', 'CONTINUOUS']], self.cfg)
        snapshot = self.call('EL:SimpleCollect', self.cfg)
        actual = self.call('EL:SimpleNetwork', snapshot, self.cfg, 'panel')
        self.h.builtins['EL:WIRESTYLE'] = lambda data: self.call('TEST:LegacyWireStyle', data)
        old_snapshot = self.call('EL:SimpleCollect', self.cfg)
        expected = self.call('EL:SimpleNetwork', old_snapshot, self.cfg, 'panel')
        self.assertEqual(snapshot, old_snapshot)
        self.assertEqual(actual, expected)
        self.assertEqual(sorted(self.get('id', b) for b in self.get('devices', actual)), ['a', 'b'])

    def test_layer_change_and_new_drawing_are_read_again_on_next_collect(self):
        self.layers()
        self.wires(3)
        self.assertEqual(len(self.get('wires', self.call('EL:SimpleCollect', self.cfg))), 3)
        self.layer_values['W'] = 'DASHED'
        self.h.builtins['NAMEDOBJDICT'] = lambda: 'second-drawing'
        self.assertFalse(truth(self.get('wires', self.call('EL:SimpleCollect', self.cfg))))
        self.assertEqual(dict(self.metrics)['source-wire-layer-reads'], 1)
        self.assert_unbound()
        self.layer_values['W'] = 'Continuous'
        self.assertEqual(len(self.get('wires', self.call('EL:SimpleCollect', self.cfg))), 3)

    def test_write_boundary_invalidates_layer_cache_inside_one_collect(self):
        self.layers()
        self.wires(3)
        original = self.h.functions[Symbol('EL:WIRERECORDDXF')]
        function = [Symbol('LAMBDA'), original[0], *original[1]]
        calls = []

        def record(*args):
            value = self.h.call(function, list(args))
            calls.append(args)
            if len(calls) == 1:
                self.layer_values['W'] = 'DASHED'
                self.call('EL:FreshBoundary')
            return value

        self.h.builtins['EL:WIRERECORDDXF'] = record
        snapshot = self.call('EL:SimpleCollect', self.cfg)
        self.assertEqual([self.get('id', w) for w in self.get('wires', snapshot)], ['w0'])
        metrics = dict(self.metrics)
        self.assertEqual(metrics['source-wire-layer-reads'], 2)
        self.assertEqual(metrics['source-wire-layer-cache-hits'], 1)
        self.assert_unbound()

    def test_cancelled_collect_drops_layer_cache_before_retry(self):
        self.layers()
        self.wires(3)
        original = self.h.functions[Symbol('EL:WIRERECORDDXF')]
        function = [Symbol('LAMBDA'), original[0], *original[1]]

        def cancelled(*args):
            self.h.call(function, list(args))
            raise RuntimeError('Function cancelled')

        self.h.builtins['EL:WIRERECORDDXF'] = cancelled
        with self.assertRaisesRegex(RuntimeError, 'Function cancelled'):
            self.call('EL:SimpleCollect', self.cfg)
        self.assert_unbound()
        del self.h.builtins['EL:WIRERECORDDXF']
        self.layer_values['W'] = 'DASHED'
        self.assertFalse(truth(self.get('wires', self.call('EL:SimpleCollect', self.cfg))))
        self.assert_unbound()


if __name__ == '__main__':
    unittest.main()
