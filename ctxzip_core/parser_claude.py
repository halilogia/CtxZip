"""Parser Claude provider parser."""
import json
from pathlib import Path
from .parser_common import Turn, iter_jsonl_rows, tool_summary
from .i18n import translate
from .text import clean_text, format_timestamp, truncate_text

def parse_claude_turns(path: Path, include_thinking: bool, language: str = "tr") -> tuple[list[Turn], dict]:
    turns: list[Turn] = []
    metadata = {"baslangic": None, "bitis": None, "dal": None}
    turn: Turn | None = None
    pending_images = 0  # Attach images to the next text message when sources split them.

    def start_turn(timestamp):
        nonlocal turn, pending_images
        turn = Turn(len(turns) + 1, timestamp)
        turns.append(turn)
        if pending_images:
            turn.lines.append(translate(language, "parser_image_attached", count=pending_images))
            pending_images = 0

    for row in iter_jsonl_rows(path):
        timestamp = row.get("timestamp")
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
            start_turn(format_timestamp(timestamp))
            turn.lines.append(f"{translate(language, 'parser_user_command')} `/{command_run.get('command', '')}` {truncate_text(command_run.get('args', ''), 2000)}")
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if entry_type == "user":
            if row.get("isCompactSummary"):
                start_turn(format_timestamp(timestamp))
                turn.lines.append(translate(language, "parser_compacted"))
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
                            c = block.get("content")
                            c = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                            turn.lines.append(f"{translate(language, 'parser_tool_error')}{truncate_text(c, 200)}")
                if has_result and not any(entry for entry in parts if entry):
                    continue
            text = "\n".join(entry for entry in parts if entry).strip()
            if not text:
                pending_images += image_count
                continue
            if text.startswith("<command-") or text.startswith("<local-command"):
                continue
            pending_images += image_count
            start_turn(format_timestamp(timestamp))
            turn.lines.append(f"{translate(language, 'parser_user')} {text}")
        elif entry_type == "assistant" and isinstance(content, list):
            if turn is None:
                start_turn(format_timestamp(timestamp))
            for block in content:
                block_type = block.get("type")
                if block_type == "text" and block.get("text", "").strip():
                    turn.lines.append(f"{translate(language, 'parser_assistant')} {block['text'].strip()}")
                elif block_type == "tool_use":
                    turn.lines.append(f"  - → {block.get('name')}: {tool_summary(block.get('name'), block.get('input'))}")
                elif block_type == "thinking" and include_thinking and block.get("thinking", "").strip():
                    turn.lines.append(f"{translate(language, 'parser_reasoning')} {truncate_text(block['thinking'], 600)}")
    return turns, metadata
