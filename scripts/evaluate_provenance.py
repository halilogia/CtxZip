#!/usr/bin/env python3
"""Evaluate source attribution and manually labeled summary claims on synthetic data."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctxzip_core.events import source_file_hash
from ctxzip_core.parsers import EVENT_PARSERS, PARSER_VERSIONS
from ctxzip_core.git_state import GitSnapshot
from ctxzip_core.knowledge import Freshness, RecordActor, TestEvidence, TestResult, test_freshness


def _event_key(event: object) -> tuple[int | None, int, str]:
    return (
        event.source.record_index,
        event.source.turn_number,
        event.kind.value,
    )


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate_case(case: dict, fixture_root: Path) -> dict[str, object]:
    """Compare parser event provenance and summary claim annotations to case labels."""
    parser_name = case["parser"]
    parser = EVENT_PARSERS.get(parser_name)
    if parser is None:
        raise ValueError(f"Unsupported event parser in evaluation case: {parser_name}")
    fixture = (fixture_root / case["source_fixture"]).resolve()
    if fixture_root.resolve() not in fixture.parents:
        raise ValueError("Evaluation fixture must stay within the fixture root")
    parsed = parser(fixture, include_thinking=False, language="en")

    expected_events = Counter(
        (item["record_index"], item["turn_number"], item["kind"])
        for item in case["expected_events"]
    )
    actual_events = Counter(_event_key(event) for event in parsed.events)
    event_true_positives = sum((expected_events & actual_events).values())
    event_false_positives = sum((actual_events - expected_events).values())
    event_false_negatives = sum((expected_events - actual_events).values())
    source_version_valid = all(
        event.source.source_id == parser_name
        and event.source.session_id == fixture.stem
        and event.source.parser_version == case["expected_parser_version"]
        and event.source.parser_version == PARSER_VERSIONS[parser_name]
        and event.source.source_hash == source_file_hash(fixture)
        for event in parsed.events
    )
    if not source_version_valid:
        raise ValueError(f"Parser emitted incomplete source-version provenance: {case['case_id']}")

    claims_by_id = {claim["id"]: claim for claim in case["claims"]}
    if len(claims_by_id) != len(case["claims"]):
        raise ValueError(f"Duplicate gold claim ID in evaluation case: {case['case_id']}")
    summary_claims = case["summary_claims"]
    if any(claim["id"] not in claims_by_id for claim in summary_claims):
        raise ValueError(f"Summary references an unknown claim ID: {case['case_id']}")
    if len({claim["id"] for claim in summary_claims}) != len(summary_claims):
        raise ValueError(f"Duplicate summary claim ID: {case['case_id']}")

    supported_ids = {claim["id"] for claim in case["claims"] if claim["supported"]}
    included_ids = {claim["id"] for claim in summary_claims}
    claim_true_positives = len(included_ids & supported_ids)
    claim_false_positives = len(included_ids - supported_ids)
    claim_false_negatives = len(supported_ids - included_ids)

    expected_citations = 0
    correct_citations = 0
    emitted_citations = 0
    for summary_claim in summary_claims:
        gold_claim = claims_by_id[summary_claim["id"]]
        actual_refs = Counter(tuple(ref) for ref in summary_claim["source_events"])
        emitted_citations += sum(actual_refs.values())
        if gold_claim["supported"]:
            expected_refs = Counter(tuple(ref) for ref in gold_claim["source_events"])
            expected_citations += sum(expected_refs.values())
            correct_citations += sum((expected_refs & actual_refs).values())

    git_evidence_results = []
    for item in case.get("test_evidence", []):
        evidence = TestEvidence(
            id=item["id"],
            actor=RecordActor.TEST_RUNNER,
            command="python <arguments omitted>",
            result=TestResult.PASSED,
            exit_code=0,
            captured_at="2026-01-01T00:00:00Z",
            scope=("tests",),
            branch="main",
            head_sha=item["head_sha"],
            worktree_fingerprint=item["fingerprint"],
            dirty=False,
        )
        current = GitSnapshot(
            is_repository=True,
            branch="main",
            head_sha=item["current_head_sha"],
            dirty=False,
            staged_diff_hash="0" * 64,
            unstaged_diff_hash="0" * 64,
            status_hash="0" * 64,
            untracked_files=(),
            changed_files=(),
            fingerprint=item["current_fingerprint"],
        )
        observed = test_freshness(evidence, current).value
        git_evidence_results.append({
            "id": item["id"],
            "expected": item["expected_freshness"],
            "observed": observed,
            "matches_label": observed == item["expected_freshness"],
        })

    return {
        "case_id": case["case_id"],
        "evidence_level": "synthetic-manual-labels",
        "event_attribution": {
            "precision": _ratio(event_true_positives, event_true_positives + event_false_positives),
            "recall": _ratio(event_true_positives, event_true_positives + event_false_negatives),
            "expected_event_count": sum(expected_events.values()),
            "actual_event_count": sum(actual_events.values()),
            "source_version_reference_valid": source_version_valid,
        },
        "summary_claims": {
            "supported_claim_precision": _ratio(
                claim_true_positives, claim_true_positives + claim_false_positives,
            ),
            "supported_claim_recall": _ratio(
                claim_true_positives, claim_true_positives + claim_false_negatives,
            ),
            "unsupported_included_claims": claim_false_positives,
        },
        "claim_source_attribution": {
            "precision": _ratio(correct_citations, emitted_citations),
            "recall": _ratio(correct_citations, expected_citations),
            "expected_citation_count": expected_citations,
            "emitted_citation_count": emitted_citations,
        },
        "git_bound_test_evidence": {
            "cases": git_evidence_results,
            "label_accuracy": _ratio(
                sum(item["matches_label"] for item in git_evidence_results),
                len(git_evidence_results),
            ),
        },
    }


def load_dataset(path: Path) -> dict:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("schema_version") != 1 or not isinstance(dataset.get("cases"), list):
        raise ValueError("Unsupported provenance evaluation dataset")
    return dataset


def main() -> int:
    default_dataset = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "provenance" / "eval_cases.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=default_dataset)
    arguments = parser.parse_args()
    dataset = load_dataset(arguments.dataset)
    fixture_root = arguments.dataset.resolve().parents[1]
    report = {
        "evidence_level": dataset["evidence_level"],
        "scope_note": dataset["scope_note"],
        "cases": [evaluate_case(case, fixture_root) for case in dataset["cases"]],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
