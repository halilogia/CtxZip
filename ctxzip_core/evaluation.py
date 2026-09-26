"""Small deterministic retrieval metrics for sanitized evaluation cases."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .context_planner import ContextItem, plan_context
from .retrieval import (
    RankedSummary, SummaryCandidate, deduplicate_overlapping_summaries, rank_summaries,
)
from .summary_ranges import SourceRange
from .text import estimate_tokens


@dataclass(frozen=True)
class RankingMetrics:
    precision_at_k: float
    recall_at_k: float
    stale_context_rate: float
    token_efficiency: float
    source_coverage: float
    selected_ids: tuple[str, ...]
    irrelevant_selected_count: int


@dataclass(frozen=True)
class PlannedContextMetrics:
    """Measure candidate quality after ranking, overlap filtering, and budget packing."""

    precision_at_k: float
    recall_at_k: float
    stale_context_rate: float
    token_efficiency: float
    source_coverage: float
    selected_ids: tuple[str, ...]
    plan_item_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]
    omitted_candidate_ids: tuple[str, ...]
    packed_tokens: int
    irrelevant_selected_count: int


@dataclass(frozen=True)
class OverlapMetrics:
    candidate_ids: tuple[str, ...]
    selected_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]
    unique_turns_before: int
    unique_turns_after: int
    unique_turns_lost: int
    duplicate_turn_instances_after: int
    coverage_retained: float
    unattributed_candidates_before: int
    unattributed_candidates_after: int


def _unique_turn_count(candidates: list[SummaryCandidate]) -> int:
    """Count the union of known inclusive source-turn intervals."""
    intervals: dict[str, list[tuple[int, int]]] = {}
    for candidate in candidates:
        for source_range in candidate.source_ranges:
            if (
                isinstance(source_range, SourceRange)
                and isinstance(source_range.session_id, str)
                and source_range.session_id.strip()
                and isinstance(source_range.first_turn, int)
                and not isinstance(source_range.first_turn, bool)
                and isinstance(source_range.last_turn, int)
                and not isinstance(source_range.last_turn, bool)
                and source_range.first_turn >= 1
                and source_range.last_turn >= source_range.first_turn
            ):
                intervals.setdefault(source_range.session_id.casefold(), []).append(
                    (source_range.first_turn, source_range.last_turn),
                )
    total = 0
    for ranges in intervals.values():
        end = 0
        for first, last in sorted(ranges):
            if first > end + 1:
                total += last - first + 1
            elif last > end:
                total += last - end
            end = max(end, last)
    return total


def _turn_instance_count(candidates: list[SummaryCandidate]) -> int:
    return sum(
        source_range.last_turn - source_range.first_turn + 1
        for candidate in candidates
        for source_range in candidate.source_ranges
        if isinstance(source_range, SourceRange)
        and isinstance(source_range.first_turn, int)
        and not isinstance(source_range.first_turn, bool)
        and isinstance(source_range.last_turn, int)
        and not isinstance(source_range.last_turn, bool)
        and source_range.first_turn >= 1
        and source_range.last_turn >= source_range.first_turn
    )


def measure_overlap_impact(
    candidates: list[SummaryCandidate],
    *,
    task: str = "",
    files: tuple[str, ...] = (),
    commits: tuple[str, ...] = (),
    symbols: tuple[str, ...] = (),
    changed_files: tuple[str, ...] = (),
) -> OverlapMetrics:
    """Quantify unique source turns removed by whole-summary overlap exclusion."""
    ranked = rank_summaries(
        candidates, task=task, files=files, commits=commits,
        symbols=symbols, changed_files=changed_files,
    )
    selected, exclusions = deduplicate_overlapping_summaries(ranked)
    all_items = [item.candidate for item in ranked]
    kept_items = [item.candidate for item in selected]
    before = _unique_turn_count(all_items)
    after = _unique_turn_count(kept_items)
    lost = max(0, before - after)
    return OverlapMetrics(
        candidate_ids=tuple(_candidate_id(item) for item in all_items),
        selected_ids=tuple(_candidate_id(item) for item in kept_items),
        excluded_ids=tuple(_candidate_id(item.candidate.candidate) for item in exclusions),
        unique_turns_before=before,
        unique_turns_after=after,
        unique_turns_lost=lost,
        duplicate_turn_instances_after=max(0, _turn_instance_count(kept_items) - after),
        coverage_retained=after / before if before else 0.0,
        unattributed_candidates_before=sum(not item.source_ranges for item in all_items),
        unattributed_candidates_after=sum(not item.source_ranges for item in kept_items),
    )


def _candidate_id(candidate: SummaryCandidate) -> str:
    return candidate.candidate_id or candidate.title


def evaluate_ranking(
    ranked: list[SummaryCandidate],
    *,
    relevant_ids: set[str],
    relevant_sources: set[str],
    k: int,
    token_budget: int,
) -> RankingMetrics:
    """Measure relevance, freshness, token use, and provenance coverage.

    Budget packing mirrors context behavior: candidates that do not fit are skipped
    while later candidates may still fit. Metrics use no provider-specific tokenizer.
    """
    if k <= 0 or token_budget < 0:
        raise ValueError("k must be positive and token_budget cannot be negative")
    top = ranked[:k]
    top_ids = {_candidate_id(item) for item in top}
    relevant_top = top_ids & relevant_ids
    precision = len(relevant_top) / len(top) if top else 0.0
    recall = len(relevant_top) / len(relevant_ids) if relevant_ids else 0.0

    selected: list[SummaryCandidate] = []
    selected_tokens = 0
    for candidate in ranked:
        cost = estimate_tokens(candidate.body)
        if cost <= token_budget - selected_tokens:
            selected.append(candidate)
            selected_tokens += cost
    stale_count = sum(
        str(item.metadata.get("freshness", "")).casefold().replace("-", "_")
        in {"stale", "possibly_stale"}
        for item in selected
    )
    stale_rate = stale_count / len(selected) if selected else 0.0
    relevant_tokens = sum(
        estimate_tokens(item.body) for item in selected if _candidate_id(item) in relevant_ids
    )
    token_efficiency = relevant_tokens / selected_tokens if selected_tokens else 0.0
    covered_sources = {
        item.metadata.get("source_id", "") for item in selected
        if _candidate_id(item) in relevant_ids and item.metadata.get("source_id")
    }
    source_coverage = len(covered_sources & relevant_sources) / len(relevant_sources) if relevant_sources else 0.0
    return RankingMetrics(
        precision_at_k=precision,
        recall_at_k=recall,
        stale_context_rate=stale_rate,
        token_efficiency=token_efficiency,
        source_coverage=source_coverage,
        selected_ids=tuple(_candidate_id(item) for item in selected),
        irrelevant_selected_count=sum(_candidate_id(item) not in relevant_ids for item in selected),
    )


def _evaluate_ranked_plan(
    ranked: list[RankedSummary],
    *,
    relevant_ids: set[str],
    relevant_sources: set[str],
    k: int,
    token_budget: int,
    profile: str,
    fixed_items: tuple[ContextItem, ...],
) -> PlannedContextMetrics:
    if k <= 0 or token_budget < 0:
        raise ValueError("k must be positive and token_budget cannot be negative")
    selected, exclusions = deduplicate_overlapping_summaries(ranked)
    summary_items = [
        ContextItem(
            key=f"summary:{_candidate_id(item.candidate)}",
            section="summaries",
            title=item.candidate.title,
            body=item.candidate.body,
            source=item.candidate.metadata.get("source_id", ""),
            priority=item.score,
            ordinal=item.candidate.ordinal,
            reasons=item.reasons,
        )
        for item in selected
    ]
    plan = plan_context([*fixed_items, *summary_items], token_budget, "Source", profile=profile)
    candidate_by_key = {item.key: item for item in summary_items}
    selected_summary_items = [item for item in plan.selected if item.key in candidate_by_key]
    selected_ids = tuple(candidate_by_key[item.key].key.removeprefix("summary:") for item in selected_summary_items)
    top_ids = set(selected_ids[:k])
    relevant_top = top_ids & relevant_ids
    precision = len(relevant_top) / min(k, len(selected_ids)) if selected_ids else 0.0
    recall = len(relevant_top) / len(relevant_ids) if relevant_ids else 0.0
    freshness_by_id = {
        _candidate_id(item.candidate): item.candidate.metadata.get("freshness", "")
        for item in selected
    }
    stale_count = sum(
        str(freshness_by_id.get(item.key.removeprefix("summary:"), "")).casefold().replace("-", "_")
        in {"stale", "possibly_stale"}
        for item in selected_summary_items
    )
    relevant_tokens = sum(
        estimate_tokens(item.rendered("Source"))
        for item in selected_summary_items
        if item.key.removeprefix("summary:") in relevant_ids
    )
    token_efficiency = relevant_tokens / plan.token_count if plan.token_count else 0.0
    covered_sources = {
        item.source for item in selected_summary_items
        if item.key.removeprefix("summary:") in relevant_ids and item.source
    }
    omitted_candidate_ids = tuple(
        item.key.removeprefix("summary:") for item in plan.omitted
        if item.key.startswith("summary:")
    )
    excluded_ids = tuple(_candidate_id(item.candidate.candidate) for item in exclusions)
    return PlannedContextMetrics(
        precision_at_k=precision,
        recall_at_k=recall,
        stale_context_rate=stale_count / len(selected_summary_items) if selected_summary_items else 0.0,
        token_efficiency=token_efficiency,
        source_coverage=(len(covered_sources & relevant_sources) / len(relevant_sources)
                         if relevant_sources else 0.0),
        selected_ids=selected_ids,
        plan_item_ids=tuple(item.key for item in plan.selected),
        excluded_ids=excluded_ids,
        omitted_candidate_ids=omitted_candidate_ids,
        packed_tokens=plan.token_count,
        irrelevant_selected_count=sum(
            item.key.removeprefix("summary:") not in relevant_ids
            for item in selected_summary_items
        ),
    )


def compare_planned_context(
    candidates: list[SummaryCandidate],
    *,
    relevant_ids: set[str],
    relevant_sources: set[str],
    task: str = "",
    files: tuple[str, ...] = (),
    commits: tuple[str, ...] = (),
    symbols: tuple[str, ...] = (),
    changed_files: tuple[str, ...] = (),
    k: int = 5,
    token_budget: int = 12000,
    profile: str = "priority",
    fixed_items: tuple[ContextItem, ...] = (),
) -> dict[str, PlannedContextMetrics]:
    """Compare task ranking and recency after actual context planner budget packing."""
    task_ranked = rank_summaries(
        candidates, task=task, files=files, commits=commits,
        symbols=symbols, changed_files=changed_files,
    )
    recency_ranked = [
        RankedSummary(candidate, 0.0, ("recency-fallback",))
        for candidate in sorted(candidates, key=lambda item: item.ordinal)
    ]
    common = {
        "relevant_ids": relevant_ids,
        "relevant_sources": relevant_sources,
        "k": k,
        "token_budget": token_budget,
        "profile": profile,
        "fixed_items": fixed_items,
    }
    return {
        "task_aware": _evaluate_ranked_plan(task_ranked, **common),
        "recency": _evaluate_ranked_plan(recency_ranked, **common),
    }
def compare_with_recency(
    candidates: list[SummaryCandidate],
    *,
    relevant_ids: set[str],
    relevant_sources: set[str],
    task: str = "",
    files: tuple[str, ...] = (),
    commits: tuple[str, ...] = (),
    symbols: tuple[str, ...] = (),
    changed_files: tuple[str, ...] = (),
    k: int = 5,
    token_budget: int = 12000,
) -> dict[str, RankingMetrics]:
    """Compare task-aware ordering to the legacy most-recent-first baseline."""
    task_ranked = [
        item.candidate for item in rank_summaries(
            candidates, task=task, files=files, commits=commits,
            symbols=symbols, changed_files=changed_files,
        )
    ]
    recent_ranked = sorted(candidates, key=lambda item: item.ordinal)
    common = {
        "relevant_ids": relevant_ids,
        "relevant_sources": relevant_sources,
        "k": k,
        "token_budget": token_budget,
    }
    return {
        "task_aware": evaluate_ranking(task_ranked, **common),
        "recency": evaluate_ranking(recent_ranked, **common),
    }


def metrics_to_dict(metrics: RankingMetrics | PlannedContextMetrics | OverlapMetrics) -> dict[str, object]:
    """Return a JSON-ready representation for the evaluation command."""
    return asdict(metrics)
