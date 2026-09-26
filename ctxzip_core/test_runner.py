"""Run an explicit local command and persist its Git-bound test evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Sequence

from .git_state import capture_git_snapshot
from .knowledge import KnowledgeStore, RecordActor, TestEvidence, TestResult, new_record_id


def _validate_scope(values: Sequence[str]) -> tuple[str, ...]:
    scopes = []
    for value in values:
        normalized = value.replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        if (
            not normalized
            or path.is_absolute()
            or re.match(r"^[A-Za-z]:", normalized)
            or ".." in path.parts
        ):
            raise ValueError("Test scopes must be repository-relative paths")
        scopes.append(normalized)
    return tuple(dict.fromkeys(scopes))


def _safe_command_label(command: Sequence[str]) -> str:
    executable = Path(command[0].replace("\\", "/")).name
    if not executable:
        raise ValueError("Test command must include an executable")
    return f"{executable} <arguments omitted>"


def run_and_record_test(
    command: Sequence[str],
    *,
    store: KnowledgeStore,
    repository_dir: Path,
    scope: Sequence[str] = (),
) -> TestEvidence:
    """Execute argv without a shell and store only its outcome and pre-run snapshot.

    Command arguments and subprocess output are deliberately not persisted.
    Spawn failures are stored as ERROR observations with no fabricated exit code.
    """
    argv = tuple(command)
    if not argv or any(not isinstance(part, str) or not part for part in argv):
        raise ValueError("Test command must contain non-empty arguments")
    label = _safe_command_label(argv)
    normalized_scope = _validate_scope(scope)
    repository = Path(repository_dir).resolve()
    snapshot = capture_git_snapshot(repository)

    try:
        completed = subprocess.run(argv, cwd=repository, check=False)
    except OSError:
        result = TestResult.ERROR
        exit_code = None
    else:
        exit_code = completed.returncode
        result = TestResult.PASSED if exit_code == 0 else TestResult.FAILED

    evidence = TestEvidence(
        id=new_record_id("test"),
        actor=RecordActor.TEST_RUNNER,
        command=label,
        result=result,
        exit_code=exit_code,
        captured_at=datetime.now(timezone.utc).isoformat(),
        scope=normalized_scope,
        branch=snapshot.branch if snapshot.is_repository else None,
        head_sha=snapshot.head_sha if snapshot.is_repository else None,
        worktree_fingerprint=snapshot.fingerprint if snapshot.is_repository else None,
        dirty=snapshot.dirty if snapshot.is_repository else None,
    )
    store.add_test_evidence(evidence)
    return evidence
