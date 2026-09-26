"""Compatibility facade for provider parsers and localized transcript labels."""
import hashlib
from pathlib import Path
from .parser_common import Turn, iter_jsonl_rows, claude_working_directory, codex_working_directory, is_codex_file, tool_summary
from .text import truncate_text
from .parser_claude import PARSER_VERSION as CLAUDE_PARSER_VERSION, parse_claude_session, parse_claude_turns
from .parser_codex import PARSER_VERSION as CODEX_PARSER_VERSION, parse_codex_session, parse_codex_turns
from .parser_antigravity import PARSER_VERSION as ANTIGRAVITY_PARSER_VERSION, parse_antigravity_turns
from .parser_manual import PARSER_VERSION as MANUAL_PARSER_VERSION, parse_manual_turns
from .parser_chatgpt import PARSER_VERSION as CHATGPT_PARSER_VERSION, parse_chatgpt_session, parse_chatgpt_turns
from .events import ParsedSession, events_from_turns, source_file_hash
from .source_capabilities import SOURCE_CAPABILITIES, SourceCapabilities, get_source_capabilities

PARSERS = {"claude-code": parse_claude_turns, "codex": parse_codex_turns, "antigravity": parse_antigravity_turns, "elle": parse_manual_turns, "chatgpt": parse_chatgpt_turns}
PARSER_VERSIONS = {
    "claude-code": CLAUDE_PARSER_VERSION,
    "codex": CODEX_PARSER_VERSION,
    "antigravity": ANTIGRAVITY_PARSER_VERSION,
    "elle": MANUAL_PARSER_VERSION,
    "chatgpt": CHATGPT_PARSER_VERSION,
}
EVENT_PARSERS = {"claude-code": parse_claude_session, "codex": parse_codex_session, "chatgpt": parse_chatgpt_session}

def read_session(tool_name: str, path: Path, settings: dict, language: str = "tr"):
    turns, metadata = PARSERS[tool_name](path, settings["dusunceleri_dahil_et"], language)
    return [turn for turn in turns if turn.text()], metadata


def read_session_events(tool_name: str, path: Path, settings: dict, language: str = "tr"):
    """Return native events or source-linked transcript events without inferring structure."""
    parser = EVENT_PARSERS.get(tool_name)
    if parser is not None:
        return parser(path, settings["dusunceleri_dahil_et"], language)

    if tool_name not in PARSERS:
        raise ValueError(f"Unknown session source: {tool_name}")

    turns, metadata = PARSERS[tool_name](path, settings["dusunceleri_dahil_et"], language)
    turns = [turn for turn in turns if turn.text()]
    source_hash = _source_content_hash(path)
    source_id = tool_name
    session_id = event_session_id(tool_name, path)
    events = events_from_turns(
        turns,
        source_id=source_id,
        session_id=session_id,
        source_hash=source_hash,
        parser_version=PARSER_VERSIONS[tool_name],
        include_timestamp=False,
    )
    return ParsedSession(turns=turns, metadata=metadata, events=events)


def event_session_id(tool_name: str, path: Path) -> str:
    """Return the event identity used for a parser input without exposing its path."""
    if tool_name in EVENT_PARSERS:
        return path.stem
    locator = str(path.resolve()).encode("utf-8", errors="surrogatepass")
    return "session:" + hashlib.sha256(locator).hexdigest()[:24]


def _source_content_hash(path: Path) -> str:
    """Hash a file or an Antigravity artifact tree without exposing its path."""
    if path.is_file():
        return source_file_hash(path)
    digest = hashlib.sha256()
    for artifact in sorted(path.rglob("*.md"), key=lambda item: item.as_posix()):
        relative_name = artifact.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative_name).to_bytes(8, "big"))
        digest.update(relative_name)
        digest.update(bytes.fromhex(source_file_hash(artifact)))
    return digest.hexdigest()


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
