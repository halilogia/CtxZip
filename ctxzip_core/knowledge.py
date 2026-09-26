"""Versioned, source-linked project knowledge stored apart from summaries."""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path, PurePosixPath
import re
import uuid
from typing import TypeVar

from .events import EventReference, SessionEvent, SourceRef
from .git_state import GitSnapshot
from .storage import atomic_write_json


SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = {1, 2, SCHEMA_VERSION}
_SOURCE_HASH = re.compile(r"^[0-9a-f]{64}$")
_HEX_SHA = re.compile(r"^[0-9a-f]{40,64}$")


class KnowledgeStatus(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"


class QuestionStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class TaskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecordActor(str, Enum):
    USER = "user"
    AGENT = "agent"
    EXTRACTOR = "extractor"
    TEST_RUNNER = "test_runner"


class TestResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class Freshness(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    POSSIBLY_STALE = "possibly-stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DecisionRecord:
    id: str
    statement: str
    status: KnowledgeStatus
    actor: RecordActor
    created_at: str
    source_refs: tuple[EventReference, ...]
    supersedes: str | None = None
    validity_paths: tuple[str, ...] = ()
    validity_head_sha: str | None = None


@dataclass(frozen=True)
class ConstraintRecord:
    id: str
    statement: str
    scope: str
    status: KnowledgeStatus
    actor: RecordActor
    created_at: str
    source_refs: tuple[EventReference, ...]
    validity_paths: tuple[str, ...] = ()
    validity_head_sha: str | None = None
    supersedes: str | None = None


@dataclass(frozen=True)
class TestEvidence:
    id: str
    actor: RecordActor
    command: str
    result: TestResult
    exit_code: int | None
    captured_at: str
    scope: tuple[str, ...]
    branch: str | None
    head_sha: str | None
    worktree_fingerprint: str | None
    dirty: bool | None


@dataclass(frozen=True)
class OpenQuestionRecord:
    id: str
    question: str
    status: QuestionStatus
    actor: RecordActor
    created_at: str
    source_refs: tuple[EventReference, ...]


@dataclass(frozen=True)
class TaskRecord:
    id: str
    title: str
    status: TaskStatus
    actor: RecordActor
    created_at: str
    source_refs: tuple[EventReference, ...]


@dataclass(frozen=True)
class FileMentionRecord:
    id: str
    path: str
    symbol: str | None
    status: KnowledgeStatus
    actor: RecordActor
    created_at: str
    source_refs: tuple[EventReference, ...]


class KnowledgeStoreError(RuntimeError):
    """Raised when a knowledge collection cannot be safely read or updated."""


RecordT = TypeVar("RecordT")


def new_record_id(record_type: str) -> str:
    """Create an opaque, type-prefixed record ID without embedding record text."""
    if record_type not in {"decision", "constraint", "test", "question", "task", "file"}:
        raise ValueError("Unknown knowledge record type")
    return f"{record_type}:{uuid.uuid4().hex}"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def event_reference(event: SessionEvent) -> EventReference:
    """Capture event identity and its immutable source-version reference."""
    return EventReference(event_id=event.id, source=event.source)


def test_freshness(evidence: TestEvidence, current: GitSnapshot) -> Freshness:
    """Compare test provenance to the current worktree without rewriting history."""
    if (
        not current.is_repository
        or not evidence.worktree_fingerprint
        or not current.fingerprint
        or evidence.head_sha is None
        or current.head_sha is None
    ):
        return Freshness.UNKNOWN
    if evidence.head_sha == current.head_sha and evidence.worktree_fingerprint == current.fingerprint:
        return Freshness.CURRENT
    return Freshness.STALE


def knowledge_freshness(record: DecisionRecord | ConstraintRecord, current: GitSnapshot | None) -> Freshness:
    """Conservatively compare explicitly scoped claims with a current Git snapshot."""
    if (
        current is None
        or not current.is_repository
        or not record.validity_paths
        or not record.validity_head_sha
        or not current.head_sha
    ):
        return Freshness.UNKNOWN
    if record.validity_head_sha != current.head_sha:
        return Freshness.POSSIBLY_STALE
    expected = {path.replace("\\", "/").casefold() for path in record.validity_paths}
    changed = {path.replace("\\", "/").casefold() for path in current.changed_files}
    if expected & changed:
        return Freshness.POSSIBLY_STALE
    return Freshness.CURRENT


def _require_source_refs(source_refs: tuple[EventReference, ...]) -> None:
    if not source_refs:
        raise ValueError("Knowledge claims require at least one event source reference")
    for reference in source_refs:
        if not reference.event_id:
            raise ValueError("Event references require an event ID")
        source = reference.source
        if (
            not source.source_id
            or not source.session_id
            or not source.parser_version
            or not _SOURCE_HASH.fullmatch(source.source_hash)
            or source.turn_number < 0
            or (source.record_index is not None and source.record_index < 0)
        ):
            raise ValueError("Event references require valid source-version provenance")


def _validate_timestamp(value: str) -> None:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("Timestamps must use ISO 8601 format with a timezone") from error
    if timestamp.utcoffset() is None:
        raise ValueError("Timestamps must use ISO 8601 format with a timezone")


def _validate_actor(actor: RecordActor) -> None:
    if not isinstance(actor, RecordActor):
        raise ValueError("Knowledge records require a recognized authoring actor")


def _validate_knowledge_status(status: KnowledgeStatus, actor: RecordActor) -> None:
    _validate_actor(actor)
    if not isinstance(status, KnowledgeStatus):
        raise ValueError("Knowledge records require a recognized verification status")
    if status == KnowledgeStatus.CONFIRMED and actor != RecordActor.USER:
        raise ValueError("Only a user-authored record can be marked confirmed")


def _validate_relative_path(value: str) -> None:
    normalized = value.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if (
        not value.strip()
        or parsed.is_absolute()
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in parsed.parts
    ):
        raise ValueError("File mentions must use repository-relative paths")


def _validate_validity(paths: tuple[str, ...], head_sha: str | None) -> None:
    if not isinstance(paths, tuple):
        raise ValueError("Validity paths must be a tuple of repository-relative paths")
    if bool(paths) != (head_sha is not None):
        raise ValueError("Validity paths and their Git HEAD baseline must be provided together")
    for path in paths:
        _validate_relative_path(path)
    if head_sha is not None and not _HEX_SHA.fullmatch(head_sha):
        raise ValueError("Validity HEAD must be a hexadecimal Git SHA")


def _decode_validity(value: dict) -> tuple[tuple[str, ...], str | None]:
    paths = value.get("validity_paths", [])
    head_sha = value.get("validity_head_sha")
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise ValueError("Validity paths must be a list of repository-relative paths")
    normalized_paths = tuple(paths)
    _validate_validity(normalized_paths, head_sha)
    return normalized_paths, head_sha


def _serialize(record) -> dict:
    return asdict(record)


def _source_ref_from_dict(value: dict) -> SourceRef:
    source = dict(value)
    source["record_ids"] = tuple(source.get("record_ids", ()))
    return SourceRef(**source)


def _event_refs_from_list(values: list[dict]) -> tuple[EventReference, ...]:
    return tuple(
        EventReference(event_id=value["event_id"], source=_source_ref_from_dict(value["source"]))
        for value in values
    )


def _decode_decision(value: dict) -> DecisionRecord:
    validity_paths, validity_head_sha = _decode_validity(value)
    return DecisionRecord(
        **{
            **value,
            "status": KnowledgeStatus(value["status"]),
            "actor": RecordActor(value["actor"]),
            "source_refs": _event_refs_from_list(value["source_refs"]),
            "validity_paths": validity_paths,
            "validity_head_sha": validity_head_sha,
        }
    )


def _decode_constraint(value: dict) -> ConstraintRecord:
    validity_paths, validity_head_sha = _decode_validity(value)
    return ConstraintRecord(
        **{
            **value,
            "supersedes": value.get("supersedes"),
            "status": KnowledgeStatus(value["status"]),
            "actor": RecordActor(value["actor"]),
            "source_refs": _event_refs_from_list(value["source_refs"]),
            "validity_paths": validity_paths,
            "validity_head_sha": validity_head_sha,
        }
    )


def _decode_test(value: dict) -> TestEvidence:
    return TestEvidence(**{**value, "result": TestResult(value["result"]), "scope": tuple(value["scope"])})


def _decode_question(value: dict) -> OpenQuestionRecord:
    return OpenQuestionRecord(
        **{
            **value,
            "status": QuestionStatus(value["status"]),
            "actor": RecordActor(value["actor"]),
            "source_refs": _event_refs_from_list(value["source_refs"]),
        }
    )


def _decode_task(value: dict) -> TaskRecord:
    return TaskRecord(
        **{
            **value,
            "status": TaskStatus(value["status"]),
            "actor": RecordActor(value["actor"]),
            "source_refs": _event_refs_from_list(value["source_refs"]),
        }
    )


def _decode_file_mention(value: dict) -> FileMentionRecord:
    return FileMentionRecord(
        **{
            **value,
            "status": KnowledgeStatus(value["status"]),
            "actor": RecordActor(value["actor"]),
            "source_refs": _event_refs_from_list(value["source_refs"]),
        }
    )


class KnowledgeStore:
    """Store each record type in a separate versioned collection.

    Pass a private project archive directory such as ``<archive>/knowledge``.
    Each collection is atomically replaced; this API currently assumes one writer.
    """

    _COLLECTIONS = {
        "decisions": ("decisions.json", _decode_decision),
        "constraints": ("constraints.json", _decode_constraint),
        "test_runs": ("test_runs.json", _decode_test),
        "open_questions": ("open_questions.json", _decode_question),
        "tasks": ("tasks.json", _decode_task),
        "file_mentions": ("file_mentions.json", _decode_file_mention),
    }

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _path(self, collection: str) -> Path:
        return self.directory / self._COLLECTIONS[collection][0]

    def _load(self, collection: str) -> list:
        path = self._path(collection)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as error:
            raise KnowledgeStoreError(f"Cannot read knowledge collection: {path.name}") from error
        if not isinstance(value, dict) or value.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
            raise KnowledgeStoreError(f"Unsupported knowledge schema: {path.name}")
        if not isinstance(value.get("records"), list):
            raise KnowledgeStoreError(f"Invalid knowledge collection: {path.name}")
        decoder = self._COLLECTIONS[collection][1]
        try:
            records = [decoder(record) for record in value["records"]]
        except (KeyError, TypeError, ValueError) as error:
            raise KnowledgeStoreError(f"Invalid record in knowledge collection: {path.name}") from error
        ids = [record.id for record in records]
        if any(not record_id for record_id in ids) or len(ids) != len(set(ids)):
            raise KnowledgeStoreError(f"Duplicate or empty record ID in collection: {path.name}")
        return records

    def _write(self, collection: str, records: list) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self._path(collection),
            {"schema_version": SCHEMA_VERSION, "records": [_serialize(record) for record in records]},
        )

    def _add(self, collection: str, record: RecordT) -> RecordT:
        record_type = {
            "constraints": "constraint",
            "test_runs": "test",
            "open_questions": "question",
            "tasks": "task",
            "file_mentions": "file",
        }[collection]
        if not record.id.startswith(f"{record_type}:"):
            raise ValueError(f"Record IDs must use the {record_type}: prefix")
        records = self._load(collection)
        for existing in records:
            if existing.id == record.id:
                if existing == record:
                    return existing
                raise KnowledgeStoreError("A different record already uses this ID")
        records.append(record)
        self._write(collection, records)
        return record

    def add_decision(self, record: DecisionRecord) -> DecisionRecord:
        _require_source_refs(record.source_refs)
        _validate_knowledge_status(record.status, record.actor)
        _validate_timestamp(record.created_at)
        _validate_validity(record.validity_paths, record.validity_head_sha)
        if not record.statement.strip():
            raise ValueError("Decision statement cannot be empty")
        if not record.id.startswith("decision:"):
            raise ValueError("Decision IDs must use the decision: prefix")
        records = self.list_decisions()
        for existing in records:
            if existing.id == record.id:
                if existing == record:
                    return existing
                raise KnowledgeStoreError("A different record already uses this ID")
        if record.supersedes:
            if record.status != KnowledgeStatus.CONFIRMED or record.actor != RecordActor.USER:
                raise ValueError("Only a user-confirmed decision can supersede another decision")
            for index, existing in enumerate(records):
                if existing.id == record.supersedes:
                    if existing.status not in (
                        KnowledgeStatus.OBSERVED,
                        KnowledgeStatus.INFERRED,
                        KnowledgeStatus.CONFIRMED,
                    ):
                        raise ValueError("Only a current decision can be superseded")
                    records[index] = replace(existing, status=KnowledgeStatus.SUPERSEDED)
                    break
            else:
                raise ValueError("A superseded decision must already exist")
        records.append(record)
        self._write("decisions", records)
        return record

    def add_constraint(self, record: ConstraintRecord) -> ConstraintRecord:
        _require_source_refs(record.source_refs)
        _validate_knowledge_status(record.status, record.actor)
        _validate_timestamp(record.created_at)
        _validate_validity(record.validity_paths, record.validity_head_sha)
        if not record.statement.strip() or not record.scope.strip():
            raise ValueError("Constraint statement and scope cannot be empty")
        if not record.id.startswith("constraint:"):
            raise ValueError("Record IDs must use the constraint: prefix")
        records = self.list_constraints()
        for existing in records:
            if existing.id == record.id:
                if existing == record:
                    return existing
                raise KnowledgeStoreError("A different record already uses this ID")
        if record.status == KnowledgeStatus.INVALIDATED and not record.supersedes:
            raise ValueError("A constraint can only be invalidated by an explicit replacement")
        if record.supersedes:
            if record.status != KnowledgeStatus.CONFIRMED or record.actor != RecordActor.USER:
                raise ValueError("Only a user-confirmed constraint can invalidate another constraint")
            for index, existing in enumerate(records):
                if existing.id != record.supersedes:
                    continue
                if existing.status not in (
                    KnowledgeStatus.OBSERVED,
                    KnowledgeStatus.INFERRED,
                    KnowledgeStatus.CONFIRMED,
                ):
                    raise ValueError("Only an active constraint can be invalidated")
                if existing.scope.strip().casefold() != record.scope.strip().casefold():
                    raise ValueError("A replacement constraint must use the same scope")
                records[index] = replace(existing, status=KnowledgeStatus.INVALIDATED)
                break
            else:
                raise ValueError("The constraint to invalidate must already exist")
        records.append(record)
        self._write("constraints", records)
        return record

    def add_test_evidence(self, record: TestEvidence) -> TestEvidence:
        _validate_timestamp(record.captured_at)
        if record.actor != RecordActor.TEST_RUNNER:
            raise ValueError("Test evidence must be authored by the test runner")
        if not record.command.strip():
            raise ValueError("Test command cannot be empty")
        if record.head_sha is not None and not _HEX_SHA.fullmatch(record.head_sha):
            raise ValueError("Test HEAD must be a hexadecimal Git SHA")
        if record.worktree_fingerprint is not None and not _SOURCE_HASH.fullmatch(record.worktree_fingerprint):
            raise ValueError("Worktree fingerprint must be a lowercase SHA-256 digest")
        if record.result == TestResult.PASSED and record.exit_code != 0:
            raise ValueError("Passing test evidence requires exit code zero")
        if record.result == TestResult.FAILED and (record.exit_code is None or record.exit_code == 0):
            raise ValueError("Failed test evidence requires a non-zero exit code")
        return self._add("test_runs", record)

    def add_open_question(self, record: OpenQuestionRecord) -> OpenQuestionRecord:
        _require_source_refs(record.source_refs)
        _validate_actor(record.actor)
        _validate_timestamp(record.created_at)
        if not isinstance(record.status, QuestionStatus):
            raise ValueError("Questions require a recognized status")
        if not record.question.strip():
            raise ValueError("Question cannot be empty")
        return self._add("open_questions", record)

    def add_file_mention(self, record: FileMentionRecord) -> FileMentionRecord:
        _require_source_refs(record.source_refs)
        _validate_knowledge_status(record.status, record.actor)
        _validate_timestamp(record.created_at)
        _validate_relative_path(record.path)
        return self._add("file_mentions", record)

    def add_task(self, record: TaskRecord) -> TaskRecord:
        _require_source_refs(record.source_refs)
        _validate_actor(record.actor)
        _validate_timestamp(record.created_at)
        if not isinstance(record.status, TaskStatus):
            raise ValueError("Tasks require a recognized status")
        if not record.title.strip():
            raise ValueError("Task title cannot be empty")
        return self._add("tasks", record)

    def list_decisions(self) -> list[DecisionRecord]:
        return self._load("decisions")

    def list_constraints(self) -> list[ConstraintRecord]:
        return self._load("constraints")

    def list_test_evidence(self) -> list[TestEvidence]:
        return self._load("test_runs")

    def list_open_questions(self) -> list[OpenQuestionRecord]:
        return self._load("open_questions")

    def list_tasks(self) -> list[TaskRecord]:
        return self._load("tasks")

    def list_file_mentions(self) -> list[FileMentionRecord]:
        return self._load("file_mentions")
