# Implementation Plan

## Goal

A local context tool that safely carries sessions from different coding agents forward and keeps claims traceable to their sources.

## Design context and target

The user's Isekai Zero research and CtxZip assessment suggest adding a small local context selector on top of session archiving. The steps below are implementation proposals; they are not claims that the features are complete or that every recommendation in the research was approved. External product claims in the research report have not been re-verified as part of this plan.

Target data separation: source records → lossy chapter/volume summaries; separate source-linked decision/test records; a context planner that selects by task and budget → `BAGLAM.md`. Provider caches are not durable project memory. The active `raw/` path is updated, while replaced JSONL bytes are retained as content-addressed sibling versions; it is not an append-only event log.

Source parsers, summary-state management, source discovery/copying, per-project transcript writing, and context-pack generation now live in core modules behind CLI wrappers. Atomic writes, sanitized Claude/Codex format fixtures, granular Claude/Codex events, transcript-level Antigravity/manual events, versioned per-session event snapshots with retained content-addressed source/parser history, read-only Git fingerprints, a separate structured-record store, explicit `test-run` evidence capture, and a first lexical summary selector now provide foundations. Antigravity tree sync archives changed/deleted artifacts before replacing current copies and refreshes event snapshots. A local ChatGPT export adapter now splits supported extracted `conversations.json` files into separate session records without modifying the input; its schema coverage is synthetic and awaits a real sanitized export. The initial layered context planner and known-overlap exclusion are implemented; next, measure coverage impact and broaden retrieval evaluation. The wrapper records only commands it executes; arbitrary external test invocations are not intercepted. MCP remains conditional on demand.

The long-term target is a **local-first context engine**, not one giant summary: canonical source copies feed normalized events; lossy narrative summaries and source-linked evidence remain separate; current task and Git/test state drive an explainable, budgeted context pack. Build only the next measured capability. A full event store, database, embeddings, daemon, or MCP server is not an early prerequisite.

## 1. Harden import

Test parsers using real Claude/Codex records sanitized of personal data; cover reruns, growing/shrinking sources, and partial-file states; add atomic writes; validate the Antigravity format.

**Exit criteria:** Processing the same record twice does not create duplicate chapters, and a summary can be traced back to its source turns.

## 2. Summaries and safety

Preview LLM prompts, inspect for secrets, attribute source turns/commits, preserve manual edits, and keep processing state consistent on model errors.

**Exit criteria:** Important decision/test claims are traceable, and a failed run does not corrupt the archive.

## 3. Task-relevant context

Select chapters based on task, files, and Git changes; warn about stale claims; measure actual tokens and success in new sessions. Add an MCP interface if demand is confirmed.

**Exit criteria:** More relevant context and less stale information than the current recency-first approach.

### 3a. First measurable context selector

- Implemented CLI inputs: `context --task`, repeatable `--file`, `--symbol`, and `--commit`, `--from-git-diff`, plus `--explain`. Ranking is in `ctxzip_core/retrieval.py`, using exact path/symbol/commit and changed-path signals plus task-word overlap, with recency as a deterministic tie-breaker and a penalty for stale metadata. When a changed worktree path exactly matches a path in summary text/title or file metadata, the generated context labels that summary possibly stale without changing it. `summary-validity` records explicitly reviewed tracked paths and a clean Git HEAD into Chapter/Volume frontmatter while preserving the body; comprehensive claim-to-file scope is not inferred. Structured records are composed in separate planner sections.
- Included summaries and structured records carry source references; `--explain` reports ranking signals and budget omissions with estimated costs.
- Preserve current behavior when no task input is supplied. Exclude incomplete summaries and fully redundant ranges; retain partial overlaps and manually edited summaries to avoid losing unique information.
- A runnable sanitized eleven-case evaluation set covers duplicate-chapter retrieval, Codex parser truncation, unrelated-task fallback, equal-score recency ties, empty and unanswerable results, changed-source freshness, multi-source coverage across Chapter/Volume candidate types, the unique-turn coverage loss from excluding a partially overlapping summary, accepted confirmation policy, and test-fingerprint currentness. Two new direct-relevance cases received blind second-reader review. The report measures Precision@K, Recall@K, stale-context rate, token efficiency, source coverage, and irrelevant selected items against recency. The overlap case also reports unique turns before/after exclusion and the retained fraction. These synthetic cases are regression checks, not representative quality evidence.
- Unit/integration tests also cover exact path and commit matches, no-query recency order, and localized context generation preserving manually edited summaries. The synthetic partial-overlap case retains all 10 unique turns while including two duplicate turn instances; expand with independently labeled sanitized ranges to measure this trade-off before tuning scoring weights.

### 3b. Structured records and validity

- Keep `durum.json` as chapter/volume processing state. `ctxzip_core.knowledge.KnowledgeStore` now stores versioned decisions, constraints, test evidence, open questions, and file mentions in separate atomic JSON collections under a caller-provided private archive directory. Localized `knowledge add` / `hafiza add` supports explicitly authored decisions, constraints, tasks, questions, and file mentions tied to an archived source turn; it requires granular event snapshots from Claude Code, Codex, or ChatGPT.
- Knowledge claims require an event/source-version reference, authoring actor, and status. Extractors cannot confirm claims. User-confirmed decision replacements mark the old record superseded in the same collection write. A same-scope, user-confirmed constraint replacement invalidates its previous record atomically; cross-scope conflict resolution remains undefined and automatic extraction stays disabled.
- Define source identities within project/provider/session and source version. Parser changes or rewritten sources can shift turn numbers, so `T12` alone is not a durable identity.
- `TestEvidence` captures a sanitized command label, exit code/result, time, scope, branch, SHA, dirty state, and worktree fingerprint. The explicit `test-run` wrapper records commands it executes and compares stored evidence to a current snapshot; arbitrary test commands run outside the wrapper are not intercepted. Context output labels available evidence current, stale, or unknown against the supplied snapshot.
- The planner offers a legacy shared `priority` cap and an opt-in `balanced` profile scaled from the roadmap 32k allocation: task/state 4k, decisions 3k, Git/tests 4k, files/symbols 8k, summaries 7k, recent raw 4k, safety 2k. Balanced mode enforces proportional category ceilings, includes up to 20 latest raw turns outside current Chapter ranges, and reports used/remaining raw-turn and safety allocations. Chapter source hashes are checked against readable current turns; changed/shortened summaries and containing Volumes are excluded without modifying summary files, while current Chapters from those Volumes can be selected separately. Metadata-backed orphan Chapters/Volumes are recovered at summarization startup even when numbers have gaps; file bodies stay unchanged, subsequent numbering starts after the maximum, and malformed/ambiguous files block unchanged. Volume folding only groups contiguous chapter numbers. A summary is excluded only when higher-ranked summaries fully cover its ranges; partial overlaps and manually edited summaries remain eligible. Legacy hashes, parser-version uncertainty, metadata-less/contradictory orphan recovery and representative overlap measurements remain open. Token counts remain approximate.

### 3c. Context-pack output contract

- `BAGLAM.md` now starts with a JSON metadata comment identified by `ctxzip-context-pack` and schema version 1. It records locale, project label, generation timestamp, budget/profile, estimated selected tokens, source references, and optional Git snapshot identity. A parser validates the leading contract.
- Keep the readable Markdown body and current `BAGLAM.md` output/copy name stable. `CONTEXT.md` is reserved and protected from Git while a compatibility-aware alias/migration remains a future decision.

### 3d. Later expansion

Add file/symbol and Git diff matching in response to measured gaps. Evaluate embeddings, a vector database, daemon, and MCP after the first selector's quality and data contract are established. A cloud/multi-tenant service design from the research is not required for a local CLI.

## 4. Canonical events and source capabilities

- Once sanitized fixtures cover supported source versions, normalize provider records into a provider-neutral event model with stable source references. Keep only information the source actually exposes; do not infer access to hidden reasoning or unavailable history.
- Give each adapter an explicit capability description (for example: full history, timestamps, tool calls, project path, and native message IDs). User-facing claims must follow those verified capabilities.
- Retain the current archive layout during this transition. Raw files remain the canonical source copies; normalization is a derived view, not a destructive rewrite.

## 5. Structured memory and current-state evidence

- Keep narrative episode/chapter summaries separate from decisions, constraints, test observations, open questions, and file/symbol references.
- Mark extracted facts as observed, inferred, confirmed, superseded, invalidated, or unknown as appropriate. Inferred content must not silently become a confirmed user decision.
- Store provenance and source versions for records. Test observations include command, result, scope, time, Git head, and a working-tree fingerprint; mismatched evidence is historical, not a current pass.
- Define conflict and invalidation behavior before growing the schema. Keep `durum.json` dedicated to processing state.

## 6. Retrieval, planning, and evaluation

- Retrieve candidate evidence with exact path, symbol, commit, and lexical matches before considering embeddings.
- Deduplicate candidates, check freshness, explain inclusion/exclusion, then allocate a token budget across the task, constraints, current Git/test evidence, relevant history, and recent raw turns.
- Maintain a sanitized evaluation set and measure source recall, stale-item rate, provenance coverage, and token efficiency against recency-only selection.
- Add SQLite/FTS, semantic retrieval, MCP, or session hooks only when evaluation or real usage identifies a need. Keep each as an optional local capability with a narrow interface.
