import unittest

from ctxzip_core.events import EventBuilder, EventKind, EventRole, events_from_turns
from ctxzip_core.parser_common import Turn


class CanonicalEventTests(unittest.TestCase):
    def setUp(self):
        self.turns = [Turn(1, "2026-01-01 00:00:00")]
        self.turns[0].lines.extend(["**User:** Safe task", "**Assistant:** Safe result"])
        self.source = {
            "source_id": "codex",
            "session_id": "fixture-session",
            "source_hash": "a" * 64,
            "parser_version": "1",
        }

    def test_turn_bridge_preserves_text_and_records_versioned_provenance(self):
        events = events_from_turns(self.turns, **self.source)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.kind, EventKind.TURN_TRANSCRIPT)
        self.assertIsNone(event.role)
        self.assertEqual(event.text, self.turns[0].text())
        self.assertEqual(event.sequence, 1)
        self.assertEqual(event.timestamp, "2026-01-01 00:00:00")
        self.assertEqual(event.source.source_hash, self.source["source_hash"])
        self.assertEqual(event.source.parser_version, "1")
        self.assertTrue(event.id.startswith("event:"))

    def test_event_identity_is_stable_for_same_source_and_changes_with_source_version(self):
        first = events_from_turns(self.turns, **self.source)[0]
        repeated = events_from_turns(self.turns, **self.source)[0]
        changed = events_from_turns(
            self.turns, **(self.source | {"source_hash": "b" * 64})
        )[0]

        self.assertEqual(first.id, repeated.id)
        self.assertNotEqual(first.id, changed.id)

    def test_rejects_invalid_source_hash_and_missing_identity(self):
        with self.assertRaises(ValueError):
            events_from_turns(self.turns, **(self.source | {"source_hash": "unknown"}))
        with self.assertRaises(ValueError):
            events_from_turns(self.turns, **(self.source | {"session_id": ""}))

    def test_source_record_ids_are_validated_and_part_of_event_identity(self):
        first_builder = EventBuilder("chatgpt", "fixture-session", "a" * 64, "2")
        second_builder = EventBuilder("chatgpt", "fixture-session", "a" * 64, "2")
        first = first_builder.build(
            record_index=None, record_ids=("mapping-node-a",), turn_number=1,
            timestamp=None, kind=EventKind.TURN_TRANSCRIPT, text="Sanitized turn.",
        )
        second = second_builder.build(
            record_index=None, record_ids=("mapping-node-b",), turn_number=1,
            timestamp=None, kind=EventKind.TURN_TRANSCRIPT, text="Sanitized turn.",
        )

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.source.record_ids, ("mapping-node-a",))
        with self.assertRaisesRegex(ValueError, "non-empty strings"):
            first_builder.build(
                record_index=None, record_ids=(1,), turn_number=1,
                timestamp=None, kind=EventKind.TURN_TRANSCRIPT, text="Sanitized turn.",
            )

    def test_roles_are_explicit_for_future_provider_adapters(self):
        self.assertEqual(EventRole.USER.value, "user")
        self.assertEqual(EventRole.TOOL.value, "tool")


if __name__ == "__main__":
    unittest.main()
