"""Date: 2026-10-14. v138 GB2312 delivery parity; no native CAD timing claim."""
import json
from check_store_write_package import ROOT, check_package

FUNCTIONS = {
    'common': ['EL:PERFCALL', 'EL:MONITORTITLE'],
    'store-compact': ['EL:COMPACTTAKE', 'EL:COMPACTREADINTEGERCHUNK',
                      'EL:COMPACTUNPACKINTEGERS', 'EL:COMPACTPOOLLENGTH',
                      'EL:COMPACTDECODE', 'EL:STOREEXPAND'],
}


if __name__ == '__main__':
    result = check_package(138, FUNCTIONS)
    result.update({'focused_regression_cases': 103,
                   'native_cad_status': '138 first-read timing pending; two-second target not yet verified'})
    output = ROOT / 'tests/evidence/2026-10-14-store-read-package-138.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
