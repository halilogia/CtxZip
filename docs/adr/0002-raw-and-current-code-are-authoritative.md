# ADR-0002: Treat summaries as derived memory

- Status: Accepted
- Recorded: 2026-09-26

## Context

Chapter and Volume summaries are lossy and can become outdated when source sessions or project files change. Replacing source records with summaries would make errors difficult to detect and recover from.

## Decision

Keep raw session copies as the canonical conversation archive. Treat transcripts, Chapters, Volumes, structured knowledge, and `BAGLAM.md` as derived records with source provenance where available. Current project code, Git state, and matching test evidence take precedence over narrative summaries. Preserve the existing Turkish archive paths, state keys, and `BAGLAM.md` output name unless a compatibility migration is designed.

## Consequences

- Context generation must retain provenance and conservatively label or exclude stale derived content.
- Summary regeneration must preserve verified user edits and avoid duplicate Chapters or Volumes on retry.
- Future storage migrations must not silently rewrite the existing archive format.

## Evidence

- `AGENTS.md` behavioral invariants
- `ctxzip_core/source_freshness.py` and `ctxzip_core/summarizing.py`
- `ARCHITECTURE.md` data-flow description
