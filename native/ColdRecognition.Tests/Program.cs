// Date: 2026-10-22. Offline core regression entry; no AutoCAD runtime dependency.
using System;

namespace EmergencyLighting.ColdRecognition.Tests
{
    internal static class Program
    {
        private static int Main()
        {
            try
            {
                int spatial = SpatialIndexTests.Run();
                int sourceGuard = SourceGuardTests.Run();
                int count = spatial + sourceGuard;
                Console.WriteLine("{\"status\":\"passed\",\"test_groups\":" + count
                    + ",\"spatial_test_groups\":" + spatial + ",\"source_guard_test_groups\":" + sourceGuard + "}");
                return 0;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(error.ToString());
                return 1;
            }
        }
    }
}
