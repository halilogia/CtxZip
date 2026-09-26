# Changelog

## [Unreleased]

### Fixed

- Reject Claude/Codex event parses when the source file changes between provenance hashing and parse completion.
- Leave ChatGPT turn-event `record_index` empty instead of treating the derived turn ordinal as a source record; retain active mapping-node keys in `record_ids`, bump the adapter parser version, and add source-change verification.
- Extend canonical event snapshots to schema v2 for source record IDs while preserving resolution of existing schema v1 snapshots.
- Preserve manually edited Chapter and Volume prompts when retrying after an abrupt exit between prompt creation and summary-file creation.
- Normalize hyphenated and underscored `possibly-stale` freshness labels consistently in summary ranking and retrieval evaluation.

### Added

- Add `summary-validity` (`ozet-gecerlilik`) to record explicitly reviewed tracked paths and a clean Git HEAD baseline without changing the summary body.
- Build the balanced recent-raw context section from provider-neutral turn-transcript events; bridge legacy Claude/Codex turn output without changing the rendered transcript, while keeping Claude's explicit private-thinking option outside the event bridge.
- Add platform-independent installation and private unattended collection instructions for Windows Task Scheduler, macOS launchd, and Linux systemd user timers.
- Add a synthetic manual-label provenance evaluator for event source references, summary claim support/citations, and Git-bound test-evidence freshness; results are explicitly non-representative.
- Add a synthetic production-pipeline evaluation that combines stale Chapter/Volume exclusion, retention of a legacy summary without source-range provenance, source-linked knowledge, oversized irrelevant-record omission, actual-output secret redaction, Git state, and context budget in one generated pack.
- Add sanitized synthetic Claude/Codex tool-heavy parser fixtures and normalized goldens covering calls, error results, `commandRun`, custom/local-shell calls, and reasoning opt-in.
- Report unattributed-summary counts before and after overlap filtering, with a synthetic regression proving incomplete-provenance summaries stay eligible while fully covered known ranges can be excluded.
- Add a repeatable synthetic retrieval-scale benchmark and bucket candidate source ranges by session/turn to reduce overlap-filter scans on large candidate sets.
- Add localized `knowledge add` / `hafiza add` for explicit event-linked decisions, constraints, tasks, questions, and file mentions; no automatic extraction or LLM request is performed.
- Preserve normalized event snapshots by source hash and parser-version digest, resolving old event references after source changes and removals.
- Extend retrieval evaluation reports through source-range exclusion and the production context budget planner while retaining the ranking-only baseline.
- Add blind-reviewed synthetic relevance cases for accepted LLM confirmation policy and test-fingerprint freshness, plus an unanswerable-query fixture and irrelevant-selection counts.
- Label summaries possibly stale in generated context when an explicitly referenced file matches a changed path or optional `validity_paths`/`validity_head_sha` metadata no longer matches the supplied worktree; source summary files remain untouched.
- Verify recovery after abrupt process termination midway through a multi-source collection batch.
- Verify multi-project summary recovery after an abrupt exit between project state writes.
- Add a local ChatGPT `conversations.json` importer for `gelen/`. Collection creates a separate derived session per conversation and leaves the export unchanged; fixture coverage is synthetic and real-export/schema verification remains open.
- Add a read-only `doctor` command for settings, Python, source roots, locale catalogs, parser registry, archive destination, LLM configuration, Git, and the installed privacy hook.
- Add source-linked transcript events for Antigravity Markdown artifacts and manual imports without inferring unavailable message or tool structure.
- Persist canonical events as private, schema-versioned snapshots and atomically refresh a session when its source content or parser version changes.
- Reconcile Antigravity Markdown artifact trees, retaining changed and removed artifact versions before updating the active archive copy.
- Preserve every replaced JSONL session version under a content-hash-derived history filename before updating the active copy; repeated collection does not duplicate archived versions.
- Resolve current or retained JSONL/ChatGPT source bytes by provider, session, and content hash for provenance verification.
- Require user-confirmed same-scope replacement before invalidating a stored constraint; migrate knowledge collections to schema version 3 while continuing to read versions 1 and 2.
- Add `test-run` (`record-test`) to run an explicit local argv and save only its outcome and pre-run Git identity as private test evidence; command arguments and output are not persisted.
- Recover metadata-backed orphan Chapters/Volumes even when their numbers have gaps; preserve file bodies, avoid reusing numbers, and stop safely when identity or source ranges are ambiguous.
- Exclude a lower-ranked summary only when higher-ranked summaries fully cover its known source-turn ranges; keep partial overlaps and manually edited summaries to preserve unique information. `--explain` reports exclusions.
- Deterministic task-aware context ranking by task words, exact file paths, and commit attributions, with optional localized selection explanations.
- Additive symbol and current-worktree changed-path signals, plus an explicit penalty for candidates already marked stale.
- Sanitized retrieval evaluation dataset and a recency baseline report with Precision@K, Recall@K, stale-context rate, token efficiency, and source coverage.
- Expanded retrieval regression fixtures to eleven cases and measured the partial-overlap trade-off: one synthetic case retains all 10 unique turns and reports two duplicated turn instances. This is illustrative only, not a representative benchmark.
- A priority-ordered context planner that composes existing source-linked knowledge, optional current Git/test evidence, and relevant summaries under the token budget; omitted items can be explained. An opt-in balanced profile adds proportional category caps plus recent-raw and safety reserves.
- Version-1 JSON metadata for `BAGLAM.md` with source references, budget details, and optional Git snapshot identity; a validator reads the stable header contract.
- Balanced context packs now include up to 20 latest raw turns outside recorded Chapter ranges, with source hash/turn provenance.
- Context generation now checks unedited Chapter source/parser versions against current parsed turns in the recorded locale, skips changed or shortened-source summaries and containing Volumes, and keeps verified manual edits as user overrides without changing files.
- Conservative file, decision, and constraint freshness labels based on recorded paths and Git HEAD; unscoped historical records remain explicitly unknown. Knowledge schema v1 collections remain readable and migrate to v2 on write.
- Turkish and English CLI/localized prompts via `language`, `--language`, or `CTXZIP_LANG`; English command aliases are available alongside Turkish commands.
- Extensible namespace-based JSON locale catalogs with named interpolation, plural forms, locale normalization, and catalog consistency validation.
- English-first Python API names with Turkish compatibility aliases; persisted archive names and keys remain stable.
- Renamed the checked-in sample configuration to `ctxzip.settings.example.json` and made `ctxzip.settings.json` the preferred private settings filename; existing `ctxzip_ayar.json` files still load automatically.
- Regression tests using synthetic records for reruns, source growth/shrinkage, manual edits, continuation after LLM errors, redaction, and the import graph.
- Fault-injection tests verify Chapter and Volume retries reconcile state after the summary file succeeds but its following state write fails.
- Retry tests cover interrupted source collection, partial transcript output, and resuming multi-project summaries after a later project fails.
- Minimized, content-scrubbed real-format JSONL fixtures for Claude Code and Codex parser coverage.
- Sanitized normalized-event golden files for the Claude Code and Codex baseline fixtures, checked alongside the fixture privacy allowlist.
- Keep complete Claude/Codex events readable when the final JSONL row is truncated by an interrupted source write.
- A source capability registry that declares retained inputs and transcript limitations per adapter.
- An initial provider-neutral event envelope with stable source-version provenance, bridged from existing turns without changing archive behavior.
- Granular source-linked event APIs for Claude Code and Codex message, tool, metadata, and supported result records; legacy transcript APIs remain available.
- A read-only Git snapshot API with branch/HEAD, staged and unstaged diff hashes, untracked-file hashes, and deterministic worktree fingerprints.
- A versioned `KnowledgeStore` with separate task, decision, constraint, test, question, and file-mention collections; user-confirmed decision replacements are atomic and test freshness is checked against Git fingerprints.
- Full-prompt and destination preview before LLM calls, with interactive approval by default.
- Explicit `--onayli-gonder` option for non-interactive automation.
- Personal-output, common-secret, and user-path scanning for selected Git files; a hook installer that preserves an existing hook.
- Ignore/tracking checks in the target Git repository for `baglam --kopyala`.

### Changed

- Move source discovery, project mapping, archive copies, and incoming-export collection from the CLI into `ctxzip_core/source_collection.py`; keep legacy CLI helper names available.
- Move per-project transcript formatting, redaction, atomic output, and event snapshot persistence into `ctxzip_core/transcripts.py`; retain the CLI entry point and localized result messages.
- Move context selection, freshness checks, pack rendering, atomic output, and safe optional copy into `ctxzip_core/context_generation.py`; preserve `ctxzip.build_context` as the CLI compatibility wrapper.
- Source parsers, session listing, turn budgeting, summary files/state management, and chapter/volume orchestration were moved into core modules while preserving commands and archive formats.
- Raw source copies, transcripts, manual prompts, summaries, processing state, and context packs now use atomic file replacement to avoid exposing partial files.
- Privacy cleanup, LLM submission, and Git copy checks were separated into `ctxzip_core/` modules while preserving CLI and output behavior.
- Automatic summarization stops early with a clear error when `llm.model` contains the sample value.
- Known secret patterns are also redacted from the final prompt sent to the LLM.

### Documentation

- Added the `AGENTS.md` guide for coding agents.
- Updated the README, architecture, roadmap, technical notes, plan, and task list.
- Expanded `.gitignore` to reduce the chance of personal data entering the repository.

## [0.1.0] - 2026-09-25

### Added

- Collection of Claude Code and Codex JSONL sessions, and Antigravity Markdown artifacts.
- Readable transcripts, chapter/volume summaries, manual summarization, and `BAGLAM.md`.
- OpenAI-compatible LLM endpoint and private JSON settings.

### Known limitations

- Full Antigravity chat history is not supported; token counting is approximate.
