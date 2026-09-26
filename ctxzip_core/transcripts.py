"""Generate localized transcripts and persist their canonical event snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .event_store import remove_session_events, save_session_events
from .i18n import translate
from .parsers import event_session_id, read_session_events
from .privacy import redact_secrets
from .sessions import list_sessions, short_id
from .storage import atomic_write_text
from .text import format_timestamp


@dataclass(frozen=True)
class TranscriptResult:
    project: str
    count: int
    output_dir: Path


def generate_transcripts(settings: dict, project_dir: Path) -> TranscriptResult:
    """Write one transcript per readable source session for a single project."""
    language = settings.get("language", "tr")
    target = project_dir / "dokum"
    target.mkdir(exist_ok=True)
    transcript_count = 0
    for tool, session_id, path in list_sessions(project_dir):
        parsed = read_session_events(tool, path, settings, language)
        turns, session_info = parsed.turns, parsed.metadata
        if not turns:
            remove_session_events(project_dir, tool, event_session_id(tool, path))
            continue
        save_session_events(project_dir, parsed)
        start_time = format_timestamp(session_info["baslangic"])
        start_label = translate(language, "transcript_start")
        end_label = translate(language, "transcript_end")
        branch_label = translate(language, "transcript_branch")
        turn_label = translate(language, "transcript_turns")
        raw_label = translate(language, "transcript_raw_source")
        session_label = translate(language, "transcript_session")
        date_label = start_time[:10] or translate(language, "transcript_undated")
        short_session_id = short_id(session_id)
        name = f"{date_label}_{tool}_{short_session_id}.md"
        transcript_lines = [
            f"# {project_dir.name} — {tool} {session_label} {short_session_id}",
            f"{start_label}: {start_time} · {end_label}: {format_timestamp(session_info['bitis'])} · "
            f"{branch_label}: {session_info['dal'] or '-'} · {turn_label}: {len(turns)}",
            f"{raw_label}: `{path.relative_to(project_dir)}`",
            "",
        ]
        for turn in turns:
            transcript_lines.append(f"## [T{turn.number}] {turn.timestamp}\n\n{turn.text()}\n")
        atomic_write_text(
            target / name,
            redact_secrets("\n".join(transcript_lines), language),
        )
        transcript_count += 1
    return TranscriptResult(project=project_dir.name, count=transcript_count, output_dir=target)
