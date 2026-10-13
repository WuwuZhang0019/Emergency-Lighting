"""CAD2020 directional starts package verification. Date: 2026-10-13."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import zipfile

from autolisp_host import Symbol, parse
import test_circuit_starts as starts
import test_circuit_number as numbers

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ('EL:FixedStatPick', 'EL:FixedStartPick', 'EL:PickCircuitStarts', 'EL:StartPickResumeResult',
             'EL:StartSnapshot', 'EL:SimpleNetworkBuild', 'EL:SplitNetwork', 'EL:NumberRootStation',
             'EL:ConfigValid', 'EL:RecognitionRules', 'EL:RecognizeFixed', 'EL:FixedFreshSnapshot',
             'EL:PanelStartInit', 'EL:PanelDialog', 'EL:PickButtonRuns', 'EL:TrunkButtonDraw')


def definitions(text):
    return {f[1]: f for f in parse(text)
            if isinstance(f,list) and f and f[0] == Symbol('DEFUN')}


def check():
    spec = importlib.util.spec_from_file_location('starts_builder',ROOT/'tools/build_cad2020.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    directory, archive = builder.DEST, builder.DEST.with_suffix('.zip')
    source = {}
    for p in (ROOT/'src').glob('*.lsp'):
        source.update(definitions(p.read_text(encoding='utf-8')))
    entries = ('START-CAD2020.lsp',builder.UPDATE_NAME,'src/load.lsp')
    cases = [(starts.CircuitStartTests,'test_actual_panel_number_then_continuous_starts_reaches_editor'),
             (starts.CircuitStartTests,'test_cancel_then_second_button_reuses_panel_and_number'),
             (starts.CircuitStartTests,'test_reselect_adds_circuit_and_preserves_manual_inputs_and_uids'),
             (numbers.NumberWorkflowTests,'test_actual_elstat_pick_five_plane_numbers_reach_panel_and_plan')]
    assets=[]
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        files={p.relative_to(directory.parent).as_posix() for p in directory.rglob('*') if p.is_file()}
        assert files == {n for n in z.namelist() if not n.endswith('/')}
        for name in sorted(files):
            data=z.read(name)
            assert data == (directory.parent/name).read_bytes(), name
            if Path(name).suffix.lower() in ('.lsp','.dcl'):
                decoded=data.decode('gb2312',errors='strict')
                assert decoded.encode('gb2312',errors='strict') == data
                if Path(name).suffix.lower()=='.lsp': parse(decoded)
                assets.append(name)
        for entry in entries:
            packed=definitions(z.read(f'{builder.NAME}/{entry}').decode('gb2312'))
            for name in FUNCTIONS:
                key=Symbol(name.upper())
                assert packed[key] == source[key], (entry,name)
            for cls,method in cases:
                fixture=cls(method)
                fixture.setUp()
                try:
                    for form in packed.values(): fixture.h.evaluate(form)
                    getattr(fixture,method)()
                finally:
                    fixture.doCleanups()
    report={'date':'2026-10-13','status':'completed','package':builder.PACKAGE_NO,'passed':True,
            'lisp_dcl_count':len(assets),'checked_entries':entries,'checked_functions':FUNCTIONS,
            'entry_workflows_passed':len(cases)*len(entries),
            'checks':['ZIP CRC','all package and archive bytes equal','strict GB2312 roundtrip',
                      'all LISP parsing','changed definitions equal source AST',
                      'actual selection, cancellation, draft preservation and numbering in all three entries'],
            'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'native_cad_status':'pending; finite CAD/DCL adapters are not original DWG acceptance'}
    path=ROOT/'tests/evidence'/f'2026-10-13-circuit-starts-package-{builder.PACKAGE_NO:03d}.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{builder.NAME}: {len(assets)} GB2312 assets; {len(cases)*len(entries)} entry workflows passed')


if __name__ == '__main__':
    check()
