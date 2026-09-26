"""Tests that the synthetic scaling runner covers the retrieval layouts."""
import unittest

from scripts.benchmark_retrieval import run_benchmark


class RetrievalBenchmarkTests(unittest.TestCase):
    def test_small_run_reports_all_source_range_layouts_without_losing_candidates(self):
        report = run_benchmark([8], repeats=1)
        self.assertTrue(report["synthetic"])
        self.assertEqual(
            [item["layout"] for item in report["measurements"]],
            ["unattributed", "many-sessions", "one-session"],
        )
        for measurement in report["measurements"]:
            self.assertEqual(measurement["selected_count"], 8)
            self.assertEqual(measurement["excluded_count"], 0)
            self.assertGreaterEqual(measurement["overlap_median_ms"], 0)


if __name__ == "__main__":
    unittest.main()
