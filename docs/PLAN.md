# Implementation Plan

## Goal

A local context tool that safely carries sessions from different coding agents forward and keeps claims traceable to their sources.

## Design context and target

The user's Isekai Zero research and CtxZip assessment suggest adding a small local context selector on top of session archiving. The steps below are implementation proposals; they are not claims that the features are complete or that every recommendation in the research was approved. External product claims in the research report have not been re-verified as part of this plan.

Target data separation: source records → lossy chapter/volume summaries; separate source-linked decision/test records; a context planner that selects by task and budget → `BAGLAM.md`. Provider caches are not durable project memory. The current `raw/` is an updated source copy, not an append-only event log.

Source parsers and summary-state management have been moved into core modules. Next implementation order: write reliability → measurable task-aware selection → source-linked structured records/Git validity → MCP if demand is confirmed. The small first step for 0.3 context selection can proceed without waiting for every integration, while preserving write reliability as a prerequisite.

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

- Proposed CLI inputs: `context --task`, repeatable `--file`, and `--commit`. These options are not implemented yet. Initial commit matching searches summary attributions; Git diff analysis is a separate step.
- Keep selection logic in the core, separate from the CLI. The first version should match file paths, commit attributions, and words; recency should only break ties. Expose selection reasons, source references, estimated cost, and candidates omitted due to budget.
- Preserve current behavior when no task input is supplied. Exclude incomplete summaries and avoid duplicate context where chapter/volume source ranges overlap.
- Synthetic evaluation set: old relevant/new irrelevant summaries, exact file paths, commit matches, ties, empty results, and tight budgets. Compare with current recency ordering at the same budget; measure whether relevant sources are selected and traceable.

### 3b. Structured records and validity

- Keep `durum.json` as chapter/volume processing state. Define a separate versioned record schema for tasks, explicit decisions, constraints, test events, and open questions. JSON format alone does not guarantee correctness.
- Every claim should include a source session/turn or tool event, source hash, authoring actor, and verification status. A recommendation inferred from a summary must not automatically become a user decision or verified fact.
- Define source identities within project/provider/session and source version. Parser changes or rewritten sources can shift turn numbers, so `T12` alone is not a durable identity.
- A test event should capture command, exit code, time, scope, SHA, and working-tree fingerprint. Uncommitted changes at the same SHA also affect validity; results whose evidence does not match should be shown as historical observations.
- Allocate the context budget explicitly across task/constraints, verified state, relevant summaries, and recent source turns. Do not present approximate token counts as guarantees of model limits.

### 3c. Later expansion

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
