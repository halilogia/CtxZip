# Architecture

CtxZip is a CLI application that uses the Python 3.10+ standard library. `ctxzip.py` manages commands and data flow; security and external-system boundaries live in `ctxzip_core/`.

```text
source discovery → collect → raw/
raw/ → format parsers → dokum/
turns → summarize → bolumler/ → ciltler/
bolumler/ + ciltler/ → context → BAGLAM.md
```

| Layer | Role | Boundary |
| --- | --- | --- |
| `raw/` | Source copy | Updated as a session grows. If a source shrinks, the previous copy is saved separately. May contain sensitive data. |
| `transcripts/` (`dokum/` in existing archives) | Readable Markdown | Tool output is truncated; this does not replace the raw record. |
| `chapters/` (`bolumler/`) | Turn ranges from one session | Includes source-turn and hash metadata; summaries may be wrong. |
| `volumes/` (`ciltler/`) | Higher-level summaries of completed chapters | Detail is progressively lost. |
| `state.json` (`durum.json`) | Processed ranges and chapter/volume relationships | Processing state, not the source conversation. |
| `CONTEXT.md` (`BAGLAM.md`) | New-session context pack | Does not replace code, Git, or tests. |

## Module map

| Module | Responsibility |
| --- | --- |
| `ctxzip.py` | Settings, source discovery/copying, project selection, transcripts, context, and CLI commands |
| `ctxzip_core/parsers.py` | Parser facade for source selection and Turkish compatibility exports |
| `ctxzip_core/parser_common.py` | Shared `Turn` model, JSONL reading, working-directory discovery, and tool summaries |
| `ctxzip_core/parser_claude.py`, `parser_codex.py`, `parser_antigravity.py`, `parser_manual.py` | Provider-specific source format parsers behind the shared turn model |
| `ctxzip_core/sessions.py` | Listing archived/incoming sessions and generating short session IDs |
| `ctxzip_core/text.py` | Shared text cleanup, timestamp formatting, hashing, and approximate token counting |
| `ctxzip_core/chunking.py` | Turn budgeting and chapter chunking |
| `ctxzip_core/summary_store.py` | `durum.json`, summary metadata, body hashes, and manual-edit detection |
| `ctxzip_core/storage.py` | Atomic text/JSON replacement and metadata-preserving atomic file copies |
| `ctxzip_core/prompts.py` | Chapter/volume prompts and prompt version |
| `ctxzip_core/i18n.py` | Locale resolution, namespace catalog loading, fallback, named interpolation, and validation (`locales/<locale>/<namespace>.json`) |
| `ctxzip_core/summarizing.py` | Fills pending summaries, creates chapters/volumes, and manages state transitions for one project |
| `ctxzip_core/privacy.py`, `llm.py`, `git_safety.py` | Redaction, approval/network calls, and Git copy boundary |

Dependency direction is `ctxzip.py → ctxzip_core`. `summarizing` uses session/parser, chunking, summary-store, prompt, and LLM modules. Source parsers use `parser_common` and `text`; `sessions → parsers → parser_common`, `chunking → parsers/text`, `summary_store → text`, and `llm → privacy`. Core modules do not import the CLI; a static import-graph test checks for cycles. Older helper names are compatibility aliases on the facade and CLI. Tests mock LLM calls at the `ctxzip_core.summarizing.call_llm` boundary.

The CLI selects projects and calls `summarize_project`. If a chapter LLM call fails, the core returns `False` and the command stops instead of continuing to other projects, matching prior behavior. Write ordering, file formats, and turn numbering are preserved. English names are primary in the Python API; older Turkish names remain compatibility aliases. Turkish on-disk directory names, JSON keys, and summary metadata remain unchanged to preserve existing user archives.

A chapter never crosses a session boundary. The final chunk of an active session is held back. Incomplete chapters are excluded from volumes and context packs. A summary does not replace the source record or the current project state.

## Known architectural debt

Critical single-file outputs and source copies use same-directory temporary files and atomic replacement. Multi-file operations still lack deterministic reconciliation after interruption. If a source is rewritten or shortened within the same turn range, existing summaries are not reevaluated. State dictionaries have no formal schema; source discovery/copying, transcript generation, and context selection still live in the CLI. Coverage against real source-format versions and task-relevant summary selection are incomplete. See the [task list](docs/TASKS.md).

Before sending, `call_llm` redacts known secret patterns and previews the full prompt and destination. It makes no network request without interactive approval or the explicit `--approved-send` / `--onayli-gonder` option. For Git safety, `context --copy` / `baglam --kopyala` requires the destination file to be untracked and ignored by the target repository. `scripts/check_staged.py` scans selected index content; `scripts/install_hook.py` installs the check while preserving an existing `pre-commit` hook. These measures are not comprehensive data-loss prevention.
