"""Archive session enumeration and display identifiers."""
from pathlib import Path
import re

from .parsers import is_codex_file
from .parser_chatgpt import import_conversations

def short_id(session_id: str) -> str:
    """Return a distinctive short session ID (Codex rollout IDs end with a UUID)."""
    return session_id[-8:] if session_id.startswith("rollout-") else session_id[:8]

def list_sessions(project_dir: Path):
    """Yield (tool, session ID, path) for raw/ and manually added incoming/ files."""
    raw = project_dir / "raw"
    for tool_name in ("claude-code", "codex"):
        for path in sorted((raw / tool_name).glob("*.jsonl")) if (raw / tool_name).exists() else []:
            if ".onceki." in path.name:
                continue
            yield tool_name, path.stem, path
    chatgpt_dir = raw / "chatgpt"
    if chatgpt_dir.exists():
        for path in sorted(chatgpt_dir.glob("*.json")):
            if path.is_file():
                yield "chatgpt", path.stem, path
    artifact_dir = raw / "antigravity"
    if artifact_dir.exists():
        for row in sorted(entry for entry in artifact_dir.iterdir() if entry.is_dir()):
            yield "antigravity", row.name, row
    incoming_dir = project_dir / "gelen"
    if incoming_dir.exists():
        for path in sorted(incoming_dir.glob("*")):
            if path.suffix.lower() in (".md", ".txt"):
                yield "elle", path.stem, path
            elif path.suffix.lower() == ".jsonl":
                # Infer whether a raw session downloaded from the cloud is Codex or Claude Code from its contents.
                yield ("codex" if is_codex_file(path) else "claude-code"), path.stem, path


def import_incoming_exports(project_dir: Path, language: str = "tr") -> tuple[int, int]:
    """Import supported bundled exports as per-conversation derived raw records."""
    incoming_dir = project_dir / "gelen"
    if not incoming_dir.is_dir():
        return 0, 0
    created = updated = 0
    export_pattern = re.compile(r"^conversations(?:[-_]\d+)?\.json$", re.IGNORECASE)
    for export_path in sorted(path for path in incoming_dir.glob("*.json") if export_pattern.fullmatch(path.name)):
        new_count, update_count = import_conversations(export_path, project_dir / "raw" / "chatgpt", language)
        created += new_count
        updated += update_count
    return created, updated


# Backward-compatible Turkish API aliases.
kisa_id = short_id
oturumlari_listele = list_sessions
