"""Verify complete large-XRecord CAD2020 delivery. Date: 2026-10-13."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile
from autolisp_host import Symbol, parse
from test_large_xrecord_create import LargeXRecordTests
from test_gap_cross_circuit import CrossCircuitGapTests

ROOT=Path(__file__).resolve().parents[1]
FUNCTIONS=('EL:StoreCreatePayload','EL:StoreReplacePayload','EL:StoreWrite',
    'EL:StoreLegacyBackup','EL:TransactionGuarded','EL:SimpleGapSnapshot')


def definitions(text):
    return {form[1]:form for form in parse(text) if isinstance(form,list)
        and form and form[0]==Symbol('DEFUN')}


def check():
    spec=importlib.util.spec_from_file_location('builder',ROOT/'tools/build_cad2020.py')
    builder=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    directory=builder.DEST
    archive=directory.with_suffix('.zip')
    evidence=ROOT/'tests/evidence'/f'2026-10-13-large-xrecord-{builder.PACKAGE_NO:03d}.json'
    regression=json.loads(evidence.read_text(encoding='utf-8'))
    assert regression['passed'] and not regression['failures'] and not regression['errors']
    for name,digest in regression['source_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    source={}
    for name in ('diagram-store','simple'):
        source.update(definitions((ROOT/'src'/f'{name}.lsp').read_text(encoding='utf-8')))
    entries=('START-CAD2020.lsp',builder.UPDATE_NAME,'src/load.lsp')
    assets=[]
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        files={p.relative_to(directory.parent).as_posix() for p in directory.rglob('*') if p.is_file()}
        assert files=={name for name in z.namelist() if not name.endswith('/')}
        for name in sorted(files):
            raw=z.read(name)
            assert raw==(directory.parent/name).read_bytes(),name
            if Path(name).suffix.lower() in ('.lsp','.dcl'):
                text=raw.decode('gb2312',errors='strict')
                assert text.encode('gb2312',errors='strict')==raw,name
                if Path(name).suffix.lower()=='.lsp':
                    parse(text)
                assets.append(name.split('/',1)[1])
        assert f'{builder.NAME}/package-{builder.PACKAGE_NO:03d}.marker' in files
        assert z.read(f'{builder.NAME}/tests/evidence/{evidence.name}')==evidence.read_bytes()
        baseline=ROOT/'tests/evidence'/regression['baseline_report']
        assert z.read(f'{builder.NAME}/tests/evidence/{baseline.name}')==baseline.read_bytes()
        for entry in entries:
            packed=definitions(z.read(f'{builder.NAME}/{entry}').decode('gb2312'))
            for name in FUNCTIONS:
                key=Symbol(name.upper())
                assert packed[key]==source[key],(entry,name)
            for cls,method in ((LargeXRecordTests,'test_first_large_store_save_reopen_and_rewrite_preserve_exact_contents'),
                               (CrossCircuitGapTests,'test_1430_gap_crosses_other_circuit_device_and_wire_without_merging')):
                fixture=cls(method)
                fixture.setUp()
                try:
                    for form in packed.values():
                        fixture.h.evaluate(form)
                    getattr(fixture,method)()
                finally:
                    fixture.doCleanups()
    report={'date':'2026-10-13','status':'completed','package':builder.PACKAGE_NO,'passed':True,
        'regression_tests_run':regression['tests_run'],'lisp_dcl_count':len(assets),'assets':assets,
        'checked_functions':FUNCTIONS,'checked_entries':entries,
        'checks':['strict GB2312','ZIP CRC','all file-set and byte equality','all LISP parsing',
            'passing regression report matches source hashes','changed source AST equals all three entries',
            'large first save/reopen/rewrite and 1430 mm circuit isolation in each packaged entry'],
        'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'native_cad_status':'pending; original DWG fault site was not recorded in v117'}
    target=ROOT/'tests/evidence'/f'2026-10-13-large-xrecord-package-{builder.PACKAGE_NO:03d}.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{builder.NAME}: {len(assets)} LISP/DCL assets, 3 entrypoints passed save and gap scenarios')


if __name__=='__main__':
    check()
