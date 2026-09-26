"""Derive source-turn coverage for summary candidates from archive state."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SourceRange:
    session_id: str
    first_turn: int
    last_turn: int


def _chapter_range(record: dict) -> SourceRange | None:
    session_id = record.get("oturum")
    first_turn = record.get("tur_baslangic")
    last_turn = record.get("tur_bitis")
    if (
        not isinstance(session_id, str)
        or not session_id.strip()
        or not isinstance(first_turn, int)
        or isinstance(first_turn, bool)
        or not isinstance(last_turn, int)
        or isinstance(last_turn, bool)
        or first_turn < 1
        or last_turn < first_turn
    ):
        return None
    return SourceRange(session_id, first_turn, last_turn)


def _metadata_int(metadata: dict, key: str) -> int | None:
    try:
        return int(metadata[key])
    except (KeyError, TypeError, ValueError):
        return None


def source_ranges_for_summary(
    kind: str, filename: str, state: dict, metadata: dict,
) -> tuple[SourceRange, ...]:
    """Return the source-turn ranges a Chapter or Volume claims to summarize.

    State and embedded file metadata must agree. Invalid, incomplete, or
    contradictory legacy records yield no coverage, so retrieval retains the
    candidate instead of making an unsupported exclusion.
    """
    if not isinstance(metadata, dict) or not isinstance(state, dict):
        return ()
    chapters = state.get("bolumler", [])
    if not isinstance(chapters, list):
        return ()
    if kind == "bolumler":
        filename_match = re.fullmatch(r"B(\d{4})\.md", filename)
        matches = [
            chapter for chapter in chapters
            if isinstance(chapter, dict) and chapter.get("dosya") == filename
        ]
        if len(matches) != 1 or filename_match is None:
            return ()
        record = matches[0]
        source_range = _chapter_range(record)
        turn_text = metadata.get("turlar", "")
        metadata_range = (
            re.fullmatch(r"T(\d+)-T(\d+)", turn_text)
            if isinstance(turn_text, str) else None
        )
        if (
            source_range is None
            or metadata.get("tur") != "bolum"
            or _metadata_int(metadata, "no") != int(filename_match.group(1))
            or metadata.get("kaynak") != source_range.session_id
            or metadata_range is None
            or (int(metadata_range.group(1)), int(metadata_range.group(2)))
            != (source_range.first_turn, source_range.last_turn)
        ):
            return ()
        return (source_range,)
    if kind != "ciltler":
        return ()

    volumes = state.get("ciltler", [])
    if not isinstance(volumes, list):
        return ()
    filename_match = re.fullmatch(r"C(\d{3})\.md", filename)
    matches = [
        item for item in volumes
        if isinstance(item, dict) and item.get("dosya") == filename
    ]
    if len(matches) != 1 or filename_match is None:
        return ()
    volume = matches[0]
    chapter_numbers = volume.get("bolumler")
    if (
        not isinstance(chapter_numbers, list)
        or not chapter_numbers
        or any(not isinstance(number, int) or isinstance(number, bool) for number in chapter_numbers)
    ):
        return ()
    chapter_text = metadata.get("bolumler", "")
    metadata_range = (
        re.fullmatch(r"B(\d+)-B(\d+)", chapter_text)
        if isinstance(chapter_text, str) else None
    )
    volume_number = int(filename_match.group(1))
    if (
        metadata.get("tur") != "cilt"
        or _metadata_int(metadata, "no") != volume_number
        or metadata_range is None
        or (int(metadata_range.group(1)), int(metadata_range.group(2)))
        != (chapter_numbers[0], chapter_numbers[-1])
        or chapter_numbers != list(range(chapter_numbers[0], chapter_numbers[-1] + 1))
    ):
        return ()
    chapter_by_number = {
        chapter.get("no"): chapter for chapter in chapters
        if isinstance(chapter, dict) and isinstance(chapter.get("no"), int)
    }
    if len(chapter_by_number) != len([chapter for chapter in chapters if isinstance(chapter, dict)]):
        return ()
    ranges = []
    for number in chapter_numbers:
        if not isinstance(number, int) or isinstance(number, bool):
            return ()
        chapter = chapter_by_number.get(number)
        source_range = _chapter_range(chapter) if chapter is not None else None
        if source_range is None:
            return ()
        ranges.append(source_range)
    return tuple(dict.fromkeys(ranges))
