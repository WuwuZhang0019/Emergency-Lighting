"""Check the current-only AutoCAD 2020 package. Date: 2026-10-14. Status: current."""

import importlib.util
from pathlib import Path
import zipfile

from autolisp_host import Symbol, parse


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cad2020_builder", ROOT / "tools/build_cad2020.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def definitions(source):
    return {form[1]: form for form in parse(source)
            if isinstance(form, list) and form and form[0] == Symbol("DEFUN")}


def check():
    directory = builder.DEST
    archive = directory.with_suffix(".zip")
    assert directory.is_dir() and archive.is_file()
    names = {path.relative_to(directory.parent).as_posix(): path
             for path in directory.rglob("*") if path.is_file()}
    for obsolete in ("src/existing-power.lsp", "src/existing-power-text.lsp",
                     "docs/00_面板保存记录.md"):
        assert f"{builder.NAME}/{obsolete}" not in names
    source = {}
    for module in ("simple", "diagram-store", "diagram-update", "diagram-commands",
                   "device-ui", "panel"):
        source.update(definitions((ROOT / "src" / f"{module}.lsp").read_text(encoding="utf-8")))
    required = {Symbol(name) for name in (
        "EL:FIXEDSTAT", "EL:PANELDIALOG", "EL:DLUIOPEN", "EL:CREATEDIAGRAM",
        "EL:SYNCDIAGRAMSCOPED", "EL:STOREPUTDIAGRAM", "EL:SIMPLEDEVICEPATHHIT",
        "EL:DEVICECONTACTSHAPE", "EL:DEVICECONTACTTOLERANCE")}
    removed = {Symbol(name) for name in (
        "C:ELUPDATE", "EL:APPLYUPDATE", "EL:HISTORYOPEN", "EL:PANELSTARTDIALOG",
        "EL:DLPANELEDITORINIT", "EL:THUMBPREPARE")}
    assert required <= source.keys()
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert names.keys() == {name for name in z.namelist() if not name.endswith("/")}
        for name, path in names.items():
            data = z.read(name)
            assert data == path.read_bytes(), name
            if path.suffix.lower() in (".lsp", ".dcl"):
                assert data.decode("gb2312", errors="strict").encode("gb2312") == data, name
        for entry in ("START-CAD2020.lsp", builder.UPDATE_NAME, "src/load.lsp"):
            packed = definitions(z.read(f"{builder.NAME}/{entry}").decode("gb2312"))
            assert not (removed & packed.keys()), entry
            for key in required:
                assert packed[key] == source[key], (entry, key)
        dcl = z.read(f"{builder.NAME}/ui/power.dcl").decode("gb2312")
        assert "el_panel : dialog" in dcl
        assert "el_fixed_exits : dialog" not in dcl
        panel = dcl.split("el_panel : dialog", 1)[1]
        assert "b_library" in panel and "p_generate" in panel
        assert "h_records" not in panel and "b_watts" not in panel
    print(f"PASS: {len(names)} package files; GB2312, current flow, ZIP bytes")


if __name__ == "__main__":
    check()
