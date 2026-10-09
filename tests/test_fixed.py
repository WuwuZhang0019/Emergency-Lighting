"""Fixed diagram pure-function checks. Date: 2026-10-09."""
import unittest
from autolisp_host import truth
import test_kernel as kernel

class FixedTests(unittest.TestCase):
    setUp = kernel.KernelTests.setUp
    generation_fixture = kernel.KernelTests.generation_fixture
    check_lisp = kernel.KernelTests.check_lisp

    def fixture(self):
        self.h.load_definitions(__import__('pathlib').Path(__file__).resolve().parents[1]/'src/fixed.lsp')
        self.generation_fixture()
        self.h.run('''(setq template (EL:Put 'panel (EL:Put 'name "dfgjhdrtyjtfgj4SADFG3" (EL:Get 'panel template))
          (EL:Put 'circuit (EL:Put 'name "fghjftyuk" (EL:Get 'circuit template)) template)))''')

    def test_fixed_coordinates_reserves_and_rotation(self):
        self.fixture()
        self.check_lisp('''(setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))
          (setq rows (EL:Get 'rows plan))
          (and (= (length rows) 4) (equal (EL:Get 'position (car rows)) '(6427.0 -5500.0 0.0))
            (equal (EL:Get 'text-position (car rows)) '(17063.0 -5938.0 0.0))
            (equal (EL:Get 'text (car rows)) "120W") (not (EL:Get 'text (nth 2 rows)))
            (not (EL:Get 'watts (nth 2 rows)))
            (equal (EL:Get 'position (car (EL:Get 'rows (EL:FixedPlan result template 'cap300
              '(100.0 200.0 0.0) (/ pi 2.0) 2.0)))) '(11100.0 13054.0 0.0) 0.000001)
            (equal (EL:Get 'text-position (car (EL:Get 'rows (EL:FixedPlan result template 'cap300
              '(100.0 200.0 0.0) (/ pi 2.0) 2.0)))) '(11976.0 34326.0 0.0) 0.000001))''')

    def test_n_counts_and_invalid_result(self):
        self.fixture()
        for n in (1,3,10):
            self.h.run(f"(setq cs nil i 0) (repeat {n} (setq i (1+ i) cs (cons (list (cons 'id (itoa i)) (cons 'watts i)) cs)))")
            self.check_lisp(f"(= (length (EL:Get 'rows (EL:FixedPlan (EL:Put 'circuits cs result) template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))) {n+2})")
        self.check_lisp("(not (EL:FixedPlan (EL:Put 'circuits nil result) template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))")
