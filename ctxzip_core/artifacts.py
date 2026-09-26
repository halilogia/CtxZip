"""Reconcile copied Markdown artifact trees while retaining prior file versions."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .storage import atomic_copy2


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _history_path(history_root: Path, relative_path: Path, content_hash: str) -> Path:
    path_key = hashlib.sha256(relative_path.as_posix().encode("utf-8")).hexdigest()[:24]
    return history_root / f"{path_key}.{content_hash}.md"


def markdown_files(root: Path) -> list[Path]:
    """Return a complete Markdown inventory or raise instead of implying deletions."""
    if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
        raise OSError(f"Markdown source tree is not readable: {root}")

    files: list[Path] = []

    def fail(error: OSError) -> None:
        raise error

    for directory, _, filenames in os.walk(root, onerror=fail, followlinks=False):
        for filename in filenames:
            if filename.lower().endswith(".md"):
                path = Path(directory) / filename
                if not path.is_file():
                    raise OSError(f"Markdown source file is not readable: {path}")
                files.append(path)
    return sorted(files, key=lambda item: item.as_posix())


def has_markdown_artifacts(root: Path) -> bool:
    return bool(markdown_files(root))


def _preserve_version(path: Path, relative_path: Path, history_root: Path) -> None:
    content_hash = _file_hash(path)
    backup = _history_path(history_root, relative_path, content_hash)
    if backup.exists() and _file_hash(backup) == content_hash:
        return
    backup.parent.mkdir(parents=True, exist_ok=True)
    atomic_copy2(path, backup)


def sync_markdown_tree(source_root: Path, target_root: Path, history_root: Path) -> bool:
    """Make target Markdown artifacts match source, archiving changed/deleted files first.

    Prior copies are stored under opaque, content-addressed filenames. A failed
    backup prevents replacement/deletion, and repeated runs do not duplicate history.
    """
    source_files = {path.relative_to(source_root): path for path in markdown_files(source_root)}
    target_files = {path.relative_to(target_root): path for path in markdown_files(target_root)} if target_root.exists() else {}
    changed = False

    for relative_path, source_path in source_files.items():
        target_path = target_root / relative_path
        if target_path.exists() and _file_hash(target_path) == _file_hash(source_path):
            continue
        if target_path.exists():
            _preserve_version(target_path, relative_path, history_root)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_copy2(source_path, target_path)
        changed = True

    for relative_path, target_path in target_files.items():
        if relative_path in source_files:
            continue
        _preserve_version(target_path, relative_path, history_root)
        target_path.unlink()
        changed = True

    if target_root.exists():
        for directory in sorted((item for item in target_root.rglob("*") if item.is_dir()), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
    return changed
