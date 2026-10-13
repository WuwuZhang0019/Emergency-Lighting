"""Strict gap policy and spatial index regressions. Date: 2026-10-13.

Runs actual LISP, not AutoCAD. The all-pairs oracle only checks index completeness.
"""
import math
import pathlib
import random
import unittest

from autolisp_host import Host, Pair, Symbol, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]


class GapIndexTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for path in (ROOT / 'src').glob('*.lsp'):
            self.h.load_definitions(path)
        self.cfg = self.h.run('''(EL:Put 'wire-layers '("E")
            (EL:Put 'params (EL:SuggestedParams) (EL:DefaultConfig "test")))''')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, record):
        return self.call('EL:Get', Symbol(key.upper()), record)

    def put(self, key, value, record):
        return self.call('EL:Put', Symbol(key.upper()), value, record)

    def record(self, **values):
        return [Pair(Symbol(k.upper().replace('_', '-')), v) for k, v in values.items()]

    def end(self, name, point, direction):
        return self.record(key=[name, Symbol('END')], wire=name, point=list(point),
                           direction=list(direction), geometry=Symbol('STRAIGHT'), layer='E')

    def accepted(self, a, b, snapshot=None, cfg=None):
        return truth(self.get('accepted', self.call('EL:ValidateGapPair', a, b, snapshot, cfg or self.cfg)))

    def test_strict_alignment_ignores_legacy_large_tolerances(self):
        params = self.get('params', self.cfg)
        for key, value in [('eps_perp', 10.0), ('theta_max', 0.2), ('eps_z', 10.0)]:
            params = self.put(key, value, params)
        cfg = self.put('params', params, self.cfg)
        a = self.end('a', (0., 0., 0.), (1., 0., 0.))
        b = self.end('b', (2000., 0., 0.), (-1., 0., 0.))
        self.assertTrue(self.accepted(a, b, cfg=cfg))
        for point in [(2000.001, 0., 0.), (1000., 0.001, 0.), (1000., 0., 0.001)]:
            self.assertFalse(self.accepted(a, self.put('point', list(point), b), cfg=cfg))
        angle = 0.001
        self.assertFalse(self.accepted(a, self.put('direction', [-math.cos(angle), math.sin(angle), 0.], b), cfg=cfg))
        self.assertFalse(self.accepted(a, self.put('direction', [1., 0., 0.], b), cfg=cfg))

    def test_index_matches_all_pairs_for_rotated_negative_and_duplicate_points(self):
        ends = []
        rng = random.Random(10)
        for i in range(8):
            angle = rng.uniform(-math.pi, math.pi)
            d = [math.cos(angle), math.sin(angle), 0.]
            p = [-10000. + i * 3300., rng.uniform(-5000., 5000.), float(i % 2)]
            for j, length in enumerate((0., 500., 2000., 2000.1)):
                ends.append(self.end(f'{i}-{j}', [p[k] + length * d[k] for k in range(3)],
                                     d if j == 0 else [-x for x in d]))
        ends.append(self.put('key', ['duplicate', Symbol('END')], self.put('wire', 'duplicate', ends[1])))
        ends += [self.end('vertical-a', (0., -100., 0.), (0., 1., 0.)),
                 self.end('vertical-b', (0., 1900., 0.), (0., -1., 0.))]
        snap = self.record(ends=ends)
        expected = {}
        for a in ends:
            expected[self.get('wire', a)] = sorted(self.get('wire', b) for b in ends
                                                  if self.accepted(a, b, snap))
        for ordered in (ends, list(reversed(ends))):
            self.h.steps = 0
            rows = self.call('EL:FindGapCandidates', self.record(ends=ordered), self.cfg)
            actual = {self.get('key', r)[0]: sorted(self.get('target', c)[0]
                      for c in (self.get('candidates', r) or [])) for r in rows}
            self.assertEqual(actual, expected)

    def test_index_prunes_unrelated_rows_before_pair_validation(self):
        ends = []
        for i in range(64):
            ends += [self.end(f'{i}-a', (0., i * 100., 0.), (1., 0., 0.)),
                     self.end(f'{i}-b', (1000., i * 100., 0.), (-1., 0., 0.))]
        calls = []

        def validate(*args):
            calls.append(1)
            del self.h.builtins['EL:VALIDATEGAPPAIR']
            try:
                return self.call('EL:ValidateGapPair', *args)
            finally:
                self.h.builtins['EL:VALIDATEGAPPAIR'] = validate

        self.h.builtins['EL:VALIDATEGAPPAIR'] = validate
        rows = self.call('EL:FindGapCandidates', self.record(ends=ends), self.cfg)
        self.assertEqual(len(rows), 128)
        self.assertTrue(all(len(self.get('candidates', r)) == 1 for r in rows))
        self.assertEqual(len(calls), 128)  # All-pairs would visit 128 * 127 = 16256 pairs.

    def test_spatial_tree_serializes_each_tie_break_key_once(self):
        ends = [self.end(str(i), (float(i % 4), float(i // 4), 0.), (1., 0., 0.))
                for i in range(32)]
        # Coincident endpoints with different keys must both survive sorting.
        ends.append(self.end('duplicate-point', (0., 0., 0.), (-1., 0., 0.)))
        original = self.h.functions[Symbol('EL:SIGNATURE')]
        signatures = []

        def signature(value):
            signatures.append(value)
            return self.h.call([Symbol('LAMBDA'), original[0], *original[1]], [value])

        self.h.builtins['EL:SIGNATURE'] = signature
        tree = self.call('EL:SpatialTree', ends, 0)
        self.assertEqual(len(signatures), len(ends))
        found = self.call('EL:SpatialRayQuery', tree, [-1., 0., 0.], [1., 0., 0.], 10.)
        self.assertEqual(sorted(self.get('wire', end) for end in found),
                         ['0', '1', '2', '3', 'duplicate-point'])

    def test_mutual_pairs_lookup_preserves_order_and_last_endpoint_without_full_scans(self):
        a = self.end('a', (0., 0., 0.), (1., 0., 0.))
        b = self.end('b', (1000., 0., 0.), (-1., 0., 0.))
        free = self.end('free', (0., 500., 0.), (1., 0., 0.))
        occupied_a = self.put('occupied', True, a)
        rows = [self.record(key=self.get('key', b), candidates=[self.record(target=self.get('key', a))]),
                self.record(key=self.get('key', free)),
                self.record(key=self.get('key', a), candidates=[self.record(target=self.get('key', b))])]
        snapshot = self.record(ends=[occupied_a, b, free, a])
        self.h.builtins['EL:BY'] = lambda *args: self.fail('Full interpreted record scan')
        result = self.call('EL:BuildMutualPairs', rows, snapshot, self.cfg)
        pairs = self.get('pairs', result)
        issues = self.get('issues', result)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(self.get('a', pairs[0]), self.get('key', a))
        self.assertEqual(self.get('b', pairs[0]), self.get('key', b))
        self.assertEqual([self.get('code', issue) for issue in issues], [Symbol('NO_CANDIDATE')])
        self.assertEqual(self.get('object', issues[0]), 'free')

    def test_noncollinear_geometry_ignored_but_collinear_segment_blocks(self):
        a = self.end('a', (0., 0., 0.), (1., 0., 0.))
        b = self.end('b', (1000., 0., 0.), (-1., 0., 0.))
        crossing = self.record(id='cross', segments=[[[300., -100., 0.], [300., 100., 0.]]],
                               bounds=[[250., -100., 0.], [350., 100., 0.]])
        snap = self.record(ends=[a, b], blocks=[crossing], wires=[crossing])
        rows = self.call('EL:FindGapCandidates', snap, self.cfg)
        self.assertTrue(all(len(self.get('candidates', r)) == 1 for r in rows))
        for kind in ('blocks', 'wires'):
            for segment, allowed in [([[300., 0., 0.], [350., 0., 0.]], False),
                                     ([[300., 0.001, 0.], [350., 0.001, 0.]], True),
                                     ([[300., 0., 1.], [350., 0., 1.]], True)]:
                block = self.record(id='path', segments=[segment])
                self.assertEqual(self.accepted(a, b, self.put(kind, [block], snap)), allowed)

    def test_equipment_contact_excludes_both_ends_and_manual_pair(self):
        a = self.end('a', (0., 0., 0.), (1., 0., 0.))
        back = self.put('key', ['a', Symbol('START')], self.end('a', (-10., 0., 0.), (-1., 0., 0.)))
        b = self.end('b', (1000., 0., 0.), (-1., 0., 0.))
        for role in ('PANEL', 'DEVICE'):
            block = self.record(id='equipment', role=Symbol(role),
                                segments=[[[-10., -1., 0.], [-10., 1., 0.]]])
            snap = self.record(ends=[a, back, b], blocks=[block])
            physical = self.call('EL:BuildPhysical', snap, self.cfg, None)
            snap = self.get('snapshot', physical)
            marked = self.get('ends', snap)
            self.assertTrue(all(truth(self.get('wire-attached', e)) for e in marked[:2]))
            rows = self.call('EL:FindGapCandidates', snap, self.cfg)
            self.assertFalse(any(self.get('candidates', r) for r in rows))
            pair = self.record(a=self.get('key', a), b=self.get('key', b), source=Symbol('MANUAL'))
            checked = self.call('EL:ValidatePairSet', snap, self.cfg, None, [pair], None)
            self.assertFalse(self.get('pairs', checked))
            self.assertTrue(self.get('issues', checked))

    def test_upgrade_defaults_and_stale_confirmation_without_losing_samples(self):
        params = self.h.run("'((eps_touch . 0.1) (eps_boundary . 0.1) (eps_perp . 0.5) (eps_z . 0.01) (theta_max . 0.01) (R0 . 20) (Dmax . 200))")
        cfg = self.put('params', params, self.put('calibrated', True, self.cfg))
        upgraded = self.call('EL:UpgradeGapConfig', cfg)
        self.assertEqual(self.get('Dmax', self.get('params', upgraded)), 2000.)
        self.assertEqual(self.get('wire-layers', upgraded), ['E'])
        self.assertFalse(truth(self.get('calibrated', upgraded)))
        self.assertEqual(self.get('Dmax', params), 200)
        upgraded = self.put('params', self.put('Dmax', 3000., self.get('params', upgraded)), upgraded)
        self.assertEqual(self.call('EL:UpgradeGapConfig', upgraded), upgraded)


if __name__ == '__main__':
    unittest.main(verbosity=2)
