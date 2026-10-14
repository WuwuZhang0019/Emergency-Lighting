"""Date: 2026-10-15. Focused recognition, exact source and diagnostic regressions."""
import hashlib
import io
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUITES = [
    'test_recognition_fastpath', 'test_recognition_preset', 'test_gap_index',
    'test_signature_depth', 'test_diagnostics', 'test_circuit_number.NumberScopeTests',
    'test_reachable_network', 'test_network_reuse.NetworkReuseTests',
    'test_network_reuse.FreshNetworkSignatureTests',
    'test_fixed_source_signature.FixedSourceSignatureTests', 'test_circuit_starts',
    'test_junction_box.JunctionTests.test_registered_names_on_other_layers_survive_preset_filter',
]


if __name__ == '__main__':
    result = unittest.TextTestRunner(stream=io.StringIO()).run(
        unittest.defaultTestLoader.loadTestsFromNames(SUITES))
    failures = [{'case': case.id(), 'detail': '\n'.join(trace.splitlines()[-8:])}
                for case, trace in result.failures + result.errors]
    sources = [ROOT / 'src' / (name + '.lsp')
               for name in ('common', 'config', 'geometry', 'simple', 'circuit-number')]
    sources += [ROOT / 'tests/test_recognition_fastpath.py',
                ROOT / 'tests/fixtures/recognition-138-oracle.lsp',
                ROOT / 'tests/test_recognition_preset.py', Path(__file__).resolve()]
    report = {'date': '2026-10-15', 'status': 'passed' if result.wasSuccessful() else 'failed',
              'scope': 'Focused Python adapter checks, not native AutoCAD acceptance',
              'cases': result.testsRun, 'suites': SUITES, 'failures': failures,
              'sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sources}}
    output = ROOT / 'tests/evidence/2026-10-15-recognition-checks-139.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(not result.wasSuccessful())
