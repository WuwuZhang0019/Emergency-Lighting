import pathlib
import unittest
import json
from autolisp_host import Host, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for path in sorted((ROOT / 'src').glob('*.lsp')):
            self.h.load_definitions(path)
        self.h.run('''
          (setq p '((eps_touch . 0.1) (eps_boundary . 0.1) (eps_perp . 0.5)
                    (eps_z . 0.01) (theta_max . 0.01) (R0 . 20) (Dmax . 200)))
          (setq cfg (EL:Put 'params p (EL:DefaultConfig "test")))
          (setq cfg (EL:Put 'wire-layers '("E") cfg))
          (defun test:end (id point direction)
            (list (cons 'key (list id 'end)) (cons 'wire id) (cons 'side 'end)
                  (cons 'point point) (cons 'direction direction) (cons 'geometry 'straight)
                  (cons 'layer "E")))
          (setq a (test:end "A" '(0.0 0.0 0.0) '(1.0 0.0 0.0)))
          (setq b (test:end "B" '(75.0 0.0 0.0) '(-1.0 0.0 0.0)))
          (setq snap (list (cons 'ends (list a b)) (cons 'signature "source-v1")))''')

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

    def test_variable_gaps_and_search_limit(self):
        fixture = json.loads((ROOT/'tests/fixtures/baseline.json').read_text())
        for length in fixture['gap_lengths']:
            with self.subTest(length=length):
                result = self.h.run(f'''(EL:Get 'accepted (EL:ValidateGapPair a
                    (EL:Put 'point '({length}.0 0.0 0.0) b) snap cfg))''')
                self.assertEqual(truth(result), length <= 200)

    def test_rejections_and_pi_boundary_rotation(self):
        self.check_lisp('''
          (and (not (EL:Get 'accepted (EL:ValidateGapPair a (EL:Put 'point '(75.0 2.0 0.0) b) snap cfg)))
               (not (EL:Get 'accepted (EL:ValidateGapPair a (EL:Put 'direction '(1.0 0.0 0.0) b) snap cfg)))
               (not (EL:Get 'accepted (EL:ValidateGapPair a (EL:Put 'point '(75.0 0.0 2.0) b) snap cfg)))
               (not (EL:Get 'accepted (EL:ValidateGapPair a (EL:Put 'geometry 'UNSUPPORTED_END_GEOMETRY b) snap cfg))))''')
        for angle in [-0.001, 0.001, 3.141, -3.141]:
            self.check_lisp(f'''
              (setq tdir (list (cos {angle}) (sin {angle}) 0.0))
              (EL:Get 'accepted (EL:ValidateGapPair (EL:Put 'direction tdir a)
                (EL:Put 'point (EL:V* 75.0 tdir) (EL:Put 'direction (EL:V* -1.0 tdir) b)) snap cfg))''')

    def test_crossing_allowed_device_and_collinear_path_block(self):
        self.check_lisp('''
          (setq crossing '((id . "cross") (segments ((30.0 -10.0 0.0) (30.0 10.0 0.0)))))
          (setq snap (EL:Put 'wires (list crossing) snap))
          (and (EL:Get 'accepted (EL:ValidateGapPair a b snap cfg))
               (= (EL:Get 'reason (EL:ValidateGapPair a b (EL:Put 'blocks (list crossing) snap) cfg)) 'BLOCKED_BY_DEVICE_OR_PATH)
               (= (EL:Get 'reason (EL:ValidateGapPair a b
                  (EL:Put 'wires '(((id . "path") (segments ((20.0 0.0 0.0) (30.0 0.0 0.0))))) snap) cfg)) 'BLOCKED_BY_DEVICE_OR_PATH))''')

    def test_complete_range_and_reverse_uniqueness(self):
        self.check_lisp('''
          (setq c (test:end "C" '(-0.2 0.4 0.0) '(1.0 0.0 0.0)))
          (setq snap (EL:Put 'ends (list a b c) snap) rows (EL:FindGapCandidates snap cfg))
          (and (= (length (EL:Get 'candidates (EL:By 'key (EL:Get 'key a) rows))) 1)
               (= (length (EL:Get 'candidates (EL:By 'key (EL:Get 'key b) rows))) 2)
               (not (EL:Get 'pairs (EL:BuildMutualPairs rows snap cfg))))''')
        self.check_lisp('''
          (setq b (EL:Put 'point '(20.0 0.0 0.0) b)
                c (test:end "C" '(180.0 0.4 0.0) '(-1.0 0.0 0.0)))
          (setq snap (EL:Put 'ends (list a b c) snap) rows (EL:FindGapCandidates snap cfg))
          (and (= (length (EL:Get 'candidates (EL:By 'key (EL:Get 'key a) rows))) 2)
               (not (EL:Get 'pairs (EL:BuildMutualPairs rows snap cfg))))''')

    def test_end_directions_repeated_vertices_and_arc(self):
        self.check_lisp('''
          (setq pts '((0.0 0.0 0.0) (0.0 0.0 0.0) (5.0 0.0 0.0) (5.0 8.0 0.0)))
          (and (equal (EL:Get 'direction (EL:MakeEnd "P" 'start pts '(0.0 0.0 0.0 0.0) "E")) '(-1.0 0.0 0.0))
               (equal (EL:Get 'direction (EL:MakeEnd "P" 'end pts '(0.0 0.0 0.0 0.0) "E")) '(0.0 1.0 0.0))
               (= (EL:Get 'geometry (EL:MakeEnd "P" 'end pts '(0.0 0.0 1.0 0.0) "E")) 'UNSUPPORTED_END_GEOMETRY)
               (= (EL:Get 'geometry (EL:MakeEnd "P" 'start '((0.0 0.0 0.0) (0.0 0.0 0.0)) '(0.0 0.0) "E")) 'INVALID_GEOMETRY))''')

    def test_rotation_mirror_nonuniform_nested_transform(self):
        self.check_lisp('''
          (setq m '(0.0 -2.0 -3.0 0.0 10.0 20.0 0.0 1.0))
          (setq n '(1.0 0.0 0.0 1.0 4.0 5.0 0.0 1.0))
          (and (equal (EL:AffinePoint '(1.0 2.0 0.0) m) '(4.0 18.0 0.0))
               (equal (EL:AffinePoint '(1.0 2.0 0.0) (EL:AffineCompose m n))
                 (EL:AffinePoint (EL:AffinePoint '(1.0 2.0 0.0) n) m) 0.000001))''')

    def test_physical_crossing_and_t_contact(self):
        self.check_lisp('''
          (setq w1 '((id . "W1") (segments ((-10.0 0.0 0.0) (10.0 0.0 0.0)))))
          (setq w2 '((id . "W2") (segments ((0.0 -10.0 0.0) (0.0 10.0 0.0)))))
          (setq e1 (test:end "W1" '(10.0 0.0 0.0) '(1.0 0.0 0.0)))
          (setq e2 (test:end "W2" '(0.0 10.0 0.0) '(0.0 1.0 0.0)))
          (setq local (list (cons 'wires (list w1 w2)) (cons 'ends (list e1 e2))))
          (and (not (EL:Get 'edges (EL:BuildPhysical local cfg nil)))
               (EL:Get 'issues (EL:BuildPhysical (EL:Put 'ends
                  (list (EL:Put 'point '(0.0 0.0 0.0) e1) e2) local) cfg nil)))''')

    def test_single_circuit_unique_device_and_terminal(self):
        self.check_lisp('''
          (setq local '((blocks ((id . "D") (role . device)))))
          (setq circuit (EL:TraceCircuit '((id . "C1") (wire . "W")) local '(("W" "D")) nil))
          (and (EL:Get 'complete circuit) (= (length (EL:Get 'devices circuit)) 1)
               (not (EL:Get 'complete (EL:TraceCircuit '((id . "C1") (wire . "W")) local
                 '(("W" "D")) (list (EL:Issue 'NO_CANDIDATE "W" nil))))))''')


if __name__ == '__main__':
    unittest.main(verbosity=2)
