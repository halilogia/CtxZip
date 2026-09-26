"""Select unsummarized recent turns without duplicating Chapter ranges."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .events import EventKind, ParsedSession, events_from_turns
from .parser_common import Turn

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SessionTurns:
    session_key: str
    source_hash: str
    turns: tuple[Turn, ...]


def session_turns_from_events(
    parsed: ParsedSession,
    *,
    session_key: str,
    source_id: str,
    session_id: str,
    source_hash: str,
    parser_version: str,
) -> SessionTurns:
    """Adapt provider-neutral turn events for recent-context selection.

    Older granular adapters expose per-message events plus legacy turns. Bridge
    those turns into source-linked transcript events; providers that already emit
    turn transcripts, such as ChatGPT, retain their native event provenance.
    """
    transcript_events = [
        event for event in parsed.events if event.kind == EventKind.TURN_TRANSCRIPT
    ]
    if not transcript_events and parsed.turns:
        source = parsed.events[0].source if parsed.events else None
        transcript_events = events_from_turns(
            parsed.turns,
            source_id=source.source_id if source else source_id,
            session_id=source.session_id if source else session_id,
            source_hash=source.source_hash if source else source_hash,
            parser_version=source.parser_version if source else parser_version,
        )
    hashes = {event.source.source_hash for event in transcript_events}
    if len(hashes) > 1:
        raise ValueError("Recent transcript events span multiple source versions")
    event_turns = []
    for event in transcript_events:
        if not event.text:
            continue
        turn = Turn(event.source.turn_number, event.timestamp or "")
        turn.lines.append(event.text)
        event_turns.append(turn)
    return SessionTurns(
        session_key=session_key,
        source_hash=next(iter(hashes), source_hash),
        turns=tuple(event_turns),
    )


@dataclass(frozen=True)
class RecentTurn:
    session_key: str
    turn_number: int
    timestamp: str
    source_hash: str
    text: str

    @property
    def key(self) -> str:
        return f"raw:{self.session_key}:T{self.turn_number}"

    @property
    def source(self) -> str:
        return f"{self.session_key}#T{self.turn_number}@{self.source_hash[:12]}"


def select_uncovered_recent_turns(
    sessions: Iterable[SessionTurns],
    chapters: Iterable[dict],
    limit: int = 20,
) -> list[RecentTurn]:
    """Return the newest turns outside all persisted chapter source intervals.

    Chapters are the coverage authority because volumes summarize Chapters.
    Source records are sorted chronologically before the recent tail is chosen;
    returned turns stay oldest-first so a short context tail reads naturally.
    """
    if limit < 1:
        raise ValueError("Recent-turn limit must be positive")
    covered: dict[str, list[tuple[int, int]]] = {}
    for chapter in chapters:
        key = chapter.get("oturum")
        first = chapter.get("tur_baslangic")
        last = chapter.get("tur_bitis")
        if isinstance(key, str) and isinstance(first, int) and isinstance(last, int) and first <= last:
            covered.setdefault(key, []).append((first, last))

    candidates: list[tuple[str, str, int, RecentTurn]] = []
    for session in sessions:
        if not session.session_key or not _SHA256.fullmatch(session.source_hash):
            raise ValueError("Recent turns require session identity and source SHA-256")
        intervals = covered.get(session.session_key, ())
        for turn in session.turns:
            text = turn.text()
            if not text or any(first <= turn.number <= last for first, last in intervals):
                continue
            recent = RecentTurn(
                session_key=session.session_key,
                turn_number=turn.number,
                timestamp=turn.timestamp,
                source_hash=session.source_hash,
                text=text,
            )
            candidates.append((turn.timestamp, session.session_key, turn.number, recent))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in candidates[-limit:]]
