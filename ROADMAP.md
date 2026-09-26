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

- First small step: a lexical and exact-match selector accepting task/file/commit inputs; compare its reasons and results with recency ordering.
- Find relevant summaries by task, file, symbol, and commit.
- Flag outdated decision and test claims against current Git/test evidence.
- Source-linked decision/test records separate from processing state; validate against Git SHA and uncommitted working-tree changes.
- Calibrate token estimates and evaluate source-linked summary quality.

Prioritize this stage's first selector after 0.2 write reliability is in place. Embeddings and a separate service are not prerequisites; detailed acceptance criteria are in the [plan](docs/PLAN.md).

## 0.4 — Verifiable project memory

- Introduce a canonical event model only after current source formats have sanitized compatibility fixtures.
- Store source-linked decisions, constraints, open questions, and test observations separately from `durum.json` processing state.
- Record Git and working-tree evidence so old test results and changed-source claims are not presented as current facts.
- Preserve provenance from every extracted record to its session, event/turn, and source version.

## 0.5 — Retrieval quality and freshness

- Add explainable relevance scoring, duplicate/overlap handling, freshness checks, and layered context budgeting.
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
