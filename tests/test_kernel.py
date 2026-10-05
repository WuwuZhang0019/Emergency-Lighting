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

    def test_global_seed_conflict_rejects_entire_component(self):
        self.check_lisp('''
          (setq pair (list (cons 'a (EL:Get 'key a)) (cons 'b (EL:Get 'key b)) (cons 'source 'auto)))
          (setq seeds '(((id . "R1") (wire . "A")) ((id . "R2") (wire . "B"))))
          (setq checked (EL:ValidatePairSet snap cfg nil (list pair) seeds))
          (and (not (EL:Get 'pairs checked)) (not (EL:Get 'edges checked))
               (= (EL:Get 'code (car (EL:Get 'issues checked))) 'CIRCUIT_CONFLICT))''')

    def test_endpoint_occupation_is_order_independent(self):
        self.check_lisp('''
          (setq c (test:end "C" '(100.0 0.0 0.0) '(-1.0 0.0 0.0)))
          (setq snap (EL:Put 'ends (list a b c) snap))
          (setq p1 (list (cons 'a (EL:Get 'key a)) (cons 'b (EL:Get 'key b))))
          (setq p2 (list (cons 'a (EL:Get 'key b)) (cons 'b (EL:Get 'key c))))
          (and (not (EL:Get 'pairs (EL:ValidatePairSet snap cfg nil (list p1 p2) nil)))
               (not (EL:Get 'pairs (EL:ValidatePairSet snap cfg nil (list p2 p1) nil))))''')

    def test_manual_reuse_requires_whole_snapshot(self):
        self.check_lisp('''
          (setq pair (list (cons 'a (EL:Get 'key a)) (cons 'b (EL:Get 'key b))
                  (cons 'drawing "test") (cons 'source 'manual) (cons 'signature "source-v1") (cons 'params p)))
          (setq cfg (EL:Put 'gap-pairs (list pair) cfg))
          (and (EL:Get 'pairs (EL:LoadValidGapPairs cfg snap))
               (not (EL:Get 'pairs (EL:LoadValidGapPairs cfg (EL:Put 'signature "new-interfering-line" snap))))
               (not (EL:Get 'pairs (EL:LoadValidGapPairs cfg (EL:Put 'ends (list a) snap)))))''')

    def test_manual_model_exception_keeps_global_restrictions(self):
        self.check_lisp('''
          (setq b (EL:Put 'point '(1000.0 30.0 0.0) b) snap (EL:Put 'ends (list a b) snap))
          (setq pair (list (cons 'a (EL:Get 'key a)) (cons 'b (EL:Get 'key b)) (cons 'source 'manual)))
          (and (EL:Get 'pairs (EL:ValidatePairSet snap cfg nil (list pair) '(((id . "R1") (wire . "A")))))
               (not (EL:Get 'pairs (EL:ValidatePairSet snap cfg nil (list pair)
                  '(((id . "R1") (wire . "A")) ((id . "R2") (wire . "B"))))))
               (not (EL:Get 'pairs (EL:ValidatePairSet (EL:Put 'ends (list a (EL:Put 'point '(1000.0 30.0 5.0) b)) snap)
                   cfg nil (list pair) nil))))''')

    def test_leader_pair_deleted_or_moved_never_complete(self):
        self.check_lisp('''
          (setq la '((id . "LA") (role . leader) (raw . "a-v1")))
          (setq lb '((id . "LB") (role . leader) (raw . "b-v1")))
          (setq snap (EL:Put 'blocks (list la lb) snap))
          (setq cfg (EL:Put 'leader-pairs '(((a . "LA") (b . "LB") (a-state . "a-v1") (b-state . "b-v1"))) cfg))
          (setq base '(("W1" "LA") ("W2" "LB")))
          (and (member '("LA" "LB") (EL:Get 'edges (EL:LeaderConnections snap cfg base)))
               (not (EL:Get 'issues (EL:LeaderConnections snap cfg base)))
               (EL:Get 'issues (EL:LeaderConnections (EL:Put 'blocks (list la (EL:Put 'raw "moved" lb)) snap) cfg base))
               (EL:Get 'issues (EL:LeaderConnections (EL:Put 'blocks (list la) snap) cfg base)))''')

    def test_integrated_gap_trace_and_unrelated_issues(self):
        self.check_lisp('''
          (setq pts1 '((0.0 0.0 0.0) (10.0 0.0 0.0)) pts2 '((30.0 0.0 0.0) (50.0 0.0 0.0)))
          (setq w1 (list (cons 'id "W1") (cons 'segments (EL:Segments pts1))
                    (cons 'ends (list (EL:MakeEnd "W1" 'start pts1 '(0.0 0.0) "E") (EL:MakeEnd "W1" 'end pts1 '(0.0 0.0) "E")))))
          (setq w2 (list (cons 'id "W2") (cons 'segments (EL:Segments pts2))
                    (cons 'ends (list (EL:MakeEnd "W2" 'start pts2 '(0.0 0.0) "E") (EL:MakeEnd "W2" 'end pts2 '(0.0 0.0) "E")))))
          (setq box '((id . "BOX") (role . panel) (segments ((0.0 -2.0 0.0) (0.0 2.0 0.0)))))
          (setq lamp '((id . "LAMP") (role . device) (segments ((50.0 -2.0 0.0) (50.0 2.0 0.0)))))
          (setq local (list (cons 'wires (list w1 w2)) (cons 'blocks (list box lamp))
                    (cons 'ends (append (EL:Get 'ends w1) (EL:Get 'ends w2))) (cons 'signature "baseline")))
          (setq result (EL:AnalyzeSnapshot local cfg "BOX" '(((id . "R1") (wire . "W1")))))
          (and (EL:Get 'complete result) (= (length (EL:Get 'connections result)) 1)
               (equal (EL:Get 'devices (car (EL:Get 'circuits result))) '("LAMP")))''')


if __name__ == '__main__':
    unittest.main(verbosity=2)
