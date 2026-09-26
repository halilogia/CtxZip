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
import sys
from datetime import datetime
from pathlib import Path

from ctxzip_core.text import (
    estimate_tokens, text_hash, format_timestamp, SISTEM_ETIKETI as SYSTEM_LABEL, clean_text, truncate_text,
)
from ctxzip_core.parsers import (
    iter_jsonl_rows, claude_working_directory, codex_working_directory, is_codex_file, Turn, tool_summary, parse_claude_turns, parse_codex_turns, parse_antigravity_turns, parse_manual_turns, PARSERS, PARSER_VERSIONS, read_session, read_session_events, event_session_id,
)
from ctxzip_core.sessions import list_sessions
from ctxzip_core.transcripts import generate_transcripts
from ctxzip_core.context_generation import (
    build_context_pack, _event_provenance, _knowledge_context_items,
    _repository_context_item, _session_source_hash, _recent_context_items, _stale_chapter_files,
)
from ctxzip_core.source_collection import (
    collect_sources, discover_sources, expand_path, file_hash, project_name, safe_name,
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
from ctxzip_core.summary_validity import SummaryValidityError, record_summary_validity
from ctxzip_core.git_safety import ensure_git_safe_copy
from ctxzip_core.retrieval import SummaryCandidate, deduplicate_overlapping_summaries, rank_summaries
from ctxzip_core.summary_ranges import source_ranges_for_summary
from ctxzip_core.git_state import capture_git_snapshot
from ctxzip_core.context_planner import ContextItem, balanced_allocation, plan_context
from ctxzip_core.recent_context import SessionTurns, select_uncovered_recent_turns
from ctxzip_core.source_freshness import chapter_source_hash
from ctxzip_core.context_pack import FORMAT_ID, SCHEMA_VERSION, render_metadata_block
from ctxzip_core.diagnostics import run_diagnostics
from ctxzip_core.test_runner import run_and_record_test
from ctxzip_core.knowledge_capture import capture_knowledge, SUPPORTED_SOURCES
from ctxzip_core.knowledge import (
    Freshness, KnowledgeStatus, KnowledgeStore, KnowledgeStoreError, QuestionStatus, TaskStatus,
    knowledge_freshness, test_freshness,
)
from ctxzip_core.llm import call_llm
from ctxzip_core.privacy import redact_secrets
from ctxzip_core.i18n import LocalizationError, preferred_language, translate, validate_catalogs
from ctxzip_core.storage import atomic_copy2, atomic_write_text

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


def load_settings(path: Path) -> dict:
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    if path.exists():
        user_settings = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(user_settings, dict):
            raise ValueError("Settings file must contain a JSON object")
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


# ---------------------------------------------------------------- 1) collect

def collect(settings: dict, archive_root: Path) -> None:
    result = collect_sources(settings, archive_root)
    print(translate(
        settings.get("language"), "collect_result",
        new=result.new, updated=result.updated, same=result.unchanged, path=archive_root,
    ))

# ---------------------------------------------------------------- 2) transcripts


def write_transcripts(settings: dict, archive_root: Path, project: str | None) -> None:
    for project_dir in project_directories(archive_root, project, settings.get("language", "tr")):
        result = generate_transcripts(settings, project_dir)
        print(translate(
            settings.get("language"), "transcript_result",
            project=result.project, count=result.count, path=result.output_dir,
        ))


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

# ---------------------------------------------------------------- 4) context pack

def build_context(
    settings: dict,
    archive_root: Path,
    project: str,
    budget: int,
    copy_target: str | None,
    *,
    task: str = "",
    files: tuple[str, ...] = (),
    commits: tuple[str, ...] = (),
    symbols: tuple[str, ...] = (),
    changed_files: tuple[str, ...] = (),
    git_snapshot=None,
    explain: bool = False,
    budget_profile: str = "priority",
) -> None:
    project_dir = project_directories(archive_root, project, settings.get("language", "tr"))[0]
    build_context_pack(
        settings, project_dir, budget, copy_target, task=task, files=files,
        commits=commits, symbols=symbols, changed_files=changed_files,
        git_snapshot=git_snapshot, explain=explain, budget_profile=budget_profile,
    )


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
    doctor_requested = False
    argument_index = 1
    while argument_index < len(sys.argv):
        option = sys.argv[argument_index]
        if option in ("--ayar", "--settings", "--language"):
            argument_index += 2
            continue
        if option.startswith("-"):
            argument_index += 1
            continue
        doctor_requested = option == "doctor"
        break
    settings_option = next((option for option in ("--ayar", "--settings") if option in sys.argv), None)
    if settings_option and sys.argv.index(settings_option) + 1 < len(sys.argv):
        settings_path = Path(sys.argv[sys.argv.index(settings_option) + 1])
    settings_error = False
    try:
        bootstrap_settings = load_settings(settings_path)
    except (OSError, ValueError, UnicodeError) as error:
        if not doctor_requested:
            raise SystemExit(f"Invalid settings file: {error}") from None
        bootstrap_settings = None
        settings_error = True
    configured_language = (bootstrap_settings or DEFAULT_SETTINGS).get("language", "tr")
    if not isinstance(configured_language, str):
        configured_language = "tr"
    explicit_language = None
    if "--language" in sys.argv and sys.argv.index("--language") + 1 < len(sys.argv):
        explicit_language = sys.argv[sys.argv.index("--language") + 1]
    try:
        language = preferred_language(configured_language, explicit_language)
        validate_catalogs()
    except (LocalizationError, OSError, ValueError) as error:
        if not doctor_requested:
            raise SystemExit(str(error)) from None
        try:
            language = preferred_language("en", explicit_language)
        except LocalizationError:
            language = "en"

    def translate_message(key: str, **values: object) -> str:
        try:
            return translate(language, key, **values)
        except (LocalizationError, OSError, ValueError):
            if doctor_requested:
                return key.replace("_", " ")
            raise

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
    validity_parser = subparsers.add_parser(
        "summary-validity", aliases=["ozet-gecerlilik"],
        help=translate_message("summary_validity_help"),
    )
    validity_parser.add_argument("--project", required=True, help=translate_message("summary_validity_project_help"))
    validity_parser.add_argument("summary_file", help=translate_message("summary_validity_file_help"))
    validity_parser.add_argument(
        "--validity-path", action="append", default=[],
        help=translate_message("summary_validity_path_help"),
    )
    context_parser = subparsers.add_parser("baglam", aliases=["context"], help=translate_message("context_help"))
    context_parser.add_argument("project")
    context_parser.add_argument("--token", "--tokens", dest="tokens", type=int, default=12000)
    context_parser.add_argument(
        "--budget-profile", choices=("priority", "balanced"), default="priority",
        help=translate_message("context_budget_profile_help"),
    )
    context_parser.add_argument("--kopyala", "--copy", dest="copy_target", help=translate_message("copy_help"))
    context_parser.add_argument("--task", help=translate_message("context_task_help"))
    context_parser.add_argument("--file", dest="files", action="append", default=[], help=translate_message("context_file_help"))
    context_parser.add_argument("--commit", dest="commits", action="append", default=[], help=translate_message("context_commit_help"))
    context_parser.add_argument("--symbol", dest="symbols", action="append", default=[], help=translate_message("context_symbol_help"))
    context_parser.add_argument("--from-git-diff", action="store_true", help=translate_message("context_git_diff_help"))
    context_parser.add_argument("--explain", action="store_true", help=translate_message("context_explain_help"))
    all_command_parser = subparsers.add_parser("hepsi", aliases=["all"], help=translate_message("all_help"))
    all_command_parser.add_argument("--elle", "--manual", dest="manual", action="store_true", help=translate_message("manual_help"))
    all_command_parser.add_argument("--onayli-gonder", "--approved-send", dest="onayli_gonder", action="store_true",
                   help=translate_message("approved_help"))
    subparsers.add_parser("durum", aliases=["status"], help=translate_message("status_help"))
    subparsers.add_parser("doctor", help=translate_message("doctor_help"))
    knowledge_parser = subparsers.add_parser(
        "knowledge", aliases=["hafiza"], help=translate_message("knowledge_help")
    )
    knowledge_commands = knowledge_parser.add_subparsers(dest="knowledge_command", required=True)
    knowledge_add_parser = knowledge_commands.add_parser("add", help=translate_message("knowledge_add_help"))
    knowledge_add_parser.add_argument("--project", required=True, help=translate_message("knowledge_project_help"))
    knowledge_add_parser.add_argument(
        "--kind", required=True, choices=("decision", "constraint", "task", "question", "file"),
        help=translate_message("knowledge_kind_help"),
    )
    knowledge_add_parser.add_argument(
        "--source", required=True, choices=SUPPORTED_SOURCES,
        help=translate_message("knowledge_source_help"),
    )
    knowledge_add_parser.add_argument("--session", required=True, help=translate_message("knowledge_session_help"))
    knowledge_add_parser.add_argument("--turn", required=True, type=int, help=translate_message("knowledge_turn_help"))
    knowledge_add_parser.add_argument("--text", help=translate_message("knowledge_text_help"))
    knowledge_add_parser.add_argument(
        "--status", choices=("observed", "inferred", "confirmed"),
        help=translate_message("knowledge_status_help"),
    )
    knowledge_add_parser.add_argument("--scope", help=translate_message("knowledge_scope_help"))
    knowledge_add_parser.add_argument("--path", help=translate_message("knowledge_path_help"))
    knowledge_add_parser.add_argument("--symbol", help=translate_message("knowledge_symbol_help"))
    knowledge_add_parser.add_argument(
        "--task-status", choices=("open", "in_progress"),
        help=translate_message("knowledge_task_status_help"),
    )
    knowledge_add_parser.add_argument(
        "--validity-path", action="append", default=[],
        help=translate_message("knowledge_validity_path_help"),
    )
    knowledge_add_parser.add_argument("--validity-head", help=translate_message("knowledge_validity_head_help"))
    knowledge_add_parser.add_argument("--supersedes", help=translate_message("knowledge_supersedes_help"))
    test_run_parser = subparsers.add_parser("test-run", aliases=["record-test"], help=translate_message("test_run_help"))
    test_run_parser.add_argument("--project", required=True, help=translate_message("test_project_help"))
    test_run_parser.add_argument("--scope", action="append", default=[], help=translate_message("test_scope_help"))
    test_run_parser.add_argument("test_argv", nargs=argparse.REMAINDER)
    arguments = argument_parser.parse_args()

    if arguments.command == "doctor":
        doctor_settings = bootstrap_settings or DEFAULT_SETTINGS
        checks = run_diagnostics(
            doctor_settings,
            repository_dir=Path.cwd(),
            settings_valid=not settings_error,
        )
        print(translate_message("doctor_heading"))
        for check in checks:
            status_label = translate_message(f"doctor_status_{check.status}")
            check_label = translate_message(check.check_key)
            values = dict(check.values)
            if "key_present" in values:
                values["key_present"] = translate_message(
                    "doctor_yes" if values["key_present"] else "doctor_no"
                )
            detail = translate_message(check.detail_key, **values)
            print(f"[{status_label}] {check_label}: {detail}")
        raise SystemExit(1 if any(check.status == "error" for check in checks) else 0)

    settings = bootstrap_settings or load_settings(Path(arguments.settings))
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
    elif arguments.command in ("summary-validity", "ozet-gecerlilik"):
        project_dir = project_directories(archive_root, arguments.project, settings["language"])[0]
        try:
            summary_name, paths, head_sha = record_summary_validity(
                project_dir, arguments.summary_file, tuple(arguments.validity_path), Path.cwd(),
            )
        except SummaryValidityError as error:
            raise SystemExit(translate_message(f"summary_validity_{error.code}")) from None
        print(translate_message(
            "summary_validity_recorded", file=summary_name, count=len(paths), head=head_sha[:12],
        ))
    elif arguments.command in ("baglam", "context"):
        changed_files = ()
        git_snapshot = None
        if arguments.from_git_diff:
            git_snapshot = capture_git_snapshot(Path.cwd())
            if not git_snapshot.is_repository:
                raise SystemExit(translate(settings["language"], "context_git_required"))
            changed_files = git_snapshot.changed_files
        build_context(settings, archive_root, arguments.project, arguments.tokens, arguments.copy_target,
                      task=arguments.task or "", files=tuple(arguments.files), commits=tuple(arguments.commits),
                      symbols=tuple(arguments.symbols), changed_files=changed_files,
                      git_snapshot=git_snapshot,
                      explain=arguments.explain, budget_profile=arguments.budget_profile)
    elif arguments.command in ("hepsi", "all"):
        collect(settings, archive_root)
        write_transcripts(settings, archive_root, None)
        summarize(settings, archive_root, None, arguments.manual)
    elif arguments.command in ("durum", "status"):
        show_status(archive_root, settings["language"])
    elif arguments.command in ("test-run", "record-test"):
        command = arguments.test_argv[1:] if arguments.test_argv[:1] == ["--"] else arguments.test_argv
        if not command:
            raise SystemExit(translate(settings["language"], "test_command_required"))
        project_dir = project_directories(archive_root, arguments.project, settings["language"])[0]
        evidence = run_and_record_test(
            command,
            store=KnowledgeStore(project_dir / "knowledge"),
            repository_dir=Path.cwd(),
            scope=arguments.scope,
        )
        exit_display = (
            str(evidence.exit_code)
            if evidence.exit_code is not None
            else translate(settings["language"], "test_exit_unavailable")
        )
        head_display = evidence.head_sha or translate(settings["language"], "test_head_unknown")
        result_display = translate(settings["language"], f"test_result_{evidence.result.value}")
        print(translate(
            settings["language"], "test_run_recorded",
            result=result_display, exit_code=exit_display, head=head_display,
        ))
        raise SystemExit(evidence.exit_code if evidence.exit_code is not None else 127)
    elif arguments.command in ("knowledge", "hafiza"):
        project_dir = project_directories(archive_root, arguments.project, settings["language"])[0]
        try:
            record = capture_knowledge(
                project_dir,
                kind=arguments.kind,
                source_id=arguments.source,
                session_id=arguments.session,
                turn_number=arguments.turn,
                text=arguments.text,
                status=arguments.status,
                scope=arguments.scope,
                path=arguments.path,
                symbol=arguments.symbol,
                task_status=arguments.task_status,
                validity_paths=tuple(arguments.validity_path),
                validity_head_sha=arguments.validity_head,
                supersedes=arguments.supersedes,
            )
        except (ValueError, KnowledgeStoreError) as error:
            raise SystemExit(translate(settings["language"], "knowledge_capture_error", error=error)) from None
        except OSError:
            raise SystemExit(translate(settings["language"], "knowledge_capture_unavailable")) from None
        kind_label = translate(settings["language"], f"knowledge_kind_{arguments.kind}")
        print(translate(
            settings["language"], "knowledge_capture_recorded",
            kind=kind_label, record_id=record.id, source=arguments.source,
            turn=arguments.turn, event_count=len(record.source_refs),
        ))


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
