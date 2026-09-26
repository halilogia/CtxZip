"""Parser and local importer for ChatGPT conversations.json exports.

The adapter intentionally supports one documented export shape: a JSON array of
conversation objects with a ``mapping`` message tree and ``current_node``.
Keep the original export in ``gelen/``; per-conversation files are derived
working copies used by the existing session pipeline.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .events import EventBuilder, EventKind, ParsedSession
from .parser_common import Turn
from .i18n import translate
from .text import clean_text, format_timestamp


PARSER_VERSION = "2"
MAX_EXPORT_BYTES = 256 * 1024 * 1024


def iter_conversations(export_path: Path, language: str = "tr"):
    """Yield validated conversations from the supported ChatGPT export shape."""
    if export_path.stat().st_size > MAX_EXPORT_BYTES:
        raise ValueError(translate(language, "chatgpt_export_too_large"))
    try:
        data = json.loads(export_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(translate(language, "chatgpt_export_invalid")) from error
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError(translate(language, "chatgpt_export_shape"))
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError(translate(language, "chatgpt_export_missing_id"))
        conversation_id = item["id"]
        if conversation_id in seen:
            raise ValueError(translate(language, "chatgpt_export_duplicate_id"))
        seen.add(conversation_id)
        if not isinstance(item.get("mapping"), dict) or not (
            isinstance(item.get("current_node"), str)
            or (item.get("current_node") is None and not item["mapping"])
        ):
            raise ValueError(translate(language, "chatgpt_export_conversation_shape"))
        _active_nodes(item, language)
        yield item


def conversation_key(conversation_id: str) -> str:
    """Return a filesystem-safe stable key without exposing provider IDs."""
    return hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:24]


def _active_nodes(conversation: dict, language: str) -> list[tuple[str, dict]]:
    mapping = conversation["mapping"]
    current = conversation.get("current_node")
    if current is None and not mapping:
        return []
    reverse_path: list[tuple[str, dict]] = []
    visited: set[str] = set()
    while current:
        if current in visited:
            raise ValueError(translate(language, "chatgpt_session_cycle"))
        visited.add(current)
        node = mapping.get(current)
        if not isinstance(node, dict):
            raise ValueError(translate(language, "chatgpt_session_missing_node"))
        reverse_path.append((current, node))
        parent = node.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise ValueError(translate(language, "chatgpt_session_parent"))
        current = parent
    return list(reversed(reverse_path))


def import_conversations(export_path: Path, output_dir: Path, language: str = "tr") -> tuple[int, int]:
    """Materialize one derived JSON source per conversation; leave export untouched."""
    conversations = list(iter_conversations(export_path, language))
    created = updated = 0
    output_dir.mkdir(parents=True, exist_ok=True)
    for conversation in conversations:
        target = output_dir / f"{conversation_key(conversation['id'])}.json"
        content = json.dumps(conversation, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if target.exists() and target.read_text(encoding="utf-8") == content:
            continue
        from .storage import atomic_write_text

        existed = target.exists()
        atomic_write_text(target, content)
        if existed:
            updated += 1
        else:
            created += 1
    return created, updated


def parse_chatgpt_turns(path: Path, include_thinking: bool = False, language: str = "tr"):
    """Parse the active parent chain into user/assistant turns."""
    del include_thinking
    conversation = _read_conversation(path, language)
    turns, metadata, _record_ids = _parse_chatgpt_conversation(conversation, language)
    return turns, metadata


def _read_conversation(path: Path, language: str) -> dict:
    try:
        content = path.read_bytes()
        if len(content) > MAX_EXPORT_BYTES:
            raise ValueError(translate(language, "chatgpt_export_too_large"))
        conversation = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(translate(language, "chatgpt_session_invalid")) from error
    if not isinstance(conversation, dict) or not isinstance(conversation.get("mapping"), dict):
        raise ValueError(translate(language, "chatgpt_session_shape"))
    return conversation


def _parse_chatgpt_conversation(conversation: dict, language: str):
    """Return legacy turns plus source mapping IDs grouped by turn."""
    if conversation.get("current_node") is None and not conversation["mapping"]:
        return [], {"baslangic": None, "bitis": None, "dal": None}, []
    if not isinstance(conversation.get("current_node"), str):
        raise ValueError(translate(language, "chatgpt_session_shape"))
    metadata = {"baslangic": None, "bitis": None, "dal": None}
    turns: list[Turn] = []
    turn_record_ids: list[list[str]] = []
    for node_id, node in _active_nodes(conversation, language):
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        author = message.get("author")
        role = author.get("role") if isinstance(author, dict) else None
        if role not in ("user", "assistant"):
            continue
        content = message.get("content")
        parts = content.get("parts", []) if isinstance(content, dict) else []
        if not isinstance(parts, list):
            continue
        text_parts = [clean_text(part) for part in parts if isinstance(part, str) and part.strip()]
        if not text_parts:
            continue
        raw_time = message.get("create_time")
        timestamp = _timestamp(raw_time)
        if timestamp:
            metadata["baslangic"] = metadata["baslangic"] or raw_time
            metadata["bitis"] = raw_time
        if role == "user" or not turns:
            turns.append(Turn(len(turns) + 1, timestamp))
            turn_record_ids.append([])
        turns[-1].lines.extend(text_parts)
        turn_record_ids[-1].append(node_id)
    return turns, metadata, turn_record_ids


def parse_chatgpt_session(path: Path, include_thinking: bool, language: str = "tr") -> ParsedSession:
    del include_thinking
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ValueError(translate(language, "chatgpt_session_invalid")) from error
    if len(content) > MAX_EXPORT_BYTES:
        raise ValueError(translate(language, "chatgpt_export_too_large"))
    try:
        conversation = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(translate(language, "chatgpt_session_invalid")) from error
    if not isinstance(conversation, dict) or not isinstance(conversation.get("mapping"), dict):
        raise ValueError(translate(language, "chatgpt_session_shape"))
    turns, metadata, turn_record_ids = _parse_chatgpt_conversation(conversation, language)
    source_hash = hashlib.sha256(content).hexdigest()
    session_id = path.stem
    builder = EventBuilder("chatgpt", session_id, source_hash, PARSER_VERSION)
    events = []
    for turn, record_ids in zip(turns, turn_record_ids):
        events.append(builder.build(
            # One turn can merge multiple mapping nodes, so its ordinal is not
            # a valid source-record index.
            record_index=None, record_ids=record_ids, turn_number=turn.number,
            timestamp=turn.timestamp,
            kind=EventKind.TURN_TRANSCRIPT, text=turn.text(),
        ))
    return ParsedSession(turns, metadata, events)


def _timestamp(value) -> str:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return ""
    if isinstance(value, str):
        return format_timestamp(value)
    return ""
