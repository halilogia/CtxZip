#!/usr/bin/env python3
"""Measure synthetic summary ranking and source-range overlap filtering scale."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctxzip_core.retrieval import (
    SummaryCandidate, deduplicate_overlapping_summaries, rank_summaries,
)
from ctxzip_core.summary_ranges import SourceRange


def _candidates(count: int, layout: str) -> list[SummaryCandidate]:
    result = []
    for ordinal in range(count):
        source_ranges = ()
        if layout == "one-session":
            source_ranges = (SourceRange("synthetic-session", ordinal + 1, ordinal + 1),)
        elif layout == "many-sessions":
            source_ranges = (SourceRange(f"synthetic-session-{ordinal}", 1, 1),)
        result.append(SummaryCandidate(
            title=f"Synthetic summary {ordinal}",
            body="Synthetic parser state summary for retrieval scaling measurement.",
            kind="chapter",
            metadata={"source_id": f"synthetic-source-{ordinal}"},
            ordinal=ordinal,
            candidate_id=f"synthetic-summary-{ordinal}",
            source_ranges=source_ranges,
        ))
    return result


def _measure(candidates: list[SummaryCandidate], repeats: int) -> dict[str, float | int]:
    rank_samples = []
    overlap_samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        ranked = rank_summaries(candidates, task="parser state retrieval")
        rank_samples.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        selected, excluded = deduplicate_overlapping_summaries(ranked)
        overlap_samples.append((time.perf_counter() - started) * 1000)
        if len(selected) + len(excluded) != len(candidates):
            raise RuntimeError("Overlap filtering lost or duplicated candidates")
    return {
        "rank_median_ms": round(statistics.median(rank_samples), 3),
        "overlap_median_ms": round(statistics.median(overlap_samples), 3),
        "selected_count": len(selected),
        "excluded_count": len(excluded),
    }


def run_benchmark(sizes: list[int], repeats: int) -> dict:
    if not sizes or any(size < 1 for size in sizes):
        raise ValueError("Every benchmark size must be a positive integer")
    if repeats < 1:
        raise ValueError("Repeat count must be a positive integer")
    measurements = []
    for size in sizes:
        for layout in ("unattributed", "many-sessions", "one-session"):
            measurements.append({
                "candidate_count": size,
                "layout": layout,
                **_measure(_candidates(size, layout), repeats),
            })
    return {
        "synthetic": True,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "repeats": repeats,
        "measurements": measurements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 5000])
    parser.add_argument("--repeats", type=int, default=3)
    arguments = parser.parse_args()
    try:
        report = run_benchmark(arguments.sizes, arguments.repeats)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
