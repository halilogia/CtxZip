# Changelog

## [Unreleased]

### Added

- Turkish and English CLI/localized prompts via `language`, `--language`, or `CTXZIP_LANG`; English command aliases are available alongside Turkish commands.
- Extensible namespace-based JSON locale catalogs with named interpolation, plural forms, locale normalization, and catalog consistency validation.
- English-first Python API names with Turkish compatibility aliases; persisted archive names and keys remain stable.
- Renamed the checked-in sample configuration to `ctxzip.settings.example.json` and made `ctxzip.settings.json` the preferred private settings filename; existing `ctxzip_ayar.json` files still load automatically.
- Regression tests using synthetic records for reruns, source growth/shrinkage, manual edits, continuation after LLM errors, redaction, and the import graph.
- Full-prompt and destination preview before LLM calls, with interactive approval by default.
- Explicit `--onayli-gonder` option for non-interactive automation.
- Personal-output, common-secret, and user-path scanning for selected Git files; a hook installer that preserves an existing hook.
- Ignore/tracking checks in the target Git repository for `baglam --kopyala`.

### Changed

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
