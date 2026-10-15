"""Date: 2026-10-15. Actual LISP work before/after v140, not native CAD seconds."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
from time import perf_counter

from autolisp_host import Pair, Symbol, parse, truth
from check_recognition_six_work import six_fixture
from check_store_read_work import exact
from test_store_split import SplitStoreTests

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '41b9c27'
MODULES = ('common', 'simple', 'diagram-store', 'diagram-update', 'diagram-commands')


def install_baseline(host):
    for module in MODULES:
        source = subprocess.check_output(['git', 'show', f'{BASELINE}:src/{module}.lsp'], cwd=ROOT).decode('utf-8')
        for form in parse(source):
            if isinstance(form, list) and form[0] == Symbol('DEFUN'):
                host.evaluate(form)


def measure(f, name, args):
    h = f.h
    counts, original = Counter(), h.call
    def observe(function, values):
        if isinstance(function, str):
            if function in h.functions:
                counts['lisp_calls'] += 1
            if function in ('EL:STOREENCODE', 'EL:STOREDECODE', 'EL:SIMPLECOLLECT',
                            'EL:WIRERECORDDXF', 'EL:SPATIALTREE', 'EL:ENTITYBOUNDS', 'ENTGET'):
                counts[function] += 1
        answer = original(function, values)
        if function == 'EL:STOREENCODE':
            counts['serialized_fields'] += len(answer)
        return answer
    h.steps = 0
    h.call = observe
    started = perf_counter()
    try:
        answer = f.call(name, *args)
    finally:
        counts['host_seconds'] = round(perf_counter() - started, 3)
        counts['host_evaluation_steps'] = h.steps
        h.call = original
    return answer, dict(counts)


def source_run(baseline):
    f = six_fixture(767, 483, 12)
    if baseline:
        install_baseline(f.h)
    f.call('EL:PerfStart', 'ELSTAT')
    result = f.call('EL:RecognizeFixed', f.cfg, 'panel')
    before = exact(result)
    f.call('EL:FreshBoundary')
    answer, counts = measure(f, 'EL:FreshResult', [result, f.cfg])
    assert truth(answer) and exact(result) == before
    counts['source_derived_reuses'] = f.call('EL:Get', 'source-derived-reuses', f.h.lookup('*EL:PERFMETRICS*')) or 0
    return result, counts


def store_run(baseline, result):
    f = SplitStoreTests(); f.setUp()
    h = f.h
    for module in ('config', 'geometry', 'topology', 'statistics', 'generation', 'fixed', 'panel', 'diagram-update', 'diagram-commands'):
        h.load_definitions(ROOT / 'src' / f'{module}.lsp')
    if baseline:
        install_baseline(h)
    h.step_limit = 150_000_000
    h.builtins['EL:TEMPLATEREADY'] = lambda template, cfg: truth(template)
    put = lambda key, value, data: f.call('EL:Put', Symbol(key.upper()), value, data)
    # The adapter represents CONS/CDR by Python list copies. Keep this tape
    # bounded; native AutoLISP cons cells do not have that quadratic host cost.
    geometry = [[Pair(Symbol('HANDLE'), f'W{i}'), Pair(Symbol('LAYER'), '应急照明'),
                 [Symbol('POINTS'), [float(i), 1.e-98, 0.],
                  [float(i+1), 1.0000000000000002, 0.]],
                 [Symbol('MEMBERS'), 'W1', 'W2', 'D1']] for i in range(96)]
    signature = [Symbol('EL_FIXED_SOURCE_V1'), [[Symbol('WIRES'), *geometry]]]
    result = put('snapshot', put('signature', signature, f.get('snapshot', result)), result)
    old_signature = [signature[0], put('previous-source', 1, signature[1])]
    rows = [put('panel-output-handle', f'previous-output-{i}',
                put('source-signature', old_signature,
                    put('source-panel-handle', f'P{i}',
                        put('diagram-id', f'old-{i}', h.lookup('RECORD1'))))) for i in range(1, 7)]
    old_store = put('diagrams', rows, h.lookup('STORE'))
    assert truth(f.get('committed', f.save(old_store)))
    result = put('panel', 'P1', result)
    cfg = h.run("'((template (name . \"captured\")))")
    # The real panel already read the current box before the click.
    f.call('EL:StoreForResult', result)
    saved, counts = measure(f, 'EL:SaveDraft', [result, cfg, [Pair('灯具', 5)], Symbol('CAP600')])
    assert truth(saved)
    actual = f.call('EL:StoreRead')
    for i in range(2, 7):
        assert exact(f.call('EL:DiagramForPanel', f'P{i}', actual)) == exact(rows[i-1])
    current = f.call('EL:DiagramForPanel', 'P1', actual)
    assert (f.get('draft-source-signature', current) is not None) == baseline
    assert f.get('draft-capacity', current) == Symbol('CAP600')
    assert exact(f.get('draft-circuits', current)) == exact(f.get('circuits', result))
    normalized = f.call('EL:InputRecord', current)
    counts['large_snapshot_persisted'] = bool(f.get('draft-source-signature', current))
    counts['other_five_box_records_exact'] = True
    return exact(normalized), counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    expected, source_before = source_run(True)
    print('baseline source check complete', flush=True)
    actual, source_after = source_run(False)
    assert exact(actual) == exact(expected)
    print('candidate source check complete', flush=True)
    old_inputs, store_before = store_run(True, expected)
    print('baseline input write complete', flush=True)
    new_inputs, store_after = store_run(False, actual)
    assert old_inputs == new_inputs
    assert source_after['source_derived_reuses'] == 1
    assert source_after['host_evaluation_steps'] < source_before['host_evaluation_steps']
    assert store_after['serialized_fields'] < store_before['serialized_fields']
    report = {'date': '2026-10-15', 'status': 'passed', 'baseline_commit': BASELINE,
              'scope': 'Real LISP in a finite Python adapter; counts are not original-DWG CAD timing',
              'fixture': {'circuits': 6, 'wires': 773, 'blocks': 556, 'connected_devices': 72,
                          'retained_other_boxes': 5, 'storage_snapshot_geometry_rows': 96},
              'exact_recognition_result_equal': True, 'exact_current_inputs_equal': True,
              'source_check': {'before': source_before, 'after': source_after},
              'first_input_write': {'before': store_before, 'after': store_after}}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
