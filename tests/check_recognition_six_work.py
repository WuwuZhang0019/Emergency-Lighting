"""Date: 2026-10-15. Six-circuit exact v139 comparison; adapter work, not CAD time."""
import argparse
from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess
from time import perf_counter

from autolisp_host import Pair, Symbol, parse
from check_recognition_work import ROOT, fixture
from check_store_read_work import exact

BASELINE = '2149cfa'
MODULES = ('common', 'geometry', 'simple', 'circuit-number', 'diagram-update', 'panel')


@lru_cache(None)
def baseline_forms(module):
    source = subprocess.check_output(['git', 'show', f'{BASELINE}:src/{module}.lsp'], cwd=ROOT).decode('utf-8')
    return [f for f in parse(source) if isinstance(f, list) and f[0] == 'DEFUN']


def install_baseline(host):
    for module in MODULES:
        for form in baseline_forms(module):
            host.evaluate(form)


def six_fixture(remote_wires=24, remote_blocks=24, devices_per_circuit=4):
    f = fixture(0)
    f.selected = ['panel']
    starts = []
    for i in range(6):
        direction = [math.cos(i * math.pi / 3), math.sin(i * math.pi / 3)]
        def point(distance):
            return [distance * direction[0], distance * direction[1], 0.]
        handle = f'root-{i}'
        distances = [1.5, 7.] + [17. + 10 * n for n in range(devices_per_circuit - 1)] + [10. * devices_per_circuit - 1.]
        points = [point(n)[:2] for n in distances]
        reverse = i % 2 == 1
        if reverse:
            points.reverse()
        f.entities[handle] = [Pair(0, 'LWPOLYLINE'), Pair(5, handle), Pair(8, 'W'),
            Pair(410, 'Model'), Pair(70, 0), Pair(38, 0.), Pair(210, [0., 0., 1.]),
            *[Pair(10, p) for p in points], [-3, ['linenum', Pair(1000, f'ZE{i + 1}')]]]
        f.selected.append(handle)
        starts.append([Pair(Symbol('WIRE'), handle), Pair(Symbol('END'), Symbol('END' if reverse else 'START')),
                       Pair(Symbol('POINT'), point(1.5))])
        for n in range(devices_per_circuit):
            device = f'active-{i}-{n}'
            f.block('LAMP', 'D', device, point(10. * (n + 1)))
            f.selected.append(device)
    for i in range(max(remote_wires, remote_blocks)):
        x, y = 20000. + (i % 32) * 3000., 20000. + (i // 32) * 3000.
        if i < remote_wires:
            wire = f'remote-wire-{i}'
            f.line(wire, [x, y, 0.], [x + 9., y, 0.], 'W')
            f.selected.append(wire)
        if i < remote_blocks:
            device = f'remote-device-{i}'
            f.block('LAMP', 'D', device, [x + 10., y, 0.])
            f.selected.append(device)
    f.cfg = f.call('EL:Put', Symbol('CIRCUIT-STARTS'), starts, f.cfg)
    return f


def recognize(f, baseline=False, check_devices=True):
    h = f.h
    if baseline:
        install_baseline(h)
    f.call('EL:PerfStart', 'ELSTAT')
    h.frames[0].update({'*EL:LOGACTIVE*': True, '*EL:LOGSEQUENCE*': 0,
                      '*EL:PERFLOGSOFF*': True, '*EL:LOGVERBOSE*': None})
    counts, stages, original = Counter(), {}, h.call
    observed = {'ENTGET': 'entity_reads', 'EL:DEVICEDEFINITIONCONTOUR': 'definition_reads',
                'EL:SIMPLEDEVICEPATHHIT': 'wire_device_checks', 'EL:STABLEDATA': 'stable_data_calls',
                'EL:BLOCKPOINTHIT': 'point_contact_checks'}
    def observe(name, args):
        named = isinstance(name, str)
        if named and name in h.functions:
            counts['lisp_calls'] += 1
        if named and name in observed:
            counts[observed[name]] += 1
        measured = named and name in ('EL:SIMPLECOLLECT', 'EL:SIMPLENETWORK', 'EL:SPLITNETWORK')
        before = h.steps
        result = original(name, args)
        if measured:
            stages[name] = h.steps - before
        return result
    h.call, h.steps = observe, 0
    started = perf_counter()
    result = f.call('EL:RecognizeFixed', f.cfg, 'panel')
    elapsed = perf_counter() - started
    steps = h.steps
    h.call = original
    circuits = f.get('circuits', result)
    assert len(circuits) == 6 and f.get('complete', result)
    expected = [[f'active-{i}-{n}' for n in range(sum(e.startswith(f'active-{i}-') for e in f.selected))]
                for i in range(6)]
    if check_devices:
        assert sorted(sorted(f.get('devices', c)) for c in circuits) == sorted(sorted(row) for row in expected)
    # Resolve labels after the measured recognition stage, as the panel does.
    resolved = f.call('EL:ResolveCircuitNumbers', result)
    assert all(f.get('number-status', c) == Symbol('READY') for c in f.get('circuits', resolved))
    counts.update({'host_evaluation_steps': steps, 'host_seconds': round(elapsed, 3)})
    return [result, resolved], {**counts, 'inclusive_stage_steps': stages}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    expected, before = recognize(six_fixture(767, 483, 12), True)
    actual, after = recognize(six_fixture(767, 483, 12))
    assert exact(actual) == exact(expected), 'complete typed recognition result differs'
    assert after['host_evaluation_steps'] < before['host_evaluation_steps']
    report = {'date': '2026-10-15', 'status': 'passed', 'baseline_commit': BASELINE,
              'scope': 'Cold full RecognizeFixed in Python adapter; not native AutoCAD seconds',
              'fixture': {'circuits': 6, 'connected_devices': 72, 'wires': 773, 'blocks': 556,
                          'description': 'Six radial polylines, alternating start/end selection, native ZE labels; unrelated remote geometry'},
              'exact_complete_result_equal': True, 'baseline': before, 'candidate': after,
              'step_reduction_percent': round(100 * (1 - after['host_evaluation_steps'] / before['host_evaluation_steps']), 1)}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
