import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ctxzip_core.events import SourceRef
from ctxzip_core.git_state import GitSnapshot
from ctxzip_core.knowledge import (
    ConstraintRecord,
    DecisionRecord,
    EventReference,
    FileMentionRecord,
    Freshness,
    KnowledgeStatus,
    KnowledgeStore,
    KnowledgeStoreError,
    OpenQuestionRecord,
    QuestionStatus,
    RecordActor,
    TestEvidence,
    TestResult,
    TaskRecord,
    TaskStatus,
    event_reference,
    new_record_id,
    knowledge_freshness,
    test_freshness,
)


class KnowledgeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.store = KnowledgeStore(Path(self.temp_dir.name) / "knowledge")
        self.source_ref = EventReference(
            event_id="event:fixture",
            source=SourceRef(
                source_id="codex",
                session_id="fixture-session",
                source_hash="a" * 64,
                parser_version="1",
                turn_number=1,
                record_index=2,
            ),
        )

    def test_decisions_round_trip_with_provenance_and_idempotent_add(self):
        record = DecisionRecord(
            id=new_record_id("decision"),
            statement="Keep event data local.",
            status=KnowledgeStatus.INFERRED,
            actor=RecordActor.EXTRACTOR,
            created_at="2026-01-01T00:00:00Z",
            source_refs=(self.source_ref,),
        )

        self.store.add_decision(record)
        self.store.add_decision(record)

        self.assertEqual(self.store.list_decisions(), [record])
        self.assertEqual(self.store.list_decisions()[0].source_refs[0], self.source_ref)
        saved = json.loads((self.store.directory / "decisions.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"], 3)
        self.assertEqual(set(path.name for path in self.store.directory.iterdir()), {"decisions.json"})

    def test_record_types_use_separate_collections(self):
        decision = DecisionRecord(
            id=new_record_id("decision"), statement="Use atomic replacement.",
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
        )
        constraint = ConstraintRecord(
            id=new_record_id("constraint"),
            statement="Do not store raw conversations in the repository.", scope="privacy",
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
        )
        question = OpenQuestionRecord(
            id=new_record_id("question"),
            question="Which providers should receive granular events next?",
            status=QuestionStatus.OPEN, actor=RecordActor.AGENT,
            created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
        )
        mention = FileMentionRecord(
            id=new_record_id("file"), path="ctxzip_core/events.py", symbol="SessionEvent",
            status=KnowledgeStatus.OBSERVED, actor=RecordActor.AGENT,
            created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
        )
        task = TaskRecord(
            id=new_record_id("task"), title="Add event-backed retrieval.",
            status=TaskStatus.IN_PROGRESS, actor=RecordActor.AGENT,
            created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
        )
        self.store.add_decision(decision)
        self.store.add_constraint(constraint)
        self.store.add_open_question(question)
        self.store.add_file_mention(mention)
        self.store.add_task(task)
        self.assertEqual(self.store.list_constraints(), [constraint])
        self.assertEqual(self.store.list_open_questions(), [question])
        self.assertEqual(self.store.list_file_mentions(), [mention])
        self.assertEqual(self.store.list_tasks(), [task])
        self.assertEqual(
            {path.name for path in self.store.directory.iterdir()},
            {"decisions.json", "constraints.json", "open_questions.json", "tasks.json", "file_mentions.json"},
        )

    def test_legacy_collection_loads_and_migrates_on_next_write(self):
        record = DecisionRecord(
            id="decision:legacy", statement="Legacy record", status=KnowledgeStatus.OBSERVED,
            actor=RecordActor.AGENT, created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
        )
        self.store.add_decision(record)
        path = self.store.directory / "decisions.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = 1
        payload["records"][0].pop("validity_paths")
        payload["records"][0].pop("validity_head_sha")
        path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = self.store.list_decisions()[0]
        self.assertEqual(loaded.validity_paths, ())
        self.assertIsNone(loaded.validity_head_sha)
        self.store.add_decision(DecisionRecord(
            id="decision:new", statement="New record", status=KnowledgeStatus.OBSERVED,
            actor=RecordActor.AGENT, created_at="2026-01-02T00:00:00Z", source_refs=(self.source_ref,),
        ))
        migrated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], 3)
        self.assertEqual(len(migrated["records"]), 2)

    def test_v2_constraint_collection_migrates_supersession_field_on_next_write(self):
        constraint = ConstraintRecord(
            id="constraint:legacy", statement="Keep archives local.", scope="privacy",
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
        )
        self.store.add_constraint(constraint)
        path = self.store.directory / "constraints.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = 2
        payload["records"][0].pop("supersedes")
        path.write_text(json.dumps(payload), encoding="utf-8")

        self.assertEqual(self.store.list_constraints(), [constraint])
        replacement = ConstraintRecord(
            id="constraint:new", statement="Keep canonical event snapshots local.", scope="privacy",
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-02T00:00:00Z", source_refs=(self.source_ref,),
            supersedes=constraint.id,
        )
        self.store.add_constraint(replacement)

        migrated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], 3)
        records = {record["id"]: record for record in migrated["records"]}
        self.assertEqual(records[constraint.id]["status"], KnowledgeStatus.INVALIDATED.value)
        self.assertIsNone(records[constraint.id]["supersedes"])

    def test_constraint_invalidation_requires_confirmed_same_scope_user_replacement(self):
        old = ConstraintRecord(
            id="constraint:old", statement="Keep archives local.", scope="privacy",
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
        )
        self.store.add_constraint(old)
        inferred = ConstraintRecord(
            id="constraint:inferred", statement="Send archives to a provider.", scope="privacy",
            status=KnowledgeStatus.INFERRED, actor=RecordActor.EXTRACTOR,
            created_at="2026-01-02T00:00:00Z", source_refs=(self.source_ref,), supersedes=old.id,
        )
        wrong_scope = ConstraintRecord(
            id="constraint:wrong-scope", statement="Another rule.", scope="style",
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-02T00:00:00Z", source_refs=(self.source_ref,), supersedes=old.id,
        )

        with self.assertRaisesRegex(ValueError, "user-confirmed constraint"):
            self.store.add_constraint(inferred)
        with self.assertRaisesRegex(ValueError, "same scope"):
            self.store.add_constraint(wrong_scope)
        self.assertEqual(self.store.list_constraints(), [old])

    def test_failed_atomic_constraint_invalidation_preserves_old_constraint(self):
        old = ConstraintRecord(
            id="constraint:atomic-old", statement="Keep archives local.", scope="privacy",
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
        )
        replacement = ConstraintRecord(
            id="constraint:atomic-new", statement="Keep event snapshots local.", scope="privacy",
            status=KnowledgeStatus.CONFIRMED, actor=RecordActor.USER,
            created_at="2026-01-02T00:00:00Z", source_refs=(self.source_ref,), supersedes=old.id,
        )
        self.store.add_constraint(old)

        with mock.patch("ctxzip_core.storage.os.replace", side_effect=OSError("simulated")):
            with self.assertRaises(OSError):
                self.store.add_constraint(replacement)

        self.assertEqual(self.store.list_constraints(), [old])

    def test_scoped_knowledge_freshness_is_conservative(self):
        record = DecisionRecord(
            id="decision:scoped", statement="Parser behavior", status=KnowledgeStatus.CONFIRMED,
            actor=RecordActor.USER, created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
            validity_paths=("src/parser.py",), validity_head_sha="a" * 40,
        )
        base = GitSnapshot(True, "main", "a" * 40, False, "1" * 64, "2" * 64, "3" * 64, (), (), "4" * 64)
        unrelated = GitSnapshot(True, "main", "a" * 40, True, "1" * 64, "2" * 64, "3" * 64, (), ("docs/readme.md",), "4" * 64)
        relevant = GitSnapshot(True, "main", "a" * 40, True, "1" * 64, "2" * 64, "3" * 64, (), ("src/parser.py",), "4" * 64)
        later_head = GitSnapshot(True, "main", "b" * 40, False, "1" * 64, "2" * 64, "3" * 64, (), (), "5" * 64)
        self.assertEqual(knowledge_freshness(record, base), Freshness.CURRENT)
        self.assertEqual(knowledge_freshness(record, unrelated), Freshness.CURRENT)
        self.assertEqual(knowledge_freshness(record, relevant), Freshness.POSSIBLY_STALE)
        self.assertEqual(knowledge_freshness(record, later_head), Freshness.POSSIBLY_STALE)
        unscoped = DecisionRecord(
            id=record.id, statement=record.statement, status=record.status, actor=record.actor,
            created_at=record.created_at, source_refs=record.source_refs,
        )
        self.assertEqual(knowledge_freshness(unscoped, base), Freshness.UNKNOWN)

    def test_invalid_persisted_validity_paths_are_rejected(self):
        record = DecisionRecord(
            id="decision:scoped", statement="Parser behavior", status=KnowledgeStatus.OBSERVED,
            actor=RecordActor.AGENT, created_at="2026-01-01T00:00:00Z", source_refs=(self.source_ref,),
            validity_paths=("src/parser.py",), validity_head_sha="a" * 40,
        )
        self.store.add_decision(record)
        path = self.store.directory / "decisions.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["records"][0]["validity_paths"] = ["../outside.py"]
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(KnowledgeStoreError, "Invalid record"):
            self.store.list_decisions()

    def test_extractor_cannot_confirm_claim_and_file_mentions_must_be_relative(self):
        with self.assertRaisesRegex(ValueError, "Only a user-authored"):
            self.store.add_decision(
                DecisionRecord(
                    id=new_record_id("decision"),
                    statement="Unverified claim",
                    status=KnowledgeStatus.CONFIRMED,
                    actor=RecordActor.EXTRACTOR,
                    created_at="2026-01-01T00:00:00Z",
                    source_refs=(self.source_ref,),
                )
            )
        with self.assertRaisesRegex(ValueError, "repository-relative"):
            self.store.add_file_mention(
                FileMentionRecord(
                    id=new_record_id("file"),
                    path="../outside.py",
                    symbol=None,
                    status=KnowledgeStatus.INFERRED,
                    actor=RecordActor.AGENT,
                    created_at="2026-01-01T00:00:00Z",
                    source_refs=(self.source_ref,),
                )
            )
        self.assertFalse(self.store.directory.exists())

    def test_knowledge_claims_require_timezone_aware_timestamps(self):
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            self.store.add_decision(
                DecisionRecord(
                    id=new_record_id("decision"),
                    statement="A claim with no timezone.",
                    status=KnowledgeStatus.INFERRED,
                    actor=RecordActor.AGENT,
                    created_at="2026-01-01T00:00:00",
                    source_refs=(self.source_ref,),
                )
            )
        self.assertFalse(self.store.directory.exists())

    def test_duplicate_id_with_different_contents_is_rejected_without_overwrite(self):
        first = DecisionRecord(
            id="decision:stable",
            statement="First statement",
            status=KnowledgeStatus.INFERRED,
            actor=RecordActor.AGENT,
            created_at="2026-01-01T00:00:00Z",
            source_refs=(self.source_ref,),
        )
        conflict = DecisionRecord(
            id=first.id,
            statement="Conflicting statement",
            status=KnowledgeStatus.INFERRED,
            actor=RecordActor.AGENT,
            created_at=first.created_at,
            source_refs=(self.source_ref,),
        )
        self.store.add_decision(first)

        with self.assertRaisesRegex(KnowledgeStoreError, "already uses this ID"):
            self.store.add_decision(conflict)
        self.assertEqual(self.store.list_decisions(), [first])

    def test_user_confirmed_replacement_supersedes_old_decision_atomically(self):
        old = DecisionRecord(
            id="decision:old",
            statement="Use the original parser design.",
            status=KnowledgeStatus.CONFIRMED,
            actor=RecordActor.USER,
            created_at="2026-01-01T00:00:00Z",
            source_refs=(self.source_ref,),
        )
        new = DecisionRecord(
            id="decision:new",
            statement="Use the provider-neutral event API.",
            status=KnowledgeStatus.CONFIRMED,
            actor=RecordActor.USER,
            created_at="2026-01-02T00:00:00Z",
            source_refs=(self.source_ref,),
            supersedes=old.id,
        )
        self.store.add_decision(old)

        self.store.add_decision(new)
        decisions = {record.id: record for record in self.store.list_decisions()}

        self.assertEqual(decisions[old.id].status, KnowledgeStatus.SUPERSEDED)
        self.assertEqual(decisions[new.id].supersedes, old.id)

    def test_inferred_decision_cannot_supersede_confirmed_claim(self):
        old = DecisionRecord(
            id="decision:confirmed",
            statement="Existing confirmed choice.",
            status=KnowledgeStatus.CONFIRMED,
            actor=RecordActor.USER,
            created_at="2026-01-01T00:00:00Z",
            source_refs=(self.source_ref,),
        )
        inferred = DecisionRecord(
            id="decision:inferred",
            statement="Unreviewed alternative.",
            status=KnowledgeStatus.INFERRED,
            actor=RecordActor.EXTRACTOR,
            created_at="2026-01-02T00:00:00Z",
            source_refs=(self.source_ref,),
            supersedes=old.id,
        )
        self.store.add_decision(old)

        with self.assertRaisesRegex(ValueError, "user-confirmed"):
            self.store.add_decision(inferred)
        self.assertEqual(self.store.list_decisions(), [old])

    def test_failed_atomic_supersession_preserves_previous_collection(self):
        old = DecisionRecord(
            id="decision:atomic-old",
            statement="Existing choice.",
            status=KnowledgeStatus.CONFIRMED,
            actor=RecordActor.USER,
            created_at="2026-01-01T00:00:00Z",
            source_refs=(self.source_ref,),
        )
        replacement = DecisionRecord(
            id="decision:atomic-new",
            statement="Replacement choice.",
            status=KnowledgeStatus.CONFIRMED,
            actor=RecordActor.USER,
            created_at="2026-01-02T00:00:00Z",
            source_refs=(self.source_ref,),
            supersedes=old.id,
        )
        self.store.add_decision(old)

        with mock.patch("ctxzip_core.storage.os.replace", side_effect=OSError("simulated")):
            with self.assertRaises(OSError):
                self.store.add_decision(replacement)

        self.assertEqual(self.store.list_decisions(), [old])
        self.assertEqual(list(self.store.directory.glob("*.tmp")), [])

    def test_test_evidence_tracks_worktree_fingerprint_freshness(self):
        record = TestEvidence(
            id=new_record_id("test"),
            actor=RecordActor.TEST_RUNNER,
            command="python -m unittest",
            result=TestResult.PASSED,
            exit_code=0,
            captured_at="2026-01-01T00:00:00Z",
            scope=("tests",),
            branch="main",
            head_sha="b" * 40,
            worktree_fingerprint="c" * 64,
            dirty=True,
        )
        self.store.add_test_evidence(record)
        same_snapshot = GitSnapshot(True, "main", "b" * 40, True, "", "", "", (), (), "c" * 64)
        changed_snapshot = GitSnapshot(True, "main", "b" * 40, True, "", "", "", (), (), "d" * 64)
        unavailable = GitSnapshot(False, None, None, False, "", "", "", (), (), None)

        self.assertEqual(self.store.list_test_evidence(), [record])
        self.assertEqual(test_freshness(record, same_snapshot), Freshness.CURRENT)
        self.assertEqual(test_freshness(record, changed_snapshot), Freshness.STALE)
        self.assertEqual(test_freshness(record, unavailable), Freshness.UNKNOWN)

    def test_unsupported_schema_is_not_rewritten(self):
        self.store.directory.mkdir(parents=True)
        path = self.store.directory / "decisions.json"
        original = '{"schema_version": 999, "records": []}'
        path.write_text(original, encoding="utf-8")

        with self.assertRaises(KnowledgeStoreError):
            self.store.list_decisions()
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_event_reference_copies_source_identity_without_event_content(self):
        from ctxzip_core.events import EventKind, EventRole, SessionEvent

        event = SessionEvent(
            id="event:one",
            session_id="fixture-session",
            sequence=1,
            timestamp=None,
            kind=EventKind.USER_MESSAGE,
            role=EventRole.USER,
            text="Sensitive message body stays out of the reference.",
            source=self.source_ref.source,
        )

        reference = event_reference(event)
        self.assertEqual(reference.event_id, event.id)
        self.assertEqual(reference.source, event.source)
        self.assertNotIn("Sensitive", repr(reference))


if __name__ == "__main__":
    unittest.main()
