"""Versioning, replacement, and privacy checks for canonical event snapshots."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ctxzip_core import event_store
from ctxzip_core.event_store import (
    EventStoreError, SCHEMA_ID, SCHEMA_VERSION, event_references_for_turn,
    remove_session_events,
    resolve_event_reference, save_session_events,
)
from ctxzip_core.events import EventReference, ParsedSession, events_from_turns
from ctxzip_core.parser_common import Turn


class EventStoreTests(unittest.TestCase):
    def setUp(self):
        turn = Turn(1, "2026-01-01 00:00:00")
        turn.lines.append("Sanitized event-store message.")
        self.turns = [turn]
        self.source = {
            "source_id": "claude-code",
            "session_id": "private-session-id",
            "source_hash": "a" * 64,
            "parser_version": "1",
        }

    def parsed(self, **source_overrides):
        events = events_from_turns(self.turns, **(self.source | source_overrides))
        return ParsedSession(self.turns, {}, events)

    def test_snapshot_is_versioned_atomic_data_and_does_not_put_source_path_in_filename(self):
        with tempfile.TemporaryDirectory(prefix="private-source-path-") as temporary:
            project_dir = Path(temporary) / "project"
            self.assertTrue(save_session_events(project_dir, self.parsed()))
            snapshots = list((project_dir / ".ctxzip-events" / "claude-code").glob("*.json"))
            self.assertEqual(len(snapshots), 1)
            self.assertNotIn("private-session-id", snapshots[0].name)
            value = json.loads(snapshots[0].read_text(encoding="utf-8"))

        self.assertEqual(value["schema"], SCHEMA_ID)
        self.assertEqual(value["schema_version"], SCHEMA_VERSION)
        self.assertEqual(value["source_hash"], self.source["source_hash"])
        self.assertEqual(value["events"][0]["text"], "Sanitized event-store message.")

    def test_schema_v1_snapshot_remains_resolvable_after_schema_v2_addition(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            parsed = self.parsed()
            save_session_events(project_dir, parsed)
            snapshot_path = event_store._snapshot_path(
                project_dir, self.source["source_id"], self.source["session_id"],
            )
            value = json.loads(snapshot_path.read_text(encoding="utf-8"))
            value["schema_version"] = 1
            for event in value["events"]:
                event["source"].pop("record_ids")
            snapshot_path.write_text(json.dumps(value), encoding="utf-8")

            reference = event_references_for_turn(
                project_dir, self.source["source_id"], self.source["session_id"], 1,
            )[0]
            resolved = resolve_event_reference(project_dir, reference)

        self.assertEqual(resolved.id, parsed.events[0].id)
        self.assertEqual(resolved.source.record_ids, ())

    def test_repeated_snapshot_is_idempotent_and_source_change_replaces_old_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            first = self.parsed()
            self.assertTrue(save_session_events(project_dir, first))
            snapshot_path = next((project_dir / ".ctxzip-events" / "claude-code").glob("*.json"))
            original_bytes = snapshot_path.read_bytes()

            self.assertFalse(save_session_events(project_dir, first))
            self.assertEqual(snapshot_path.read_bytes(), original_bytes)

            changed = self.parsed(source_hash="b" * 64)
            self.assertTrue(save_session_events(project_dir, changed))
            value = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(value["source_hash"], "b" * 64)
            self.assertEqual(len(list(snapshot_path.parent.glob("*.json"))), 1)
            self.assertEqual(value["events"][0]["id"], changed.events[0].id)

    def test_event_references_for_turn_are_source_version_linked(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            second = Turn(2, "2026-01-01 00:01:00")
            second.lines.append("Sanitized second-turn message.")
            turns = [self.turns[0], second]
            parsed = ParsedSession(turns, {}, events_from_turns(
                turns, source_id=self.source["source_id"],
                session_id=self.source["session_id"], source_hash=self.source["source_hash"],
                parser_version=self.source["parser_version"],
            ))
            save_session_events(project_dir, parsed)

            references = event_references_for_turn(
                project_dir, self.source["source_id"], self.source["session_id"], 2,
            )
            self.assertEqual(len(references), 1)
            self.assertEqual(references[0].event_id, parsed.events[-1].id)
            self.assertEqual(references[0].source.source_hash, self.source["source_hash"])
            self.assertEqual(references[0].source.turn_number, 2)
            self.assertEqual(event_references_for_turn(
                project_dir, self.source["source_id"], self.source["session_id"], 3,
            ), ())
            with self.assertRaisesRegex(ValueError, "positive integer"):
                event_references_for_turn(
                    project_dir, self.source["source_id"], self.source["session_id"], 0,
                )

    def test_old_event_references_resolve_after_source_and_parser_updates(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            first = self.parsed()
            save_session_events(project_dir, first)
            old_reference = event_references_for_turn(
                project_dir, "claude-code", "private-session-id", 1,
            )[0]

            changed_source = self.parsed(source_hash="b" * 64)
            save_session_events(project_dir, changed_source)
            source_resolution = resolve_event_reference(project_dir, old_reference)
            self.assertEqual(source_resolution.id, first.events[0].id)
            self.assertEqual(source_resolution.source.source_hash, "a" * 64)
            self.assertEqual(source_resolution.text, "Sanitized event-store message.")

            old_parser_reference = event_references_for_turn(
                project_dir, "claude-code", "private-session-id", 1,
            )[0]
            changed_parser = self.parsed(source_hash="b" * 64, parser_version="2")
            save_session_events(project_dir, changed_parser)
            parser_resolution = resolve_event_reference(project_dir, old_parser_reference)
            self.assertEqual(parser_resolution.source.parser_version, "1")
            latest_reference = event_references_for_turn(
                project_dir, "claude-code", "private-session-id", 1,
            )[0]
            self.assertEqual(
                resolve_event_reference(project_dir, latest_reference).source.parser_version,
                "2",
            )
            versions = list((project_dir / ".ctxzip-events" / "versions" / "claude-code").rglob("*.json"))
            self.assertEqual(len(versions), 3)

    def test_version_snapshots_are_idempotent_and_reject_identity_collisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            parsed = self.parsed()
            self.assertTrue(save_session_events(project_dir, parsed))
            version_file = next((project_dir / ".ctxzip-events" / "versions").rglob("*.json"))
            original_bytes = version_file.read_bytes()
            self.assertFalse(save_session_events(project_dir, parsed))
            self.assertEqual(version_file.read_bytes(), original_bytes)

            version_file.write_text('{"schema":"unknown"}', encoding="utf-8")
            malformed = version_file.read_bytes()
            with self.assertRaises(EventStoreError):
                save_session_events(project_dir, parsed)
            self.assertEqual(version_file.read_bytes(), malformed)

    def test_latest_write_failure_keeps_previous_snapshot_and_archives_both_versions(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            first = self.parsed()
            save_session_events(project_dir, first)
            old_reference = event_references_for_turn(
                project_dir, "claude-code", "private-session-id", 1,
            )[0]
            changed = self.parsed(source_hash="b" * 64)
            atomic_write_json = event_store.atomic_write_json

            def fail_only_latest(path, value):
                if Path(path) == event_store._snapshot_path(project_dir, "claude-code", "private-session-id"):
                    raise OSError("injected latest snapshot failure")
                return atomic_write_json(path, value)

            with mock.patch.object(event_store, "atomic_write_json", side_effect=fail_only_latest):
                with self.assertRaisesRegex(OSError, "injected"):
                    save_session_events(project_dir, changed)

            latest_path = event_store._snapshot_path(project_dir, "claude-code", "private-session-id")
            self.assertEqual(json.loads(latest_path.read_text(encoding="utf-8"))["source_hash"], "a" * 64)
            self.assertEqual(resolve_event_reference(project_dir, old_reference).id, first.events[0].id)
            new_reference = EventReference(changed.events[0].id, changed.events[0].source)
            self.assertEqual(
                resolve_event_reference(project_dir, new_reference).source.source_hash,
                "b" * 64,
            )
            changed_reference = event_references_for_turn(
                project_dir, "claude-code", "private-session-id", 1,
            )
            self.assertEqual(changed_reference[0].source.source_hash, "a" * 64)
            version_files = list((project_dir / ".ctxzip-events" / "versions").rglob("*.json"))
            self.assertEqual(len(version_files), 2)

    def test_version_archive_write_failure_leaves_latest_snapshot_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            first = self.parsed()
            save_session_events(project_dir, first)
            latest_path = event_store._snapshot_path(project_dir, "claude-code", "private-session-id")
            original_latest = latest_path.read_bytes()
            changed = self.parsed(source_hash="b" * 64)
            atomic_write_json = event_store.atomic_write_json

            def fail_only_version(path, value):
                if "versions" in Path(path).parts:
                    raise OSError("injected event history failure")
                return atomic_write_json(path, value)

            with mock.patch.object(event_store, "atomic_write_json", side_effect=fail_only_version):
                with self.assertRaisesRegex(OSError, "event history"):
                    save_session_events(project_dir, changed)

            self.assertEqual(latest_path.read_bytes(), original_latest)
            version_files = list((project_dir / ".ctxzip-events" / "versions").rglob("*.json"))
            self.assertEqual(len(version_files), 1)

    def test_removing_latest_snapshot_retains_referenced_event_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            parsed = self.parsed()
            save_session_events(project_dir, parsed)
            reference = event_references_for_turn(
                project_dir, "claude-code", "private-session-id", 1,
            )[0]

            self.assertTrue(remove_session_events(project_dir, "claude-code", "private-session-id"))
            self.assertEqual(event_references_for_turn(
                project_dir, "claude-code", "private-session-id", 1,
            ), ())
            self.assertEqual(resolve_event_reference(project_dir, reference).id, parsed.events[0].id)

    def test_failed_history_archive_prevents_latest_snapshot_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            parsed = self.parsed()
            save_session_events(project_dir, parsed)
            latest_path = event_store._snapshot_path(project_dir, "claude-code", "private-session-id")
            original_latest = latest_path.read_bytes()
            legacy_version_file = next((project_dir / ".ctxzip-events" / "versions").rglob("*.json"))
            legacy_version_file.unlink()
            atomic_write_json = event_store.atomic_write_json

            def fail_only_version(path, value):
                if "versions" in Path(path).parts:
                    raise OSError("injected event removal history failure")
                return atomic_write_json(path, value)

            with mock.patch.object(event_store, "atomic_write_json", side_effect=fail_only_version):
                with self.assertRaisesRegex(OSError, "removal history"):
                    remove_session_events(project_dir, "claude-code", "private-session-id")
            self.assertTrue(latest_path.exists())
            self.assertEqual(latest_path.read_bytes(), original_latest)

    def test_parser_version_change_replaces_snapshot_and_incompatible_state_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            self.assertTrue(save_session_events(project_dir, self.parsed()))
            snapshot_path = next((project_dir / ".ctxzip-events" / "claude-code").glob("*.json"))
            self.assertTrue(save_session_events(project_dir, self.parsed(parser_version="2")))
            value = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(value["parser_version"], "2")

            snapshot_path.write_text('{"schema":"unknown"}', encoding="utf-8")
            corrupted = snapshot_path.read_bytes()
            with self.assertRaises(EventStoreError):
                save_session_events(project_dir, self.parsed(parser_version="3"))
            self.assertEqual(snapshot_path.read_bytes(), corrupted)


if __name__ == "__main__":
    unittest.main()
