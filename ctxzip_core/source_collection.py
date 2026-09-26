"""Discover external session sources and copy them into the local archive."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re

from .artifacts import has_markdown_artifacts, sync_markdown_tree
from .parser_common import claude_working_directory, codex_working_directory
from .sessions import import_incoming_exports
from .storage import atomic_copy2, atomic_write_text


@dataclass(frozen=True)
class CollectionResult:
    new: int
    updated: int
    unchanged: int


def expand_path(path_item: str) -> Path | None:
    """Expand user paths and the optional Codex home variable."""
    if "$CODEX_HOME" in path_item:
        home = os.environ.get("CODEX_HOME")
        if not home:
            return None
        path_item = path_item.replace("$CODEX_HOME", home)
    return Path(os.path.expandvars(os.path.expanduser(path_item)))


def file_hash(path_item: Path) -> str:
    """Hash a file without loading it all into memory."""
    digest = hashlib.sha256()
    with path_item.open("rb") as source_file:
        for data_block in iter(lambda: source_file.read(1 << 20), b""):
            digest.update(data_block)
    return digest.hexdigest()


def find_source_version(
    project_dir: Path,
    source_id: str,
    session_id: str,
    source_hash: str,
) -> Path | None:
    """Resolve an exact archived JSONL/ChatGPT source version by provenance hash."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", source_id):
        raise ValueError("Invalid source identifier")
    if not session_id or session_id in {".", ".."} or Path(session_id).name != session_id:
        raise ValueError("Invalid session identifier")
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ValueError("Invalid source hash")

    source_dir = Path(project_dir) / "raw" / source_id
    resolved_source_dir = source_dir.resolve()
    current_paths = [source_dir / f"{session_id}.jsonl", source_dir / f"{session_id}.json"]
    historical_paths = sorted(source_dir.glob(f"{session_id}.*.onceki.jsonl"))
    for candidate in (*current_paths, *historical_paths):
        try:
            resolved_candidate = candidate.resolve(strict=True)
        except FileNotFoundError:
            continue
        if not resolved_candidate.is_relative_to(resolved_source_dir):
            continue
        if resolved_candidate.is_file() and file_hash(resolved_candidate) == source_hash:
            return resolved_candidate
    return None


def _archive_previous_source(target: Path) -> Path:
    """Keep a content-addressed copy before replacing an archived session."""
    content_hash = file_hash(target)
    previous = target.with_suffix(f".{content_hash}.onceki.jsonl")
    if not previous.exists() or file_hash(previous) != content_hash:
        atomic_copy2(target, previous)
    return previous


def safe_name(value: str) -> str:
    """Convert a project label to a stable directory-safe name."""
    value = re.sub(r"[^\w.\-]+", "-", value, flags=re.UNICODE).strip("-")
    return value or "adsiz"


def project_name(working_directory: str | None, settings: dict) -> str | None:
    """Resolve a session working directory through exclusions and project aliases."""
    if not working_directory:
        return None
    name = re.split(r"[\\/]", working_directory.rstrip("\\/"))[-1] or working_directory
    if name in settings["haric_projeler"]:
        return None
    return safe_name(settings["proje_takma_adlari"].get(name, name))


def discover_sources(settings: dict, archive_dir: Path | None = None):
    """Yield ``(tool, project, session_id, source_path)`` for configured providers."""
    archive_dir = Path(archive_dir) if archive_dir is not None else None
    for configured_root in settings["kaynaklar"].get("claude_code", []):
        source_root = expand_path(configured_root)
        if not source_root or not source_root.exists():
            continue
        for path_item in sorted(source_root.glob("*/*.jsonl")):
            project = project_name(claude_working_directory(path_item), settings)
            if project:
                yield "claude-code", project, path_item.stem, path_item
    for configured_root in settings["kaynaklar"].get("codex", []):
        source_root = expand_path(configured_root)
        if not source_root or not source_root.exists():
            continue
        for path_item in sorted(source_root.rglob("*.jsonl")):
            project = project_name(codex_working_directory(path_item), settings)
            if project:
                yield "codex", project, path_item.stem, path_item
    for configured_root in settings["kaynaklar"].get("antigravity_brain", []):
        source_root = expand_path(configured_root)
        if not source_root or not source_root.exists():
            continue
        for entry in sorted(item for item in source_root.iterdir() if item.is_dir()):
            project = safe_name(settings["proje_takma_adlari"].get(entry.name, "antigravity"))
            archived_marker = bool(
                archive_dir
                and (archive_dir / project / "raw" / "antigravity" / (entry.name + ".kaynak")).is_file()
            )
            if archived_marker or has_markdown_artifacts(entry):
                yield "antigravity", project, entry.name, entry


def collect_sources(settings: dict, archive_root: Path) -> CollectionResult:
    """Copy configured providers and materialize supported incoming export sessions."""
    new_count = updated_count = unchanged_count = 0
    for tool, project, session_id, source_path in discover_sources(settings, archive_root):
        target_dir = archive_root / project / "raw" / tool
        target_dir.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            target = target_dir / session_id
            history_root = target_dir.parent / "antigravity-history" / session_id
            changed = sync_markdown_tree(source_path, target, history_root)
            is_new = not (target_dir / (session_id + ".kaynak")).exists()
            atomic_write_text(target_dir / (session_id + ".kaynak"), str(source_path))
        else:
            target = target_dir / (session_id + ".jsonl")
            is_new = not target.exists()
            changed = is_new or target.stat().st_size != source_path.stat().st_size or file_hash(target) != file_hash(source_path)
            if changed:
                if not is_new:
                    _archive_previous_source(target)
                atomic_copy2(source_path, target)
        if is_new:
            new_count += 1
        elif changed:
            updated_count += 1
        else:
            unchanged_count += 1
    if archive_root.exists():
        for project_dir in sorted(
            item for item in archive_root.iterdir()
            if item.is_dir() and not item.name.startswith(".")
        ):
            imported, refreshed = import_incoming_exports(project_dir, settings.get("language", "tr"))
            new_count += imported
            updated_count += refreshed
    return CollectionResult(new_count, updated_count, unchanged_count)
