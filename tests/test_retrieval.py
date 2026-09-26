"""Deterministic summary retrieval tests with synthetic, non-personal content."""
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctxzip_core import retrieval
from ctxzip_core.retrieval import (
    SummaryCandidate, deduplicate_overlapping_summaries, matching_changed_paths, rank_summaries,
)
from ctxzip_core.summary_ranges import SourceRange, source_ranges_for_summary


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.recent = SummaryCandidate(
            "Recent unrelated", "Update the color palette in docs/theme.md.", "bolumler", {}, 0,
        )
        self.relevant = SummaryCandidate(
            "Older parser decision", "Parser.timeout handling belongs in src/parser.py; commit abc123.",
            "bolumler", {}, 1,
        )

    def test_no_query_preserves_recency_order(self):
        ranked = rank_summaries([self.recent, self.relevant])
        self.assertEqual([item.candidate.title for item in ranked], ["Recent unrelated", "Older parser decision"])
        self.assertEqual(ranked[0].reasons, ("recency-fallback",))

    def test_file_commit_and_task_signals_rank_old_relevant_summary_first(self):
        ranked = rank_summaries(
            [self.recent, self.relevant], task="parser timeout", files=("src\\parser.py",), commits=("abc123",),
        )
        self.assertEqual(ranked[0].candidate.title, "Older parser decision")
        self.assertEqual(ranked[0].reasons, ("file:src/parser.py", "commit:abc123", "task-terms:2/2"))

    def test_path_matching_is_case_and_separator_insensitive(self):
        ranked = rank_summaries([self.recent, self.relevant], files=("SRC/PARSER.PY",))
        self.assertEqual(ranked[0].candidate.title, "Older parser decision")

    def test_path_prefix_is_not_an_exact_match(self):
        candidate = SummaryCandidate("No exact path", "Changed src/parser.pyx", "bolumler", {}, 0)
        ranked = rank_summaries([candidate], files=("src/parser.py",))
        self.assertEqual(ranked[0].score, 0)

    def test_symbol_and_current_diff_paths_add_explainable_signals(self):
        ranked = rank_summaries(
            [self.recent, self.relevant],
            task="Parser.timeout",
            symbols=("Parser.timeout",),
            changed_files=("src/parser.py",),
        )
        self.assertEqual(ranked[0].candidate.title, "Older parser decision")
        self.assertEqual(
            ranked[0].reasons,
            ("changed-file:src/parser.py", "symbol:Parser.timeout", "task-terms:2/2"),
        )

    def test_changed_paths_match_explicit_summary_file_metadata_exactly(self):
        candidate = SummaryCandidate(
            "Parser behavior", "Timeout behavior is recorded.", "bolumler",
            {"files": "src/parser.py"}, 0,
        )
        self.assertEqual(
            matching_changed_paths(candidate, ("SRC\\PARSER.PY", "src/parser.pyx")),
            ("src/parser.py",),
        )

    def test_changed_paths_do_not_match_unrelated_path_prefixes(self):
        candidate = SummaryCandidate(
            "Parser behavior", "The parser handles timeouts.", "bolumler", {}, 0,
        )
        self.assertEqual(matching_changed_paths(candidate, ("src/parser.pyx",)), ())

    def test_stale_candidate_receives_explicit_score_penalty(self):
        stale = SummaryCandidate("Stale", "parser timeout", "bolumler", {"freshness": "stale"}, 0)
        current = SummaryCandidate("Current", "parser timeout", "bolumler", {"freshness": "current"}, 1)
        ranked = rank_summaries([stale, current], task="parser timeout")
        self.assertEqual(ranked[0].candidate.title, "Current")
        self.assertIn("freshness:stale", ranked[1].reasons)

    def test_deduplication_only_compares_ranges_from_the_same_session(self):
        recent = SummaryCandidate(
            "Recent", "new", "bolumler", {}, 0, "B2",
            (SourceRange("codex/session", 5, 8),),
        )
        partially_overlapping = SummaryCandidate(
            "Older", "old", "bolumler", {}, 1, "B1",
            (SourceRange("CODEX/SESSION", 1, 5),),
        )
        fully_covered = SummaryCandidate(
            "Redundant", "duplicate", "bolumler", {}, 3, "B4",
            (SourceRange("codex/session", 6, 7),),
        )
        separate = SummaryCandidate(
            "Other session", "other", "bolumler", {}, 2, "B3",
            (SourceRange("codex/other", 1, 10),),
        )

        selected, excluded = deduplicate_overlapping_summaries(
            rank_summaries([recent, partially_overlapping, separate, fully_covered]),
        )

        self.assertEqual([item.candidate.candidate_id for item in selected], ["B2", "B1", "B3"])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0].candidate.candidate.candidate_id, "B4")
        self.assertEqual(excluded[0].overlaps_with, ("B2",))

    def test_manually_edited_summary_is_never_removed_as_redundant(self):
        edited = SummaryCandidate(
            "Edited", "curated clarification", "bolumler", {}, 1, "edited",
            (SourceRange("session", 1, 4),), manually_edited=True,
        )
        covering = SummaryCandidate(
            "Covering", "summary", "ciltler", {}, 0, "covering",
            (SourceRange("session", 1, 4),),
        )
        selected, excluded = deduplicate_overlapping_summaries(
            rank_summaries([covering, edited]),
        )
        self.assertEqual([item.candidate.candidate_id for item in selected], ["covering", "edited"])
        self.assertEqual(excluded, [])

    def test_multiple_higher_ranked_ranges_can_fully_cover_a_candidate(self):
        candidates = [
            SummaryCandidate("First", "first", "bolumler", {}, 0, "first", (
                SourceRange("session", 1, 2),
            )),
            SummaryCandidate("Second", "second", "bolumler", {}, 1, "second", (
                SourceRange("session", 3, 5),
            )),
            SummaryCandidate("Combined duplicate", "duplicate", "ciltler", {}, 2, "combined", (
                SourceRange("SESSION", 1, 5),
            )),
        ]
        selected, excluded = deduplicate_overlapping_summaries(rank_summaries(candidates))
        self.assertEqual([item.candidate.candidate_id for item in selected], ["first", "second"])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0].candidate.candidate.candidate_id, "combined")
        self.assertEqual(excluded[0].overlaps_with, ("first", "second"))

    def test_overlap_index_handles_bucket_boundaries_and_long_ranges(self):
        candidates = [
            SummaryCandidate("Short cover", "cover", "chapter", {}, 0, "short-cover", (
                SourceRange("session-a", 60, 67),
            )),
            SummaryCandidate("Boundary duplicate", "duplicate", "chapter", {}, 1, "boundary-duplicate", (
                SourceRange("session-a", 64, 64),
            )),
            SummaryCandidate("Boundary partial", "unique tail", "chapter", {}, 2, "boundary-partial", (
                SourceRange("session-a", 64, 70),
            )),
            SummaryCandidate("Long cover", "cover", "chapter", {}, 3, "long-cover", (
                SourceRange("session-b", 1, 400),
            )),
            SummaryCandidate("Long-range duplicate", "duplicate", "chapter", {}, 4, "long-duplicate", (
                SourceRange("session-b", 250, 260),
            )),
        ]

        selected, excluded = deduplicate_overlapping_summaries(rank_summaries(candidates))

        self.assertEqual(
            [item.candidate.candidate_id for item in selected],
            ["short-cover", "boundary-partial", "long-cover"],
        )
        self.assertEqual(
            [entry.candidate.candidate.candidate_id for entry in excluded],
            ["boundary-duplicate", "long-duplicate"],
        )

    def test_bucketed_filter_matches_naive_reference_for_deterministic_range_sets(self):
        generator = random.Random(731_992)
        for batch in range(12):
            candidates = []
            for ordinal in range(80):
                ranges = []
                if generator.random() >= 0.2:
                    for _ in range(generator.randint(1, 3)):
                        first_turn = generator.randint(1, 400)
                        ranges.append(SourceRange(
                            f"session-{generator.randrange(4)}",
                            first_turn,
                            first_turn + generator.randint(0, 320),
                        ))
                candidates.append(SummaryCandidate(
                    title=f"{'Parser state' if generator.random() < 0.5 else 'Summary'} {ordinal}",
                    body="Parser state regression details.",
                    kind="chapter",
                    metadata={"freshness": generator.choice(("current", "possibly-stale"))},
                    ordinal=ordinal,
                    candidate_id=f"batch-{batch}-item-{ordinal}",
                    source_ranges=tuple(ranges),
                    manually_edited=generator.random() < 0.1,
                ))
            ranked = rank_summaries(candidates, task="parser state")
            expected_selected = []
            expected_excluded = []
            for current in ranked:
                covering_ranges = []
                covering_summaries = []
                for existing in expected_selected:
                    if any(
                        left.session_id.casefold() == right.session_id.casefold()
                        and left.first_turn <= right.last_turn
                        and right.first_turn <= left.last_turn
                        for left in current.candidate.source_ranges
                        for right in existing.candidate.source_ranges
                    ):
                        covering_summaries.append(
                            existing.candidate.candidate_id or existing.candidate.title,
                        )
                        covering_ranges.extend(existing.candidate.source_ranges)
                if (
                    not current.candidate.manually_edited
                    and retrieval._ranges_fully_covered(
                        current.candidate.source_ranges, tuple(covering_ranges),
                    )
                ):
                    expected_excluded.append((
                        current.candidate.candidate_id, tuple(covering_summaries),
                    ))
                else:
                    expected_selected.append(current)

            selected, excluded = deduplicate_overlapping_summaries(ranked)
            self.assertEqual(
                [item.candidate.candidate_id for item in selected],
                [item.candidate.candidate_id for item in expected_selected],
            )
            self.assertEqual(
                [
                    (item.candidate.candidate.candidate_id, item.overlaps_with)
                    for item in excluded
                ],
                expected_excluded,
            )

    def test_incomplete_volume_state_does_not_claim_partial_source_coverage(self):
        state = {
            "bolumler": [{
                "no": 1, "dosya": "B0001.md", "oturum": "codex/session",
                "tur_baslangic": 1, "tur_bitis": 4,
            }],
            "ciltler": [{"no": 1, "dosya": "C001.md", "bolumler": [1, 2]}],
        }

        self.assertEqual(
            source_ranges_for_summary(
                "ciltler", "C001.md", state,
                {"tur": "cilt", "no": 1, "bolumler": "B1-B2"},
            ),
            (),
        )

    def test_malformed_state_or_metadata_does_not_claim_source_coverage(self):
        state = {
            "bolumler": [{
                "no": 1, "dosya": "B0001.md", "oturum": "codex/session",
                "tur_baslangic": True, "tur_bitis": 4,
            }],
        }
        self.assertEqual(
            source_ranges_for_summary(
                "bolumler", "B0001.md", state,
                {"tur": "bolum", "no": 1, "kaynak": "codex/session", "turlar": 1},
            ),
            (),
        )
        self.assertEqual(source_ranges_for_summary("bolumler", "B0001.md", None, {}), ())


if __name__ == "__main__":
    unittest.main()
