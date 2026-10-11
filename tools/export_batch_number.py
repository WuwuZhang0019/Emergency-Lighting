"""Export only the standalone HLBH tool for CAD2020. Date: 2026-10-11.

No ZIP, package directory, plugin launcher or other module is generated.
"""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/batch-number.lsp'
DESTINATION = ROOT / 'output/HLPLBH.lsp'


def export(source=SOURCE, destination=DESTINATION):
    source, destination = Path(source), Path(destination)
    text = source.read_text(encoding='utf-8')
    data = text.encode('gb2312', errors='strict')
    assert data.decode('gb2312', errors='strict') == text
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_bytes(data)
    assert temporary.read_bytes() == data
    temporary.replace(destination)
    assert destination.read_bytes().decode('gb2312', errors='strict') == text
    return {'date': '2026-10-11', 'source': str(source.resolve()),
            'output': str(destination.resolve()), 'encoding': 'GB2312',
            'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'packaged': False}


if __name__ == '__main__':
    print(json.dumps(export(), ensure_ascii=False, indent=2))
