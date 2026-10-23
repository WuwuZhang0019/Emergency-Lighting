"""Date: 2026-10-21. Status: bounded all-fallback compatibility regression.

Frozen c01ea3e comparisons use finite adapters, not native CAD timing evidence.
"""
import unittest
from autolisp_host import Symbol, truth
from check_store_read_work import exact
import test_root_scope_recognition as rooted
import test_root_scope_freshness as fresh


class RootScopeFallbackBypassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rooted.RootScopeRecognitionTests.setUpClass()

    def helper(self):
        return rooted.RootScopeRecognitionTests()

    def reject(self, f, reason="unsupported-plane", error=None):
        def rejected(entity, data, cfg):
            f.h.set(Symbol("*EL:ROOTSCOPEFALLBACKREASON*"), reason)
            f.h.set(Symbol("*EL:ROOTSCOPEFALLBACKERROR*"), error)
            return None
        f.h.builtins["EL:ROOTSCOPEWIRE"] = rejected

    def forbid(self, f):
        def forbidden(*args):
            self.fail("all fallback must skip discovery and candidate ordering")
        f.h.builtins["EL:ROOTSCOPEDISCOVER"] = forbidden
        f.h.builtins["EL:ROOTSCOPEORDER"] = forbidden

    def metric(self, f, key):
        return f.call("EL:Get", key, f.h.lookup(Symbol("*EL:PERFMETRICS*")))

    def test_all_fallback_preserves_frozen_snapshot_numbers_preview_and_source_facts(self):
        helper = self.helper()
        def build(f):
            helper.four_roots(f, remote=12)
            self.reject(f)
            self.forbid(f)
            f.events = []
            f.h.builtins["EL:LOGEVENT"] = lambda *args: f.events.append(args)
            f.call("EL:PerfStart", "ELSTAT")
        old, new = helper.compare(build)
        f, snapshot, _, result, _, counts, _ = new
        for key in ("wires", "ends", "blocks", "issues"):
            self.assertEqual(exact(f.get(key, snapshot)), exact(old[0].get(key, old[1])), key)
        self.assertEqual(counts["wire_records"], 16)
        self.assertEqual([f.get("circuit-number", row) for row in f.get("circuits", result)],
                         ["ZE1", "ZE2", "ZE3", "ZE4"])
        facts = f.get("source-selection-facts", snapshot)
        self.assertEqual([f.call("CDR", f.call("ASSOC", 5, fact[0])) for fact in facts], f.selected)
        self.assertEqual(f.get("source-wire-ids", snapshot),
                         list(reversed([handle for handle in f.selected if "wire" in handle or "root" in handle])))
        for key, expected in (("proxy-wires", 0), ("wire-fallbacks", 16), ("fine-wires", 16),
                              ("skipped-wires", 0), ("all-fallback-bypass", 1)):
            self.assertEqual(self.metric(f, "root-scope-" + key), expected, key)
        bypass = [detail for stage, detail in f.events if stage == "ROOT_SCOPE_BYPASSED"]
        self.assertEqual(len(bypass), 1)
        self.assertEqual(f.get("reason", bypass[0]), Symbol("ALL-WIRE-FALLBACKS"))
        for key in ("REASON", "ERROR"):
            self.assertIsNone(f.h.lookup(Symbol("*EL:ROOTSCOPEFALLBACK" + key + "*")))

    def test_reasons_accumulate_performance_session_and_samples_remain_bounded(self):
        helper = self.helper()
        f = helper.fixture()
        helper.four_roots(f, remote=12)
        reasons = ["exception", "unsupported-plane", "closed-polyline", "invalid-width"]
        rejected_handles = []
        def rejected(entity, data, cfg):
            reason = reasons[len(rejected_handles) % len(reasons)]
            rejected_handles.append(entity)
            f.h.set(Symbol("*EL:ROOTSCOPEFALLBACKREASON*"), reason)
            f.h.set(Symbol("*EL:ROOTSCOPEFALLBACKERROR*"), "bad function: LENGTH" if reason == "exception" else None)
            return None
        f.h.builtins["EL:ROOTSCOPEWIRE"] = rejected
        self.forbid(f)
        events = []
        f.h.builtins["EL:LOGEVENT"] = lambda *args: events.append(args)
        f.call("EL:PerfStart", "ELSTAT")
        for _ in range(2):
            f.call("EL:SimpleCollect", f.cfg)
        summaries = [detail for stage, detail in events if stage == "ROOT_SCOPE_FALLBACKS"]
        self.assertEqual(len(summaries), 2, "one event per batch, no per-wire events")
        for summary in summaries:
            self.assertEqual(f.get("fallback-wires", summary), 16)
            self.assertEqual({row.car: row.cdr for row in f.get("reasons", summary)},
                             {reason: 4 for reason in reasons})
            samples = f.get("samples", summary)
            self.assertEqual(len(samples), 3)
            self.assertEqual(len({f.get("reason", sample) for sample in samples}), 3)
            self.assertEqual(f.get("error", samples[0]), "bad function: LENGTH")
        self.assertEqual(self.metric(f, "root-scope-wire-fallbacks"), 32)
        self.assertEqual({row.car: row.cdr for row in self.metric(f, "root-scope-fallback-reasons")},
                         {reason: 8 for reason in reasons})
        self.assertEqual(self.metric(f, "root-scope-all-fallback-bypass"), 2)

    def test_mixed_fallback_still_discovers_and_orders_dependencies(self):
        helper = self.helper()
        def build(f):
            helper.four_roots(f, remote=2)
            original = f.h.call
            f.root_calls = []
            def observe(name, args):
                if name == Symbol("EL:ROOTSCOPEWIRE") and args[0] == "remote-wire-0":
                    f.h.set(Symbol("*EL:ROOTSCOPEFALLBACKREASON*"), "unsupported-plane")
                    f.h.set(Symbol("*EL:ROOTSCOPEFALLBACKERROR*"), None)
                    return None
                if name in (Symbol("EL:ROOTSCOPEDISCOVER"), Symbol("EL:ROOTSCOPEORDER")):
                    f.root_calls.append(name)
                return original(name, args)
            f.h.call = observe
            f.call("EL:PerfStart", "ELSTAT")
        _, new = helper.compare(build)
        f = new[0]
        self.assertEqual(f.root_calls, [Symbol("EL:ROOTSCOPEDISCOVER"), Symbol("EL:ROOTSCOPEORDER")])
        self.assertEqual(self.metric(f, "root-scope-proxy-wires"), 5)
        self.assertEqual(self.metric(f, "root-scope-wire-fallbacks"), 1)
        self.assertEqual(self.metric(f, "root-scope-all-fallback-bypass"), 0)
        self.assertIn("remote-wire-0", new[6]["wire"])

    def test_all_fallback_keeps_remote_fact_invalidation(self):
        helper = self.helper()
        def build(f):
            helper.four_roots(f, remote=1)
            self.reject(f)
            self.forbid(f)
        f, _, _, result, *_ = helper.run_case(build)
        self.assertTrue(truth(f.call("EL:FreshResult", result, f.cfg)))
        f.line("remote-wire-0", [100000., 100000., 0.], [100008., 100000., 0.], "W")
        f.call("EL:FreshBoundary")
        self.assertFalse(truth(f.call("EL:FreshResult", result, f.cfg)))

    def test_all_fallback_keeps_owner_and_epoch_guard(self):
        for change in ("owner", "epoch"):
            with self.subTest(change=change):
                helper = fresh.RootScopeFreshnessTests()
                helper.setUp()
                self.reject(helper.f.f)
                self.forbid(helper.f.f)
                original = helper.h.builtins["EL:ENTITYBOUNDS"]
                fired = []
                def mutate(entity):
                    if not fired:
                        fired.append(entity)
                        if change == "epoch":
                            helper.call("EL:FreshBoundary")
                        else:
                            helper.h.builtins["NAMEDOBJDICT"] = lambda: "other-drawing"
                    return original(entity)
                helper.h.builtins["EL:ENTITYBOUNDS"] = mutate
                helper.h.builtins["EXIT"] = lambda: (_ for _ in ()).throw(RuntimeError("quit / exit abort"))
                with self.assertRaisesRegex(RuntimeError, "quit / exit abort"):
                    helper.call("EL:SimpleCollect", helper.cfg)
                self.assertTrue(any(stage == "VALIDATION_FAILED" and
                    "SOURCE_CHANGED" in helper.get("message", detail) for stage, detail in helper.events))
                for key in ("*EL:COLLECTMEMO*", "*EL:NETWORKMEMO*"):
                    self.assertIsNone(helper.h.lookup(Symbol(key)))

    def test_empty_selection_does_not_count_as_all_fallback(self):
        helper = self.helper()
        f = helper.fixture()
        helper.base(f)
        f.selected = ["panel", "lamp"]
        self.forbid(f)
        events = []
        f.h.builtins["EL:LOGEVENT"] = lambda *args: events.append(args)
        f.call("EL:PerfStart", "ELSTAT")
        snapshot = f.call("EL:SimpleCollect", f.cfg)
        self.assertIsNone(f.get("wires", snapshot))
        self.assertEqual(self.metric(f, "root-scope-all-fallback-bypass"), 0)
        self.assertEqual(self.metric(f, "root-scope-proxy-wires"), 0)
        self.assertFalse([detail for stage, detail in events if stage == "ROOT_SCOPE_FALLBACKS"])
        bypass = [detail for stage, detail in events if stage == "ROOT_SCOPE_BYPASSED"]
        self.assertEqual(f.get("reason", bypass[0]), Symbol("NO-SOURCE-WIRES"))


if __name__ == "__main__":
    unittest.main()
