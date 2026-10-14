"""Current-source draft and new-only generation checks. Date: 2026-10-14.

Finite adapters verify store identities and untouched old output; native CAD
geometry/contact and placement still require original-DWG acceptance.
"""
import copy
import unittest

from autolisp_host import Host, Symbol, truth
import test_diagram_store as storage
import test_diagram_update as generation
import test_post_stat_workflow as workflow


class SimplifiedFlowTests(unittest.TestCase):
    def test_one_current_record_per_source_and_monotonic_ids(self):
        f = storage.StoreTests()
        f.setUp()
        h = f.h
        h.load_definitions(storage.ROOT / "src" / "geometry.lsp")
        h.run('''(setq store (EL:StoreInitial)
          a1 (EL:NewRecord "A" store)
          store (EL:StorePutDiagram a1 store)
          b1 (EL:NewRecord "B" store)
          store (EL:StorePutDiagram b1 store)
          a2 (EL:NewRecord "A" store)
          store (EL:StorePutDiagram a2 store))''')
        self.assertEqual(h.run("(length (EL:Get 'diagrams store))"), 2)
        self.assertEqual(h.run("(EL:Get 'diagram-id (EL:DiagramForPanel \"A\" store))"),
                         h.run("(EL:Get 'diagram-id a2)"))
        self.assertEqual(h.run("(EL:Get 'diagram-id (EL:DiagramForPanel \"B\" store))"),
                         h.run("(EL:Get 'diagram-id b1)"))
        self.assertEqual(h.run("(EL:DiagramSerial (EL:Get 'diagram-id a2) \"A\" store)"), 2)
        h.run("(setq a3 (EL:NewRecord \"A\" store))")
        self.assertEqual(h.run("(EL:DiagramSerial (EL:Get 'diagram-id a3) \"A\" store)"), 3)
        h.run('''(setq malformed (EL:Put 'diagram-id
          (strcat (EL:Get 'drawing-uuid store) "/A/A0") a3)
          store (EL:StorePutDiagram malformed store))''')
        self.assertEqual(h.run("(EL:DiagramSerial (EL:Get 'diagram-id malformed) \"A\" store)"), 0)
        self.assertEqual(h.run("(EL:DiagramSerial (EL:Get 'diagram-id (EL:NewRecord \"A\" store)) \"A\" store)"), 3)

    def test_consecutive_generation_keeps_old_entities_and_prunes_history(self):
        f = generation.UpdateTests()
        f.setUp()
        f.install_sync()
        h = f.h
        getvar = h.builtins["GETVAR"]
        h.builtins["GETVAR"] = lambda key: (
            1 if key == "TILEMODE" else 2 if key == "CVPORT"
            else 20261014.0 if key == "CDATE" else getvar(key))
        h.builtins.update({
            "GETPOINT": lambda *args: [100., 200., 0.],
            "TRANS": lambda point, *args: point,
            "EL:OUTPUTLAYERREADY": lambda *args: True,
            "EL:FIXEDTEMPLATE": lambda template: template,
            "EL:NUMBERINPUTSCURRENT": lambda *args: True,
            "EL:DLSUBMISSIONCURRENT": lambda *args: True,
        })
        self.assertTrue(truth(h.run("(EL:SyncDiagram result nil nil 'cap300 T nil)")))
        first = h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        first_id = f.get("diagram-id", first)
        refs = f.call("EL:DiagramOutputRefs", first)
        old_entities = {handle: copy.deepcopy(f.entities[handle])
                        for handle, *_ in refs if handle}
        self.assertTrue(truth(h.run("(EL:SyncDiagram result nil nil 'cap300 T nil)")))
        second = h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertNotEqual(first_id, f.get("diagram-id", second))
        self.assertEqual(h.run("(length (EL:Get 'diagrams (EL:StoreRead)))"), 1)
        self.assertIsNone(f.call("EL:StoreRecord", first_id))
        for handle, data in old_entities.items():
            self.assertEqual(f.entities[handle], data)

    def test_elstat_starts_with_pick_without_history_dialog(self):
        h = Host()
        h.load_definitions(storage.ROOT / "src" / "diagram-commands.lsp")
        stages = []
        h.builtins.update({
            "EL:PERFSTART": lambda stage: stages.append(stage) or "timer",
            "EL:PERFCALL": lambda stage, function, args:
                stages.append(stage) or h.call(function, args or []),
            "EL:PERFFINISH": lambda *args: True,
            "EL:FIXEDSTATPICK": lambda: stages.append("picked") or None,
            "EL:GET": lambda key, row: None,
        })
        h.call(Symbol("EL:FIXEDSTAT"), [])
        self.assertEqual(stages, ["ELSTAT", "PICK_PANEL", "picked"])

    def test_review_preview_and_library_do_not_reidentify_or_precompute_legends(self):
        for key, expected in (("f_preview", ["compute", "preview"]),
                              ("b_library", ["compute"])):
            with self.subTest(action=key):
                f = workflow.PostStatWorkflowTests()
                f.setUp()
                h, callbacks, calls = f.h, {}, []
                h.builtins["ACTION_TILE"] = lambda tile, action: callbacks.__setitem__(tile, action)
                for name in ("EL:RECOGNIZEFIXED", "EL:THUMBPREPARE", "EL:FRESHRESULT"):
                    h.builtins[name] = lambda *args, stage=name: self.fail(stage)

                def compute(*args):
                    calls.append("compute")
                    del h.builtins["EL:PANELCOMPUTE"]
                    try:
                        return h.call(Symbol("EL:PANELCOMPUTE"), list(args))
                    finally:
                        h.builtins["EL:PANELCOMPUTE"] = compute

                h.builtins["EL:PANELCOMPUTE"] = compute
                h.builtins["EL:ALLCIRCUITCOLORPREVIEW"] = lambda result: calls.append("preview")
                f.actions = [lambda: f.invoke_action(callbacks, key)]
                if key == "f_preview":
                    f.actions.append(lambda: f.invoke_action(callbacks, "cancel"))
                result = f.dialog()
                self.assertEqual(calls, expected)
                self.assertEqual(len(f.dialogs), 2 if key == "f_preview" else 1)
                if key == "b_library":
                    self.assertTrue(f.get("library-panel", result))

    def test_legacy_hidden_exclusions_do_not_drop_explicitly_picked_devices(self):
        f = workflow.PostStatWorkflowTests()
        f.setUp()
        f.result = f.call("EL:Put", Symbol("EXCLUDED-DEVICES"), ["a"], f.result)
        f.result = f.call("EL:Put", Symbol("EXCLUDED-SEEDS"),
                          [f.get("key", f.get("seed", f.get("circuits", f.result)[0]))], f.result)
        callbacks = {}
        f.h.builtins["ACTION_TILE"] = lambda tile, action: callbacks.__setitem__(tile, action)
        f.actions = [lambda: f.invoke_action(callbacks, "cancel")]
        f.dialog()
        self.assertIn("已识别设备 2 个", f.tiles["p_device_status"])
        self.assertTrue(f.tiles["p_row0"])


if __name__ == "__main__":
    unittest.main()
