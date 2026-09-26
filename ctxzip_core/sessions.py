"""Archive session enumeration and display identifiers."""
from pathlib import Path

from .parsers import is_codex_file

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


# Backward-compatible Turkish API aliases.
kisa_id = short_id
oturumlari_listele = list_sessions
