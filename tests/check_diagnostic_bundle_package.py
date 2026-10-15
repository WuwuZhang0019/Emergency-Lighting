"""Date: 2026-10-15. GB2312 and embedded ZIP-helper delivery parity."""
import hashlib
import json

from check_store_write_package import ROOT, check_package

FUNCTIONS = {
    'common': ['EL:EXPORTDIAGNOSTICRUN'],
    'config': ['EL:ROOTVALID'],
    'diagram-commands': ['EL:DIAGNOSTICREQUIRE', 'EL:DIAGNOSTICFAILURE',
        'EL:DIAGNOSTICRECORD', 'EL:DIAGNOSTICRECORDVALID', 'EL:DIAGNOSTICWINDOWSPATH',
        'EL:DIAGNOSTICWRITETEXT', 'EL:DIAGNOSTICWRITEDATA', 'EL:DIAGNOSTICFOLDERAT',
        'EL:DIAGNOSTICFOLDER', 'EL:DIAGNOSTICPSQUOTE', 'EL:DIAGNOSTICENCODEDCOMMAND',
        'EL:DIAGNOSTICZIP', 'EL:DIAGNOSTICBUNDLE', 'EL:DIAGNOSTICOPENFOLDER',
        'EL:DIAGNOSTICEXPORT', 'EL:PANELDIAGNOSTICEXPORT', 'C:ELDIAG'],
    'panel': ['EL:PANELDIALOG'],
}

if __name__ == '__main__':
    regression = json.loads((ROOT / 'tests/evidence/2026-10-15-diagnostic-bundle-checks-143.json').read_text(encoding='utf-8'))
    assert regression['status'] == 'passed' and not regression['failures']
    for name, expected in regression['sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    result = check_package(143, FUNCTIONS)
    package = ROOT / 'output/应急照明-143'
    assert (package / 'src/diagnostic-bundle.ps1').read_bytes() == (ROOT / 'src/diagnostic-bundle.ps1').read_bytes()
    ui = (package / 'ui/power.dcl').read_bytes().decode('gb2312')
    assert ui == (ROOT / 'ui/power.dcl').read_text(encoding='utf-8')
    assert ': edit_box { key = "p_diagnostic_path";' in ui
    assert 'key = "p_diagnostic_open"; label = "打开所在文件夹"' in ui
    result.update({'date': '2026-10-15', 'focused_regression_cases': regression['cases'],
                   'native_cad_status': 'Native AutoCAD COM, DCL path copy and Explorer action acceptance pending'})
    output = ROOT / 'tests/evidence/2026-10-15-diagnostic-bundle-package-143.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
