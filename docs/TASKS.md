# Tasks

`[ ]` open, `[x]` complete.

## P0 — Data reliability

- [x] Add one minimized, content-scrubbed real-format Claude Code and Codex JSONL fixture; broader schema/version variants remain open.
- [x] Add a clearly synthetic Codex tool-heavy fixture and normalized event golden for function/custom/local-shell calls and opt-in reasoning; this tests parser branches but does not validate new upstream schemas.
- [x] Add a clearly synthetic Claude tool-heavy fixture and normalized event golden for tool calls, error results, and `commandRun`; observed upstream schema variants remain open.
- [x] Verify with synthetic records that rerunning `collect → transcript → summarize`, source growth/shrinkage, and continuation after an LLM error do not create duplicate chapters.
- [x] Preserve replaced JSONL source versions across growth, shrinkage, and rewrite using content-addressed names; verify repeat collection reuses history and does not list old versions as active sessions.
- [x] Resolve exact archived JSONL/ChatGPT source versions from source ID, session ID, and SHA-256 provenance; verify old event references remain resolvable after a source update.
- [x] Preserve normalized event snapshots by source hash and parser version, including active-source removal; resolve old references and fault-inject history/latest write failures.
- [x] Extend event snapshots to schema v2 for source record IDs while keeping schema v1 snapshots readable and resolvable.
- [ ] If strict event/source snapshot consistency becomes necessary, parse Claude/Codex from an immutable hashed snapshot; current before/after hashing detects persistent changes but not a change-and-restore between checks.
- [x] Feed canonical turn-transcript events into recent raw context selection, bridging legacy parsed turns when needed and keeping opt-in Claude private thinking outside canonical events.
- [x] Use atomic replacement for source copies, transcripts, summary prompts/files, `durum.json`, and context packs; cover failed replacement/copy behavior.
- [x] Add personal-path and common-secret scanning for the Git index, plus LLM preview and approval before network calls.
- [x] Show a clear error and `--manual` guidance when the model name is empty or still set to the sample value.
- [ ] Measure coverage for detecting unknown secrets and personal information against real sanitized examples.

## P1 — Coverage and correctness

- [ ] Validate the Antigravity format with a real example; improve project matching.
- [x] Import ChatGPT `conversations.json` and numbered conversation JSON files from `gelen/` as separate sessions; verify source preservation and rerun idempotence with a sanitized synthetic fixture.
- [ ] Validate the ChatGPT adapter against a real sanitized export and additional schema/version variants.
- [x] Verify with synthetic tests that user edits to completed chapters/volumes survive reruns and are included in volume prompts.
- [ ] Build an evaluation set for source-turn/commit attribution and summary accuracy.
- [x] Add an initial synthetic, manually labeled evaluator for parser event attribution, summary claim support/citations, and Git-bound test freshness; real-session and representative summary-accuracy evidence remains open.
- [x] Select existing structured decisions, constraints, test evidence, file mentions, open tasks/questions, Git state, and task-relevant summaries for `BAGLAM.md`.
- [x] Core lexical selector with task/file/commit inputs; preserve current behavior without inputs; explain included-summary matches.
- [x] Add exact symbol/current-diff-path signals and stale metadata penalty; path-scoped file mentions are marked possibly stale when their exact path changes in the current worktree.
- [x] Add optional validity paths and Git HEAD baselines to decisions/constraints; read schema v1/v2 records and migrate to v3 on the next collection write.
- [x] Explain context items omitted by the token budget, including estimated cost and source references.
- [x] Add an initial sanitized retrieval evaluation set and compare task-aware ranking with recency using relevance, stale-context, token-efficiency, and source-coverage metrics.
- [x] Add independently reviewed synthetic relevance judgments for two task/content cases and measure irrelevant selections on an unanswerable query.
- [x] Expand sanitized evaluation regressions across Chapter/Volume source types, equal-score ties, empty results, multi-source coverage, and stale/current changed-source ranking.
- [ ] Establish a representative benchmark across sanitized real tasks and sources before treating scores as general quality evidence; current two independently reviewed cases are synthetic checks only.
- [x] Add versioned task, decision, constraint, test, open-question, and file-mention records outside `durum.json`; require event provenance and authoring status for knowledge claims.
- [x] Add localized user-authored CLI capture for event-backed knowledge; keep automatic extraction disabled and transcript-only providers explicit.
- [x] Tie granular session events to source hashes, parser versions, and source-record indexes.
- [x] Reject Claude/Codex/ChatGPT event parses when a source changes between hash capture and parse completion.
- [x] Do not expose a ChatGPT turn ordinal as a source-record index; retain explicit turn-level attribution until source-node IDs are modeled.
- [x] Retain active ChatGPT mapping-node keys as `record_ids` on turn-level event references; keep `record_index` empty for aggregated turns.
- [ ] Validate ChatGPT mapping-node IDs against real sanitized export variants; current schema coverage is synthetic.
- [x] Record parser versions with new Chapter source hashes and exclude unedited summaries when the current adapter version differs; bump provider `PARSER_VERSION` when normalized interpretation changes.
- [x] Mark a summary possibly stale when an explicitly referenced repository path changes in the supplied worktree snapshot; preserve the summary file and show the label in generated context.
- [x] Read optional summary frontmatter `validity_paths` and `validity_head_sha`; flag changed scoped paths or a different current HEAD without rewriting the summary.
- [x] Add a localized summary-validity command that records user-reviewed paths at a clean tracked Git HEAD while preserving the summary body and manual-edit marker.
- [ ] Generate comprehensive validity baselines for every claim in a summary; current baselines remain limited to paths explicitly reviewed and supplied by the user.
- [x] Define scoped test evidence with command/result/time, Git SHA, and working-tree fingerprint; classify freshness against a current Git snapshot.
- [x] Capture runs executed through the explicit `test-run` CLI wrapper and keep mismatched evidence historical when building context; arbitrary external test invocations are not intercepted.
- [x] Add up to 20 latest source turns outside recorded Chapter ranges to the balanced profile raw-turn allocation with session/turn/hash provenance.
- [x] During context generation, compare available Chapter source hashes with current turns; exclude changed/shortened Chapters and containing Volumes without overwriting user edits.
- [x] Recover sequential and non-sequential orphan Chapters/Volumes after output/state failures when embedded metadata proves identity; preserve files, allocate future numbers after the maximum, and block malformed or ambiguous files unchanged.
- [x] Exclude lower-ranked summaries only when higher-ranked candidates fully cover their source-turn ranges; retain partial overlaps and manually edited summaries, explain exclusions, and avoid guessing incomplete provenance.
- [x] Add a sanitized partial-overlap retrieval case that measures unique-turn coverage and duplicate-turn trade-offs.
- [x] Measure summaries with incomplete source-range provenance separately and verify they remain eligible during overlap filtering; whether retained legacy text is actually unique still requires labeled source data.
- [x] Exercise the production context builder end to end with a sanitized source fixture, stale Chapter/Volume filtering, source-linked knowledge, Git metadata, and token-budget assertions.
- [ ] Define recovery for metadata-less/contradictory orphan files and reconcile missing legacy source hashes/parser versions only when provenance is sufficient; measure partial-overlap duplication on independently labeled cases.

## P2 — Usability

- [x] Document Python installation, private settings, and unattended manual-mode scheduling for Windows Task Scheduler, macOS launchd, and Linux systemd user timers; avoid scheduled provider sends by default.
- [x] Add a read-only `doctor` command for settings, parser registry versions, configured source roots, localization, archive writability, LLM configuration, Git, and commit guard diagnostics without printing secrets or contacting providers.
- [x] Add `.editorconfig` with settings aligned to UTF-8, LF repository blobs, and existing Python/JSON indentation.
- [x] Add a concise `CONTRIBUTING.md` with setup, privacy, architecture, and local verification expectations.
- [x] Record verifiable current architecture contracts in small ADRs without asserting an undocumented historical approval.
- [x] Add `docs/PROJECT_HANDOFF.md` for this active multi-step effort with the last verified date, base commit, worktree state, tests, and next actions; refresh or remove it when the effort ends.
- [ ] Add `SECURITY.md` with supported versions after a real, monitored vulnerability-reporting channel is verified.
- [ ] Review `LICENSE` provenance and attribution; its header names Godot AI Sidebar, so do not rewrite it until ownership/history is confirmed.
- [x] Separate privacy, LLM, and Git copy boundaries into `ctxzip_core/` modules.
- [x] Move source parsing and summary-state management into separate modules without changing behavior; preserve the CLI dependency direction and test the import graph for cycles.
- [x] Add English/Turkish CLI and summary-prompt language selection; retain Turkish command names and provide English aliases.
- [x] Add compatibility aliases for older Turkish Python symbols; keep new core API names English.
- [x] Add namespace-based Turkish/English catalogs with placeholder/plural validation and locale fallback.
- [x] Use English names for Python source files, application symbols, comments, and docstrings; use an English filename for the sample settings file.
- [x] Split source-format parsers into small provider modules with English names and retain the `parsers.py` compatibility facade.
- [x] Fault-inject Chapter/Volume state-write failures and partial collect/transcript batches; retry completes deterministic outputs without duplicate files or records.
- [x] Verify a later project can fail after an earlier project completes, then retry without duplicating the completed project's summaries.
- [x] Verify abrupt process exit before atomic replacement preserves the old file and exits after Chapter/event writes can be retried without duplicate summaries or event/transcript files.
- [x] Verify an abrupt process exit during a multi-source collection batch and confirm retry completes without duplicate source files.
- [x] Verify an abrupt exit after one project completes and another writes an orphan Chapter; retry recovers the second project without duplicating either summary.
- [x] Evaluate a schema-backed state model for summary processing state; deterministic file metadata reconciliation covers demonstrated retry cases, so a separate journal is not justified yet.
- [x] Preserve a manually edited Chapter/Volume prompt when a process exits after writing the prompt but before creating its summary file.
- [x] Exclude stale summaries from generated context when the readable source changes or shrinks within a recorded range, while preserving user edits on disk.
- [x] Move configured source discovery, project mapping, archive copying, and incoming-export collection into `ctxzip_core/source_collection.py`; preserve CLI helpers as compatibility exports.
- [x] Move per-project transcript generation, localized formatting, redaction, atomic writes, and event persistence to `ctxzip_core/transcripts.py`.
- [x] Move context-pack selection, freshness checks, Markdown rendering, atomic output, and safe optional copy into `ctxzip_core/context_generation.py`; keep project selection and the public `build_context` wrapper in the CLI.
- [ ] Design an MCP interface.

## P3 — Context engine foundations

- [x] Define and test a provider capability registry; declare Antigravity Markdown-artifact coverage accurately.
- [x] Pin normalized Claude/Codex event outputs for the sanitized baseline fixtures and run the personal-data/secret allowlist against those goldens.
- [x] Verify that an incomplete trailing JSONL row from an interrupted write does not discard preceding complete Claude/Codex events.
- [x] Define an immutable provider-neutral event envelope and deterministic source/version-linked IDs; bridge existing turns without changing parser or archive behavior.
- [x] Emit granular, source-version-linked message/tool/metadata events for Claude Code and Codex; validate event shapes with sanitized parser fixtures and synthetic tool-call records.
- [x] Add source-linked transcript-event coverage for Antigravity Markdown artifacts and manual imports without inferring message roles or tool structure; declared limitations remain explicit.
- [x] Persist canonical events as atomically replaced schema-versioned per-session snapshots and refresh them when the archived source hash or parser version changes; reconcile changed/deleted Antigravity artifacts only after complete source inventory and preserve prior versions.
- [x] Keep narrative summaries separate from versioned, source-linked decisions, constraints, test observations, open questions, and file/symbol mentions in per-type collections.
- [x] Capture Git branch/HEAD, dirty state, staged/unstaged diffs, changed paths, untracked-content hashes, and deterministic worktree fingerprints through a read-only core API.
- [x] Store test evidence with Git/worktree fingerprints and classify it as current, stale, or unknown against a later snapshot.
- [x] Require user confirmation before a decision can supersede another; update the old/new records atomically.
- [x] Define conservative constraint invalidation: only a user-confirmed replacement in the same scope can invalidate an active constraint, and the transition is atomic.
- [ ] Define broader cross-scope conflict rules before automatic knowledge extraction.
- [x] Add omission explanations, freshness labeling, and priority/balanced context-budget profiles with explicit raw-turn and safety reserves.
- [x] Allocate balanced-profile budget to recent unsummarized raw turns; turn-range exclusion prevents overlap with tracked Chapters.
- [x] Recover metadata-backed orphan summaries, including number gaps, without rewriting their bodies; keep future numbering collision-free.
- [x] Exclude fully redundant Chapter/Volume source ranges while retaining partial overlaps and user-edited summaries.
- [ ] Resolve overlap for rewritten sources with incomplete provenance and ambiguous orphan files; measure duplication and source coverage on representative cases.
- [x] Define a versioned context-pack metadata contract with Git/source provenance while preserving `BAGLAM.md`; ignore/protect the future `CONTEXT.md` output name.
- [x] Build a small sanitized retrieval evaluation harness and compare task-aware selection with recency-only selection.
- [x] Measure ranking after source-range exclusion and the production context budget planner, including fixed context items that consume budget.
- [ ] Establish a representative benchmark before using scores to tune relevance weights or make general quality claims.

## P4 — Conditional scale and integrations

- [ ] Measure representative sanitized archive/query scale before selecting SQLite/FTS or another index; a synthetic candidate-count benchmark now exists but does not model disk I/O or real archive distributions.
- [ ] Evaluate semantic retrieval only after lexical retrieval, provenance, and freshness have measurable baselines.
- [ ] Add source adapters only when the format has a known, testable access path and documented capabilities.
- [ ] Revisit MCP and automatic session lifecycle integration after the local context engine is stable and demand is demonstrated.
- [ ] Define stable schema and archive migration guarantees before a 1.0 release.

## Documentation

- [x] Write/update the README, architecture, roadmap, changelog, technical notes, plan, and task list.
- [ ] Finish the staged-documentation audit: ADRs and contribution/installation guides exist; add `SECURITY.md` only after a real monitored vulnerability-reporting path is verified, and review all contributed examples for privacy.
- [ ] Keep research-source citations portable and review all examples for personal project names, archive counts, paths, and secrets before publication. Current untracked Markdown research files contain 435 opaque `turn...search...` source references; their PDF companions contain URL references. One named-user example was generalized. Common secret/path patterns had no matches, but this is not full PII review. Do not stage the sources until source-reference mapping and the remaining privacy review are resolved.
- [x] Expand `.gitignore` to protect personal data.
