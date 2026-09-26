"""Summary generation and persistent chapter/arc state transitions."""
from pathlib import Path
import time

from .chunking import group_chapters, truncate_turn
from .i18n import summary_prompt_version, translate
from .llm import call_llm
from .parsers import PARSER_VERSIONS, read_session
from .privacy import redact_secrets
from .prompts import arc_prompt, chapter_prompt
from .sessions import list_sessions, short_id
from .summary_store import (
    PLACEHOLDER, load_summary_state, read_summary_body, save_summary_state,
    split_summary_metadata, write_summary_file,
)
from .storage import atomic_write_text
from .text import format_timestamp, text_hash
from .source_freshness import chapter_source_hash
from .summary_recovery import (
    SummaryRecoveryError, next_summary_number, reconcile_orphan_summaries,
)


def _write_prompt_if_missing(prompt_path: Path, content: str) -> None:
    """Create a manual prompt once, preserving edits across interrupted retries."""
    if not prompt_path.exists():
        atomic_write_text(prompt_path, content)


def fill_pending_summaries(settings: dict, project_dir: Path) -> int:
    """Fill unfinished manual summary prompts when automatic mode is enabled."""
    completed_count = 0
    language = settings.get("language", "tr")
    for folder_name, system_prompt in (("bolumler", chapter_prompt(language)), ("ciltler", arc_prompt(language))):
        summary_dir = project_dir / folder_name
        for summary_path in sorted(summary_dir.glob("*.md")) if summary_dir.exists() else []:
            if summary_path.name.endswith(".istem.md") or PLACEHOLDER not in summary_path.read_text(encoding="utf-8"):
                continue
            prompt_path = summary_path.with_name(summary_path.stem + ".istem.md")
            if not prompt_path.exists():
                continue
            prompt_text = prompt_path.read_text(encoding="utf-8")
            markers = ("# USER\n\n", "# KULLANICI\n\n")
            marker_positions = [(prompt_text.find(marker), marker) for marker in markers]
            position, marker = max(marker_positions, key=lambda item: item[0])
            user_prompt = prompt_text[position + len(marker):] if position >= 0 else prompt_text
            try:
                body = call_llm(settings, system_prompt, user_prompt)
            except RuntimeError as error:
                print(translate(language, "pending_failed", file=summary_path.name, error=error))
                return completed_count
            metadata, content = split_summary_metadata(summary_path.read_text(encoding="utf-8"))
            title = content.split("\n", 1)[0].lstrip("# ").strip()
            metadata.pop("govde_hash", None)
            write_summary_file(summary_path, dict(metadata, model=settings["llm"]["model"]), title, body)
            completed_count += 1
            print(translate(language, "pending_completed", project=project_dir.name, file=summary_path.name))
    return completed_count


def fold_volume(settings: dict, project_dir: Path, state: dict, manual: bool) -> int:
    language = settings.get("language", "tr")
    volume_dir = project_dir / "ciltler"
    volume_dir.mkdir(exist_ok=True)
    created_count = 0
    while True:
        unassigned = [chapter for chapter in state["bolumler"] if chapter["cilt"] is None]
        group_size = settings["cilt_bolum_sayisi"]
        chapter_group = []
        for start in range(max(0, len(unassigned) - group_size + 1)):
            possible_group = unassigned[start:start + group_size]
            if all(
                later["no"] == earlier["no"] + 1
                for earlier, later in zip(possible_group, possible_group[1:])
            ):
                chapter_group = possible_group
                break
        if len(chapter_group) < settings["cilt_bolum_sayisi"]:
            return created_count
        pending = [chapter for chapter in chapter_group
                   if PLACEHOLDER in (project_dir / "bolumler" / chapter["dosya"]).read_text(encoding="utf-8")]
        if pending:
            print(translate(language, "arc_waiting", project=project_dir.name, count=len(pending)))
            return created_count

        volume_number = next_summary_number(state["ciltler"])
        first_number, last_number = chapter_group[0]["no"], chapter_group[-1]["no"]
        section_label = translate(language, "chapter_label")
        chapter_sections = []
        for chapter in chapter_group:
            _metadata, body = read_summary_body(project_dir / "bolumler" / chapter["dosya"])
            chapter_sections.append(
                f"# {section_label} {chapter['no']} ({chapter['oturum']} T{chapter['tur_baslangic']}–T{chapter['tur_bitis']})\n{body}"
            )
        user_prompt = translate(language, "arc_input", project=project_dir.name, first=first_number,
                                last=last_number, chapters="\n\n".join(chapter_sections))

        summary_path = volume_dir / f"C{volume_number:03d}.md"
        metadata = {"tur": "cilt", "no": volume_number, "bolumler": f"B{first_number}-B{last_number}",
                    "prompt": summary_prompt_version(language)}
        volume_label = translate(language, "arc_label")
        title = f"{volume_label} {volume_number} — {section_label} {first_number}–{last_number}"
        system_prompt = arc_prompt(language)
        if manual:
            prompt_path = volume_dir / f"C{volume_number:03d}.istem.md"
            _write_prompt_if_missing(
                prompt_path,
                f"# {translate(language, 'system_heading')}\n\n{system_prompt}\n\n"
                f"# {translate(language, 'user_heading')}\n\n{user_prompt}\n")
            paste_instruction = translate(language, "arc_manual_instruction")
            write_summary_file(summary_path, dict(metadata, model="elle"), title,
                               f"{PLACEHOLDER}\n`{prompt_path.name}` {paste_instruction}.")
        else:
            try:
                body = call_llm(settings, system_prompt, user_prompt)
            except RuntimeError as error:
                print(translate(language, "arc_error", project=project_dir.name, number=volume_number, error=error))
                return created_count
            write_summary_file(summary_path, dict(metadata, model=settings["llm"]["model"]), title, body)

        for chapter in chapter_group:
            chapter["cilt"] = volume_number
        state["ciltler"].append({"no": volume_number, "dosya": summary_path.name,
                                 "bolumler": [chapter["no"] for chapter in chapter_group]})
        created_count += 1
        print(translate(language, "arc_written", project=project_dir.name, number=volume_number,
                        first=first_number, last=last_number))


def summarize_project(settings: dict, project_dir: Path, manual: bool) -> bool | None:
    """Process a project while persisting completed summaries after each chapter."""
    language = settings.get("language", "tr")
    system_prompt = chapter_prompt(language)
    state = load_summary_state(project_dir)
    try:
        if reconcile_orphan_summaries(project_dir, state):
            save_summary_state(project_dir, state)
    except SummaryRecoveryError as error:
        print(translate(language, "summary_recovery_blocked", file=error.filename))
        return False
    chapter_dir = project_dir / "bolumler"
    chapter_dir.mkdir(exist_ok=True)
    if not manual and settings["llm"].get("model"):
        fill_pending_summaries(settings, project_dir)

    processed_through = {}
    for chapter in state["bolumler"]:
        session_key = chapter["oturum"]
        processed_through[session_key] = max(processed_through.get(session_key, 0), chapter["tur_bitis"])

    sessions = []
    for tool_name, session_id, source_path in list_sessions(project_dir):
        turns, session_metadata = read_session(tool_name, source_path, settings, language)
        if turns:
            sessions.append((str(session_metadata["baslangic"] or ""), tool_name, session_id, source_path, turns))
    sessions.sort(key=lambda item: format_timestamp(item[0]))

    created_count = 0
    for _start_time, tool_name, session_id, source_path, turns in sessions:
        session_key = f"{tool_name}/{session_id}"
        is_closed = (time.time() - source_path.stat().st_mtime) > settings["aktif_oturum_dk"] * 60
        for chunk, is_full in group_chapters(turns, processed_through.get(session_key, 0), settings["bolum_token"]):
            if not is_full and not is_closed:
                message = translate(language, "active_session_deferred", project=project_dir.name,
                                    session=session_key, count=len(chunk))
                print(f"[{translate(language, 'summary_label')}] {message}")
                continue
            chapter_number = next_summary_number(state["bolumler"])
            first_turn, last_turn = chunk[0].number, chunk[-1].number
            source_hash = chapter_source_hash(
                chunk, first_turn, last_turn, settings["bolum_token"], language,
            )
            source_text = "\n\n".join(
                f"## [T{turn.number}] {turn.timestamp}\n{truncate_turn(turn.text(), settings['bolum_token'], language)}"
                for turn in chunk
            )
            source_text = redact_secrets(source_text, language)
            user_prompt = translate(language, "chapter_input", project=project_dir.name, tool=tool_name,
                                    session=short_id(session_id), first=first_turn, last=last_turn,
                                    transcript=source_text)

            summary_path = chapter_dir / f"B{chapter_number:04d}.md"
            metadata = {"tur": "bolum", "no": chapter_number, "kaynak": session_key,
                        "turlar": f"T{first_turn}-T{last_turn}", "tarih": chunk[0].timestamp,
                        "kaynak_hash": source_hash or text_hash(source_text), "source_language": language,
                        "parser_version": PARSER_VERSIONS.get(tool_name, ""),
                        "prompt": summary_prompt_version(language)}
            chapter_label = translate(language, "chapter_label")
            title = (f"{chapter_label} {chapter_number} — {chunk[0].timestamp[:10]} · {tool_name} "
                     f"{short_id(session_id)} · T{first_turn}–T{last_turn}")
            if manual:
                prompt_path = chapter_dir / f"B{chapter_number:04d}.istem.md"
                _write_prompt_if_missing(
                    prompt_path,
                    f"# {translate(language, 'system_heading')}\n\n{system_prompt}\n\n"
                    f"# {translate(language, 'user_heading')}\n\n{user_prompt}\n")
                instruction = translate(language, "chapter_manual_instruction", file=prompt_path.name)
                write_summary_file(summary_path, dict(metadata, model="elle"), title, f"{PLACEHOLDER}\n{instruction}")
            else:
                try:
                    body = call_llm(settings, system_prompt, user_prompt)
                except RuntimeError as error:
                    print(translate(language, "chapter_error", project=project_dir.name, number=chapter_number, error=error))
                    save_summary_state(project_dir, state)
                    return False
                write_summary_file(summary_path, dict(metadata, model=settings["llm"]["model"]), title, body)

            state["bolumler"].append({"no": chapter_number, "dosya": summary_path.name, "oturum": session_key,
                                      "tur_baslangic": first_turn, "tur_bitis": last_turn, "cilt": None})
            save_summary_state(project_dir, state)
            created_count += 1
            print(translate(language, "chapter_written", project=project_dir.name, number=chapter_number,
                            session=session_key, first=first_turn, last=last_turn))

    created_count += fold_volume(settings, project_dir, state, manual)
    save_summary_state(project_dir, state)
    if not created_count:
        print(translate(language, "no_new_summaries", project=project_dir.name))


# Backward-compatible Turkish API alias.
proje_ozetle = summarize_project
