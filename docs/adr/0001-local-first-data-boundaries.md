# ADR-0001: Keep project archives local by default

- Status: Accepted
- Recorded: 2026-09-26

## Context

Session archives can contain source code, personal information, and secrets. CtxZip can also send selected text to a configured LLM provider when automatic summarization is enabled. The archive, derived summaries, and credentials therefore need explicit local and network boundaries.

## Decision

Keep collection, storage, parsing, retrieval, and context-pack generation in the local CLI. Do not require a cloud service or background daemon. Send text to an LLM only through the configured provider path, after displaying the request and receiving approval unless the user explicitly enabled approved sending. `--elle` must not make automatic LLM requests.

## Consequences

- The user controls the local archive and decides whether selected text leaves the machine.
- Privacy checks are defense in depth, not a guarantee that every secret is detected.
- Any future network or service feature needs a separate, explicit boundary and privacy review.

## Evidence

- `AGENTS.md` data boundaries
- `ctxzip_core/llm.py` and `ctxzip_core/privacy.py`
- `README.md` security and LLM behavior
