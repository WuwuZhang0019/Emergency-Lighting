"""Generation rejection details and grouped power guidance. Date: 2026-10-12."""
import unittest
from pathlib import Path
from autolisp_host import Host, Symbol
from test_diagram_store import dump

class GenerationReasonsTests(unittest.TestCase):
    def setUp(self):
        self.h=Host()
        for name in ('common','config','geometry','device-library','device-ui','panel'):
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
        self.assertIn('单个功率',lines[0]); self.assertIn('A1',lines[0]); self.assertIn('UNSUPPORTED_GEOMETRY',lines[1])

    def test_rejection_is_visible_and_logged(self):
        alerts=[]; logs=[]; tiles=[]
        self.h.builtins.update({'ALERT':alerts.append,'EL:LOGEVENT':lambda *args:logs.append(args),
            'EL:PANELTEXT':lambda *args:tiles.append(args)})
        self.h.run("(EL:PanelGenerationBlocked '((circuits ((power-complete . nil)))) )")
        self.assertIn('回路1',alerts[0]); self.assertEqual(logs[0][0],'GENERATION_BLOCKED')
        self.assertIn('回路1',tiles[0][1])

    def reported(self, types=6):
        blocks, circuits = [], []
        for circuit_index in range(3):
            issues = []
            for kind in range(types):
                name = f'$equip_U${kind:08d}(Zhangyufeng)'
                ids = [f'D{circuit_index}-{kind}-{i}' for i in range(3 if kind < 3 else 2)]
                for ident in ids:
                    blocks.append(self.h.run(f'\'((id . "{ident}") (name . "{name}"))'))
                    issues.append(self.h.run(f'\'((code . DEVICE_LIBRARY_UNKNOWN) (object . "{ident}") (detail . "{name}"))'))
                issues.append(self.h.run(f'\'((code . POWER_MISSING_OR_INVALID) (object {" ".join(chr(34)+i+chr(34) for i in ids)}) (detail "{name}" nil "block-name-v1"))'))
            circuits.append(self.h.call('EL:PUT', [Symbol('POWER-ISSUES'), issues, None]))
        result = self.h.call('EL:PUT', [Symbol('CIRCUITS'), circuits, None])
        return self.h.call('EL:PUT', [Symbol('SNAPSHOT'), [[Symbol('BLOCKS'), *blocks]], result])

    def test_45_instances_and_both_validators_produce_six_rows_across_three_circuits(self):
        result = self.reported()
        rows = self.h.call('EL:GENERATIONMISSING', [result])
        self.assertEqual(len(rows), 6)
        self.assertEqual(sum(len(self.h.call('EL:GET', [Symbol('IDS'), r])) for r in rows), 45)
        lines = self.h.call('EL:GENERATIONPROBLEMS', [result])
        self.assertEqual(len(lines), 6)
        self.assertTrue(all('回路 1;2;3' in line for line in lines))
        self.assertTrue(all('block-name-v1' not in line and 'nil' not in line for line in lines))

    def test_dialog_is_bounded_but_full_connection_details_remain_in_log(self):
        result = self.reported(15)
        alerts, logs = [], []
        self.h.builtins.update({'ALERT': alerts.append, 'EL:LOGEVENT': lambda *args: logs.append(args),
            'EL:PANELTEXT': lambda *args: None, 'EL:PANELGENERATIONFOCUS': lambda *args: None})
        self.h.call('EL:PANELGENERATIONBLOCKED', [result])
        self.assertIn('15 种设备', alerts[0])
        self.assertIn('另有 5 项', alerts[0])
        reasons = self.h.call('EL:GET', [Symbol('REASONS'), logs[0][1]])
        self.assertEqual(len(reasons), 15)
        self.assertLess(len(alerts[0].splitlines()), 17)

    def test_missing_power_summary_does_not_hide_connection_fault_or_power_limit(self):
        result = self.reported()
        circuits = self.h.call('EL:GET', [Symbol('CIRCUITS'), result])
        faults = self.h.run('\'(((code . CLOSED_CIRCUIT) (object . "WIRE7")) ((code . POWER_OVER_LIMIT) (object . "DEVICE7")))')
        circuits[0] = self.h.call('EL:PUT', [Symbol('ISSUES'), faults, circuits[0]])
        result = self.h.call('EL:PUT', [Symbol('CIRCUITS'), circuits, result])
        lines = self.h.call('EL:GENERATIONPROBLEMS', [result])
        self.assertEqual(len(lines), 8)
        self.assertIn('WIRE7', lines[-2]); self.assertIn('超过172W', lines[-1])
