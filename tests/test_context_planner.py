"""Context allocation tests use synthetic items and no archive data."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctxzip_core.context_planner import ContextItem, balanced_allocation, plan_context
from ctxzip_core.text import estimate_tokens


class ContextPlannerTests(unittest.TestCase):
    def test_balanced_allocation_scales_reference_budget_and_preserves_total(self):
        allocation = balanced_allocation(32000)
        self.assertEqual(allocation, {
            "task_state": 4000,
            "decisions": 3000,
            "git_tests": 4000,
            "files": 8000,
            "summaries": 7000,
            "recent_raw": 4000,
            "safety": 2000,
        })
        self.assertEqual(sum(balanced_allocation(137).values()), 137)

    def test_balanced_profile_enforces_section_caps_and_reports_reserves(self):
        task = ContextItem("task", "task", "Task", "x" * 2000)
        summary = ContextItem("summary", "summaries", "History", "relevant note")
        plan = plan_context([task, summary], 3200, "Source", profile="balanced")
        allocation = balanced_allocation(3200)
        self.assertEqual([item.key for item in plan.selected], ["summary"])
        self.assertEqual([item.key for item in plan.omitted], ["task"])
        self.assertLessEqual(plan.token_count, allocation["summaries"])
        self.assertEqual(plan.profile, "balanced")
        self.assertEqual(plan.recent_raw_budget_tokens, allocation["recent_raw"])
        self.assertEqual(plan.recent_raw_used_tokens, 0)
        self.assertEqual(plan.recent_raw_reserved_tokens, allocation["recent_raw"])
        self.assertEqual(plan.safety_reserved_tokens, allocation["safety"])
        self.assertEqual(plan.reserved_tokens, allocation["recent_raw"] + allocation["safety"])

    def test_priority_profile_keeps_shared_budget_and_rejects_unknown_profiles(self):
        item = ContextItem("task", "task", "Task", "x" * 250)
        plan = plan_context([item], 100, "Source")
        self.assertEqual(plan.selected, (item,))
        self.assertEqual(plan.reserved_tokens, 0)
        with self.assertRaisesRegex(ValueError, "Unknown context allocation"):
            plan_context([item], 100, "Source", profile="unknown")

    def test_fixed_section_order_precedes_relevance_priority(self):
        items = [
            ContextItem("summary", "summaries", "Relevant", "task match", priority=100),
            ContextItem("constraint", "constraints", "Hard rule", "must hold", priority=0),
            ContextItem("task", "task", "Current task", "Fix parser"),
        ]
        plan = plan_context(items, 1000, "Source")
        self.assertEqual([item.key for item in plan.selected], ["task", "constraint", "summary"])

    def test_oversized_item_is_skipped_so_smaller_later_item_can_fit(self):
        large = ContextItem("large", "constraints", "Large", "x" * 700)
        small = ContextItem("small", "decisions", "Small", "keep the parser stable")
        budget = estimate_tokens(small.rendered("Source"))
        plan = plan_context([large, small], budget, "Source")
        self.assertEqual([item.key for item in plan.selected], ["small"])
        self.assertEqual([item.key for item in plan.omitted], ["large"])
        self.assertLessEqual(plan.token_count, budget)

    def test_duplicate_keys_are_included_once(self):
        first = ContextItem("same", "decisions", "Decision", "one")
        duplicate = ContextItem("same", "questions", "Duplicate", "two")
        plan = plan_context([first, duplicate], 100, "Source")
        self.assertEqual([item.key for item in plan.selected], ["same"])


if __name__ == "__main__":
    unittest.main()
