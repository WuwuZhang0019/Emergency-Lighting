// Date: 2026-10-22. Per-invocation native identity guard; no AutoCAD runtime dependency.
using System;
using System.Collections.Generic;

namespace EmergencyLighting.ColdRecognition.Core
{
    public struct SourceIdentity
    {
        public readonly IntPtr Document;
        public readonly IntPtr Database;

        public SourceIdentity(IntPtr document, IntPtr database)
        {
            Document = document;
            Database = database;
        }
    }

    public static class SourceGuard
    {
        public static string[] Evaluate(SourceIdentity before, SourceIdentity after,
            int changes, int dbmodBefore, int dbmodAfter)
        {
            List<string> reasons = new List<string>();
            CompareIdentity(before.Document, after.Document, "DOCUMENT", reasons);
            CompareIdentity(before.Database, after.Database, "DATABASE", reasons);
            if (changes != 0) reasons.Add("DATABASE_EVENTS_OBSERVED");
            if (dbmodBefore < 0) reasons.Add("DBMOD_BEFORE_UNREADABLE");
            if (dbmodAfter < 0) reasons.Add("DBMOD_AFTER_UNREADABLE");
            if (dbmodBefore >= 0 && dbmodAfter >= 0 && dbmodBefore != dbmodAfter)
                reasons.Add("DBMOD_CHANGED");
            return reasons.ToArray();
        }

        private static void CompareIdentity(IntPtr before, IntPtr after, string kind,
            List<string> reasons)
        {
            if (before == IntPtr.Zero) reasons.Add(kind + "_IDENTITY_BEFORE_MISSING");
            if (after == IntPtr.Zero) reasons.Add(kind + "_IDENTITY_AFTER_MISSING");
            if (before != IntPtr.Zero && after != IntPtr.Zero && before != after)
                reasons.Add(kind + "_IDENTITY_CHANGED");
        }
    }
}
