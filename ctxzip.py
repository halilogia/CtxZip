#!/usr/bin/env python3
"""Archive coding-agent sessions, generate hierarchical summaries, and build context packs.

The CLI owns command flow; reusable parsing, privacy, localization, and summary logic live
in ctxzip_core. Turkish archive names and persisted field names remain stable for compatibility.
Requires only the Python standard library. Run ``python ctxzip.py --help`` for usage.
License: GPL-3.0 (see LICENSE).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from ctxzip_core.text import (
    estimate_tokens, text_hash, format_timestamp, SISTEM_ETIKETI as SYSTEM_LABEL, clean_text, truncate_text,
)
from ctxzip_core.parsers import (
    iter_jsonl_rows, claude_working_directory, codex_working_directory, is_codex_file, Turn, tool_summary, parse_claude_turns, parse_codex_turns, parse_antigravity_turns, parse_manual_turns, PARSERS, read_session,
)
from ctxzip_core.sessions import (
    short_id, list_sessions,
)
from ctxzip_core.summary_store import (
    BURAYA as SUMMARY_PLACEHOLDER, load_summary_state, save_summary_state, split_summary_metadata, write_summary_file, read_summary_body, is_manually_edited,
)
from ctxzip_core.chunking import (
    truncate_turn, group_chapters,
)
from ctxzip_core.prompts import (
    PROMPT_SURUMU as PROMPT_VERSION, BOLUM_SISTEM as CHAPTER_SYSTEM, CILT_SISTEM as VOLUME_SYSTEM,
)
from ctxzip_core.summarizing import (
    fill_pending_summaries, fold_volume, summarize_project,
)
from ctxzip_core.git_safety import ensure_git_safe_copy
from ctxzip_core.llm import call_llm
from ctxzip_core.privacy import redact_secrets
from ctxzip_core.i18n import LocalizationError, preferred_language, translate, validate_catalogs

VERSION = "0.1.0"

DEFAULT_SETTINGS = {
    "arsiv_klasoru": "~/CtxZip-Arsiv",
    "kaynaklar": {
        "claude_code": ["~/.claude/projects"],
        "codex": ["$CODEX_HOME/sessions", "~/.codex/sessions"],
        "antigravity_brain": ["~/.gemini/antigravity/brain"],
    },
    # Project mapping: working directory name -> archive project name
    "proje_takma_adlari": {},
    # Sessions from these directory names are not archived (for example, the home directory).
    "haric_projeler": [],
    "llm": {
        "base_url": "http://127.0.0.1:20128/v1",
        "model": "",
        "api_key_env": "CTXZIP_API_KEY",
        "timeout_sn": 300,
    },
    "bolum_token": 25000,     # Approximate transcript size per chapter.
    "cilt_bolum_sayisi": 8,   # Number of chapters folded into a volume.
    "aktif_oturum_dk": 120,   # A session unchanged for this many minutes is considered closed.
    "dusunceleri_dahil_et": False,
    "language": "tr",
}

# ---------------------------------------------------------------- helpers

def expand_path(path_item: str) -> Path | None:
    if "$CODEX_HOME" in path_item:
        home = os.environ.get("CODEX_HOME")
        if not home:
            return None
        path_item = path_item.replace("$CODEX_HOME", home)
    return Path(os.path.expandvars(os.path.expanduser(path_item)))


def load_settings(path: Path) -> dict:
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    if path.exists():
        user_settings = json.loads(path.read_text(encoding="utf-8"))
        for source_root, value in user_settings.items():
            if isinstance(value, dict) and isinstance(settings.get(source_root), dict):
                settings[source_root].update(value)
            else:
                settings[source_root] = value
    return settings


def default_settings_path(application_dir: Path) -> Path:
    """Prefer the English settings name and continue loading the legacy file."""
    settings_path = application_dir / "ctxzip.settings.json"
    legacy_settings_path = application_dir / "ctxzip_ayar.json"
    if not settings_path.exists() and legacy_settings_path.exists():
        return legacy_settings_path
    return settings_path


def file_hash(path_item: Path) -> str:
    file_digest = hashlib.sha256()
    with path_item.open("rb") as source_file:
        for data_block in iter(lambda: source_file.read(1 << 20), b""):
            file_digest.update(data_block)
    return file_digest.hexdigest()


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w.\-]+", "-", value, flags=re.UNICODE).strip("-")
    return value or "adsiz"


# ---------------------------------------------------------------- source discovery


def project_name(working_directory: str | None, settings: dict) -> str | None:
    if not working_directory:
        return None
    name = re.split(r"[\\/]", working_directory.rstrip("\\/"))[-1] or working_directory
    if name in settings["haric_projeler"]:
        return None
    return safe_name(settings["proje_takma_adlari"].get(name, name))


def discover_sources(settings: dict):
    """Yield (tool, project, session_id, source_path) tuples."""
    for archive_root in settings["kaynaklar"].get("claude_code", []):
        source_root = expand_path(archive_root)
        if not source_root or not source_root.exists():
            continue
        for path_item in sorted(source_root.glob("*/*.jsonl")):
            project = project_name(claude_working_directory(path_item), settings)
            if project:
                yield "claude-code", project, path_item.stem, path_item
    for archive_root in settings["kaynaklar"].get("codex", []):
        source_root = expand_path(archive_root)
        if not source_root or not source_root.exists():
            continue
        for path_item in sorted(source_root.rglob("*.jsonl")):
            project = project_name(codex_working_directory(path_item), settings)
            if project:
                yield "codex", project, path_item.stem, path_item
    for archive_root in settings["kaynaklar"].get("antigravity_brain", []):
        source_root = expand_path(archive_root)
        if not source_root or not source_root.exists():
            continue
        # Antigravity "brain" directory: per-conversation Markdown artifacts (task, plan, walkthrough).
        # Project metadata is not guaranteed in files, so use "antigravity"; a configured alias can remap it.
        for entry in sorted(x for x in source_root.iterdir() if x.is_dir()):
            if any(entry.glob("*.md")):
                yield "antigravity", safe_name(settings["proje_takma_adlari"].get(entry.name, "antigravity")), entry.name, entry

# ---------------------------------------------------------------- 1) collect

def collect(settings: dict, archive_root: Path) -> None:
    new_count = updated_count = unchanged_count = 0
    for tool, project, session_id, source_path in discover_sources(settings):
        target_dir = archive_root / project / "raw" / tool
        target_dir.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            target = target_dir / session_id
            changed = False
            for markdown_file in source_path.rglob("*.md"):
                copied_path = target / markdown_file.relative_to(source_path)
                if not copied_path.exists() or copied_path.read_bytes() != markdown_file.read_bytes():
                    copied_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(markdown_file, copied_path)
                    changed = True
            is_new = not (target_dir / (session_id + ".kaynak")).exists()
            (target_dir / (session_id + ".kaynak")).write_text(str(source_path), encoding="utf-8")
        else:
            target = target_dir / (session_id + ".jsonl")
            is_new = not target.exists()
            changed = is_new or target.stat().st_size != source_path.stat().st_size or file_hash(target) != file_hash(source_path)
            if changed:
                if not is_new and target.stat().st_size > source_path.stat().st_size:
                    # If the source shrank because the tool rewrote it, preserve the previous copy before replacement.
                    shutil.copy2(target, target.with_suffix(f".{int(time.time())}.onceki.jsonl"))
                shutil.copy2(source_path, target)
        if is_new:
            new_count += 1
        elif changed:
            updated_count += 1
        else:
            unchanged_count += 1
    print(translate(settings.get("language"), "collect_result", new=new_count, updated=updated_count, same=unchanged_count, path=archive_root))

# ---------------------------------------------------------------- 2) transcripts


def write_transcripts(settings: dict, archive_root: Path, project: str | None) -> None:
    for project_dir in project_directories(archive_root, project, settings.get("language", "tr")):
        target = project_dir / "dokum"
        target.mkdir(exist_ok=True)
        transcript_count = 0
        for tool, session_id, path in list_sessions(project_dir):
            turns, session_info = read_session(tool, path, settings, settings.get("language", "tr"))
            if not turns:
                continue
            start_time = format_timestamp(session_info["baslangic"])
            language = settings.get("language", "tr")
            start_label = translate(language, "transcript_start")
            end_label = translate(language, "transcript_end")
            branch_label = translate(language, "transcript_branch")
            turn_label = translate(language, "transcript_turns")
            raw_label = translate(language, "transcript_raw_source")
            session_label = translate(language, "transcript_session")
            date_label = start_time[:10] or translate(language, "transcript_undated")
            name = f"{date_label}_{tool}_{short_id(session_id)}.md"
            transcript_lines = [f"# {project_dir.name} — {tool} {session_label} {short_id(session_id)}",
                     f"{start_label}: {start_time} · {end_label}: {format_timestamp(session_info['bitis'])} · {branch_label}: {session_info['dal'] or '-'} · {turn_label}: {len(turns)}",
                     f"{raw_label}: `{path.relative_to(project_dir)}`", ""]
            for turn in turns:
                transcript_lines.append(f"## [T{turn.number}] {turn.timestamp}\n\n{turn.text()}\n")
            (target / name).write_text(redact_secrets("\n".join(transcript_lines), settings.get("language", "tr")), encoding="utf-8")
            transcript_count += 1
        print(translate(settings.get("language"), "transcript_result", project=project_dir.name, count=transcript_count, path=target))


def project_directories(archive_root: Path, project: str | None, language: str = "tr"):
    if project:
        project_dir = archive_root / safe_name(project)
        if not project_dir.exists():
            sys.exit(translate(language, "project_missing", path=project_dir))
        return [project_dir]
    return sorted(x for x in archive_root.iterdir() if x.is_dir() and not x.name.startswith(".")) if archive_root.exists() else []

# ---------------------------------------------------------------- 3) summarize


def summarize(settings: dict, archive_root: Path, project: str | None, manual: bool) -> None:
    for project_dir in project_directories(archive_root, project, settings.get("language", "tr")):
        if summarize_project(settings, project_dir, manual) is False:
            return


# ---------------------------------------------------------------- 4) context pack

def build_context(settings: dict, archive_root: Path, project: str, budget: int, copy_target: str | None) -> None:
    project_dir = project_directories(archive_root, project, settings.get("language", "tr"))[0]
    summary_state = load_summary_state(project_dir)
    selected_summaries: list[tuple[str, str]] = []
    remaining_tokens = budget
    # Newest first: chapters not folded into volumes, followed by volumes.
    candidates = [("bolumler", chapter_record["dosya"]) for chapter_record in reversed(summary_state["bolumler"]) if chapter_record["cilt"] is None]
    candidates += [("ciltler", c["dosya"]) for c in reversed(summary_state["ciltler"])]
    omitted_count = 0
    for folder, name in candidates:
        path = project_dir / folder / name
        _summary_metadata, body = read_summary_body(path)
        if SUMMARY_PLACEHOLDER in body:
            continue
        token_count = estimate_tokens(body)
        if token_count > remaining_tokens:
            omitted_count += 1
            continue
        title = path.read_text(encoding="utf-8").split("\n# ", 1)[-1].split("\n", 1)[0]
        selected_summaries.append((title, body))
        remaining_tokens -= token_count
    selected_summaries.reverse()  # Restore chronological order.
    language = settings.get("language", "tr")
    output_lines = [f"# {project_dir.name} — {translate(language, 'context_title')}",
             f"_{translate(language, 'generated')}: {datetime.now().strftime('%Y-%m-%d %H:%M')} · {translate(language, 'summary_count', count=len(selected_summaries))} · ~{translate(language, 'token_count', count=budget - remaining_tokens)}"
             + (f" · {omitted_count} {translate(language, 'budget_omitted')}" if omitted_count else "") + "_", "",
             "> " + translate(language, "context_notice"), ""]
    for title, body in selected_summaries:
        output_lines.append(f"---\n\n# {title}\n\n{body}\n")
    target = project_dir / "BAGLAM.md"
    target.write_text("\n".join(output_lines), encoding="utf-8")
    print(translate(language, "context_result", path=target, count=len(selected_summaries), tokens=budget - remaining_tokens))
    if copy_target:
        source_root = Path(os.path.expanduser(copy_target))
        source_root = source_root / "BAGLAM.md" if source_root.is_dir() else source_root
        ensure_git_safe_copy(source_root, language)
        shutil.copy2(target, source_root)
        print(f"[{translate(language, 'copied')}] -> {source_root}")

# ---------------------------------------------------------------- status

def show_status(archive_root: Path, language: str = "tr") -> None:
    if not archive_root.exists():
        print(translate(language, "archive_missing", path=archive_root))
        return
    print(f"{translate(language, 'project'):32} {translate(language, 'sessions'):>8} {translate(language, 'chapters'):>8} {translate(language, 'arcs'):>6} {translate(language, 'pending'):>10} {translate(language, 'edited'):>10}")
    for project_dir in project_directories(archive_root, None, language):
        session_count = sum(1 for _ in list_sessions(project_dir))
        summary_state = load_summary_state(project_dir)
        pending_count = sum(1 for chapter in summary_state["bolumler"]
                       if (project_dir / "bolumler" / chapter["dosya"]).exists() and SUMMARY_PLACEHOLDER in (project_dir / "bolumler" / chapter["dosya"]).read_text(encoding="utf-8"))
        edited_count = sum(1 for source_root in ("bolumler", "ciltler") for summary_file in (project_dir / source_root).glob("*.md")
                         if (project_dir / source_root).exists() and not summary_file.name.endswith(".istem.md") and is_manually_edited(summary_file))
        print(f"{project_dir.name[:32]:32} {session_count:>8} {len(summary_state['bolumler']):>8} {len(summary_state['ciltler']):>6} {pending_count:>10} {edited_count:>10}")


def main() -> None:
    application_dir = Path(__file__).parent
    settings_path = default_settings_path(application_dir)
    settings_option = next((option for option in ("--ayar", "--settings") if option in sys.argv), None)
    if settings_option and sys.argv.index(settings_option) + 1 < len(sys.argv):
        settings_path = Path(sys.argv[sys.argv.index(settings_option) + 1])
    try:
        configured_language = load_settings(settings_path).get("language", "tr")
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Invalid settings file: {error}") from None
    explicit_language = None
    if "--language" in sys.argv and sys.argv.index("--language") + 1 < len(sys.argv):
        explicit_language = sys.argv[sys.argv.index("--language") + 1]
    try:
        language = preferred_language(configured_language, explicit_language)
        validate_catalogs()
    except LocalizationError as error:
        raise SystemExit(str(error)) from None
    translate_message = lambda key, **values: translate(language, key, **values)
    argument_parser = argparse.ArgumentParser(description=translate_message("app_description"))
    argument_parser.add_argument("--ayar", "--settings", dest="settings", default=str(settings_path), help=translate_message("settings_help"))
    argument_parser.add_argument("--language", choices=("tr", "en"), help=translate_message("language_help"))
    subparsers = argument_parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("topla", aliases=["collect"], help=translate_message("collect_help"))
    entry = subparsers.add_parser("dokum", aliases=["transcript"], help=translate_message("transcript_help"))
    entry.add_argument("--proje", "--project", dest="project")
    summary_parser = subparsers.add_parser("ozetle", aliases=["summarize"], help=translate_message("summarize_help"))
    summary_parser.add_argument("--proje", "--project", dest="project")
    summary_parser.add_argument("--elle", "--manual", dest="manual", action="store_true", help=translate_message("manual_help"))
    summary_parser.add_argument("--onayli-gonder", "--approved-send", dest="onayli_gonder", action="store_true",
                   help=translate_message("approved_help"))
    context_parser = subparsers.add_parser("baglam", aliases=["context"], help=translate_message("context_help"))
    context_parser.add_argument("project")
    context_parser.add_argument("--token", "--tokens", dest="tokens", type=int, default=12000)
    context_parser.add_argument("--kopyala", "--copy", dest="copy_target", help=translate_message("copy_help"))
    all_command_parser = subparsers.add_parser("hepsi", aliases=["all"], help=translate_message("all_help"))
    all_command_parser.add_argument("--elle", "--manual", dest="manual", action="store_true", help=translate_message("manual_help"))
    all_command_parser.add_argument("--onayli-gonder", "--approved-send", dest="onayli_gonder", action="store_true",
                   help=translate_message("approved_help"))
    subparsers.add_parser("durum", aliases=["status"], help=translate_message("status_help"))
    arguments = argument_parser.parse_args()

    settings = load_settings(Path(arguments.settings))
    settings["language"] = preferred_language(settings.get("language"), arguments.language)
    settings["_onayli_gonder"] = getattr(arguments, "onayli_gonder", False)
    archive_root = expand_path(settings["arsiv_klasoru"])
    archive_root.mkdir(parents=True, exist_ok=True)
    if arguments.command in ("topla", "collect"):
        collect(settings, archive_root)
    elif arguments.command in ("dokum", "transcript"):
        write_transcripts(settings, archive_root, arguments.project)
    elif arguments.command in ("ozetle", "summarize"):
        summarize(settings, archive_root, arguments.project, arguments.manual)
    elif arguments.command in ("baglam", "context"):
        build_context(settings, archive_root, arguments.project, arguments.tokens, arguments.copy_target)
    elif arguments.command in ("hepsi", "all"):
        collect(settings, archive_root)
        write_transcripts(settings, archive_root, None)
        summarize(settings, archive_root, None, arguments.manual)
    elif arguments.command in ("durum", "status"):
        show_status(archive_root, settings["language"])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()



# Backward-compatible Turkish API aliases.
VARSAYILAN_AYAR = DEFAULT_SETTINGS
SURUM = VERSION
PROMPT_SURUMU = PROMPT_VERSION
BOLUM_SISTEM = CHAPTER_SYSTEM
CILT_SISTEM = VOLUME_SYSTEM
SISTEM_ETIKETI = SYSTEM_LABEL
genislet = expand_path
ayar_yukle = load_settings
dosya_hash = file_hash
guvenli_ad = safe_name
proje_adi = project_name
kaynaklari_bul = discover_sources
topla = collect
dokum_yaz = write_transcripts
proje_klasorleri = project_directories
ozetle = summarize
baglam = build_context
listele = show_status
kopya_git_guvenli_mi = ensure_git_safe_copy
llm_cagir = call_llm
gizli_temizle = redact_secrets
BURAYA = SUMMARY_PLACEHOLDER
durum_yukle = load_summary_state
durum_kaydet = save_summary_state
elle_duzenlenmis = is_manually_edited
ozet_govdesi = read_summary_body
claude_turlari = parse_claude_turns
codex_turlari = parse_codex_turns
antigravity_turlari = parse_antigravity_turns
elle_turlari = parse_manual_turns
oturum_oku = read_session
claude_cwd = claude_working_directory
codex_cwd = codex_working_directory
jsonl_satirlari = iter_jsonl_rows
token_tahmini = estimate_tokens
zaman_str = format_timestamp
metin_hash = text_hash
kisalt = truncate_text
OKUYUCULAR = PARSERS
Tur = Turn
