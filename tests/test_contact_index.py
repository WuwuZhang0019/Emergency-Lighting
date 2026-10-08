"""Physical contact performance and v16 equivalence. Date: 2026-10-08.

Synthetic geometry only; work counts are not native AutoCAD timings.
"""
import math
import random
import unittest

from autolisp_host import Pair, Symbol, truth
import test_cad_adapter as adapter
import test_diagnostics as diagnostics


class ContactIndexTests(unittest.TestCase):
    setUp = adapter.CadAdapterTests.setUp
    call = adapter.CadAdapterTests.call
    get = adapter.CadAdapterTests.get
    line = adapter.CadAdapterTests.line
    logging = diagnostics.DiagnosticTests.logging

    def record(self, **fields):
        return [Pair(Symbol(k.upper().replace('_', '-')), v) for k, v in fields.items()]

    @staticmethod
    def polygon(points):
        p = [[*xy, 0.] if len(xy) == 2 else list(xy) for xy in points]
        return [[a, b] for a, b in zip(p, p[1:] + p[:1])]

    def circle(self, n, x=0., y=0., r=10.):
        return self.polygon([(x+r*math.cos(math.tau*i/n), y+r*math.sin(math.tau*i/n)) for i in range(n)])

    def block_record(self, name, rings, role='device', holes=None, issues=None, bounds=None, extra=None):
        segments = sum(rings, []) + (extra or [])
        return self.record(id=name, role=Symbol(role.upper()), segments=segments, regions=rings,
                           holes=holes, issues=issues, bounds=bounds or self.call('EL:SegmentBounds', segments))

    def wire(self, name, a, b):
        self.line(name, list(a), list(b), 'W')
        return self.call('EL:WireRecord', name, self.h.lookup('CFG'))

    def snapshot(self, wires, blocks):
        return self.record(wires=wires, blocks=blocks, ends=sum((self.get('ends', w) for w in wires), []))

    def legacy(self):
        self.h.load_definitions(adapter.ROOT / 'tests/fixtures/contact-v16-oracle.lsp')

    def count_calls(self, names):
        counts = dict.fromkeys(names, 0)
        for name in names:
            params, body = self.h.functions[Symbol(name.upper())]
            original = [Symbol('LAMBDA'), params, *body]

            def counted(*args, name=name, original=original):
                counts[name] += 1
                return self.h.call(original, list(args))

            self.h.builtins[name.upper()] = counted
        return counts

    def test_prepared_predicates_match_frozen_v16_for_holes_concavity_z_and_crossings(self):
        self.legacy()
        concave = self.polygon([(0., 0.), (6., 0.), (6., 6.), (4., 6.), (4., 2.), (2., 2.), (2., 6.), (0., 6.)])
        hole = self.polygon([(.5, .5, 9.), (1.5, .5, 9.), (1.5, 1.5, 9.), (.5, 1.5, 9.)])
        blocks = [self.block_record('C', [concave], holes=[hole]),
                  self.block_record('ROUND', [self.circle(128)]),
                  self.block_record('EMPTY', [], issues=[self.record(code=Symbol('UNSUPPORTED_CONTOUR'))],
                                    bounds=[[-5., -5., 0.], [5., 5., 0.]])]
        rng = random.Random(17)
        points = [[1., 1., 0.], [3., 4., 0.], [0., 2., 0.], [10.1, 0., 0.], [10.100001, 0., 0.],
                  [1., 4., 2.], [0., 0., 1e-7], [0., 0., 1.01e-7]]
        points += [[rng.uniform(-15., 15.), rng.uniform(-15., 15.), 0.] for _ in range(15)]
        for block in blocks:
            prepared = self.call('EL:PrepareContactBlock', block)
            for point in points:
                self.assertEqual(truth(self.call('EL:BlockPointHit', point, prepared, self.h.lookup('CFG'))),
                                 truth(self.call('TEST16:BlockPointHit', point, block, self.h.lookup('CFG'))))
            for i in range(0, len(points)-1, 2):
                wire = self.record(segments=[[points[i], points[i+1]]])
                self.assertEqual(truth(self.call('EL:PathBlockHit', wire, prepared, self.h.lookup('CFG'))),
                                 truth(self.call('TEST16:PathBlockHit', wire, block, self.h.lookup('CFG'))))
        # Crossing succeeds even when both endpoints and the midpoint are outside.
        block = blocks[1]
        wire = self.record(segments=[[[-100., 5., 0.], [12., 5., 0.]]])
        self.assertTrue(truth(self.call('EL:PathBlockHit', wire, self.call('EL:PrepareContactBlock', block), self.h.lookup('CFG'))))

    def test_whole_physical_result_matches_legacy_and_does_not_store_indexes(self):
        self.legacy()
        square = self.polygon([(-1., -1.), (1., -1.), (1., 1.), (-1., 1.)])
        wires = [self.wire('A', [-3., 0., 0.], [0., 0., 0.]),
                 self.wire('B', [0., 0., 0.], [4., 0., 0.]),
                 self.wire('C', [8., -20., 0.], [8., 12., 0.]),
                 self.wire('D', [4., 0., 0.], [4., 5., 0.]),
                 self.wire('E', [1., 0., 3.], [10., 0., 3.])]
        for role in ('device', 'panel', 'unknown', 'ambiguous', 'ignore'):
            blocks = [self.block_record('BOX', [square], role='panel'),
                      self.block_record('B', [self.circle(64, 8., 0., 2.)], role=role),
                      self.block_record('UNVERIFIED', [], issues=[self.record(code=Symbol('UNSUPPORTED_CONTOUR'))],
                                        bounds=[[3., 3., 0.], [5., 6., 0.]])]
            snapshot = self.snapshot(wires, blocks)
            self.h.steps = 0
            expected = self.call('TEST16:BuildPhysical', snapshot, self.h.lookup('CFG'), 'BOX')
            self.h.steps = 0
            actual = self.call('EL:BuildPhysical', snapshot, self.h.lookup('CFG'), 'BOX')
            self.assertEqual(actual, expected)
            self.assertEqual(self.get('blocks', self.get('snapshot', actual)), blocks)

    def test_contact_index_prunes_large_contour_and_returns_on_first_hit(self):
        self.legacy()
        block = self.block_record('C', [self.circle(512)])
        prepared = self.call('EL:PrepareContactBlock', block)
        counts = self.count_calls(['EL:PointSegmentDistance', 'EL:GapHitsSegment'])
        wire = self.record(segments=[[[100., 100., 0.], [120., 110., 0.]]])
        self.call('TEST16:PathBlockHit', wire, block, self.h.lookup('CFG'))
        old = dict(counts)
        for name in counts: counts[name] = 0
        self.call('EL:PathBlockHit', wire, prepared, self.h.lookup('CFG'))
        self.assertEqual(old['EL:PointSegmentDistance'], 1024)
        self.assertEqual(old['EL:GapHitsSegment'], 512)
        self.assertEqual(sum(counts.values()), 0)
        wire = self.record(segments=[[[0., 0., 0.], [100., 100., 0.]]] * 30)
        self.assertTrue(truth(self.call('EL:PathBlockHit', wire, prepared, self.h.lookup('CFG'))))
        self.assertLess(sum(counts.values()), 10)

    def test_44_wires_48_blocks_reuse_contact_indexes_and_finish(self):
        self.h.step_limit = 50000000
        rings = [self.circle(512, i*40., 0.) for i in range(12)]
        extra = [[[i*2., -20., 0.], [i*2.+1., -19., 0.]] for i in range(84)]
        blocks = [self.block_record('LARGE', rings, extra=extra)]
        self.assertEqual(len(self.get('segments', blocks[0])), 6228)
        blocks += [self.block_record(str(i), [self.polygon([(1000.+i*10., 0.), (1001.+i*10., 0.),
                   (1001.+i*10., 1.), (1000.+i*10., 1.)])]) for i in range(47)]
        wires = [self.wire(str(i), [i*10., -5., 0.], [i*10.+2., 5., 0.]) for i in range(44)]
        counts = self.count_calls(['EL:PrepareContactBlock', 'EL:PointSegmentDistance', 'EL:GapHitsSegment'])
        self.h.steps = 0
        result = self.call('EL:BuildPhysical', self.snapshot(wires, blocks), self.h.lookup('CFG'), 'BOX')
        self.assertEqual(counts['EL:PrepareContactBlock'], 48)
        self.assertLess(counts['EL:PointSegmentDistance'] + counts['EL:GapHitsSegment'], 15000)
        self.assertEqual(len(self.get('ends', self.get('snapshot', result))), 88)
        self.assertEqual(self.get('blocks', self.get('snapshot', result)), blocks)

    def test_failed_path_keeps_wire_block_and_progress_context(self):
        self.logging()
        self.h.run('(EL:LogStart)')
        block = self.block_record('B', [self.circle(16)])
        wire = self.wire('W', [-20., 5., 0.], [12., 5., 0.])

        def failed(*args):
            raise RuntimeError('cancelled in path check')

        self.h.builtins['EL:PATHBLOCKHIT'] = failed
        with self.assertRaisesRegex(RuntimeError, 'cancelled in path') as error:
            self.call('EL:BuildPhysical', self.snapshot([wire], [block]), self.h.lookup('CFG'), 'BOX')
        self.call('EL:LogFailure', str(error.exception))
        log = self.log.read_text(encoding='utf-8')
        self.assertIn('PHYSICAL_PROGRESS', log)
        for value in ('PHYSICAL_PATH_CHECK', 'WIRE', 'BLOCK', 'W', 'B', 'BLOCK-SEGMENTS'):
            self.assertIn(value, log.split('| ERROR |')[-1])


if __name__ == '__main__':
    unittest.main()
