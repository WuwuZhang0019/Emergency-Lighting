// Date: 2026-10-22. Native identity snapshots replace managed-wrapper reference checks.
using System;
using EmergencyLighting.ColdRecognition.Core;

namespace EmergencyLighting.ColdRecognition.Tests
{
    public static class SourceGuardTests
    {
        // Each getter creates a new wrapper around the same simulated native object.
        // This reproduces the distinction between CLR identity and native identity.
        private sealed class Wrapper
        {
            public readonly IntPtr NativeIdentity;

            public Wrapper(long identity) { NativeIdentity = new IntPtr(identity); }
        }

        public static int Run()
        {
            FreshWrappersWithStableNativeIdentity();
            DocumentChange();
            DatabaseChange();
            MissingIdentity();
            EventsRemainBlocking();
            DbmodChangeAndUnreadableValues();
            AggregateIndependentReasons();
            PerCallIsolation();
            return 8;
        }

        private static void FreshWrappersWithStableNativeIdentity()
        {
            Wrapper documentBefore = new Wrapper(1001);
            Wrapper documentAfter = new Wrapper(1001);
            Wrapper databaseBefore = new Wrapper(2001);
            Wrapper databaseAfter = new Wrapper(2001);
            Require(!Object.ReferenceEquals(documentBefore, documentAfter), "document wrappers differ");
            Require(!Object.ReferenceEquals(databaseBefore, databaseAfter), "database wrappers differ");
            SourceIdentity before = new SourceIdentity(documentBefore.NativeIdentity, databaseBefore.NativeIdentity);
            SourceIdentity after = new SourceIdentity(documentAfter.NativeIdentity, databaseAfter.NativeIdentity);
            AssertReasons(before, after, 0, 20, 20);
            AssertReasons(before, after, 0, 0, 0);
        }

        private static void DocumentChange()
        {
            AssertReasons(Identity(1001, 2001), Identity(1002, 2001), 0, 20, 20,
                "DOCUMENT_IDENTITY_CHANGED");
        }

        private static void DatabaseChange()
        {
            AssertReasons(Identity(1001, 2001), Identity(1001, 2002), 0, 20, 20,
                "DATABASE_IDENTITY_CHANGED");
        }

        private static void MissingIdentity()
        {
            AssertReasons(Identity(0, 2001), Identity(1001, 2001), 0, 20, 20,
                "DOCUMENT_IDENTITY_BEFORE_MISSING");
            AssertReasons(Identity(1001, 2001), Identity(0, 2001), 0, 20, 20,
                "DOCUMENT_IDENTITY_AFTER_MISSING");
            AssertReasons(Identity(1001, 0), Identity(1001, 2001), 0, 20, 20,
                "DATABASE_IDENTITY_BEFORE_MISSING");
            AssertReasons(Identity(1001, 2001), Identity(1001, 0), 0, 20, 20,
                "DATABASE_IDENTITY_AFTER_MISSING");
            // Two absent identities must not look like an unchanged source.
            AssertReasons(default(SourceIdentity), default(SourceIdentity), 0, 20, 20,
                "DOCUMENT_IDENTITY_BEFORE_MISSING", "DOCUMENT_IDENTITY_AFTER_MISSING",
                "DATABASE_IDENTITY_BEFORE_MISSING", "DATABASE_IDENTITY_AFTER_MISSING");
        }

        private static void EventsRemainBlocking()
        {
            SourceIdentity identity = Identity(1001, 2001);
            AssertReasons(identity, identity, 1, 20, 20, "DATABASE_EVENTS_OBSERVED");
            AssertReasons(identity, identity, 1234, 20, 20, "DATABASE_EVENTS_OBSERVED");
            AssertReasons(identity, identity, -1, 20, 20, "DATABASE_EVENTS_OBSERVED");
        }

        private static void DbmodChangeAndUnreadableValues()
        {
            SourceIdentity identity = Identity(1001, 2001);
            AssertReasons(identity, identity, 0, 20, 21, "DBMOD_CHANGED");
            AssertReasons(identity, identity, 0, 20, 0, "DBMOD_CHANGED");
            AssertReasons(identity, identity, 0, -1, 20, "DBMOD_BEFORE_UNREADABLE");
            AssertReasons(identity, identity, 0, 20, -1, "DBMOD_AFTER_UNREADABLE");
            AssertReasons(identity, identity, 0, -1, -1, "DBMOD_BEFORE_UNREADABLE", "DBMOD_AFTER_UNREADABLE");
            AssertReasons(identity, identity, 0, Int32.MinValue, Int32.MinValue,
                "DBMOD_BEFORE_UNREADABLE", "DBMOD_AFTER_UNREADABLE");
        }

        private static void AggregateIndependentReasons()
        {
            AssertReasons(Identity(1001, 2001), Identity(1002, 2002), 7, 20, 21,
                "DOCUMENT_IDENTITY_CHANGED", "DATABASE_IDENTITY_CHANGED", "DATABASE_EVENTS_OBSERVED", "DBMOD_CHANGED");
            AssertReasons(Identity(0, 2001), Identity(1002, 0), 1, -1, -1,
                "DOCUMENT_IDENTITY_BEFORE_MISSING", "DATABASE_IDENTITY_AFTER_MISSING", "DATABASE_EVENTS_OBSERVED",
                "DBMOD_BEFORE_UNREADABLE", "DBMOD_AFTER_UNREADABLE");
        }

        private static void PerCallIsolation()
        {
            SourceIdentity first = Identity(1001, 2001);
            SourceIdentity second = Identity(1002, 2002);
            string[] failure = SourceGuard.Evaluate(first, second, 1, 20, 21);
            Require(failure.Length == 4, "first invocation rejected");
            failure[0] = "caller-owned mutation";
            AssertReasons(first, first, 0, 20, 20);
            AssertReasons(second, second, 0, 0, 0);
            AssertReasons(first, second, 0, 20, 20,
                "DOCUMENT_IDENTITY_CHANGED", "DATABASE_IDENTITY_CHANGED");
            AssertReasons(second, second, 0, 20, 20);
        }

        private static SourceIdentity Identity(long document, long database)
        {
            return new SourceIdentity(new IntPtr(document), new IntPtr(database));
        }

        private static void AssertReasons(SourceIdentity before, SourceIdentity after, int changes,
            int dbmodBefore, int dbmodAfter, params string[] expected)
        {
            string[] actual = SourceGuard.Evaluate(before, after, changes, dbmodBefore, dbmodAfter);
            Require(actual.Length == expected.Length, "reason count: " + String.Join(",", actual));
            for (int i = 0; i < expected.Length; ++i)
                Require(actual[i] == expected[i], "reason order/value at " + i + ": " + actual[i]);
        }

        private static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException("Source guard regression: " + message);
        }
    }
}
