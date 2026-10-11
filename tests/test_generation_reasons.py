"""Generation rejection details. Date: 2026-10-11."""
import unittest
from pathlib import Path
from autolisp_host import Host, Symbol
from test_diagram_store import dump

class GenerationReasonsTests(unittest.TestCase):
    def setUp(self):
        self.h=Host()
        for name in ('common','panel'):
            self.h.load_definitions(Path(__file__).resolve().parents[1]/'src'/f'{name}.lsp')
        self.h.builtins['VL-PRIN1-TO-STRING']=dump

    def test_connection_failure_names_circuit_and_objects(self):
        lines=self.h.run("(EL:GenerationProblems '((circuits ((watts . 90) (issues ((code . CLOSED_CIRCUIT) (object . \"21FA\") (detail . \"2220\")))) ((watts . 20) (power-complete . T)))))")
        self.assertEqual(len(lines),1)
        for value in ('回路1','闭合连接','21FA','2220'): self.assertIn(value,lines[0])
        self.assertNotIn('超过172W', lines[0])

    def test_power_failure_and_snapshot_failure_both_visible(self):
        lines=self.h.run("(EL:GenerationProblems '((circuits ((power-issues ((code . POWER_MISSING_OR_INVALID) (object . \"A1\"))))) (snapshot (issues ((code . UNSUPPORTED_GEOMETRY) (object . \"W1\"))))))")
        self.assertEqual(len(lines),2)
        self.assertIn('功率缺失',lines[0]); self.assertIn('UNSUPPORTED_GEOMETRY',lines[1])

    def test_rejection_is_visible_and_logged(self):
        alerts=[]; logs=[]; tiles=[]
        self.h.builtins.update({'ALERT':alerts.append,'EL:LOGEVENT':lambda *args:logs.append(args),
            'EL:PANELTEXT':lambda *args:tiles.append(args)})
        self.h.run("(EL:PanelGenerationBlocked '((circuits ((power-complete . nil)))) )")
        self.assertIn('回路1',alerts[0]); self.assertEqual(logs[0][0],'GENERATION_BLOCKED')
        self.assertIn('回路1',tiles[0][1])
