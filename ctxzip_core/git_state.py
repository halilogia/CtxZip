"""Read-only Git and worktree fingerprints for local evidence provenance."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


@dataclass(frozen=True)
class GitSnapshot:
    """A privacy-conscious snapshot; file contents are represented only by hashes."""

    is_repository: bool
    branch: str | None
    head_sha: str | None
    dirty: bool
    staged_diff_hash: str
    unstaged_diff_hash: str
    status_hash: str
    untracked_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    fingerprint: str | None


class GitStateError(RuntimeError):
    """Raised when a repository was found but its state cannot be read safely."""


def _run_git(repository: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise GitStateError("Git is unavailable while reading repository state") from error
    if result.returncode != 0:
        raise GitStateError("Git failed while reading repository state")
    return result.stdout


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_git_output(repository: Path, *arguments: str) -> str:
    digest = hashlib.sha256()
    try:
        process = subprocess.Popen(
            ["git", *arguments],
            cwd=repository,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise GitStateError("Git is unavailable while hashing repository changes") from error
    if process.stdout is None:
        process.kill()
        process.wait()
        raise GitStateError("Git output stream could not be opened")
    with process.stdout:
        for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
            digest.update(chunk)
    if process.wait() != 0:
        raise GitStateError("Git failed while hashing repository changes")
    return digest.hexdigest()


def _untracked_hash(repository: Path, relative_path: str) -> str:
    path = repository.joinpath(*relative_path.split("/"))
    try:
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode):
            content = os.readlink(path).encode("utf-8", errors="surrogateescape")
            return _sha256(content)
        else:
            digest = hashlib.sha256()
            with path.open("rb") as file:
                before = os.fstat(file.fileno())
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(chunk)
                after = os.fstat(file.fileno())
    except OSError as error:
        raise GitStateError("An untracked file changed while its fingerprint was read") from error
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise GitStateError("An untracked file changed while its fingerprint was read")
    return digest.hexdigest()


def capture_git_snapshot(path: Path) -> GitSnapshot:
    """Capture branch, HEAD, diffs, and non-ignored untracked content hashes.

    The snapshot never returns file contents or an absolute repository path. Callers
    should still treat relative file names and branch names as potentially private.
    """
    requested = path.resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=requested,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise GitStateError("Git is unavailable while checking the repository") from error
    if result.returncode != 0:
        empty_hash = _sha256(b"")
        return GitSnapshot(
            is_repository=False,
            branch=None,
            head_sha=None,
            dirty=False,
            staged_diff_hash=empty_hash,
            unstaged_diff_hash=empty_hash,
            status_hash=empty_hash,
            untracked_files=(),
            changed_files=(),
            fingerprint=None,
        )

    repository = Path(os.fsdecode(result.stdout.rstrip(b"\r\n"))).resolve()
    branch_result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    branch = os.fsdecode(branch_result.stdout.rstrip(b"\r\n")) if branch_result.returncode == 0 else None
    head_result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    head_sha = os.fsdecode(head_result.stdout.rstrip(b"\r\n")) if head_result.returncode == 0 else None

    status = _run_git(repository, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    untracked_output = _run_git(repository, "ls-files", "--others", "--exclude-standard", "-z")
    untracked_files = tuple(
        sorted(os.fsdecode(item).replace("\\", "/") for item in untracked_output.split(b"\0") if item)
    )
    staged_paths = _run_git(repository, "diff", "--cached", "--name-only", "-z", "--no-renames")
    unstaged_paths = _run_git(repository, "diff", "--name-only", "-z", "--no-renames")
    changed_files = tuple(
        sorted(
            {
                os.fsdecode(item).replace("\\", "/")
                for output in (staged_paths, unstaged_paths, untracked_output)
                for item in output.split(b"\0")
                if item
            }
        )
    )

    staged_hash = _hash_git_output(
        repository, "diff", "--cached", "--binary", "--no-ext-diff", "--no-renames"
    )
    unstaged_hash = _hash_git_output(
        repository, "diff", "--binary", "--no-ext-diff", "--no-renames"
    )
    status_hash = _sha256(status)
    untracked_state = [
        {"path": relative_path, "sha256": _untracked_hash(repository, relative_path)}
        for relative_path in untracked_files
    ]
    identity = json.dumps(
        {
            "branch": branch,
            "head_sha": head_sha,
            "staged_diff_hash": staged_hash,
            "unstaged_diff_hash": unstaged_hash,
            "status_hash": status_hash,
            "untracked": untracked_state,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    fingerprint = _sha256(identity)
    return GitSnapshot(
        is_repository=True,
        branch=branch,
        head_sha=head_sha,
        dirty=bool(status),
        staged_diff_hash=staged_hash,
        unstaged_diff_hash=unstaged_hash,
        status_hash=status_hash,
        untracked_files=untracked_files,
        changed_files=changed_files,
        fingerprint=fingerprint,
    )
