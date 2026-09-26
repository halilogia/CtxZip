"""Read-only freshness checks for summaries derived from session turns."""
from __future__ import annotations

from collections.abc import Iterable

from .chunking import truncate_turn
from .parser_common import Turn
from .privacy import redact_secrets
from .text import text_hash


def chapter_source_hash(
    turns: Iterable[Turn],
    first_turn: int,
    last_turn: int,
    token_budget: int,
    language: str,
) -> str | None:
    """Recreate the exact sanitized source text hashed for a Chapter.

    ``None`` means the current parsed source does not contain the complete
    recorded turn interval, so freshness cannot be established.
    """
    selected = [turn for turn in turns if first_turn <= turn.number <= last_turn]
    if (
        not selected
        or selected[0].number != first_turn
        or selected[-1].number != last_turn
        or [turn.number for turn in selected] != list(range(first_turn, last_turn + 1))
    ):
        return None
    source_text = "\n\n".join(
        f"## [T{turn.number}] {turn.timestamp}\n"
        f"{truncate_turn(turn.text(), token_budget, language)}"
        for turn in selected
    )
    return text_hash(redact_secrets(source_text, language))
