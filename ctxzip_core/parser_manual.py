"""Parser Manual provider parser."""
import json
from pathlib import Path
from .parser_common import Turn, iter_jsonl_rows, tool_summary
from .text import clean_text, format_timestamp, truncate_text

PARSER_VERSION = "1"

def parse_manual_turns(path: Path, include_thinking: bool, language: str = "tr") -> tuple[list[Turn], dict]:
    turn = Turn(1, format_timestamp(path.stat().st_mtime))
    turn.lines.append(path.read_text(encoding="utf-8", errors="replace").strip())
    return [turn], {"baslangic": path.stat().st_mtime, "bitis": path.stat().st_mtime, "dal": None}
