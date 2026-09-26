"""Provider-neutral, versioned references for normalized session events."""
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Protocol


class TurnLike(Protocol):
    number: int
    timestamp: str

    def text(self) -> str: ...


class EventKind(str, Enum):
    """Kinds available to adapters as provider coverage is expanded."""

    TURN_TRANSCRIPT = "turn_transcript"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    REASONING_SUMMARY = "reasoning_summary"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FILE_EDIT = "file_edit"
    COMMAND = "command"
    TEST_RESULT = "test_result"
    SYSTEM = "system"
    METADATA = "metadata"


class EventRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass(frozen=True)
class SourceRef:
    """Identify the exact parser/source version behind an event."""

    source_id: str
    session_id: str
    source_hash: str
    parser_version: str
    turn_number: int
    record_index: int | None
    record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventReference:
    """Reference one normalized event and the exact source version behind it."""

    event_id: str
    source: SourceRef


@dataclass(frozen=True)
class SessionEvent:
    """Normalized event envelope; transcript text is retained without reinterpretation."""

    id: str
    session_id: str
    sequence: int
    timestamp: str | None
    kind: EventKind
    role: EventRole | None
    text: str | None
    source: SourceRef
    tool_name: str | None = None
    tool_input_summary: str | None = None
    tool_output: str | None = None


@dataclass(frozen=True)
class ParsedSession:
    """Additive rich parser result; legacy callers can continue using turns only."""

    turns: list[TurnLike]
    metadata: dict[str, object]
    events: list[SessionEvent]


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def source_file_hash(path: Path) -> str:
    """Hash source bytes without loading a potentially large session into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_file_unchanged(path: Path, expected_hash: str) -> None:
    """Reject a parse result if its source changed after provenance was captured."""
    if source_file_hash(path) != expected_hash:
        raise RuntimeError(f"Session source changed while it was being parsed: {path.name}")


class EventBuilder:
    """Assign stable IDs and exact source references to parser-emitted events."""

    def __init__(self, source_id: str, session_id: str, source_hash: str, parser_version: str):
        if not _SHA256_PATTERN.fullmatch(source_hash):
            raise ValueError("source_hash must be a lowercase SHA-256 hex digest")
        if not source_id or not session_id or not parser_version:
            raise ValueError("source_id, session_id, and parser_version are required")
        self.source_id = source_id
        self.session_id = session_id
        self.source_hash = source_hash
        self.parser_version = parser_version
        self._sequence = 0

    def build(
        self,
        *,
        record_index: int | None,
        record_ids: Iterable[str] = (),
        turn_number: int,
        timestamp: str | None,
        kind: EventKind,
        role: EventRole | None = None,
        text: str | None = None,
        tool_name: str | None = None,
        tool_input_summary: str | None = None,
        tool_output: str | None = None,
    ) -> SessionEvent:
        self._sequence += 1
        record_ids = tuple(record_ids)
        if any(not isinstance(record_id, str) or not record_id for record_id in record_ids):
            raise ValueError("record_ids must contain non-empty strings")
        identity_fields = {
                "source_id": self.source_id,
                "session_id": self.session_id,
                "source_hash": self.source_hash,
                "parser_version": self.parser_version,
                "record_index": record_index,
                "turn_number": turn_number,
                "sequence": self._sequence,
                "kind": kind.value,
            }
        # Preserve stable IDs for all existing events that lack source record IDs.
        if record_ids:
            identity_fields["record_ids"] = record_ids
        identity = json.dumps(
            identity_fields,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return SessionEvent(
            id="event:" + hashlib.sha256(identity).hexdigest(),
            session_id=self.session_id,
            sequence=self._sequence,
            timestamp=timestamp,
            kind=kind,
            role=role,
            text=text,
            source=SourceRef(
                source_id=self.source_id,
                session_id=self.session_id,
                source_hash=self.source_hash,
                parser_version=self.parser_version,
                turn_number=turn_number,
                record_index=record_index,
                record_ids=record_ids,
            ),
            tool_name=tool_name,
            tool_input_summary=tool_input_summary,
            tool_output=tool_output,
        )


def events_from_turns(
    turns: Iterable[TurnLike],
    *,
    source_id: str,
    session_id: str,
    source_hash: str,
    parser_version: str,
    include_timestamp: bool = True,
) -> list[SessionEvent]:
    """Wrap legacy parser turns as stable, source-linked canonical event envelopes.

    The bridge intentionally preserves the existing transcript body byte-for-byte
    at the Python string level. Provider adapters can emit richer event kinds later.
    """
    if not _SHA256_PATTERN.fullmatch(source_hash):
        raise ValueError("source_hash must be a lowercase SHA-256 hex digest")
    if not source_id or not session_id or not parser_version:
        raise ValueError("source_id, session_id, and parser_version are required")

    builder = EventBuilder(source_id, session_id, source_hash, parser_version)
    events = []
    for turn in turns:
        events.append(
            builder.build(
                record_index=None,
                turn_number=turn.number,
                timestamp=turn.timestamp if include_timestamp else None,
                kind=EventKind.TURN_TRANSCRIPT,
                text=turn.text(),
            )
        )
    return events
