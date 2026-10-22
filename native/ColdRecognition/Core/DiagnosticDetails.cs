// Date: 2026-10-22. Bounded exception evidence shared by CAD and offline tests.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;

namespace EmergencyLighting.ColdRecognition.Core
{
    public static class DiagnosticDetails
    {
        public const int MessageLimit = 1024;
        public const int StackLimit = 4096;
        public const int InnerLimit = 3;

        public static Dictionary<string, object> Error(Exception error)
        {
            Dictionary<string, object> result = Single(error);
            List<object> inner = new List<object>();
            Exception current = error.InnerException;
            while (current != null && inner.Count < InnerLimit)
            {
                inner.Add(Single(current));
                current = current.InnerException;
            }
            result["inner"] = inner;
            result["inner-truncated"] = current != null;
            return result;
        }

        public static string Bounded(string value, int limit)
        { return value == null ? "" : value.Length <= limit ? value : value.Substring(0, limit); }

        private static Dictionary<string, object> Single(Exception error)
        {
            string cadStatus = null;
            try
            {
                // AutoCAD's ErrorStatus remains available without making this
                // diagnostic formatter depend on or load Autodesk assemblies.
                PropertyInfo status = error.GetType().GetProperty("ErrorStatus");
                if (status != null) cadStatus = Convert.ToString(status.GetValue(error, null), CultureInfo.InvariantCulture);
            }
            catch (Exception) { cadStatus = "<unavailable>"; }
            return new Dictionary<string, object> {
                { "type", error.GetType().FullName },
                { "message", Bounded(error.Message, MessageLimit) },
                { "hresult", "0x" + error.HResult.ToString("X8", CultureInfo.InvariantCulture) },
                { "cad-error-status", Bounded(cadStatus, 160) },
                { "stack", Bounded(error.StackTrace, StackLimit) }
            };
        }
    }
}
