"""Date: 2026-10-14. Actual cold decoder work; synthetic data, not native CAD timing."""
import argparse
import json
from pathlib import Path
import subprocess
from time import perf_counter

from autolisp_host import Pair, Symbol, parse
import test_store_compact as compact

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '89bcd71'


def exact(value):
    """Distinguish integer/REAL, signed zero, symbols, strings and dotted tails."""
    if isinstance(value, Pair): return ('pair', exact(value.car), exact(value.cdr))
    if isinstance(value, list): return ('list', tuple(map(exact, value)))
    if type(value) is float: return ('real', value.hex())
    return (type(value).__name__, value)


def run(baseline, kind):
    f = compact.StoreCompactTests(); f.setUp()
    h = f.h
    h.step_limit = 100_000_000
    if baseline:
        source = subprocess.check_output(['git', 'show', f'{BASELINE}:src/store-compact.lsp'],
                                         cwd=ROOT).decode('utf-8')
        for form in parse(source):
            if isinstance(form, list) and form[0] == 'DEFUN': h.evaluate(form)
    if kind == 'mixed_geometry':
        rows = [[Pair(Symbol('HANDLE'), f'{i:04X}'), Pair(Symbol('LAYER'), '应急照明'),
                 [Symbol('POINTS'), [float(i), 1.e-98, -0.0],
                  [float(i + 1), 1.0000000000000002, 0.0]],
                 [Symbol('MEMBERS'), 'W1', 'W2', 'D1'], Pair(Symbol('READY'), True)]
                for i in range(160)]
    elif kind == 'integer_dense':
        rows = [[-2147483648, 2147483647, -i, i, None, True] * 6 for i in range(80)]
    else:
        rows = [[float(i), 1.e-98, -0.0, 1.0000000000000002] * 6 for i in range(80)]
    store = f.put('extension', rows, f.fixture())
    wire = f.call('EL:StoreEncode', store)
    original = h.call
    counts = {'lisp_function_calls': 0, 'lambda_calls': 0, 'native_read_calls': 0}
    stages = {}

    def observe(name, args):
        named = isinstance(name, str)
        if named and name in h.functions: counts['lisp_function_calls'] += 1
        if isinstance(name, list): counts['lambda_calls'] += 1
        if name == 'READ': counts['native_read_calls'] += 1
        measured = named and name in ('EL:STOREEXPAND', 'EL:COMPACTUNPACKINTEGERS')
        before = h.steps
        result = original(name, args)
        if measured: stages[name] = h.steps - before
        return result

    h.call = observe
    h.steps = 0
    start = perf_counter()
    restored = f.call('EL:StoreDecode', wire)
    counts['host_seconds'] = round(perf_counter() - start, 3)
    counts['host_evaluation_steps'] = h.steps
    counts['inclusive_stage_steps'] = stages
    assert exact(restored) == exact(store)
    return counts, exact(wire)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fixtures = {}
    for kind in ('mixed_geometry', 'integer_dense', 'real_dense'):
        before, old_wire = run(True, kind)
        after, new_wire = run(False, kind)
        assert old_wire == new_wire
        assert after['host_evaluation_steps'] < before['host_evaluation_steps']
        fixtures[kind] = {'baseline': before, 'candidate': after,
                         'exact_wire_and_typed_logical_values_equal': True,
                         'step_reduction_percent': round(100 * (1 - after['host_evaluation_steps'] /
                                                                 before['host_evaluation_steps']), 1)}
    result = {'date': '2026-10-14', 'status': 'passed', 'baseline_commit': BASELINE,
              'scope': 'Python adapter executes actual uncached LISP StoreDecode; synthetic fixtures, not original DWG or CAD seconds',
              'stage_note': 'Inclusive child stages must not be added to their parent',
              'fixtures': fixtures}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
