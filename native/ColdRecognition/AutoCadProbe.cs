// Date: 2026-10-22. Independent, read-only, per-call cold-recognition probe.
// This measures acquisition and coarse dependency work. It never supplies a
// production recognition result, edits a drawing, or retains a result cache.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using EmergencyLighting.ColdRecognition.Core;
using CadApplication = Autodesk.AutoCAD.ApplicationServices.Application;

namespace EmergencyLighting.ColdRecognition
{
    public sealed class AutoCadProbe
    {
        private sealed class Wire
        {
            internal string Handle;
            internal Bounds3 Bounds;
            internal readonly List<Endpoint> Ends = new List<Endpoint>();
        }

        private sealed class Block
        {
            internal string Handle;
            internal string EffectiveName;
            internal Point3 Position;
            internal Bounds3 Bounds;
        }

        private sealed class Endpoint
        {
            internal int WireIndex;
            internal string Side;
            internal Point3 Point;
            internal Point3 Direction;
            internal bool RayEligible;
        }

        private sealed class Sample
        {
            internal string Handle;
            internal Bounds3 Bounds;
        }

        private sealed class CallState
        {
            internal readonly List<Wire> Wires = new List<Wire>();
            internal readonly List<Block> Blocks = new List<Block>();
            internal readonly List<Endpoint> Ends = new List<Endpoint>();
            internal readonly List<Sample> Samples = new List<Sample>();
            internal readonly List<object> Errors = new List<object>();
            internal readonly Dictionary<string, int> WireHandles = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            internal readonly Dictionary<string, object> Metrics = new Dictionary<string, object>();
            internal int ErrorCount;
            internal int BoundsErrors;
            internal int Managed;
            internal int Lines;
            internal int Polylines;
            internal int Inserts;
            internal int Other;
            internal int Vertices;
            internal int Closed;
            internal int CurvedSegments;
            internal int NonDefaultNormals;
            internal int Changes;
            internal bool Limited;
            internal string Panel;
            internal string Status = "PROTOTYPE_COARSE_ONLY";

            internal void Error(string handle, string phase, System.Exception error)
            {
                ++ErrorCount;
                Status = "ERROR";
                if (Errors.Count < 10)
                    Errors.Add(Row("handle", handle, "phase", phase, "type", error.GetType().FullName, "message", BoundedMessage(error)));
            }
        }

        // Flat arguments: selection set, panel ObjectId, comma-separated root handles,
        // device tolerance, Dmax, boundary tolerance, existing output folder/file path.
        // Return value: (jsonText ((handle minPoint maxPoint) ...)), at most 16 samples.
        [LispFunction("ELNETCOLD76")]
        public static ResultBuffer Run(ResultBuffer arguments)
        {
            try
            {
                // The same callable entry proves both registration and version.
                // No active document, transaction, geometry or CallState is touched.
                TypedValue[] values = arguments == null ? new TypedValue[0] : arguments.AsArray();
                if (values.Length == 1 && values[0].TypeCode == (int)LispDataType.Text &&
                    String.Equals(values[0].Value as string, "EL_NET_COLD_PING_V1", StringComparison.Ordinal))
                    return new ResultBuffer(new TypedValue((int)LispDataType.Text, "EL_NET_COLD_PROBE_V1/0.1.76"));
                return RunCore(arguments);
            }
            catch (System.Exception)
            {
                // Even a failure while serializing/returning diagnostics is never
                // presented as a successful coarse analysis or a business result.
                return new ResultBuffer(new TypedValue((int)LispDataType.ListBegin),
                    new TypedValue((int)LispDataType.Text,
                        "{\"schema\":\"EL_NET_COLD_PROBE_V1\",\"status\":\"ERROR\",\"complete-recognition\":false,\"readonly\":true,\"result-cache\":false,\"error\":\"Unhandled diagnostic serialization or bridge failure\"}"),
                    new TypedValue((int)LispDataType.ListBegin), new TypedValue((int)LispDataType.ListEnd),
                    new TypedValue((int)LispDataType.ListEnd));
            }
        }

        private static ResultBuffer RunCore(ResultBuffer arguments)
        {
            Stopwatch whole = Stopwatch.StartNew();
            CallState state = new CallState();
            Dictionary<string, object> timings = new Dictionary<string, object>();
            Document document = null;
            Database database = null;
            string reportPath = null;
            int selectedCount = 0;
            int dbmodBefore = -1;
            int dbmodAfter = -1;
            ObjectEventHandler changed = delegate(object sender, ObjectEventArgs args) { ++state.Changes; };
            ObjectErasedEventHandler erased = delegate(object sender, ObjectErasedEventArgs args) { ++state.Changes; };
            bool observing = false;
            try
            {
                TypedValue[] values = arguments == null ? new TypedValue[0] : arguments.AsArray();
                if (values.Length != 7) throw new ArgumentException("ELNETCOLD76 expects exactly seven flat arguments.");
                SelectionSet selection = values[0].Value as SelectionSet;
                if (selection == null) throw new ArgumentException("The first argument must be a SelectionSet.");
                if (!(values[1].Value is ObjectId)) throw new ArgumentException("The panel argument must be an ObjectId.");
                ObjectId panel = (ObjectId)values[1].Value;
                string rootsText = values[2].Value as string;
                if (String.IsNullOrWhiteSpace(rootsText)) throw new ArgumentException("Root handles are required.");
                double deviceTolerance = Number(values[3].Value, "device tolerance");
                double dmax = Number(values[4].Value, "Dmax");
                double boundaryTolerance = Number(values[5].Value, "boundary tolerance");
                if (dmax <= 0.0) throw new ArgumentException("Dmax must be positive.");
                reportPath = values[6].Value as string;
                if (String.IsNullOrWhiteSpace(reportPath)) throw new ArgumentException("A report path is required.");
                reportPath = Path.GetFullPath(reportPath);
                if (!Directory.Exists(Path.GetDirectoryName(reportPath))) throw new DirectoryNotFoundException("The report directory does not exist.");
                document = CadApplication.DocumentManager.MdiActiveDocument;
                if (document == null) throw new InvalidOperationException("No active document.");
                database = document.Database;
                dbmodBefore = Convert.ToInt32(CadApplication.GetSystemVariable("DBMOD"), CultureInfo.InvariantCulture);
                ObjectId[] ids = selection.GetObjectIds();
                selectedCount = ids.Length;
                state.Panel = panel.Handle.ToString();
                List<string> roots = new List<string>();
                foreach (string entry in rootsText.Split(','))
                {
                    string root = entry.Trim();
                    if (root.Length == 0 || !IsHandle(root)) throw new ArgumentException("Invalid root handle.");
                    if (!roots.Contains(root)) roots.Add(root);
                }
                timings["argument-selection-ms"] = whole.Elapsed.TotalMilliseconds;
                database.ObjectModified += changed;
                database.ObjectAppended += changed;
                database.ObjectErased += erased;
                observing = true;
                Stopwatch phase = Stopwatch.StartNew();
                using (Transaction transaction = database.TransactionManager.StartTransaction())
                {
                    BlockTable table = (BlockTable)transaction.GetObject(database.BlockTableId, OpenMode.ForRead);
                    ObjectId model = table[BlockTableRecord.ModelSpace];
                    RegAppTable applications = (RegAppTable)transaction.GetObject(database.RegAppTableId, OpenMode.ForRead);
                    bool markerRegistered = applications.Has("EL_FIXED_V1");
                    Entity panelEntity = transaction.GetObject(panel, OpenMode.ForRead) as Entity;
                    if (!(panelEntity is BlockReference) || panelEntity.OwnerId != model || (markerRegistered && IsManaged(panelEntity)))
                        throw new InvalidOperationException("The panel must be an unmanaged model-space block reference.");
                    foreach (ObjectId id in ids)
                    {
                        string handle = "";
                        try
                        {
                            handle = id.Handle.ToString();
                            Entity entity = transaction.GetObject(id, OpenMode.ForRead) as Entity;
                            if (entity == null || entity.OwnerId != model)
                                throw new InvalidOperationException("Selection contains a non-model-space entity.");
                            if (markerRegistered && IsManaged(entity)) { ++state.Managed; continue; }
                            BlockReference block = entity as BlockReference;
                            Line line = entity as Line;
                            Polyline polyline = entity as Polyline;
                            if (block != null)
                            {
                                ++state.Inserts;
                                Bounds3 bounds = ReadBounds(entity, state);
                                ObjectId definitionId = block.IsDynamicBlock ? block.DynamicBlockTableRecord : block.BlockTableRecord;
                                BlockTableRecord definition = (BlockTableRecord)transaction.GetObject(definitionId, OpenMode.ForRead);
                                state.Blocks.Add(new Block { Handle = handle, Bounds = bounds, EffectiveName = definition.Name, Position = Point(block.Position) });
                                if (state.Samples.Count < 16) state.Samples.Add(new Sample { Handle = handle, Bounds = bounds });
                            }
                            else if (line != null)
                            {
                                ++state.Lines;
                                Point3 a = Point(line.StartPoint);
                                Point3 b = Point(line.EndPoint);
                                AddWire(state, handle, Bounds3.Union(Bounds3.At(a), Bounds3.At(b)), new Point3[] { a, b }, new double[] { 0.0, 0.0 }, false);
                            }
                            else if (polyline != null)
                            {
                                ++state.Polylines;
                                int count = polyline.NumberOfVertices;
                                state.Vertices += count;
                                if (count < 2) throw new InvalidOperationException("A polyline has fewer than two vertices.");
                                Point3[] points = new Point3[count];
                                double[] bulges = new double[count];
                                for (int vertex = 0; vertex < count; ++vertex)
                                {
                                    points[vertex] = Point(polyline.GetPoint3dAt(vertex));
                                    bulges[vertex] = polyline.GetBulgeAt(vertex);
                                    Number(bulges[vertex], "bulge", true);
                                    Number(polyline.GetStartWidthAt(vertex), "start width");
                                    Number(polyline.GetEndWidthAt(vertex), "end width");
                                    if (Math.Abs(bulges[vertex]) > 1.0e-12) ++state.CurvedSegments;
                                }
                                Vector3d normal = polyline.Normal;
                                if (normal.X != 0.0 || normal.Y != 0.0 || normal.Z != 1.0) ++state.NonDefaultNormals;
                                bool closed = polyline.Closed;
                                if (closed) ++state.Closed;
                                AddWire(state, handle, ReadBounds(entity, state), points, bulges, closed);
                            }
                            else
                            {
                                ++state.Other;
                                throw new NotSupportedException("The selection contains an unsupported entity type: " + entity.GetType().Name);
                            }
                        }
                        catch (System.Exception error) { state.Error(handle, "entity-read", error); }
                    }
                    // Deliberately no Commit: all objects were opened ForRead.
                }
                timings["read-ms"] = phase.Elapsed.TotalMilliseconds;
                if (state.ErrorCount == 0)
                {
                    phase.Restart();
                    List<SpatialItem> wireItems = new List<SpatialItem>(state.Wires.Count);
                    List<SpatialItem> blockItems = new List<SpatialItem>(state.Blocks.Count);
                    List<SpatialItem> endItems = new List<SpatialItem>(state.Ends.Count);
                    for (int index = 0; index < state.Wires.Count; ++index)
                        wireItems.Add(Item(index, "\"" + state.Wires[index].Handle + "\"", state.Wires[index].Bounds));
                    for (int index = 0; index < state.Blocks.Count; ++index)
                        blockItems.Add(Item(index, "\"" + state.Blocks[index].Handle + "\"", state.Blocks[index].Bounds));
                    for (int index = 0; index < state.Ends.Count; ++index)
                    {
                        Endpoint end = state.Ends[index];
                        endItems.Add(new SpatialItem(index, "(\"" + state.Wires[end.WireIndex].Handle + "\" " + end.Side + ")", end.Point, Bounds3.At(end.Point)));
                    }
                    // Expand index envelopes once so ray queries also include tolerance
                    // corridors. Coarse work may retain extra objects; it must not prune
                    // nearby objects by an infinitesimally thin endpoint ray.
                    double corridor = Math.Max(deviceTolerance, boundaryTolerance) + SpatialIndex.GapEpsilon;
                    for (int index = 0; index < wireItems.Count; ++index)
                        wireItems[index] = Expanded(wireItems[index], corridor);
                    for (int index = 0; index < blockItems.Count; ++index)
                        blockItems[index] = Expanded(blockItems[index], corridor);
                    for (int index = 0; index < endItems.Count; ++index)
                        endItems[index] = Expanded(endItems[index], corridor);
                    SpatialIndex wireTree = SpatialIndex.Build(wireItems, 0);
                    SpatialIndex blockTree = SpatialIndex.Build(blockItems, 0);
                    SpatialIndex endTree = SpatialIndex.Build(endItems, 0);
                    timings["index-ms"] = phase.Elapsed.TotalMilliseconds;
                    phase.Restart();
                    Trace(state, roots, wireTree, blockTree, endTree, Math.Max(deviceTolerance, boundaryTolerance), dmax);
                    timings["coarse-trace-ms"] = phase.Elapsed.TotalMilliseconds;
                }
                if (!Object.ReferenceEquals(document, CadApplication.DocumentManager.MdiActiveDocument) ||
                    !Object.ReferenceEquals(database, document.Database) || state.Changes != 0)
                    throw new InvalidOperationException("SOURCE_CHANGED during the read-only probe.");
            }
            catch (System.Exception error) { state.Error(state.Panel ?? "", "probe", error); }
            finally
            {
                if (observing)
                {
                    database.ObjectModified -= changed;
                    database.ObjectAppended -= changed;
                    database.ObjectErased -= erased;
                }
                try { dbmodAfter = Convert.ToInt32(CadApplication.GetSystemVariable("DBMOD"), CultureInfo.InvariantCulture); }
                catch (System.Exception) { }
            }
            if (dbmodBefore >= 0 && dbmodAfter >= 0 && dbmodBefore != dbmodAfter)
                state.Error(state.Panel ?? "", "source-guard", new InvalidOperationException("SOURCE_CHANGED: DBMOD changed during the read-only probe."));
            state.Metrics["selected"] = selectedCount;
            state.Metrics["managed-skipped"] = state.Managed;
            state.Metrics["block-references"] = state.Inserts;
            state.Metrics["lines"] = state.Lines;
            state.Metrics["polylines"] = state.Polylines;
            state.Metrics["other"] = state.Other;
            state.Metrics["wire-records"] = state.Wires.Count;
            state.Metrics["block-records"] = state.Blocks.Count;
            state.Metrics["endpoints"] = state.Ends.Count;
            state.Metrics["polyline-vertices-read"] = state.Vertices;
            state.Metrics["closed-polylines"] = state.Closed;
            state.Metrics["curved-segments"] = state.CurvedSegments;
            state.Metrics["non-default-polyline-normals"] = state.NonDefaultNormals;
            state.Metrics["unsupported-bounds"] = state.BoundsErrors;
            state.Metrics["error-count"] = state.ErrorCount;
            state.Metrics["source-change-events"] = state.Changes;
            Dictionary<string, object> report = Row(
                "schema", "EL_NET_COLD_PROBE_V1", "date", "2026-10-22", "status", state.Status,
                "complete-recognition", false, "readonly", true, "result-cache", false,
                "production-result-substitution", false, "production-equivalence-verified", false,
                "coarse-candidates-are-connectivity", false,
                "selection-policy", "caller-preset-selection-superset", "business-filtering", false,
                "scope-note", "No precise contacts, gap validation, numbering, proof, preview or production-result substitution is performed.",
                "panel", state.Panel, "timings", timings, "counts", state.Metrics, "errors", state.Errors,
                "trace-limit-reached", state.Limited, "dbmod-before", dbmodBefore, "dbmod-after", dbmodAfter,
                "goal-ms", 3000, "goal-scope", "managed-coarse-stage-only", "complete-goal-achieved", false,
                "final-report-write-in-timings", false, "report-path", reportPath);
            List<object> samples = new List<object>();
            foreach (Sample sample in state.Samples)
                samples.Add(Row("handle", sample.Handle, "min", Coordinates(sample.Bounds.Min), "max", Coordinates(sample.Bounds.Max)));
            report["block-bounds-samples"] = samples;
            Stopwatch reporting = Stopwatch.StartNew();
            Json(report);
            timings["report-serialization-sample-ms"] = reporting.Elapsed.TotalMilliseconds;
            timings["managed-total-before-final-report-ms"] = whole.Elapsed.TotalMilliseconds;
            report["managed-stage-under-goal"] = state.ErrorCount == 0 && whole.Elapsed.TotalMilliseconds < 3000.0;
            string json = Json(report);
            if (reportPath != null)
            {
                try { File.WriteAllText(reportPath, json, new UTF8Encoding(false)); }
                catch (System.Exception error)
                {
                    state.Error("", "report-write", error);
                    report["status"] = state.Status;
                    state.Metrics["error-count"] = state.ErrorCount;
                    json = Json(report);
                }
            }
            List<TypedValue> output = new List<TypedValue>();
            output.Add(new TypedValue((int)LispDataType.ListBegin));
            output.Add(new TypedValue((int)LispDataType.Text, json));
            output.Add(new TypedValue((int)LispDataType.ListBegin));
            foreach (Sample sample in state.Samples)
            {
                output.Add(new TypedValue((int)LispDataType.ListBegin));
                output.Add(new TypedValue((int)LispDataType.Text, sample.Handle));
                output.Add(new TypedValue((int)LispDataType.Point3d, NativePoint(sample.Bounds.Min)));
                output.Add(new TypedValue((int)LispDataType.Point3d, NativePoint(sample.Bounds.Max)));
                output.Add(new TypedValue((int)LispDataType.ListEnd));
            }
            output.Add(new TypedValue((int)LispDataType.ListEnd));
            output.Add(new TypedValue((int)LispDataType.ListEnd));
            return new ResultBuffer(output.ToArray());
        }

        private static void AddWire(CallState state, string handle, Bounds3 bounds, Point3[] points, double[] bulges, bool closed)
        {
            int index = state.Wires.Count;
            Wire wire = new Wire { Handle = handle, Bounds = bounds };
            if (!closed)
            {
                Endpoint start = MakeEnd(index, "START", points, bulges, false);
                Endpoint end = MakeEnd(index, "END", points, bulges, true);
                wire.Ends.Add(start); wire.Ends.Add(end);
                state.Ends.Add(start); state.Ends.Add(end);
            }
            state.WireHandles.Add(handle, index);
            state.Wires.Add(wire);
        }

        private static Endpoint MakeEnd(int wire, string side, Point3[] points, double[] bulges, bool reverse)
        {
            int vertex = reverse ? points.Length - 1 : 0;
            int step = reverse ? -1 : 1;
            Point3 p = points[vertex];
            int next = vertex + step;
            while (next >= 0 && next < points.Length && Distance(p, points[next]) < 1.0e-9) next += step;
            Endpoint end = new Endpoint { WireIndex = wire, Side = side, Point = p };
            if (next >= 0 && next < points.Length)
            {
                Point3 q = points[next];
                double length = Distance(p, q);
                end.Direction = new Point3((p.X - q.X) / length, (p.Y - q.Y) / length, (p.Z - q.Z) / length);
                int bulgeIndex = reverse ? next : next - 1;
                end.RayEligible = Math.Abs(bulges[bulgeIndex]) <= 1.0e-12;
            }
            return end;
        }

        private static void Trace(CallState state, List<string> roots, SpatialIndex wires, SpatialIndex blocks, SpatialIndex ends, double tolerance, double dmax)
        {
            const long hitLimit = 2000000;
            const int objectLimit = 50000;
            Queue<int> queue = new Queue<int>();
            HashSet<int> seenWires = new HashSet<int>();
            HashSet<int> seenBlocks = new HashSet<int>();
            foreach (string handle in roots)
            {
                int wire;
                if (!state.WireHandles.TryGetValue(handle, out wire)) throw new InvalidOperationException("Root wire missing from the new selection: " + handle);
                if (seenWires.Add(wire)) queue.Enqueue(wire);
            }
            long hits = 0;
            long queries = 0;
            int processed = 0;
            while (queue.Count > 0)
            {
                int code = queue.Dequeue();
                ++processed;
                Bounds3 bounds = code >= 0 ? state.Wires[code].Bounds : state.Blocks[-code - 1].Bounds;
                int[] nearWires = wires.QueryBox(bounds, tolerance);
                int[] nearBlocks = blocks.QueryBox(bounds, tolerance);
                int[] nearEnds = ends.QueryBox(bounds, tolerance);
                queries += 3;
                hits += nearWires.Length + nearBlocks.Length + nearEnds.Length;
                AddWires(nearWires, queue, seenWires);
                AddBlocks(nearBlocks, queue, seenBlocks);
                foreach (int endpoint in nearEnds)
                {
                    int wire = state.Ends[endpoint].WireIndex;
                    if (seenWires.Add(wire)) queue.Enqueue(wire);
                }
                if (code >= 0)
                {
                    foreach (Endpoint endpoint in state.Wires[code].Ends)
                    {
                        if (!endpoint.RayEligible) continue;
                        int[] rayWires = wires.QueryRay(endpoint.Point, endpoint.Direction, dmax);
                        int[] rayBlocks = blocks.QueryRay(endpoint.Point, endpoint.Direction, dmax);
                        int[] rayEnds = ends.QueryRay(endpoint.Point, endpoint.Direction, dmax);
                        queries += 3;
                        hits += rayWires.Length + rayBlocks.Length + rayEnds.Length;
                        AddWires(rayWires, queue, seenWires);
                        AddBlocks(rayBlocks, queue, seenBlocks);
                        foreach (int endpointIndex in rayEnds)
                        {
                            int wire = state.Ends[endpointIndex].WireIndex;
                            if (seenWires.Add(wire)) queue.Enqueue(wire);
                        }
                    }
                }
                if (hits > hitLimit || (processed >= objectLimit && queue.Count > 0))
                {
                    state.Limited = true;
                    state.Error("", "coarse-trace", new InvalidOperationException("Coarse candidate expansion reached its explicit safety limit; no complete result is claimed."));
                    break;
                }
            }
            state.Metrics["coarse-candidate-wires"] = seenWires.Count;
            state.Metrics["coarse-candidate-blocks"] = seenBlocks.Count;
            state.Metrics["coarse-processed-objects"] = processed;
            state.Metrics["coarse-query-count"] = queries;
            state.Metrics["coarse-query-hits"] = hits;
            state.Metrics["coarse-hit-limit"] = hitLimit;
            state.Metrics["coarse-object-limit"] = objectLimit;
        }

        private static void AddWires(int[] candidates, Queue<int> queue, HashSet<int> seen)
        { foreach (int candidate in candidates) if (seen.Add(candidate)) queue.Enqueue(candidate); }
        private static void AddBlocks(int[] candidates, Queue<int> queue, HashSet<int> seen)
        { foreach (int candidate in candidates) if (seen.Add(candidate)) queue.Enqueue(-candidate - 1); }
        private static Bounds3 ReadBounds(Entity entity, CallState state)
        {
            try
            {
                Extents3d extents = entity.GeometricExtents;
                return new Bounds3(Point(extents.MinPoint), Point(extents.MaxPoint));
            }
            catch (System.Exception) { ++state.BoundsErrors; throw; }
        }
        private static bool IsManaged(Entity entity)
        { using (ResultBuffer data = entity.GetXDataForApplication("EL_FIXED_V1")) { return data != null; } }
        private static SpatialItem Item(int index, string key, Bounds3 bounds)
        { return new SpatialItem(index, key, new Point3((bounds.Min.X + bounds.Max.X) / 2.0, (bounds.Min.Y + bounds.Max.Y) / 2.0, (bounds.Min.Z + bounds.Max.Z) / 2.0), bounds); }
        private static SpatialItem Expanded(SpatialItem item, double margin)
        {
            Bounds3 bounds = item.Bounds.Value;
            Bounds3 expanded = new Bounds3(new Point3(bounds.Min.X - margin, bounds.Min.Y - margin, bounds.Min.Z - margin),
                new Point3(bounds.Max.X + margin, bounds.Max.Y + margin, bounds.Max.Z + margin));
            return new SpatialItem(item.SourceIndex, item.KeySignature, item.Point, expanded);
        }
        private static Point3 Point(Point3d point)
        { Number(point.X, "point X", true); Number(point.Y, "point Y", true); Number(point.Z, "point Z", true); return new Point3(point.X, point.Y, point.Z); }
        private static Point3d NativePoint(Point3 point) { return new Point3d(point.X, point.Y, point.Z); }
        private static double[] Coordinates(Point3 point) { return new double[] { point.X, point.Y, point.Z }; }
        private static double Distance(Point3 a, Point3 b) { double x = a.X - b.X, y = a.Y - b.Y, z = a.Z - b.Z; return Math.Sqrt(x * x + y * y + z * z); }
        private static double Number(object value, string name) { return Number(value, name, false); }
        private static double Number(object value, string name, bool signed)
        {
            if (!(value is double) && !(value is int) && !(value is short) && !(value is long)) throw new ArgumentException("Invalid " + name + ".");
            double result = Convert.ToDouble(value, CultureInfo.InvariantCulture);
            if (Double.IsNaN(result) || Double.IsInfinity(result) || Math.Abs(result) >= 1.0e100 || (!signed && result < 0.0)) throw new ArgumentException("Invalid " + name + ".");
            return result;
        }
        private static bool IsHandle(string value)
        { foreach (char c in value) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false; return value.Length > 0 && value.Length <= 16; }
        private static string BoundedMessage(System.Exception error)
        { string message = error.Message ?? ""; return message.Length <= 1024 ? message : message.Substring(0, 1024); }
        private static Dictionary<string, object> Row(params object[] values)
        { Dictionary<string, object> row = new Dictionary<string, object>(); for (int i = 0; i < values.Length; i += 2) row.Add((string)values[i], values[i + 1]); return row; }
        private static string Json(object value)
        { StringBuilder output = new StringBuilder(); JsonValue(output, value); return output.ToString(); }
        private static void JsonValue(StringBuilder output, object value)
        {
            if (value == null) { output.Append("null"); return; }
            string text = value as string;
            if (text != null)
            {
                output.Append('"');
                foreach (char c in text)
                {
                    if (c == '"' || c == '\\') { output.Append('\\'); output.Append(c); }
                    else if (c < 32) { output.Append("\\u"); output.Append(((int)c).ToString("x4", CultureInfo.InvariantCulture)); }
                    else output.Append(c);
                }
                output.Append('"'); return;
            }
            if (value is bool) { output.Append((bool)value ? "true" : "false"); return; }
            IDictionary dictionary = value as IDictionary;
            if (dictionary != null)
            {
                output.Append('{'); bool first = true;
                foreach (DictionaryEntry entry in dictionary)
                { if (!first) output.Append(','); first = false; JsonValue(output, (string)entry.Key); output.Append(':'); JsonValue(output, entry.Value); }
                output.Append('}'); return;
            }
            IEnumerable sequence = value as IEnumerable;
            if (sequence != null)
            {
                output.Append('['); bool first = true;
                foreach (object item in sequence) { if (!first) output.Append(','); first = false; JsonValue(output, item); }
                output.Append(']'); return;
            }
            if (value is double) output.Append(((double)value).ToString("R", CultureInfo.InvariantCulture));
            else output.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
        }
    }
}
