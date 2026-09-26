"""User-authored knowledge capture remains linked to exact archived events."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import ctxzip
from ctxzip_core.event_store import save_session_events
from ctxzip_core.events import ParsedSession, events_from_turns
from ctxzip_core.knowledge import KnowledgeStore
from ctxzip_core.knowledge_capture import capture_knowledge
from ctxzip_core.parser_common import Turn


class KnowledgeCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        turn = Turn(1, "2026-01-01T00:00:00Z")
        turn.lines.append("Sanitized user-approved evidence from a test conversation.")
        self.parsed = ParsedSession(
            [turn], {}, events_from_turns(
                [turn], source_id="codex", session_id="synthetic-session",
                source_hash="a" * 64, parser_version="1",
            ),
        )
        save_session_events(self.project, self.parsed)

    def tearDown(self):
        self.temporary.cleanup()

    def capture(self, kind, **options):
        return capture_knowledge(
            self.project, kind=kind, source_id="codex", session_id="synthetic-session",
            turn_number=1, **options,
        )

    def test_captures_each_user_authored_record_type_with_source_version(self):
        decision = self.capture("decision", text="Use the existing event store.")
        constraint = self.capture("constraint", text="Keep summaries editable.", scope="storage")
        task = self.capture("task", text="Add another parser fixture.")
        question = self.capture("question", text="Which provider format comes next?")
        file_mention = self.capture("file", path="ctxzip_core/events.py", symbol="SessionEvent")

        self.assertEqual(decision.status.value, "confirmed")
        self.assertEqual(constraint.scope, "storage")
        self.assertEqual(task.status.value, "open")
        self.assertEqual(question.status.value, "open")
        self.assertEqual(file_mention.symbol, "SessionEvent")
        for record in (decision, constraint, task, question, file_mention):
            self.assertEqual(len(record.source_refs), 1)
            self.assertEqual(record.source_refs[0].event_id, self.parsed.events[0].id)
            self.assertEqual(record.source_refs[0].source.source_hash, "a" * 64)

    def test_missing_source_event_and_unsupported_providers_are_rejected_without_records(self):
        with self.assertRaisesRegex(ValueError, "No archived events"):
            capture_knowledge(
                self.project, kind="task", source_id="codex", session_id="missing",
                turn_number=1, text="Never write this without provenance.",
            )
        with self.assertRaisesRegex(ValueError, "supported event source"):
            capture_knowledge(
                self.project, kind="task", source_id="antigravity", session_id="synthetic-session",
                turn_number=1, text="Unsupported source.",
            )
        self.assertEqual(KnowledgeStore(self.project / "knowledge").list_tasks(), [])

    def test_type_requirements_and_incompatible_options_are_rejected(self):
        cases = (
            ("decision", {}, "Decision text is required"),
            ("constraint", {"text": "No empty scope"}, "Constraint text and scope are required"),
            ("file", {}, "File path is required"),
            ("task", {"text": "A task", "scope": "wrong"}, "Scope applies only to constraints"),
            ("question", {"text": "A question", "status": "confirmed"}, "Verification status applies"),
            ("decision", {"text": "A claim", "validity_paths": ("src/a.py",)}, "require a Git HEAD"),
        )
        for kind, options, message in cases:
            with self.subTest(kind=kind, options=options), self.assertRaisesRegex(ValueError, message):
                self.capture(kind, **options)

    def test_confirmed_replacement_is_explicit_and_same_scope_constraints_only(self):
        original = self.capture("constraint", text="Use JSON files.", scope="storage")
        replacement = self.capture(
            "constraint", text="Use a local database.", scope="storage", supersedes=original.id,
        )
        constraints = KnowledgeStore(self.project / "knowledge").list_constraints()
        self.assertEqual([record.status.value for record in constraints], ["invalidated", "confirmed"])
        self.assertEqual(replacement.supersedes, original.id)
        with self.assertRaisesRegex(ValueError, "same scope"):
            self.capture(
                "constraint", text="Replace across scopes.", scope="security", supersedes=replacement.id,
            )

    def test_cli_capture_is_localized_and_does_not_echo_record_text(self):
        settings_path = Path(self.temporary.name) / "settings.json"
        settings_path.write_text(json.dumps({
            "arsiv_klasoru": str(self.project.parent / "archive"), "language": "en",
        }), encoding="utf-8")
        archived_project = self.project.parent / "archive" / "Demo"
        save_session_events(archived_project, self.parsed)
        output = io.StringIO()
        secret_body = "Private decision text that must not appear in CLI output."
        arguments = [
            "ctxzip.py", "--settings", str(settings_path), "knowledge", "add",
            "--project", "Demo", "--kind", "decision", "--source", "codex",
            "--session", "synthetic-session", "--turn", "1", "--text", secret_body,
        ]
        with mock.patch.object(sys, "argv", arguments), mock.patch.object(ctxzip, "call_llm") as llm_call, \
                contextlib.redirect_stdout(output):
            ctxzip.main()

        self.assertIn("Recorded decision", output.getvalue())
        self.assertNotIn(secret_body, output.getvalue())
        records = KnowledgeStore(archived_project / "knowledge").list_decisions()
        self.assertEqual(records[0].statement, secret_body)
        llm_call.assert_not_called()

        output = io.StringIO()
        arguments[3] = "hafiza"
        arguments[1:1] = ["--language", "tr"]
        with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stdout(output):
            ctxzip.main()
        self.assertIn("eklendi", output.getvalue())


if __name__ == "__main__":
    unittest.main()
