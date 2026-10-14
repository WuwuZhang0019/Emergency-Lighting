"""Date: 2026-10-15. Exact v139 source, delivery and completed regression evidence."""
import hashlib
import json
from check_store_write_package import ROOT, check_package

FUNCTIONS = {
    'common': ['EL:STABLEDATA', 'EL:LOGENTITY', 'EL:LOGENTITYDATA'],
    'config': ['EL:PRESETBLOCKALLOWED', 'EL:PRESETBLOCKNAMEALLOWED'],
    'geometry': ['EL:POLYLINEDATA', 'EL:POLYLINEDATADXF', 'EL:WIRERECORD',
                 'EL:WIRERECORDDXF', 'EL:SPATIALTREE', 'EL:SPATIALTREEBUILD'],
    'simple': ['EL:COLLECTBLOCKNAME', 'EL:SIMPLECOLLECT'],
    'circuit-number': ['EL:NUMBERPATHMEASURES', 'EL:NUMBERPATHSLICE',
                       'EL:NUMBERPATHSLICEMEASURED', 'EL:NUMBERSHAPEHIT',
                       'EL:NUMBERSHAPEHITSTRICT', 'EL:NUMBERFIRSTDEVICE'],
}


if __name__ == '__main__':
    regression = json.loads((ROOT / 'tests/evidence/2026-10-15-recognition-checks-139.json').read_text(encoding='utf-8'))
    assert regression['status'] == 'passed' and not regression['failures']
    for name, expected in regression['sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    result = check_package(139, FUNCTIONS)
    result.update({'date': '2026-10-15', 'focused_regression_cases': regression['cases'],
                   'native_cad_status': '139 whole-panel recognition timing pending; one-second target not yet verified'})
    output = ROOT / 'tests/evidence/2026-10-15-recognition-package-139.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
