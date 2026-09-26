"""User-authored knowledge capture with exact session-event provenance."""
from pathlib import Path

from .event_store import event_references_for_turn
from .knowledge import (
    ConstraintRecord,
    DecisionRecord,
    FileMentionRecord,
    KnowledgeStatus,
    KnowledgeStore,
    OpenQuestionRecord,
    QuestionStatus,
    RecordActor,
    TaskRecord,
    TaskStatus,
    new_record_id,
    utc_timestamp,
)


SUPPORTED_SOURCES = ("claude-code", "codex", "chatgpt")


def capture_knowledge(
    project_dir: Path,
    *,
    kind: str,
    source_id: str,
    session_id: str,
    turn_number: int,
    text: str | None = None,
    status: str | None = None,
    scope: str | None = None,
    path: str | None = None,
    symbol: str | None = None,
    task_status: str | None = None,
    validity_paths: tuple[str, ...] = (),
    validity_head_sha: str | None = None,
    supersedes: str | None = None,
):
    """Add one user-authored record; never infer or extract claims automatically."""
    if source_id not in SUPPORTED_SOURCES:
        raise ValueError("Knowledge capture requires a supported event source")
    references = event_references_for_turn(project_dir, source_id, session_id, turn_number)
    if not references:
        raise ValueError("No archived events found for the selected source session and turn")

    allowed = {"decision", "constraint", "task", "question", "file"}
    if kind not in allowed:
        raise ValueError("Unknown knowledge record type")
    if validity_paths and not validity_head_sha:
        raise ValueError("Validity paths require a Git HEAD baseline")
    if validity_head_sha and not validity_paths:
        raise ValueError("A Git HEAD baseline requires at least one validity path")
    if kind not in {"decision", "constraint"} and (validity_paths or validity_head_sha or supersedes):
        raise ValueError("Validity and replacement options apply only to decisions or constraints")
    if status is not None and kind not in {"decision", "constraint", "file"}:
        raise ValueError("Verification status applies only to decisions, constraints, and file mentions")
    if kind != "constraint" and scope is not None:
        raise ValueError("Scope applies only to constraints")
    if kind != "file" and (path is not None or symbol is not None):
        raise ValueError("Path and symbol apply only to file mentions")
    if kind != "task" and task_status is not None:
        raise ValueError("Task status applies only to tasks")
    if kind == "file" and text is not None:
        raise ValueError("File mentions use --path and do not accept --text")

    created_at = utc_timestamp()
    actor = RecordActor.USER
    if kind == "decision":
        if not text or not text.strip():
            raise ValueError("Decision text is required")
        record = DecisionRecord(
            id=new_record_id("decision"), statement=text, status=KnowledgeStatus(status or "confirmed"),
            actor=actor, created_at=created_at, source_refs=references,
            supersedes=supersedes, validity_paths=validity_paths,
            validity_head_sha=validity_head_sha,
        )
        return KnowledgeStore(project_dir / "knowledge").add_decision(record)
    if kind == "constraint":
        if not text or not text.strip() or not scope or not scope.strip():
            raise ValueError("Constraint text and scope are required")
        record = ConstraintRecord(
            id=new_record_id("constraint"), statement=text, scope=scope,
            status=KnowledgeStatus(status or "confirmed"), actor=actor,
            created_at=created_at, source_refs=references, validity_paths=validity_paths,
            validity_head_sha=validity_head_sha, supersedes=supersedes,
        )
        return KnowledgeStore(project_dir / "knowledge").add_constraint(record)
    if kind == "task":
        if not text or not text.strip():
            raise ValueError("Task text is required")
        record = TaskRecord(
            id=new_record_id("task"), title=text, status=TaskStatus(task_status or "open"),
            actor=actor, created_at=created_at, source_refs=references,
        )
        return KnowledgeStore(project_dir / "knowledge").add_task(record)
    if kind == "question":
        if not text or not text.strip():
            raise ValueError("Question text is required")
        record = OpenQuestionRecord(
            id=new_record_id("question"), question=text, status=QuestionStatus.OPEN,
            actor=actor, created_at=created_at, source_refs=references,
        )
        return KnowledgeStore(project_dir / "knowledge").add_open_question(record)
    if not path or not path.strip():
        raise ValueError("File path is required")
    record = FileMentionRecord(
        id=new_record_id("file"), path=path, symbol=symbol,
        status=KnowledgeStatus(status or "observed"), actor=actor,
        created_at=created_at, source_refs=references,
    )
    return KnowledgeStore(project_dir / "knowledge").add_file_mention(record)
