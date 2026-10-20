"""Explicit system-block import and drawing-first source policy. Date: 2026-10-21.

Finite COM/DCL adapters only; no native AutoCAD acceptance.
"""
from pathlib import Path
import unittest

from autolisp_host import Host, Pair, Symbol, truth

ROOT = Path(__file__).resolve().parents[1]
BLOCKS = ["ZYF_Tool_应急照明配电箱图块", "ZYF_Tool_应急照明配电回路图块"]
STYLES = ["_TEL_DIM", "ICDA-STYLE1"]


class SystemBlockImportTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        self.h.load_definitions(ROOT / "src/common.lsp")
        self.h.load_definitions(ROOT / "src/insert-circuit.lsp")
        self.h.set("*EL:ROOT*", "C:/中文 工具包/")
        self.h.set("*EL:SYSTEMBLOCKSOURCE*", Symbol("LIBRARY"))
        self.h.set("VLAX-VBOBJECT", 9)
        self.target = {"BLOCK": {}, "STYLE": {}}
        self.source = {"BLOCK": {name: ("BLOCK", name) for name in BLOCKS},
                       "STYLE": {name: ("STYLE", name) for name in STYLES}}
        self.path_exists = True
        self.events, self.messages, self.released = [], [], []
        self.fail_stage = None
        self.clone_style_dependencies = False
        self.ignore_copy = False
        self.h.builtins.update({
            "TBLSEARCH": lambda kind, name: [Pair(2, name)] if name in self.target[kind] else None,
            "VL-STRING-RIGHT-TRIM": lambda chars, value: value.rstrip(chars),
            "FINDFILE": lambda path: path if self.path_exists else None,
            "VL-LOAD-COM": lambda: True,
            "VLAX-GET-ACAD-OBJECT": lambda: "application",
            "VLA-GET-ACTIVEDOCUMENT": lambda app: "target",
            "GETVAR": lambda key: "23.1s (LMS Tech)",
            # Native ATOI reads the integer prefix; the generic host uses Python int.
            "ATOI": lambda value: int(value.split(".", 1)[0]),
            "VLA-GETINTERFACEOBJECT": self.interface,
            "VLAX-INVOKE-METHOD": self.open_database,
            "VLA-GET-BLOCKS": lambda db: (db, "BLOCK"),
            "VLA-GET-TEXTSTYLES": lambda db: (db, "STYLE"),
            "VLA-ITEM": self.item,
            "VLAX-MAKE-SAFEARRAY": self.array,
            "VLAX-SAFEARRAY-PUT-ELEMENT": lambda array, index, value: array.__setitem__(index, value),
            "VLA-COPYOBJECTS": self.copy,
            "VLAX-RELEASE-OBJECT": lambda db: self.released.append(db),
            "PRINC": lambda value="": self.messages.append(str(value)),
            "COMMAND": lambda *args: self.fail("import must not run an insert command"),
            "VLA-INSERTBLOCK": lambda *args: self.fail("import must not create a wrapper or sample entity"),
            "VLA-SAVEAS": lambda *args: self.fail("source DWG must not be saved"),
        })

    def interface(self, app, progid):
        self.events.append(("interface", app, progid))
        if self.fail_stage == "interface":
            raise RuntimeError("ObjectDBX unavailable")
        return "dbx"

    def open_database(self, db, method, path):
        self.events.append(("open", db, str(method), path))
        if self.fail_stage == "open":
            raise RuntimeError("cannot open source DWG")

    def item(self, owner, name):
        db, kind = owner
        self.assertEqual(db, "dbx")
        self.events.append(("item", kind, name))
        if name not in self.source[kind]:
            raise RuntimeError("source symbol not found: " + name)
        return self.source[kind][name]

    def array(self, datatype, bounds):
        self.assertEqual(datatype, 9)
        self.assertEqual(bounds.car, 0)
        return [None] * (bounds.cdr + 1)

    def copy(self, db, objects, owner):
        self.assertEqual(db, "dbx")
        target, kind = owner
        self.assertEqual(target, "target")
        self.events.append(("copy", kind, list(objects)))
        if self.fail_stage == "copy":
            raise RuntimeError("deep clone failed")
        if self.ignore_copy:
            return None
        for source_kind, name in objects:
            self.assertEqual(source_kind, kind)
            self.assertNotIn(name, self.target[kind], "existing definitions must not be replaced")
            self.target[kind][name] = "imported"
        if kind == "BLOCK" and self.clone_style_dependencies:
            self.target["STYLE"].update({name: "dependency" for name in STYLES})
        return objects

    def call(self):
        return self.h.call(Symbol("EL:ENSURESYSTEMBLOCKS"), [BLOCKS, STYLES])

    def test_missing_definitions_import_from_matching_dbx_and_read_back(self):
        self.assertTrue(truth(self.call()))
        self.assertEqual(set(self.target["BLOCK"]), set(BLOCKS))
        self.assertEqual(set(self.target["STYLE"]), set(STYLES))
        self.assertEqual(self.events[0], ("interface", "application", "ObjectDBX.AxDbDocument.23"))
        copies = [event for event in self.events if event[0] == "copy"]
        self.assertEqual([event[1] for event in copies], ["BLOCK", "STYLE"])
        self.assertTrue(all(event[0] != "copy" for event in self.events[:6]))
        self.assertEqual(self.released, ["dbx"])
        self.assertIsNone(self.h.lookup("*EL:SYSTEMBLOCKNOTICE*"))
        self.assertGreaterEqual(self.h.lookup("*EL:FRESHEPOCH*"), 6)

    def test_default_drawing_and_unknown_sources_report_names_without_library_lookup(self):
        for source in (None, Symbol("DRAWING"), Symbol("UNKNOWN"), "library", 1):
            with self.subTest(source=source):
                self.setUp()
                self.h.set("*EL:SYSTEMBLOCKSOURCE*", source)
                self.h.builtins["FINDFILE"] = lambda path: self.fail("drawing source must not search library paths")
                self.assertFalse(truth(self.call()))
                self.assertEqual(self.events, [])
                self.assertEqual(self.released, [])
                self.assertEqual(self.target, {"BLOCK": {}, "STYLE": {}})
                notice = self.h.lookup("*EL:SYSTEMBLOCKNOTICE*")
                for name in BLOCKS + STYLES:
                    self.assertIn(name, notice)
                self.assertIn("当前输入保留", notice)

    def test_drawing_source_with_existing_definitions_succeeds_and_clears_old_notice(self):
        self.h.set("*EL:SYSTEMBLOCKSOURCE*", None)
        self.h.set("*EL:SYSTEMBLOCKNOTICE*", "old failure")
        self.target = {"BLOCK": dict.fromkeys(BLOCKS, "existing"), "STYLE": dict.fromkeys(STYLES, "existing")}
        self.h.builtins["FINDFILE"] = lambda path: self.fail("existing definitions must not search library paths")
        self.assertTrue(truth(self.call()))
        self.assertIsNone(self.h.lookup("*EL:SYSTEMBLOCKNOTICE*"))
        self.assertEqual(self.events, [])

    def test_drawing_failure_can_retry_explicit_library_without_losing_existing_symbols(self):
        self.target["BLOCK"][BLOCKS[0]] = "keep-panel"
        self.target["STYLE"][STYLES[0]] = "keep-style"
        self.h.set("*EL:SYSTEMBLOCKSOURCE*", Symbol("DRAWING"))
        self.assertFalse(truth(self.call()))
        notice = self.h.lookup("*EL:SYSTEMBLOCKNOTICE*")
        self.assertNotIn(BLOCKS[0], notice)
        self.assertNotIn(STYLES[0], notice)
        self.assertIn(BLOCKS[1], notice)
        self.assertIn(STYLES[1], notice)
        self.h.set("*EL:SYSTEMBLOCKSOURCE*", Symbol("LIBRARY"))
        self.assertTrue(truth(self.call()))
        self.assertEqual(self.target["BLOCK"][BLOCKS[0]], "keep-panel")
        self.assertEqual(self.target["STYLE"][STYLES[0]], "keep-style")
        self.assertIsNone(self.h.lookup("*EL:SYSTEMBLOCKNOTICE*"))

    def test_existing_definitions_skip_source_and_com(self):
        for kind, names in (("BLOCK", BLOCKS), ("STYLE", STYLES)):
            self.target[kind] = {name: "existing" for name in names}
        self.path_exists = False
        self.assertTrue(truth(self.call()))
        self.assertEqual(self.events, [])

    def test_partial_missing_preserves_existing_block_and_style_objects(self):
        self.target["BLOCK"][BLOCKS[0]] = "keep-panel"
        self.target["STYLE"][STYLES[0]] = "keep-style"
        self.assertTrue(truth(self.call()))
        self.assertEqual(self.target["BLOCK"][BLOCKS[0]], "keep-panel")
        self.assertEqual(self.target["STYLE"][STYLES[0]], "keep-style")
        copies = [event for event in self.events if event[0] == "copy"]
        self.assertEqual(copies[0][2], [("BLOCK", BLOCKS[1])])
        self.assertEqual(copies[1][2], [("STYLE", STYLES[1])])

    def test_block_dependencies_do_not_cause_duplicate_style_copy(self):
        self.clone_style_dependencies = True
        self.assertTrue(truth(self.call()))
        self.assertEqual([e[1] for e in self.events if e[0] == "copy"], ["BLOCK"])

    def test_missing_library_returns_failure_without_opening_database(self):
        self.path_exists = False
        self.assertFalse(truth(self.call()))
        self.assertEqual(self.events, [])
        self.assertIn("当前输入保留", "".join(self.messages))

    def test_missing_source_symbol_stops_before_any_target_write_and_releases_dbx(self):
        del self.source["STYLE"][STYLES[1]]
        self.assertFalse(truth(self.call()))
        self.assertEqual(self.target, {"BLOCK": {}, "STYLE": {}})
        self.assertFalse(any(e[0] == "copy" for e in self.events))
        self.assertEqual(self.released, ["dbx"])
        self.assertIn(STYLES[1], "".join(self.messages))
        self.assertIn(STYLES[1], self.h.lookup("*EL:SYSTEMBLOCKNOTICE*"))

    def test_definitions_appearing_during_library_open_are_preserved(self):
        original_open = self.open_database

        def open_with_symbols(*args):
            original_open(*args)
            self.target["BLOCK"][BLOCKS[0]] = "arrived-panel"
            self.target["STYLE"][STYLES[0]] = "arrived-style"

        self.h.builtins["VLAX-INVOKE-METHOD"] = open_with_symbols
        self.assertTrue(truth(self.call()))
        self.assertEqual(self.target["BLOCK"][BLOCKS[0]], "arrived-panel")
        self.assertEqual(self.target["STYLE"][STYLES[0]], "arrived-style")

    def test_library_operations_have_separate_timing_stages(self):
        stages = []
        self.h.builtins["EL:PERFCALL"] = lambda stage, function, args: (
            stages.append(stage), self.h.call(function, args or []))[1]
        self.assertTrue(truth(self.call()))
        self.assertEqual(stages, ["SYSTEM_LIBRARY_OPEN", "SYSTEM_BLOCK_COPY", "SYSTEM_STYLE_COPY"])

    def test_com_errors_are_not_success_and_open_database_is_released(self):
        for stage in ("interface", "open", "copy"):
            with self.subTest(stage=stage):
                self.setUp()
                self.fail_stage = stage
                self.assertFalse(truth(self.call()))
                self.assertEqual(self.released, [] if stage == "interface" else ["dbx"])
                self.assertIn("导入失败", "".join(self.messages))
                self.assertIn("当前输入保留", self.h.lookup("*EL:SYSTEMBLOCKNOTICE*"))
                self.assertGreaterEqual(self.h.lookup("*EL:FRESHEPOCH*"), 2)

    def test_ignored_copy_cannot_pass_table_readback_and_retry_can_succeed(self):
        self.ignore_copy = True
        self.assertFalse(truth(self.call()))
        self.assertIn("未读到全部所需定义", "".join(self.messages))
        self.ignore_copy = False
        self.assertTrue(truth(self.call()))
        self.assertEqual(self.released, ["dbx", "dbx"])

    def test_capture_imports_before_style_checks_and_keeps_config_on_failure(self):
        self.h.load_definitions(ROOT / "src/fixed.lsp")
        self.h.load_definitions(ROOT / "src/generation.lsp")
        calls = []
        self.h.builtins["EL:ENSURESYSTEMBLOCKS"] = lambda blocks, styles: calls.append((blocks, styles)) or None
        self.h.builtins["TBLSEARCH"] = lambda *args: self.fail("style/template check ran after import failure")
        cfg = [Pair(Symbol("TEMPLATE"), "existing-template")]
        result = self.h.call(Symbol("EL:CAPTUREFIXEDTEMPLATE"), [cfg])
        self.assertFalse(truth(result))
        self.assertEqual(calls, [(BLOCKS, STYLES)])
        self.assertEqual(cfg, [Pair(Symbol("TEMPLATE"), "existing-template")])


class RedStepDrawingTests(unittest.TestCase):
    def test_four_step_numbers_are_red_and_fit_image_tiles_at_two_sizes(self):
        h = Host()
        h.load_definitions(ROOT / "src/panel.lsp")
        for width, height in ((64, 20), (128, 40)):
            images = {}
            current = [None]
            h.builtins.update({
                "DIMX_TILE": lambda key: width, "DIMY_TILE": lambda key: height,
                "START_IMAGE": lambda key: (images.__setitem__(key, []), current.__setitem__(0, key)),
                "FILL_IMAGE": lambda *args: images[current[0]].append(args),
                "END_IMAGE": lambda: current.__setitem__(0, None),
            })
            h.call(Symbol("EL:STEPLABELSDRAW"), [])
            self.assertEqual(set(images), {"p_step1", "p_step2", "p_step3", "p_step4"})
            for rectangles in images.values():
                self.assertEqual(rectangles[0], (0, 0, width, height, -15))
                self.assertGreater(len(rectangles), 20)
                for x, y, w, hh, color in rectangles[1:]:
                    self.assertEqual(color, 1)
                    self.assertTrue(0 <= x < x + w <= width)
                    self.assertTrue(0 <= y < y + hh <= height)


if __name__ == "__main__":
    unittest.main()
