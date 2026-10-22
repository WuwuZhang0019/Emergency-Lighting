// Date: 2026-10-22. No AutoCAD runtime needed; compare with the original recursive tree.
using System;
using System.Collections.Generic;
using EmergencyLighting.ColdRecognition.Core;

namespace EmergencyLighting.ColdRecognition.Tests
{
    public static class SpatialIndexTests
    {
        private sealed class ReferenceNode
        {
            public SpatialItem Item;
            public ReferenceNode Left;
            public ReferenceNode Right;
            public Bounds3 Bounds;
        }

        public static int Run()
        {
            EmptyAndSingle();
            AxisAndSignatureOrder();
            MixedDimensionsAndMissingBounds();
            BoundaryAndRaySemantics();
            RandomizedTreeAndQueries();
            LargeEndpointInput();
            RejectAmbiguousOrInvalidInput();
            PerCallIsolation();
            FrozenLispHostFixture();
            return 9;
        }

        private static void EmptyAndSingle()
        {
            SpatialIndex empty = SpatialIndex.Build(new SpatialItem[0], 0);
            Require(empty.Root == -1 && empty.Count == 0, "empty tree");
            Require(empty.QueryBox(Box(-1, -1, -1, 1, 1, 1), 0.0).Length == 0, "empty box query");
            Require(empty.QueryRay(new Point3(0, 0, 0), new Point3(1, 0, 0), 100).Length == 0, "empty ray query");
            SpatialItem[] single = { Item(17, "\"ONE\"", 5, 6, 7, Box(4, 5, 6, 7, 8, 9)) };
            AssertMatches(single, 0);
            SpatialIndex tree = SpatialIndex.Build(single, 2);
            Require(tree.GetNode(tree.Root).ItemIndex == 17, "source index is not internal ordinal");
        }

        private static void AxisAndSignatureOrder()
        {
            // Planar/coincident positions exercise signature sorting at Z-only levels.
            SpatialItem[] items = {
                Item(11, "\"B\"", 0, 0, 0, Box(0, 0, 0, 0, 0, 0)),
                Item(12, "\"a\"", 0, 0, 0, Box(0, 0, 0, 0, 0, 0)),
                Item(13, "(\"A\" START)", 0, 0, 0, Box(0, 0, 0, 0, 0, 0)),
                Item(14, "\"A\"", 0, 0, 0, Box(0, 0, 0, 0, 0, 0)),
                Item(15, "10", 0, 0, 0, Box(0, 0, 0, 0, 0, 0)),
                Item(16, "2", 0, 0, 0, Box(0, 0, 0, 0, 0, 0)),
                Item(17, "NIL", 0, 0, 0, Box(0, 0, 0, 0, 0, 0))
            };
            for (int axis = 0; axis < 3; ++axis)
            {
                AssertMatches(items, axis);
                Array.Reverse(items);
                AssertMatches(items, axis);
            }
        }

        private static void MixedDimensionsAndMissingBounds()
        {
            SpatialItem[] items = {
                Item(0, "\"WIRE-0\"", 0, 0, 0, Box(-50, -0.5, -0.1, 50, 0.5, 0.1)),
                Item(1, "\"BLOCK-1\"", 50, 20, 6, Box(49, 19, 5, 51, 21, 7)),
                Item(2, "(\"WIRE-2\" START)", 25, 0, 0, Box(25, 0, 0, 25, 0, 0)),
                Item(3, "\"POINT-NO-BOUNDS\"", 0, 0, 0, null),
                Item(4, "\"REMOTE\"", 100000, -200000, 19, Box(99999, -200010, 18, 100010, -199990, 20))
            };
            for (int axis = 0; axis < 3; ++axis) AssertMatches(items, axis);
            SpatialIndex tree = SpatialIndex.Build(items, 0);
            Require(Array.IndexOf(tree.QueryBox(Box(0, 0, 0, 0, 0, 0), 0), 3) < 0,
                "box query must omit item without bounds");
            Require(Array.IndexOf(tree.QueryRay(new Point3(0, 0, 0), new Point3(1, 0, 0), 0), 3) >= 0,
                "ray query uses point when bounds are absent");
        }

        private static void BoundaryAndRaySemantics()
        {
            Bounds3 point = Box(1, 0, 0, 1, 0, 0);
            Require(SpatialIndex.Overlaps(point, point, 0), "box inclusive boundary");
            Require(!SpatialIndex.Overlaps(point, point, -1.0e-9), "negative tolerance retains contraction semantics");
            Require(SpatialIndex.Overlaps(point, Box(1 + 1.0e-7, 0, 0, 1 + 1.0e-7, 0, 0), 1.0e-7),
                "box tolerance is applied to query bounds");
            Require(!SpatialIndex.Overlaps(point, Box(1, 0, 0.1, 1, 0, 0.1), 0), "box checks Z");
            Require(SpatialIndex.RayHits(new Point3(0, 0, 0), new Point3(1, 0, 0), 1, point), "ray inclusive limit");
            Require(!SpatialIndex.RayHits(new Point3(0, 0, 0), new Point3(-1, 0, 0), 1, point), "ray direction");
            Require(SpatialIndex.RayHits(new Point3(1, 0, 0), new Point3(0, 0, 0), -1, point),
                "all-parallel ray preserves original negative-limit behavior");
            double[] nearParallel = { 0.0, 0.5e-15, 1.0e-15, -1.0e-15, 2.0e-15 };
            double[] offsets = { -2.0e-7, -1.0e-7, 0, 1.0e-7, 2.0e-7 };
            foreach (double component in nearParallel)
                foreach (double offset in offsets)
                {
                    Point3 origin = new Point3(0, offset, offset);
                    Point3 direction = new Point3(1, component, -component);
                    Require(SpatialIndex.RayHits(origin, direction, 10, point) == ReferenceRay(origin, direction, 10, point),
                        "parallel/epsilon slab boundary");
                }
        }

        private static void RandomizedTreeAndQueries()
        {
            Random random = new Random(20261022);
            int[] sizes = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 17, 32, 63, 128, 257 };
            foreach (int size in sizes)
                for (int repetition = 0; repetition < 3; ++repetition)
                {
                    SpatialItem[] items = RandomItems(random, size, repetition == 0);
                    int axis = repetition;
                    SpatialIndex actual = SpatialIndex.Build(items, axis);
                    ReferenceNode expected = ReferenceBuild(new List<SpatialItem>(items), axis);
                    AssertTree(expected, actual, actual.Root);
                    for (int q = 0; q < 20; ++q)
                    {
                        Point3 p = new Point3(random.Next(-120, 121), random.Next(-120, 121), random.Next(-3, 4));
                        double radius = q % 4 == 0 ? 0.0 : random.Next(1, 35);
                        Bounds3 box = new Bounds3(new Point3(p.X - radius, p.Y - radius, p.Z - radius),
                            new Point3(p.X + radius, p.Y + radius, p.Z + radius));
                        double tolerance = q % 3 == 0 ? 0.0 : (q % 3 == 1 ? 1.0e-7 : -1.0e-7);
                        List<int> boxResult = new List<int>();
                        ReferenceBox(expected, box, tolerance, boxResult);
                        AssertSequence(boxResult.ToArray(), actual.QueryBox(box, tolerance), "random box candidate order");
                        Point3 direction = new Point3(random.Next(-2, 3), random.Next(-2, 3), random.Next(-1, 2));
                        double limit = q % 5 == 0 ? 0.0 : random.Next(1, 250);
                        List<int> rayResult = new List<int>();
                        ReferenceRayQuery(expected, p, direction, limit, rayResult);
                        AssertSequence(rayResult.ToArray(), actual.QueryRay(p, direction, limit), "random ray candidate order");
                    }
                }
        }

        private static void LargeEndpointInput()
        {
            // Original-DWG scale: about 6,000 endpoints, largely coplanar, built afresh.
            SpatialItem[] items = new SpatialItem[6134];
            for (int i = 0; i < items.Length; ++i)
            {
                Point3 p = new Point3((i % 113) * 20.0, (i / 113) * 30.0, 0.0);
                items[i] = new SpatialItem(i, "(\"W" + (i / 2).ToString("D5") + "\" " + (i % 2 == 0 ? "START" : "END") + ")", p, Bounds3.At(p));
            }
            SpatialIndex actual = SpatialIndex.Build(items, 0);
            ReferenceNode expected = ReferenceBuild(new List<SpatialItem>(items), 0);
            AssertTree(expected, actual, actual.Root);
            Bounds3 box = Box(-10, -10, -0.01, 500, 500, 0.01);
            List<int> result = new List<int>();
            ReferenceBox(expected, box, 1.0e-7, result);
            AssertSequence(result.ToArray(), actual.QueryBox(box, 1.0e-7), "large endpoint order");
        }

        private static void RejectAmbiguousOrInvalidInput()
        {
            ExpectArgument(delegate { SpatialIndex.Build(null, 0); }, "null source");
            ExpectArgument(delegate { SpatialIndex.Build(new SpatialItem[0], 3); }, "invalid axis");
            ExpectArgument(delegate { SpatialIndex.Build(new SpatialItem[] { null }, 0); }, "null item");
            ExpectArgument(delegate { SpatialIndex.Build(new[] { Item(0, null, 0, 0, 0, null) }, 0); }, "null signature");
            ExpectArgument(delegate { SpatialIndex.Build(new[] { Item(0, "\u56fe\u5757", 0, 0, 0, null) }, 0); }, "legacy non-ASCII collation");
            ExpectArgument(delegate { SpatialIndex.Build(new[] { Item(0, "same", 0, 0, 0, null), Item(1, "same", 1, 2, 3, null) }, 0); },
                "duplicate signatures use caller fallback");
            ExpectArgument(delegate { SpatialIndex.Build(new[] { Item(0, "a", 0, 0, 0, null), Item(0, "b", 1, 2, 3, null) }, 0); },
                "duplicate source indices");
            ExpectArgument(delegate { SpatialIndex.Build(new[] { Item(0, "nan", Double.NaN, 0, 0, null) }, 0); }, "NaN");
            ExpectArgument(delegate { SpatialIndex.Build(new[] { Item(0, "infinity", 0, Double.PositiveInfinity, 0, null) }, 0); }, "infinity");
            ExpectArgument(delegate { SpatialIndex.Build(new[] { Item(0, "large", 0, 0, 1.0e100, null) }, 0); }, "EL:Number bound");
            ExpectArgument(delegate { SpatialIndex.Build(new[] { Item(0, "reverse", 0, 0, 0, Box(1, 0, 0, 0, 1, 1)) }, 0); }, "reversed bounds");
            SpatialIndex empty = SpatialIndex.Build(new SpatialItem[0], 0);
            ExpectArgument(delegate { empty.QueryBox(Box(0, 0, 0, 1, 1, 1), Double.NaN); }, "invalid tolerance");
            ExpectArgument(delegate { empty.QueryRay(new Point3(0, 0, 0), new Point3(Double.NaN, 0, 0), 1); }, "invalid direction");
        }

        private static void PerCallIsolation()
        {
            List<SpatialItem> source = new List<SpatialItem>();
            source.Add(Item(0, "a", 0, 0, 0, Box(0, 0, 0, 0, 0, 0)));
            SpatialIndex first = SpatialIndex.Build(source, 0);
            source[0] = Item(0, "a", 100000, 0, 0, Box(100000, 0, 0, 100000, 0, 0));
            SpatialIndex second = SpatialIndex.Build(source, 0);
            Bounds3 origin = Box(0, 0, 0, 0, 0, 0);
            Require(first.QueryBox(origin, 0).Length == 1, "old invocation owns immutable source values");
            Require(second.QueryBox(origin, 0).Length == 0, "new invocation reads current source");
            SpatialNode[] exposed = first.Nodes;
            exposed[0] = default(SpatialNode);
            Require(first.QueryBox(origin, 0).Length == 1, "node array copy cannot mutate index");
        }

        private static void FrozenLispHostFixture()
        {
            // Date: 2026-10-22. Generated by the unchanged EL:SpatialTree,
            // EL:SpatialBoxQuery and EL:SpatialRayQuery in tests/autolisp_host.py.
            // ASCII K00..K18 keys have the same ordering under host/native serialization.
            SpatialItem[] items = new SpatialItem[19];
            for (int i = 0; i < items.Length; ++i)
            {
                Point3 p = new Point3((i * 7) % 11 - 5, (i * 5) % 9 - 4, i % 3 - 1);
                items[i] = new SpatialItem(i, "\"K" + i.ToString("D2") + "\"", p,
                    Box(p.X - (i % 2) * 0.5, p.Y - 0.1, p.Z, p.X + (i % 2) * 0.5, p.Y + 0.1, p.Z));
            }
            int[][] expectedPreorder = {
                new[] { 18, 8, 2, 13, 0, 11, 16, 7, 10, 5, 17, 15, 6, 9, 4, 1, 3, 12, 14 },
                new[] { 8, 18, 9, 15, 0, 6, 13, 11, 2, 4, 10, 12, 7, 1, 3, 17, 16, 5, 14 },
                new[] { 7, 1, 4, 18, 0, 15, 3, 9, 6, 12, 2, 5, 11, 8, 16, 10, 17, 13, 14 }
            };
            int[][] expectedBox = { new[] { 13, 10, 4, 1 }, new[] { 13, 4, 10, 1 }, new[] { 1, 4, 10, 13 } };
            int[][] expectedRay = { new[] { 10, 1 }, new[] { 10, 1 }, new[] { 1, 10 } };
            for (int axis = 0; axis < 3; ++axis)
            {
                SpatialIndex actual = SpatialIndex.Build(items, axis);
                List<int> preorder = new List<int>();
                CollectPreorder(actual, actual.Root, preorder);
                AssertSequence(expectedPreorder[axis], preorder.ToArray(), "frozen LISP pivot order");
                AssertSequence(expectedBox[axis], actual.QueryBox(Box(-2, -2, -0.1, 3, 3, 1), 0.1), "frozen LISP box order");
                AssertSequence(expectedRay[axis], actual.QueryRay(new Point3(-10, 1, 0), new Point3(1, 0, 0), 20), "frozen LISP ray order");
            }
        }

        private static void CollectPreorder(SpatialIndex index, int current, List<int> output)
        {
            if (current < 0) return;
            SpatialNode node = index.GetNode(current);
            output.Add(node.ItemIndex);
            CollectPreorder(index, node.Left, output);
            CollectPreorder(index, node.Right, output);
        }

        private static SpatialItem[] RandomItems(Random random, int count, bool planar)
        {
            SpatialItem[] items = new SpatialItem[count];
            for (int i = 0; i < count; ++i)
            {
                double x = random.Next(-100, 101);
                double y = random.Next(-100, 101);
                double z = planar ? 0 : random.Next(-3, 4);
                double hx = random.Next(0, 15);
                double hy = random.Next(0, 15);
                double hz = planar ? 0 : random.Next(0, 2);
                Bounds3? bounds = i % 13 == 0 ? (Bounds3?)null : Box(x - hx, y - hy, z - hz, x + hx, y + hy, z + hz);
                items[i] = Item(i * 3 + 2, "\"KEY-" + i.ToString("D5") + "\"", x, y, z, bounds);
            }
            for (int i = items.Length - 1; i > 0; --i)
            {
                int j = random.Next(i + 1);
                SpatialItem swap = items[i];
                items[i] = items[j];
                items[j] = swap;
            }
            return items;
        }

        private static void AssertMatches(SpatialItem[] items, int axis)
        {
            SpatialIndex actual = SpatialIndex.Build(items, axis);
            ReferenceNode expected = ReferenceBuild(new List<SpatialItem>(items), axis);
            AssertTree(expected, actual, actual.Root);
        }

        private static ReferenceNode ReferenceBuild(List<SpatialItem> input, int axis)
        {
            if (input.Count == 0) return null;
            // Literal recursive-sort/reversed-child construction from EL:SpatialTreeBuild.
            input.Sort(delegate(SpatialItem a, SpatialItem b)
            {
                double av = a.Point.Coordinate(axis);
                double bv = b.Point.Coordinate(axis);
                return av == bv ? StringComparer.Ordinal.Compare(a.KeySignature, b.KeySignature) : (av < bv ? -1 : 1);
            });
            int mid = input.Count / 2;
            SpatialItem pivot = input[mid];
            List<SpatialItem> left = input.GetRange(0, mid);
            left.Reverse();
            List<SpatialItem> right = input.GetRange(mid + 1, input.Count - mid - 1);
            right.Reverse();
            ReferenceNode node = new ReferenceNode();
            node.Item = pivot;
            node.Left = ReferenceBuild(left, (axis + 1) % 3);
            node.Right = ReferenceBuild(right, (axis + 1) % 3);
            node.Bounds = pivot.Bounds ?? Bounds3.At(pivot.Point);
            if (node.Left != null) node.Bounds = ReferenceUnion(node.Bounds, node.Left.Bounds);
            if (node.Right != null) node.Bounds = ReferenceUnion(node.Bounds, node.Right.Bounds);
            return node;
        }

        private static Bounds3 ReferenceUnion(Bounds3 a, Bounds3 b)
        {
            return new Bounds3(new Point3(a.Min.X < b.Min.X ? a.Min.X : b.Min.X,
                a.Min.Y < b.Min.Y ? a.Min.Y : b.Min.Y, a.Min.Z < b.Min.Z ? a.Min.Z : b.Min.Z),
                new Point3(a.Max.X > b.Max.X ? a.Max.X : b.Max.X,
                a.Max.Y > b.Max.Y ? a.Max.Y : b.Max.Y, a.Max.Z > b.Max.Z ? a.Max.Z : b.Max.Z));
        }

        private static void AssertTree(ReferenceNode expected, SpatialIndex actual, int index)
        {
            if (expected == null)
            {
                Require(index == -1, "nil child layout");
                return;
            }
            Require(index >= 0, "non-nil child layout");
            SpatialNode node = actual.GetNode(index);
            Require(node.ItemIndex == expected.Item.SourceIndex, "pivot order");
            AssertPoint(expected.Bounds.Min, node.Bounds.Min);
            AssertPoint(expected.Bounds.Max, node.Bounds.Max);
            AssertTree(expected.Left, actual, node.Left);
            AssertTree(expected.Right, actual, node.Right);
        }

        private static void ReferenceBox(ReferenceNode node, Bounds3 query, double tolerance, List<int> result)
        {
            if (node == null || !ReferenceOverlap(node.Bounds, query, tolerance)) return;
            if (node.Item.Bounds.HasValue && ReferenceOverlap(node.Item.Bounds.Value, query, tolerance)) result.Add(node.Item.SourceIndex);
            ReferenceBox(node.Left, query, tolerance, result);
            ReferenceBox(node.Right, query, tolerance, result);
        }

        private static bool ReferenceOverlap(Bounds3 a, Bounds3 b, double tolerance)
        {
            for (int axis = 0; axis < 3; ++axis)
                if (!(a.Min.Coordinate(axis) <= b.Max.Coordinate(axis) + tolerance
                    && a.Max.Coordinate(axis) >= b.Min.Coordinate(axis) - tolerance)) return false;
            return true;
        }

        private static void ReferenceRayQuery(ReferenceNode node, Point3 origin, Point3 direction, double limit, List<int> result)
        {
            if (node == null || !ReferenceRay(origin, direction, limit, node.Bounds)) return;
            if (ReferenceRay(origin, direction, limit, node.Item.Bounds ?? Bounds3.At(node.Item.Point))) result.Add(node.Item.SourceIndex);
            ReferenceRayQuery(node.Left, origin, direction, limit, result);
            ReferenceRayQuery(node.Right, origin, direction, limit, result);
        }

        private static bool ReferenceRay(Point3 p, Point3 direction, double limit, Bounds3 bounds)
        {
            int axis = 0;
            double near = 0.0;
            double far = limit;
            bool ok = true;
            while (ok && axis < 3)
            {
                double low = bounds.Min.Coordinate(axis) - 1.0e-7 - p.Coordinate(axis);
                double high = bounds.Max.Coordinate(axis) + 1.0e-7 - p.Coordinate(axis);
                double d = direction.Coordinate(axis);
                if (Math.Abs(d) < 1.0e-15)
                {
                    if (low > 0.0 || high < 0.0) ok = false;
                }
                else
                {
                    low = low / d;
                    high = high / d;
                    if (low > high)
                    {
                        double swap = low;
                        low = high;
                        high = swap;
                    }
                    if (low > near) near = low;
                    if (high < far) far = high;
                    if (near > far) ok = false;
                }
                axis++;
            }
            return ok;
        }

        private static SpatialItem Item(int index, string key, double x, double y, double z, Bounds3? bounds)
        {
            return new SpatialItem(index, key, new Point3(x, y, z), bounds);
        }

        private static Bounds3 Box(double x1, double y1, double z1, double x2, double y2, double z2)
        {
            return new Bounds3(new Point3(x1, y1, z1), new Point3(x2, y2, z2));
        }

        private static void AssertPoint(Point3 a, Point3 b)
        {
            Require(a.X == b.X && a.Y == b.Y && a.Z == b.Z, "node bounds");
        }

        private static void AssertSequence(int[] expected, int[] actual, string label)
        {
            Require(expected.Length == actual.Length, label + " count");
            for (int i = 0; i < expected.Length; ++i) Require(expected[i] == actual[i], label + " at " + i);
        }

        private static void ExpectArgument(Action action, string label)
        {
            try { action(); }
            catch (ArgumentException) { return; }
            throw new InvalidOperationException("Expected fallback for " + label);
        }

        private static void Require(bool condition, string label)
        {
            if (!condition) throw new InvalidOperationException("Spatial regression: " + label);
        }
    }
}
