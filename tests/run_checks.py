"""Run source/host checks and save reproducible evidence. Does not start AutoCAD."""
import hashlib
import json
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]


class RecordingResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.records=[]
    def addSuccess(self,test):
        super().addSuccess(test)
        self.records.append({'test':test.id(),'status':'passed'})
    def addFailure(self,test,err):
        super().addFailure(test,err)
        self.records.append({'test':test.id(),'status':'failed'})
    def addError(self,test,err):
        super().addError(test,err)
        self.records.append({'test':test.id(),'status':'error'})


if __name__=='__main__':
    sys.path.insert(0,str(ROOT/'tests'))
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=RecordingResult).run(suite)
    paths=sorted(list((ROOT/'src').glob('*.lsp'))+list((ROOT/'ui').glob('*.dcl'))+
                 list((ROOT/'tests').glob('*.py'))+list((ROOT/'tests/fixtures').glob('*.*')))
    evidence={
        'session_date':'2026-10-08',
        'scope':'actual AutoLISP pure functions in a subset host; source contracts and adapter stubs; no CAD acceptance',
        'passed':result.wasSuccessful(), 'test_count':result.testsRun,
        'failure_count':len(result.failures), 'error_count':len(result.errors),
        'baseline':json.loads((ROOT/'tests/fixtures/baseline.json').read_text()),
        'tests':sorted(result.records,key=lambda r:r['test']),
        'sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()},
        'cad_status':'pending; no AutoCAD, representative DWG or real dynamic templates provided',
    }
    (ROOT/'tests/evidence/automated-checks.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    sys.exit(0 if result.wasSuccessful() else 1)
