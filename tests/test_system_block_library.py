"""System-library folder action and input retention. Date: 2026-10-15.

Finite CAD/DCL adapters only; no native AutoCAD or Explorer acceptance.
"""
import unittest
from pathlib import PureWindowsPath

from autolisp_host import Host, Symbol
import test_post_stat_workflow as workflow

ROOT = workflow.db.ROOT


class SystemBlockLibraryTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for module in ("config", "panel"):
            self.h.load_definitions(ROOT / "src" / (module + ".lsp"))
        self.root = "C:/中文 目录/工具包/"
        self.path = self.root + "templates/系统图块库.dwg"
        self.folder = self.root + "templates"
        self.present = True
        self.directory = True
        self.opened = []
        self.h.set("*EL:ROOT*", self.root)
        self.h.builtins.update({
            "VL-STRING-RIGHT-TRIM": lambda chars, value: value.rstrip(chars),
            "VL-FILENAME-DIRECTORY": lambda value: value.rsplit("/", 1)[0],
            "VL-FILE-DIRECTORY-P": lambda value: value == self.folder and self.directory,
            "FINDFILE": lambda value: value if value == self.path and self.present else None,
            "VL-STRING-TRANSLATE": lambda old, new, value: value.translate(str.maketrans(old, new)),
            "STARTAPP": lambda app, args: self.opened.append((app, args)) or 1,
        })

    def call(self):
        return self.h.call(Symbol("EL:PANELOPENBLOCKLIBRARY"), [])

    def test_selects_bundled_dwg_with_chinese_and_space_path(self):
        self.assertIn("已打开", self.call())
        self.assertEqual(self.opened, [("explorer.exe", '/select,"' + str(PureWindowsPath(self.path)) + '"')])

    def test_missing_dwg_opens_folder_and_reports_missing_file(self):
        self.present = False
        self.assertIn("尚缺系统图块库.dwg", self.call())
        self.assertEqual(self.opened, [("explorer.exe", '"' + str(PureWindowsPath(self.folder)) + '"')])

    def test_launch_failure_and_exception_are_reported(self):
        def fail(*args):
            raise RuntimeError("launch rejected")
        for launch in (lambda *args: None, fail):
            with self.subTest(launch=launch):
                self.h.builtins["STARTAPP"] = launch
                self.assertIn("无法打开", self.call())

    def test_missing_directory_or_root_does_not_launch_explorer(self):
        self.directory = False
        self.assertIn("不存在", self.call())
        self.h.set("*EL:ROOT*", None)
        self.assertIn("不存在", self.call())
        self.assertEqual(self.opened, [])

    def test_folder_action_keeps_capacity_power_and_unsaved_library_edits(self):
        f = workflow.PostStatWorkflowTests()
        f.setUp()
        callbacks, opens = {}, []
        f.h.builtins["ACTION_TILE"] = lambda key, action: callbacks.__setitem__(key, action)
        f.h.builtins["EL:PANELOPENBLOCKLIBRARY"] = lambda: opens.append(True) or "已打开图块文件夹"
        def edit_and_open():
            f.tiles["dl_display"] = "保留的设备名称"
            f.tiles["dl_watts"] = "7"
            f.call("EL:PanelCapacity", "p_600")
            f.invoke_action(callbacks, "p_block_library_open")
        f.actions = [edit_and_open, lambda: f.invoke_action(callbacks, "cancel")]
        f.dialog()
        self.assertEqual(opens, [True])
        self.assertEqual(f.dialogs, ["el_panel", "el_panel"])
        self.assertEqual(f.tiles["p_capacity"], "p_600")
        self.assertEqual(f.get("display", f.call("EL:DLUIDraft")), "保留的设备名称")
        self.assertEqual(f.get("watts-text", f.call("EL:DLUIDraft")), "7")
        self.assertEqual(f.tiles["dl_watts"], "7")
        self.assertEqual(f.tiles["dl_status"], "已打开图块文件夹")

    def test_home_folder_action_does_not_trigger_recognition_or_clear_edits(self):
        f = workflow.PostStatWorkflowTests()
        f.setUp()
        callbacks = {}
        f.h.builtins["ACTION_TILE"] = lambda key, action: callbacks.__setitem__(key, action)
        f.h.builtins["EL:PANELOPENBLOCKLIBRARY"] = lambda: "已打开图块文件夹"
        f.h.builtins["EL:RECOGNIZEFIXED"] = lambda *args: self.fail("unexpected recognition")
        f.actions = [lambda: (f.tiles.__setitem__("dl_display", "未拾取时的编辑"),
                              f.invoke_action(callbacks, "p_block_library_open")),
                     lambda: f.invoke_action(callbacks, "cancel")]
        f.call("EL:PanelDialog", None, None, None, None)
        self.assertEqual(f.dialogs, ["el_panel", "el_panel"])
        self.assertEqual(f.get("display", f.call("EL:DLUIDraft")), "未拾取时的编辑")


if __name__ == "__main__":
    unittest.main()
