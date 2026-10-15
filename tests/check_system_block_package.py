"""Verify the bundled system DWG and all CAD 2020 loading entries. Date: 2026-10-15."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

from autolisp_host import Symbol, parse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("system_block_builder", ROOT / "tools/build_cad2020.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def definitions(source):
    return {form[1]: form for form in parse(source)
            if isinstance(form, list) and form and form[0] == Symbol("DEFUN")}


def embedded_drawing(function, relative):
    payloads = []
    def walk(node):
        if not isinstance(node, list):
            return
        if len(node) == 4 and node[0] == Symbol("EL:STARTUPRESOURCE"):
            location = node[2]
            if isinstance(location, list) and location[-1] == relative:
                assert node[3][0] == Symbol("QUOTE")
                payloads.append(base64.b64decode("".join(node[3][1]), validate=True))
        for child in node:
            walk(child)
    walk(function)
    assert len(payloads) == 1, (relative, len(payloads))
    return payloads[0]


def check():
    directory = builder.DEST
    archive = directory.with_suffix(".zip")
    relative = "templates/系统图块库.dwg"
    original = (ROOT / relative).read_bytes()
    assert original[:6] == b"AC1024"
    assert (directory / relative).read_bytes() == original
    text_files = 0
    entries = ("START-CAD2020.lsp", builder.UPDATE_NAME, "src/load.lsp", "CCKK.lsp")
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert z.read(builder.NAME + "/" + relative) == original
        for name in z.namelist():
            if name.endswith("/"):
                continue
            data = z.read(name)
            assert data == (directory.parent / name).read_bytes(), name
            if Path(name).suffix.lower() in (".lsp", ".dcl"):
                assert not data.startswith(b"\xef\xbb\xbf"), name
                assert data.decode("gb2312", errors="strict").encode("gb2312") == data, name
                text_files += 1
        ui = z.read(builder.NAME + "/ui/power.dcl").decode("gb2312")
        for label in ("第一步：拾取配电箱和回路起始端导线", "第二步：选择配电箱容量",
                      "第三步：在图面查看全部回路", "第四步：生成新系统图", "图块图纸：系统图块库.dwg"):
            assert label in ui, label
        for index in range(1, 5):
            assert f'key = "p_step{index}"' in ui
        assert 'key = "p_block_library_open"' in ui
        for entry in entries:
            text = z.read(builder.NAME + "/" + entry).decode("gb2312")
            assert "ZYF_Tool_应急照明配电箱图块" in text, entry
            assert "ZYF_Tool_应急照明配电回路图块" in text, entry
            assert "疏散指示及应急照明" in text, entry
            assert "dfgjhdrtyjtfgj4SADFG3" not in text, entry
            assert "fghjftyuk" not in text, entry
            assert "商铺疏散指示及应急照明" not in text, entry
            if entry in ("START-CAD2020.lsp", "src/load.lsp"):
                forms = definitions(text)
                assert embedded_drawing(forms[Symbol("EL:STARTUPEMBEDDEDASSETS")], relative) == original
                assert Symbol("EL:PANELOPENBLOCKLIBRARY") in forms
                assert Symbol("EL:ENSURESYSTEMBLOCKS") in forms
                assert Symbol("EL:REDSTEPDRAW") in forms
    evidence = {
        "date": "2026-10-15", "package": builder.NAME, "passed": True,
        "lisp_dcl_files": text_files, "dwg_bytes": len(original),
        "dwg_signature": original[:6].decode("ascii"),
        "dwg_sha256": hashlib.sha256(original).hexdigest(),
        "checks": ["ZIP and extracted files byte identity", "strict GB2312 and no UTF-8 BOM",
                   "four visible steps and system drawing entry", "all loading entries use renamed blocks and purpose caption",
                   "original DWG bytes in source, package and ZIP", "original DWG bytes reconstructed from both standalone loading entries"],
        "cad_status": "pending; no native AutoCAD 2020 DCL, Explorer, actual block names, dynamic states or generated geometry acceptance",
    }
    report = ROOT / f"tests/evidence/2026-10-15-system-block-library-package-{builder.PACKAGE_NO:03d}.json"
    report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {text_files} LISP/DCL files; original system DWG {len(original)} bytes; embedded bytes match")


if __name__ == "__main__":
    check()
