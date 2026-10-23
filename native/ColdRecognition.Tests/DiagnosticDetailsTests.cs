// Date: 2026-10-22. Actual exception evidence and limits, without CAD runtime.
using System;
using System.Collections.Generic;
using EmergencyLighting.ColdRecognition.Core;

namespace EmergencyLighting.ColdRecognition.Tests
{
    internal static class DiagnosticDetailsTests
    {
        private sealed class CadLikeException : Exception
        {
            public string ErrorStatus { get { return "eInvalidInput"; } }
            public override string StackTrace { get { return new string('S', 5000); } }
            public CadLikeException(string message, Exception inner) : base(message, inner)
            { HResult = unchecked((int)0x80004005); }
        }

        public static int Run()
        {
            ExceptionEvidence();
            BoundedFields();
            BoundedInnerChain();
            PerCallIsolation();
            return 4;
        }

        private static void ExceptionEvidence()
        {
            Dictionary<string, object> error = DiagnosticDetails.Error(new CadLikeException("native failure", null));
            Require((string)error["message"] == "native failure", "original message");
            Require(((string)error["type"]).EndsWith("CadLikeException"), "original type");
            Require((string)error["hresult"] == "0x80004005", "HRESULT hexadecimal");
            Require((string)error["cad-error-status"] == "eInvalidInput", "native status");
            Require(!(bool)error["inner-truncated"], "no absent inner exception");
        }

        private static void BoundedFields()
        {
            Dictionary<string, object> error = DiagnosticDetails.Error(new CadLikeException(new string('M', 2000), null));
            Require(((string)error["message"]).Length == DiagnosticDetails.MessageLimit, "bounded message");
            Require(((string)error["stack"]).Length == DiagnosticDetails.StackLimit, "bounded stack");
            Require(DiagnosticDetails.Bounded(null, 5) == "", "null text");
            Require(DiagnosticDetails.Bounded("short", 5) == "short", "boundary text");
        }

        private static void BoundedInnerChain()
        {
            Exception chain = new InvalidOperationException("leaf");
            for (int i = 0; i < 6; ++i) chain = new CadLikeException("level-" + i, chain);
            Dictionary<string, object> error = DiagnosticDetails.Error(chain);
            List<object> inner = (List<object>)error["inner"];
            Require(inner.Count == DiagnosticDetails.InnerLimit, "bounded inner count");
            Require((bool)error["inner-truncated"], "inner truncation explicit");
            Require((string)((Dictionary<string, object>)inner[0])["message"] == "level-4", "inner order");
            error = DiagnosticDetails.Error(new Exception("outer", new Exception("leaf")));
            Require(((List<object>)error["inner"]).Count == 1 && !(bool)error["inner-truncated"], "short chain preserved");
        }

        private static void PerCallIsolation()
        {
            Dictionary<string, object> first = DiagnosticDetails.Error(new Exception("first"));
            Dictionary<string, object> second = DiagnosticDetails.Error(new Exception("second"));
            first["message"] = "caller mutation";
            Require((string)second["message"] == "second", "independent invocation");
            Require((string)second["stack"] == "", "unthrown stack represented");
        }

        private static void Require(bool condition, string message)
        { if (!condition) throw new InvalidOperationException("Diagnostic regression: " + message); }
    }
}
