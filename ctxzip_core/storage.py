"""Atomic filesystem writes for derived archives and processing state."""
from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from pathlib import Path


def _output_path(path: Path) -> Path:
    target = Path(path)
    # Preserve the behavior of write_text/copy2 when an output is a symlink.
    return target.resolve() if target.is_symlink() else target


def _preserve_mode(target: Path, temporary: Path) -> None:
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        return
    os.chmod(temporary, mode)


def _replace(temporary: Path, target: Path) -> None:
    _preserve_mode(target, temporary)
    os.replace(temporary, target)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write text to a same-directory temporary file, then atomically replace target."""
    target = _output_path(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        _replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: object, *, indent: int = 2) -> None:
    """Serialize JSON with the same readable formatting used by project state files."""
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=indent))


def atomic_copy2(source: Path, destination: Path) -> None:
    """Copy a file and its metadata without exposing a partially copied destination."""
    source = Path(source)
    target = _output_path(destination)
    temporary: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        with source.open("rb") as source_file, os.fdopen(descriptor, "wb") as target_file:
            descriptor = None
            shutil.copyfileobj(source_file, target_file)
            target_file.flush()
            os.fsync(target_file.fileno())
        shutil.copystat(source, temporary)
        _replace(temporary, target)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
