"""Exact ordered role restoration and batch evidence timing. Date: 2026-10-21.

Operation counts verify reduced repeated lookup work, not native CAD seconds.
"""
from pathlib import Path
import unittest

from autolisp_host import Host, Pair, Symbol, car, equal, seq, truth


ROOT = Path(__file__).resolve().parents[1]


class NetworkRoleOrderTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'simple'):
            self.h.load_definitions(ROOT / 'src' / (name + '.lsp'))
        # Frozen pre-optimization lookup semantics, including first ASSOC match.
        self.h.run("""
          (defun TEST:LegacyNetworkProofInput (baseline proof / rows key blocks block role)
            (foreach key (EL:Get 'input-keys proof)
              (cond
                ((equal key 'ends) (setq rows (cons (cons key (EL:Get 'input-ends proof)) rows)))
                ((equal key 'blocks)
                  (setq blocks nil)
                  (foreach block (EL:Get 'blocks baseline)
                    (setq role (EL:Get (EL:Get 'id block) (EL:Get 'input-roles proof)))
                    (setq block (if role (EL:Put 'role (cdr role) block)
                      (vl-remove-if '(lambda (pair) (equal (car pair) 'role)) block)))
                    (setq blocks (cons block blocks)))
                  (setq rows (cons (cons key (reverse blocks)) rows)))
                (T (setq rows (cons (assoc key baseline) rows))))) (reverse rows))
        """)
        self.counts = []
        self.h.builtins['EL:PERFCOUNT'] = lambda name, value: self.counts.append((name, value))

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, data):
        return self.call('EL:Get', Symbol(key.upper()), data)

    def put(self, key, value, data):
        return self.call('EL:Put', Symbol(key.upper()), value, data)

    def block(self, handle, role=Symbol('DEVICE'), missing=False):
        result = [Pair(Symbol('ID'), handle), Pair(Symbol('FUTURE-BLOCK-FIELD'), [handle, 9])]
        if not missing:
            # Native (role . nil) is the proper list (role), not a dotted pair.
            result.append([Symbol('ROLE')] if role is None else Pair(Symbol('ROLE'), role))
        return result

    def proof(self, roles):
        return [Pair(Symbol('INPUT-KEYS'), [Symbol('BLOCKS'), Symbol('ENDS'), Symbol('FUTURE')]),
                Pair(Symbol('INPUT-ROLES'), roles), Pair(Symbol('INPUT-ENDS'), ['old-ends'])]

    def compare(self, blocks, roles, ordered):
        baseline = [Pair(Symbol('BLOCKS'), blocks), Pair(Symbol('ENDS'), ['new-ends']),
                    Pair(Symbol('FUTURE'), ['preserved', 17])]
        proof = self.proof(roles)
        expected = self.call('TEST:LegacyNetworkProofInput', baseline, proof)
        self.counts.clear()
        actual = self.call('EL:NetworkProofInput', baseline, proof)
        self.assertEqual(actual, expected)
        self.assertEqual(self.get('future', actual), ['preserved', 17])
        self.assertEqual(self.get('ends', actual), ['old-ends'])
        self.assertEqual(self.counts, [('network-role-blocks', len(blocks)),
                                     ('network-role-ordered-batches' if ordered else
                                      'network-role-fallback-batches', 1)])
        return self.get('blocks', actual)

    def test_ordered_restore_preserves_absent_nil_role_and_all_unknown_fields(self):
        source = [self.block('A', missing=True), self.block('AB', None),
                  self.block('a', Symbol('PANEL')), self.block('灯1', Symbol('DEVICE'))]
        roles = [Pair(self.get('id', block), self.call('ASSOC', Symbol('ROLE'), block))
                 for block in source]
        output = [self.put('role', Symbol('BUILDER-ROLE'), block) for block in source]
        restored = self.compare(output, roles, True)
        self.assertEqual(restored, source)
        self.assertIsNone(self.call('ASSOC', Symbol('ROLE'), restored[0]))
        self.assertTrue(truth(self.call('ASSOC', Symbol('ROLE'), restored[1])))
        self.assertIsNone(self.get('role', restored[1]))

    def test_noncanonical_tables_keep_first_match_missing_and_order_semantics(self):
        role_a = Pair('A', Pair(Symbol('ROLE'), Symbol('FIRST')))
        role_b = Pair('B', Pair(Symbol('ROLE'), Symbol('SECOND')))
        cases = [
            ([self.block('A'), self.block('B')], [role_b, role_a]),
            ([self.block('A'), self.block('B')], [role_a]),
            ([self.block('A')], [role_a, role_b]),
            ([self.block('A'), self.block('A')], [role_a, Pair('A', Pair(Symbol('ROLE'), None))]),
            ([self.block('B'), self.block('A')], [role_a, role_a]),
            ([self.block(None)], [Pair(None, Pair(Symbol('ROLE'), Symbol('NIL-ID')))]),
            ([self.block(17)], [Pair(17, Pair(Symbol('ROLE'), Symbol('NUMBER-ID')))]),
        ]
        for blocks, roles in cases:
            with self.subTest(ids=[self.get('id', block) for block in blocks], roles=roles):
                self.compare(blocks, roles, False)

    def test_code_comparison_distinguishes_full_prefix_case_and_unicode(self):
        values = ['', 'A', 'AA', 'AB', 'AB0', 'ABC', 'B', 'a', '灯', '灯1', '灯2']
        for a in values:
            for b in values:
                actual = self.call('EL:NetworkRoleCodeLess', list(map(ord, a)) or None,
                                   list(map(ord, b)) or None)
                self.assertEqual(truth(actual), a < b, (a, b))
        roles = [Pair(value, Pair(Symbol('ROLE'), Symbol('DEVICE'))) for value in values]
        self.compare([self.block(value) for value in values], roles, True)

    def test_duplicate_fallback_works_when_sort_retains_or_removes_duplicates(self):
        blocks = [self.block('A'), self.block('A'), self.block('B')]
        roles = [Pair(self.get('id', block), Pair(Symbol('ROLE'), Symbol('FIRST')))
                 for block in blocks]
        self.compare(blocks, roles, False)
        original = self.h.builtins['VL-SORT']

        def native_deduplicating_sort(values, compare):
            result = []
            for item in seq(original(values, compare)):
                if not result or not equal(result[-1], item):
                    result.append(item)
            return result or None

        self.h.builtins['VL-SORT'] = native_deduplicating_sort
        self.compare(blocks, roles, False)

    def test_proof_keeps_final_exact_comparison_and_rejects_unknown_mutations(self):
        blocks = [self.block('A', missing=True), self.block('B', None)]
        source = [Pair(Symbol('BLOCKS'), blocks), Pair(Symbol('ENDS'), ['before']),
                  Pair(Symbol('FUTURE'), ['exact', 8])]
        output = self.put('blocks', [self.put('role', Symbol('DEVICE'), block) for block in blocks], source)
        output = self.put('ends', ['builder-endpoints'], output)
        cfg = [Pair(Symbol('FUTURE-RULE'), 2), Pair(Symbol('TEMPLATE'), 'old-template')]
        proof = self.call('EL:NetworkProofMake', source, output, cfg, 'P', None)
        self.assertTrue(truth(proof))
        self.assertEqual(self.get('version', proof), 4)
        self.assertIsNone(self.get('template', self.get('config', proof)))
        mutations = [self.put('future', ['exact', 9], output),
                     self.put('blocks', [self.put('future-block-field', ['changed'], blocks[0]), blocks[1]], output),
                     self.put('new-unknown-key', 'never-drop', output)]
        # Unknown additional top-level rows are intentionally outside input-keys
        # in the legacy proof; changed existing unknown fields must be rejected.
        for changed in mutations[:2]:
            self.assertIsNone(self.call('EL:NetworkProofMake', source, changed, cfg, 'P', None))
        # Keep the original oracle's exact input-key projection for added rows.
        added = self.call('EL:NetworkProofMake', source, mutations[2], cfg, 'P', None)
        self.assertTrue(truth(added))
        output_blocks = self.get('blocks', output)
        changed_block = self.put('new-unknown-field', ['never-drop'], output_blocks[0])
        self.assertIsNone(self.call('EL:NetworkProofMake', source,
                                    self.put('blocks', [changed_block, output_blocks[1]], output), cfg, 'P', None))

    def test_large_unique_table_avoids_quadratic_role_search(self):
        size = 384
        blocks = [self.block(f'{i:06X}') for i in range(size)]
        roles = [Pair(self.get('id', block), Pair(Symbol('ROLE'), Symbol('PANEL')))
                 for block in blocks]
        baseline = [Pair(Symbol('BLOCKS'), blocks), Pair(Symbol('ENDS'), None),
                    Pair(Symbol('FUTURE'), True)]
        proof = self.proof(roles)
        comparisons = [0]
        original_assoc = self.h.builtins['ASSOC']
        original_equal = self.h.builtins['EQUAL']
        original_less = self.h.builtins['<']
        original_numeric_equal = self.h.builtins['=']

        def assoc(key, rows):
            if isinstance(key, str) and not isinstance(key, Symbol):
                for row in seq(rows):
                    comparisons[0] += 1
                    if equal(car(row), key):
                        return row
                return None
            return original_assoc(key, rows)

        def exact(*args):
            comparisons[0] += 1
            return original_equal(*args)

        def less(*args):
            comparisons[0] += 1
            return original_less(*args)

        def numeric_equal(*args):
            comparisons[0] += 1
            return original_numeric_equal(*args)

        self.h.builtins.update({'ASSOC': assoc, 'EQUAL': exact, '<': less, '=': numeric_equal})
        expected = self.call('TEST:LegacyNetworkProofInput', baseline, proof)
        old_count = comparisons[0]
        comparisons[0] = 0
        actual = self.call('EL:NetworkProofInput', baseline, proof)
        self.assertEqual(actual, expected)
        self.assertGreaterEqual(old_count, size*(size+1)//2)
        self.assertLess(comparisons[0], size*20)
        self.assertLess(comparisons[0]*8, old_count)
        type(self).work_evidence = {'blocks': size, 'legacy_comparisons': old_count,
                                   'ordered_comparisons': comparisons[0], 'equal_output': True}

    def test_empty_batches_and_phase_calls_are_bounded_by_proof_not_block_count(self):
        stages = []
        self.h.builtins['EL:PERFCALL'] = lambda stage, function, arguments: (
            stages.append(stage), self.h.call(function, seq(arguments)))[1]
        for count in (0, 31):
            stages.clear()
            self.counts.clear()
            source = [Pair(Symbol('BLOCKS'), [self.block(str(i)) for i in range(count)] or None),
                      Pair(Symbol('ENDS'), None)]
            self.assertTrue(truth(self.call('EL:NetworkProofMake', source, source, None, 'P', None)))
            self.assertEqual(stages, ['NETWORK_PROOF_STABLE_INPUT', 'NETWORK_PROOF_STABLE_OUTPUT',
                                      'NETWORK_PROOF_CONTACTS', 'NETWORK_ROLE_RESTORE',
                                      'NETWORK_PROOF_COMPARE'])
            self.assertEqual(self.counts, [('network-role-blocks', count),
                                          ('network-role-ordered-batches', 1)])

    def test_real_batch_timers_keep_parent_identity_and_leave_no_pending_frames(self):
        clock = [0]
        self.h.builtins['GETVAR'] = lambda key: clock[0] if key == 'MILLISECS' else 20261021.12
        for name, cost in (('EL:StableSnapshot', 3), ('EL:DeviceContactEvidence', 5),
                           ('EL:NetworkRestoreRoles', 7)):
            original = Symbol('TEST:' + name.split(':', 1)[1].upper())
            self.h.functions[original] = self.h.functions[Symbol(name.upper())]

            def measured(*args, function=original, advance=cost):
                clock[0] += advance
                return self.h.call(function, list(args))

            self.h.builtins[name.upper()] = measured
        source = [Pair(Symbol('BLOCKS'), [self.block('A')]), Pair(Symbol('ENDS'), None)]
        self.call('EL:PerfStart', 'ELSTAT')
        proof = self.call('EL:PerfCall', 'NETWORK_PROOF_PREPARE', Symbol('EL:NETWORKPROOFMAKE'),
                          [source, source, None, 'P', None])
        self.assertTrue(truth(proof))
        expected = {'NETWORK_PROOF_PREPARE': 18, 'NETWORK_PROOF_STABLE_INPUT': 3,
                    'NETWORK_PROOF_STABLE_OUTPUT': 3, 'NETWORK_PROOF_CONTACTS': 5,
                    'NETWORK_ROLE_RESTORE': 7, 'NETWORK_PROOF_COMPARE': 0}
        stages = self.h.lookup('*EL:PERFSTAGES*')
        for name, duration in expected.items():
            stage = self.call('EL:Get', name, stages)
            self.assertEqual(self.get('calls', stage), 1, name)
            self.assertEqual(self.get('inclusive-ms', stage), duration, name)
        records = self.h.lookup('*EL:MONITORROWS*')
        parent = next(row for row in records if self.get('stage', row) == 'NETWORK_PROOF_PREPARE')
        for row in records:
            if self.get('stage', row) in expected and self.get('stage', row) != 'NETWORK_PROOF_PREPARE':
                self.assertEqual(self.get('parent-id', row), self.get('id', parent))
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))


if __name__ == '__main__':
    unittest.main()
