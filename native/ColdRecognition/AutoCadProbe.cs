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
        private const string DiagnosticRevision = "2026-10-22-logs1";
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
            internal readonly List<object> Stages = new List<object>();
            internal readonly List<string> Roots = new List<string>();
            internal readonly Dictionary<string, int> ErrorGroups = new Dictionary<string, int>();
            internal readonly Stopwatch Clock = Stopwatch.StartNew();
            internal string Phase = "entry";
            internal string EntityType;
            internal string CurrentHandle;
            internal int? CurrentVertex;
            internal string RootInput;

            internal void Stage(string phase)
            {
                Phase = phase;
                if (Stages.Count < 48)
                    Stages.Add(Row("phase", phase, "elapsed-ms", Clock.Elapsed.TotalMilliseconds));
            }
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
                string group = phase + "/" + Phase + "/" + error.GetType().FullName;
                if (ErrorGroups.ContainsKey(group)) ++ErrorGroups[group];
                else if (ErrorGroups.Count < 20) ErrorGroups[group] = 1;
                else
                {
                    const string overflow = "<other-error-groups>";
                    if (!ErrorGroups.ContainsKey(overflow)) ErrorGroups[overflow] = 0;
                    ++ErrorGroups[overflow];
                }
                if (Errors.Count < 10)
                {
                    Dictionary<string, object> details = DiagnosticDetails.Error(error);
                    details["handle"] = handle;
                    details["phase"] = phase;
                    details["step"] = Phase;
                    details["entity-type"] = EntityType;
                    details["vertex-index"] = CurrentVertex;
                    Errors.Add(details);
                }
            }
        }

        // Flat arguments: selection set, panel ObjectId, comma-separated root handles,
        // device tolerance, Dmax, boundary tolerance, existing output folder/file path.
        // Return value: (jsonText ((handle minPoint maxPoint) ...)), at most 16 samples.
        [LispFunction("ELNETCOLD82")]
        public static ResultBuffer Run(ResultBuffer arguments)
        {
            CallState state = null;
            try
            {
                // The same callable entry proves both registration and version.
                // No active document, transaction, geometry or CallState is touched.
                TypedValue[] values = arguments == null ? new TypedValue[0] : arguments.AsArray();
                if (values.Length == 1 && values[0].TypeCode == (int)LispDataType.Text &&
                    String.Equals(values[0].Value as string, "EL_NET_COLD_PING_V1", StringComparison.Ordinal))
                    return new ResultBuffer(new TypedValue((int)LispDataType.Text, "EL_NET_COLD_PROBE_V1/0.1.82"));
                state = new CallState();
                return RunCore(arguments, state);
            }
            catch (System.Exception error)
            {
                // Preserve failures after the normal probe catch, including JSON,
                // final report I/O and ResultBuffer construction. No extra file is created.
                DiagnosticCommandLine("ELNETCOLD82 " + DiagnosticRevision + " failed at "
                    + (state == null ? "entry" : state.Phase) + ": " + error.GetType().FullName
                    + ": " + DiagnosticDetails.Bounded(error.Message, 1024));
                try
                {
                    if (state == null) state = new CallState();
                    state.Error(state.CurrentHandle ?? state.Panel ?? "", "bridge", error);
                    string reportPath = DiagnosticReportPath(arguments);
                    Dictionary<string, object> report = Row("schema", "EL_NET_COLD_PROBE_V1",
                        "date", "2026-10-22", "diagnostic-revision", DiagnosticRevision,
                        "status", "ERROR", "bridge-error", DiagnosticDetails.Error(error),
                        "assembly", AssemblyDiagnostics(), "complete-recognition", false,
                        "readonly", true, "result-cache", false, "last-phase", state.Phase,
                        "stages", state.Stages, "errors", state.Errors, "error-groups", state.ErrorGroups,
                        "report-path", reportPath);
                    string json = Json(report);
                    if (reportPath != null)
                    {
                        try { File.WriteAllText(reportPath, json, new UTF8Encoding(false)); }
                        catch (System.Exception writeError)
                        {
                            report["fallback-report-write-error"] = DiagnosticDetails.Error(writeError);
                            json = Json(report);
                        }
                    }
                    DiagnosticCommandLine("ELNETCOLD82 " + DiagnosticRevision + " failed at " + state.Phase
                        + ": " + error.GetType().FullName + ": " + DiagnosticDetails.Bounded(error.Message, 1024)
                        + (reportPath == null ? " (report path unavailable)" : " | report=" + reportPath));
                    return new ResultBuffer(new TypedValue((int)LispDataType.ListBegin),
                        new TypedValue((int)LispDataType.Text, json),
                        new TypedValue((int)LispDataType.ListBegin), new TypedValue((int)LispDataType.ListEnd),
                        new TypedValue((int)LispDataType.ListEnd));
                }
                catch (System.Exception diagnosticError)
                {
                    DiagnosticCommandLine("ELNETCOLD82 fallback diagnostics failed: "
                        + DiagnosticDetails.Bounded(diagnosticError.Message, 1024)
                        + " | original=" + DiagnosticDetails.Bounded(error.Message, 1024));
                    // Propagate the original probe/bridge failure to the LISP catch,
                    // rather than replacing it with a secondary diagnostic exception.
                    System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(error).Throw();
                    return null;
                }
            }
        }

        private static ResultBuffer RunCore(ResultBuffer arguments, CallState state)
        {
            Stopwatch whole = Stopwatch.StartNew();
            Dictionary<string, object> timings = new Dictionary<string, object>();
            Document document = null;
            Database database = null;
            string reportPath = null;
            int selectedCount = 0;
            int dbmodBefore = -1;
            int dbmodAfter = -1;
            SourceIdentity sourceBefore = default(SourceIdentity);
            SourceIdentity sourceAfter = default(SourceIdentity);
            List<string> sourceReasons = new List<string>();
            bool sourceGuardStarted = false;
            bool sourceGuardRead = false;
            bool? documentWrapperSame = null;
            bool? databaseWrapperSame = null;
            ObjectEventHandler changed = delegate(object sender, ObjectEventArgs args) { ++state.Changes; };
            ObjectErasedEventHandler erased = delegate(object sender, ObjectErasedEventArgs args) { ++state.Changes; };
            bool observing = false;
            try
            {
                state.Stage("arguments-begin");
                TypedValue[] values = arguments == null ? new TypedValue[0] : arguments.AsArray();
                if (values.Length != 7) throw new ArgumentException("ELNETCOLD82 expects exactly seven flat arguments.");
                SelectionSet selection = values[0].Value as SelectionSet;
                if (selection == null) throw new ArgumentException("The first argument must be a SelectionSet.");
                if (!(values[1].Value is ObjectId)) throw new ArgumentException("The panel argument must be an ObjectId.");
                ObjectId panel = (ObjectId)values[1].Value;
                string rootsText = values[2].Value as string;
                state.RootInput = DiagnosticDetails.Bounded(rootsText, 2048);
                if (String.IsNullOrWhiteSpace(rootsText)) throw new ArgumentException("Root handles are required.");
                double deviceTolerance = Number(values[3].Value, "device tolerance");
                double dmax = Number(values[4].Value, "Dmax");
                double boundaryTolerance = Number(values[5].Value, "boundary tolerance");
                if (dmax <= 0.0) throw new ArgumentException("Dmax must be positive.");
                reportPath = values[6].Value as string;
                if (String.IsNullOrWhiteSpace(reportPath)) throw new ArgumentException("A report path is required.");
                reportPath = Path.GetFullPath(reportPath);
                if (!Directory.Exists(Path.GetDirectoryName(reportPath))) throw new DirectoryNotFoundException("The report directory does not exist.");
                state.Stage("source-guard-before");
                document = CadApplication.DocumentManager.MdiActiveDocument;
                if (document == null) throw new InvalidOperationException("No active document.");
                database = document.Database;
                sourceBefore = SourceIdentityOf(document, database);
                if (sourceBefore.Document == IntPtr.Zero || sourceBefore.Database == IntPtr.Zero)
                    throw new InvalidOperationException("SOURCE_IDENTITY_UNAVAILABLE before the read-only probe.");
                dbmodBefore = Convert.ToInt32(CadApplication.GetSystemVariable("DBMOD"), CultureInfo.InvariantCulture);
                sourceGuardStarted = true;
                ObjectId[] ids = selection.GetObjectIds();
                selectedCount = ids.Length;
                state.Panel = panel.Handle.ToString();
                List<string> roots = state.Roots;
                foreach (string entry in rootsText.Split(','))
                {
                    string root = entry.Trim();
                    if (root.Length == 0 || !IsHandle(root)) throw new ArgumentException("Invalid root handle.");
                    if (!roots.Contains(root)) roots.Add(root);
                }
                state.Metrics["device-tolerance"] = deviceTolerance;
                state.Metrics["Dmax"] = dmax;
                state.Metrics["boundary-tolerance"] = boundaryTolerance;
                state.Metrics["root-count"] = roots.Count;
                state.Stage("arguments-complete");
                timings["argument-selection-ms"] = whole.Elapsed.TotalMilliseconds;
                database.ObjectModified += changed;
                database.ObjectAppended += changed;
                database.ObjectErased += erased;
                observing = true;
                Stopwatch phase = Stopwatch.StartNew();
                state.Stage("entity-read-begin");
                using (Transaction transaction = database.TransactionManager.StartTransaction())
                {
                    state.Phase = "transaction-model-space";
                    BlockTable table = (BlockTable)transaction.GetObject(database.BlockTableId, OpenMode.ForRead);
                    ObjectId model = table[BlockTableRecord.ModelSpace];
                    RegAppTable applications = (RegAppTable)transaction.GetObject(database.RegAppTableId, OpenMode.ForRead);
                    bool markerRegistered = applications.Has("EL_FIXED_V1");
                    state.Phase = "panel-validation";
                    Entity panelEntity = transaction.GetObject(panel, OpenMode.ForRead) as Entity;
                    if (!(panelEntity is BlockReference) || panelEntity.OwnerId != model || (markerRegistered && IsManaged(panelEntity)))
                        throw new InvalidOperationException("The panel must be an unmanaged model-space block reference.");
                    foreach (ObjectId id in ids)
                    {
                        string handle = "";
                        state.EntityType = null;
                        state.CurrentHandle = null;
                        state.CurrentVertex = null;
                        try
                        {
                            state.Phase = "entity-handle";
                            handle = id.Handle.ToString();
                            state.CurrentHandle = handle;
                            state.Phase = "entity-open";
                            Entity entity = transaction.GetObject(id, OpenMode.ForRead) as Entity;
                            state.EntityType = entity == null ? null : entity.GetType().FullName;
                            state.Phase = "entity-owner";
                            if (entity == null || entity.OwnerId != model)
                                throw new InvalidOperationException("Selection contains a non-model-space entity.");
                            state.Phase = "entity-managed-marker";
                            if (markerRegistered && IsManaged(entity)) { ++state.Managed; continue; }
                            BlockReference block = entity as BlockReference;
                            Line line = entity as Line;
                            Polyline polyline = entity as Polyline;
                            if (block != null)
                            {
                                ++state.Inserts;
                                state.Phase = "block-extents";
                                Bounds3 bounds = ReadBounds(entity, state);
                                state.Phase = "block-definition";
                                ObjectId definitionId = block.IsDynamicBlock ? block.DynamicBlockTableRecord : block.BlockTableRecord;
                                BlockTableRecord definition = (BlockTableRecord)transaction.GetObject(definitionId, OpenMode.ForRead);
                                state.Phase = "block-position-record";
                                state.Blocks.Add(new Block { Handle = handle, Bounds = bounds, EffectiveName = definition.Name, Position = Point(block.Position) });
                                if (state.Samples.Count < 16) state.Samples.Add(new Sample { Handle = handle, Bounds = bounds });
                            }
                            else if (line != null)
                            {
                                ++state.Lines;
                                state.Phase = "line-points";
                                Point3 a = Point(line.StartPoint);
                                Point3 b = Point(line.EndPoint);
                                state.Phase = "line-endpoints-record";
                                AddWire(state, handle, Bounds3.Union(Bounds3.At(a), Bounds3.At(b)), new Point3[] { a, b }, new double[] { 0.0, 0.0 }, false);
                            }
                            else if (polyline != null)
                            {
                                ++state.Polylines;
                                state.Phase = "polyline-vertex-count";
                                int count = polyline.NumberOfVertices;
                                state.Vertices += count;
                                if (count < 2) throw new InvalidOperationException("A polyline has fewer than two vertices.");
                                Point3[] points = new Point3[count];
                                double[] bulges = new double[count];
                                for (int vertex = 0; vertex < count; ++vertex)
                                {
                                    state.CurrentVertex = vertex;
                                    state.Phase = "polyline-vertex-point";
                                    points[vertex] = Point(polyline.GetPoint3dAt(vertex));
                                    state.Phase = "polyline-vertex-bulge-width";
                                    bulges[vertex] = polyline.GetBulgeAt(vertex);
                                    Number(bulges[vertex], "bulge", true);
                                    Number(polyline.GetStartWidthAt(vertex), "start width");
                                    Number(polyline.GetEndWidthAt(vertex), "end width");
                                    if (Math.Abs(bulges[vertex]) > 1.0e-12) ++state.CurvedSegments;
                                }
                                state.CurrentVertex = null;
                                state.Phase = "polyline-normal-closed";
                                Vector3d normal = polyline.Normal;
                                if (normal.X != 0.0 || normal.Y != 0.0 || normal.Z != 1.0) ++state.NonDefaultNormals;
                                bool closed = polyline.Closed;
                                if (closed) ++state.Closed;
                                state.Phase = "polyline-extents";
                                Bounds3 polylineBounds = ReadBounds(entity, state);
                                state.Phase = "polyline-endpoints-record";
                                AddWire(state, handle, polylineBounds, points, bulges, closed);
                            }
                            else
                            {
                                ++state.Other;
                                state.Phase = "entity-supported-type";
                                throw new NotSupportedException("The selection contains an unsupported entity type: " + entity.GetType().Name);
                            }
                        }
                        catch (System.Exception error) { state.Error(handle, "entity-read", error); }
                    }
                    state.CurrentHandle = null;
                    state.EntityType = null;
                    state.CurrentVertex = null;
                    state.Phase = "transaction-dispose";
                    // Deliberately no Commit: all objects were opened ForRead.
                }
                timings["read-ms"] = phase.Elapsed.TotalMilliseconds;
                state.CurrentHandle = null;
                state.EntityType = null;
                state.CurrentVertex = null;
                state.Stage("entity-read-complete");
                if (state.ErrorCount == 0)
                {
                    phase.Restart();
                    state.Stage("index-begin");
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
                    state.Stage("index-complete");
                    phase.Restart();
                    state.Stage("coarse-trace-begin");
                    Trace(state, roots, wireTree, blockTree, endTree, Math.Max(deviceTolerance, boundaryTolerance), dmax);
                    timings["coarse-trace-ms"] = phase.Elapsed.TotalMilliseconds;
                    state.Stage("coarse-trace-complete");
                }
            }
            catch (System.Exception error) { state.Error(state.Panel ?? "", "probe", error); }
            finally
            {
                // Date: 2026-10-22. CAD may return another managed wrapper for
                // the same native document/database. Wrapper references are only
                // diagnostics; compare the per-call native identities instead.
                Stopwatch guardTime = Stopwatch.StartNew();
                state.CurrentHandle = null;
                state.EntityType = null;
                state.CurrentVertex = null;
                state.Stage("source-guard-after");
                if (sourceGuardStarted)
                {
                    try
                    {
                        Document current = CadApplication.DocumentManager.MdiActiveDocument;
                        Database currentDatabase = current == null || current.IsDisposed ? null : current.Database;
                        documentWrapperSame = Object.ReferenceEquals(document, current);
                        databaseWrapperSame = Object.ReferenceEquals(database, currentDatabase);
                        sourceAfter = SourceIdentityOf(current, currentDatabase);
                        dbmodAfter = Convert.ToInt32(CadApplication.GetSystemVariable("DBMOD"), CultureInfo.InvariantCulture);
                        sourceGuardRead = true;
                    }
                    catch (System.Exception error)
                    {
                        sourceReasons.Add("SOURCE_GUARD_READ_FAILED");
                        state.Error(state.Panel ?? "", "source-guard-read", error);
                    }
                }
                if (observing)
                {
                    state.Phase = "source-event-unsubscribe";
                    database.ObjectModified -= changed;
                    database.ObjectAppended -= changed;
                    database.ObjectErased -= erased;
                }
                timings["source-guard-ms"] = guardTime.Elapsed.TotalMilliseconds;
                state.Stage("source-guard-read-complete");
            }
            state.Stage("source-guard-evaluate");
            if (sourceGuardStarted)
            {
                sourceReasons.AddRange(SourceGuard.Evaluate(sourceBefore, sourceAfter, state.Changes, dbmodBefore, dbmodAfter));
                if (sourceReasons.Count != 0)
                    state.Error(state.Panel ?? "", "source-guard", new InvalidOperationException(
                        "SOURCE_CHANGED_OR_UNVERIFIED: " + String.Join(",", sourceReasons)));
            }
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
            state.Stage("report-build");
            Dictionary<string, object> report = Row(
                "schema", "EL_NET_COLD_PROBE_V1", "date", "2026-10-22", "status", state.Status,
                // Keep original error messages before verbose geometry/stages in bounded LISP logs.
                "errors", state.Errors,
                "diagnostic-revision", DiagnosticRevision, "assembly", AssemblyDiagnostics(),
                "stages", state.Stages, "stage-record-limit", 48,
                "error-groups", state.ErrorGroups, "errors-truncated", state.ErrorCount > state.Errors.Count,
                "root-input", state.RootInput, "root-diagnostics", RootDiagnostics(state),
                "complete-recognition", false, "readonly", true, "result-cache", false,
                "production-result-substitution", false, "production-equivalence-verified", false,
                "coarse-candidates-are-connectivity", false,
                "selection-policy", "caller-preset-selection-superset", "business-filtering", false,
                "scope-note", "No precise contacts, gap validation, numbering, proof, preview or production-result substitution is performed.",
                "panel", state.Panel, "timings", timings, "counts", state.Metrics,
                "trace-limit-reached", state.Limited, "dbmod-before", dbmodBefore, "dbmod-after", dbmodAfter,
                "source-guard", Row("scheme", "native-document-database-identity-v1",
                    "started", sourceGuardStarted, "completed", sourceGuardRead, "reasons", sourceReasons,
                    "document-before-valid", sourceBefore.Document != IntPtr.Zero,
                    "document-after-valid", sourceAfter.Document != IntPtr.Zero,
                    "database-before-valid", sourceBefore.Database != IntPtr.Zero,
                    "database-after-valid", sourceAfter.Database != IntPtr.Zero,
                    "document-native-same", sourceBefore.Document != IntPtr.Zero && sourceBefore.Document == sourceAfter.Document,
                    "database-native-same", sourceBefore.Database != IntPtr.Zero && sourceBefore.Database == sourceAfter.Database,
                    "document-wrapper-same", documentWrapperSame, "database-wrapper-same", databaseWrapperSame),
                "goal-ms", 3000, "goal-scope", "managed-coarse-stage-only", "complete-goal-achieved", false,
                "final-report-write-in-timings", false, "report-path", reportPath);
            List<object> samples = new List<object>();
            foreach (Sample sample in state.Samples)
                samples.Add(Row("handle", sample.Handle, "min", Coordinates(sample.Bounds.Min), "max", Coordinates(sample.Bounds.Max)));
            report["block-bounds-samples"] = samples;
            Stopwatch reporting = Stopwatch.StartNew();
            state.Stage("report-serialize-sample");
            Json(report);
            timings["report-serialization-sample-ms"] = reporting.Elapsed.TotalMilliseconds;
            timings["managed-total-before-final-report-ms"] = whole.Elapsed.TotalMilliseconds;
            report["managed-stage-under-goal"] = state.ErrorCount == 0 && whole.Elapsed.TotalMilliseconds < 3000.0;
            state.Stage("final-report-write-begin");
            report["last-phase"] = state.Phase;
            string json = Json(report);
            if (reportPath != null)
            {
                try { File.WriteAllText(reportPath, json, new UTF8Encoding(false)); }
                catch (System.Exception error)
                {
                    state.Error("", "report-write", error);
                    DiagnosticCommandLine("ELNETCOLD82 report write failed: " + DiagnosticDetails.Bounded(error.Message, 1024));
                    report["status"] = state.Status;
                    state.Metrics["error-count"] = state.ErrorCount;
                    json = Json(report);
                }
            }
            state.Stage("return-buffer-build");
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

        private static Dictionary<string, object> AssemblyDiagnostics()
        {
            try
            {
                System.Reflection.Assembly assembly = typeof(AutoCadProbe).Assembly;
                return Row("name", assembly.GetName().Name, "version", assembly.GetName().Version.ToString(),
                    "location", assembly.Location, "module-version-id", assembly.ManifestModule.ModuleVersionId.ToString("D"));
            }
            catch (System.Exception error) { return Row("metadata-error", DiagnosticDetails.Error(error)); }
        }

        private static object RootDiagnostics(CallState state)
        {
            const int limit = 32;
            List<object> rows = new List<object>();
            int found = 0;
            foreach (string handle in state.Roots)
            {
                int index;
                bool read = state.WireHandles.TryGetValue(handle, out index);
                if (read) ++found;
                if (rows.Count >= limit) continue;
                Dictionary<string, object> row = Row("handle", handle, "wire-read", read);
                if (read)
                {
                    Wire wire = state.Wires[index];
                    row["min"] = Coordinates(wire.Bounds.Min);
                    row["max"] = Coordinates(wire.Bounds.Max);
                    List<object> ends = new List<object>();
                    foreach (Endpoint end in wire.Ends)
                        ends.Add(Row("side", end.Side, "point", Coordinates(end.Point),
                            "outward-direction", Coordinates(end.Direction), "ray-eligible", end.RayEligible));
                    row["endpoints"] = ends;
                }
                rows.Add(row);
            }
            return Row("requested", state.Roots.Count, "wire-read", found,
                "wire-missing", state.Roots.Count - found, "record-limit", limit,
                "truncated", state.Roots.Count > limit, "items", rows);
        }

        private static string DiagnosticReportPath(ResultBuffer arguments)
        {
            try
            {
                TypedValue[] values = arguments == null ? new TypedValue[0] : arguments.AsArray();
                if (values.Length != 7 || !(values[6].Value is string)) return null;
                string path = Path.GetFullPath((string)values[6].Value);
                return Directory.Exists(Path.GetDirectoryName(path)) ? path : null;
            }
            catch (System.Exception) { return null; }
        }

        private static void DiagnosticCommandLine(string message)
        {
            try
            {
                Document current = CadApplication.DocumentManager.MdiActiveDocument;
                if (current != null && !current.IsDisposed) current.Editor.WriteMessage("\n" + message);
            }
            catch (System.Exception) { /* Diagnostics must not replace the original failure. */ }
        }

        private static SourceIdentity SourceIdentityOf(Document document, Database database)
        {
            // Do not dereference or dispose native pointers. They are valid only
            // as identity tokens within this synchronous, read-only invocation.
            IntPtr documentId = document == null || document.IsDisposed ? IntPtr.Zero : document.UnmanagedObject;
            IntPtr databaseId = database == null || database.IsDisposed ? IntPtr.Zero : database.UnmanagedObject;
            return new SourceIdentity(documentId, databaseId);
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
