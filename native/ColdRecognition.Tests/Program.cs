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
                int count = SpatialIndexTests.Run();
                Console.WriteLine("{\"status\":\"passed\",\"test_groups\":" + count + "}");
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
