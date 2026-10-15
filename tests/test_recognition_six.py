"""Date: 2026-10-15. Exact results, numerical boundaries and scoped cache invalidation."""
import random
import unittest

from autolisp_host import Pair, Symbol, equal
from check_recognition_six_work import baseline_forms, six_fixture, recognize
from check_store_read_work import exact


def oracle(host, module, names):
    rename = {Symbol(n.upper()): Symbol(n.upper().replace('EL:', 'ORACLE:')) for n in names}
    def rewrite(value):
        if isinstance(value, Symbol):
            return rename.get(value, value)
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        if isinstance(value, Pair):
            return Pair(rewrite(value.car), rewrite(value.cdr))
        return value
    for form in baseline_forms(module):
        if form[1] in rename:
            host.evaluate(rewrite(form))


class SixRecognitionTests(unittest.TestCase):
    def test_complete_six_circuits_exact_including_raw_snapshot_number_ranges_and_proof(self):
        expected, _ = recognize(six_fixture(), True)
        f = six_fixture()
        actual, _ = recognize(f)
        self.assertEqual(exact(actual), exact(expected))
        self.assertIsNone(f.h.lookup('*EL:RECOGNITIONPASS*'))
        self.assertIsNone(f.h.lookup('*EL:RECOGNITIONCONTACTS*'))
        self.assertIsNone(f.h.lookup('*EL:STABLESNAPSHOTMEMO*'))
        # A fresh command rereads changed definition geometry and matches 139.
        fresh = six_fixture()
        for target in (f, fresh):
            for i in range(4):
                target.entities[f'LAMP-edge-{i}'] = [Pair(p.car, [.75 if p.cdr[0] == 1. else p.cdr[0], *p.cdr[1:]])
                    if isinstance(p, Pair) and p.car in (10, 11) else p for p in target.entities[f'LAMP-edge-{i}']]
        changed, _ = recognize(f, check_devices=False)
        changed_expected, _ = recognize(fresh, True, check_devices=False)
        self.assertEqual(exact(changed), exact(changed_expected))
        self.assertNotEqual(exact(actual), exact(changed))

    def test_stable_proper_dotted_and_mixed_types_match_139(self):
        f = six_fixture(0, 0, 1)
        oracle(f.h, 'common', ['EL:StableData'])
        values = [None, [0, 0., -0., 1.e-15, '中文', Symbol('K')],
                  Pair(Symbol('KEY'), 4.), Pair([1, 2.], Pair([3, None], 'tail')),
                  Pair('a', ['b', Pair('tail', -0.)]),
                  [[float(i), i + 1, None] for i in range(4000)]]
        for value in values:
            self.assertEqual(exact(f.call('EL:StableData', value)), exact(f.call('oracle:StableData', value)))

    def test_snapshot_memo_preserves_unknown_fields_and_rejects_changed_rows_owner_epoch(self):
        f = six_fixture(0, 0, 1)
        h = f.h
        h.frames[0]['*EL:RECOGNITIONPASS*'] = True
        row = Pair(Symbol('FUTURE-FIELD'), [1., 2, '中文'])
        snapshot = [row, Pair(Symbol('WIRES'), [])]
        expected = f.call('EL:StableData', snapshot)
        self.assertEqual(exact(f.call('EL:StableSnapshot', snapshot)), exact(expected))
        first = h.lookup('*EL:STABLESNAPSHOTMEMO*')
        self.assertEqual(exact(f.call('EL:StableSnapshot', snapshot)), exact(expected))
        self.assertIs(h.lookup('*EL:STABLESNAPSHOTMEMO*'), first)
        changed = [Pair(Symbol('FUTURE-FIELD'), [1. + 1.e-15, 2, '中文']), snapshot[1]]
        self.assertNotEqual(exact(f.call('EL:StableSnapshot', changed)), exact(expected))
        self.assertEqual(exact(f.call('EL:StableSnapshot', changed)), exact(f.call('EL:StableData', changed)))
        for owner, epoch in [('other-DWG', 0), ('other-DWG', 1)]:
            h.builtins['NAMEDOBJDICT'] = lambda owner=owner: owner
            h.frames[0]['*EL:FRESHEPOCH*'] = epoch
            f.call('EL:StableSnapshot', snapshot)
            self.assertEqual(len(h.lookup('*EL:STABLESNAPSHOTMEMO*')), 2)
            self.assertIsNot(h.lookup('*EL:STABLESNAPSHOTMEMO*'), first)

    def test_ray_slab_rejection_matches_139_near_parallel_negative_and_boundary_cases(self):
        f = six_fixture(0, 0, 1)
        oracle(f.h, 'geometry', ['EL:RayBoxHits'])
        rng = random.Random(140)
        cases = [([0., 0., 0.], [1., 0., 0.], 10., [10. + delta, -1., 0.], [11., 1., 0.])
                 for delta in (-1.e-7, 0., 1.e-7, 2.e-7)]
        for _ in range(100):
            p = [rng.uniform(-100, 100) for _ in range(3)]
            lo = [rng.uniform(-100, 100) for _ in range(3)]
            hi = [v + rng.uniform(0, 100) for v in lo]
            direction = [rng.choice([0., 1.e-16, -1.e-16, rng.uniform(-1, 1)]) for _ in range(3)]
            cases.append((p, direction, rng.uniform(-1, 100), lo, hi))
        for args in cases:
            self.assertTrue(equal(f.call('EL:RayBoxHits', *args), f.call('oracle:RayBoxHits', *args)))

    def test_number_probe_matches_139_for_curves_large_coordinates_and_both_directions(self):
        f = six_fixture(0, 0, 1)
        oracle(f.h, 'circuit-number', ['EL:NumberFirstDevice', 'EL:NumberShapeHitStrict'])
        for offset in (0., 154776.123456789):
            ring = f.call('EL:BoundsSegments', [[offset + 12., -2., 0.], [offset + 14., 2., 0.]])
            shapes = {'ring': [Pair(Symbol('SEGMENTS'), ring), Pair(Symbol('REGIONS'), [ring])],
                      'circle': [Pair(Symbol('CURVES'), [[[offset + 8., 0., 0.], 1., 0., 6.283185307179586, True]])]}
            f.h.builtins['EL:DEVICECONTACTSHAPE'] = lambda b: shapes[f.get('id', b)]
            for start, finish in ((0., 20.), (20., 0.), (10., 20.), (10., 0.)):
                wire = [Pair(Symbol('SEGMENTS'), [[[offset + i, 0., 0.], [offset + i + 2., 0., 0.]] for i in range(0, 20, 2)])]
                devices = [[Pair(Symbol('ID'), name)] for name in shapes]
                actual = f.call('EL:NumberFirstDevice', wire, start, finish, devices, f.cfg)
                expected = f.call('oracle:NumberFirstDevice', wire, start, finish, devices, f.cfg)
                self.assertEqual(exact(actual), exact(expected))


if __name__ == '__main__':
    unittest.main()
