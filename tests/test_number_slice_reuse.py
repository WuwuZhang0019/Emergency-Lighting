"""Date: 2026-10-21. Status: frozen v0.1.73 numbering-prefix equivalence.

Bounded-host operation counts are evidence of reused work, not native CAD time.
"""
from collections import Counter
import copy
from functools import lru_cache
import math
import subprocess
import unittest

from autolisp_host import Pair, Symbol, parse
from check_store_read_work import exact
import test_number_prefix_bounds as fixture

ROOT = fixture.ROOT
BASELINE = "9c0a448"


@lru_cache(maxsize=1)
def baseline_forms():
    source = subprocess.check_output(["git", "show", f"{BASELINE}:src/circuit-number.lsp"], cwd=ROOT)
    return [form for form in parse(source.decode("utf-8"))
            if isinstance(form, list) and form[0] == "DEFUN"]


def pair(key, value):
    return Pair(Symbol(key.upper()), value)


class NumberSliceReuseTests(unittest.TestCase):
    def make(self, baseline=False):
        f = fixture.NumberPrefixBoundsTests()
        f.setUp()
        # Remove fixture closures bound to the current definitions before loading
        # the entire frozen module. Both hosts then use their own actual module.
        for name in ("EL:NUMBERPATHSLICEMEASURED", "EL:NUMBERSHAPEHITSTRICT",
                     "EL:NUMBERPREFIXBOUNDS", "EL:NUMBERNATIVEBOUNDSXY"):
            f.h.builtins.pop(name, None)
        if baseline:
            for form in baseline_forms():
                f.h.evaluate(form)
        f.h.step_limit = 100_000_000
        return f

    @staticmethod
    def wire(points, widths=None):
        segments = [[a, b] for a, b in zip(points, points[1:])]
        rows = [pair("segments", segments)]
        if widths:
            rows.append(pair("width-profiles", [[a, b, *widths] for a, b in segments]))
        return rows

    def observe(self, f, wire, entry, target, devices, profile=True):
        h = f.h
        h.frames[0]["*EL:PERFACTIVE*"] = profile
        h.builtins["EL:TICK"] = lambda: self.fail("Numbering reuse adds no clocks")
        operations, slices, exact_inputs = Counter(), [], []
        wide_cache_sizes = []
        original = h.call
        def observe(name, values):
            if isinstance(name, str):
                operations[name] += 1
                if name == "EL:NUMBERSHAPEHITSTRICT":
                    exact_inputs.append(exact(copy.deepcopy(values)))
            result = original(name, values)
            if name == "EL:NUMBERPATHSLICEMEASURED":
                slices.append((exact(copy.deepcopy(values)), exact(result)))
            if name == "EL:NUMBERPROBEWIDEPATHHIT":
                wide_cache_sizes.append(len(h.lookup("*EL:NUMBERPROBEWIDEHITS*") or []))
            return result
        h.call = observe
        f.counts.clear()
        f.shape_reads.clear()
        before = exact(copy.deepcopy((wire, devices, f.cfg)))
        try:
            result = f.call("EL:NumberFirstDevice", wire, entry, target, devices, f.cfg)
        finally:
            h.call = original
        self.assertEqual(exact((wire, devices, f.cfg)), before)
        for key in ("*EL:NUMBERPROBEACTIVE*", "*EL:NUMBERSLICEREUSEACTIVE*",
                    "*EL:NUMBERPROBEWHOLESEGMENTS*", "*EL:NUMBERPROBESTRIPS*",
                    "*EL:NUMBERPROBEFIXEDSTRIPS*", "*EL:NUMBERPROBEWIDEHITS*", "*EL:NUMBERSLICEMEASURES*"):
            self.assertIsNone(h.lookup(key), key)
        return dict(result=exact(result), slices=slices, exact_inputs=exact_inputs,
                    reads=f.shape_reads[:], operations=operations,
                    counts=dict(f.counts), steps=h.steps, max_wide_cache=max(wide_cache_sizes, default=0))

    def compare(self, make_case, entry, target, profile=True):
        old, new = self.make(True), self.make()
        old_wire, old_devices = make_case(old)
        wire, devices = make_case(new)
        expected = self.observe(old, old_wire, entry, target, old_devices, profile)
        actual = self.observe(new, wire, entry, target, devices, profile)
        for key in ("result", "slices", "exact_inputs", "reads"):
            self.assertEqual(actual[key], expected[key], key)
        for key, value in expected["counts"].items():
            self.assertEqual(actual["counts"][key], value, key)
        return expected, actual

    def test_frozen_all_prefixes_forward_reverse_ties_holes_and_partial_entry(self):
        def make(f):
            points = [[x, 0., 0.] for x in (0., 4., 8., 12., 16., 20.)]
            near = f.device("near", [[9., -1., 0.], [10., 1., 0.]])
            tie = f.device("tie", [[9., -1., 0.], [10., 1., 0.]])
            far = f.device("far", [[17., -1., 0.], [18., 1., 0.]])
            hole = f.device("hole", [[2., -2., 0.], [19., 2., 0.]],
                            [[3., -1., 0.], [18.5, 1., 0.]])
            return self.wire(points), [far, near, tie, hole]
        for entry, target in ((0., 20.), (20., 0.), (7., 20.), (13., 0.)):
            with self.subTest(entry=entry, target=target):
                old, new = self.compare(make, entry, target)
                self.assertEqual(len(new["slices"]), 33)
                self.assertGreater(new["counts"]["number-prefix-full-segment-reuses"], 0)
                self.assertEqual(new["counts"]["number-prefix-strip-builds"], 0)
                self.assertEqual(new["counts"]["number-prefix-strip-reuses"], 0)

    def test_wide_original_carriers_taper_overlap_and_reverse_keep_exact_strips(self):
        for widths in ((50., 50.), (20., 80.), (80., 20.)):
            def make(f):
                points = [[x, 0., 0.] for x in (0., 40., 80., 120.)]
                wire = self.wire(points, widths)
                # Duplicate and overlapping carriers retain profile order and
                # original distance-based projection on the uncut carrier.
                profiles = f.get("width-profiles", wire)
                profiles.append([[0., 0., 0.], [120., 0., 0.], 8., 16.])
                device = f.device("device", [[95., 3., 0.], [96., 5., 0.]])
                return wire, [device]
            for entry, target in ((0., 120.), (120., 0.), (35., 120.), (85., 0.)):
                with self.subTest(widths=widths, entry=entry, target=target):
                    self.compare(make, entry, target)

    def test_sampled_curves_native_circle_large_coordinates_and_zero_segments(self):
        for offset in (0., 154776.123456789, 1.e9):
            def make(f):
                points = [[offset + 5.*math.cos(i*math.pi/12),
                           5.*math.sin(i*math.pi/12), 0.] for i in range(7)]
                points.insert(1, points[0][:])
                device = f.circle("circle", offset+3.5, 3.5, 0.8)
                return self.wire(points), [device]
            probe = self.make()
            wire, _ = make(probe)
            length = probe.call("EL:NumberPathLength", wire)
            for entry, target in ((0., length), (length, 0.)):
                with self.subTest(offset=offset, entry=entry):
                    self.compare(make, entry, target)

    def test_width_profile_nil_miss_is_reused_but_does_not_cross_search(self):
        def make(f):
            wire = self.wire([[x, 0., 0.] for x in (0., 10., 20., 30.)])
            wire.append(pair("width-profiles", [[[0., 100., 0.], [30., 100., 0.], 50., 50.]]))
            return wire, [f.device("device", [[24., -1., 0.], [25., 1., 0.]])]
        old, new = self.compare(make, 0., 30.)
        self.assertGreater(new["counts"]["number-prefix-strip-reuses"], 20)
        self.assertLess(new["operations"]["EL:WIRECONTACTSTRIPS"],
                        old["operations"]["EL:WIRECONTACTSTRIPS"] + 3)
        f = self.make()
        wire, devices = make(f)
        self.observe(f, wire, 0., 30., devices)
        wire = f.call("EL:Put", Symbol("WIDTH-PROFILES"),
                      [[[0., 0., 0.], [30., 0., 0.], 50., 50.]], wire)
        actual = self.observe(f, wire, 0., 30., devices)
        baseline = self.make(True)
        old_wire, old_devices = make(baseline)
        old_wire = baseline.call("EL:Put", Symbol("WIDTH-PROFILES"),
                                [[[0., 0., 0.], [30., 0., 0.], 50., 50.]], old_wire)
        expected = self.observe(baseline, old_wire, 0., 30., old_devices)
        self.assertEqual(actual["slices"], expected["slices"])

    def test_single_segment_and_plain_slice_do_not_enable_caches(self):
        def make(f):
            return self.wire([[0., 0., 0.], [100., 0., 0.]], (50., 50.)), [
                f.device("one", [[70., 4., 0.], [72., 5., 0.]])]
        old, new = self.compare(make, 0., 100.)
        for key in ("number-prefix-full-segment-builds", "number-prefix-full-segment-reuses",
                    "number-prefix-strip-builds", "number-prefix-strip-reuses",
                    "number-prefix-wide-builds", "number-prefix-wide-reuses"):
            self.assertEqual(new["counts"][key], 0)
        self.assertEqual(new["operations"]["EL:V+"], old["operations"]["EL:V+"])
        f = self.make()
        wire, _ = make(f)
        f.h.frames[0]["*EL:NUMBERPROBEACTIVE*"] = True
        f.h.builtins["EL:NUMBERSLICECONTACTSTRIPS"] = lambda *args: self.fail("Plain slice must use old path")
        f.call("EL:NumberPathSlice", wire, 0., 25.)
        self.assertIsNone(f.h.lookup("*EL:NUMBERPROBESTRIPS*"))

    def test_two_three_four_segment_single_candidate_reduces_repeated_vector_work(self):
        for segment_count in (2, 3, 4):
            def make(f):
                points = [[float(i*100), 0., 0.] for i in range(segment_count+1)]
                return self.wire(points, (50., 50.)), [
                    f.device("one", [[segment_count*100.-15., 4., 0.], [segment_count*100.-14., 5., 0.]])]
            old, new = self.compare(make, 0., segment_count*100.)
            self.assertEqual(len(new["slices"]), 33)
            self.assertEqual(len(new["exact_inputs"]), 33)
            self.assertLess(new["operations"]["EL:V+"], old["operations"]["EL:V+"])
            self.assertLess(new["operations"]["EL:NORM"], old["operations"]["EL:NORM"])
            self.assertGreater(new["counts"]["number-prefix-strip-reuses"], 20)
            self.assertGreater(new["counts"]["number-prefix-wide-reuses"], 20)
            self.assertLess(new["operations"]["EL:CONTOURPATHHIT"], old["operations"]["EL:CONTOURPATHHIT"])
            self.assertLessEqual(new["max_wide_cache"], segment_count)

    def test_disabled_profile_keeps_result_without_metrics_or_clocks(self):
        def make(f):
            return self.wire([[0., 0., 0.], [10., 0., 0.], [20., 0., 0.]], (6., 6.)), [
                f.device("one", [[17., 1., 0.], [18., 2., 0.]])]
        old, new = self.compare(make, 0., 20., profile=False)
        self.assertEqual(new["counts"], {})

    def test_nested_search_and_shape_failure_unwind_local_cache(self):
        f = self.make()
        wire = self.wire([[0., 0., 0.], [10., 0., 0.], [20., 0., 0.]], (6., 6.))
        device = f.device("outer", [[17., 1., 0.], [18., 2., 0.]])
        nested_device = f.device("inner", [[3., 0., 0.], [4., 1., 0.]])
        original = f.h.builtins["EL:DEVICECONTACTSHAPE"]
        entered = []
        other_wire = self.wire([[100., 4., 0.], [110., 4., 0.], [120., 4., 0.]], (20., 20.))
        baseline = self.make(True)
        expected_plain = baseline.call("EL:NumberPathSlice", other_wire, 0., 15.)
        def nested(block):
            if f.get("id", block) == "outer" and not entered:
                entered.append(True)
                outer_cache = f.h.lookup("*EL:NUMBERPROBEWHOLESEGMENTS*")
                outer_measures = f.h.lookup("*EL:NUMBERSLICEMEASURES*")
                # A regular slice called under the dynamic scope must not
                # pair another wire with this search's parallel cached rows.
                actual_plain = f.call("EL:NumberPathSlice", other_wire, 0., 15.)
                self.assertEqual(exact(actual_plain), exact(expected_plain))
                self.assertIs(f.h.lookup("*EL:NUMBERSLICEMEASURES*"), outer_measures)
                f.call("EL:NumberFirstDevice", self.wire([[0., 0., 0.], [5., 0., 0.]]),
                       0., 5., [nested_device], f.cfg)
                self.assertIs(f.h.lookup("*EL:NUMBERPROBEWHOLESEGMENTS*"), outer_cache)
            return original(block)
        f.h.builtins["EL:DEVICECONTACTSHAPE"] = nested
        result = f.call("EL:NumberFirstDevice", wire, 0., 20., [device], f.cfg)
        self.assertIsNotNone(result)
        self.assertEqual(entered, [True])
        def fail(block):
            raise RuntimeError("native shape read failed")
        f.h.builtins["EL:DEVICECONTACTSHAPE"] = fail
        with self.assertRaisesRegex(RuntimeError, "native shape read failed"):
            f.call("EL:NumberFirstDevice", wire, 0., 20., [device], f.cfg)
        for key in ("*EL:NUMBERSLICEREUSEACTIVE*", "*EL:NUMBERPROBEWHOLESEGMENTS*", "*EL:NUMBERPROBESTRIPS*",
                    "*EL:NUMBERPROBEFIXEDSTRIPS*", "*EL:NUMBERPROBEWIDEHITS*", "*EL:NUMBERSLICEMEASURES*"):
            self.assertIsNone(f.h.lookup(key))


    def test_wide_hit_keeps_later_strip_checks_and_caches_nil(self):
        f = self.make()
        first = [pair("id", "first")]
        second = [pair("id", "second")]
        calls = []
        def check(strip, shape, cfg):
            calls.append(f.get("id", strip))
            return f.get("id", strip) == "first"
        f.h.builtins["EL:NUMBERPROBESTRIPSHAPEHIT"] = check
        f.h.run("""(defun test:WideTwice (wire shape cfg / *EL:NumberProbeFixedStrips* *EL:NumberProbeWideHits*)
          (setq *EL:NumberProbeFixedStrips* (EL:Get 'contact-strips wire))
          (list (EL:NumberProbeWidePathHit wire shape cfg) (EL:NumberProbeWidePathHit wire shape cfg)))""")
        actual = f.call("test:WideTwice", [pair("contact-strips", [first, second])], None, f.cfg)
        self.assertEqual(actual, [True, True])
        self.assertEqual(calls, ["first", "second"])
        self.assertIsNone(f.h.lookup("*EL:NUMBERPROBEWIDEHITS*"))

    def test_shape_and_strict_tolerance_changes_start_a_fresh_search(self):
        def make(f):
            return self.wire([[0., 0., 0.], [10., 0., 0.], [20., 0., 0.]], (6., 6.)), [
                f.device("one", [[17., 1., 0.], [18., 2., 0.]])]
        current = self.make()
        wire, devices = make(current)
        self.observe(current, wire, 0., 20., devices)
        # Same native id, changed geometry and a changed strict tolerance must
        # never read either the previous positive or negative strip result.
        devices = [current.device("one", [[16., 3.015, 0.], [17., 3.1, 0.]])]
        params = current.get("params", current.cfg)
        params = current.call("EL:Put", Symbol("EPS_DEVICE"), .02, params)
        current.cfg = current.call("EL:Put", Symbol("PARAMS"), params, current.cfg)
        actual = self.observe(current, wire, 0., 20., devices)
        baseline = self.make(True)
        old_wire, _ = make(baseline)
        old_devices = [baseline.device("one", [[16., 3.015, 0.], [17., 3.1, 0.]])]
        params = baseline.get("params", baseline.cfg)
        params = baseline.call("EL:Put", Symbol("EPS_DEVICE"), .02, params)
        baseline.cfg = baseline.call("EL:Put", Symbol("PARAMS"), params, baseline.cfg)
        expected = self.observe(baseline, old_wire, 0., 20., old_devices)
        for key in ("result", "slices", "exact_inputs", "reads"):
            self.assertEqual(actual[key], expected[key], key)


if __name__ == "__main__":
    unittest.main()
