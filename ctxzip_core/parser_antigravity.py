"""Parser Antigravity provider parser."""
import json
from pathlib import Path
from .parser_common import Turn
from .i18n import translate
from .text import clean_text, format_timestamp, truncate_text

def parse_antigravity_turns(folder: Path, include_thinking: bool, language: str = "tr") -> tuple[list[Turn], dict]:
    turns: list[Turn] = []
    files = sorted(folder.rglob("*.md"), key=lambda entry: entry.stat().st_mtime)
    for markdown_path in files:
        turn = Turn(len(turns) + 1, format_timestamp(markdown_path.stat().st_mtime))
        turn.lines.append(f"{translate(language, 'parser_artifact')}{markdown_path.name}`:**\n\n{markdown_path.read_text(encoding='utf-8', errors='replace').strip()}")
        turns.append(turn)
    timestamps = [markdown_path.stat().st_mtime for markdown_path in files]
    metadata = {"baslangic": min(timestamps) if timestamps else None, "bitis": max(timestamps) if timestamps else None, "dal": None}
    return turns, metadata
