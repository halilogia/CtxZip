"""Turn budgeting without crossing session boundaries."""
from .parsers import Turn
from .text import estimate_tokens
from .i18n import translate

def truncate_turn(text: str, token_budget: int, language: str = "tr") -> str:
    """Shorten a turn that exceeds the budget by itself, preserving its beginning and end (request and result)."""
    limit = int(token_budget * 3.5)
    if len(text) <= limit:
        return text
    half = limit // 2
    marker = translate(language, "turn_truncated", count=len(text) - 2 * half)
    return text[:half] + marker + text[-half:]

def group_chapters(turns: list[Turn], start_turn: int, budget: int):
    """Group turns after the starting turn by budget; never split an individual turn."""
    chunk: list[Turn] = []
    size = 0
    for turn in turns:
        if turn.number <= start_turn:
            continue
        turn_tokens = estimate_tokens(turn.text())
        if chunk and size + turn_tokens > budget:
            yield chunk, True
            chunk, size = [], 0
        chunk.append(turn)
        size += turn_tokens
    if chunk:
        yield chunk, False


# Backward-compatible Turkish API aliases.
tur_sinirla = truncate_turn
bolum_parcalari = group_chapters
