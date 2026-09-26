"""Declared limits of source adapters and their normalized transcript output."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SourceCapabilities:
    source_format: str
    history_scope: Literal["session_log", "markdown_artifacts", "manual_text", "conversation_export"]
    raw_source_preserved: bool
    normalized_messages: bool
    tool_calls: bool
    granular_event_kinds: tuple[str, ...]
    tool_results: Literal["all", "errors_only", "none"]
    event_timestamps: bool
    file_timestamps: bool
    working_directory: bool
    git_branch: bool
    limitation: str


SOURCE_CAPABILITIES: dict[str, SourceCapabilities] = {
    "claude-code": SourceCapabilities(
        source_format="Claude Code local JSONL",
        history_scope="session_log",
        raw_source_preserved=True,
        normalized_messages=True,
        tool_calls=True,
        granular_event_kinds=("user_message", "assistant_message", "tool_call", "tool_result", "command", "metadata"),
        tool_results="errors_only",
        event_timestamps=True,
        file_timestamps=False,
        working_directory=True,
        git_branch=True,
        limitation="The raw JSONL is retained; transcripts omit sidechain/meta records and ordinary tool-result bodies.",
    ),
    "codex": SourceCapabilities(
        source_format="Codex local JSONL",
        history_scope="session_log",
        raw_source_preserved=True,
        normalized_messages=True,
        tool_calls=True,
        granular_event_kinds=("user_message", "assistant_message", "tool_call", "reasoning_summary", "metadata"),
        tool_results="none",
        event_timestamps=True,
        file_timestamps=False,
        working_directory=True,
        git_branch=True,
        limitation="The raw JSONL is retained; transcripts normalize message text, tool-call summaries, and optional reasoning summaries.",
    ),
    "chatgpt": SourceCapabilities(
        source_format="ChatGPT conversations.json export (mapping/current_node shape)",
        history_scope="conversation_export",
        raw_source_preserved=True,
        normalized_messages=True,
        tool_calls=False,
        granular_event_kinds=("turn_transcript",),
        tool_results="none",
        event_timestamps=True,
        file_timestamps=False,
        working_directory=False,
        git_branch=False,
        limitation="The source export stays unchanged in gelen/; derived per-conversation records parse only the active parent chain and text parts. Events summarize whole turns, omit record_index, and retain the active mapping-node keys in record_ids. Validate against a real sanitized export before relying on schema compatibility.",
    ),
    "antigravity": SourceCapabilities(
        source_format="Antigravity Markdown artifacts",
        history_scope="markdown_artifacts",
        raw_source_preserved=True,
        normalized_messages=False,
        tool_calls=False,
        granular_event_kinds=(),
        tool_results="none",
        event_timestamps=False,
        file_timestamps=True,
        working_directory=False,
        git_branch=False,
        limitation="Only discovered brain/<id> Markdown artifacts are copied; this is not a full chat transcript.",
    ),
    "elle": SourceCapabilities(
        source_format="Manually imported text",
        history_scope="manual_text",
        raw_source_preserved=True,
        normalized_messages=False,
        tool_calls=False,
        granular_event_kinds=(),
        tool_results="none",
        event_timestamps=False,
        file_timestamps=True,
        working_directory=False,
        git_branch=False,
        limitation="The supplied text is one imported turn; role, tool, and session structure are not inferred.",
    ),
}


def get_source_capabilities(source_id: str) -> SourceCapabilities:
    """Return declared capabilities for a parser key, raising KeyError if unknown."""
    return SOURCE_CAPABILITIES[source_id]
