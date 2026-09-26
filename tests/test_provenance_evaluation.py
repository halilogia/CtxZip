import json
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.evaluate_provenance import evaluate_case, load_dataset


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "tests" / "fixtures" / "provenance" / "eval_cases.json"


class ProvenanceEvaluationTests(unittest.TestCase):
    def test_synthetic_case_reports_event_and_claim_attribution_metrics(self):
        dataset = load_dataset(DATASET)
        report = evaluate_case(dataset["cases"][0], DATASET.resolve().parents[1])

        self.assertEqual(report["event_attribution"]["precision"], 1.0)
        self.assertEqual(report["event_attribution"]["recall"], 1.0)
        self.assertTrue(report["event_attribution"]["source_version_reference_valid"])
        self.assertEqual(report["summary_claims"]["supported_claim_precision"], 0.75)
        self.assertEqual(report["summary_claims"]["supported_claim_recall"], 1.0)
        self.assertEqual(report["summary_claims"]["unsupported_included_claims"], 1)
        self.assertEqual(report["claim_source_attribution"]["precision"], 0.5)
        self.assertEqual(report["claim_source_attribution"]["recall"], 2 / 3)
        self.assertEqual(report["git_bound_test_evidence"]["label_accuracy"], 1.0)

    def test_cli_report_labels_evidence_as_synthetic(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "evaluate_provenance.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["evidence_level"], "synthetic-manual-labels")
        self.assertEqual(len(report["cases"]), 1)
        self.assertIn("not a real-session", report["scope_note"])

    def test_rejects_fixture_path_escape(self):
        dataset = load_dataset(DATASET)
        case = dict(dataset["cases"][0], source_fixture="../../README.md")

        with self.assertRaisesRegex(ValueError, "within the fixture root"):
            evaluate_case(case, DATASET.resolve().parents[1])


if __name__ == "__main__":
    unittest.main()
