"""Tests the privacy-scrubbed retrieval evaluation harness."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_retrieval import evaluate_case, load_dataset
from scripts.check_staged import content_issues
from ctxzip_core.context_planner import ContextItem
from ctxzip_core.evaluation import compare_planned_context
from ctxzip_core.retrieval import SummaryCandidate, rank_summaries
from ctxzip_core.text import estimate_tokens


class RetrievalEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.dataset_path = ROOT / "tests" / "fixtures" / "retrieval" / "eval_cases.json"
        self.cases = load_dataset(self.dataset_path)

    def test_task_aware_selection_improves_relevant_recall_for_old_context(self):
        result = evaluate_case(self.cases[0])
        self.assertEqual(result["task_aware"]["recall_at_k"], 1.0)
        self.assertEqual(result["recency"]["recall_at_k"], 0.0)
        self.assertEqual(result["task_aware"]["source_coverage"], 1.0)
        self.assertEqual(result["planned_context"]["task_aware"]["selected_ids"], ("old-summary-state",))
        self.assertEqual(result["planned_context"]["recency"]["selected_ids"], ("recent-theme-note",))

    def test_file_and_commit_query_selects_expected_codex_context(self):
        result = evaluate_case(self.cases[1])
        self.assertEqual(result["task_aware"]["selected_ids"], ("codex-parser-summary",))
        self.assertEqual(result["task_aware"]["stale_context_rate"], 0.0)
        self.assertEqual(result["recency"]["stale_context_rate"], 1.0)
        self.assertEqual(result["planned_context"]["task_aware"]["stale_context_rate"], 0.0)
        self.assertEqual(result["planned_context"]["recency"]["stale_context_rate"], 1.0)

    def test_budget_metrics_report_cost_efficiency_and_source_coverage(self):
        result = evaluate_case(self.cases[0])["task_aware"]
        self.assertGreater(result["token_efficiency"], 0.0)
        self.assertEqual(result["token_efficiency"], 1.0)
        self.assertEqual(result["source_coverage"], 1.0)

    def test_evaluation_script_emits_json_for_all_cases(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "evaluate_retrieval.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertEqual(set(report), {case["case_id"] for case in self.cases})
        self.assertIn("planned_context", report["duplicate-chapter-prevention"])

    def test_equal_scores_keep_deterministic_recency_order(self):
        case = next(item for item in self.cases if item['case_id'] == 'equal-score-recency-tie')
        result = evaluate_case(case)
        self.assertEqual(result['task_aware']['selected_ids'], ('newer-unrelated-export',))
        self.assertEqual(result['recency']['selected_ids'], ('newer-unrelated-export',))
        self.assertEqual(result['task_aware']['precision_at_k'], 1.0)
        self.assertEqual(result['recency']['precision_at_k'], 1.0)
        self.assertEqual(result['task_aware']['recall_at_k'], 0.5)
        self.assertEqual(result['recency']['recall_at_k'], 0.5)

    def test_independently_reviewed_synthetic_cases_have_clear_gold_labels(self):
        expected = {
            'accepted-confirmation-policy': 'confirmed-send-gate',
            'test-fingerprint-currentness': 'fingerprint-currentness-rule',
        }
        for case_id, relevant_id in expected.items():
            with self.subTest(case=case_id):
                case = next(item for item in self.cases if item['case_id'] == case_id)
                result = evaluate_case(case)
                self.assertEqual(case['annotation']['case_type'], 'independent_synthetic_label')
                self.assertEqual(case['relevant_ids'], [relevant_id])
                self.assertEqual(result['task_aware']['selected_ids'][0], relevant_id)
                self.assertEqual(result['task_aware']['precision_at_k'], 1.0)

    def test_unanswerable_case_reports_irrelevant_selected_context(self):
        case = next(item for item in self.cases if item['case_id'] == 'unanswerable-with-distractors')
        result = evaluate_case(case)
        self.assertEqual(case['relevant_ids'], [])
        self.assertEqual(result['task_aware']['recall_at_k'], 0.0)
        self.assertGreater(result['task_aware']['irrelevant_selected_count'], 0)
        self.assertGreater(result['planned_context']['task_aware']['irrelevant_selected_count'], 0)

    def test_empty_results_report_zero_metrics(self):
        case = next(item for item in self.cases if item['case_id'] == 'empty-result')
        result = evaluate_case(case)
        for ranking in (result["task_aware"], result["recency"]):
            self.assertEqual(ranking['selected_ids'], ())
            self.assertEqual(ranking['precision_at_k'], 0.0)
            self.assertEqual(ranking['recall_at_k'], 0.0)
        for ranking in result["planned_context"].values():
            self.assertEqual(ranking["selected_ids"], ())
            self.assertEqual(ranking["packed_tokens"], 0)

    def test_planned_context_compares_candidates_after_fixed_items_and_budget(self):
        candidates = [
            SummaryCandidate(
                "Theme styling notes", "Theme styling notes cover a small visual adjustment.",
                "chapter", {"source_id": "theme-source"}, 0, "theme-summary",
            ),
            SummaryCandidate(
                "Codex parser truncation fix", "Codex parser truncation preserves complete events.",
                "chapter", {"source_id": "parser-source"}, 1, "parser-summary",
            ),
        ]
        fixed = ContextItem(
            key="constraint:policy", section="constraints", title="Hard constraint",
            body="Preserve raw source history.", source="policy-source",
        )
        summary_cost = max(
            estimate_tokens(ContextItem(
                key="summary:" + candidate.candidate_id, section="summaries",
                title=candidate.title, body=candidate.body,
                source=candidate.metadata["source_id"],
            ).rendered("Source"))
            for candidate in candidates
        )
        budget = estimate_tokens(fixed.rendered("Source")) + summary_cost
        metrics = compare_planned_context(
            candidates, relevant_ids={"parser-summary"}, relevant_sources={"parser-source"},
            task="Codex parser truncation regression", k=1, token_budget=budget,
            fixed_items=(fixed,),
        )

        self.assertEqual(metrics["task_aware"].selected_ids, ("parser-summary",))
        self.assertEqual(metrics["recency"].selected_ids, ("theme-summary",))
        self.assertLessEqual(metrics["task_aware"].packed_tokens, budget)
        self.assertEqual(metrics["task_aware"].plan_item_ids[0], "constraint:policy")
        self.assertEqual(metrics["task_aware"].source_coverage, 1.0)
        self.assertLess(metrics["task_aware"].token_efficiency, 1.0)

    def test_changed_source_prefers_current_summary_over_stale_candidate(self):
        case = next(item for item in self.cases if item['case_id'] == 'changed-source-freshness')
        result = evaluate_case(case)
        self.assertEqual(result['task_aware']['selected_ids'][0], 'current-source-parser')
        self.assertEqual(result['task_aware']['stale_context_rate'], 0.0)

    def test_hyphenated_possibly_stale_label_is_penalized_and_measured(self):
        candidates = [
            SummaryCandidate(
                "Parser behavior", "Parser behavior is recorded here.", "chapter",
                {"freshness": "possibly-stale", "source_id": "stale-source"}, 0, "stale",
            ),
            SummaryCandidate(
                "Parser behavior", "Parser behavior is recorded here.", "chapter",
                {"freshness": "current", "source_id": "current-source"}, 1, "current",
            ),
        ]

        result = compare_planned_context(
            candidates, relevant_ids={"stale"}, relevant_sources={"stale-source"},
            task="parser behavior", k=2, token_budget=2000,
        )

        ranked = rank_summaries(candidates, task="parser behavior")
        self.assertEqual(ranked[0].candidate.candidate_id, "current")
        self.assertIn("freshness:possibly_stale", ranked[1].reasons)
        self.assertEqual(result["task_aware"].stale_context_rate, 0.5)
        self.assertEqual(result["recency"].stale_context_rate, 0.5)
        self.assertLess(
            result["task_aware"].selected_ids.index("current"),
            result["task_aware"].selected_ids.index("stale"),
        )

    def test_multi_source_case_measures_relevant_source_coverage(self):
        case = next(item for item in self.cases if item['case_id'] == 'multi-source-coverage')
        result = evaluate_case(case)
        self.assertEqual(result['task_aware']['source_coverage'], 1.0)

    def test_partial_overlap_case_measures_coverage_and_duplicate_tradeoff(self):
        case = next(
            item for item in self.cases
            if item["case_id"] == "partial-overlap-coverage-impact"
        )
        impact = evaluate_case(case)["overlap_impact"]
        self.assertEqual(
            impact["selected_ids"], ("current-parser-window", "older-parser-window"),
        )
        self.assertEqual(impact["excluded_ids"], ())
        self.assertEqual(impact["unique_turns_before"], 10)
        self.assertEqual(impact["unique_turns_after"], 10)
        self.assertEqual(impact["unique_turns_lost"], 0)
        self.assertEqual(impact["duplicate_turn_instances_after"], 2)
        self.assertEqual(impact["coverage_retained"], 1.0)

    def test_incomplete_provenance_is_retained_and_reported_separately(self):
        case = next(
            item for item in self.cases
            if item["case_id"] == "incomplete-provenance-retention"
        )
        result = evaluate_case(case)
        impact = result["overlap_impact"]
        planned = result["planned_context"]["task_aware"]

        self.assertEqual(
            set(impact["selected_ids"]),
            {"current-parser-window", "legacy-unattributed-summary"},
        )
        self.assertEqual(impact["excluded_ids"], ("redundant-known-range",))
        self.assertEqual(impact["unattributed_candidates_before"], 1)
        self.assertEqual(impact["unattributed_candidates_after"], 1)
        self.assertEqual(impact["unique_turns_lost"], 0)
        self.assertIn("legacy-unattributed-summary", planned["selected_ids"])
        self.assertIn("redundant-known-range", planned["excluded_ids"])

    def test_evaluation_fixture_has_no_known_secrets_or_personal_home_paths(self):
        self.assertEqual(content_issues(self.dataset_path.read_bytes()), [])


if __name__ == "__main__":
    unittest.main()
