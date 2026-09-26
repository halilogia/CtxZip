# Contributing

CtxZip is a local-first Python CLI. Contributions should preserve archive compatibility, privacy boundaries, and the one-way dependency direction from `ctxzip.py` to `ctxzip_core/`.

## Development setup

- Use Python 3.10 or newer. Runtime dependencies are from the standard library.
- See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) for platform-specific setup and safe manual-mode scheduling.
- Clone the repository and install the staged-content guard with `python scripts/install_hook.py`. The installer preserves an existing pre-commit hook.
- Copy `ctxzip.settings.example.json` to the private `ctxzip.settings.json` only when local settings are needed. Do not commit the private file.

## Validate changes

Run the full test suite and CLI smoke check before submitting:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q ctxzip.py ctxzip_core tests scripts
python ctxzip.py --help
python scripts/check_staged.py
```

For parser, summary, storage, localization, or privacy changes, add focused tests for the affected behavior. Do not claim live provider behavior was tested unless a real provider request was made.

## Change expectations

- Keep Python filenames, symbols, comments, docstrings, and developer-facing documentation in English. Add user-facing strings to both locale catalogs.
- Preserve Turkish public aliases and existing archive directory names, persisted keys, and output filenames unless a compatibility migration is included.
- Keep modules focused and dependencies one-way. Core modules must not import `ctxzip.py`.
- Update `README.md`, `ARCHITECTURE.md`, `docs/TASKS.md`, and `CHANGELOG.md` when user-visible behavior or architecture changes.
- Use sanitized fixtures only. Never add real chats, archive data, private settings, API keys, or personal paths.
- Keep LLM prompt previews and the default approval gate. Do not weaken staged-file privacy checks.

## Pull requests

Describe the behavior change, compatibility impact, privacy implications, and validation performed. Keep changes focused and include tests that verify behavior rather than mirror implementation details.
