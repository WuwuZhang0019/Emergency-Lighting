"""Changed-circuit statistics and preview retention; Date: 2026-10-13."""
import unittest
from pathlib import Path
from autolisp_host import Host, Pair, Symbol
ROOT = Path(__file__).resolve().parents[1]

class ChangeScopeTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for module in ('common', 'geometry', 'statistics', 'panel'):
            self.h.load_definitions(ROOT / 'src' / (module + '.lsp'))
        self.h.run("""(setq cfg '((powers ((identity "A") (category . other) (display . "A") (watts . 5))
          ((identity "B") (category . other) (display . "B") (watts . 7))))
          result '((complete . T) (snapshot (blocks ((id . "D1") (identity "A") (name . "A") (role . device))
          ((id . "D2") (identity "B") (name . "B") (role . device)) ((id . "D3") (identity "A") (name . "A") (role . device))))
          (circuits ((id . "R1") (devices "D1") (complete . T))
          ((id . "R2") (devices "D2") (complete . T)) ((id . "R3") (devices "D3") (complete . T))))
          *EL:StatisticsScopeEnabled* T)""")
        self.calculated = []
        original = self.h.functions['EL:CIRCUITSTATISTICS']
        self.h.functions['TEST:ORIGINALSTATISTICS'] = original
        def compute(circuit, *args):
            self.calculated.append(self.get('id', circuit))
            return self.call('TEST:ORIGINALSTATISTICS', circuit, *args)
        self.h.builtins['EL:CIRCUITSTATISTICS'] = compute

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, data):
        return self.call('EL:Get', Symbol(key.upper()), data)

    def compute(self):
        return self.call('EL:BoxStatistics', self.h.lookup('RESULT'), self.h.lookup('CFG'), None, None)

    def test_power_change_recomputes_only_two_affected_circuits(self):
        self.compute()
        self.calculated.clear()
        self.h.run("(setq cfg (EL:Put 'powers (cons (EL:Put 'watts 9 (car (EL:Get 'powers cfg))) (cdr (EL:Get 'powers cfg))) cfg))")
        changed = self.compute()
        self.assertEqual(self.calculated, ['R1', 'R3'])
        self.assertEqual(self.get('box-watts', changed), 25)
        self.h.run('(setq *EL:StatisticsScopeEnabled* nil)')
        self.assertEqual(changed, self.compute()) # independent full calculation equality

    def test_template_and_repeat_reuse_but_rules_and_geometry_invalidate(self):
        self.compute(); self.calculated.clear()
        self.h.run("(setq cfg (EL:Put 'template '((output . custom)) cfg))")
        self.compute()
        self.assertEqual(self.calculated, [])
        self.h.run("(setq cfg (EL:Put 'params '((epsilon . 0.1)) cfg))")
        self.compute()
        self.assertEqual(self.calculated, ['R1', 'R2', 'R3'])
        self.calculated.clear()
        self.h.run("(setq result (EL:Put 'snapshot (EL:Put 'blocks (cons (EL:Put 'position '(1 2 3) (car (EL:Get 'blocks (EL:Get 'snapshot result)))) (cdr (EL:Get 'blocks (EL:Get 'snapshot result)))) (EL:Get 'snapshot result)) result))")
        self.compute()
        self.assertEqual(self.calculated, ['R1', 'R2', 'R3'])

    def test_exclusion_changes_conflict_dependencies_and_matches_full(self):
        self.compute(); self.calculated.clear()
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'devices nil (car (EL:Get 'circuits result))) (cdr (EL:Get 'circuits result))) result))")
        changed = self.compute()
        self.assertEqual(self.calculated, ['R1'])
        self.h.run('(setq *EL:StatisticsScopeEnabled* nil)')
        self.assertEqual(changed, self.compute())

if __name__ == '__main__': unittest.main()
