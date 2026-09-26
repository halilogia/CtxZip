# Roadmap

This document describes targets, not claims that features are complete. Implementation order is in the [plan](docs/PLAN.md); concrete work is tracked in [tasks](docs/TASKS.md).

## 0.1 — Local foundation (current)

- Collect local Claude Code and Codex sessions, and Antigravity Markdown artifacts.
- Raw records, readable transcripts, chapter/volume summaries, and context packs.
- Manual summarization and an OpenAI-compatible LLM endpoint.

## 0.2 — Reliable import

- Parser tests against real sessions sanitized of personal data.
- Reruns, truncated/rewritten sources, and atomic writes.
- Validate Antigravity source format; preview LLM prompts and inspect for secrets.

## 0.3 — More relevant context

- First step implemented: a lexical and exact-match selector accepts task/file/symbol/commit/current-diff inputs, penalizes explicitly stale candidates, and can explain included summaries. A small sanitized evaluation compares relevance, stale-context rate, token efficiency, and source coverage with recency; expand the benchmark before tuning weights or claiming quality.
- Find relevant summaries by task, file, symbol, and commit.
- Flag outdated decision and test claims against current Git/test evidence.
- Source-linked decision/test records separate from processing state; validate against Git SHA and uncommitted working-tree changes.
- First priority-section planner composes existing records, optional Git/test evidence, and relevant summaries under an approximate budget. Chapter source hashes are checked against readable current turns; changed/shortened Chapters and containing Volumes are excluded without overwriting manual edits. Balanced mode admits recent raw turns outside current Chapter ranges. Missing legacy hashes, parser-version uncertainty, orphan summaries, and broader cross-Volume overlap remain open.
- `BAGLAM.md` has a versioned machine-readable metadata header with source and Git provenance; a future `CONTEXT.md` alias/migration remains compatibility-gated.
- Calibrate token estimates and evaluate source-linked summary quality.

Prioritize this stage's first selector after 0.2 write reliability is in place. Embeddings and a separate service are not prerequisites; detailed acceptance criteria are in the [plan](docs/PLAN.md).

## 0.4 — Verifiable project memory

- Introduce a canonical event model only after current source formats have sanitized compatibility fixtures.
- Store source-linked decisions, constraints, open questions, and test observations separately from `durum.json` processing state.
- Record Git and working-tree evidence so old test results and changed-source claims are not presented as current facts.
- Preserve provenance from every extracted record to its session, event/turn, and source version.

## 0.5 — Retrieval quality and freshness

- Add explainable relevance scoring, duplicate/overlap handling, freshness checks, and layered context budgeting. A first balanced profile now applies proportional caps and reserves recent-raw/safety capacity and includes unsummarized raw turns; rewritten-source and Chapter/Volume overlap handling remain open.
- Compare task-aware retrieval with recency-only selection on a maintained evaluation set.
- Consider SQLite/FTS only when archive size or query needs justify an index; do not require a separate vector service.

## 0.6+ — Optional integrations

- Evaluate semantic retrieval after lexical retrieval, provenance, and freshness are measured.
- Add MCP or automatic session lifecycle integration only when the local context engine is stable and there is demonstrated demand.
- Expand source adapters only for formats with a known, testable access path; declare each adapter's capabilities and limitations.
- Treat multi-agent, branch-aware memory, and knowledge-graph features as later options, not prerequisites for a useful local CLI.

## 1.0 — Stable local context engine

- Versioned archive and structured-record schemas with migration guarantees.
- Reproducible evaluation of relevance, provenance, freshness, and token-budget quality.
- Keep raw records canonical, summaries explicitly lossy, and each task's context pack a traceable derived artifact.

The roadmap is intentionally staged: storage correctness and evidence quality come before broader integrations or semantic infrastructure.

## Beyond 1.0 — Integration options

- Versioned export format and, if demand is demonstrated, an MCP interface.
- User-controlled local scheduler and multi-agent performance evaluation.

Cloud services are out of scope until the local version is reliable and a need is demonstrated.
