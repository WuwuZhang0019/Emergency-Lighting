import pathlib
import unittest
from autolisp_host import Host, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for path in sorted((ROOT / 'src').glob('*.lsp')):
            self.h.load_definitions(path)

    def check_lisp(self, code):
        self.assertTrue(truth(self.h.run(code)), code)

    def test_config_validation_and_data_only(self):
        self.check_lisp('''
          (setq cfg (EL:DefaultConfig "drawing-a"))
          (and (EL:ConfigValid cfg "drawing-a")
               (not (EL:ConfigValid cfg "drawing-b"))
               (not (EL:ConfigValid (EL:Put 'execute '(command "ERASE") cfg) "drawing-a")))''')

    def test_same_layer_role_exclusion(self):
        self.check_lisp('''
          (setq cfg '((panel-layers "E") (device-layers "E") (leader-layers "E")
                      (panel-names "box") (leader-names "arrow") (device-names "lamp")))
          (and (= (EL:Role "E" "box" cfg) 'panel)
               (= (EL:Role "E" "arrow" cfg) 'leader)
               (= (EL:Role "E" "lamp" cfg) 'device)
               (= (EL:Role "E" "unknown" cfg) 'unknown))''')

    def test_parameters_and_symmetric_layers(self):
        self.check_lisp('''
          (setq p '((eps_touch . 0.1) (eps_boundary . 0.1) (eps_perp . 0.5)
                    (eps_z . 0.01) (theta_max . 0.01) (R0 . 20) (Dmax . 200)))
          (setq cfg '((wire-layers "A" "B") (layer-pairs ("A" "B"))))
          (and (EL:ParamsValid p) (not (EL:ParamsValid (EL:Put 'Dmax 0 p)))
               (not (EL:ParamsValid (EL:Put 'theta_max pi p)))
               (EL:LayerAllowed "A" "B" cfg) (EL:LayerAllowed "B" "A" cfg)
               (not (EL:LayerAllowed "A" "OTHER" cfg)))''')


if __name__ == '__main__':
    unittest.main(verbosity=2)
