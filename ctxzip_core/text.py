"""Shared deterministic text formatting and fingerprints."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

def estimate_tokens(text: str) -> int:
    # Rough estimate for mixed Turkish/English text (~3.5 characters per token).
    return int(len(text) / 3.5) + 1

def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

def format_timestamp(timestamp: str | float | None) -> str:
    if timestamp is None:
        return ""
    try:
        if isinstance(timestamp, (int, float)):
            parsed_datetime = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        else:
            parsed_datetime = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        return parsed_datetime.astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return str(timestamp)[:16]

SYSTEM_LABEL = re.compile(r"<(system-reminder|local-command-caveat|environment_context|user_instructions)>.*?</\1>", re.S)

def clean_text(value: str) -> str:
    return SYSTEM_LABEL.sub("", value).strip()

def truncate_text(value: str, limit: int) -> str:
    value = " ".join(str(value).split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


# Backward-compatible Turkish API aliases.
token_tahmini = estimate_tokens
metin_hash = text_hash
zaman_str = format_timestamp
temiz_metin = clean_text
kisalt = truncate_text
SISTEM_ETIKETI = SYSTEM_LABEL
