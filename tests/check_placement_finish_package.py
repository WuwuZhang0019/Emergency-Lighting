"""Date: 2026-10-15. v142 GB2312, ZIP and loading-entry verification."""
import hashlib
import json
from check_store_write_package import ROOT, check_package

FUNCTIONS = {
    'common': ['EL:PERFSTART', 'EL:PERFFINISH', 'EL:LOGEVENT', 'EL:EXPORTDIAGNOSTICRUN'],
    'diagram-commands': ['EL:EDITPANELONCE', 'EL:REMEMBERDIAGRAMDIAGNOSTIC',
                         'EL:DIAGNOSTICEXPORT', 'EL:PANELDIAGNOSTICEXPORT', 'EL:FIXEDSTAT'],
    'diagram-store': ['EL:CREATEDIAGRAM'],
    'diagram-update': ['EL:SYNCDIAGRAMSCOPED'],
    'panel': ['EL:PANELDIALOG'],
}

if __name__ == '__main__':
    regression = json.loads((ROOT / 'tests/evidence/2026-10-15-placement-finish-checks-142.json').read_text(encoding='utf-8'))
    assert regression['status'] == 'passed' and not regression['failures']
    for name, expected in regression['sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    result = check_package(142, FUNCTIONS)
    ui = ROOT / 'output/应急照明-142/ui/power.dcl'
    assert ui.read_bytes().decode('gb2312') == (ROOT / 'ui/power.dcl').read_text(encoding='utf-8')
    assert 'key = "p_diagnostic"; label = "导出诊断日志"' in ui.read_bytes().decode('gb2312')
    result.update({'date': '2026-10-15', 'focused_regression_cases': regression['cases'],
                   'native_cad_status': 'Original DWG placement latency and diagnostic button acceptance pending'})
    output = ROOT / 'tests/evidence/2026-10-15-placement-finish-package-142.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
