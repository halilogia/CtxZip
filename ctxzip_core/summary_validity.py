"""Explicitly record a reviewed Git baseline for a Chapter or Volume summary."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

from .git_state import capture_git_snapshot
from .storage import atomic_write_text
from .summary_store import split_summary_metadata

_SUMMARY_NAME = re.compile(r"^(?:B\d{4}|C\d{3})\.md$")


class SummaryValidityError(ValueError):
    """A summary validity baseline could not be recorded safely."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _git_root(repository_dir: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repository_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as error:
        raise SummaryValidityError("not_repository") from error
    if result.returncode != 0:
        raise SummaryValidityError("not_repository")
    return Path(os.fsdecode(result.stdout.rstrip(b"\r\n"))).resolve()


def _normalize_validity_paths(paths: tuple[str, ...], repository_root: Path) -> tuple[str, ...]:
    if not paths:
        raise SummaryValidityError("paths_required")
    normalized = []
    seen = set()
    root = repository_root.resolve()
    for raw_path in paths:
        value = raw_path.strip().replace("\\", "/")
        path = PurePosixPath(value)
        if (
            not value
            or "\x00" in value
            or not path.parts
            or path.is_absolute()
            or ":" in path.parts[0]
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise SummaryValidityError("invalid_path")
        relative = path.as_posix()
        resolved = (root / Path(*path.parts)).resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise SummaryValidityError("path_unavailable")
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", relative],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError as error:
            raise SummaryValidityError("path_unavailable") from error
        if tracked.returncode != 0:
            raise SummaryValidityError("path_unavailable")
        key = relative.casefold()
        if key not in seen:
            seen.add(key)
            normalized.append(relative)
    return tuple(normalized)


def record_summary_validity(
    project_dir: Path,
    summary_name: str,
    validity_paths: tuple[str, ...],
    repository_dir: Path,
) -> tuple[str, tuple[str, ...], str]:
    """Atomically attach explicitly reviewed paths and the clean current Git HEAD.

    The summary body and its existing manual-edit hash are preserved. Callers must
    run from the repository that owns the files being declared valid.
    """
    if not _SUMMARY_NAME.fullmatch(summary_name):
        raise SummaryValidityError("invalid_summary")
    folder = "bolumler" if summary_name.startswith("B") else "ciltler"
    summary_path = Path(project_dir) / folder / summary_name
    if summary_path.is_symlink() or not summary_path.is_file():
        raise SummaryValidityError("invalid_summary")

    snapshot = capture_git_snapshot(Path(repository_dir))
    if not snapshot.is_repository:
        raise SummaryValidityError("not_repository")
    if snapshot.dirty:
        raise SummaryValidityError("dirty_repository")
    if not snapshot.head_sha:
        raise SummaryValidityError("missing_head")

    root = _git_root(Path(repository_dir))
    paths = _normalize_validity_paths(validity_paths, root)
    original = summary_path.read_text(encoding="utf-8")
    metadata, remaining = split_summary_metadata(original)
    metadata["validity_paths"] = json.dumps(paths, ensure_ascii=False)
    metadata["validity_head_sha"] = snapshot.head_sha
    header = "\n".join(f"{key}: {value}" for key, value in metadata.items())
    output = f"---\n{header}\n---\n{remaining}"
    current = capture_git_snapshot(Path(repository_dir))
    if (
        not current.is_repository
        or current.dirty
        or current.fingerprint != snapshot.fingerprint
    ):
        raise SummaryValidityError("dirty_repository")
    atomic_write_text(summary_path, output)
    return summary_name, paths, snapshot.head_sha
