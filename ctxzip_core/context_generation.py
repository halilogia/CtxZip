"""Build, validate, and write task-scoped context packs for one project."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

from .chunking import truncate_turn
from .context_pack import FORMAT_ID, SCHEMA_VERSION, render_metadata_block
from .context_planner import ContextItem, balanced_allocation, plan_context
from .git_safety import ensure_git_safe_copy
from .i18n import translate
from .knowledge import (
    Freshness, KnowledgeStatus, KnowledgeStore, QuestionStatus, TaskStatus,
    knowledge_freshness, test_freshness,
)
from .parsers import PARSER_VERSIONS, event_session_id, read_session, read_session_events
from .privacy import redact_secrets
from .recent_context import (
    SessionTurns, select_uncovered_recent_turns, session_turns_from_events,
)
from .retrieval import (
    SummaryCandidate, deduplicate_overlapping_summaries, rank_summaries,
    summary_is_possibly_stale,
)
from .sessions import list_sessions
from .source_collection import file_hash
from .source_freshness import chapter_source_hash
from .summary_ranges import source_ranges_for_summary
from .summary_store import (
    PLACEHOLDER as SUMMARY_PLACEHOLDER, load_summary_state, read_summary_body, is_manually_edited,
)
from .storage import atomic_copy2, atomic_write_text
from .text import estimate_tokens


def _event_provenance(references) -> str:
    labels = []
    for reference in references:
        source = reference.source
        label = f"{source.source_id}/{source.session_id}#T{source.turn_number}"
        if source.record_index is not None:
            label += f"/R{source.record_index}"
        label += f"@{source.source_hash[:12]}"
        labels.append(label)
    return "; ".join(labels)


def _knowledge_context_items(
    project_dir: Path,
    *,
    task: str,
    files: tuple[str, ...],
    commits: tuple[str, ...],
    symbols: tuple[str, ...],
    changed_files: tuple[str, ...],
    git_snapshot,
    language: str,
) -> list[ContextItem]:
    knowledge_dir = project_dir / "knowledge"
    if not knowledge_dir.exists():
        return []
    store = KnowledgeStore(knowledge_dir)
    items: list[ContextItem] = []
    ordinal = 0

    def add_ranked(
        *, record_id: str, section: str, title: str, text: str, metadata: dict[str, str],
        source: str, base_priority: float = 0, extra_reasons: tuple[str, ...] = (),
    ) -> None:
        nonlocal ordinal
        candidate = SummaryCandidate(title, text, section, metadata, ordinal, record_id)
        ranked = rank_summaries(
            [candidate], task=task, files=files, commits=commits, symbols=symbols,
            changed_files=changed_files,
        )[0]
        items.append(ContextItem(
            key=record_id,
            section=section,
            title=title,
            body=text,
            source=source,
            priority=ranked.score + base_priority,
            ordinal=ordinal,
            reasons=ranked.reasons + extra_reasons,
        ))
        ordinal += 1

    terminal_knowledge_statuses = {KnowledgeStatus.SUPERSEDED, KnowledgeStatus.INVALIDATED}
    for record in store.list_constraints():
        if record.status in terminal_knowledge_statuses:
            continue
        freshness = knowledge_freshness(record, git_snapshot)
        title = translate(
            language, "context_constraint_title", scope=record.scope, status=record.status.value,
        ) + " (" + translate(language, f"freshness_{freshness.value.replace('-', '_')}") + ")"
        add_ranked(
            record_id=record.id, section="constraints", title=title, text=record.statement,
            metadata={"scope": record.scope}, source=_event_provenance(record.source_refs),
            base_priority=(20.0 if record.status == KnowledgeStatus.CONFIRMED else 0.0)
            - (10.0 if freshness == Freshness.POSSIBLY_STALE else 0.0),
            extra_reasons=("validity-path-changed",) if freshness == Freshness.POSSIBLY_STALE else (),
        )
    for record in store.list_decisions():
        if record.status in terminal_knowledge_statuses:
            continue
        freshness = knowledge_freshness(record, git_snapshot)
        title = translate(
            language, "context_decision_title", status=record.status.value,
        ) + " (" + translate(language, f"freshness_{freshness.value.replace('-', '_')}") + ")"
        add_ranked(
            record_id=record.id, section="decisions", title=title, text=record.statement,
            metadata={}, source=_event_provenance(record.source_refs),
            base_priority=(30.0 if record.status == KnowledgeStatus.CONFIRMED else 0.0)
            - (10.0 if freshness == Freshness.POSSIBLY_STALE else 0.0),
            extra_reasons=("validity-path-changed",) if freshness == Freshness.POSSIBLY_STALE else (),
        )
    for record in store.list_test_evidence():
        freshness = test_freshness(record, git_snapshot).value if git_snapshot else Freshness.UNKNOWN.value
        result_text = translate(
            language, "context_test_body",
            result=translate(language, f"test_result_{record.result.value}"), freshness=freshness,
            command=record.command, exit_code=record.exit_code, captured_at=record.captured_at,
            head=record.head_sha or "-", fingerprint=(record.worktree_fingerprint or "-")[:12],
        )
        add_ranked(
            record_id=record.id, section="tests",
            title=translate(language, "context_test_title", freshness=freshness),
            text=result_text,
            metadata={"freshness": freshness},
            source=translate(language, "context_test_source", value=record.id),
            base_priority=25.0 if freshness == Freshness.CURRENT.value else 0.0,
        )
    for record in store.list_file_mentions():
        if record.status in terminal_knowledge_statuses:
            continue
        text = record.path + (f" — {record.symbol}" if record.symbol else "")
        path_is_changed = git_snapshot is not None and any(
            changed.casefold() == record.path.replace("\\", "/").casefold()
            for changed in git_snapshot.changed_files
        )
        freshness = "possibly-stale" if path_is_changed else "unknown"
        reasons = ("source-path-changed",) if path_is_changed else ()
        add_ranked(
            record_id=record.id, section="files",
            title=translate(language, "context_file_title") + " (" + translate(
                language, f"freshness_{freshness.replace('-', '_')}"
            ) + ")",
            text=text, metadata={"files": record.path, "symbols": record.symbol or ""},
            source=_event_provenance(record.source_refs), base_priority=-20.0 if path_is_changed else 0.0,
            extra_reasons=reasons,
        )
    for record in store.list_tasks():
        if record.status not in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS}:
            continue
        add_ranked(
            record_id=record.id, section="next_actions",
            title=translate(language, "context_task_record_title", status=record.status.value),
            text=record.title, metadata={}, source=_event_provenance(record.source_refs),
        )
    for record in store.list_open_questions():
        if record.status != QuestionStatus.OPEN:
            continue
        add_ranked(
            record_id=record.id, section="questions", title=translate(language, "context_question_title"),
            text=record.question, metadata={}, source=_event_provenance(record.source_refs),
        )
    return items


def _repository_context_item(git_snapshot, language: str) -> ContextItem:
    changed = list(git_snapshot.changed_files)
    max_paths = 40
    path_lines = changed[:max_paths]
    if len(changed) > max_paths:
        path_lines.append(translate(language, "context_more_changed_files", count=len(changed) - max_paths))
    body = "\n".join((
        translate(language, "context_git_branch", value=git_snapshot.branch or "-"),
        translate(language, "context_git_head", value=git_snapshot.head_sha or "-"),
        translate(language, "context_git_dirty", value=translate(
            language, "context_git_dirty_yes" if git_snapshot.dirty else "context_git_dirty_no"
        )),
        translate(language, "context_git_fingerprint", value=(git_snapshot.fingerprint or "-")[:16]),
        translate(language, "context_git_changed_files", value="\n".join(f"- {item}" for item in path_lines) or "-"),
    ))
    return ContextItem(
        key="git:current", section="repository", title=translate(language, "context_git_title"),
        body=body, source=f"git/{git_snapshot.head_sha or 'unknown'}", priority=1000.0,
        reasons=("current-git-snapshot",),
    )


def _session_source_hash(source_path: Path) -> str:
    if source_path.is_file():
        return file_hash(source_path)
    digest = hashlib.sha256()
    for markdown_path in sorted(source_path.rglob("*.md")):
        relative_path = markdown_path.relative_to(source_path).as_posix()
        digest.update(relative_path.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_hash(markdown_path)))
    return digest.hexdigest()


def _recent_context_items(
    project_dir: Path, settings: dict, language: str, budget: int, summary_state: dict,
) -> list[ContextItem]:
    recent_reserve = balanced_allocation(budget)["recent_raw"]
    if recent_reserve <= 0:
        return []
    sessions = []
    for tool_name, session_id, source_path in list_sessions(project_dir):
        session_key = f"{tool_name}/{session_id}"
        if tool_name == "claude-code" and settings.get("dusunceleri_dahil_et"):
            # Preserve the explicit private-thinking context option without
            # wrapping that content in the provider-neutral event model.
            turns, _metadata = read_session(tool_name, source_path, settings, language)
            session_turns = SessionTurns(
                session_key=session_key,
                source_hash=_session_source_hash(source_path),
                turns=tuple(turns),
            )
        else:
            parsed = read_session_events(tool_name, source_path, settings, language)
            session_turns = session_turns_from_events(
                parsed,
                session_key=session_key,
                source_id=tool_name,
                session_id=event_session_id(tool_name, source_path),
                source_hash=_session_source_hash(source_path),
                parser_version=PARSER_VERSIONS[tool_name],
            )
        if session_turns.turns:
            sessions.append(session_turns)
    recent_turns = select_uncovered_recent_turns(sessions, summary_state["bolumler"])
    per_turn_budget = max(1, recent_reserve - 64)
    return [
        ContextItem(
            key=turn.key,
            section="recent_raw",
            title=translate(
                language, "context_recent_turn_title", session=turn.session_key,
                turn=turn.turn_number, timestamp=turn.timestamp,
            ),
            body=truncate_turn(turn.text, per_turn_budget, language),
            source=turn.source,
            priority=float(ordinal),
            ordinal=ordinal,
            reasons=("recent-raw-tail",),
        )
        for ordinal, turn in enumerate(recent_turns)
    ]


def _stale_chapter_files(project_dir: Path, settings: dict, summary_state: dict) -> set[str]:
    """Find Chapters whose recorded source hash no longer matches their turns."""
    language = settings.get("language", "tr")
    sessions = {
        f"{tool_name}/{session_id}": source_path
        for tool_name, session_id, source_path in list_sessions(project_dir)
    }
    parsed_sessions = {}
    stale_files = set()
    for chapter in summary_state["bolumler"]:
        chapter_path = project_dir / "bolumler" / chapter["dosya"]
        metadata, _body = read_summary_body(chapter_path)
        if is_manually_edited(chapter_path):
            continue
        expected_hash = metadata.get("kaynak_hash", "")
        source_language = metadata.get("source_language")
        session_key = chapter.get("oturum", "")
        tool_name = session_key.split("/", 1)[0]
        expected_parser_version = metadata.get("parser_version", "")
        current_parser_version = PARSER_VERSIONS.get(tool_name)
        source_path = sessions.get(session_key)
        if expected_parser_version and current_parser_version and expected_parser_version != current_parser_version:
            stale_files.add(chapter["dosya"])
            continue
        if not expected_hash or source_path is None or source_language not in {"tr", "en"}:
            continue
        session_language_key = (session_key, source_language)
        if session_language_key not in parsed_sessions:
            parsed_sessions[session_language_key] = read_session(
                tool_name, source_path, settings, source_language,
            )[0]
        current_hash = chapter_source_hash(
            parsed_sessions[session_language_key], chapter["tur_baslangic"], chapter["tur_bitis"],
            settings["bolum_token"], source_language,
        )
        current_turns = parsed_sessions[session_language_key]
        if current_hash is not None and current_hash != expected_hash:
            stale_files.add(chapter["dosya"])
        elif current_hash is None and current_turns:
            # The source is readable but no longer contains the full recorded range.
            stale_files.add(chapter["dosya"])
    return stale_files


def build_context_pack(
    settings: dict,
    project_dir: Path,
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
    language = settings.get("language", "tr")
    summary_state = load_summary_state(project_dir)
    stale_chapter_files = _stale_chapter_files(project_dir, settings, summary_state)
    stale_chapter_numbers = {
        chapter["no"] for chapter in summary_state["bolumler"]
        if chapter["dosya"] in stale_chapter_files
    }
    stale_volume_numbers = {
        volume["no"] for volume in summary_state["ciltler"]
        if stale_chapter_numbers.intersection(volume["bolumler"])
    }
    current_chapter_state = dict(summary_state)
    current_chapter_state["bolumler"] = [
        chapter for chapter in summary_state["bolumler"]
        if chapter["dosya"] not in stale_chapter_files
    ]
    selected_summaries: list[tuple[str, str]] = []
    remaining_tokens = budget
    # Newest first: chapters not folded into volumes, followed by volumes.
    candidates = [
        ("bolumler", chapter_record["dosya"])
        for chapter_record in reversed(summary_state["bolumler"])
        if chapter_record["dosya"] not in stale_chapter_files
        and (chapter_record["cilt"] is None or chapter_record["cilt"] in stale_volume_numbers)
    ]
    candidates += [
        ("ciltler", volume["dosya"])
        for volume in reversed(summary_state["ciltler"])
        if volume["no"] not in stale_volume_numbers
    ]
    query_active = bool(task.strip() or files or commits or symbols or changed_files)
    knowledge_items = _knowledge_context_items(
        project_dir, task=task, files=files, commits=commits, symbols=symbols,
        changed_files=changed_files, git_snapshot=git_snapshot, language=language,
    )
    recent_items = (
        _recent_context_items(project_dir, settings, language, budget, current_chapter_state)
        if budget_profile == "balanced" else []
    )
    planner_active = query_active or bool(knowledge_items) or git_snapshot is not None or budget_profile != "priority"
    ranked_candidates: list[tuple[SummaryCandidate, Path]] = []
    for ordinal, (folder, name) in enumerate(candidates):
        path = project_dir / folder / name
        metadata, body = read_summary_body(path)
        if SUMMARY_PLACEHOLDER in body:
            continue
        title = path.read_text(encoding="utf-8").split("\n# ", 1)[-1].split("\n", 1)[0]
        candidate = SummaryCandidate(
            title, body, folder, metadata, ordinal, f"{folder}/{name}",
            source_ranges_for_summary(folder, name, summary_state, metadata),
            is_manually_edited(path),
        )
        current_head = getattr(git_snapshot, "head_sha", None)
        if summary_is_possibly_stale(candidate, changed_files, current_head):
            metadata = dict(metadata)
            metadata["freshness"] = Freshness.POSSIBLY_STALE.value
            candidate = SummaryCandidate(
                candidate.title, candidate.body, candidate.kind, metadata,
                candidate.ordinal, candidate.candidate_id, candidate.source_ranges,
                candidate.manually_edited,
            )
        ranked_candidates.append((candidate, path))
    ranked = rank_summaries(
        [item[0] for item in ranked_candidates], task=task, files=files, commits=commits,
        symbols=symbols, changed_files=changed_files,
    )
    ranked, overlap_exclusions = deduplicate_overlapping_summaries(ranked)
    omitted_count = 0
    selected_ranking = []
    context_plan = None
    source_label = translate(language, "context_source_label")
    if planner_active:
        planner_items = list(knowledge_items) + recent_items
        if task.strip():
            planner_items.append(ContextItem(
                key="task:current", section="task", title=translate(language, "context_task_title"),
                body=task.strip(), source=translate(language, "context_task_source"), priority=1000.0,
                reasons=("explicit-task",),
            ))
        requested_paths = list(dict.fromkeys(files + symbols + commits))
        if requested_paths:
            planner_items.append(ContextItem(
                key="query:targets", section="files", title=translate(language, "context_targets_title"),
                body="\n".join(f"- {item}" for item in requested_paths),
                source=translate(language, "context_task_source"), priority=1000.0,
                reasons=("explicit-reference",),
            ))
        if git_snapshot is not None:
            planner_items.append(_repository_context_item(git_snapshot, language))
        for ranked_item in ranked:
            candidate = ranked_item.candidate
            summary_source = ""
            source_session = candidate.metadata.get("kaynak")
            source_turns = candidate.metadata.get("turlar")
            if source_session or source_turns:
                summary_source = "; ".join(value for value in (source_session, source_turns) if value)
            freshness = str(candidate.metadata.get("freshness", "")).casefold().replace("-", "_")
            summary_title = candidate.title
            if freshness in {"stale", "possibly_stale"}:
                summary_title += " (" + translate(language, f"freshness_{freshness}") + ")"
            planner_items.append(ContextItem(
                key=f"summary:{candidate.candidate_id}", section="summaries",
                title=summary_title, body=candidate.body, source=summary_source,
                priority=ranked_item.score, ordinal=candidate.ordinal,
                reasons=ranked_item.reasons,
            ))
        context_plan = plan_context(planner_items, budget, source_label, profile=budget_profile)
        selected_keys = {item.key for item in context_plan.selected}
        selected_summaries = [
            (item.title, item.body) for item in context_plan.selected if item.section == "summaries"
        ]
        selected_ranking = [
            item for item in ranked if f"summary:{item.candidate.candidate_id}" in selected_keys
        ]
        omitted_count = len(context_plan.omitted)
        remaining_tokens = budget - context_plan.token_count
    else:
        for ranked_item in ranked:
            candidate = ranked_item.candidate
            token_count = estimate_tokens(candidate.body)
            if token_count > remaining_tokens:
                omitted_count += 1
                continue
            selected_summaries.append((candidate.title, candidate.body))
            selected_ranking.append(ranked_item)
            remaining_tokens -= token_count
    if not planner_active:
        selected_summaries.reverse()  # Preserve legacy chronological output without selectors.
    if explain:
        if context_plan and context_plan.profile == "balanced":
            print(translate(
                language, "budget_reserves",
                recent_budget=context_plan.recent_raw_budget_tokens,
                recent_used=context_plan.recent_raw_used_tokens,
                safety=context_plan.safety_reserved_tokens,
            ))
        reason_labels = {
            "recency-fallback": translate(language, "selection_reason_recency"),
        }
        for ranked_item in selected_ranking:
            rendered_reasons = []
            for reason in ranked_item.reasons:
                if reason.startswith("file:"):
                    rendered_reasons.append(translate(language, "selection_reason_file", value=reason[5:]))
                elif reason.startswith("commit:"):
                    rendered_reasons.append(translate(language, "selection_reason_commit", value=reason[7:]))
                elif reason.startswith("changed-file:"):
                    rendered_reasons.append(translate(language, "selection_reason_changed_file", value=reason[13:]))
                elif reason.startswith("symbol:"):
                    rendered_reasons.append(translate(language, "selection_reason_symbol", value=reason[7:]))
                elif reason.startswith("task-terms:"):
                    rendered_reasons.append(translate(language, "selection_reason_task", value=reason[11:]))
                elif reason.startswith("freshness:"):
                    rendered_reasons.append(translate(language, "selection_reason_freshness", value=reason[10:]))
                elif reason in {"source-path-changed", "validity-path-changed"}:
                    rendered_reasons.append(translate(language, "selection_reason_path_changed"))
                elif reason == "recent-raw-tail":
                    rendered_reasons.append(translate(language, "selection_reason_recent_raw"))
                else:
                    rendered_reasons.append(reason_labels.get(reason, reason))
            print(translate(language, "selection_explanation", title=ranked_item.candidate.title,
                            score=f"{ranked_item.score:g}", reasons=", ".join(rendered_reasons)))
        for exclusion in overlap_exclusions:
            print(translate(
                language,
                "selection_overlap_omitted",
                title=exclusion.candidate.candidate.title,
                sources=", ".join(exclusion.overlaps_with),
            ))
        if context_plan is not None:
            section_names = {
                item.section: translate(language, f"planner_section_{item.section}")
                for item in context_plan.selected
            }
            for item in context_plan.selected:
                if item.section == "summaries":
                    continue
                reasons = [translate(language, "selection_reason_section", value=section_names[item.section])]
                for reason in item.reasons:
                    if reason.startswith("file:"):
                        reasons.append(translate(language, "selection_reason_file", value=reason[5:]))
                    elif reason.startswith("commit:"):
                        reasons.append(translate(language, "selection_reason_commit", value=reason[7:]))
                    elif reason.startswith("changed-file:"):
                        reasons.append(translate(language, "selection_reason_changed_file", value=reason[13:]))
                    elif reason.startswith("symbol:"):
                        reasons.append(translate(language, "selection_reason_symbol", value=reason[7:]))
                    elif reason.startswith("task-terms:"):
                        reasons.append(translate(language, "selection_reason_task", value=reason[11:]))
                    elif reason.startswith("freshness:"):
                        reasons.append(translate(language, "selection_reason_freshness", value=reason[10:]))
                    elif reason == "source-path-changed":
                        reasons.append(translate(language, "selection_reason_path_changed"))
                    elif reason == "validity-path-changed":
                        reasons.append(translate(language, "selection_reason_path_changed"))
                    elif reason == "recent-raw-tail":
                        reasons.append(translate(language, "selection_reason_recent_raw"))
                print(translate(
                    language, "selection_explanation", title=item.title,
                    score=f"{item.priority:g}", reasons=", ".join(reasons),
                ))
            for omitted_item in context_plan.omitted:
                omitted_tokens = estimate_tokens(omitted_item.rendered(source_label))
                print(translate(language, "selection_omitted", title=omitted_item.title, tokens=omitted_tokens))
    output_lines = [f"# {project_dir.name} — {translate(language, 'context_title')}",
             f"_{translate(language, 'generated')}: {datetime.now().strftime('%Y-%m-%d %H:%M')} · {translate(language, 'summary_count', count=len(selected_summaries))} · ~{translate(language, 'token_count', count=budget - remaining_tokens)}"
             + (f" · {omitted_count} {translate(language, 'budget_omitted')}" if omitted_count else "") + "_", "",
             "> " + translate(language, "context_notice"), ""]
    if context_plan is None:
        for title, body in selected_summaries:
            output_lines.append(f"---\n\n# {title}\n\n{body}\n")
    else:
        previous_section = None
        for item in context_plan.selected:
            if item.section != previous_section:
                section_title = translate(language, f"planner_section_{item.section}")
                output_lines.extend((f"## {section_title}", ""))
                previous_section = item.section
            output_lines.extend((item.rendered(source_label), ""))
    target = project_dir / "BAGLAM.md"
    metadata_sources = []
    if context_plan is not None:
        metadata_sources = [item.source for item in context_plan.selected if item.source]
    else:
        metadata_sources = [
            source for ranked_item in selected_ranking
            for source in (
                ranked_item.candidate.metadata.get("kaynak", ""),
                ranked_item.candidate.metadata.get("turlar", ""),
            ) if source
        ]
    git_metadata = None
    if git_snapshot is not None:
        git_metadata = {
            "branch": git_snapshot.branch,
            "head_sha": git_snapshot.head_sha,
            "dirty": git_snapshot.dirty,
            "worktree_fingerprint": git_snapshot.fingerprint,
        }
    pack_metadata = {
        "format": FORMAT_ID,
        "schema_version": SCHEMA_VERSION,
        "project": project_dir.name,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "language": language,
        "budget": {
            "limit": budget,
            "profile": context_plan.profile if context_plan else "priority",
            "recent_raw_allocation": context_plan.recent_raw_budget_tokens if context_plan else 0,
            "recent_raw_used": context_plan.recent_raw_used_tokens if context_plan else 0,
            "recent_raw_reserved": context_plan.recent_raw_reserved_tokens if context_plan else 0,
            "safety_reserved": context_plan.safety_reserved_tokens if context_plan else 0,
        },
        "estimated_tokens": budget - remaining_tokens,
        "git": git_metadata,
        "sources": list(dict.fromkeys(metadata_sources)),
    }
    markdown_body = "\n".join(output_lines)
    output_text = redact_secrets(render_metadata_block(pack_metadata) + "\n\n" + markdown_body, language)
    atomic_write_text(target, output_text)
    print(translate(language, "context_result", path=target, count=len(selected_summaries), tokens=budget - remaining_tokens))
    if copy_target:
        source_root = Path(os.path.expanduser(copy_target))
        source_root = source_root / "BAGLAM.md" if source_root.is_dir() else source_root
        ensure_git_safe_copy(source_root, language)
        atomic_copy2(target, source_root)
        print(f"[{translate(language, 'copied')}] -> {source_root}")
