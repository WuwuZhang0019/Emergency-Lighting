"""Date: 2026-10-21. Status: focused proxy envelope and fallback checks.

The frozen c01ea3e wire reader is the geometry oracle. These checks prove
containment and endpoint equivalence, not native CAD timing or acceptance.
"""
import copy
import math
import random
import subprocess
import unittest
from pathlib import Path

from autolisp_host import Host, Pair, Symbol, car, cdr, parse, seq

ROOT = Path(__file__).resolve().parents[1]
FROZEN = "c01ea3e"


def field(name, record):
    return next((cdr(row) for row in seq(record)
                 if car(row) == Symbol(name.upper())), None)


class StrictSymbolBindingHost(Host):
    """Exercise native local symbol shadowing without changing the shared host."""
    def call(self, name, values):
        if isinstance(name, Symbol):
            for frame in reversed(self.frames[1:]):
                if name in frame:
                    raise RuntimeError(f"bad function: local {name} = {frame[name]!r}")
        return super().call(name, values)


class RootScopeGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = subprocess.check_output(
            ["git", "show", FROZEN + ":src/geometry.lsp"], cwd=ROOT).decode("utf-8")
        cls.frozen = next(form for form in parse(source)
                          if isinstance(form, list) and len(form) > 1
                          and form[:1] == [Symbol("DEFUN")]
                          and form[1] == Symbol("EL:WIRERECORDDXF"))
        cls.frozen = copy.deepcopy(cls.frozen)
        cls.frozen[1] = Symbol("ORACLE:WIRERECORDDXF")

    def setUp(self):
        self.h = Host()
        self.h.step_limit = 3000000
        for name in ("common", "config", "geometry"):
            self.h.load_definitions(ROOT / "src" / (name + ".lsp"))
        self.h.evaluate(self.frozen)
        self.events = []
        self.h.builtins["EL:LOGEVENT"] = lambda *args: self.events.append(copy.deepcopy(args))
        self.h.builtins["TRANS"] = lambda point, *args: point
        self.h.builtins["MIN"] = lambda *values: min(values)
        self.h.builtins["MAX"] = lambda *values: max(values)
        self.cfg = self.h.run("""(EL:Put 'params (EL:SuggestedParams) (EL:DefaultConfig "test.dwg"))""")

    def call(self, name, *args):
        self.h.steps = 0
        return self.h.call(Symbol(name.upper()), list(args))

    def line(self, start=(0., 0., 0.), end=(10., 0., 0.)):
        return [Pair(0, "LINE"), Pair(5, "wire"), Pair(8, "W"),
                Pair(10, list(start)), Pair(11, list(end)), Pair(410, "Model")]

    def polyline(self, points, bulges=None, widths=None, constant=0., elevation=0.):
        data = [Pair(0, "LWPOLYLINE"), Pair(5, "wire"), Pair(8, "W"),
                Pair(70, 0), Pair(38, elevation), Pair(43, constant),
                Pair(210, [0., 0., 1.]), Pair(410, "Model")]
        for index, point in enumerate(points):
            data.append(Pair(10, list(point)))
            if bulges is not None:
                data.append(Pair(42, bulges[index]))
            if widths is not None:
                data.extend([Pair(40, widths[index][0]), Pair(41, widths[index][1])])
        return data

    def assert_hint(self, data):
        before = copy.deepcopy(data)
        proxy = self.call("EL:RootScopeWire", "native-wire", data, self.cfg)
        self.assertIsNotNone(proxy)
        oracle = self.call("ORACLE:WireRecordDXF", "native-wire", data, self.cfg)
        self.assertIsNone(field("issues", oracle))
        self.assertEqual(field("ends", proxy), field("ends", oracle))
        self.assertEqual(field("id", proxy), field("id", oracle))
        self.assertEqual(field("layer", proxy), field("layer", oracle))
        self.assertEqual(field("type", proxy), field("type", oracle))
        self.assertEqual(field("entity", proxy), "native-wire")
        self.assertEqual(field("deferred-dxf", proxy), before)
        self.assertIsNone(field("segments", proxy))
        self.assertIsNone(field("contact-strips", proxy))
        outer = field("contact-bounds", proxy)
        inner = field("contact-bounds", oracle)
        if field("candidate-bounds", proxy) is not None:
            self.assertEqual(field("candidate-bounds", proxy), inner)
        for axis in range(3):
            self.assertLessEqual(outer[0][axis], inner[0][axis])
            self.assertGreaterEqual(outer[1][axis], inner[1][axis])
        self.assertEqual(data, before)
        return proxy, oracle

    def test_line_endpoints_and_complete_frozen_bounds_without_native_bounds(self):
        for start, end in (((0., 0., 0.), (10., 0., 0.)),
                           ((12., -80., 4.), (-30., 2., 4.)),
                           ((1.e9, 1.e9, 0.), (1.e9 + 100., 1.e9 + 300., 0.))):
            with self.subTest(start=start, end=end):
                self.assert_hint(self.line(start, end))

    def test_straight_polyline_and_repeated_vertices_keep_exact_ends(self):
        for points in (((0., 0.), (5., 0.), (5., 8.)),
                       ((0., 0.), (0., 0.), (8., 0.), (8., 0.)),
                       ((0., 0.), (2.e-10, 0.), (10., 0.))):
            with self.subTest(points=points):
                self.assert_hint(self.polyline(points, elevation=7.))

    def test_minor_major_and_reversed_arcs_enclose_old_sampled_centerlines(self):
        for bulge in (.1, -.1, 1., -1., 2.5, -2.5):
            with self.subTest(bulge=bulge):
                self.assert_hint(self.polyline(((0., 0.), (10., 0.), (20., 6.)),
                                               [bulge, 0., 0.]))

    def test_constant_variable_and_overlapping_width_profiles_are_contained(self):
        self.assert_hint(self.polyline(((0., 0.), (10., 0.), (10., 20.)), constant=4.))
        self.assert_hint(self.polyline(((0., 0.), (10., 0.), (0., 0.), (10., 0.)),
                                      widths=((2., 6.), (10., 2.), (1., 40.), (0., 0.))))
        self.assert_hint(self.polyline(((0., 0.), (10., 0.), (20., 0.)),
                                      [.5, 0., 0.], constant=8.))

    def test_tiny_overlapping_profile_extrapolation_is_covered(self):
        # The old profile predicate accepts up to epsilon past a short profile.
        # Its interpolated strip can be much wider than max(source width)/2.
        data = self.polyline(((0., 0.), (2.e-9, 0.), (8.e-8, 0.), (10., 0.)),
                             widths=((0., 10.), (0., 0.), (0., 0.), (0., 0.)))
        proxy, oracle = self.assert_hint(data)
        self.assertGreater(abs(field("contact-bounds", oracle)[0][1]), 5.)
        self.assertGreater(abs(field("contact-bounds", proxy)[0][1]), 5.)

    def test_seeded_mixed_curves_and_widths_fit_frozen_bounds(self):
        rng = random.Random(20261021)
        for index in range(24):
            points = [(rng.uniform(-200., 200.), rng.uniform(-200., 200.)) for _ in range(5)]
            bulges = [rng.choice((0., 0., .2, -.7, 1.5)) for _ in points]
            widths = [(rng.uniform(0., 10.), rng.uniform(0., 10.)) for _ in points]
            with self.subTest(index=index):
                self.assert_hint(self.polyline(points, bulges, widths, elevation=3.))

    def test_proxy_has_no_sampling_strip_native_bound_or_vertex_diagnostics(self):
        def forbidden(*args):
            self.fail("precision/native geometry called while making a proxy")
        for name in ("EL:POLYLINEDATADXF", "EL:POLYLINESEGMENTS", "EL:WIRERECORDDXF",
                     "EL:WIRECONTACTSTRIPS", "EL:ENTITYBOUNDS", "EL:ARCPOINTS", "TRANS", "ENTGET"):
            self.h.builtins[name] = forbidden
        data = self.polyline(((0., 0.), (10., 0.), (20., 4.)), [.5, 0., 0.], constant=4.)
        self.assertIsNotNone(self.call("EL:RootScopeWire", "wire", data, self.cfg))
        self.assertEqual(self.events, [])

    def test_unsupported_plane_closed_invalid_and_unsampleable_records_fall_back(self):
        base = self.polyline(((0., 0.), (10., 0.)))
        cases = [self.line((0., 0., 0.), (0., 0., 0.)),
                 self.polyline(((0., 0.),)),
                 self.polyline(((0., 0.), (1.e30, 0.)), [.5, 0.]),
                 self.polyline(((0., 0.), (10., 0.)), widths=((-1., 2.), (0., 0.))),
                 self.polyline(((0., 0.), (10., 0.)), [float("nan"), 0.]),
                 self.line((0., 0., 0.), (10., 0., 20.))]
        for code, value in ((70, 1), (210, [0., 0., -1.]), (210, [0., .1, 1.]),
                            (38, "bad"), (43, "bad"), (10, [0., "bad"])):
            cases.append([Pair(code, value) if car(row) == code else row for row in base])
        for index, data in enumerate(cases):
            with self.subTest(index=index):
                self.assertIsNone(self.call("EL:RootScopeWire", "wire", data, self.cfg))
        self.assertEqual(self.events, [])


    def strict_host(self):
        strict = StrictSymbolBindingHost(step_limit=3000000)
        strict.functions = copy.deepcopy(self.h.functions)
        for name in ("EL:LOGEVENT", "TRANS", "MIN", "MAX"):
            strict.builtins[name] = self.h.builtins[name]
        self.h = strict

    def test_strict_local_symbol_binding_preserves_line_and_polyline_proxies(self):
        self.strict_host()
        for data in (self.line(), self.polyline(((0., 0.), (10., 0.), (10., 8.))),
                     self.polyline(((0., 0.), (10., 0.)), [.5, 0.], constant=4.)):
            with self.subTest(kind=cdr(data[0])):
                self.assert_hint(data)
                self.assertIsNone(self.h.lookup(Symbol("*EL:ROOTSCOPEFALLBACKREASON*")))
                self.assertIsNone(self.h.lookup(Symbol("*EL:ROOTSCOPEFALLBACKERROR*")))

    def test_legacy_length_collision_is_caught_and_next_success_clears_diagnostics(self):
        self.strict_host()
        name = Symbol("EL:ROOTSCOPEWIREBOUNDS")
        fixed = copy.deepcopy(self.h.functions[name])

        def legacy(value):
            if value == Symbol("CHORD-LENGTH"):
                return Symbol("LENGTH")
            if isinstance(value, list):
                return [legacy(item) for item in value]
            return value

        self.h.functions[name] = tuple(legacy(part) for part in fixed)
        self.assertIsNone(self.call("EL:RootScopeWire", "wire", self.line(), self.cfg))
        self.assertEqual(self.h.lookup(Symbol("*EL:ROOTSCOPEFALLBACKREASON*")), "exception")
        self.assertIn("local LENGTH", self.h.lookup(Symbol("*EL:ROOTSCOPEFALLBACKERROR*")))
        self.assertEqual(self.events, [])
        self.h.functions[name] = fixed
        self.assert_hint(self.line())
        self.assertIsNone(self.h.lookup(Symbol("*EL:ROOTSCOPEFALLBACKREASON*")))
        self.assertIsNone(self.h.lookup(Symbol("*EL:ROOTSCOPEFALLBACKERROR*")))

    def test_fallback_reasons_are_specific_without_per_wire_logging(self):
        base = self.polyline(((0., 0.), (10., 0.)))

        def changed(code, value):
            return [Pair(code, value) if car(row) == code else row for row in base]

        cases = [("identity", [row for row in base if car(row) != 5]),
                 ("unsupported-plane", changed(210, [0., 0., -1.])),
                 ("unsupported-type", changed(0, "ARC")),
                 ("invalid-line", self.line((0., 0., 0.), (10., 0., 20.))),
                 ("invalid-polyline-metadata", changed(38, "bad")),
                 ("closed-polyline", changed(70, 1)),
                 ("invalid-vertex", changed(10, [0., "bad"])),
                 ("invalid-bulge", self.polyline(((0., 0.), (10., 0.)), ["bad", 0.])),
                 ("invalid-width", changed(43, -1.)),
                 ("envelope-unproven", self.line((0., 0., 0.), (0., 0., 0.)))]
        for reason, data in cases:
            with self.subTest(reason=reason):
                self.assertIsNone(self.call("EL:RootScopeWire", "wire", data, self.cfg))
                self.assertEqual(self.h.lookup(Symbol("*EL:ROOTSCOPEFALLBACKREASON*")), reason)
                self.assertIsNone(self.h.lookup(Symbol("*EL:ROOTSCOPEFALLBACKERROR*")))
        self.assertEqual(self.events, [])

    def test_proxy_is_current_per_call_and_never_keeps_a_previous_dxf(self):
        first = self.line()
        second = self.line(end=(1000., 0., 0.))
        a = self.call("EL:RootScopeWire", "same-wire", first, self.cfg)
        b = self.call("EL:RootScopeWire", "same-wire", second, self.cfg)
        self.assertNotEqual(field("ends", a), field("ends", b))
        self.assertEqual(field("deferred-dxf", a), first)
        self.assertEqual(field("deferred-dxf", b), second)
        self.assertGreater(field("contact-bounds", b)[1][0], 1000.)


if __name__ == "__main__":
    unittest.main()
