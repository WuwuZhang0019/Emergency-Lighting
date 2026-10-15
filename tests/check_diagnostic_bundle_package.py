"""Date: 2026-10-15. GB2312 and embedded ZIP-helper delivery parity."""
import hashlib
import json

from check_store_write_package import ROOT, check_package, definitions

FUNCTIONS = {
    'common': ['EL:EXPORTDIAGNOSTICRUN'],
    'config': ['EL:ROOTVALID'],
    'diagram-commands': ['EL:DIAGNOSTICREQUIRE', 'EL:DIAGNOSTICFAILURE',
        'EL:DIAGNOSTICRECORD', 'EL:DIAGNOSTICRECORDVALID', 'EL:DIAGNOSTICWINDOWSPATH',
        'EL:DIAGNOSTICWRITETEXT', 'EL:DIAGNOSTICPROGRESS', 'EL:DIAGNOSTICNATIVETEXT',
        'EL:DIAGNOSTICFIELDS', 'EL:DIAGNOSTICRESULT', 'EL:DIAGNOSTICFOLDERAT',
        'EL:DIAGNOSTICFOLDER', 'EL:DIAGNOSTICPSQUOTE', 'EL:DIAGNOSTICENCODEDCOMMAND',
        'EL:DIAGNOSTICZIP', 'EL:DIAGNOSTICBUNDLE', 'EL:DIAGNOSTICOPENFOLDER',
        'EL:DIAGNOSTICEXPORT', 'EL:PANELDIAGNOSTICEXPORT', 'C:ELDIAG'],
    'panel': ['EL:PANELDIALOG'],
    'startup': ['EL:STARTUPROOT', 'EL:STARTUPCOMMANDHINT'],
}

if __name__ == '__main__':
    regression = json.loads((ROOT / 'tests/evidence/2026-10-15-diagnostic-bundle-checks-144.json').read_text(encoding='utf-8'))
    assert regression['status'] == 'passed' and not regression['failures']
    for name, expected in regression['sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    result = check_package(144, FUNCTIONS)
    package = ROOT / 'output/应急照明-144'
    # The native temporary file uses the CAD2020 system codepage; final data is UTF-8.
    transformed = (ROOT / 'src/diagram-commands.lsp').read_text(encoding='utf-8').replace(
        '(open tmp "w" "utf8")', '(open tmp "w")').replace(
        '(defun EL:DiagnosticNativeCharset () "utf-8")',
        '(defun EL:DiagnosticNativeCharset () "gb2312")')
    expected = definitions(transformed)
    for entry in ('src/diagram-commands.lsp', 'START-CAD2020.lsp', 'src/load.lsp', 'UPDATE-144.lsp'):
        actual = definitions((package / entry).read_bytes().decode('gb2312'))
        for name in ('EL:DIAGNOSTICWRITEDATA', 'EL:DIAGNOSTICNATIVECHARSET'):
            assert actual[name] == expected[name], (entry, name)
        script = actual['EL:DIAGNOSTICSCRIPTTEXT'][3]
        assert script[0] == 'EL:MONITORJOIN' and script[1][0] == 'QUOTE'
        assert ''.join(script[1][1]) == (ROOT / 'src/diagnostic-bundle.ps1').read_text(encoding='utf-8')
    assert (package / 'src/diagnostic-bundle.ps1').read_bytes() == (ROOT / 'src/diagnostic-bundle.ps1').read_bytes()
    ui = (package / 'ui/power.dcl').read_bytes().decode('gb2312')
    assert ui == (ROOT / 'ui/power.dcl').read_text(encoding='utf-8')
    assert ': edit_box { key = "p_diagnostic_path";' in ui
    assert 'key = "p_diagnostic_open"; label = "打开所在文件夹"' in ui
    result.update({'date': '2026-10-15', 'focused_regression_cases': regression['cases'],
                   'native_cad_status': 'Native AutoCAD COM, DCL path copy and Explorer action acceptance pending'})
    output = ROOT / 'tests/evidence/2026-10-15-diagnostic-bundle-package-144.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
