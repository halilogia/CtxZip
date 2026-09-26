"""Redact known secret patterns."""

import re

from .i18n import translate

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization)(\"?\s*[:=]\s*\"?)(Bearer\s+)?[^\s\"',}]{8,}"),
]


def redact_secrets(text: str, language: str = "tr") -> str:
    """Remove known key patterns from text sent to models and written to transcripts."""
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda match: match.group(1) + match.group(2) + translate(language, "secret"), text)
        else:
            text = pattern.sub(translate(language, "secret"), text)
    return text


# Backward-compatible Turkish API aliases.
gizli_temizle = redact_secrets
GIZLI_KALIPLAR = SECRET_PATTERNS
