"""Focused S01-S06 regression evidence. Date: 2026-10-09."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from run_checks import RecordingResult

ROOT=pathlib.Path(__file__).resolve().parents[1]
MODULES=('test_source_contracts','test_fixed','test_template_choices','test_panel','test_diagram_store',
         'test_diagram_update','test_simple_flow','test_cad_adapter','test_root_init','test_kernel')
if __name__=='__main__':
    # Keep temporary file adapters inside the authorized workspace on Windows.
    tempfile.tempdir=str(ROOT/'output')
    suite=unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result=unittest.TextTestRunner(verbosity=2,resultclass=RecordingResult).run(suite)
    files=sorted(list((ROOT/'src').glob('*.lsp'))+list((ROOT/'ui').glob('*'))+
                 list((ROOT/'tests').glob('*.py'))+[ROOT/'tools/build_cad2020.py'])
    evidence={'date':'2026-10-09','scope':'S01-S06 focused source functions and finite CAD/DCL adapters',
      'passed':result.wasSuccessful(),'test_count':result.testsRun,'tests':result.records,
      'cad_status':'pending; no native AutoCAD 2020, real dynamic-template DWG, save/reopen or native UNDO acceptance',
      'sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}}
    (ROOT/'tests/evidence/2026-10-09-fixed-diagram.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
