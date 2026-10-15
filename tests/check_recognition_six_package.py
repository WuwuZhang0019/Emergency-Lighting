"""Date: 2026-10-15. Exact v140 load-entry parity, GB2312 and removed draft action."""
import hashlib
import json
from check_store_write_package import ROOT, check_package

FUNCTIONS = {
    'common': ['EL:STABLEDATA', 'EL:STABLESNAPSHOT', 'EL:STABLESNAPSHOTROW'],
    'geometry': ['EL:SPATIALTREEBUILD', 'EL:RAYBOXHITS'],
    'simple': ['EL:NETWORKPROOFMAKE', 'EL:SIMPLENETWORK', 'EL:WALKDEVICEPATHHIT',
               'EL:WALKPATHHIT', 'EL:WALKBLOCK', 'EL:SIMPLENETWORKBUILD'],
    'circuit-number': ['EL:NUMBERSHAPEHITSTRICT', 'EL:NUMBERPROBEPOINTHIT',
                       'EL:NUMBERPROBEPATHHIT', 'EL:NUMBERFIRSTDEVICE'],
    'diagram-update': ['EL:RECOGNIZEFIXED'],
    'panel': ['EL:FIXEDSOURCESIGNATURE', 'EL:SPLITNETWORK', 'EL:PANELGENERATEBODY',
              'EL:PANELFILL', 'EL:PANELHOMEFILL', 'EL:PANELDIALOG'],
}


if __name__ == '__main__':
    regression = json.loads((ROOT / 'tests/evidence/2026-10-15-recognition-checks-140.json').read_text(encoding='utf-8'))
    assert regression['status'] == 'passed' and not regression['failures']
    for name, expected in regression['sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    result = check_package(140, FUNCTIONS)
    dcl = (ROOT / 'output/应急照明-140/ui/power.dcl').read_bytes().decode('gb2312')
    panel = (ROOT / 'output/应急照明-140/src/panel.lsp').read_bytes().decode('gb2312')
    assert '保存当前输入' not in dcl
    assert 'key = "p_generate"; label = "第四步：生成新系统图"; is_default = true;' in dcl
    assert '(EL:MonitorActionTile "accept" "(EL:PanelAccept)")' not in panel
    assert '"f_preview" "accept" "p_generate"' not in panel
    result.update({'date': '2026-10-15', 'focused_regression_cases': regression['cases'],
                   'standalone_draft_action_removed': True,
                   'native_cad_status': '140 six-circuit recognition timing pending; one-second target unverified'})
    output = ROOT / 'tests/evidence/2026-10-15-recognition-package-140.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
