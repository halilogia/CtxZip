# ADR-0003: Keep the CLI dependent on focused core modules

- Status: Accepted
- Recorded: 2026-09-26

## Context

The original CLI accumulated source parsing, summary-state transitions, privacy handling, and external-system code. Continuing that structure would make provider changes and failure recovery harder to test independently.

## Decision

Keep command parsing and top-level orchestration in `ctxzip.py`; put focused domain and integration boundaries in `ctxzip_core/`. Dependencies flow from the CLI into core modules. Core modules do not import the CLI. Keep `ctxzip_core/parsers.py` as the compatibility facade while provider parsers and summary-state management remain in dedicated modules.

## Consequences

- Core behavior can be tested without invoking the CLI except at integration boundaries.
- New functionality should be added to a focused core module before expanding CLI orchestration.
- Existing Turkish Python names remain compatibility aliases; new internal names and source filenames use English.

## Evidence

- `AGENTS.md` architecture invariants
- `ctxzip_core/parser_*.py`, `ctxzip_core/parsers.py`, and `ctxzip_core/summarizing.py`
- `tests/test_architecture.py`
