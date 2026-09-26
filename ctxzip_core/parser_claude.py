"""Parser Claude provider parser."""
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


def _parse_claude(
    path: Path,
    include_thinking: bool,
    language: str,
    event_builder: EventBuilder | None,
) -> ParsedSession:
    turns: list[Turn] = []
    events = []
    metadata = {"baslangic": None, "bitis": None, "dal": None}
    turn: Turn | None = None
    pending_images = 0  # Attach images to the next text message when sources split them.

    def add_event(
        row_index: int,
        kind: EventKind,
        *,
        role: EventRole | None = None,
        text: str | None = None,
        tool_name: str | None = None,
        tool_input_summary: str | None = None,
        tool_output: str | None = None,
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
                tool_output=tool_output,
            )
        )

    row_timestamp: str | None = None

    def start_turn(timestamp: str, row_index: int) -> None:
        nonlocal turn, pending_images
        turn = Turn(len(turns) + 1, timestamp)
        turns.append(turn)
        if pending_images:
            turn.lines.append(translate(language, "parser_image_attached", count=pending_images))
            add_event(row_index, EventKind.METADATA, text=f"image_count:{pending_images}")
            pending_images = 0

    for row_index, row in enumerate(iter_jsonl_rows(path)):
        timestamp = row.get("timestamp")
        row_timestamp = str(timestamp) if timestamp is not None else None
        if timestamp:
            metadata["baslangic"] = metadata["baslangic"] or timestamp
            metadata["bitis"] = timestamp
        if row.get("gitBranch") and not metadata["dal"]:
            metadata["dal"] = row["gitBranch"]
        if row.get("isSidechain") or row.get("isMeta"):
            continue
        entry_type = row.get("type")
        if entry_type == "system" and isinstance(row.get("commandRun"), dict):
            command_run = row["commandRun"]
            start_turn(format_timestamp(timestamp), row_index)
            args = truncate_text(command_run.get("args", ""), 2000)
            command = command_run.get("command", "")
            turn.lines.append(f"{translate(language, 'parser_user_command')} `/{command}` {args}")
            add_event(
                row_index,
                EventKind.COMMAND,
                role=EventRole.USER,
                text=args,
                tool_name=str(command),
            )
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if entry_type == "user":
            if row.get("isCompactSummary"):
                start_turn(format_timestamp(timestamp), row_index)
                turn.lines.append(translate(language, "parser_compacted"))
                add_event(row_index, EventKind.METADATA, text="Conversation compacted")
                continue
            parts = []
            image_count = 0
            if isinstance(content, str):
                parts.append(clean_text(content))
            elif isinstance(content, list):
                has_result = False
                for block in content:
                    block_type = block.get("type")
                    if block_type == "text":
                        parts.append(clean_text(block.get("text", "")))
                    elif block_type == "image":
                        image_count += 1
                    elif block_type == "tool_result":
                        has_result = True
                        if block.get("is_error") and turn:
                            value = block.get("content")
                            value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                            output = truncate_text(value, 200)
                            turn.lines.append(f"{translate(language, 'parser_tool_error')}{output}")
                            add_event(
                                row_index,
                                EventKind.TOOL_RESULT,
                                role=EventRole.TOOL,
                                tool_output=output,
                            )
                if has_result and not any(entry for entry in parts if entry):
                    continue
            text = "\n".join(entry for entry in parts if entry).strip()
            if not text:
                pending_images += image_count
                continue
            if text.startswith("<command-") or text.startswith("<local-command"):
                continue
            pending_images += image_count
            start_turn(format_timestamp(timestamp), row_index)
            turn.lines.append(f"{translate(language, 'parser_user')} {text}")
            add_event(row_index, EventKind.USER_MESSAGE, role=EventRole.USER, text=text)
        elif entry_type == "assistant" and isinstance(content, list):
            if turn is None:
                start_turn(format_timestamp(timestamp), row_index)
            for block in content:
                block_type = block.get("type")
                if block_type == "text" and block.get("text", "").strip():
                    text = block["text"].strip()
                    turn.lines.append(f"{translate(language, 'parser_assistant')} {text}")
                    add_event(row_index, EventKind.ASSISTANT_MESSAGE, role=EventRole.ASSISTANT, text=text)
                elif block_type == "tool_use":
                    name = str(block.get("name") or "")
                    summary = tool_summary(name, block.get("input"))
                    turn.lines.append(f"  - → {block.get('name')}: {summary}")
                    add_event(
                        row_index,
                        EventKind.TOOL_CALL,
                        role=EventRole.ASSISTANT,
                        tool_name=name,
                        tool_input_summary=summary,
                    )
                elif block_type == "thinking" and include_thinking and block.get("thinking", "").strip():
                    # Thinking remains an opt-in transcript artifact, not canonical memory.
                    turn.lines.append(
                        f"{translate(language, 'parser_reasoning')} "
                        f"{truncate_text(block['thinking'], 600)}"
                    )
    return ParsedSession(turns=turns, metadata=metadata, events=events)


def parse_claude_session(
    path: Path, include_thinking: bool, language: str = "tr"
) -> ParsedSession:
    source_hash = source_file_hash(path)
    event_builder = EventBuilder("claude-code", path.stem, source_hash, PARSER_VERSION)
    parsed = _parse_claude(path, include_thinking, language, event_builder)
    verify_source_file_unchanged(path, source_hash)
    return parsed


def parse_claude_turns(
    path: Path, include_thinking: bool, language: str = "tr"
) -> tuple[list[Turn], dict]:
    parsed = _parse_claude(path, include_thinking, language, None)
    return parsed.turns, parsed.metadata
