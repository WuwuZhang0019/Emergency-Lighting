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
          (and (equal (EL:Role "E" "box" cfg) 'panel)
               (equal (EL:Role "E" "arrow" cfg) 'leader)
               (equal (EL:Role "E" "lamp" cfg) 'device)
               (equal (EL:Role "E" "unknown" cfg) 'unknown))''')

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
               (EL:Get 'accepted (EL:ValidateGapPair a b (EL:Put 'blocks (list crossing) snap) cfg))
               (equal (EL:Get 'reason (EL:ValidateGapPair a b
                  (EL:Put 'wires '(((id . "path") (segments ((20.0 0.0 0.0) (30.0 0.0 0.0))))) snap) cfg)) 'BLOCKED_BY_DEVICE_OR_PATH))''')

    def test_complete_range_and_reverse_uniqueness(self):
        self.check_lisp('''
          (setq c (test:end "C" '(-0.2 0.0 0.0) '(1.0 0.0 0.0)))
          (setq snap (EL:Put 'ends (list a b c) snap) rows (EL:FindGapCandidates snap cfg))
          (and (= (length (EL:Get 'candidates (EL:By 'key (EL:Get 'key a) rows))) 1)
               (= (length (EL:Get 'candidates (EL:By 'key (EL:Get 'key b) rows))) 2)
               (not (EL:Get 'pairs (EL:BuildMutualPairs rows snap cfg))))''')
        self.check_lisp('''
          (setq b (EL:Put 'point '(20.0 0.0 0.0) b)
                c (test:end "C" '(180.0 0.0 0.0) '(-1.0 0.0 0.0)))
          (setq snap (EL:Put 'ends (list a b c) snap) rows (EL:FindGapCandidates snap cfg))
          (and (= (length (EL:Get 'candidates (EL:By 'key (EL:Get 'key a) rows))) 2)
               (not (EL:Get 'pairs (EL:BuildMutualPairs rows snap cfg))))''')

    def test_end_directions_repeated_vertices_and_arc(self):
        self.check_lisp('''
          (setq pts '((0.0 0.0 0.0) (0.0 0.0 0.0) (5.0 0.0 0.0) (5.0 8.0 0.0)))
          (and (equal (EL:Get 'direction (EL:MakeEnd "P" 'start pts '(0.0 0.0 0.0 0.0) "E")) '(-1.0 0.0 0.0))
               (equal (EL:Get 'direction (EL:MakeEnd "P" 'end pts '(0.0 0.0 0.0 0.0) "E")) '(0.0 1.0 0.0))
               (equal (EL:Get 'geometry (EL:MakeEnd "P" 'end pts '(0.0 0.0 1.0 0.0) "E")) 'UNSUPPORTED_END_GEOMETRY)
               (equal (EL:Get 'geometry (EL:MakeEnd "P" 'start '((0.0 0.0 0.0) (0.0 0.0 0.0)) '(0.0 0.0) "E")) 'INVALID_GEOMETRY))''')

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
               (equal (EL:Get 'code (car (EL:Get 'issues checked))) 'CIRCUIT_CONFLICT))''')

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

    def test_integrated_gap_excludes_both_equipment_attached_wires(self):
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
          (and (not (EL:Get 'complete result)) (not (EL:Get 'connections result))
               (not (EL:Get 'devices (car (EL:Get 'circuits result))))
               (member 'WIRE_ATTACHED_TO_EQUIPMENT
                 (mapcar '(lambda (issue) (EL:Get 'code issue)) (EL:Get 'issues (car (EL:Get 'circuits result))))))''')

    def test_power_defaults_and_precedence(self):
        self.check_lisp('''
          (setq identity '("lamp" nil "definition-v1"))
          (setq saved (list (cons 'identity identity) (cons 'category 'lighting) (cons 'display "应急照明")
                    (cons 'watts 7) (cons 'zero-confirmed nil)))
          (setq current (EL:Put 'watts 9 saved) library (EL:Put 'watts 6 saved))
          (and (= (EL:DefaultWatts 'lighting) 5) (= (EL:DefaultWatts 'sign) 1)
               (not (EL:DefaultWatts 'unknown))
               (= (EL:Get 'watts (EL:ResolvePower identity (list current) (list saved) (list library))) 9)
               (= (EL:Get 'watts (EL:ResolvePower identity nil (list saved) (list library))) 7)
               (= (EL:Get 'watts (EL:ResolvePower identity nil nil (list library))) 6)
               (not (EL:ResolvePower '("lamp" nil "changed-definition") nil (list saved) nil)))''')

    def test_integer_power_parser_and_zero_confirmation(self):
        for text in ['', '-1', '1.5', '5W', ' 5', '2147483648', 'NaN']:
            with self.subTest(text=text):
                self.assertIsNone(self.h.run(f'(EL:ParseWatts "{text}")'))
        for text, expected in [('0',0), ('172',172), ('0005',5), ('2147483647',2147483647)]:
            self.assertEqual(self.h.run(f'(EL:ParseWatts "{text}")'),expected)
        self.check_lisp('''
          (setq record '((display . "零功率说明") (category . other) (watts . 0)))
          (and (not (EL:PowerValid record)) (EL:PowerValid (EL:Put 'zero-confirmed T record))
               (not (EL:PowerValid (EL:Put 'watts 1.5 record)))
               (not (EL:PowerValid (EL:Put 'watts -1 record))))''')

    def test_power_171_172_173_and_incomplete(self):
        self.h.run('''
          (setq identity '("lamp" nil "definition-v1"))
          (setq blocks (list (list (cons 'id "D") (cons 'name "lamp") (cons 'identity identity) (cons 'role 'device))))
          (setq circuit '((id . "R1") (devices "D" "D") (complete . T)))
          (setq power (list (cons 'identity identity) (cons 'category 'lighting) (cons 'display "lamp") (cons 'watts 172)))''')
        for watts, expected in [(171,'PASS'),(172,'PASS'),(173,'OVER-LIMIT')]:
            status=self.h.run(f'''(EL:Get 'power-status (EL:CircuitStatistics circuit blocks nil
                (EL:Put 'powers (list (EL:Put 'watts {watts} power)) cfg) nil nil))''')
            self.assertEqual(str(status),expected)
        self.check_lisp('''
          (and (equal (EL:Get 'power-status (EL:CircuitStatistics circuit blocks nil cfg nil nil)) 'incomplete)
               (equal (EL:Get 'power-status (EL:CircuitStatistics (EL:Put 'complete nil circuit) blocks nil
                  (EL:Put 'powers (list power) cfg) nil nil)) 'incomplete)
               (= (length (EL:Get 'counts (EL:CircuitStatistics circuit blocks nil cfg nil nil))) 1))''')

    def test_conflicted_device_not_double_counted(self):
        self.check_lisp('''
          (setq identity '("lamp" nil "definition-v1"))
          (setq blocks (list (list (cons 'id "D") (cons 'name "lamp") (cons 'identity identity) (cons 'role 'device))))
          (setq circuits '(((id . "R1") (devices "D") (complete . T)) ((id . "R2") (devices "D") (complete . T))))
          (setq result (list (cons 'complete T) (cons 'circuits circuits) (cons 'snapshot (list (cons 'blocks blocks)))))
          (setq power (list (cons 'identity identity) (cons 'category 'lighting) (cons 'display "lamp") (cons 'watts 5)))
          (setq computed (EL:BoxStatistics result (EL:Put 'powers (list power) cfg) nil nil))
          (and (not (EL:Get 'can-generate computed)) (= (EL:Get 'box-watts computed) 0)
               (EL:Get 'device-conflicts computed))''')

    def test_120_watt_example_and_leader_exclusion(self):
        self.check_lisp('''
          (setq blocks nil ids nil powers nil)
          (foreach spec '(("lighting" lighting 20 5) ("sign" sign 12 1) ("exit" exit 8 1))
            (setq identity (list (car spec) nil "definition-v1") i 0)
            (setq powers (cons (list (cons 'identity identity) (cons 'category (cadr spec))
                  (cons 'display (car spec)) (cons 'watts (nth 3 spec))) powers))
            (repeat (nth 2 spec)
              (setq id (strcat (car spec) (itoa i)) i (1+ i) ids (cons id ids)
                    blocks (cons (list (cons 'id id) (cons 'name (car spec)) (cons 'identity identity) (cons 'role 'device)) blocks))))
          (setq blocks (cons '((id . "LEADER") (role . leader)) blocks))
          (setq circuit (list (cons 'id "R1") (cons 'devices (cons "LEADER" ids)) (cons 'complete T)))
          (setq computed (EL:CircuitStatistics circuit blocks nil (EL:Put 'powers powers cfg) nil nil))
          (and (= (EL:Get 'watts computed) 120) (= (length (EL:Get 'counts computed)) 3)
               (equal (EL:Get 'power-status computed) 'pass))''')

    def generation_fixture(self):
        self.h.run('''
          (setq contour '(((0.0 0.0 0.0) (5.0 0.0 0.0))))
          (setq annotation '((offset 3.0 4.0 0.0) (type . "TEXT") (style . "Standard")
                            (height . 2.0) (align . 0) (rotation . 0.0) (width . 0.0) (factor . 1.0) (oblique . 0.0)))
          (setq panelstates nil circuitstates nil)
          (foreach option '(cap300 cap600 cap1000)
            (setq panelstates (cons (list (cons 'option option) (cons 'value (vl-symbol-name option))
              (cons 'connection '(10.0 0.0 0.0)) (cons 'contour contour)) panelstates)))
          (foreach option '(normal ground reserve)
            (setq circuitstates (cons (list (cons 'option option) (cons 'value (vl-symbol-name option))
              (cons 'connection '(2.0 0.0 0.0)) (cons 'contour contour) (cons 'text annotation)) circuitstates)))
          (setq template (list (cons 'panel (list (cons 'name "BOX") (cons 'property "real-property")
              (cons 'definition "panel-definition") (cons 'states panelstates)))
            (cons 'circuit (list (cons 'name "CIRCUIT") (cons 'property "other-property")
              (cons 'definition "circuit-definition") (cons 'states circuitstates)))
            (cons 'step '(0.0 -10.0 0.0)) (cons 'actual-format "{回路编号} {设备数量摘要} 合计{回路功率W}W")
            (cons 'reserve-format "预留") (cons 'layer "EL-SYSTEM")))
          (setq result '((can-generate . T) (circuits
              ((id . "R1") (watts . 120) (counts ((name . "lamp") (display . "照明") (count . 20))))
              ((id . "R2") (watts . 50) (counts ((name . "sign") (count . 50)))))))
          (setq outputs '(((circuit-id . "R2") (label . "L2") (mode . ground))
                          ((circuit-id . "R1") (label . "L1") (mode . normal))
                          ((label . "RES1") (mode . reserve))))''')

    def test_generation_correspondence_order_reserve_and_text(self):
        self.generation_fixture()
        self.check_lisp('''
          (setq plan (EL:BuildGenerationPlan result template 'cap600 outputs '(100.0 200.0 0.0) 0.0 1.0))
          (setq rows (EL:Get 'rows plan))
          (and (EL:TemplateValid template) (= (length rows) 3)
               (= (EL:Get 'circuit-id (car rows)) "R2") (= (EL:Get 'value (car rows)) "GROUND")
               (= (EL:Get 'text (cadr rows)) "L1 照明×20 合计120W")
               (= (EL:Get 'text (caddr rows)) "预留") (not (EL:Get 'watts (caddr rows))))''')

    def test_actual_load_cannot_be_hidden_or_omitted(self):
        self.generation_fixture()
        self.check_lisp('''
          (and (not (EL:BuildGenerationPlan result template 'cap300 (cdr outputs) '(0.0 0.0 0.0) 0.0 1.0))
               (not (EL:BuildGenerationPlan result template 'cap300
                 (cons (EL:Put 'mode 'reserve (car outputs)) (cdr outputs)) '(0.0 0.0 0.0) 0.0 1.0))
               (not (EL:BuildGenerationPlan result template 'cap300
                 (cons (EL:Put 'label "L1" (car outputs)) (cdr outputs)) '(0.0 0.0 0.0) 0.0 1.0))
               (not (EL:BuildGenerationPlan (EL:Put 'can-generate nil result) template 'cap300 outputs '(0.0 0.0 0.0) 0.0 1.0)))''')

    def test_rotated_scaled_output_positions(self):
        self.generation_fixture()
        self.check_lisp('''
          (setq plan (EL:BuildGenerationPlan result template 'cap1000 outputs '(100.0 200.0 0.0) (/ pi 2.0) 2.0))
          (setq row (car (EL:Get 'rows plan)))
          (and (equal (EL:Get 'position row) '(100.0 216.0 0.0) 0.000001)
               (equal (EL:Get 'text-position row) '(92.0 222.0 0.0) 0.000001)
               (equal (EL:InversePoint '(4.0 18.0 0.0) '(0.0 -2.0 -3.0 0.0 10.0 20.0 0.0 1.0)) '(1.0 2.0 0.0)))''')

    def test_template_tokens_and_stale_recognition_rules(self):
        self.check_lisp('''
          (setq result (list (cons 'drawing "test") (cons 'rules (EL:RecognitionRules cfg)) (cons 'snapshot snap)))
          (and (EL:FormatValid "{回路编号} 合计{回路功率W}W")
               (not (EL:FormatValid "{unknown} {回路功率W}W"))
               (not (EL:FormatValid "无功率字段")) (EL:SourceCurrent result cfg snap)
               (EL:SourceCurrent result (EL:Put 'powers '(updated) cfg) snap)
               (not (EL:SourceCurrent result (EL:Put 'params (EL:Put 'eps_touch 0.2 p) cfg) snap))
               (not (EL:SourceCurrent result cfg (EL:Put 'signature "changed-source" snap))))''')

    def test_three_independent_outlets_and_unrelated_open_end(self):
        self.check_lisp('''
          (defun test:wire (id points)
            (list (cons 'id id) (cons 'layer "E") (cons 'segments (EL:Segments points))
              (cons 'ends (list (EL:MakeEnd id 'start points '(0.0 0.0) "E") (EL:MakeEnd id 'end points '(0.0 0.0) "E")))))
          (setq wires nil blocks nil ends nil i 0 identity '("lamp" nil "definition-v1"))
          (foreach y '(10.0 20.0 30.0)
            (setq i (1+ i) wire (test:wire (strcat "W" (itoa i)) (list (list 0.0 y 0.0) (list 50.0 y 0.0)))
                  wires (cons wire wires) ends (append ends (EL:Get 'ends wire)))
            (setq blocks (cons (list (cons 'id (strcat "D" (itoa i))) (cons 'role 'device) (cons 'name "lamp")
              (cons 'identity identity) (cons 'segments (list (list (list 50.0 (- y 1.0) 0.0) (list 50.0 (+ y 1.0) 0.0))))) blocks)))
          (setq blocks (cons '((id . "BOX") (role . panel) (segments ((0.0 0.0 0.0) (0.0 40.0 0.0)))) blocks)
                ends (cons (test:end "unrelated" '(10000.0 10000.0 0.0) '(1.0 0.0 0.0)) ends))
          (setq local (list (cons 'wires wires) (cons 'blocks blocks) (cons 'ends ends) (cons 'signature "three-circuits")))
          (setq physical (EL:BuildPhysical local cfg "BOX") seeds (EL:SeedCandidates (EL:Get 'snapshot physical) cfg "BOX"))
          (setq result (EL:AnalyzeSnapshot local cfg "BOX" seeds))
          (setq power (list (cons 'identity identity) (cons 'category 'lighting) (cons 'display "lamp") (cons 'watts 5)))
          (setq computed (EL:BoxStatistics result (EL:Put 'powers (list power) cfg) nil nil))
          (and (= (length seeds) 3) (= (length (EL:Get 'circuits result)) 3) (EL:Get 'complete result)
               (EL:Get 'unrelated-issues result) (EL:Get 'can-generate computed) (= (EL:Get 'box-watts computed) 15))''')

    def test_multiple_gaps_only_pair_equipment_free_middle_wires(self):
        self.check_lisp('''
          (setq wires nil ends nil i 0)
          (foreach interval '((0.0 10.0) (30.0 40.0) (115.0 125.0) (305.0 315.0))
            (setq i (1+ i) id (strcat "W" (itoa i))
                  points (list (list (car interval) 0.0 0.0) (list (cadr interval) 0.0 0.0)))
            (setq wire (list (cons 'id id) (cons 'segments (EL:Segments points)) (cons 'ends
              (list (EL:MakeEnd id 'start points '(0.0 0.0) "E") (EL:MakeEnd id 'end points '(0.0 0.0) "E"))))
                  wires (cons wire wires) ends (append ends (EL:Get 'ends wire))))
          (setq blocks '(((id . "BOX") (role . panel) (segments ((0.0 -2.0 0.0) (0.0 2.0 0.0))))
                        ((id . "LAMP") (role . device) (segments ((315.0 -2.0 0.0) (315.0 2.0 0.0))))))
          (setq local (list (cons 'wires wires) (cons 'ends ends) (cons 'blocks blocks) (cons 'signature "three-gaps")))
          (setq result (EL:AnalyzeSnapshot local cfg "BOX" '(((id . "R1") (wire . "W1")))))
          (and (not (EL:Get 'complete result)) (= (length (EL:Get 'connections result)) 1)
               (not (EL:Get 'devices (car (EL:Get 'circuits result)))))''')

    def test_candidate_and_seed_order_do_not_change_decisions(self):
        self.check_lisp('''
          (setq first (EL:Get 'pairs (EL:BuildMutualPairs (EL:FindGapCandidates snap cfg) snap cfg)))
          (setq reversed (EL:Put 'ends (reverse (EL:Get 'ends snap)) snap))
          (and (equal first (EL:Get 'pairs (EL:BuildMutualPairs (EL:FindGapCandidates reversed cfg) reversed cfg)))
               (equal (EL:Get 'candidates (EL:By 'key (EL:Get 'key a) (EL:FindGapCandidates snap cfg)))
                      (EL:Get 'candidates (EL:By 'key (EL:Get 'key a) (EL:FindGapCandidates reversed cfg)))))''')

    def test_unverified_contour_is_a_veto_not_a_confirmed_connection(self):
        self.check_lisp('''
          (setq block '((id . "unsupported") (role . device) (bounds (-1.0 -1.0 0.0) (1.0 1.0 0.0))
                        (issues ((code . UNSUPPORTED_CONTOUR) (object . "unsupported")))))
          (setq local (EL:Put 'blocks (list block) snap) physical (EL:BuildPhysical local cfg nil))
          (and (EL:Get 'issues physical) (not (EL:Get 'edges physical))
               (EL:Get 'occupied (EL:By 'key (EL:Get 'key a) (EL:Get 'ends (EL:Get 'snapshot physical))))
               (EL:Get 'accepted (EL:ValidateGapPair a b (EL:Put 'blocks
                 (list (EL:Put 'bounds '((30.0 -1.0 0.0) (35.0 1.0 0.0)) block)) snap) cfg)))''')

    def test_plane_tolerance_for_physical_device_contacts(self):
        self.check_lisp('''
          (and (EL:Touches '(0.0 0.0 0.0) '(((0.0 -1.0 0.0) (0.0 1.0 0.0))) 0.1 0.01)
               (not (EL:Touches '(0.0 0.0 0.08) '(((0.0 -1.0 0.0) (0.0 1.0 0.0))) 0.1 0.01)))''')

    def test_missing_template_and_power_overflow_are_explicit(self):
        self.check_lisp('''
          (setq identity '("lamp" nil "definition-v1"))
          (setq blocks (list (list (cons 'id "D1") (cons 'name "lamp") (cons 'identity identity) (cons 'role 'device))
                             (list (cons 'id "D2") (cons 'name "lamp") (cons 'identity identity) (cons 'role 'device))))
          (setq power (list (cons 'identity identity) (cons 'category 'lighting) (cons 'display "lamp") (cons 'watts 2147483647)))
          (setq computed (EL:CircuitStatistics '((id . "R1") (devices "D1" "D2") (complete . T)) blocks nil
                             (EL:Put 'powers (list power) cfg) nil nil))
          (and (not (EL:TemplateRuntimeValid nil cfg)) (equal (EL:Get 'power-status computed) 'incomplete)
               (equal (EL:Get 'code (car (EL:Get 'power-issues computed))) 'POWER_OVERFLOW))''')

    def test_library_schema_rejects_unknown_fields_and_invalid_power(self):
        self.check_lisp('''
          (setq identity '("lamp" nil "definition-v1"))
          (setq power (list (cons 'identity identity) (cons 'category 'lighting) (cons 'display "lamp") (cons 'watts 7)))
          (setq library (list (cons 'version 1) (cons 'devices (list power))))
          (and (EL:LibraryValid library) (not (EL:LibraryValid (EL:Put 'execute '(command "ERASE") library)))
               (not (EL:LibraryValid (EL:Put 'devices (list (EL:Put 'watts -1 power)) library))))''')

    def test_multiple_device_ports_and_return_to_same_device_are_not_terminal(self):
        self.check_lisp('''
          (setq e1 (EL:Put 'side 'start (EL:Put 'key '("A" start) a)))
          (setq e2 (EL:Put 'point '(0.0 1.0 0.0) (test:end "B" '(0.0 0.0 0.0) '(1.0 0.0 0.0))))
          (setq e3 (EL:Put 'side 'start (EL:Put 'key '("B" start)
                        (test:end "B" '(0.0 -1.0 0.0) '(-1.0 0.0 0.0)))))
          (setq local (list (cons 'ends (list e1 e2 e3))
             (cons 'blocks '(((id . "D") (role . device) (segments ((0.0 -2.0 0.0) (0.0 2.0 0.0))))))))
          (setq physical (EL:BuildPhysical local cfg nil))
          (setq circuit (EL:TraceCircuit '((id . "R1") (wire . "A")) (EL:Get 'snapshot physical)
                              (EL:Get 'edges physical) (EL:Get 'issues physical)))
          (and (not (EL:Get 'complete circuit)) (EL:Get 'issues physical))''')


if __name__ == '__main__':
    unittest.main(verbosity=2)
