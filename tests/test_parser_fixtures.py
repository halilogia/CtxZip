import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ctxzip_core.event_store import event_references_for_turn, resolve_event_reference, save_session_events
from ctxzip_core.events import EventKind
from ctxzip_core.parser_claude import parse_claude_session, parse_claude_turns
from ctxzip_core.parser_codex import parse_codex_session, parse_codex_turns
from ctxzip_core.parser_chatgpt import parse_chatgpt_session, parse_chatgpt_turns
from ctxzip_core.parsers import EVENT_PARSERS, PARSERS, read_session_events
from ctxzip_core.source_capabilities import SOURCE_CAPABILITIES, get_source_capabilities
from scripts.check_staged import content_issues


FIXTURE_ROOT = Path(__file__).parent / "fixtures"
SAFE_VALUES = {
    "Sanitized example message.",
    "Sanitized example message.\nSanitized example message.\nSanitized example message.",
    "branch:main",
    "Sanitized reasoning sample.",
    "Sanitized tool output.",
    "Sanitized tool result.",
    "Sanitized example text.",
    "example arguments",
    "Sanitized example prompt.",
    "Sanitized example summary.",
    "Sanitized example query.",
    "Sanitized example description.",
    "Sanitized example title.",
    "Sanitized example reason.",
    "<redacted>",
    "unknown",
    "fixture-id",
    "example_tool",
    "example_tool_id",
    "main",
    "/workspace/example",
    "src/example.py",
    "2026-01-01T00:00:00Z",
    "1",
    "user",
    "assistant",
    "system",
    "session_meta",
    "response_item",
    "message",
    "tool_result",
    "tool_use",
    "text",
    "input_text",
    "output_text",
    "image",
    "thinking",
    "function_call",
    "custom_tool_call",
    "local_shell_call",
    "reasoning",
    "file-history-snapshot",
    "turn_context",
    "event_msg",
    "command",
    "developer",
    "tool",
    "function",
    "user_message",
    "assistant_message",
    "tool_call",
    "metadata",
    "reasoning_summary",
    "fixture-conversation-one", "fixture-conversation-two", "root", "root-2", "user-1", "user-2",
    "assistant-1", "assistant-2", "assistant-current", "assistant-branch", "content_type",
    "current_node", "mapping", "parent", "children", "parts", "create_time", "id", "title",
}


class SanitizedParserFixtureTests(unittest.TestCase):
    def test_staged_content_guard_detects_a_personal_path_pattern(self):
        personal_path = "C:" + "\\" + "Us" + "ers" + "\\example\\project\\session.jsonl"
        self.assertIn(
            "personal home path",
            content_issues(personal_path.encode("utf-8")),
        )

    def test_capability_registry_matches_parser_keys_and_states_antigravity_limit(self):
        self.assertEqual(set(SOURCE_CAPABILITIES), set(PARSERS))
        self.assertEqual(set(EVENT_PARSERS), {"claude-code", "codex", "chatgpt"})
        self.assertIn("tool_result", get_source_capabilities("claude-code").granular_event_kinds)
        self.assertFalse(get_source_capabilities("antigravity").granular_event_kinds)
        antigravity = get_source_capabilities("antigravity")
        self.assertEqual(antigravity.history_scope, "markdown_artifacts")
        self.assertFalse(antigravity.normalized_messages)
        self.assertFalse(antigravity.event_timestamps)
        self.assertTrue(antigravity.file_timestamps)
        self.assertIn("not a full chat transcript", antigravity.limitation)

    def test_chatgpt_export_fixture_is_sanitized_and_branch_aware(self):
        fixture = FIXTURE_ROOT / "chatgpt" / "conversations.json.fixture"
        content = fixture.read_text(encoding="utf-8")
        self.assertEqual(content_issues(content.encode("utf-8")), [])
        values = set()
        def collect(value):
            if isinstance(value, dict):
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
            elif isinstance(value, str):
                values.add(value)
        collect(json.loads(content))
        self.assertLessEqual(values, SAFE_VALUES)

        conversations = json.loads(content)
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "conversation-one.json"
            first.write_text(json.dumps(conversations[0]), encoding="utf-8")
            turns, _metadata = parse_chatgpt_turns(first)
            self.assertEqual(len(turns), 1)
            self.assertIn("Sanitized example message.", turns[0].text())
            self.assertIn("Sanitized tool output.", turns[0].text())
            self.assertNotIn("Sanitized reasoning sample.", turns[0].text())
            parsed = parse_chatgpt_session(first, False)
            self.assertTrue(parsed.events)
            self.assertEqual(parsed.events[0].source.source_id, "chatgpt")
            self.assertEqual(parsed.events[0].source.parser_version, "2")
            self.assertIsNone(parsed.events[0].source.record_index)
            self.assertEqual(
                parsed.events[0].source.record_ids,
                ("user-1", "assistant-1", "assistant-current"),
            )
            self.assertIn("record_ids", get_source_capabilities("chatgpt").limitation)
            project = Path(directory) / "project"
            save_session_events(project, parsed)
            reference = event_references_for_turn(
                project, "chatgpt", parsed.events[0].session_id, 1,
            )[0]
            resolved = resolve_event_reference(project, reference)
            self.assertEqual(resolved.id, parsed.events[0].id)
            self.assertIsNone(resolved.source.record_index)
            self.assertEqual(tuple(resolved.source.record_ids), reference.source.record_ids)

    def assert_fixture_is_redacted(self, path: Path) -> list[dict]:
        content = path.read_text(encoding="utf-8")
        self.assertEqual(content_issues(content.encode("utf-8")), [])
        rows = [json.loads(line) for line in content.splitlines() if line.strip()]
        values: set[str] = set()

        def collect(value):
            if isinstance(value, dict):
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
            elif isinstance(value, str):
                values.add(value)

        collect(rows)
        self.assertLessEqual(values, SAFE_VALUES)
        return rows

    def assert_json_fixture_is_redacted(self, path: Path):
        content = path.read_text(encoding="utf-8")
        self.assertEqual(content_issues(content.encode("utf-8")), [])
        value = json.loads(content)
        values: set[str] = set()

        def collect(item):
            if isinstance(item, dict):
                for child in item.values():
                    collect(child)
            elif isinstance(item, list):
                for child in item:
                    collect(child)
            elif isinstance(item, str):
                values.add(item)

        collect(value)
        self.assertLessEqual(values, SAFE_VALUES)
        return value

    def test_claude_real_format_fixture_is_sanitized_and_parses(self):
        fixture = FIXTURE_ROOT / "claude" / "normal.jsonl.fixture"
        self.assert_fixture_is_redacted(fixture)

        turns, metadata = parse_claude_turns(fixture, include_thinking=True, language="en")

        self.assertEqual(len(turns), 1)
        self.assertEqual(
            turns[0].text(),
            "**User:** Sanitized example message.\n"
            "  - → example_tool: Sanitized example description.\n"
            "**Assistant:** Sanitized example message.",
        )
        self.assertEqual(metadata["dal"], "main")

    def test_codex_real_format_fixture_is_sanitized_and_parses(self):
        fixture = FIXTURE_ROOT / "codex" / "normal.jsonl.fixture"
        self.assert_fixture_is_redacted(fixture)

        turns, metadata = parse_codex_turns(fixture, include_thinking=True, language="en")

        self.assertEqual(len(turns), 1)
        self.assertEqual(
            turns[0].text(),
            "**User:** Sanitized example message.\n"
            "Sanitized example message.\n"
            "Sanitized example message.\n"
            "**Assistant:** Sanitized example message.",
        )
        self.assertEqual(metadata["dal"], "main")

    def test_provider_parsers_emit_granular_source_linked_events(self):
        cases = (
            ("claude-code", FIXTURE_ROOT / "claude" / "normal.jsonl.fixture", parse_claude_session),
            ("codex", FIXTURE_ROOT / "codex" / "normal.jsonl.fixture", parse_codex_session),
        )
        for source_id, fixture, parser in cases:
            with self.subTest(source=source_id):
                parsed = parser(fixture, include_thinking=True, language="en")
                kinds = [event.kind for event in parsed.events]
                expected_kinds = (
                    [EventKind.USER_MESSAGE, EventKind.TOOL_CALL, EventKind.ASSISTANT_MESSAGE]
                    if source_id == "claude-code"
                    else [EventKind.METADATA, EventKind.USER_MESSAGE, EventKind.ASSISTANT_MESSAGE]
                )
                self.assertEqual(kinds, expected_kinds)
                self.assertEqual(len(parsed.turns), 1)
                self.assertTrue(all(event.source.source_hash for event in parsed.events))
                self.assertTrue(all(event.source.parser_version == "1" for event in parsed.events))
                self.assertEqual(parsed.events[0].source.source_id, source_id)
                self.assertEqual(parsed.events[0].source.record_index, 0)

    def test_provider_events_match_sanitized_normalized_goldens(self):
        cases = (
            ("claude", parse_claude_session),
            ("codex", parse_codex_session),
        )
        for provider, parser in cases:
            with self.subTest(provider=provider):
                source = FIXTURE_ROOT / provider / "normal.jsonl.fixture"
                expected_path = FIXTURE_ROOT / provider / "normal.events.json.fixture"
                self.assert_fixture_is_redacted(source)
                expected = self.assert_json_fixture_is_redacted(expected_path)
                parsed = parser(source, include_thinking=True, language="en")
                actual = [
                    {
                        "kind": event.kind.value,
                        "role": event.role.value if event.role else None,
                        "text": event.text,
                        "tool_name": event.tool_name,
                        "tool_input_summary": event.tool_input_summary,
                        "tool_output": event.tool_output,
                        "timestamp": event.timestamp,
                        "turn_number": event.source.turn_number,
                        "record_index": event.source.record_index,
                    }
                    for event in parsed.events
                ]
                self.assertEqual(actual, expected)

    def test_codex_tool_heavy_fixture_matches_normalized_golden(self):
        source = FIXTURE_ROOT / "codex" / "tool-heavy.jsonl.fixture"
        expected_path = FIXTURE_ROOT / "codex" / "tool-heavy.events.json.fixture"
        self.assert_fixture_is_redacted(source)
        expected = self.assert_json_fixture_is_redacted(expected_path)

        parsed = parse_codex_session(source, include_thinking=True, language="en")
        actual = [
            {
                "kind": event.kind.value,
                "role": event.role.value if event.role else None,
                "text": event.text,
                "tool_name": event.tool_name,
                "tool_input_summary": event.tool_input_summary,
                "tool_output": event.tool_output,
                "timestamp": event.timestamp,
                "turn_number": event.source.turn_number,
                "record_index": event.source.record_index,
            }
            for event in parsed.events
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(len(parsed.turns), 1)

        without_reasoning = parse_codex_session(source, include_thinking=False, language="en")
        self.assertNotIn(
            EventKind.REASONING_SUMMARY,
            [event.kind for event in without_reasoning.events],
        )

    def test_claude_tool_heavy_fixture_matches_normalized_golden(self):
        source = FIXTURE_ROOT / "claude" / "tool-heavy.jsonl.fixture"
        expected_path = FIXTURE_ROOT / "claude" / "tool-heavy.events.json.fixture"
        self.assert_fixture_is_redacted(source)
        expected = self.assert_json_fixture_is_redacted(expected_path)

        parsed = parse_claude_session(source, include_thinking=False, language="en")
        actual = [
            {
                "kind": event.kind.value,
                "role": event.role.value if event.role else None,
                "text": event.text,
                "tool_name": event.tool_name,
                "tool_input_summary": event.tool_input_summary,
                "tool_output": event.tool_output,
                "timestamp": event.timestamp,
                "turn_number": event.source.turn_number,
                "record_index": event.source.record_index,
            }
            for event in parsed.events
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(len(parsed.turns), 2)

    def test_incomplete_final_jsonl_row_does_not_drop_complete_events(self):
        cases = (
            ("claude", parse_claude_session),
            ("codex", parse_codex_session),
        )
        for provider, parser in cases:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                source = FIXTURE_ROOT / provider / "normal.jsonl.fixture"
                self.assert_fixture_is_redacted(source)
                incomplete = Path(directory) / "interrupted.jsonl"
                incomplete.write_bytes(source.read_bytes() + b'{"type":"interrupted","payload":')
                parsed = parser(incomplete, include_thinking=True, language="en")
                expected = json.loads(
                    (FIXTURE_ROOT / provider / "normal.events.json.fixture").read_text(encoding="utf-8")
                )
                actual = [
                    {
                        "kind": event.kind.value,
                        "role": event.role.value if event.role else None,
                        "text": event.text,
                        "tool_name": event.tool_name,
                        "tool_input_summary": event.tool_input_summary,
                        "tool_output": event.tool_output,
                        "timestamp": event.timestamp,
                        "turn_number": event.source.turn_number,
                        "record_index": event.source.record_index,
                    }
                    for event in parsed.events
                ]
                self.assertEqual(actual, expected)

    def test_event_parsers_reject_sources_changed_during_parse(self):
        cases = (
            ("claude", parse_claude_session, "ctxzip_core.parser_claude._parse_claude"),
            ("codex", parse_codex_session, "ctxzip_core.parser_codex._parse_codex"),
        )
        for provider, parser, parse_target in cases:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "changing.jsonl"
                source.write_bytes((FIXTURE_ROOT / provider / "normal.jsonl.fixture").read_bytes())
                parser_module = __import__(parse_target.rsplit(".", 1)[0], fromlist=["_parse"])
                original_parse = getattr(parser_module, parse_target.rsplit(".", 1)[1])

                def parse_then_change(*args, **kwargs):
                    parsed = original_parse(*args, **kwargs)
                    with source.open("ab") as file:
                        file.write(b"\n")
                    return parsed

                with mock.patch(parse_target, side_effect=parse_then_change):
                    with self.assertRaisesRegex(RuntimeError, "changed while it was being parsed"):
                        parser(source, include_thinking=False, language="en")

    def test_chatgpt_parser_hashes_the_exact_bytes_it_parses(self):
        fixture = FIXTURE_ROOT / "chatgpt" / "conversations.json.fixture"
        conversation = json.loads(fixture.read_text(encoding="utf-8"))[0]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "conversation.json"
            source.write_text(json.dumps(conversation), encoding="utf-8")
            from ctxzip_core import parser_chatgpt

            original_parse = parser_chatgpt._parse_chatgpt_conversation

            original_bytes = source.read_bytes()

            def parse_then_change(*args, **kwargs):
                parsed = original_parse(*args, **kwargs)
                source.write_bytes(original_bytes + b" ")
                return parsed

            with mock.patch.object(
                parser_chatgpt, "_parse_chatgpt_conversation", side_effect=parse_then_change,
            ):
                parsed = parser_chatgpt.parse_chatgpt_session(source, include_thinking=False)
            self.assertEqual(parsed.events[0].source.source_hash, hashlib.sha256(original_bytes).hexdigest())

    def test_parser_facade_keeps_native_provider_events_available(self):
        parsed = read_session_events(
            "claude-code",
            FIXTURE_ROOT / "claude" / "normal.jsonl.fixture",
            {"dusunceleri_dahil_et": False},
            language="en",
        )
        self.assertTrue(parsed.events)

    def test_antigravity_artifacts_emit_transcript_events_without_inferred_structure(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact_folder = Path(temporary) / "brain"
            artifact_folder.mkdir()
            (artifact_folder / "artifact-a.md").write_text("Sanitized artifact A.", encoding="utf-8")
            (artifact_folder / "artifact-b.md").write_text("Sanitized artifact B.", encoding="utf-8")

            parsed = read_session_events(
                "antigravity", artifact_folder,
                {"dusunceleri_dahil_et": False}, language="en",
            )

        self.assertEqual(len(parsed.events), 2)
        self.assertEqual([event.kind for event in parsed.events], [EventKind.TURN_TRANSCRIPT] * 2)
        self.assertTrue(all(event.role is None for event in parsed.events))
        self.assertTrue(all(event.timestamp is None for event in parsed.events))
        self.assertTrue(all(event.source.source_id == "antigravity" for event in parsed.events))
        self.assertTrue(all(event.source.record_index is None for event in parsed.events))
        self.assertIn("artifact-a.md", parsed.events[0].text)
        self.assertEqual(get_source_capabilities("antigravity").granular_event_kinds, ())

    def test_manual_import_emits_one_unclassified_source_linked_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "manual.md"
            source.write_text("Sanitized manual import.", encoding="utf-8")

            parsed = read_session_events(
                "elle", source,
                {"dusunceleri_dahil_et": False}, language="en",
            )

        self.assertEqual(len(parsed.events), 1)
        event = parsed.events[0]
        self.assertEqual(event.kind, EventKind.TURN_TRANSCRIPT)
        self.assertIsNone(event.role)
        self.assertIsNone(event.timestamp)
        self.assertEqual(event.text, "Sanitized manual import.")
        self.assertEqual(event.source.source_id, "elle")
        self.assertEqual(event.source.source_hash, parsed.events[0].source.source_hash)

    def test_codex_tool_and_opt_in_reasoning_events_are_structured(self):
        records = [
            {"type": "session_meta", "payload": {"git": {"branch": "main"}}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Sanitized example message."}],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "example_tool",
                    "arguments": '{"path":"src/example.py"}',
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "reasoning",
                    "summary": [{"text": "Sanitized reasoning sample."}],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "safe-session.jsonl"
            fixture.write_text(
                "\n".join(json.dumps(row) for row in records), encoding="utf-8"
            )
            parsed = parse_codex_session(fixture, include_thinking=True, language="en")

        self.assertEqual(
            [event.kind for event in parsed.events],
            [
                EventKind.METADATA,
                EventKind.USER_MESSAGE,
                EventKind.TOOL_CALL,
                EventKind.REASONING_SUMMARY,
            ],
        )
        tool_call = parsed.events[2]
        self.assertEqual(tool_call.tool_name, "example_tool")
        self.assertEqual(tool_call.tool_input_summary, "src/example.py")
        self.assertEqual(parsed.events[3].text, "Sanitized reasoning sample.")


if __name__ == "__main__":
    unittest.main()
