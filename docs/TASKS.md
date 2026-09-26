# Tasks

`[ ]` open, `[x]` complete.

## P0 — Data reliability

- [ ] Parser tests using real Claude Code and Codex JSONL samples sanitized of personal data.
- [x] Verify with synthetic records that rerunning `collect → transcript → summarize`, source growth/shrinkage, and continuation after an LLM error do not create duplicate chapters.
- [x] Use atomic replacement for source copies, transcripts, summary prompts/files, `durum.json`, and context packs; cover failed replacement/copy behavior.
- [x] Add personal-path and common-secret scanning for the Git index, plus LLM preview and approval before network calls.
- [x] Show a clear error and `--manual` guidance when the model name is empty or still set to the sample value.
- [ ] Measure coverage for detecting unknown secrets and personal information against real sanitized examples.

## P1 — Coverage and correctness

- [ ] Validate the Antigravity format with a real example; improve project matching.
- [ ] Test importing cloud/export files from `gelen/`.
- [x] Verify with synthetic tests that user edits to completed chapters/volumes survive reruns and are included in volume prompts.
- [ ] Build an evaluation set for source-turn/commit attribution and summary accuracy.
- [ ] Select task-relevant files and decisions for `BAGLAM.md`.
- [ ] Core selector with task/file/commit inputs; preserve current behavior without inputs; explain selection and budget.
- [ ] Measure selection quality against recency ordering using old-relevant/new-irrelevant summaries and tight budgets.
- [ ] Add versioned decision/constraint/test records outside `durum.json`, requiring source and verification status.
- [ ] Tie session/turn attribution to source hashes and parser versions; define invalidation rules for changed sources.
- [ ] Add working-tree fingerprints and scoped test events alongside Git SHAs; prevent historical results from appearing as current passes.
- [ ] Resolve overlap between chapters/volumes and recent raw turns; add a layered context budget.

## P2 — Usability

- [ ] Platform-independent installation and scheduler instructions.
- [ ] Add a `doctor` command for source-version and configuration diagnostics.
- [ ] Add `.editorconfig` with settings that match the repository's actual conventions.
- [ ] Add a concise `CONTRIBUTING.md` if external contributions are invited; keep setup and verification commands aligned with CI/local tests.
- [ ] Add `SECURITY.md` with a real, monitored vulnerability-reporting path and supported-version policy.
- [ ] Record significant accepted architecture choices in small ADRs; do not invent uncertain historical rationale.
- [ ] Use `docs/PROJECT_HANDOFF.md` only for active multi-step work, with a last-verified date and commit, then remove or refresh stale status.
- [x] Separate privacy, LLM, and Git copy boundaries into `ctxzip_core/` modules.
- [x] Move source parsing and summary-state management into separate modules without changing behavior; preserve the CLI dependency direction and test the import graph for cycles.
- [x] Add English/Turkish CLI and summary-prompt language selection; retain Turkish command names and provide English aliases.
- [x] Add compatibility aliases for older Turkish Python symbols; keep new core API names English.
- [x] Add namespace-based Turkish/English catalogs with placeholder/plural validation and locale fallback.
- [x] Use English names for Python source files, application symbols, comments, and docstrings; use an English filename for the sample settings file.
- [x] Split source-format parsers into small provider modules with English names and retain the `parsers.py` compatibility facade.
- [ ] Reconcile multi-file processing after interruption; evaluate a schema-backed state model.
- [ ] Handle stale summaries for sources that change or shrink within the same turn range, while preserving user edits.
- [ ] Move source discovery/copying, transcript generation, and context flows out of the CLI as needed.
- [ ] Design an MCP interface.

## P3 — Context engine foundations

- [ ] Define and test a provider capability registry; describe partial Antigravity history accurately.
- [ ] Design a provider-neutral event model with stable source/version references after sanitized parser fixtures exist.
- [ ] Keep narrative summaries separate from versioned, source-linked decisions, constraints, test observations, open questions, and file/symbol mentions.
- [ ] Capture Git head, dirty state, and worktree fingerprints for current-state and test evidence; mark mismatched evidence historical or stale.
- [ ] Define conflict/supersession and invalidation rules before automatic knowledge extraction.
- [ ] Add relevance explanations, deduplication, freshness filtering, and explicit context-budget allocation.
- [ ] Build a sanitized retrieval evaluation set and compare task-aware selection with recency-only selection.

## P4 — Conditional scale and integrations

- [ ] Measure archive/query scale before selecting SQLite/FTS or another index.
- [ ] Evaluate semantic retrieval only after lexical retrieval, provenance, and freshness have measurable baselines.
- [ ] Add source adapters only when the format has a known, testable access path and documented capabilities.
- [ ] Revisit MCP and automatic session lifecycle integration after the local context engine is stable and demand is demonstrated.
- [ ] Define stable schema and archive migration guarantees before a 1.0 release.

## Documentation

- [x] Write/update the README, architecture, roadmap, changelog, technical notes, plan, and task list.
- [ ] Add staged repository docs (ADRs, security, contribution guidance) only with verified scope, accepted decisions, and a real reporting path.
- [ ] Keep research-source citations portable and review all examples for personal project names, archive counts, paths, and secrets before publication.
- [x] Expand `.gitignore` to protect personal data.
