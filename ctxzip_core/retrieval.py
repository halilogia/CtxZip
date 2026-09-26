"""Deterministic lexical ranking for completed summary candidates."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .summary_ranges import SourceRange

TASK_OVERLAP_WEIGHT = 20.0
FILE_MATCH_WEIGHT = 100.0
SYMBOL_MATCH_WEIGHT = 120.0
CHANGED_FILE_MATCH_WEIGHT = 60.0
COMMIT_MATCH_WEIGHT = 80.0
STALE_PENALTY = 100.0
_OVERLAP_BUCKET_TURNS = 16
_MAX_BUCKETED_RANGE_TURNS = 256


@dataclass(frozen=True)
class SummaryCandidate:
    """A summary and its ranking inputs, independent of archive storage."""

    title: str
    body: str
    kind: str
    metadata: dict[str, str]
    ordinal: int
    candidate_id: str = ""
    source_ranges: tuple[SourceRange, ...] = ()
    manually_edited: bool = False


@dataclass(frozen=True)
class RankedSummary:
    candidate: SummaryCandidate
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OverlapExclusion:
    candidate: RankedSummary
    overlaps_with: tuple[str, ...]


def deduplicate_overlapping_summaries(
    ranked: list[RankedSummary],
) -> tuple[list[RankedSummary], list[OverlapExclusion]]:
    """Exclude lower-ranked candidates whose entire ranges are already covered.

    A partial intersection is not enough to discard a whole summary: its
    non-overlapping turns may contain unique information. Candidates without
    reliable coverage also remain eligible.
    """
    selected: list[RankedSummary] = []
    excluded: list[OverlapExclusion] = []
    selected_range_buckets: dict[str, dict[int, set[int]]] = {}
    selected_long_ranges: dict[str, list[tuple[int, SourceRange]]] = {}
    selected_ranges_by_index: list[tuple[SourceRange, ...]] = []
    for current in ranked:
        current_ranges = current.candidate.source_ranges
        if not current_ranges:
            # Missing provenance can never justify exclusion; avoid scanning all prior items.
            selected.append(current)
            selected_ranges_by_index.append(())
            continue

        overlapping_indices: set[int] = set()
        for source_range in current_ranges:
            session_key = source_range.session_id.casefold()
            buckets = selected_range_buckets.get(session_key, {})
            long_ranges = selected_long_ranges.get(session_key, ())
            overlapping_indices.update(index for index, _range in long_ranges)
            if source_range.last_turn - source_range.first_turn + 1 <= _MAX_BUCKETED_RANGE_TURNS:
                first_bucket = source_range.first_turn // _OVERLAP_BUCKET_TURNS
                last_bucket = source_range.last_turn // _OVERLAP_BUCKET_TURNS
                for bucket_number in range(first_bucket, last_bucket + 1):
                    overlapping_indices.update(buckets.get(bucket_number, ()))
            else:
                for bucket_indices in buckets.values():
                    overlapping_indices.update(bucket_indices)

        overlapping_indices = {
            selected_index for selected_index in overlapping_indices
            if any(
                left.session_id.casefold() == right.session_id.casefold()
                and left.first_turn <= right.last_turn
                and right.first_turn <= left.last_turn
                for left in current_ranges
                for right in selected_ranges_by_index[selected_index]
            )
        }

        covering_ranges = []
        covering_summaries = []
        for selected_index in sorted(overlapping_indices):
            existing = selected[selected_index]
            covering_summaries.append(existing.candidate.candidate_id or existing.candidate.title)
            covering_ranges.extend(selected_ranges_by_index[selected_index])
        if (
            not current.candidate.manually_edited
            and _ranges_fully_covered(current_ranges, tuple(covering_ranges))
        ):
            excluded.append(OverlapExclusion(current, tuple(covering_summaries)))
        else:
            selected_index = len(selected)
            selected.append(current)
            selected_ranges_by_index.append(current_ranges)
            for source_range in current_ranges:
                session_key = source_range.session_id.casefold()
                if source_range.last_turn - source_range.first_turn + 1 > _MAX_BUCKETED_RANGE_TURNS:
                    selected_long_ranges.setdefault(session_key, []).append((selected_index, source_range))
                    continue
                buckets = selected_range_buckets.setdefault(session_key, {})
                first_bucket = source_range.first_turn // _OVERLAP_BUCKET_TURNS
                last_bucket = source_range.last_turn // _OVERLAP_BUCKET_TURNS
                for bucket_number in range(first_bucket, last_bucket + 1):
                    buckets.setdefault(bucket_number, set()).add(selected_index)
    return selected, excluded


def _ranges_fully_covered(
    ranges: tuple[SourceRange, ...],
    covering_ranges: tuple[SourceRange, ...],
) -> bool:
    """Return whether every requested range is covered without a turn gap."""
    if not ranges or not covering_ranges:
        return False
    for source_range in ranges:
        matching = sorted(
            (
                item.first_turn, item.last_turn
            )
            for item in covering_ranges
            if item.session_id.casefold() == source_range.session_id.casefold()
            and item.last_turn >= source_range.first_turn
            and item.first_turn <= source_range.last_turn
        )
        next_turn = source_range.first_turn
        for first_turn, last_turn in matching:
            if first_turn > next_turn:
                break
            next_turn = max(next_turn, last_turn + 1)
            if next_turn > source_range.last_turn:
                break
        if next_turn <= source_range.last_turn:
            return False
    return True


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE) if len(token) > 1}


def _normalized_path(value: str) -> str:
    return value.strip().replace("\\", "/").strip("/").casefold()


def _contains_path(text: str, path: str) -> bool:
    return re.search(
        rf"(?<![\w./-]){re.escape(path)}(?![\w/-]|\.[\w])",
        text,
        flags=re.UNICODE,
    ) is not None


def _contains_identifier(text: str, identifier: str) -> bool:
    return re.search(
        rf"(?<!\w){re.escape(identifier)}(?!\w)", text, flags=re.UNICODE | re.IGNORECASE,
    ) is not None


def _metadata_values(metadata: dict[str, str], names: tuple[str, ...]) -> str:
    return " ".join(value for key, value in metadata.items() if key.casefold() in names)


def matching_changed_paths(candidate: SummaryCandidate, changed_files: tuple[str, ...]) -> tuple[str, ...]:
    """Return changed paths explicitly mentioned in summary text or file metadata."""
    metadata_paths = _metadata_values(
        candidate.metadata, ("files", "dosyalar", "file", "path", "validity_paths"),
    )
    source_text = f"{candidate.title}\n{candidate.body}\n{metadata_paths}"
    return tuple(
        normalized
        for normalized in dict.fromkeys(
            path for path in (_normalized_path(item) for item in changed_files) if path
        )
        if _contains_path(_normalized_path(source_text), normalized)
    )


def summary_is_possibly_stale(
    candidate: SummaryCandidate,
    changed_files: tuple[str, ...],
    current_head: str | None,
) -> bool:
    """Check declared HEAD/path validity and exact changed-path mentions."""
    freshness = str(candidate.metadata.get("freshness", "")).casefold().replace("-", "_")
    if freshness in {"stale", "possibly_stale"}:
        return True
    validity_head = str(candidate.metadata.get("validity_head_sha", "")).strip().casefold()
    if validity_head and current_head and validity_head != current_head.casefold():
        return True
    return bool(matching_changed_paths(candidate, changed_files))


def rank_summaries(
    candidates: list[SummaryCandidate],
    *,
    task: str = "",
    files: tuple[str, ...] = (),
    commits: tuple[str, ...] = (),
    symbols: tuple[str, ...] = (),
    changed_files: tuple[str, ...] = (),
) -> list[RankedSummary]:
    """Rank with transparent exact path/commit signals and lexical task overlap.

    Input order is the recency fallback and tie-breaker. With no query, scores are
    zero and the legacy order is retained exactly.
    """
    task_terms = _tokens(task)
    normalized_files = tuple(dict.fromkeys(path for path in (_normalized_path(item) for item in files) if path))
    normalized_changed_files = tuple(dict.fromkeys(path for path in (_normalized_path(item) for item in changed_files) if path))
    commit_terms = tuple(dict.fromkeys(item.strip().casefold() for item in commits if item.strip()))
    symbol_terms = tuple(dict.fromkeys(item.strip() for item in symbols if item.strip()))
    ranked: list[RankedSummary] = []
    for candidate in candidates:
        haystack = f"{candidate.title}\n{candidate.body}"
        normalized_haystack = _normalized_path(haystack)
        metadata_files = _normalized_path(_metadata_values(candidate.metadata, ("files", "dosyalar", "file", "path")))
        metadata_commits = _metadata_values(candidate.metadata, ("commit", "commits", "commit_sha", "sha" )).casefold()
        reasons: list[str] = []
        score = 0.0
        for requested in normalized_files:
            if _contains_path(metadata_files, requested) or _contains_path(normalized_haystack, requested):
                score += FILE_MATCH_WEIGHT
                reasons.append(f"file:{requested}")
        for changed_path in matching_changed_paths(candidate, normalized_changed_files):
            if changed_path:
                score += CHANGED_FILE_MATCH_WEIGHT
                reasons.append(f"changed-file:{changed_path}")
        for symbol in symbol_terms:
            if _contains_identifier(haystack, symbol):
                score += SYMBOL_MATCH_WEIGHT
                reasons.append(f"symbol:{symbol}")
        for commit in commit_terms:
            if _contains_identifier(metadata_commits, commit) or _contains_identifier(haystack, commit):
                score += COMMIT_MATCH_WEIGHT
                reasons.append(f"commit:{commit}")
        overlap = task_terms & _tokens(haystack)
        if task_terms and overlap:
            fraction = len(overlap) / len(task_terms)
            score += TASK_OVERLAP_WEIGHT * fraction
            reasons.append(f"task-terms:{len(overlap)}/{len(task_terms)}")
        freshness = str(candidate.metadata.get("freshness", "")).casefold().replace("-", "_")
        if freshness in {"stale", "possibly_stale"}:
            score -= STALE_PENALTY
            reasons.append(f"freshness:{freshness}")
        if not reasons:
            reasons.append("recency-fallback")
        ranked.append(RankedSummary(candidate, score, tuple(reasons)))
    ranked.sort(key=lambda item: (-item.score, item.candidate.ordinal))
    return ranked
