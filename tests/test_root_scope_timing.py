"""Date: 2026-10-21. Status: rooted discovery fixed-batch timing regression.

Frozen v0.1.73 discovery and finite clocks verify order/accounting, not CAD speed.
"""
import copy
from pathlib import Path
import subprocess
import unittest

from autolisp_host import Symbol, parse, truth
from check_store_read_work import exact
import test_root_scope_recognition as rooted

ROOT = Path(__file__).resolve().parents[1]
FROZEN = "9c0a448"


class RootScopeTimingTests(unittest.TestCase):
    stages = (
        "ROOT_SCOPE_PANEL_SHAPE", "ROOT_SCOPE_BLOCK_RECORDS", "ROOT_SCOPE_ROOT_PREPARE",
        "ROOT_SCOPE_START_SNAPSHOT", "ROOT_SCOPE_WIRE_INDEX", "ROOT_SCOPE_BLOCK_INDEX",
        "ROOT_SCOPE_JUNCTION_INDEX", "ROOT_SCOPE_END_INDEX", "ROOT_SCOPE_GAP_SNAPSHOT",
        "ROOT_SCOPE_ROOT_LINKS", "ROOT_SCOPE_REACHABLE_TRACE", "ROOT_SCOPE_RESULT_ORDER",
    )
    domain_names = set(map(Symbol, (
        "EL:PANELCONTACTSHAPE", "EL:FIXEDBLOCKROLE", "EL:ROOTSCOPERESOLVE",
        "EL:STARTBOUNDARYBOUNDS", "EL:STARTSNAPSHOT", "EL:SPATIALTREE",
        "EL:JUNCTIONTREE", "EL:SIMPLEGAPSNAPSHOT", "EL:WALKLINK", "EL:WALKWIRE",
        "EL:WALKBLOCK", "EL:ROOTSCOPEGAPINDEX", "EL:SPATIALRAYQUERY", "EL:SPATIALBOXQUERY",
    )))

    @classmethod
    def setUpClass(cls):
        rooted.RootScopeRecognitionTests.setUpClass()
        source = subprocess.check_output(
            ["git", "show", FROZEN + ":src/simple.lsp"], cwd=ROOT).decode("utf-8")
        cls.frozen_discovery = next(form for form in parse(source)
            if isinstance(form, list) and form[:2] ==
            [Symbol("DEFUN"), Symbol("EL:ROOTSCOPEDISCOVER")])

    def helper(self):
        return rooted.RootScopeRecognitionTests()

    def observe(self, f, baseline=False, active=True):
        form = self.frozen_discovery
        f.h.evaluate([form[0], Symbol("ORACLE:ROOTDISCOVER73"), *form[2:]])
        original = f.h.call
        old_getvar = f.h.builtins["GETVAR"]
        state = {"inside": False, "ticks": 0, "clock": 0, "batchticks": 0, "inbatch": False, "domain": []}
        def getvar(key):
            if key == "MILLISECS":
                state["clock"] += 1
                if state["inside"]:
                    state["ticks"] += 1
                    if state["inbatch"]:
                        state["batchticks"] += 1
                return state["clock"]
            return old_getvar(key)
        f.h.builtins["GETVAR"] = getvar
        f.h.builtins["EL:COLLECTREADDETAILENABLED"] = lambda: None
        def observe(name, args):
            if name == Symbol("EL:ROOTSCOPEDISCOVER"):
                state["inside"] = True
                try:
                    return original(Symbol("ORACLE:ROOTDISCOVER73") if baseline else name, args)
                finally:
                    state["inside"] = False
            if state["inside"] and name in (Symbol("EL:PERFBEGIN"), Symbol("EL:PERFEND")):
                state["inbatch"] = True
                try:
                    return original(name, args)
                finally:
                    state["inbatch"] = False
            if state["inside"] and isinstance(name, Symbol) and name in self.domain_names:
                state["domain"].append((str(name), exact(copy.deepcopy(args))))
            return original(name, args)
        f.h.call = observe
        if active:
            f.call("EL:PerfStart", "ELSTAT")
        return state

    def run_discovery(self, build, baseline=False, active=True):
        helper = self.helper()
        state = []
        def prepared(f):
            build(helper, f)
            state.append(self.observe(f, baseline, active))
        result = helper.run_case(prepared)
        return result, state[0]

    def assert_rows(self, f):
        rows = f.h.lookup("*EL:MONITORROWS*")
        root = next(row for row in rows if f.get("stage", row) == "ROOT_SCOPE_DISCOVERY")
        children = [row for row in reversed(rows)
                    if f.get("parent-id", row) == f.get("id", root)]
        self.assertEqual([f.get("stage", row) for row in children], list(self.stages))
        self.assertEqual(len(children), 12)
        for row in [root, *children]:
            self.assertEqual(f.get("status", row), Symbol("RETURNED"))
            self.assertGreaterEqual(f.get("program-ms", row), 0)
        start = next(row for row in rows if f.get("stage", row) == "START_SNAPSHOT"
                     and f.get("parent", row) == "ROOT_SCOPE_START_SNAPSHOT")
        batch = next(row for row in children if f.get("stage", row) == "ROOT_SCOPE_START_SNAPSHOT")
        self.assertEqual(f.get("parent-id", start), f.get("id", batch))
        self.assertFalse(truth(f.h.lookup("*EL:PERFPENDING*")))

    def test_frozen_discovery_preserves_domain_call_order_result_numbers_and_preview(self):
        def four(helper, f):
            helper.four_roots(f, remote=12)
        def gap(helper, f):
            helper.base(f)
            f.line("root", [1., 0., 0.], [10., 0., 0.], "W")
            f.line("after", [20., 0., 0.], [29., 0., 0.], "W")
            f.block("LAMP", "D", "lamp", [30., 0., 0.])
            f.selected.append("after")
            helper.starts(f, [("root", "start")])
        for build in (four, gap):
            with self.subTest(build=build.__name__):
                old, before = self.run_discovery(build, baseline=True)
                new, after = self.run_discovery(build)
                self.assertEqual(after["domain"], before["domain"])
                self.assertEqual(exact(new[1]), exact(old[1]))
                self.assertEqual(exact(new[4]), exact(old[4]))
                self.assertEqual(after["ticks"] - before["ticks"], 24)
                self.assert_rows(new[0])

    def test_clock_reads_are_fixed_per_batch_when_remote_entities_grow(self):
        ticks = []
        for remote in (0, 100):
            new, state = self.run_discovery(lambda helper, f: helper.four_roots(f, remote))
            ticks.append(state["ticks"])
            self.assert_rows(new[0])
            self.assertEqual(new[5]["wire_records"], 4)
        self.assertGreater(ticks[0], 0)
        self.assertEqual(ticks[0], ticks[1], "no clock reads inside object loops")

    def test_disabled_performance_adds_no_batch_clock_reads_and_preserves_output(self):
        build = lambda helper, f: helper.four_roots(f, remote=10)
        old, before = self.run_discovery(build, baseline=True, active=False)
        new, after = self.run_discovery(build, active=False)
        # Existing contact/contour diagnostics may still read the clock.
        # Disabled PerfBegin/End must add none of their own.
        self.assertEqual(after["ticks"], before["ticks"])
        self.assertEqual(before["batchticks"], 0)
        self.assertEqual(after["batchticks"], 0)
        self.assertEqual(after["domain"], before["domain"])
        self.assertEqual(exact(new[4]), exact(old[4]))

    def test_all_fallback_emits_no_discovery_or_child_frames(self):
        def build(helper, f):
            helper.four_roots(f, remote=8)
            f.h.builtins["EL:ROOTSCOPEWIRE"] = lambda *args: None
        new, state = self.run_discovery(build)
        f = new[0]
        self.assertEqual(state["ticks"], 0)
        self.assertFalse(state["domain"])
        rows = f.h.lookup("*EL:MONITORROWS*")
        self.assertFalse([row for row in rows if f.get("stage", row) in
                          ("ROOT_SCOPE_DISCOVERY", *self.stages)])
        self.assertFalse(truth(f.h.lookup("*EL:PERFPENDING*")))

    def test_failed_index_preserves_error_and_unwinds_nested_batch(self):
        helper = self.helper()
        f = helper.fixture()
        helper.four_roots(f, remote=2)
        self.observe(f)
        original = f.h.call
        calls = []
        def broken(name, args):
            if name == Symbol("EL:SPATIALTREE") and truth(f.h.lookup("*EL:ROOTSCOPEACTIVE*")):
                calls.append(1)
                if len(calls) == 2:
                    raise RuntimeError("fixture discovery index failure")
            return original(name, args)
        f.h.call = broken
        with self.assertRaisesRegex(RuntimeError, "fixture discovery index failure"):
            f.call("EL:SimpleCollect", f.cfg)
        pending = f.h.lookup("*EL:PERFPENDING*")
        self.assertEqual([f.get("stage", row) for row in pending],
                         ["ROOT_SCOPE_BLOCK_INDEX", "ROOT_SCOPE_DISCOVERY"])
        f.call("EL:PerfUnwind", None)
        self.assertFalse(truth(f.h.lookup("*EL:PERFPENDING*")))
        failed = [row for row in f.h.lookup("*EL:MONITORROWS*")
                  if f.get("status", row) == Symbol("INTERRUPTED")]
        self.assertEqual([f.get("stage", row) for row in failed],
                         ["ROOT_SCOPE_DISCOVERY", "ROOT_SCOPE_BLOCK_INDEX"])


if __name__ == "__main__":
    unittest.main()
