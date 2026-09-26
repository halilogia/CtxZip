"""Compatibility facade for provider parsers and localized transcript labels."""
from pathlib import Path
from .parser_common import Turn, iter_jsonl_rows, claude_working_directory, codex_working_directory, is_codex_file, tool_summary
from .text import truncate_text
from .parser_claude import parse_claude_turns
from .parser_codex import parse_codex_turns
from .parser_antigravity import parse_antigravity_turns
from .parser_manual import parse_manual_turns

PARSERS = {"claude-code": parse_claude_turns, "codex": parse_codex_turns, "antigravity": parse_antigravity_turns, "elle": parse_manual_turns}

def read_session(tool_name: str, path: Path, settings: dict, language: str = "tr"):
    turns, metadata = PARSERS[tool_name](path, settings["dusunceleri_dahil_et"], language)
    return [turn for turn in turns if turn.text()], metadata

# Backward-compatible Turkish API aliases.
jsonl_satirlari = iter_jsonl_rows
claude_cwd = claude_working_directory
codex_cwd = codex_working_directory
codex_dosyasi_mi = is_codex_file
arac_ozeti = tool_summary
kisalt = truncate_text
truncate_text_short = truncate_text
claude_turlari = parse_claude_turns
codex_turlari = parse_codex_turns
antigravity_turlari = parse_antigravity_turns
elle_turlari = parse_manual_turns
OKUYUCULAR = PARSERS
oturum_oku = read_session
Tur = Turn
