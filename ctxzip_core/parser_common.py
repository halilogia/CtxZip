"""Shared parser models and source-format helpers."""
import json
import re
from pathlib import Path
from .text import clean_text, truncate_text

class Turn:
    """A user request followed by assistant activity."""

    def __init__(
        self,
        number: int | None = None,
        timestamp: str | None = None,
        *,
        no: int | None = None,
        zaman: str | None = None,
    ):
        """Accept legacy Turkish keyword names while keeping English names primary."""
        if number is not None and no is not None:
            raise TypeError("Specify either number or legacy keyword 'no', not both.")
        if timestamp is not None and zaman is not None:
            raise TypeError("Specify either timestamp or legacy keyword 'zaman', not both.")
        number = number if number is not None else no
        timestamp = timestamp if timestamp is not None else zaman
        if number is None or timestamp is None:
            raise TypeError("Turn requires a number and timestamp.")
        self.number = number
        self.timestamp = timestamp
        self.lines: list[str] = []

    def text(self) -> str:
        return "\n".join(self.lines).strip()

    # Backward-compatible properties for existing integrations and archive tests.
    no = property(lambda self: self.number, lambda self, value: setattr(self, "number", value))
    zaman = property(lambda self: self.timestamp, lambda self, value: setattr(self, "timestamp", value))
    satirlar = property(lambda self: self.lines, lambda self, value: setattr(self, "lines", value))

    def metin(self) -> str:
        return self.text()


def iter_jsonl_rows(path: Path):
    with path.open(encoding="utf-8", errors="replace") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def claude_working_directory(path: Path) -> str | None:
    for index, row in enumerate(iter_jsonl_rows(path)):
        if row.get("cwd"):
            return row["cwd"]
        if index > 200:
            break
    return None


def codex_working_directory(path: Path) -> str | None:
    for index, row in enumerate(iter_jsonl_rows(path)):
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        if cwd:
            return cwd
        # Legacy format: <environment_context><cwd>...</cwd>
        value = json.dumps(row, ensure_ascii=False)
        match = re.search(r"<cwd>(.*?)</cwd>", value)
        if match:
            return match.group(1).replace("\\\\", "\\")
        if index > 50:
            break
    return None


def is_codex_file(path: Path) -> bool:
    for index, row in enumerate(iter_jsonl_rows(path)):
        if row.get("type") in ("session_meta", "response_item", "event_msg"):
            return True
        if index > 20:
            break
    return False


def tool_summary(name: str, input_value) -> str:
    if not isinstance(input_value, dict):
        return truncate_text(input_value, 140)
    for api_key in ("description", "command", "file_path", "path", "pattern", "query", "url", "prompt", "skill"):
        if input_value.get(api_key):
            return truncate_text(input_value[api_key], 140)
    return truncate_text(json.dumps(input_value, ensure_ascii=False), 140)
