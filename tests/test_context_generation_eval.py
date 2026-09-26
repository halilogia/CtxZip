"""Integration evaluation of filesystem freshness, knowledge, Git, and budget."""
import unittest

from scripts.evaluate_context_generation import evaluate_production_context


class ProductionContextEvaluationTests(unittest.TestCase):
    def test_real_context_builder_combines_freshness_knowledge_git_and_budget(self):
        result = evaluate_production_context()
        self.assertTrue(result["synthetic"])
        self.assertTrue(result["stale_chapter_excluded"])
        self.assertTrue(result["dependent_volume_excluded"])
        self.assertTrue(result["current_summary_included"])
        self.assertTrue(result["unattributed_legacy_summary_retained"])
        self.assertTrue(result["knowledge_decision_included"])
        self.assertTrue(result["unrelated_oversized_knowledge_omitted"])
        self.assertTrue(result["secret_redacted_from_generated_context"])
        self.assertTrue(result["git_head_recorded"])
        self.assertTrue(result["changed_path_marked_possibly_stale"])
        self.assertTrue(result["within_budget"])


if __name__ == "__main__":
    unittest.main()
