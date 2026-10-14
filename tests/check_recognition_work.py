"""Date: 2026-10-15. Execute real recognition before/after; no native CAD timing claim."""
import argparse
import json
from pathlib import Path
import subprocess
from time import perf_counter

from autolisp_host import Pair, Symbol, parse
from check_store_read_work import exact
import test_simple_flow as simple

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '520e46b'
MODULES = ('common', 'config', 'geometry', 'simple', 'circuit-number')


def install_baseline(host):
    for module in MODULES:
        source = subprocess.check_output(['git', 'show', f'{BASELINE}:src/{module}.lsp'], cwd=ROOT).decode('utf-8')
        for form in parse(source):
            if isinstance(form, list) and form[0] == 'DEFUN': host.evaluate(form)


def fixture(remote=48):
    f = simple.SimpleFlowTests(); f.setUp()
    for module in ('fixed', 'panel'):
        f.h.load_definitions(ROOT / 'src' / f'{module}.lsp')
    f.h.step_limit = 100_000_000
    f.block('BOX', 'P', 'panel', [0., 0., 0.])
    f.selected = ['panel']
    for index, points in enumerate(([[1., 0.], [7., 0.], [29., 0.]],
                                    [[0., 1.], [0., 7.], [0., 29.]])):
        handle = f'root-{index}'
        f.entities[handle] = [Pair(0, 'LWPOLYLINE'), Pair(5, handle), Pair(8, 'W'),
                              Pair(410, 'Model'), Pair(70, 0), Pair(38, 0.),
                              Pair(210, [0., 0., 1.]), *[Pair(10, p) for p in points]]
        f.selected.append(handle)
        for offset in (10., 20., 30.):
            device = f'device-{index}-{int(offset)}'
            f.block('LAMP', 'D', device, [offset, 0., 0.] if index == 0 else [0., offset, 0.])
            f.selected.append(device)
    for index in range(remote):
        x, y = 20000. + (index % 8) * 3000., 20000. + (index // 8) * 3000.
        handle, device = f'remote-wire-{index}', f'remote-device-{index}'
        f.line(handle, [x, y, 0.], [x + 9., y, 0.], 'W')
        f.block('LAMP', 'D', device, [x + 10., y, 0.])
        f.selected += [handle, device]
    f.h.builtins['VLAX-PROPERTY-AVAILABLE-P'] = lambda *_: True
    f.h.builtins['VLA-GET-EFFECTIVENAME'] = lambda e: next(p.cdr for p in f.entities[e] if p.car == 2)
    f.h.builtins['CHR'] = chr
    f.h.builtins['GETVAR'] = lambda key: 0 if key == 'MILLISECS' else None
    starts = [[Pair(Symbol('WIRE'), f'root-{i}'), Pair(Symbol('END'), Symbol('START')),
               Pair(Symbol('POINT'), [1., 0., 0.] if i == 0 else [0., 1., 0.])] for i in range(2)]
    for key, value in (('preset-scoped', True), ('auto-panel', 'panel'), ('circuit-starts', starts)):
        f.cfg = f.call('EL:Put', Symbol(key.upper()), value, f.cfg)
    return f


def run(baseline=False, remote=48):
    f = fixture(remote)
    h = f.h
    if baseline: install_baseline(h)
    f.call('EL:PerfStart', 'ELSTAT')
    h.frames[0].update({'*EL:LOGACTIVE*': True, '*EL:LOGSEQUENCE*': 0,
                       '*EL:PERFLOGSOFF*': True, '*EL:LOGVERBOSE*': None})
    counts = {'entity_reads': 0, 'effective_name_reads': 0, 'lisp_calls': 0,
              'prefix_slices': 0, 'number_shape_checks': 0}
    stages, original = {}, h.call

    def observe(name, args):
        named = isinstance(name, str)
        if named and name in h.functions: counts['lisp_calls'] += 1
        if name == 'ENTGET': counts['entity_reads'] += 1
        if name == 'VLA-GET-EFFECTIVENAME': counts['effective_name_reads'] += 1
        if name == ('EL:NUMBERPATHSLICE' if baseline else 'EL:NUMBERPATHSLICEMEASURED'):
            counts['prefix_slices'] += 1
        if name == ('EL:NUMBERSHAPEHIT' if baseline else 'EL:NUMBERSHAPEHITSTRICT'):
            counts['number_shape_checks'] += 1
        measured = named and name in ('EL:SIMPLECOLLECT', 'EL:SIMPLENETWORK', 'EL:SPLITNETWORK')
        before = h.steps
        result = original(name, args)
        if measured: stages[name] = h.steps - before
        return result

    h.call = observe
    h.steps = 0
    start = perf_counter()
    result = f.call('EL:RecognizeFixed', f.cfg, 'panel')
    counts.update({'host_seconds': round(perf_counter() - start, 3), 'host_evaluation_steps': h.steps,
                   'inclusive_stage_steps': stages})
    circuits = f.get('circuits', result)
    assert len(circuits) == 2
    assert sorted(sorted(f.get('devices', c)) for c in circuits) == [
        [f'device-{i}-{n}' for n in (10, 20, 30)] for i in range(2)]
    assert f.get('complete', result)
    return counts, exact(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before, expected = run(True)
    after, actual = run(False)
    assert actual == expected
    assert after['entity_reads'] < before['entity_reads']
    assert after['host_evaluation_steps'] < before['host_evaluation_steps']
    result = {'date': '2026-10-15', 'status': 'passed', 'baseline_commit': BASELINE,
              'scope': 'Actual RecognizeFixed in Python adapter; no prior result cache, synthetic drawing, not CAD seconds',
              'fixture': 'Two roots, six connected devices and 48 unrelated wire/device pairs; complete snapshots retained',
              'exact_complete_result_equal': True, 'baseline': before, 'candidate': after,
              'step_reduction_percent': round(100 * (1 - after['host_evaluation_steps'] /
                                                     before['host_evaluation_steps']), 1)}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
