"""Date: 2026-10-14. Compare actual LISP work with v136; not native CAD timing."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
from time import perf_counter

from autolisp_host import Pair, Symbol, parse, truth
from test_store_split import SplitStoreTests

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '00da449'


def run(baseline):
    f = SplitStoreTests(); f.setUp()
    h = f.h
    for name in ('config', 'geometry', 'topology', 'statistics', 'generation', 'fixed', 'panel', 'diagram-update', 'diagram-commands'):
        h.load_definitions(ROOT / 'src' / f'{name}.lsp')
    h.builtins['EL:TEMPLATEREADY'] = lambda template, cfg: truth(template)
    h.step_limit = 100_000_000
    if baseline:
        for name in ('diagram-store', 'store-compact', 'store-split', 'diagram-commands'):
            source = subprocess.check_output(['git', 'show', f'{BASELINE}:src/{name}.lsp'],
                                             cwd=ROOT).decode('utf-8')
            for form in parse(source):
                if isinstance(form, list) and form[0] == 'DEFUN': h.evaluate(form)
    put = lambda key, value, row: f.call('EL:Put', Symbol(key.upper()), value, row)
    def record(identity, offset):
        rows = [[Pair(Symbol('HANDLE'), f'{i + offset:04X}'),
                 Pair(Symbol('LAYER'), '应急照明'),
                 [Symbol('POINTS'), [float(i), 1.e-98, 0.0], [float(i + 1), 1.0000000000000002, 0.0]],
                 [Symbol('MEMBERS'), 'W1', 'W2', 'D1'], Pair(Symbol('READY'), True)]
                for i in range(96)]
        signature = [Symbol('EL_FIXED_SOURCE_V1'), rows]
        return put('diagram-id', identity, put('source-signature', signature, h.lookup('RECORD1')))
    old = put('diagrams', [record('old-a', 0), put('panel-output-handle', 'old-output',
                          record('old-b', 1000))], h.lookup('STORE'))
    current_signature = f.get('source-signature', record('current', 2000))
    h.frames[0]['CURRENT_SIGNATURE'] = current_signature
    h.run('''(setq cfg '((template (name . "captured")))
      result (list '(panel . "P1") '(engine . fixed) '(can-generate . T)
        '(panel-number . "AL1") '(capacity-source . manual)
        '(circuits ((id . "R1") (seed-key "wire" outlet) (ground-source . default)))
        (list 'snapshot (cons 'signature current_signature))))''')
    # Identical final envelopes must still produce byte-for-byte equal DXF values.
    envelope = f.call('EL:SplitEnvelope', Symbol('BLOB'), current_signature)
    h.steps = 0
    wire = f.call('EL:StoreEncode', envelope)
    encode_steps = h.steps
    assert f.call('EL:StoreDecode', wire) == envelope
    assert truth(f.call('EL:StoreWriteMonolithic', old))
    raw = copy.deepcopy(f.call('EL:StorePayload', f.entities[f.dictionary['EL_FIXED_V1']]))
    counts = {'stage_builds': 0, 'serialized_fields': 0, 'serialized_blobs': 0,
              'characters_expanded': 0}
    original = h.call
    proposals = []
    def observe(name, args):
        if name == 'EL:STOREWRITE': proposals.append(copy.deepcopy(args[0]))
        if name == 'EL:SPLITBUILD': counts['stage_builds'] += 1
        if name == 'VL-STRING->LIST': counts['characters_expanded'] += len(args[0])
        result = original(name, args)
        if name == 'EL:STOREENCODE':
            counts['serialized_fields'] += len(result)
            if f.get('chunk-kind', args[0]) == Symbol('BLOB'): counts['serialized_blobs'] += 1
        return result
    h.call = observe
    h.steps = 0
    started = perf_counter()
    saved = f.call('EL:SaveDraft', h.lookup('RESULT'), h.lookup('CFG'),
                   [Pair('灯具', 5.25)], Symbol('CAP600'))
    counts['host_seconds'] = round(perf_counter() - started, 3)
    counts['host_evaluation_steps'] = h.steps
    counts['single_blob_encode_steps'] = encode_steps
    assert truth(saved) and len(proposals) == 1
    assert f.call('EL:StoreRead') == proposals[0]
    current = f.call('EL:DiagramForPanel', 'P1', proposals[0])
    assert f.get('draft-source-signature', current) == current_signature
    assert f.get('panel-output-handle', current) is None
    assert f.get('draft-capacity', current) == Symbol('CAP600')
    assert f.get('powers', current) == [Pair('灯具', 5.25)]
    assert bool(f.get('source-signature', current)) == baseline
    assert f.call('EL:StorePayload', f.entities[f.dictionary['EL_FIXED_MONOLITH_BACKUP']]) == raw
    return counts, wire


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before, old_wire = run(True)
    after, new_wire = run(False)
    assert old_wire == new_wire
    assert after['stage_builds'] == 1 and before['stage_builds'] == 2
    assert after['host_evaluation_steps'] < before['host_evaluation_steps']
    result = {'date': '2026-10-14', 'status': 'passed', 'baseline_commit': BASELINE,
              'scope': 'Python adapter executes real LISP; synthetic snapshots, not CAD seconds or original DWG',
              'fixture': 'actual SaveDraft after two historical outputs; 96 geometry rows per snapshot',
              'exact_final_wire_equal': True, 'exact_backup_and_reopen_equal': True,
              'baseline': before, 'candidate': after}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
