"""Date: 2026-10-22. Read-only performance trial package checks; no native CAD proof."""
import sys

# Keep this checker read-only, including imports of local helpers.
sys.dont_write_bytecode = True

import base64
from datetime import date
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

from autolisp_host import Host, Symbol, parse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("performance_trial_builder", ROOT / "tools/build_cad2020.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def definitions(forms):
    return {form[1]: form for form in forms
            if isinstance(form, list) and form and form[0] == Symbol("DEFUN")}


def embedded_resources(function):
    """Decode immutable startup payloads without evaluating their writer or any CAD API."""
    payloads = {}

    def walk(node):
        if not isinstance(node, list):
            return
        if len(node) == 4 and node[0] == Symbol("EL:STARTUPRESOURCE"):
            location, quoted = node[2], node[3]
            assert isinstance(location, list) and location[0] == Symbol("STRCAT"), location
            relative = location[-1]
            assert isinstance(relative, str) and not isinstance(relative, Symbol), location
            assert quoted[0] == Symbol("QUOTE"), relative
            assert relative not in payloads, ("duplicate embedded resource", relative)
            payloads[relative] = base64.b64decode("".join(quoted[1]), validate=True)
        for child in node:
            walk(child)

    walk(function)
    return payloads


def check():
    directory = builder.DEST
    # with_suffix would truncate the final dotted version component.
    archive_path = directory.parent / (directory.name + ".zip")
    assert directory.is_dir(), directory
    assert archive_path.is_file(), archive_path
    paths = {p.relative_to(directory).as_posix() + ("/" if p.is_dir() else ""): p
             for p in directory.rglob("*")}
    files = {name: path for name, path in paths.items() if path.is_file()}
    parsed, texts = {}, {}
    encoded = 0
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None, "ZIP CRC failure"
        names = archive.namelist()
        assert len(names) == len(set(names)), "duplicate ZIP entries"
        expected = {builder.NAME + "/" + relative for relative in paths}
        assert set(names) == expected, {
            "missing_from_zip": sorted(expected - set(names)),
            "extra_in_zip": sorted(set(names) - expected),
        }
        for relative, path in files.items():
            raw = path.read_bytes()
            assert archive.read(builder.NAME + "/" + relative) == raw, relative
            if path.suffix.lower() in (".lsp", ".dcl"):
                assert not raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff",
                                           b"\x00\x00\xfe\xff")), ("BOM", relative)
                text = raw.decode("gb2312", errors="strict")
                assert text.encode("gb2312", errors="strict") == raw, relative
                encoded += 1
                texts[relative] = text
                if path.suffix.lower() == ".lsp":
                    parsed[relative] = parse(text)

    source_functions = {}
    modules_checked = []
    # Verify every converted module, then compare every effective module DEFUN
    # across all five loading entries. This includes recognition, candidate
    # deduplication, template/source policy and generation/placement timings.
    for source in sorted((ROOT / "src").glob("*.lsp")):
        if source.name == "load.lsp":
            continue
        relative = "src/" + source.name
        expected = builder.cad2020_bytes(source)
        assert (directory / relative).read_bytes() == expected, relative
        modules_checked.append(relative)
    for module in builder.MODULES:
        source_functions.update(definitions(parsed[f"src/{module}.lsp"]))

    entries = ("START-CAD2020.lsp", builder.UPDATE_NAME, "src/load.lsp",
               builder.FULL_TEST_COMMAND + ".lsp", builder.COLD_TEST_COMMAND + ".lsp")
    standalone_commands = {
        entries[3]: builder.FULL_TEST_COMMAND,
        entries[4]: builder.COLD_TEST_COMMAND,
    }
    entry_functions = {}
    embedded_root = Symbol("EL:STARTUPEMBEDDEDROOT")
    generated_definitions = definitions(parse(builder.embedded_resources()))
    for entry in entries:
        forms = parsed[entry]
        if entry in standalone_commands:
            initialize = Symbol(standalone_commands[entry].upper() + ":INITIALIZE")
            forms = definitions(forms)[initialize][3:]
        actual = definitions(forms)
        for name, function in source_functions.items():
            # Select the uncalled initializer's definitions, including its real
            # C:ELCOLD75; the standalone top-level wrapper has the same name.
            expected = (generated_definitions[name]
                        if name == embedded_root and entry != builder.UPDATE_NAME else function)
            assert actual.get(name) == expected, (entry, str(name))
        entry_functions[entry] = actual

    startup = (directory / "START-CAD2020.lsp").read_bytes()
    assert (directory / "src/load.lsp").read_bytes() == startup
    assert (directory / entries[3]).read_bytes() == builder.full_test_entry(startup.decode("gb2312"))
    assert (directory / entries[4]).read_bytes() == builder.cold_test_entry(startup.decode("gb2312"))
    assert (directory / "CCKK.lsp").read_bytes().startswith(
        builder.cad2020_bytes(ROOT / "src/insert-circuit.lsp"))
    marker = f"package-{builder.PACKAGE_NO:03d}.marker"
    assert files[marker].read_text(encoding="ascii") == f"Emergency-Lighting {builder.PACKAGE_NO}\n"
    for entry in entries:
        assert marker in texts[entry], (entry, "wrong package marker")
    for entry in (entries[0], entries[2], entries[3], entries[4]):
        assert f"runtime-{builder.PACKAGE_NO:03d}/" in texts[entry], (entry, "wrong runtime path")

    dcl_checked = []
    for source in sorted((ROOT / "ui").glob("*.dcl")):
        relative = "ui/" + source.name
        assert (directory / relative).read_bytes() == builder.cad2020_bytes(source), relative
        dcl_checked.append(relative)
    for source in sorted((ROOT / "ui").glob("*.marker")):
        relative = "ui/" + source.name
        if relative in files:
            assert files[relative].read_bytes() == source.read_bytes(), relative

    drawing = "templates/系统图块库.dwg"
    drawing_bytes = (ROOT / drawing).read_bytes()
    assert drawing_bytes[:6] in (b"AC1015", b"AC1018", b"AC1021", b"AC1024", b"AC1027", b"AC1032")
    assert files[drawing].read_bytes() == drawing_bytes, drawing
    seed_files = {p.relative_to(ROOT).as_posix(): p
                  for p in (ROOT / "assets/default-device-library").rglob("*") if p.is_file()}
    assert {name for name in files if name.startswith("assets/default-device-library/")} == set(seed_files)
    for relative, source in seed_files.items():
        assert files[relative].read_bytes() == source.read_bytes(), relative

    expected_resources = {name for name in files if name.startswith("ui/")
                          or name.startswith("assets/default-device-library/")
                          or (name.startswith("src/") and name.endswith(".lsp"))
                          or (name.startswith("templates/") and name.endswith(".dwg"))
                          or (name.startswith("native/") and name.endswith(".dll"))}
    resources_checked = {}
    for entry in (entries[0], entries[2], entries[3], entries[4]):
        actual = entry_functions[entry]
        payloads = {}
        for name in ("EL:STARTUPEMBEDDEDTEXT", "EL:STARTUPEMBEDDEDASSETS"):
            decoded = embedded_resources(actual[Symbol(name)])
            assert not set(payloads).intersection(decoded), entry
            payloads.update(decoded)
        assert set(payloads) == expected_resources, (entry, "embedded resource manifest")
        for relative, raw in payloads.items():
            # The embedded module loader precedes the standalone src/load.lsp
            # replacement and must match its own strict source conversion.
            expected = (builder.cad2020_bytes(ROOT / "src/load.lsp") if relative == "src/load.lsp"
                        else files[relative].read_bytes())
            assert raw == expected, (entry, relative)
        resources_checked[entry] = len(payloads)

    # Verify the immutable native proof against current source and actual DLL
    # metadata. Importing this helper never compiles, restores or runs AutoCAD.
    native_spec = importlib.util.spec_from_file_location(
        "performance_trial_native_builder", ROOT / "tools/build_cold_recognition.py")
    native_builder = importlib.util.module_from_spec(native_spec)
    native_spec.loader.exec_module(native_builder)
    native_path = "native/" + native_builder.DLL_NAME
    assert {name for name, path in files.items() if path.suffix.lower() == ".dll"} == {native_path}, \
        "only the project DLL may be delivered; Autodesk DLLs must not be copied"
    native_bytes = files[native_path].read_bytes()
    native_hash = hashlib.sha256(native_bytes).hexdigest()
    native_proof = json.loads(files["native/build.json"].read_text(encoding="utf-8"))
    assert native_proof["status"] == "passed" and native_proof["mode"] == "autocad-plugin"
    assert native_proof["version"] == builder.VERSION == native_builder.VERSION
    assert native_proof["framework"] == "net47" and native_proof["platform"] == "x64"
    assert native_proof["language_version"] == "7.3" and native_proof["deterministic"] is True
    assert native_proof["offline"] is True and native_proof["autodesk_dlls_copied"] is False
    assert native_proof["artifact"]["sha256"] == native_hash
    assert native_proof["artifact"]["bytes"] == len(native_bytes)
    assert Path(native_proof["artifact"]["path"]).name == native_builder.DLL_NAME
    native_source_paths = sorted((ROOT / "native/ColdRecognition").rglob("*.cs"))
    expected_native_sources = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in native_source_paths
    }
    actual_native_sources = {item["path"]: item["sha256"] for item in native_proof["sources"]}
    assert len(actual_native_sources) == len(native_proof["sources"]), "duplicate native source proof"
    assert actual_native_sources == expected_native_sources, "native DLL proof does not match current source"
    native_identity = native_builder.reference_details([files[native_path]])[0]
    assert native_identity["assembly_version"] == builder.VERSION + ".0", native_identity
    assert native_identity["file_version"] == builder.VERSION + ".0", native_identity
    assert b".NETFramework,Version=v4.7" in native_bytes, "missing net47 target-framework metadata"
    handshake = "EL_NET_COLD_PROBE_V1/" + builder.VERSION
    assert handshake.encode("utf-16le") in native_bytes, "native handshake/version mismatch"
    assert "EL_NET_COLD_PING_V1".encode("utf-16le") in native_bytes, "native handshake request missing"
    assert handshake in (ROOT / 'src/cold-probe.lsp').read_text(encoding='utf-8'), \
        "LISP handshake/version mismatch"
    reference_names = set()
    cad_names = {"acmgd", "accoremgd", "acdbmgd"}
    for reference in native_proof["references"]:
        name = reference["assembly_name"].lower()
        assert name not in reference_names, ("duplicate native reference", name)
        reference_names.add(name)
        assert hashlib.sha256(Path(reference["path"]).read_bytes()).hexdigest() == reference["sha256"], name
        if name in cad_names:
            assert reference["assembly_version"] == "23.1.0.0", reference
        else:
            assert name in {"mscorlib", "system", "system.core"}, reference
            assert reference["assembly_version"] == "4.0.0.0", reference
            assert reference["file_version"].startswith("4.7."), reference
    assert reference_names == cad_names | {"mscorlib", "system", "system.core"}

    # Execute only registration forms for BOTH standalone entries. Any native
    # API, initializer, LOAD, UI call or drawing mutation fails in this host.
    registration_checked = {}
    for entry, command in standalone_commands.items():
        forms = parsed[entry]
        initialize = Symbol(command.upper() + ":INITIALIZE")
        registered = {initialize, Symbol("C:" + command.upper())}
        assert set(definitions(forms)) == registered, entry
        assert sum(1 for form in forms if isinstance(form, list) and form[0] == Symbol("DEFUN")) == 2, entry
        assert all(isinstance(form, list) and form and form[0] in (Symbol("DEFUN"), Symbol("PRINC"))
                   for form in forms), (entry, "unexpected executable registration form")
        host = Host()
        messages = []
        host.builtins = {"PRINC": lambda *args: messages.extend(args)}
        host.body(forms)
        assert set(host.functions) == registered, entry
        assert set(host.frames[0]) == {"NIL", "T", "PI"}, (entry, "registration changed global state")
        assert any(command in message for message in messages), entry
        registration_checked[entry] = sorted(str(name) for name in registered)

    source_paths = [ROOT / name for name in modules_checked + dcl_checked]
    source_paths += [ROOT / "src/load.lsp", ROOT / "tools/build_cad2020.py",
                     ROOT / "tools/templates/full-test.lsp", ROOT / "tools/templates/cold-test.lsp",
                     ROOT / "tools/build_cold_recognition.py", Path(__file__).resolve()]
    source_paths += native_source_paths
    return {
        "date": date.today().isoformat(), "status": "passed", "version": builder.VERSION,
        "package_no": builder.PACKAGE_NO, "package": builder.NAME,
        "full_test_command": builder.FULL_TEST_COMMAND,
        "cold_test_command": builder.COLD_TEST_COMMAND,
        "archive": str(archive_path), "directory": str(directory),
        "files": len(files), "directories": len(paths) - len(files),
        "gb2312_lisp_dcl": encoded, "parsed_lisp": len(parsed),
        "converted_modules": modules_checked, "converted_dcl": dcl_checked,
        "loading_entries": list(entries), "definitions_per_entry": len(source_functions),
        "embedded_resources": resources_checked, "registration_only": True,
        "registration_entries": registration_checked,
        "native_build": {"artifact": native_path, "sha256": native_hash, "bytes": len(native_bytes),
                         "identity": native_identity, "source_sha256": actual_native_sources,
                         "reference_versions": {item["assembly_name"]: item["assembly_version"]
                                                for item in native_proof["references"]}},
        "default_library_files": len(seed_files), "system_dwg_bytes": len(drawing_bytes),
        "system_dwg_sha256": hashlib.sha256(drawing_bytes).hexdigest(),
        "archive_bytes": archive_path.stat().st_size,
        "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in source_paths},
        "checks": ["ZIP CRC", "complete ZIP/directory manifest and every file byte identity",
                   "strict GB2312 round trip without BOM for every LISP/DCL",
                   "all delivered LISP parsed by autolisp_host",
                   "converted source modules and DCL match package bytes",
                   "all effective module definitions match all five loading entries",
                   "embedded text/default assets/system DWG/native DLL match current package/source",
                   "native build proof matches current source, net47 and AutoCAD 23.1 references",
                   "native DLL identity and hash match; no Autodesk DLLs delivered",
                   "actual full and cold entries register only, with no CAD calls or drawing changes"],
        "native_cad_status": "pending; original-DWG timing, DCL, dynamic states, generated geometry, save/reopen and Undo unverified",
    }


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False, indent=2))
