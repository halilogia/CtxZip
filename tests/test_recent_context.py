import unittest
from pathlib import Path
import tempfile
from unittest import mock

from ctxzip_core import context_generation
from ctxzip_core.events import EventBuilder, EventKind, ParsedSession
from ctxzip_core.parser_common import Turn
from ctxzip_core.recent_context import (
    SessionTurns, select_uncovered_recent_turns, session_turns_from_events,
)


def make_turn(number, content, date="2026-01-01"):
    turn = Turn(number, f"{date}T00:00:{number:02d}Z")
    turn.lines.append(content)
    return turn


class RecentContextTests(unittest.TestCase):
    def test_recent_context_uses_turn_transcript_events_when_available(self):
        legacy_turn = make_turn(1, "Legacy turn text should not be selected.")
        event = EventBuilder("chatgpt", "safe-session", "d" * 64, "2").build(
            record_index=None,
            record_ids=("safe-user-node", "safe-assistant-node"),
            turn_number=1,
            timestamp="2026-01-01T00:00:01Z",
            kind=EventKind.TURN_TRANSCRIPT,
            text="Canonical event transcript.",
        )
        parsed = ParsedSession([legacy_turn], {}, [event])

        session = session_turns_from_events(
            parsed,
            session_key="chatgpt/safe-session",
            source_id="chatgpt",
            session_id="safe-session",
            source_hash="e" * 64,
            parser_version="2",
        )
        recent = select_uncovered_recent_turns([session], [])

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].text, "Canonical event transcript.")
        self.assertEqual(recent[0].source_hash, "d" * 64)

    def test_claude_private_thinking_opt_in_stays_out_of_event_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "session.jsonl"
            source.write_text("{}\n", encoding="utf-8")
            private_turn = make_turn(1, "Explicitly opted-in private thinking.")
            settings = {"dusunceleri_dahil_et": True, "language": "en"}
            with mock.patch.object(
                context_generation, "list_sessions",
                return_value=[("claude-code", "safe-session", source)],
            ), mock.patch.object(
                context_generation, "read_session", return_value=([private_turn], {}),
            ) as read_turns, mock.patch.object(
                context_generation, "read_session_events",
                side_effect=AssertionError("private thinking must not enter canonical events"),
            ) as read_events:
                items = context_generation._recent_context_items(
                    Path(directory), settings, "en", 32000, {"bolumler": []},
                )

        self.assertEqual(len(items), 1)
        self.assertIn("Explicitly opted-in private thinking.", items[0].body)
        read_turns.assert_called_once()
        read_events.assert_not_called()

    def test_excludes_all_chapter_ranges_and_returns_only_the_recent_tail(self):
        first = SessionTurns(
            "codex/first", "a" * 64,
            tuple(make_turn(number, f"first-{number}") for number in range(1, 4)),
        )
        second = SessionTurns(
            "claude-code/second", "b" * 64,
            (make_turn(1, "second-1", "2026-01-02"),),
        )
        chapters = [
            {"oturum": "codex/first", "tur_baslangic": 1, "tur_bitis": 2},
            {"oturum": "codex/first", "tur_baslangic": 2, "tur_bitis": 2},
        ]

        recent = select_uncovered_recent_turns([first, second], chapters, limit=2)

        self.assertEqual([(turn.session_key, turn.turn_number) for turn in recent], [
            ("codex/first", 3), ("claude-code/second", 1),
        ])
        self.assertEqual(recent[0].source, f"codex/first#T3@{'a' * 12}")
        self.assertNotIn("first-1", [turn.text for turn in recent])

    def test_empty_turns_and_invalid_inputs_are_handled_explicitly(self):
        session = SessionTurns("codex/empty", "c" * 64, ())
        self.assertEqual(select_uncovered_recent_turns([session], [], limit=5), [])
        with self.assertRaisesRegex(ValueError, "limit must be positive"):
            select_uncovered_recent_turns([session], [], limit=0)
        invalid = SessionTurns("codex/bad", "invalid", (make_turn(1, "content"),))
        with self.assertRaisesRegex(ValueError, "source SHA-256"):
            select_uncovered_recent_turns([invalid], [])


if __name__ == "__main__":
    unittest.main()
