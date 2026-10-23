"""AutoLISP NTH boundary regressions. Date: 2026-10-21. Status: current."""
import unittest

from autolisp_host import CaughtError, Host, Symbol


class NthTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()

    def test_nil_and_empty_list_are_errors(self):
        for expression in ('(nth 0 nil)', "(nth 0 'nil)", "(nth 0 '())",
                           '(nth 0 (list))', "(nth 0 (cdr '(only)))",
                           '(nth 0 (= 1 2))'):
            with self.subTest(expression=expression):
                with self.assertRaisesRegex(TypeError, 'bad argument type: consp nil'):
                    self.h.run(expression)

    def test_empty_adapter_list_has_same_error_as_nil(self):
        with self.assertRaisesRegex(TypeError, 'bad argument type: consp nil'):
            self.h.call(Symbol('NTH'), [0, []])

    def test_nonempty_list_is_zero_indexed(self):
        self.assertEqual(self.h.run("(nth 0 '(first second third))"), Symbol('FIRST'))
        self.assertEqual(self.h.run("(nth 2 '(first second third))"), Symbol('THIRD'))
        self.assertIsNone(self.h.run("(nth 0 '(nil second))"))

    def test_out_of_range_is_nil(self):
        self.assertIsNone(self.h.run("(nth 2 '(first second))"))
        self.assertIsNone(self.h.run("(nth 100 '(first second))"))

    def test_negative_index_cannot_select_python_tail(self):
        with self.assertRaises(TypeError):
            self.h.run("(nth -1 '(first second))")

    def test_noninteger_index_and_nonlist_are_errors(self):
        for expression in ("(nth 0.5 '(first second))", '(nth 0 "abc")'):
            with self.subTest(expression=expression):
                with self.assertRaises(TypeError):
                    self.h.run(expression)

    def test_catch_all_preserves_nil_argument_error(self):
        error = self.h.run("(vl-catch-all-apply 'nth (list 0 nil))")
        self.assertIsInstance(error, CaughtError)
        self.assertIsInstance(error.exception, TypeError)
        self.h.frames[0]['CAUGHT'] = error
        self.assertTrue(self.h.run('(vl-catch-all-error-p caught)'))
        self.assertEqual(self.h.run('(vl-catch-all-error-message caught)'),
                         'bad argument type: consp nil')


if __name__ == '__main__':
    unittest.main()
