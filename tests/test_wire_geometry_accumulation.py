"""Date: 2026-10-21. Status: focused equivalence and allocation checks.

Frozen f16fa0c functions prove geometry, ordering and diagnostics equivalence.
Logical operation counts are evidence of reduced work, not native CAD timing.
"""
import copy
import subprocess
import unittest
from pathlib import Path

from autolisp_host import Host, Pair, Symbol, car, cdr, parse, seq

ROOT = Path(__file__).resolve().parents[1]
FROZEN = "f16fa0c"
NAMES = ("EL:POLYLINESEGMENTS", "EL:WIRECONTACTSTRIPS", "EL:WIRECONTACTBOUNDS",
         "EL:PREPAREWIREBOUNDS", "EL:WIRERECORDDXF")


def renamed(value):
    if isinstance(value, Symbol) and value in NAMES:
        return Symbol("ORACLE:" + value[3:])
    if isinstance(value, list):
        return [renamed(item) for item in value]
    if isinstance(value, Pair):
        return Pair(renamed(value.car), renamed(value.cdr))
    return value


def field(name, value):
    return next((cdr(pair) for pair in seq(value)
                 if car(pair) == Symbol(name.upper())), None)


class WireGeometryAccumulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = subprocess.check_output(
            ["git", "show", FROZEN + ":src/geometry.lsp"], cwd=ROOT).decode("utf-8")
        cls.frozen = [renamed(form) for form in parse(source)
                      if isinstance(form, list) and form[:1] == [Symbol("DEFUN")]
                      and form[1] in NAMES]
        assert len(cls.frozen) == len(NAMES)

    def setUp(self):
        self.h = Host()
        for name in ("common", "config", "geometry"):
            self.h.load_definitions(ROOT / "src" / (name + ".lsp"))
        for form in self.frozen:
            self.h.evaluate(form)
        self.events = []
        self.h.builtins["EL:LOGEVENT"] = lambda *args: self.events.append(copy.deepcopy(args))
        self.h.builtins["TRANS"] = lambda point, *args: point
        # Native MIN/MAX accept one numeric argument; Python min/max do not.
        self.h.builtins["MIN"] = lambda *values: min(values)
        self.h.builtins["MAX"] = lambda *values: max(values)
        self.cfg = self.h.run("(EL:Put 'params (EL:SuggestedParams) (EL:DefaultConfig \"test.dwg\"))")

    def call(self, name, *args):
        self.h.steps = 0
        return self.h.call(Symbol(name.upper()), list(args))

    def compare(self, suffix, *args):
        before = copy.deepcopy(args)
        self.events.clear()
        expected = self.call("ORACLE:" + suffix, *args)
        logs = copy.deepcopy(self.events)
        self.events.clear()
        actual = self.call("EL:" + suffix, *args)
        self.assertEqual(actual, expected)
        self.assertEqual(self.events, logs)
        self.assertEqual(args, before)
        return actual

    def polyline(self, points, bulges=None, closed=0, widths=None, constant=4.):
        data = [Pair(0, "LWPOLYLINE"), Pair(5, "wire"), Pair(8, "W"),
                Pair(70, closed), Pair(38, points[0][2] if points else 0.),
                Pair(43, constant), Pair(210, [0., 0., 1.]), Pair(410, "Model")]
        for index, point in enumerate(points):
            data.append(Pair(10, point[:2]))
            if bulges is not None:
                data.append(Pair(42, bulges[index]))
            if widths is not None:
                data.extend([Pair(40, widths[index][0]), Pair(41, widths[index][1])])
        return data

    def test_sampled_segments_keep_straight_arc_closed_short_and_zero_order(self):
        cases = [(None, None, None), ([[0., 0., 0.]], None, None),
                 ([[0., 0., 0.], [10., 0., 0.], [10., 10., 0.]], [0., 0., 0.], None),
                 ([[0., 0., 0.], [10., 0., 0.], [20., 0., 0.]], [.5, -.5, 0.], None),
                 ([[0., 0., 0.], [10., 0., 0.], [10., 10., 0.]], [0., .5, -.3], True),
                 ([[0., 0., 0.], [0., 0., 0.], [1.e-10, 0., 0.]], None, None)]
        for points, bulges, closed in cases:
            with self.subTest(points=points, bulges=bulges, closed=closed):
                self.compare("PolylineSegments", points, bulges, closed, .01)

    def test_sampling_failure_discards_all_prior_pieces_and_stops_later_logging(self):
        points = [[float(index), 0., 0.] for index in range(5)]
        visits = []
        def sample(a, b, bulge, error):
            visits.append((a, b))
            return None if a[0] == 1. else [a, b]
        self.h.builtins["EL:BULGEPOINTS"] = sample
        self.assertIsNone(self.compare("PolylineSegments", points, None, None, .01))
        self.assertEqual([pair[0][0] for pair in visits], [0., 1., 0., 1.])
        self.assertEqual(len(self.events), 2)

    def test_overlapping_and_reversed_width_profiles_keep_every_strip_and_predicate_order(self):
        segments = [[[0., 0., 0.], [5., 0., 0.]], [[5., 0., 0.], [10., 0., 0.]],
                    [[10., 0., 0.], [5., 0., 0.]], [[5., 0., 0.], [5., 0., 0.]]]
        profiles = [[[0., 0., 0.], [10., 0., 0.], 2., 6.],
                    [[10., 0., 0.], [0., 0., 0.], 6., 2.],
                    [[0., 0., 0.], [10., 0., 0.], 2., 6.],
                    [[5., 0., 0.], [5., 0., 0.], 4., 4.]]
        original = self.h.functions[Symbol("EL:TOUCHES")]
        self.h.functions[Symbol("TEST:TOUCHES")] = original
        traces = []
        self.h.builtins["EL:TOUCHES"] = lambda *args: traces.append(copy.deepcopy(args)) or self.call("TEST:Touches", *args)
        old = self.call("ORACLE:WireContactStrips", segments, profiles)
        old_trace = traces[:]
        traces.clear()
        actual = self.compare("WireContactStrips", segments, profiles)
        self.assertEqual(actual, old)
        self.assertEqual(len(actual), 9)
        self.assertEqual(traces, old_trace + old_trace)

    def test_profile_preparation_is_lazy_and_retains_first_failure_order(self):
        good = [[0., 0., 0.], [10., 0., 0.], 2., 4.]
        bad = [[0., 0., 0.], ["broken", 0., 0.], 2., 4.]
        segments = [[[0., 0., 0.], [5., 0., 0.]], [[5., 0., 0.], [10., 0., 0.]]]
        strip_function = self.h.functions[Symbol("EL:WIRESTRIP")]
        self.h.functions[Symbol("TEST:STRIP")] = strip_function
        visits = []
        self.h.builtins["EL:WIRESTRIP"] = lambda *args: visits.append(copy.deepcopy(args)) or self.call("TEST:Strip", *args)
        errors = []
        for function in ("ORACLE:WireContactStrips", "EL:WireContactStrips"):
            visits.clear()
            with self.assertRaises((TypeError, ValueError)) as raised:
                self.call(function, segments, [good, bad])
            errors.append((type(raised.exception), str(raised.exception), visits[:]))
        self.assertEqual(errors[0], errors[1])
        self.assertEqual(len(errors[0][2]), 1, "first profile must be processed before invalid second profile")
        self.assertIsNone(self.compare("WireContactStrips", None, [bad]))
        self.assertIsNone(self.compare("WireContactStrips", segments, None))
        self.assertIsNone(self.compare("WireContactStrips", None, None))

    def test_bounds_keep_complete_segment_order_and_one_progress_scan(self):
        center = [[[float(index), 0., 0.], [float(index+1), 0., 0.]] for index in range(3)]
        strips = [[Pair(Symbol("SEGMENTS"), [segment, segment])] for segment in center]
        wire = [Pair(Symbol("SEGMENTS"), center), Pair(Symbol("CONTACT-STRIPS"), strips)]
        original = self.h.functions[Symbol("EL:SEGMENTBOUNDS")]
        self.h.functions[Symbol("TEST:BOUNDS")] = original
        inputs = []
        self.h.builtins["EL:SEGMENTBOUNDS"] = lambda segments: inputs.append(copy.deepcopy(segments)) or self.call("TEST:Bounds", segments)
        self.compare("WireContactBounds", wire)
        self.assertEqual(len(inputs), 2)
        self.assertEqual(inputs[0], center + [seg for strip in strips for seg in field("segments", strip)])
        self.assertEqual(inputs[0], inputs[1])
        inputs.clear()
        saved = [Pair(Symbol("CONTACT-BOUNDS"), None)] + wire
        self.assertIsNone(self.compare("WireContactBounds", saved))
        self.assertEqual(inputs, [])
        for strips in (None, [None], [[Pair(Symbol("SEGMENTS"), None)]]):
            self.compare("WireContactBounds", [Pair(Symbol("SEGMENTS"), center), Pair(Symbol("CONTACT-STRIPS"), strips)])

    def test_bounds_progress_retains_original_4096_segment_checkpoint(self):
        segment = [[0., 0., 0.], [1., 0., 0.]]
        wire = [Pair(Symbol("SEGMENTS"), [segment]),
                Pair(Symbol("CONTACT-STRIPS"), [[Pair(Symbol("SEGMENTS"), [segment]*4096)]])]
        self.h.frames[0]["*EL:CONTACTCONTEXT*"] = "fixture"
        visits = []
        self.h.builtins["EL:CONTACTPROGRESS"] = lambda *args: visits.append(args)
        self.compare("WireContactBounds", wire)
        self.assertEqual(visits, [("bounds", 4096, "fixture")]*2)

    def test_single_segment_retains_original_profile_setup_without_cache_lists(self):
        segments = [[[0., 0., 0.], [5., 0., 0.]]]
        profiles = [[[0., 0., 0.], [10., 0., 0.], 2., 4.]]
        original = self.h.builtins["LIST"]
        lists = []
        def make_list(*values):
            lists.append(copy.deepcopy(values))
            return original(*values)
        self.h.builtins["LIST"] = make_list
        expected = self.call("ORACLE:WireContactStrips", segments, profiles)
        old = lists[:]
        lists.clear()
        actual = self.call("EL:WireContactStrips", segments, profiles)
        self.assertEqual(actual, expected)
        self.assertEqual(lists, old)

    def test_complete_fresh_wire_records_match_frozen_output_and_logs(self):
        points = [[0., 0., 0.], [10., 0., 0.], [10., 10., 0.], [0., 0., 0.]]
        data = [[Pair(0, "LINE"), Pair(5, "line"), Pair(8, "W"), Pair(10, points[0]), Pair(11, points[1])],
                self.polyline(points, [0., 0., 0., 0.]),
                self.polyline(points, [.5, -.5, 0., 0.]),
                self.polyline(points, [0., 0., 0., 0.], closed=1),
                self.polyline(points, widths=[(0., 4.), (4., 8.), (0., 0.), (0., 0.)]),
                self.polyline([[0., 0., 0.], [0., 0., 0.], [1.e-10, 0., 0.]]),
                self.polyline([[0., 0., 0.]]), self.polyline([], constant=0.)]
        for row in data:
            with self.subTest(row=row):
                self.compare("WireRecordDXF", "wire", row, self.cfg)
        first = self.call("EL:WireRecordDXF", "wire", data[1], self.cfg)
        changed = self.call("EL:WireRecordDXF", "wire", self.polyline(points, constant=20.), self.cfg)
        self.assertNotEqual(field("contact-bounds", first), field("contact-bounds", changed))
        self.compare("WireRecordDXF", "wire", data[1], self.cfg)

    def test_long_polyline_eliminates_accumulated_append_copying(self):
        count = 300
        points = [[float(index), 0., 0.] for index in range(count+1)]
        original = self.h.builtins["APPEND"]
        copied = [0]
        def append(*values):
            copied[0] += sum(len(seq(value)) for value in values[:-1])
            return original(*values)
        self.h.builtins["APPEND"] = append
        expected = self.call("ORACLE:PolylineSegments", points, None, None, .01)
        old = copied[0]
        copied[0] = 0
        actual = self.call("EL:PolylineSegments", points, None, None, .01)
        self.assertEqual(actual, expected)
        self.assertEqual(old, count*(count-1)//2)
        self.assertEqual(copied[0], 0)

    def test_wide_bounds_eliminate_accumulated_append_copying(self):
        count = 100
        segment = [[0., 0., 0.], [1., 0., 0.]]
        strips = [[Pair(Symbol("SEGMENTS"), [segment]*4)] for _ in range(count)]
        wire = [Pair(Symbol("SEGMENTS"), [segment]), Pair(Symbol("CONTACT-STRIPS"), strips)]
        original = self.h.builtins["APPEND"]
        copied = [0]
        def append(*values):
            copied[0] += sum(len(seq(value)) for value in values[:-1])
            return original(*values)
        self.h.builtins["APPEND"] = append
        expected = self.call("ORACLE:WireContactBounds", wire)
        old = copied[0]
        copied[0] = 0
        actual = self.call("EL:WireContactBounds", wire)
        self.assertEqual(actual, expected)
        self.assertEqual(old, count + 4*count*(count-1)//2)
        self.assertEqual(copied[0], 0)

    def test_profiles_compute_baselines_once_per_call_and_do_not_cross_calls(self):
        segments = [[[float(index), 10., 0.], [float(index+1), 10., 0.]] for index in range(20)]
        profiles = [[[0., float(index), 0.], [10., float(index), 0.], 2., 4.] for index in range(8)]
        # Misses isolate profile setup work from interpolation/strip geometry.
        self.h.builtins["EL:TOUCHES"] = lambda *args: None
        original = self.h.functions[Symbol("EL:NORM")]
        self.h.functions[Symbol("TEST:NORM")] = original
        norms = [0]
        def norm(value):
            norms[0] += 1
            return self.call("TEST:Norm", value)
        self.h.builtins["EL:NORM"] = norm
        self.assertIsNone(self.call("ORACLE:WireContactStrips", segments, profiles))
        self.assertEqual(norms[0], len(segments)*len(profiles))
        norms[0] = 0
        self.assertIsNone(self.call("EL:WireContactStrips", segments, profiles))
        self.assertEqual(norms[0], len(profiles))
        self.assertIsNone(self.call("EL:WireContactStrips", segments, profiles))
        self.assertEqual(norms[0], 2*len(profiles))


if __name__ == "__main__":
    unittest.main()
