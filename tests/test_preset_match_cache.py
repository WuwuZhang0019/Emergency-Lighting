"""Collect-local preset matching against a frozen oracle. Date: 2026-10-21.

Operation counts verify less repeated work, not native CAD time.
"""
from pathlib import Path
import unittest
from autolisp_host import Host, Pair, Symbol, car, cdr, truth

ROOT = Path(__file__).resolve().parents[1]


class PresetMatchCacheTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'geometry', 'config'):
            self.h.load_definitions(ROOT / 'src' / (name + '.lsp'))
        self.h.run("""
          (defun TEST:LegacyPresetMember (value values)
            (and (equal (type value) 'STR) (member (strcase value) (mapcar 'strcase values))))
          (defun TEST:LegacyPresetBlock (name data cfg)
            (or (not (EL:Get 'preset-scoped cfg)) (EL:JunctionName name cfg)
              (and (TEST:LegacyPresetMember (cdr (assoc 8 data)) (EL:Get 'panel-layers cfg))
                (TEST:LegacyPresetMember name (EL:Get 'panel-names cfg)))
              (and (TEST:LegacyPresetMember (cdr (assoc 8 data)) (EL:Get 'device-layers cfg))
                (TEST:LegacyPresetMember name (EL:Get 'device-names cfg)))))
        """)
        self.cfg = self.h.run("""'((preset-scoped . T) (panel-layers "P" "Shared")
          (panel-names "Box" "box" "BoxTail") (wire-layers "W")
          (device-layers "D" "Shared") (device-names "Lamp" "LongLamp" "灯具")
          (unknown-future-field ("untouched" 8)))""")
        # Pair-backed tables preserve native CDR/EQ identity in the Python host.
        self.cfg = [Pair(car(row), cdr(row)) for row in self.cfg]
        self.cfg = self.call('EL:PutRole', self.cfg,
                             self.call('EL:FixedBlockIdentity', 'Junction'), Symbol('JUNCTION'))
        self.ticks = []
        self.h.builtins['EL:TICK'] = lambda: self.ticks.append(True) or len(self.ticks)
        self.reset_scope()

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, name, data):
        return self.call('EL:Get', Symbol(name.upper()), data)

    def put(self, name, value, data):
        return self.call('EL:Put', Symbol(name.upper()), value, data)

    def state(self, name):
        return self.h.lookup(Symbol('*EL:PRESETCACHE' + name.upper() + '*'))

    def reset_scope(self, cfg=None):
        self.h.run("""(setq *EL:FreshEpoch* 1 *EL:PresetCacheEnabled* T
          *EL:PresetCacheHits* 0 *EL:PresetCacheMisses* 0 *EL:PresetCacheNormalizations* 0
          *EL:PresetCacheMemberHits* 0 *EL:PresetCacheMemberMisses* 0
          *EL:PresetCacheRebuilds* 0 *EL:PresetCacheCheckMS* 0)""")
        self.call('EL:PresetCachePrepare', cfg if cfg is not None else self.cfg)

    def match(self, name, layer, cfg=None):
        cfg = self.cfg if cfg is None else cfg
        data = [Pair(0, 'INSERT'), Pair(8, layer), Pair(Symbol('UNUSED'), ['preserved'])]
        expected = self.call('TEST:LegacyPresetBlock', name, data, cfg)
        self.assertEqual(self.call('EL:PresetBlockNameAllowed', name, data, cfg), expected)
        return expected

    def test_full_case_sensitive_keys_layer_separation_and_cached_nil(self):
        cases = [('Box', 'P'), ('box', 'p'), ('Lamp', 'D'), ('Lamp', 'P'),
                 ('Lamp', 'd'), ('Lamp', 'D2'), ('LongLamp', 'D'), ('Lam', 'D'),
                 ('灯具', 'D'), ('Junction', 'ARCH'), ('JUNCTION', 'ARCH'),
                 ('JunctionExtra', 'ARCH'), (None, 'D'), ('Lamp', None)]
        for name, layer in cases:
            self.match(name, layer)
        self.assertEqual(self.state('misses'), len(cases))
        self.assertEqual(self.state('hits'), 0)
        for name, layer in reversed(cases):
            self.match(name, layer)
        self.assertEqual(self.state('hits'), len(cases))
        self.assertIsNone(self.match('Lamp', 'P'))
        self.assertEqual(self.state('misses'), len(cases))

    def test_member_preserves_duplicate_order_tail_and_unknown_table_fallback(self):
        names = self.get('panel-names', self.cfg)
        for value, expected in [('box', ['BOX', 'BOX', 'BOXTAIL']), ('boxtail', ['BOXTAIL']),
                                (8, None), (None, None)]:
            self.assertEqual(self.call('EL:PresetMember', value, names), expected)
        self.assertEqual(self.state('memberhits'), 4)
        unknown = ['other', 'OTHER', 'tail']
        self.assertEqual(self.call('EL:PresetMember', 'other', unknown),
                         self.call('TEST:LegacyPresetMember', 'other', unknown))
        self.assertEqual(self.state('membermisses'), 1)

    def test_normalize_once_and_no_repeated_checks_or_hit_clock_reads(self):
        self.h.run('(setq *EL:PerfActive* T)')
        original = self.h.builtins['STRCASE']
        conversions = []
        self.h.builtins['STRCASE'] = lambda value, *args: conversions.append(value) or original(value, *args)
        self.reset_scope()
        self.assertEqual(len(conversions), 11)
        conversions.clear()
        for _ in range(500):
            self.call('EL:PresetBlockNameAllowed', 'Lamp', [Pair(8, 'D')], self.cfg)
        self.assertEqual(self.state('normalizations'), 5)
        self.assertEqual(self.state('rebuilds'), 1)
        self.assertEqual(self.state('misses'), 1)
        self.assertEqual(self.state('hits'), 499)
        self.assertEqual(conversions, ['D', 'D', 'Lamp'])
        self.assertEqual(len(self.ticks), 2)
        self.assertEqual(self.state('checkms'), 1)
        conversions.clear()
        for _ in range(100):
            self.call('EL:PresetMember', 'lamp', self.get('device-names', self.cfg))
        self.assertEqual(conversions, ['lamp'] * 100)
        self.assertEqual(len(self.ticks), 2)
        conversions.clear()
        for _ in range(500):
            self.call('TEST:LegacyPresetBlock', 'Lamp', [Pair(8, 'D')], self.cfg)
        self.assertEqual(len(conversions), 5000)

    def test_perf_disabled_uses_no_native_clock(self):
        self.match('Lamp', 'D')
        self.match('Lamp', 'D')
        self.assertEqual(self.ticks, [])
        self.assertEqual(self.state('checkms'), 0)

    def test_config_replacement_roles_unknown_fields_and_epoch_invalidate(self):
        self.match('Lamp', 'D')
        denied = self.put('device-names', ['Changed'], self.cfg)
        self.assertIsNone(self.match('Lamp', 'D', denied))
        changed = self.put('roles', None, denied)
        self.assertIsNone(self.match('Junction', 'ARCH', changed))
        future = self.put('unknown-future-field', ['changed'], changed)
        self.match('Box', 'P', future)
        self.assertEqual(self.state('rebuilds'), 4)
        member_misses = self.state('membermisses')
        self.h.run('(setq *EL:FreshEpoch* 2)')
        self.call('EL:PresetMember', 'W', self.get('wire-layers', future))
        self.assertEqual(self.state('membermisses'), member_misses + 1)
        self.match('Box', 'P', future)
        self.assertEqual(self.state('rebuilds'), 5)
        self.assertEqual(self.state('misses'), 5)

    def test_direct_call_and_next_scope_do_not_reuse_old_decisions(self):
        self.match('Lamp', 'D')
        self.h.run('(setq *EL:PresetCacheEnabled* nil)')
        self.match('Lamp', 'D')
        self.assertEqual(self.state('hits'), 0)
        self.assertEqual(self.state('misses'), 1)
        self.reset_scope()
        self.match('Lamp', 'D')
        self.assertEqual(self.state('hits'), 0)
        self.assertEqual(self.state('misses'), 1)

    def test_disabled_scoping_and_unused_invalid_tables_keep_lazy_legacy_behavior(self):
        malformed = self.put('device-names', Pair('bad', 'dotted-tail'), self.cfg)
        malformed = self.put('panel-names', 17, malformed)
        self.reset_scope(malformed)
        self.assertTrue(truth(self.match('Junction', 'ARCH', malformed)))
        unscoped = self.put('preset-scoped', None, malformed)
        self.reset_scope(unscoped)
        self.assertEqual(self.state('normalizations'), 0)
        self.assertTrue(truth(self.match('unknown', None, unscoped)))

    def test_dynamic_effective_names_and_batch_metrics(self):
        lookups = []
        self.h.builtins['EL:EFFECTIVENAME'] = lambda entity: lookups.append(entity) or 'Lamp'
        self.call('EL:PresetBlockAllowed', '*U123', [Pair(8, 'D')], self.cfg)
        self.call('EL:PresetBlockAllowed', '*U456', [Pair(8, 'D')], self.cfg)
        self.assertEqual(lookups, ['*U123', '*U456'])
        self.assertEqual(self.state('misses'), 1)
        self.assertEqual(self.state('hits'), 1)
        counts = []
        self.h.builtins['EL:PERFCOUNT'] = lambda name, value: counts.append((name, value))
        self.call('EL:PresetCacheMetrics')
        self.assertIn(('source-preset-cache-hits', 1), counts)
        self.assertIn(('source-preset-cache-misses', 1), counts)
        self.assertIn(('source-preset-normalizations', 5), counts)
        self.assertIn(('source-preset-cache-miss-check-ms', 0), counts)


    def collect_fixture(self):
        import test_auto_wire as auto
        fixture = auto.AutoWireTests()
        fixture.setUp()
        fixture.h.builtins['CHR'] = chr
        fixture.cfg = fixture.call('EL:Put', Symbol('PRESET-SCOPED'), True, fixture.cfg)
        fixture.cfg = [Pair(car(row), cdr(row)) for row in fixture.cfg]
        # Same rejected name/layer appears twice; neither may read bounds.
        fixture.block('OTHER', 'D', 'bad1', [4., 0., 0.])
        fixture.block('OTHER', 'D', 'bad2', [6., 0., 0.])
        fixture.selected.extend(['bad1', 'bad2'])
        for name in ('TEST:LEGACYPRESETBLOCK', 'TEST:LEGACYPRESETMEMBER'):
            fixture.h.functions[Symbol(name)] = self.h.functions[Symbol(name)]
        return fixture

    def test_real_collect_reuses_within_batch_and_unwinds_before_next_collect(self):
        f = self.collect_fixture()
        counts = []
        f.h.builtins['EL:PERFCOUNT'] = lambda name, value: counts.append((name, value))
        first = f.call('EL:SimpleCollect', f.cfg)
        self.assertIn(('source-preset-cache-misses', 3), counts)
        self.assertIn(('source-preset-cache-hits', 3), counts)
        self.assertIn(('source-preset-normalizations', 5), counts)
        for name in ('Enabled', 'Cfg', 'Epoch', 'Tables', 'Blocks', 'Hits', 'Misses'):
            self.assertIsNone(f.h.lookup(Symbol('*EL:PRESETCACHE' + name.upper() + '*')))
        counts.clear()
        second = f.call('EL:SimpleCollect', f.cfg)
        self.assertEqual(first, second)
        self.assertIn(('source-preset-cache-misses', 3), counts)
        self.assertIn(('source-preset-cache-hits', 3), counts)
        f.h.builtins['EL:PRESETBLOCKNAMEALLOWED'] = lambda name, data, cfg: f.call(
            'TEST:LegacyPresetBlock', name, data, cfg)
        legacy = f.call('EL:SimpleCollect', f.cfg)
        self.assertEqual(first, legacy)
        self.assertEqual(f.call('EL:SimpleNetwork', first, f.cfg, 'panel'),
                         f.call('EL:SimpleNetwork', legacy, f.cfg, 'panel'))

    def test_real_collect_exception_unwinds_cache_scope(self):
        f = self.collect_fixture()
        def fail_bounds(entity):
            raise RuntimeError('native-bounds-failure')
        f.h.builtins['EL:ENTITYBOUNDS'] = fail_bounds
        with self.assertRaisesRegex(RuntimeError, 'native-bounds-failure'):
            f.call('EL:SimpleCollect', f.cfg)
        for name in ('Enabled', 'Cfg', 'Epoch', 'Tables', 'Blocks', 'Hits', 'Misses'):
            self.assertIsNone(f.h.lookup(Symbol('*EL:PRESETCACHE' + name.upper() + '*')))


if __name__ == '__main__':
    unittest.main()
