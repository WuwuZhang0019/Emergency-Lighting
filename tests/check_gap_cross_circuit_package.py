"""Verify cross-device continuation in the complete CAD2020 package. Date: 2026-10-13."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

from autolisp_host import Symbol, parse
from test_gap_cross_circuit import CrossCircuitGapTests

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ('EL:RecognitionRules','EL:SimpleGapSnapshot','EL:SimpleNetworkBuild','EL:SimpleGapLog')


def definitions(text):
    return {form[1]:form for form in parse(text)
        if isinstance(form,list) and form and form[0] == Symbol('DEFUN')}


def check():
    spec=importlib.util.spec_from_file_location('gap_builder',ROOT/'tools/build_cad2020.py')
    builder=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    directory=builder.DEST
    archive=directory.with_suffix('.zip')
    source={}
    for name in ('common','simple'):
        source.update(definitions((ROOT/'src'/f'{name}.lsp').read_text(encoding='utf-8')))
    assets=[]
    entries=('START-CAD2020.lsp',builder.UPDATE_NAME,'src/load.lsp')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        files={p.relative_to(directory.parent).as_posix() for p in directory.rglob('*') if p.is_file()}
        assert files == {name for name in z.namelist() if not name.endswith('/')}
        for name in sorted(files):
            data=z.read(name)
            assert data == (directory.parent/name).read_bytes(),name
            if Path(name).suffix.lower() in ('.lsp','.dcl'):
                text=data.decode('gb2312',errors='strict')
                assert text.encode('gb2312',errors='strict') == data,name
                if Path(name).suffix.lower()=='.lsp':
                    parse(text)
                assets.append(name.split('/',1)[1])
        assert f'{builder.NAME}/package-{builder.PACKAGE_NO:03d}.marker' in files
        evidence=ROOT/'tests/evidence'/f'2026-10-13-gap-cross-circuit-{builder.PACKAGE_NO:03d}.json'
        regression=json.loads(evidence.read_text(encoding='utf-8'))
        assert regression['passed'] and regression['tests_run']==56
        for name,digest in regression['source_sha256'].items():
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
        assert z.read(f'{builder.NAME}/tests/evidence/{evidence.name}')==evidence.read_bytes()
        for entry in entries:
            packed=definitions(z.read(f'{builder.NAME}/{entry}').decode('gb2312'))
            for name in FUNCTIONS:
                key=Symbol(name.upper())
                assert packed[key] == source[key],(entry,name)
            # Run the actual three packaged entry definitions through the bounded host.
            fixture=CrossCircuitGapTests('test_1430_gap_crosses_other_circuit_device_and_wire_without_merging')
            fixture.setUp()
            for form in packed.values():
                fixture.h.evaluate(form)
            try:
                fixture.test_1430_gap_crosses_other_circuit_device_and_wire_without_merging()
            finally:
                fixture.doCleanups()
    report={'date':'2026-10-13','status':'completed','package':builder.PACKAGE_NO,'passed':True,
        'regression_tests_run':regression['tests_run'],'lisp_dcl_count':len(assets),'checked_entries':entries,'checked_functions':FUNCTIONS,
        'checks':['ZIP CRC','all archive files equal extracted files','strict GB2312 roundtrip',
            'all LISP parsing','changed definitions equal source AST','1430 mm two-circuit scenario in three packaged entries'],
        'assets':assets,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('src/common.lsp','src/simple.lsp','tests/test_gap_cross_circuit.py','tests/test_simple_flow.py',
             'tools/build_cad2020.py','.gitignore')},
        'native_cad_status':'pending; bounded adapters do not establish original DWG acceptance'}
    path=ROOT/'tests/evidence'/f'2026-10-13-gap-cross-circuit-package-{builder.PACKAGE_NO:03d}.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{builder.NAME}: {len(assets)} LISP/DCL assets verified, 1430 mm scenario passed in 3 entries')


if __name__=='__main__':
    check()
