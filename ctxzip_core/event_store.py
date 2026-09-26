"""Private, versioned snapshots of normalized session events."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .events import (
    EventKind, EventReference, EventRole, ParsedSession, SessionEvent, SourceRef,
)
from .storage import atomic_write_json


SCHEMA_ID = "ctxzip.event-snapshot"
SCHEMA_VERSION = 2
_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class EventStoreError(ValueError):
    """Raised when a persisted event snapshot is malformed or unsupported."""


def _snapshot_path(project_dir: Path, source_id: str, session_id: str) -> Path:
    if not _SOURCE_ID_PATTERN.fullmatch(source_id):
        raise EventStoreError("Invalid event source identifier")
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    return project_dir / ".ctxzip-events" / source_id / f"{session_key}.json"


def _version_snapshot_path(project_dir: Path, snapshot: dict[str, Any]) -> Path:
    source_id = snapshot["source_id"]
    session_id = snapshot["session_id"]
    if not _SOURCE_ID_PATTERN.fullmatch(source_id):
        raise EventStoreError("Invalid event source identifier")
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    parser_key = hashlib.sha256(snapshot["parser_version"].encode("utf-8")).hexdigest()
    return (
        Path(project_dir) / ".ctxzip-events" / "versions" / source_id / session_key
        / f"{snapshot['source_hash']}-{parser_key}.json"
    )


def _event_record(event) -> dict[str, Any]:
    source = event.source
    return {
        "id": event.id,
        "session_id": event.session_id,
        "sequence": event.sequence,
        "timestamp": event.timestamp,
        "kind": event.kind.value,
        "role": event.role.value if event.role is not None else None,
        "text": event.text,
        "source": {
            "source_id": source.source_id,
            "session_id": source.session_id,
            "source_hash": source.source_hash,
            "parser_version": source.parser_version,
            "turn_number": source.turn_number,
            "record_index": source.record_index,
            "record_ids": list(source.record_ids),
        },
        "tool_name": event.tool_name,
        "tool_input_summary": event.tool_input_summary,
        "tool_output": event.tool_output,
    }


def _read_snapshot(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EventStoreError("Existing event snapshot cannot be read") from error
    if not isinstance(value, dict) or value.get("schema") != SCHEMA_ID:
        raise EventStoreError("Existing event snapshot has an unknown schema")
    if value.get("schema_version") not in (1, SCHEMA_VERSION):
        raise EventStoreError("Existing event snapshot version is unsupported")
    if not all(isinstance(value.get(key), str) and value[key] for key in
               ("source_id", "session_id", "source_hash", "parser_version")):
        raise EventStoreError("Existing event snapshot has invalid source metadata")
    if not re.fullmatch(r"[0-9a-f]{64}", value["source_hash"]):
        raise EventStoreError("Existing event snapshot has invalid source hash")
    events = value.get("events")
    if (
        not isinstance(events, list)
        or any(not _valid_event_record(event, value) for event in events)
        or len({event["id"] for event in events}) != len(events)
    ):
        raise EventStoreError("Existing event snapshot has invalid events")
    return value


def _valid_event_record(event: object, snapshot: dict[str, Any]) -> bool:
    if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"]:
        return False
    source = event.get("source")
    if not isinstance(source, dict):
        return False
    sequence = event.get("sequence")
    turn_number = source.get("turn_number")
    record_index = source.get("record_index")
    record_ids = source.get("record_ids", [])
    optional_strings = ("timestamp", "text", "tool_name", "tool_input_summary", "tool_output")
    return (
        isinstance(sequence, int) and not isinstance(sequence, bool) and sequence > 0
        and isinstance(turn_number, int) and not isinstance(turn_number, bool) and turn_number >= 0
        and (record_index is None or (
            isinstance(record_index, int) and not isinstance(record_index, bool) and record_index >= 0
        ))
        and isinstance(record_ids, list)
        and all(isinstance(record_id, str) and record_id for record_id in record_ids)
        and (snapshot.get("schema_version") == 1 or "record_ids" in source)
        and all(
        source.get(field) == snapshot.get(field)
        for field in ("source_id", "session_id", "source_hash", "parser_version")
        )
        and event.get("session_id") == snapshot.get("session_id")
        and isinstance(event.get("kind"), str)
        and event["kind"] in {kind.value for kind in EventKind}
        and (event.get("role") is None or event.get("role") in {role.value for role in EventRole})
        and all(event.get(field) is None or isinstance(event.get(field), str) for field in optional_strings)
    )


def event_references_for_turn(
    project_dir: Path,
    source_id: str,
    session_id: str,
    turn_number: int,
) -> tuple[EventReference, ...]:
    """Return validated source references for every event in one archived turn."""
    if not isinstance(turn_number, int) or isinstance(turn_number, bool) or turn_number < 1:
        raise ValueError("Turn number must be a positive integer")
    path = _snapshot_path(project_dir, source_id, session_id)
    if not path.is_file():
        return ()
    snapshot = _read_snapshot(path)
    if snapshot["source_id"] != source_id or snapshot["session_id"] != session_id:
        raise EventStoreError("Event snapshot identity does not match the requested source")

    references = []
    for event in snapshot["events"]:
        source = event["source"]
        if source["turn_number"] != turn_number:
            continue
        references.append(EventReference(
            event_id=event["id"],
            source=SourceRef(
                source_id=source["source_id"],
                session_id=source["session_id"],
                source_hash=source["source_hash"],
                parser_version=source["parser_version"],
                turn_number=source["turn_number"],
                record_index=source["record_index"],
                record_ids=tuple(source.get("record_ids", ())),
            ),
        ))
    return tuple(references)


def resolve_event_reference(
    project_dir: Path,
    reference: EventReference,
) -> SessionEvent | None:
    """Resolve an event from its exact source version, including retained history."""
    source = reference.source
    if (
        not isinstance(source.source_id, str)
        or not isinstance(source.session_id, str)
        or not source.session_id
    ):
        raise ValueError("Event references require a valid source identity")
    if not isinstance(reference.event_id, str) or not reference.event_id:
        raise ValueError("Event references require an event ID")
    if (
        not isinstance(source.source_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", source.source_hash)
        or not isinstance(source.parser_version, str)
        or not source.parser_version
        or not isinstance(source.record_ids, tuple)
        or any(not isinstance(record_id, str) or not record_id for record_id in source.record_ids)
    ):
        raise ValueError("Event references require a valid source version")
    latest_path = _snapshot_path(project_dir, source.source_id, source.session_id)
    history_path = _version_snapshot_path(project_dir, {
        "source_id": source.source_id,
        "session_id": source.session_id,
        "source_hash": source.source_hash,
        "parser_version": source.parser_version,
    })
    snapshot_path = history_path if history_path.is_file() else latest_path
    if not snapshot_path.is_file():
        return None
    snapshot = _read_snapshot(snapshot_path)
    identity = ("source_id", "session_id", "source_hash", "parser_version")
    requested = {
        "source_id": source.source_id,
        "session_id": source.session_id,
        "source_hash": source.source_hash,
        "parser_version": source.parser_version,
    }
    if any(snapshot[field] != requested[field] for field in identity):
        return None
    for event in snapshot["events"]:
        if event["id"] != reference.event_id:
            continue
        event_source = event["source"]
        if (
            event_source["turn_number"] != source.turn_number
            or event_source["record_index"] != source.record_index
            or tuple(event_source.get("record_ids", ())) != source.record_ids
        ):
            return None
        try:
            source_value = dict(event_source)
            source_value["record_ids"] = tuple(event_source.get("record_ids", ()))
            return SessionEvent(
                id=event["id"],
                session_id=event["session_id"],
                sequence=event["sequence"],
                timestamp=event["timestamp"],
                kind=EventKind(event["kind"]),
                role=EventRole(event["role"]) if event["role"] is not None else None,
                text=event["text"],
                source=SourceRef(**source_value),
                tool_name=event["tool_name"],
                tool_input_summary=event["tool_input_summary"],
                tool_output=event["tool_output"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise EventStoreError("Referenced event snapshot has an invalid event shape") from error
    return None


def save_session_events(project_dir: Path, parsed: ParsedSession) -> bool:
    """Atomically replace a session snapshot when its source/parser version changes.

    Returns True when a new snapshot is written. Malformed or unsupported snapshots
    are preserved and rejected instead of being silently overwritten.
    """
    if not parsed.events:
        return False
    first = parsed.events[0]
    source = first.source
    if not isinstance(source.session_id, str) or not source.session_id.strip():
        raise EventStoreError("Invalid event session identifier")
    # Per-event turn/index details vary; only source identity/version must agree.
    if any(
        event.session_id != first.session_id
        or event.source.source_id != source.source_id
        or event.source.session_id != source.session_id
        or event.source.source_hash != source.source_hash
        or event.source.parser_version != source.parser_version
        for event in parsed.events
    ):
        raise EventStoreError("Events do not share one source snapshot")

    target = _snapshot_path(project_dir, source.source_id, source.session_id)
    snapshot = {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "source_id": source.source_id,
        "session_id": source.session_id,
        "source_hash": source.source_hash,
        "parser_version": source.parser_version,
        "events": [_event_record(event) for event in parsed.events],
    }
    current = None
    if target.exists():
        current = _read_snapshot(target)
        if current["source_id"] != snapshot["source_id"] or current["session_id"] != snapshot["session_id"]:
            raise EventStoreError("Existing event snapshot identity does not match its storage key")
        identity = ("source_id", "session_id", "source_hash", "parser_version")
    version_target = _version_snapshot_path(project_dir, snapshot)
    if version_target.exists():
        archived = _read_snapshot(version_target)
        if archived != snapshot:
            raise EventStoreError("A different event snapshot already uses this source version")
    else:
        version_target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(version_target, snapshot)
    if current == snapshot:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target, snapshot)
    return True


def remove_session_events(project_dir: Path, source_id: str, session_id: str) -> bool:
    """Remove the latest event view after retaining its exact source version."""
    target = _snapshot_path(project_dir, source_id, session_id)
    if not target.exists():
        return False
    current = _read_snapshot(target)
    version_target = _version_snapshot_path(project_dir, current)
    if version_target.exists():
        archived = _read_snapshot(version_target)
        if archived != current:
            raise EventStoreError("A different event snapshot already uses this source version")
    else:
        version_target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(version_target, current)
    target.unlink()
    parent = target.parent
    try:
        parent.rmdir()
    except OSError:
        pass
    return True
