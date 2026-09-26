"""Locale-aware prompt entry points for chapter and arc summaries."""
from .i18n import translate

PROMPT_VERSION = "summary-v1"
PROMPT_SURUMU = "ozet-v1"  # Backward-compatible archive metadata value.


def chapter_prompt(language: str | None) -> str:
    return translate(language, "chapter_system")


def arc_prompt(language: str | None) -> str:
    return translate(language, "arc_system")


# Backward-compatible English constants. New code should use the locale-aware helpers.
BOLUM_SISTEM = chapter_prompt("en")
CILT_SISTEM = arc_prompt("en")
