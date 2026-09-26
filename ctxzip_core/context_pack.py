"""Versioned machine-readable metadata for generated Markdown context packs."""
from __future__ import annotations

import json
from typing import Any


FORMAT_ID = "ctxzip-context-pack"
SCHEMA_VERSION = 1
_OPEN_MARKER = "<!-- ctxzip-context-pack\n"
_CLOSE_MARKER = "\n-->"


def _validate_metadata(metadata: Any) -> dict[str, Any]:
    required = {"project", "generated_at", "language", "budget", "estimated_tokens", "git", "sources"}
    if not isinstance(metadata, dict):
        raise ValueError("Context-pack metadata must be a JSON object")
    if metadata.get("format") != FORMAT_ID or type(metadata.get("schema_version")) is not int:
        raise ValueError("Unknown context-pack format")
    if metadata["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported context-pack schema version")
    if not required.issubset(metadata):
        raise ValueError("Context-pack metadata is missing required fields")
    if (
        not isinstance(metadata["project"], str)
        or not isinstance(metadata["generated_at"], str)
        or not isinstance(metadata["language"], str)
        or metadata["language"] not in {"en", "tr"}
    ):
        raise ValueError("Context-pack metadata has invalid identity fields")
    budget = metadata["budget"]
    if (
        not isinstance(budget, dict)
        or type(budget.get("limit")) is not int
        or budget["limit"] < 0
        or not isinstance(budget.get("profile"), str)
        or budget.get("profile") not in {"priority", "balanced"}
        or type(budget.get("recent_raw_allocation")) is not int
        or type(budget.get("recent_raw_used")) is not int
        or type(budget.get("recent_raw_reserved")) is not int
        or type(budget.get("safety_reserved")) is not int
        or budget["recent_raw_reserved"] < 0
        or budget["recent_raw_allocation"] < 0
        or budget["recent_raw_used"] < 0
        or budget["recent_raw_used"] + budget["recent_raw_reserved"] != budget["recent_raw_allocation"]
        or budget["safety_reserved"] < 0
        or budget["recent_raw_reserved"] + budget["safety_reserved"] > budget["limit"]
    ):
        raise ValueError("Context-pack metadata has an invalid budget")
    if (
        type(metadata["estimated_tokens"]) is not int
        or metadata["estimated_tokens"] < 0
        or metadata["estimated_tokens"] > budget["limit"]
    ):
        raise ValueError("Context-pack metadata has an invalid token estimate")
    git_state = metadata["git"]
    if git_state is not None and (
        not isinstance(git_state, dict)
        or not isinstance(git_state.get("dirty"), bool)
        or any(git_state.get(key) is not None and not isinstance(git_state.get(key), str)
               for key in ("branch", "head_sha", "worktree_fingerprint"))
    ):
        raise ValueError("Context-pack metadata has an invalid Git snapshot")
    if not isinstance(metadata["sources"], list) or not all(
        isinstance(source, str) for source in metadata["sources"]
    ):
        raise ValueError("Context-pack metadata has invalid source references")
    return metadata


def render_metadata_block(metadata: dict[str, Any]) -> str:
    """Serialize a validated context-pack manifest as an HTML comment."""
    _validate_metadata(metadata)
    payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True).replace("-->", "--\\u003e")
    return _OPEN_MARKER + payload + _CLOSE_MARKER


def parse_metadata_block(content: str) -> dict[str, Any]:
    """Read the leading manifest and reject absent, malformed, or future schemas."""
    if not content.startswith(_OPEN_MARKER):
        raise ValueError("Context pack has no leading metadata block")
    closing = content.find(_CLOSE_MARKER, len(_OPEN_MARKER))
    if closing < 0:
        raise ValueError("Context-pack metadata block is not closed")
    try:
        metadata = json.loads(content[len(_OPEN_MARKER):closing])
    except json.JSONDecodeError as error:
        raise ValueError("Context-pack metadata is not valid JSON") from error
    return _validate_metadata(metadata)
