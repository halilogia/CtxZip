# Technical Notes and Verified Observations

## Verified

- The application uses the Python 3.10+ standard library; the CLI is in `ctxzip.py`. Source parsers, chapter/volume orchestration, state files, privacy cleanup, LLM submission, and Git copy checks live in `ctxzip_core/` modules.
- On 2026-09-25, CLI smoke tests for `--help`, `collect`, `transcript`, `status`, and manual summarization ran with Windows/Python 3.12. Project-specific archive names and counts are intentionally omitted. These checks do not verify summary quality or a live LLM connection.
- `raw/` is a source copy and is refreshed when the source grows. If the source shrinks, the previous copy is saved as `*.onceki.jsonl`.
- `BAGLAM.md` selects completed summaries only; selection favors recency and uses an approximate token budget.
- The final LLM submission boundary redacts known patterns again and displays the full prompt and destination. No request is sent without interactive approval; `--onayli-gonder` deliberately bypasses this approval.
- Git index checks run automatically only in clones where the hook is installed. Git hooks are not transferred with the repository and can be bypassed with `--no-verify`.
- Parser code is split into `parser_common.py` and provider modules for Claude, Codex, Antigravity, and manual input; `parsers.py` remains a facade for legacy import paths.
- The current test suite has 30 passing tests. Import/compile checks, CLI help in both languages, settings JSON validation, staged privacy checks, and diff whitespace validation also pass. These checks use synthetic data; no real LLM provider request was made.
- Python identifiers, source module filenames, comments, and docstrings are English. Remaining Turkish API names are explicit compatibility aliases; Turkish persisted keys and paths are part of the archive schema. The checked-in config example is `ctxzip.settings.example.json`; `ctxzip.settings.json` is preferred for private settings, and an existing `ctxzip_ayar.json` is selected automatically as a fallback.
- Localization catalogs are namespace-based JSON files under `locales/<locale>/<namespace>.json`, with Turkish and English catalogs, fallback, named interpolation, plural forms, and consistency validation.
- Critical derived files and source copies are written through same-directory temporary files and atomic replacement. Tests cover replacement/copy failures preserving the old target and cleaning partial files; multi-file crash reconciliation remains incomplete.

## Unknowns

- A request to a locally configured LLM endpoint's `/v1/models` route timed out. Live LLM summarization has not been verified.
- Claude Code and Codex JSONL fields may vary across versions. The Antigravity `brain/` path does not provide full chat history.
- `len(text)/3.5` is not an actual token count; the secret-pattern cleaner cannot find every secret.

## Principles

Do not put raw archives, settings, or context packs in the public repository. Re-verify test or behavior claims from summaries against the current commit and test output. Test new source formats with real examples sanitized of personal data.
