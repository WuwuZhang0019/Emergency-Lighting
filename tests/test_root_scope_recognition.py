"""Date: 2026-10-21. Status: rooted lazy collection frozen-source regression.

Finite adapters compare c01ea3e collection and current collection in fresh hosts.
Operation counts prove deferred work; they are not native CAD timing evidence.
"""
import copy
from collections import Counter
from pathlib import Path
import random
import subprocess
import unittest

from autolisp_host import Pair, Symbol, parse, truth
from check_store_read_work import exact
import test_simple_flow as simple

ROOT = Path(__file__).resolve().parents[1]
FROZEN = "c01ea3e"


def pair(key, value):
    return Pair(Symbol(key.upper()), value)


class RootScopeRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = subprocess.check_output(
            ["git", "show", FROZEN + ":src/simple.lsp"], cwd=ROOT).decode("utf-8")
        cls.frozen_collect = next(form for form in parse(source)
                                  if isinstance(form, list) and form[:2] ==
                                  [Symbol("DEFUN"), Symbol("EL:SIMPLECOLLECT")])

    def fixture(self):
        f = simple.SimpleFlowTests()
        f.setUp()
        for name in ("fixed", "panel"):
            f.h.load_definitions(ROOT / "src" / (name + ".lsp"))
        form = self.frozen_collect
        f.h.evaluate([form[0], Symbol("ORACLE:ROOTCOLLECT71"), *form[2:]])
        f.h.step_limit = 150_000_000
        f.h.builtins.update({
            "CHR": chr,
            "MIN": lambda *values: min(values),
            "MAX": lambda *values: max(values),
            "GETVAR": lambda key: {"MILLISECS": 0, "CDATE": 20261021.18,
                                    "DWGNAME": "root-scope.dwg", "DWGPREFIX": "C:/cad/"}.get(key),
            "VLA-GET-EFFECTIVENAME": lambda entity: next(row.cdr for row in f.entities[entity]
                                                          if isinstance(row, Pair) and row.car == 2),
            "EL:MANAGEDENTITY": lambda entity: None,
            "EL:LOGEVENT": lambda *args: None,
        })
        f.cfg = f.call("EL:Put", Symbol("PRESET-SCOPED"), True, f.cfg)
        f.cfg = f.call("EL:Put", Symbol("DEVICE-NAMES"), ["LAMP", "SIGN"], f.cfg)
        return f

    def put(self, f, key, value):
        f.cfg = f.call("EL:Put", Symbol(key.upper()), value, f.cfg)

    def starts(self, f, rows):
        starts = []
        for handle, side in rows:
            record = f.call("EL:WireRecord", handle, f.cfg)
            endpoint = f.call("EL:By", Symbol("KEY"), [handle, Symbol(side.upper())],
                              f.get("ends", record))
            self.assertIsNotNone(endpoint, (handle, side))
            starts.append([pair("wire", handle), pair("end", Symbol(side.upper())),
                           pair("point", f.get("point", endpoint))])
        self.put(f, "auto-panel", "panel")
        self.put(f, "circuit-starts", starts)

    def polyline(self, f, handle, points, bulges=None, width=0., widths=None, closed=0, normal=None):
        data = [Pair(0, "LWPOLYLINE"), Pair(5, handle), Pair(8, "W"), Pair(410, "Model"),
                Pair(70, closed), Pair(38, points[0][2]), Pair(43, width),
                Pair(210, normal or [0., 0., 1.])]
        for index, point in enumerate(points):
            data.append(Pair(10, point[:2]))
            if bulges is not None:
                data.append(Pair(42, bulges[index]))
            if widths is not None:
                data.extend([Pair(40, widths[index][0]), Pair(41, widths[index][1])])
        f.entities[handle] = data

    def base(self, f):
        f.block("BOX", "P", "panel", [0., 0., 0.])
        f.line("root", [1., 0., 0.], [9., 0., 0.], "W")
        f.block("LAMP", "D", "lamp", [10., 0., 0.])
        f.selected = ["panel", "root", "lamp"]
        self.starts(f, [("root", "start")])

    def four_roots(self, f, remote=0):
        f.block("BOX", "P", "panel", [0., 0., 0.])
        f.selected = ["panel"]
        for i in range(4):
            y = float(i * 100)
            handle, lamp = f"root-{i}", f"lamp-{i}"
            f.line(handle, [1., y, 0.], [19., y, 0.], "W")
            f.entities[handle].append([-3, ["linenum", Pair(1000, f"ZE{i+1}")]])
            f.block("LAMP", "D", lamp, [20., y, 0.])
            f.selected += [handle, lamp]
        self.starts(f, [(f"root-{i}", "start") for i in range(4)])
        for i in range(remote):
            x, y = 100000. + float(i % 32) * 100., 100000. + float(i // 32) * 100.
            handle, lamp = f"remote-wire-{i}", f"remote-lamp-{i}"
            if i % 2:
                self.polyline(f, handle, [[x, y, 0.], [x+9., y, 0.]], [0., 0.])
            else:
                f.line(handle, [x, y, 0.], [x+9., y, 0.], "W")
            f.block("LAMP", "D", lamp, [x+10., y, 0.])
            f.selected += [handle, lamp]

    def instrument(self, f):
        counts = Counter()
        calls = {"wire": [], "contour": []}
        original = f.h.call
        def observe(name, args):
            if name == Symbol("EL:WIRERECORDDXF"):
                counts["wire_records"] += 1
                calls["wire"].append(args[0])
            elif name == Symbol("EL:POLYLINEDATADXF"):
                counts["polyline_records"] += 1
            elif name == Symbol("EL:BLOCKCONTOUR"):
                counts["contours"] += 1
                calls["contour"].append(args[0])
            elif name == Symbol("EL:ENTITYBOUNDS"):
                counts["bounds"] += 1
            return original(name, args)
        f.h.call = observe
        return counts, calls

    def preview(self, f, result):
        """Run actual preview dispatch while replacing only native UI effects."""
        draws, extents = [], []
        f.h.builtins.update({
            "EL:COLORPREVIEWCLEANUP": lambda: True,
            "EL:CLEARGAPPREVIEW": lambda: None,
            "EL:CLEARPICKHIGHLIGHTS": lambda: None,
            "EL:SIMPLEZOOM": lambda *args: extents.append(copy.deepcopy(args)),
            "EL:COLORPREVIEWENTITY": lambda *args: draws.append(("entity", copy.deepcopy(args))),
            "EL:COLORPREVIEWWIRE": lambda *args: draws.append(("wire", copy.deepcopy(args))),
            "GETSTRING": lambda *args: "",
            "REDRAW": lambda *args: None,
        })
        # Invalid/shared circuits are not previewable; keep their exact circuit
        # payload in projection and cover visual dispatch for valid cases only.
        ids = [handle for circuit in f.get("circuits", result) or []
               for handle in (f.get("wires", circuit) or []) + (f.get("devices", circuit) or [])]
        if len(ids) != len(set(ids)):
            return ("shared", ids)
        f.call("EL:AllCircuitColorWait", result)
        return draws, extents

    def run_case(self, build, baseline=False):
        f = self.fixture()
        build(f)
        before = copy.deepcopy(f.entities)
        counts, calls = self.instrument(f)
        snapshot = f.call("oracle:RootCollect71" if baseline else "EL:SimpleCollect", f.cfg)
        snapshot = f.call("EL:StartSnapshot", snapshot, f.cfg, "panel")
        network = f.call("EL:SimpleNetwork", snapshot, f.cfg, "panel")
        result = f.call("EL:SplitNetwork", network, f.cfg)
        result = f.call("EL:SplitNativeNumberBranches", result, network, f.cfg)
        result = f.call("EL:SelectFixedExits", result, None)
        result = f.call("EL:ResolveCircuitNumbers", result)
        connected = f.get("wire-ids", network) or []
        # Snapshots intentionally differ in distant candidates and source facts.
        # Every connected wire's complete precision geometry remains compared.
        projection = {
            "edges": f.get("edges", network),
            "wire_ids": connected,
            "devices": f.get("devices", network),
            "gap_pairs": f.get("gap-pairs", network),
            "gap_issues": f.get("gap-issues", network),
            "connected_wire_records": [f.call("EL:By", Symbol("ID"), handle,
                                                 f.get("wires", f.get("snapshot", network)))
                                       for handle in connected],
            "circuits": f.get("circuits", result),
            "complete": f.get("complete", result),
            "number_inputs": f.get("number-inputs", result),
            "preview": self.preview(f, result),
        }
        self.assertEqual(f.entities, before, "recognition and preview adapters must not mutate source")
        return f, snapshot, network, result, projection, counts, calls

    def compare(self, build):
        old = self.run_case(build, baseline=True)
        new = self.run_case(build)
        self.assertEqual(exact(new[4]), exact(old[4]))
        return old, new

    def test_four_picked_roots_preserve_numbers_order_and_preview(self):
        old, new = self.compare(lambda f: self.four_roots(f, remote=12))
        f, _, network, result, _, counts, calls = new
        self.assertEqual(len(f.get("wire-ids", network)), 4)
        self.assertEqual(len(f.get("devices", network)), 4)
        self.assertEqual([f.get("circuit-number", row) for row in f.get("circuits", result)],
                         ["ZE1", "ZE2", "ZE3", "ZE4"])
        self.assertEqual(set(calls["wire"]), {f"root-{i}" for i in range(4)})
        self.assertEqual(counts["wire_records"], 4, "hydrate each root only once")
        self.assertEqual(old[5]["wire_records"], 16)

    def test_far_continuation_t_endpoints_and_crossing_interiors(self):
        def build(f):
            self.base(f)
            f.line("root", [1., 0., 0.], [100009., 0., 0.], "W")
            f.block("LAMP", "D", "lamp", [100010., 0., 0.])
            for name, a, b, device in (
                ("north", [50., 0., 0.], [50., 9., 0.], [50., 10., 0.]),
                ("south", [75., -9., 0.], [75., 0., 0.], [75., -10., 0.]),
                ("cross", [90., -20., 0.], [90., 20., 0.], [90., 21., 0.])):
                f.line(name, a, b, "W")
                f.block("LAMP", "D", name + "-lamp", device)
                f.selected += [name, name + "-lamp"]
            self.starts(f, [("root", "start")])
        _, new = self.compare(build)
        f, _, network, *_ = new
        self.assertEqual(set(f.get("wire-ids", network)), {"root", "north", "south"})
        self.assertNotIn("cross-lamp", [f.get("id", row) for row in f.get("devices", network)])

    def test_touching_device_chain_finds_onward_wire_but_bbox_miss_does_not(self):
        def build(f):
            self.base(f)
            for name, position in (("b", [10., 2., 0.]), ("c", [10., 4., 0.]),
                                   ("d", [100010., 4., 0.])):
                f.block("SIGN", "D", name, position)
                f.selected.append(name)
            f.line("onward", [11., 4., 0.], [100009., 4., 0.], "W")
            f.block("SIGN", "D", "false", [500., 500., 0.])
            f.bounds["false"] = [[8., -1., 0.], [501., 501., 0.]]
            f.line("independent", [501., 500., 0.], [519., 500., 0.], "W")
            f.block("LAMP", "D", "remote-lamp", [520., 500., 0.])
            f.selected += ["onward", "false", "independent", "remote-lamp"]
        _, new = self.compare(build)
        f, _, network, *_ = new
        self.assertEqual(set(f.get("wire-ids", network)), {"root", "onward"})
        self.assertEqual({f.get("id", row) for row in f.get("devices", network)},
                         {"lamp", "b", "c", "d"})

    def test_multiple_gaps_and_reversed_bent_end_direction(self):
        def build(f):
            self.base(f)
            self.polyline(f, "root", [[1., 0., 0.], [5., 0., 0.], [5., 10., 0.]])
            self.polyline(f, "middle", [[29., 25., 0.], [5., 25., 0.], [5., 20., 0.]])
            f.line("last", [40., 25., 0.], [49., 25., 0.], "W")
            f.block("LAMP", "D", "lamp", [50., 25., 0.])
            f.selected += ["middle", "last"]
            self.starts(f, [("root", "start")])
        _, new = self.compare(build)
        self.assertEqual(len(new[0].get("gap-pairs", new[2])), 2)

    def test_gap_uniqueness_occupancy_and_nonconnected_blockers(self):
        for kind in ("free", "second-candidate", "occupied", "collinear", "cross", "other-z", "over-range"):
            def build(f, kind=kind):
                self.base(f)
                f.line("root", [1., 0., 0.], [10., 0., 0.], "W")
                f.line("after", [20., 0., 0.], [29., 0., 0.], "W")
                f.block("LAMP", "D", "lamp", [30., 0., 0.])
                f.selected.append("after")
                if kind == "second-candidate":
                    f.line("second", [20., 0., 0.], [20., 10., 0.], "W")
                    f.selected.append("second")
                elif kind == "occupied":
                    f.block("SIGN", "D", "terminal", [20., 0., 0.])
                    f.selected.append("terminal")
                elif kind in ("collinear", "cross"):
                    a, b = ([14., 0., 0.], [16., 0., 0.]) if kind == "collinear" else ([15., -5., 0.], [15., 5., 0.])
                    f.line("blocker", a, b, "W")
                    f.selected.append("blocker")
                elif kind == "other-z":
                    f.line("after", [20., 0., 1.], [29., 0., 1.], "W")
                elif kind == "over-range":
                    f.line("after", [2011., 0., 0.], [2020., 0., 0.], "W")
                self.starts(f, [("root", "start")])
            with self.subTest(kind=kind):
                self.compare(build)

    def test_width_and_bulge_envelopes_keep_contacts_outside_vertex_box(self):
        for kind in ("constant", "variable", "zero", "positive-bulge", "negative-bulge"):
            def build(f, kind=kind):
                self.base(f)
                if "bulge" in kind:
                    bulge = 1. if kind == "positive-bulge" else -1.
                    self.polyline(f, "root", [[1., 0., 0.], [19., 0., 0.]], [bulge, 0.])
                    f.block("LAMP", "D", "lamp", [10., -9. * bulge, 0.])
                else:
                    widths = [(2., 8.), (0., 0.)] if kind == "variable" else ([(0., 0.), (0., 0.)] if kind == "zero" else None)
                    self.polyline(f, "root", [[1., 0., 0.], [19., 0., 0.]], width=4., widths=widths)
                    f.block("LAMP", "D", "lamp", [10., 3., 0.])
                self.starts(f, [("root", "start")])
            with self.subTest(kind=kind):
                _, new = self.compare(build)
                expected = 0 if kind == "zero" else 1
                self.assertEqual(len(new[0].get("devices", new[2]) or []), expected)

    def test_selected_order_ties_and_duplicate_candidates_preserve_ordered_result(self):
        for seed in (7, 23, 109):
            def build(f, seed=seed):
                self.four_roots(f, remote=7)
                # The same candidate is returned by two touching wire paths.
                f.line("branch", [10., 0., 0.], [10., 9., 0.], "W")
                f.block("SIGN", "D", "branch-lamp", [10., 10., 0.])
                f.selected += ["branch", "branch-lamp"]
                random.Random(seed).shuffle(f.selected)
            with self.subTest(seed=seed):
                self.compare(build)

    def test_negative_ocs_and_elevation_keep_world_space_connections(self):
        for kind in ("negative-normal", "elevation"):
            def build(f, kind=kind):
                self.base(f)
                if kind == "negative-normal":
                    f.h.builtins["TRANS"] = lambda point, source, *args: ([-point[0], point[1], -point[2]]
                        if isinstance(source, list) and source == [0., 0., -1.] else point)
                    self.polyline(f, "root", [[-1., 0., 0.], [-19., 0., 0.]],
                                  normal=[0., 0., -1.])
                    f.block("LAMP", "D", "lamp", [20., 0., 0.])
                else:
                    self.polyline(f, "root", [[1., 0., 5.], [19., 0., 5.]])
                    f.block("LAMP", "D", "lamp", [20., 0., 5.])
                    f.line("other-z", [10., 0., 8.], [10., 10., 8.], "W")
                    f.selected.append("other-z")
                self.starts(f, [("root", "start")])
            with self.subTest(kind=kind):
                _, new = self.compare(build)
                f, _, network, *_ = new
                self.assertEqual([f.get("id", row) for row in f.get("devices", network)], ["lamp"])
                self.assertEqual(f.get("wire-ids", network), ["root"])

    def test_unprovable_remote_geometry_falls_back_and_preserves_global_issues(self):
        def build(f):
            self.base(f)
            f.line("remote-zero", [100000., 100000., 0.], [100000., 100000., 0.], "W")
            f.selected.append("remote-zero")
        old, new = self.compare(build)
        f, snapshot, network, result, _, _, calls = new
        self.assertFalse(truth(f.get("complete", result)))
        self.assertEqual(f.get("wire-ids", network), ["root"])
        self.assertIn("remote-zero", calls["wire"], "unprovable geometry must use the exact fallback")
        self.assertEqual(exact(f.get("issues", snapshot)), exact(old[0].get("issues", old[1])))

    def test_remote_unique_rgb_keeps_global_palette_and_preview_colors(self):
        def build(f):
            self.four_roots(f, remote=1)
            # Cyan is the first normal circuit-preview choice. A remote source
            # using it still participates in the existing global avoidance rule.
            f.entities["remote-wire-0"].append(Pair(420, 0x00FFFF))
        _, new = self.compare(build)
        f, _, _, result, *_ = new
        self.assertNotIn(4, f.call("EL:PreviewPalette", result))
        self.assertNotIn("remote-wire-0", new[6]["wire"], "global color reads need no wire geometry")

    def test_selected_closed_wire_keeps_start_validation_failure(self):
        def build(f):
            self.base(f)
            # Capture a valid start first, then modify the selected source.
            self.polyline(f, "root", [[1., 0., 0.], [9., 0., 0.], [9., 5., 0.]], closed=1)
        failures = []
        for baseline in (True, False):
            with self.assertRaises(RuntimeError) as raised:
                self.run_case(build, baseline=baseline)
            failures.append(str(raised.exception))
        self.assertEqual(failures[0], failures[1])

    def test_new_or_moved_source_objects_invalidate_the_reviewed_local_result(self):
        for mutation in ("connected-wire", "remote-wire", "new-contact"):
            with self.subTest(mutation=mutation):
                f, _, _, result, *_ = self.run_case(lambda f: self.four_roots(f, remote=1))
                self.assertTrue(truth(f.call("EL:FreshResult", result, f.cfg)))
                if mutation == "connected-wire":
                    f.line("root-0", [1., 0., 0.], [18., 0., 0.], "W")
                elif mutation == "remote-wire":
                    f.line("remote-wire-0", [100000., 100000., 0.], [100008., 100000., 0.], "W")
                else:
                    f.line("new-contact", [10., 0., 0.], [10., 9., 0.], "W")
                    f.selected.append("new-contact")
                f.call("EL:FreshBoundary")
                self.assertFalse(truth(f.call("EL:FreshResult", result, f.cfg)))

    def ray_order_fixture(self, f):
        self.base(f)
        f.line("branch", [5., 0., 0.], [5., 5., 0.], "W")
        f.block("SIGN", "D", "branch-lamp", [5., 6., 0.])
        # The downward forward ray reaches lamp's box. The line itself is
        # physically separate and cannot form a straight gap to either root end.
        f.line("remote-ray", [10., 10., 0.], [10., 5., 0.], "W")
        f.selected += ["branch", "branch-lamp", "remote-ray"]

    def test_unconnected_ray_candidate_preserves_connected_device_order(self):
        old, new = self.compare(self.ray_order_fixture)
        f, _, network, *_ = new
        self.assertEqual(set(f.get("wire-ids", network)), {"root", "branch"})
        self.assertNotIn("remote-ray", new[6]["wire"], "candidate order should not force distant precision work")
        self.assertEqual([f.get("id", row) for row in f.get("devices", network)],
                         [old[0].get("id", row) for row in old[0].get("devices", old[2])])

    def test_remote_entity_growth_does_not_grow_precision_geometry_work(self):
        rows = []
        for remote in (0, 100, 1000):
            new = self.run_case(lambda f, remote=remote: self.four_roots(f, remote=remote))
            rows.append(new)
            self.assertEqual(new[5]["wire_records"], 4, remote)
            self.assertEqual(new[5]["polyline_records"], 0, remote)
            self.assertFalse(any(handle.startswith("remote-") for handle in new[6]["wire"]), remote)
            self.assertFalse(any(handle.startswith("remote-") for handle in new[6]["contour"]), remote)
        self.assertEqual(exact(rows[0][4]), exact(rows[1][4]))
        self.assertEqual(exact(rows[0][4]), exact(rows[2][4]))
        self.assertEqual([row[5]["contours"] for row in rows], [rows[0][5]["contours"]] * 3)


if __name__ == "__main__":
    unittest.main()
