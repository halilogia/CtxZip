#!/usr/bin/env python3
"""Compare the sanitized task-aware retrieval set with recency ordering."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctxzip_core.evaluation import (
    compare_planned_context, compare_with_recency, measure_overlap_impact, metrics_to_dict,
)
from ctxzip_core.context_planner import ContextItem
from ctxzip_core.retrieval import SummaryCandidate
from ctxzip_core.summary_ranges import SourceRange


def load_dataset(path: Path) -> list[dict]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("schema_version") != 1 or not isinstance(dataset.get("cases"), list):
        raise ValueError("Unsupported retrieval evaluation dataset")
    return dataset["cases"]


def evaluate_case(case: dict) -> dict:
    candidates = [
        SummaryCandidate(
            title=item["title"],
            body=item["body"],
            kind=item["kind"],
            metadata=item.get("metadata", {}),
            ordinal=item["ordinal"],
            candidate_id=item["id"],
            source_ranges=tuple(
                SourceRange(
                    session_id=source["session_id"],
                    first_turn=source["first_turn"],
                    last_turn=source["last_turn"],
                )
                for source in item.get("source_ranges", [])
            ),
        )
        for item in case["candidates"]
    ]
    results = compare_with_recency(
        candidates,
        relevant_ids=set(case["relevant_ids"]),
        relevant_sources=set(case["relevant_sources"]),
        task=case.get("task", ""),
        files=tuple(case.get("files", [])),
        commits=tuple(case.get("commits", [])),
        symbols=tuple(case.get("symbols", [])),
        changed_files=tuple(case.get("changed_files", [])),
        k=int(case.get("k", 5)),
        token_budget=int(case.get("token_budget", 12000)),
    )
    report = {name: metrics_to_dict(metrics) for name, metrics in results.items()}
    fixed_items = tuple(
        ContextItem(
            key=item["id"], section=item["section"], title=item["title"],
            body=item["body"], source=item.get("source", ""),
            priority=float(item.get("priority", 0)), ordinal=int(item.get("ordinal", 0)),
        )
        for item in case.get("fixed_items", [])
    )
    planned = compare_planned_context(
        candidates,
        relevant_ids=set(case["relevant_ids"]),
        relevant_sources=set(case["relevant_sources"]),
        task=case.get("task", ""),
        files=tuple(case.get("files", [])),
        commits=tuple(case.get("commits", [])),
        symbols=tuple(case.get("symbols", [])),
        changed_files=tuple(case.get("changed_files", [])),
        k=int(case.get("k", 5)),
        token_budget=int(case.get("planner_token_budget", case.get("token_budget", 12000))),
        profile=case.get("budget_profile", "priority"),
        fixed_items=fixed_items,
    )
    report["planned_context"] = {
        name: metrics_to_dict(metrics) for name, metrics in planned.items()
    }
    if any(candidate.source_ranges for candidate in candidates):
        report["overlap_impact"] = metrics_to_dict(measure_overlap_impact(
            candidates,
            task=case.get("task", ""),
            files=tuple(case.get("files", [])),
            commits=tuple(case.get("commits", [])),
            symbols=tuple(case.get("symbols", [])),
            changed_files=tuple(case.get("changed_files", [])),
        ))
    return report


def main() -> int:
    default_dataset = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "retrieval" / "eval_cases.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=default_dataset)
    arguments = parser.parse_args()
    report = {
        case["case_id"]: evaluate_case(case)
        for case in load_dataset(arguments.dataset)
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
