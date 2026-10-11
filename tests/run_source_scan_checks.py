"""Source scan/network reuse evidence; native timing pending. Date: 2026-10-11."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Pair, Symbol, parse, quoted
from run_checks import RecordingResult
from test_network_reuse import NetworkReuseTests, ScanGenerationIntegrationTests

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    'test_network_reuse', 'test_simple_flow', 'test_concentrated_trunk',
    'test_freshness_reuse', 'test_generation_boundaries', 'test_fixed_source_signature',
    'test_device_contact', 'test_contact_reuse', 'test_contact_index', 'test_device_branches',
    'test_gap_index', 'test_analytic_curves', 'test_solid_contact', 'test_wire_width',
    'test_ocs_transforms', 'test_visibility_signature',
    'test_cckk_panel_command', 'test_diagram_update', 'test_incremental_updates',
    'test_post_stat_workflow', 'test_performance', 'test_store_context',
    'test_store_decode_cache', 'test_diagram_store', 'test_source_contracts', 'test_root_init',
)


def field(key, data):
    key = Symbol(key.upper())
    for row in data or []:
        if isinstance(row, Pair) and row.car == key:
            return row.cdr
        if isinstance(row, list) and row and row[0] == key:
            return row[1:] or None


def native_baseline(perf, trace):
    """Extract bounded totals only; no personal paths or raw drawing data saved."""
    if not perf:
        return None
    lines = perf.read_bytes().decode('gb18030').splitlines()
    report = quoted(parse(next(line.split('PERF | ', 1)[1]
        for line in reversed(lines) if line.startswith('PERF | ')))[0])
    assert field('package', report) == 'package-094.marker'
    baseline = {key: field(key, report) for key in ('package', 'program-ms', 'interaction-ms', 'after-placement')}
    baseline['after-placement'] = field('program-ms', baseline['after-placement'])
    stages = field('stages', report)
    baseline['stages'] = {}
    for name in ('FRESH_SOURCE_SCAN', 'SIMPLE_COLLECT', 'SIMPLE_NETWORK', 'STORE_DECODE'):
        row = next(row[1:] for row in stages if row[0] == name)
        baseline['stages'][name] = {key: field(key, row) for key in ('calls', 'program-ms')}
    if trace:
        content = trace.read_bytes().decode('gb18030')
        baseline['exact_readbacks'] = content.count('(EQUAL . T)')
        assert baseline['exact_readbacks'] >= 4  # Two routes per save.
    baseline['scope'] = 'native 094 new diagram; no optimized CAD timing recorded'
    return baseline


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-perf', type=Path)
    parser.add_argument('--baseline-trace', type=Path)
    args = parser.parse_args()
    baseline = native_baseline(args.baseline_perf, args.baseline_trace)
    checks = ROOT / 'output/cad2020-source-scan-check'
    checks.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(checks)
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordingResult).run(
        unittest.defaultTestLoader.loadTestsFromNames(MODULES))
    paths = sorted(list((ROOT / 'src').glob('*.lsp')) + list((ROOT / 'ui').glob('*.dcl')) +
        [ROOT / '.gitignore', ROOT / 'tools/build_cad2020.py', Path(__file__),
         ROOT / 'tests/autolisp_host.py', ROOT / 'tests/run_checks.py'] +
        [ROOT / 'tests' / (name + '.py') for name in MODULES])
    evidence = {
        'date': '2026-10-11', 'package': 95,
        'scope': 'fresh raw source and complete device geometry validation before command-scoped network reuse; unchanged source signature and generation/update/readback boundaries',
        'passed': result.wasSuccessful(), 'test_count': result.testsRun,
        'failure_count': len(result.failures), 'error_count': len(result.errors),
        'tests': sorted(result.records, key=lambda row: row['test']),
        'native_094_baseline': baseline,
        'work_measurements': {
            'five_unchanged_scans': getattr(NetworkReuseTests, 'work_evidence', None),
            'generation_scenarios': getattr(ScanGenerationIntegrationTests, 'integration_evidence', None),
        },
        'cad_status': '095 pending; finite adapter call counts are not native CAD elapsed times, real dynamic block, save/reopen or UNDO acceptance',
        'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    }
    path = ROOT / 'tests/evidence/2026-10-11-source-scan-095.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
