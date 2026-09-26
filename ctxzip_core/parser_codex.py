"""Parser Codex provider parser."""
import json
from pathlib import Path

from .events import (
    EventBuilder,
    EventKind,
    EventRole,
    ParsedSession,
    source_file_hash,
    verify_source_file_unchanged,
)
from .i18n import translate
from .parser_common import Turn, iter_jsonl_rows, tool_summary
from .text import clean_text, format_timestamp, truncate_text


PARSER_VERSION = "1"


def _parse_codex(
    path: Path,
    include_thinking: bool,
    language: str,
    event_builder: EventBuilder | None,
) -> ParsedSession:
    turns: list[Turn] = []
    events = []
    metadata = {"baslangic": None, "bitis": None, "dal": None}
    turn: Turn | None = None
    row_timestamp: str | None = None

    def add_event(
        row_index: int,
        kind: EventKind,
        *,
        role: EventRole | None = None,
        text: str | None = None,
        tool_name: str | None = None,
        tool_input_summary: str | None = None,
    ) -> None:
        if event_builder is None:
            return
        events.append(
            event_builder.build(
                record_index=row_index,
                turn_number=turn.number if turn is not None else 0,
                timestamp=row_timestamp,
                kind=kind,
                role=role,
                text=text,
                tool_name=tool_name,
                tool_input_summary=tool_input_summary,
            )
        )

    for row_index, row in enumerate(iter_jsonl_rows(path)):
        timestamp = row.get("timestamp")
        row_timestamp = str(timestamp) if timestamp is not None else None
        if timestamp:
            metadata["baslangic"] = metadata["baslangic"] or timestamp
            metadata["bitis"] = timestamp
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        if row.get("type") == "session_meta":
            git = payload.get("git") or {}
            metadata["dal"] = git.get("branch") if isinstance(git, dict) else None
            if metadata["dal"]:
                add_event(
                    row_index,
                    EventKind.METADATA,
                    role=EventRole.SYSTEM,
                    text=f"branch:{metadata['dal']}",
                )
            continue
        payload_type = payload.get("type")
        if payload_type == "message":
            role = payload.get("role")
            text = "\n".join(
                content.get("text", "")
                for content in payload.get("content", [])
                if isinstance(content, dict)
            )
            text = clean_text(text)
            if (
                not text
                or text.startswith("<environment_context>")
                or text.startswith("<user_instructions>")
                or text.startswith("# AGENTS.md")
            ):
                continue
            if role == "user":
                turn = Turn(len(turns) + 1, format_timestamp(timestamp))
                turns.append(turn)
                turn.lines.append(f"{translate(language, 'parser_user')} {text}")
                add_event(row_index, EventKind.USER_MESSAGE, role=EventRole.USER, text=text)
            elif role == "assistant":
                if turn is None:
                    turn = Turn(1, format_timestamp(timestamp))
                    turns.append(turn)
                turn.lines.append(f"{translate(language, 'parser_assistant')} {text}")
                add_event(row_index, EventKind.ASSISTANT_MESSAGE, role=EventRole.ASSISTANT, text=text)
        elif payload_type in ("function_call", "custom_tool_call", "local_shell_call"):
            if turn is None:
                continue
            arguments = payload.get("arguments") or payload.get("input") or payload.get("action") or ""
            try:
                arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError:
                pass
            name = str(payload.get("name") or payload_type)
            summary = tool_summary(payload.get("name"), arguments)
            turn.lines.append(f"  - → {payload.get('name', payload_type)}: {summary}")
            add_event(
                row_index,
                EventKind.TOOL_CALL,
                role=EventRole.ASSISTANT,
                tool_name=name,
                tool_input_summary=summary,
            )
        elif payload_type == "reasoning" and include_thinking and turn is not None:
            summary = " ".join(
                value.get("text", "")
                for value in payload.get("summary", [])
                if isinstance(value, dict)
            )
            if summary.strip():
                visible_summary = truncate_text(summary, 600)
                turn.lines.append(f"{translate(language, 'parser_reasoning')} {visible_summary}")
                add_event(
                    row_index,
                    EventKind.REASONING_SUMMARY,
                    role=EventRole.ASSISTANT,
                    text=visible_summary,
                )
    return ParsedSession(turns=turns, metadata=metadata, events=events)


def parse_codex_session(
    path: Path, include_thinking: bool, language: str = "tr"
) -> ParsedSession:
    source_hash = source_file_hash(path)
    event_builder = EventBuilder("codex", path.stem, source_hash, PARSER_VERSION)
    parsed = _parse_codex(path, include_thinking, language, event_builder)
    verify_source_file_unchanged(path, source_hash)
    return parsed


def parse_codex_turns(
    path: Path, include_thinking: bool, language: str = "tr"
) -> tuple[list[Turn], dict]:
    parsed = _parse_codex(path, include_thinking, language, None)
    return parsed.turns, parsed.metadata
