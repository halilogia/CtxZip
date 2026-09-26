# AGENTS.md — CtxZip Agent Guide

This guide is for Codex, Claude Code, Antigravity, and other coding agents working in the CtxZip repository. The current behavior is defined by `ctxzip.py` and test results; historical observations in this guide do not replace current verification.

## Project purpose

CtxZip archives local sessions from different AI coding tools by project, converts them into readable transcripts, creates Chapter/Volume summaries, and prepares `BAGLAM.md` for a new conversation. It is a CLI that uses the Python 3.10+ standard library. Command orchestration lives in `ctxzip.py`; privacy, LLM, and Git boundaries live in `ctxzip_core/`.

## Before you start

1. Read `README.md`, `ARCHITECTURE.md`, and `docs/KNOWLEDGE.md`, plus `docs/PLAN.md` and/or `docs/TASKS.md` as relevant to the task.
2. Check the working tree with `git status --short`. Preserve the user's existing changes.
3. Inspect the relevant code path and source format; do not treat claims in an old summary as evidence.
4. For a new feature or behavior change, assess its impact on the README, architecture, task list, and CHANGELOG.

## Code language and project conventions

- Write new source filenames, Python symbols, variable and parameter names, comments, docstrings, and developer documentation in English. Use the localization catalogs for user-facing text; add new strings to both the TR and EN namespace catalogs.
- Do not rename existing Turkish public APIs or on-disk directory, file, or JSON-key names without assessing compatibility. When needed, add an English API, retain the old name as a compatibility alias, and document and test the migration.
- Follow universal software engineering principles: one-way dependencies, small modules with focused responsibilities, consistent naming, explicit error behavior, and focused tests that meaningfully verify behavior. Avoid unnecessary abstractions and dependencies.

## Data boundaries

- `~/CtxZip-Arsiv`, `raw/`, `dokum/`, `bolumler/`, `ciltler/`, `gelen/`, `BAGLAM.md`, `ctxzip.settings.json`, legacy `ctxzip_ayar.json`, and `.env` may contain personal data or secrets. Do not casually include them in the public repository, sample files, issues, or model prompts.
- If testing with real sessions is necessary, use only the smallest required excerpt. Remove personal data and review it again before adding it to a persistent test fixture.
- `gizli_temizle` is a limited safeguard. Do not claim that it finds every secret or that sending data to an LLM is safe.
- Automatic LLM calls are not made in `--elle` mode. Automatic summarization sends text to the selected provider; preserve this distinction.
- Do not remove the LLM preview or the default confirmation gate. `--onayli-gonder` represents only the user's explicit automation preference.
- The commit guard scans the Git index; a fresh clone requires `scripts/install_hook.py`. Do not delete or silently modify an existing hook.

## Behavioral invariants

- Raw records and current code take precedence over summaries. A summary may be wrong or out of date.
- A Chapter covers the turn range of exactly one session. The final segment of an active session waits until the closing threshold is met.
- Incomplete Chapters must not be included in a Volume or a `BAGLAM.md` context package.
- Preserve summaries manually edited by the user when rerunning the process.
- Keep `durum.json`, Chapter/Volume files, and source turn ranges consistent. Prevent data loss after partial failures.
- Do not silently change project matching, source turn/commit attribution, or context budgets.
- Preserve the dependency direction `ctxzip.py → ctxzip_core`. Core modules must not import the CLI. Keep provider parsers in small, focused `ctxzip_core/parser_*.py` modules.
- Do not describe Antigravity support as full transcripts: the current code collects the Markdown artifacts it can access.

## Verification

- At a minimum, run `python ctxzip.py --help` and a focused check of the changed command.
- If parser or summarization logic changes, prefer testing with sanitized examples in the actual source format, including reruns, growing and shrinking sources, manually edited summaries, and recovery after failure.
- Do not treat mocked or `--elle` checks as verification of network/LLM behavior. Clearly state when no real provider test was performed.
- Report the test commands and results. Do not claim untested behavior is verified.

## Documentation map

- `README.md`: user setup and limitations.
- `ARCHITECTURE.md`: data flow and layers.
- `ROADMAP.md`: target releases.
- `docs/PLAN.md`: implementation phases; `docs/TASKS.md`: open work.
- `docs/KNOWLEDGE.md`: verified technical knowledge and uncertainties.
- `CHANGELOG.md`: user-visible changes.

Finish the current task before expanding its scope; record new ideas in the relevant plan or task document.
