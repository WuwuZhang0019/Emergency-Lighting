"""Long CAD record lists must not consume one stack frame per item. Date: 2026-10-09."""
import unittest
from pathlib import Path
from autolisp_host import Host, Pair, Symbol, equal


class SignatureDepthTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        self.h.load_definitions(Path(__file__).resolve().parents[1] / 'src/common.lsp')

    def test_long_geometry_list_preserves_all_items_without_recursive_tail(self):
        data = [[float(i), float(i + 1), 0.] for i in range(4000)]
        result = self.h.call(Symbol('EL:STABLEDATA'), [data])
        self.assertEqual(result, data)

    def test_dotted_pairs_nested_lists_empty_values_and_order_match_old_algorithm(self):
        self.h.run('''(defun test:old (data)
          (cond ((equal (type data) 'ENAME) (list 'handle (cdr (assoc 5 (entget data)))))
            ((listp data) (if data (cons (test:old (car data)) (test:old (cdr data))))) (T data)))''')
        for data in [None, [None, [1., 2.], '中文'], Pair(Symbol('KEY'), 4.),
                     Pair([1, 2], Pair([3, None], 'tail'))]:
            self.assertTrue(equal(self.h.call(Symbol('EL:STABLEDATA'), [data]),
                                  self.h.call(Symbol('TEST:OLD'), [data])))


if __name__ == '__main__':
    unittest.main()
