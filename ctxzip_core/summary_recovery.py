"""Conservatively reconcile summary files written before state persistence."""
from pathlib import Path
import re

from .summary_store import read_summary_body


_CHAPTER_NAME = re.compile(r"^B(\d{4})\.md$")
_VOLUME_NAME = re.compile(r"^C(\d{3})\.md$")
_TURN_RANGE = re.compile(r"^T(\d+)-T(\d+)$")
_CHAPTER_RANGE = re.compile(r"^B(\d+)-B(\d+)$")


class SummaryRecoveryError(RuntimeError):
    """An orphan summary cannot be mapped to state without risking data loss."""

    def __init__(self, filename: str):
        super().__init__(filename)
        self.filename = filename


def next_summary_number(records: list[dict]) -> int:
    """Return an unused number after the greatest persisted summary number."""
    return max((record["no"] for record in records), default=0) + 1


def _recover_chapter(path: Path, expected_number: int | None = None) -> dict:
    match = _CHAPTER_NAME.fullmatch(path.name)
    try:
        metadata, _body = read_summary_body(path)
        number = int(match.group(1)) if match else -1
        turns = _TURN_RANGE.fullmatch(metadata.get("turlar", ""))
        first_turn, last_turn = (int(turns.group(1)), int(turns.group(2))) if turns else (0, 0)
        if (
            metadata.get("tur") != "bolum"
            or (expected_number is not None and number != expected_number)
            or int(metadata.get("no", "-1")) != number
            or not metadata.get("kaynak", "").strip()
            or turns is None
            or first_turn < 1
            or last_turn < first_turn
        ):
            raise ValueError("inconsistent Chapter metadata")
    except (OSError, UnicodeError, TypeError, ValueError) as error:
        raise SummaryRecoveryError(path.name) from error
    return {
        "no": number,
        "dosya": path.name,
        "oturum": metadata["kaynak"],
        "tur_baslangic": first_turn,
        "tur_bitis": last_turn,
        "cilt": None,
    }


def _recover_volume(
    path: Path, chapters: list[dict], expected_number: int | None = None,
) -> tuple[dict, tuple[int, ...]]:
    match = _VOLUME_NAME.fullmatch(path.name)
    try:
        metadata, _body = read_summary_body(path)
        number = int(match.group(1)) if match else -1
        chapter_range = _CHAPTER_RANGE.fullmatch(metadata.get("bolumler", ""))
        first_chapter, last_chapter = (
            (int(chapter_range.group(1)), int(chapter_range.group(2)))
            if chapter_range else (0, 0)
        )
        if first_chapter < 1 or last_chapter < first_chapter:
            raise ValueError("invalid Chapter range")
        if last_chapter - first_chapter + 1 > len(chapters):
            raise ValueError("Volume range cannot be covered by current Chapters")
        chapter_numbers = tuple(range(first_chapter, last_chapter + 1))
        by_number = {chapter["no"]: chapter for chapter in chapters}
        if (
            metadata.get("tur") != "cilt"
            or (expected_number is not None and number != expected_number)
            or int(metadata.get("no", "-1")) != number
            or chapter_range is None
            or not chapter_numbers
            or any(chapter_no not in by_number for chapter_no in chapter_numbers)
            or any(by_number[chapter_no]["cilt"] not in (None, number) for chapter_no in chapter_numbers)
        ):
            raise ValueError("inconsistent Volume metadata")
    except (OSError, UnicodeError, TypeError, ValueError) as error:
        raise SummaryRecoveryError(path.name) from error
    record = {"no": number, "dosya": path.name, "bolumler": list(chapter_numbers)}
    return record, chapter_numbers


def reconcile_orphan_summaries(project_dir: Path, state: dict) -> bool:
    """Recover orphan summaries when embedded metadata proves their identity.

    Number gaps are allowed when filename, embedded number, source range, and
    current state agree. Invalid recognized files block processing rather than
    being overwritten. Recovered records are sorted by their stable numbers.
    """
    changed = False
    chapter_dir = Path(project_dir) / "bolumler"
    chapters = state["bolumler"]
    known_chapter_files = {chapter["dosya"] for chapter in chapters}
    known_chapter_numbers = {chapter["no"] for chapter in chapters}
    for orphan_path in sorted(chapter_dir.glob("B[0-9][0-9][0-9][0-9].md")):
        if orphan_path.name in known_chapter_files:
            continue
        chapter = _recover_chapter(orphan_path)
        if chapter["no"] in known_chapter_numbers:
            raise SummaryRecoveryError(orphan_path.name)
        for existing in chapters:
            if (
                existing["oturum"].casefold() == chapter["oturum"].casefold()
                and existing["tur_baslangic"] <= chapter["tur_bitis"]
                and chapter["tur_baslangic"] <= existing["tur_bitis"]
            ):
                raise SummaryRecoveryError(orphan_path.name)
        chapters.append(chapter)
        known_chapter_files.add(orphan_path.name)
        known_chapter_numbers.add(chapter["no"])
        changed = True
    if changed:
        chapters.sort(key=lambda item: item["no"])

    volume_dir = Path(project_dir) / "ciltler"
    volumes = state["ciltler"]
    known_volume_files = {volume["dosya"] for volume in volumes}
    by_chapter_number = {chapter["no"]: chapter for chapter in chapters}
    known_volume_numbers = {volume["no"] for volume in volumes}
    for orphan_path in sorted(volume_dir.glob("C[0-9][0-9][0-9].md")):
        if orphan_path.name in known_volume_files:
            continue
        volume, chapter_numbers = _recover_volume(orphan_path, chapters)
        if volume["no"] in known_volume_numbers:
            raise SummaryRecoveryError(orphan_path.name)
        volumes.append(volume)
        known_volume_files.add(orphan_path.name)
        known_volume_numbers.add(volume["no"])
        for chapter_number in chapter_numbers:
            by_chapter_number[chapter_number]["cilt"] = volume["no"]
        changed = True
    if changed:
        volumes.sort(key=lambda item: item["no"])
    return changed
