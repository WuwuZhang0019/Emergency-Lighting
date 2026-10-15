"""Date: 2026-10-15. v141 strict GB2312, complete ZIP parity and load-entry checks."""
import hashlib
import json
from check_store_write_package import ROOT, check_package

FUNCTIONS = {
    'common': ['EL:PERFSTART', 'EL:PERFFINISH', 'EL:PERFCALL', 'EL:MONITORTITLE'],
    'simple': ['EL:COLLECTRULES', 'EL:COLLECTLAYERFACTS', 'EL:COLLECTSOURCECURRENT', 'EL:SIMPLECOLLECT'],
    'diagram-store': ['EL:INPUTRECORD'],
    'diagram-update': ['EL:RECOGNIZEFIXED', 'EL:FIXEDFRESHFORRESULT', 'EL:SYNCDIAGRAMSCOPED'],
    'diagram-commands': ['EL:SAVEDRAFT'],
}

if __name__ == '__main__':
    regression = json.loads((ROOT / 'tests/evidence/2026-10-15-generation-speed-checks-141.json').read_text(encoding='utf-8'))
    assert regression['status'] == 'passed' and not regression['failures']
    for name, expected in regression['sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    result = check_package(141, FUNCTIONS)
    result.update({'date': '2026-10-15', 'focused_regression_cases': regression['cases'],
                   'native_cad_status': 'Original DWG first-write and generation timing pending; 2-second target unverified'})
    output = ROOT / 'tests/evidence/2026-10-15-generation-speed-package-141.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
