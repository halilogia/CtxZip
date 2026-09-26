"""Parser Codex provider parser."""
import json
from pathlib import Path
from .parser_common import Turn, iter_jsonl_rows, tool_summary
from .i18n import translate
from .text import clean_text, format_timestamp, truncate_text

def parse_codex_turns(path: Path, include_thinking: bool, language: str = "tr") -> tuple[list[Turn], dict]:
    turns: list[Turn] = []
    metadata = {"baslangic": None, "bitis": None, "dal": None}
    turn: Turn | None = None
    for row in iter_jsonl_rows(path):
        timestamp = row.get("timestamp")
        if timestamp:
            metadata["baslangic"] = metadata["baslangic"] or timestamp
            metadata["bitis"] = timestamp
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        if row.get("type") == "session_meta":
            git = payload.get("git") or {}
            metadata["dal"] = git.get("branch") if isinstance(git, dict) else None
            continue
        pt = payload.get("type")
        if pt == "message":
            role = payload.get("role")
            text = "\n".join(
                c.get("text", "") for c in payload.get("content", []) if isinstance(c, dict)
            )
            text = clean_text(text)
            if not text or text.startswith("<environment_context>") or text.startswith("<user_instructions>") or text.startswith("# AGENTS.md"):
                continue
            if role == "user":
                turn = Turn(len(turns) + 1, format_timestamp(timestamp))
                turns.append(turn)
                turn.lines.append(f"{translate(language, 'parser_user')} {text}")
            elif role == "assistant":
                if turn is None:
                    turn = Turn(1, format_timestamp(timestamp))
                    turns.append(turn)
                turn.lines.append(f"{translate(language, 'parser_assistant')} {text}")
        elif pt in ("function_call", "custom_tool_call", "local_shell_call"):
            if turn is None:
                continue
            arguments = payload.get("arguments") or payload.get("input") or payload.get("action") or ""
            try:
                arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError:
                pass
            turn.lines.append(f"  - → {payload.get('name', pt)}: {tool_summary(payload.get('name'), arguments)}")
        elif pt == "reasoning" and include_thinking and turn is not None:
            summary = " ".join(value.get("text", "") for value in payload.get("summary", []) if isinstance(value, dict))
            if summary.strip():
                turn.lines.append(f"{translate(language, 'parser_reasoning')} {truncate_text(summary, 600)}")
    return turns, metadata
