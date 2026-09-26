#!/usr/bin/env python3
"""Exercise the production context-pack pipeline with a sanitized project fixture."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ctxzip
from ctxzip_core.context_generation import build_context_pack
from ctxzip_core.context_pack import parse_metadata_block
from ctxzip_core.events import EventReference, SourceRef
from ctxzip_core.git_state import GitSnapshot
from ctxzip_core.knowledge import (
    DecisionRecord, KnowledgeStatus, KnowledgeStore, RecordActor,
)
from ctxzip_core.summary_store import save_summary_state, write_summary_file


def evaluate_production_context() -> dict:
    """Return observable production-pipeline outcomes for a disposable fixture."""
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "codex" / "normal.jsonl.fixture"
    with tempfile.TemporaryDirectory(prefix="ctxzip-context-eval-") as temporary:
        project = Path(temporary) / "sanitized-project"
        source = project / "raw" / "codex" / "sanitized-session.jsonl"
        source.parent.mkdir(parents=True)
        source.write_bytes(fixture.read_bytes())

        chapter_dir = project / "bolumler"
        volume_dir = project / "ciltler"
        chapter_dir.mkdir()
        volume_dir.mkdir()
        settings = dict(ctxzip.DEFAULT_SETTINGS, language="en")
        stale_body = "STALE_SOURCE_CHAPTER_SENTINEL"
        current_body = "Current parser reference is src/parser.py."
        legacy_body = "UNATTRIBUTED_LEGACY_SENTINEL: unverified parser notes retained pending provenance."
        write_summary_file(chapter_dir / "B0001.md", {
            "tur": "bolum", "no": 1, "kaynak": "codex/sanitized-session",
            "source_language": "en", "parser_version": ctxzip.PARSER_VERSIONS["codex"],
            "turlar": "T1-T1", "kaynak_hash": "0" * 64,
        }, "Stale source chapter", stale_body)
        write_summary_file(chapter_dir / "B0002.md", {
            "tur": "bolum", "no": 2, "kaynak": "codex/other-sanitized-session",
            "source_language": "en", "parser_version": ctxzip.PARSER_VERSIONS["codex"],
            "turlar": "T1-T1",
        }, "Current parser chapter", current_body)
        write_summary_file(chapter_dir / "B0003.md", {
            "tur": "bolum", "no": 3,
        }, "Legacy summary without source range", legacy_body)
        write_summary_file(volume_dir / "C001.md", {
            "tur": "cilt", "no": 1, "bolumler": "B1-B2",
        }, "Stale dependent volume", "STALE_VOLUME_SENTINEL")
        save_summary_state(project, {
            "bolumler": [
                {"no": 1, "dosya": "B0001.md", "oturum": "codex/sanitized-session",
                 "tur_baslangic": 1, "tur_bitis": 1, "cilt": 1},
                {"no": 2, "dosya": "B0002.md", "oturum": "codex/other-sanitized-session",
                 "tur_baslangic": 1, "tur_bitis": 1, "cilt": 1},
                {"no": 3, "dosya": "B0003.md", "cilt": None},
            ],
            "ciltler": [{"no": 1, "dosya": "C001.md", "bolumler": [1, 2]}],
        })

        knowledge = KnowledgeStore(project / "knowledge")
        reference = EventReference("event:sanitized", SourceRef(
            source_id="codex", session_id="sanitized-session", source_hash="a" * 64,
            parser_version=ctxzip.PARSER_VERSIONS["codex"], turn_number=1, record_index=1,
        ))
        fake_secret = "sk-" + "Q" * 40
        knowledge.add_decision(DecisionRecord(
            id="decision:parser-path",
            statement=f"Keep the parser boundary in src/parser.py. Private key: {fake_secret}",
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-02T00:00:00Z", source_refs=(reference,),
            validity_paths=("src/parser.py",), validity_head_sha="a" * 40,
        ))
        irrelevant_sentinel = "UNRELATED_BUDGET_SENTINEL"
        knowledge.add_decision(DecisionRecord(
            id="decision:unrelated", statement=(irrelevant_sentinel + " ") * 1500,
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-03T00:00:00Z", source_refs=(reference,),
        ))

        snapshot = GitSnapshot(
            True, "main", "b" * 40, True, "1" * 64, "2" * 64, "3" * 64,
            ("src/parser.py",), ("src/parser.py",), "d" * 64,
        )
        budget = 1200
        build_context_pack(
            settings, project, budget, None,
            task="Keep the parser boundary in src/parser.py", files=("src/parser.py",),
            changed_files=("src/parser.py",), git_snapshot=snapshot,
        )
        output = (project / "BAGLAM.md").read_text(encoding="utf-8")
        metadata = parse_metadata_block(output)
        return {
            "synthetic": True,
            "stale_chapter_excluded": stale_body not in output,
            "dependent_volume_excluded": "STALE_VOLUME_SENTINEL" not in output,
            "current_summary_included": current_body in output,
            "unattributed_legacy_summary_retained": legacy_body in output,
            "knowledge_decision_included": "Keep the parser boundary" in output,
            "unrelated_oversized_knowledge_omitted": irrelevant_sentinel not in output,
            "secret_redacted_from_generated_context": fake_secret not in output and "[REDACTED]" in output,
            "git_head_recorded": metadata.get("git", {}).get("head_sha") == "b" * 40,
            "changed_path_marked_possibly_stale": "possibly stale" in output.casefold() or "possibly-stale" in output.casefold(),
            "budget_limit": budget,
            "estimated_tokens": metadata["estimated_tokens"],
            "within_budget": metadata.get("estimated_tokens", budget + 1) <= budget,
        }


def main() -> int:
    print(json.dumps(evaluate_production_context(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
