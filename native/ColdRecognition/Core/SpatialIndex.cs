// Date: 2026-10-22. Read-only, per-call spatial tree for the cold-recognition prototype.
// No AutoCAD references, native handles, global caches, or drawing writes belong here.
using System;
using System.Collections.Generic;

namespace EmergencyLighting.ColdRecognition.Core
{
    public struct Point3
    {
        public readonly double X;
        public readonly double Y;
        public readonly double Z;

        public Point3(double x, double y, double z)
        {
            X = x;
            Y = y;
            Z = z;
        }

        public double Coordinate(int axis)
        {
            if (axis == 0) return X;
            if (axis == 1) return Y;
            if (axis == 2) return Z;
            throw new ArgumentOutOfRangeException("axis");
        }
    }

    public struct Bounds3
    {
        public readonly Point3 Min;
        public readonly Point3 Max;

        public Bounds3(Point3 min, Point3 max)
        {
            Min = min;
            Max = max;
        }

        public static Bounds3 At(Point3 point)
        {
            return new Bounds3(point, point);
        }

        public static Bounds3 Union(Bounds3 a, Bounds3 b)
        {
            return new Bounds3(
                new Point3(Math.Min(a.Min.X, b.Min.X), Math.Min(a.Min.Y, b.Min.Y), Math.Min(a.Min.Z, b.Min.Z)),
                new Point3(Math.Max(a.Max.X, b.Max.X), Math.Max(a.Max.Y, b.Max.Y), Math.Max(a.Max.Z, b.Max.Z)));
        }
    }

    public sealed class SpatialItem
    {
        public int SourceIndex { get; private set; }
        public string KeySignature { get; private set; }
        public Point3 Point { get; private set; }
        public Bounds3? Bounds { get; private set; }

        // KeySignature must be the exact EL:Signature result, not a re-created C# serialization.
        public SpatialItem(int sourceIndex, string keySignature, Point3 point, Bounds3? bounds)
        {
            SourceIndex = sourceIndex;
            KeySignature = keySignature;
            Point = point;
            Bounds = bounds;
        }
    }

    public struct SpatialNode
    {
        // ItemIndex is the original source-list index. Left/Right index Nodes; -1 means nil.
        public readonly int ItemIndex;
        public readonly int Left;
        public readonly int Right;
        public readonly Bounds3 Bounds;
        internal readonly int ItemOrdinal;

        internal SpatialNode(int itemIndex, int itemOrdinal, int left, int right, Bounds3 bounds)
        {
            ItemIndex = itemIndex;
            ItemOrdinal = itemOrdinal;
            Left = left;
            Right = right;
            Bounds = bounds;
        }
    }

    public sealed class SpatialIndex
    {
        public const double GapEpsilon = 1.0e-7;
        private readonly SpatialItem[] items;
        private readonly SpatialNode[] nodes;

        public int Root { get; private set; }
        public int Count { get { return nodes.Length; } }
        // Copies keep a consumer from mutating the index while another query is running.
        public SpatialNode[] Nodes { get { return (SpatialNode[])nodes.Clone(); } }

        private SpatialIndex(SpatialItem[] items, SpatialNode[] nodes, int root)
        {
            this.items = items;
            this.nodes = nodes;
            Root = root;
        }

        public SpatialNode GetNode(int nodeIndex)
        {
            return nodes[nodeIndex];
        }

        // Three axis sorts are sufficient. Partition each ordering by the current pivot;
        // because signatures are unique this yields the same pivot/children as recursively
        // re-sorting EL:SpatialTreeBuild's reversed left/right lists, at every level.
        public static SpatialIndex Build(IList<SpatialItem> source, int initialAxis)
        {
            if (source == null) throw new ArgumentNullException("source");
            if (initialAxis < 0 || initialAxis > 2) throw new ArgumentOutOfRangeException("initialAxis");
            SpatialItem[] copied = new SpatialItem[source.Count];
            HashSet<string> signatures = new HashSet<string>(StringComparer.Ordinal);
            HashSet<int> sourceIndices = new HashSet<int>();
            for (int i = 0; i < copied.Length; ++i)
            {
                SpatialItem item = source[i];
                if (item == null) throw new ArgumentException("A spatial item is null.", "source");
                if (item.KeySignature == null) throw new ArgumentException("A key signature is null.", "source");
                // CAD 2020 legacy string collation is not assumed for non-ASCII keys.
                // Handle/endpoint/segment signatures used by this prototype are ASCII.
                foreach (char character in item.KeySignature)
                    if (character > 127) throw new ArgumentException("Non-ASCII key signatures require the original LISP sort.", "source");
                if (!signatures.Add(item.KeySignature))
                    throw new ArgumentException("Duplicate key signatures require the original LISP sort.", "source");
                if (!sourceIndices.Add(item.SourceIndex))
                    throw new ArgumentException("Source indices must be unique.", "source");
                ValidatePoint(item.Point, "source point");
                if (item.Bounds.HasValue) ValidateBounds(item.Bounds.Value, "source bounds");
                copied[i] = item;
            }

            if (copied.Length == 0) return new SpatialIndex(copied, new SpatialNode[0], -1);
            int[][] sorted = new int[3][];
            for (int axis = 0; axis < 3; ++axis)
            {
                sorted[axis] = new int[copied.Length];
                for (int i = 0; i < copied.Length; ++i) sorted[axis][i] = i;
                int sortAxis = axis;
                Array.Sort(sorted[axis], delegate(int a, int b) { return Compare(copied[a], copied[b], sortAxis); });
            }
            List<SpatialNode> built = new List<SpatialNode>(copied.Length);
            int root = BuildPartition(copied, sorted, initialAxis, built);
            return new SpatialIndex(copied, built.ToArray(), root);
        }

        private static int Compare(SpatialItem a, SpatialItem b, int axis)
        {
            double ac = a.Point.Coordinate(axis);
            double bc = b.Point.Coordinate(axis);
            if (ac < bc) return -1;
            if (ac > bc) return 1;
            return StringComparer.Ordinal.Compare(a.KeySignature, b.KeySignature);
        }

        private static int BuildPartition(SpatialItem[] source, int[][] sorted, int axis, List<SpatialNode> output)
        {
            int count = sorted[axis].Length;
            if (count == 0) return -1;
            int mid = count / 2;
            int pivot = sorted[axis][mid];
            int nodeIndex = output.Count;
            output.Add(default(SpatialNode));
            int leftNode = -1;
            int rightNode = -1;
            if (count > 1)
            {
                int[][] left = new int[3][];
                int[][] right = new int[3][];
                for (int order = 0; order < 3; ++order)
                {
                    left[order] = new int[mid];
                    right[order] = new int[count - mid - 1];
                    int li = 0;
                    int ri = 0;
                    foreach (int ordinal in sorted[order])
                    {
                        if (ordinal == pivot) continue;
                        if (Compare(source[ordinal], source[pivot], axis) < 0) left[order][li++] = ordinal;
                        else right[order][ri++] = ordinal;
                    }
                }
                int nextAxis = (axis + 1) % 3;
                leftNode = BuildPartition(source, left, nextAxis, output);
                rightNode = BuildPartition(source, right, nextAxis, output);
            }
            Bounds3 bounds = source[pivot].Bounds ?? Bounds3.At(source[pivot].Point);
            if (leftNode >= 0) bounds = Bounds3.Union(bounds, output[leftNode].Bounds);
            if (rightNode >= 0) bounds = Bounds3.Union(bounds, output[rightNode].Bounds);
            output[nodeIndex] = new SpatialNode(source[pivot].SourceIndex, pivot, leftNode, rightNode, bounds);
            return nodeIndex;
        }

        public int[] QueryBox(Bounds3 bounds, double tolerance)
        {
            ValidateBounds(bounds, "query bounds");
            ValidateNumber(tolerance, "tolerance");
            List<int> result = new List<int>();
            if (Root < 0) return result.ToArray();
            Stack<int> stack = new Stack<int>();
            stack.Push(Root);
            while (stack.Count > 0)
            {
                SpatialNode node = nodes[stack.Pop()];
                if (!Overlaps(node.Bounds, bounds, tolerance)) continue;
                SpatialItem item = items[node.ItemOrdinal];
                // EL:BoundsOverlap returns nil for absent item bounds.
                if (item.Bounds.HasValue && Overlaps(item.Bounds.Value, bounds, tolerance)) result.Add(item.SourceIndex);
                if (node.Right >= 0) stack.Push(node.Right);
                if (node.Left >= 0) stack.Push(node.Left);
            }
            return result.ToArray();
        }

        public int[] QueryRay(Point3 origin, Point3 direction, double limit)
        {
            ValidatePoint(origin, "origin");
            ValidatePoint(direction, "direction");
            ValidateNumber(limit, "limit");
            List<int> result = new List<int>();
            if (Root < 0) return result.ToArray();
            Stack<int> stack = new Stack<int>();
            stack.Push(Root);
            while (stack.Count > 0)
            {
                SpatialNode node = nodes[stack.Pop()];
                if (!RayHits(origin, direction, limit, node.Bounds)) continue;
                SpatialItem item = items[node.ItemOrdinal];
                if (RayHits(origin, direction, limit, item.Bounds ?? Bounds3.At(item.Point))) result.Add(item.SourceIndex);
                if (node.Right >= 0) stack.Push(node.Right);
                if (node.Left >= 0) stack.Push(node.Left);
            }
            return result.ToArray();
        }

        // Keep the source operand order: tolerance expands b only, on all three axes.
        public static bool Overlaps(Bounds3 a, Bounds3 b, double tolerance)
        {
            return a.Min.X <= b.Max.X + tolerance && a.Max.X >= b.Min.X - tolerance
                && a.Min.Y <= b.Max.Y + tolerance && a.Max.Y >= b.Min.Y - tolerance
                && a.Min.Z <= b.Max.Z + tolerance && a.Max.Z >= b.Min.Z - tolerance;
        }

        // Port of EL:RayBoxHits, including the strict 1e-15 parallel threshold,
        // 1e-7 roundoff padding, near=0, far=limit, and sequential slab rejection.
        public static bool RayHits(Point3 origin, Point3 direction, double limit, Bounds3 bounds)
        {
            double near = 0.0;
            double far = limit;
            for (int axis = 0; axis < 3; ++axis)
            {
                double low = bounds.Min.Coordinate(axis) - GapEpsilon - origin.Coordinate(axis);
                double high = bounds.Max.Coordinate(axis) + GapEpsilon - origin.Coordinate(axis);
                double d = direction.Coordinate(axis);
                if (Math.Abs(d) < 1.0e-15)
                {
                    if (low > 0.0 || high < 0.0) return false;
                }
                else
                {
                    low /= d;
                    high /= d;
                    if (low > high)
                    {
                        double temp = low;
                        low = high;
                        high = temp;
                    }
                    near = Math.Max(near, low);
                    far = Math.Min(far, high);
                    if (near > far) return false;
                }
            }
            return true;
        }

        private static void ValidateBounds(Bounds3 bounds, string label)
        {
            ValidatePoint(bounds.Min, label);
            ValidatePoint(bounds.Max, label);
            if (bounds.Min.X > bounds.Max.X || bounds.Min.Y > bounds.Max.Y || bounds.Min.Z > bounds.Max.Z)
                throw new ArgumentException("Reversed " + label + ".");
        }

        private static void ValidatePoint(Point3 point, string label)
        {
            ValidateNumber(point.X, label);
            ValidateNumber(point.Y, label);
            ValidateNumber(point.Z, label);
        }

        private static void ValidateNumber(double number, string label)
        {
            // EL:Number accepts only finite values with abs < 1e100.
            if (Double.IsNaN(number) || Double.IsInfinity(number) || Math.Abs(number) >= 1.0e100)
                throw new ArgumentException("Invalid " + label + ".");
        }
    }
}
