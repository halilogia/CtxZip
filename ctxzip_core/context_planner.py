"""Priority-ordered, approximate-budget planning for context-pack items."""
from __future__ import annotations

from dataclasses import dataclass

from .text import estimate_tokens

SECTION_ORDER = (
    "task",
    "constraints",
    "decisions",
    "repository",
    "tests",
    "files",
    "summaries",
    "recent_raw",
    "next_actions",
    "questions",
)
BALANCED_ALLOCATION_UNITS = {
    "task_state": 4,
    "decisions": 3,
    "git_tests": 4,
    "files": 8,
    "summaries": 7,
    "recent_raw": 4,
    "safety": 2,
}
SECTION_ALLOCATION_GROUP = {
    "task": "task_state",
    "constraints": "task_state",
    "next_actions": "task_state",
    "questions": "task_state",
    "decisions": "decisions",
    "repository": "git_tests",
    "tests": "git_tests",
    "files": "files",
    "summaries": "summaries",
    "recent_raw": "recent_raw",
}


@dataclass(frozen=True)
class ContextItem:
    key: str
    section: str
    title: str
    body: str
    source: str = ""
    priority: float = 0.0
    ordinal: int = 0
    reasons: tuple[str, ...] = ()

    def rendered(self, source_label: str) -> str:
        content = f"### {self.title}\n\n{self.body.strip()}"
        if self.source:
            content += f"\n\n_{source_label}: {self.source}_"
        return content


@dataclass(frozen=True)
class ContextPlan:
    selected: tuple[ContextItem, ...]
    omitted: tuple[ContextItem, ...]
    token_count: int
    profile: str = "priority"
    reserved_tokens: int = 0
    recent_raw_budget_tokens: int = 0
    recent_raw_used_tokens: int = 0
    recent_raw_reserved_tokens: int = 0
    safety_reserved_tokens: int = 0


def balanced_allocation(budget: int) -> dict[str, int]:
    """Scale the roadmap's 32k allocation example to an arbitrary token budget."""
    if budget < 0:
        raise ValueError("Context budget cannot be negative")
    base = {name: budget * units // 32 for name, units in BALANCED_ALLOCATION_UNITS.items()}
    remainders = {name: budget * units % 32 for name, units in BALANCED_ALLOCATION_UNITS.items()}
    remaining = budget - sum(base.values())
    order = {name: index for index, name in enumerate(remainders)}
    for name in sorted(remainders, key=lambda key: (-remainders[key], order[key]))[:remaining]:
        base[name] += 1
    return base


def plan_context(
    items: list[ContextItem], budget: int, source_label: str, profile: str = "priority",
) -> ContextPlan:
    """Select by fixed section order, then relevance priority, within one budget.

    Oversized items are skipped so a smaller later item can still fit. Duplicate
    keys are included only once. This is an approximate, model-independent budget.
    """
    if profile not in {"priority", "balanced"}:
        raise ValueError("Unknown context allocation profile")
    allocation = balanced_allocation(budget) if profile == "balanced" else None
    section_ranks = {name: index for index, name in enumerate(SECTION_ORDER)}
    ordered = sorted(
        items,
        key=lambda item: (section_ranks.get(item.section, len(section_ranks)), -item.priority, item.ordinal),
    )
    selected: list[ContextItem] = []
    omitted: list[ContextItem] = []
    used = 0
    seen: set[str] = set()
    used_by_group = {name: 0 for name in (allocation or {})}
    for item in ordered:
        if item.key in seen:
            continue
        seen.add(item.key)
        cost = estimate_tokens(item.rendered(source_label))
        group = SECTION_ALLOCATION_GROUP.get(item.section)
        if allocation is None:
            group_remaining = budget
        elif group in allocation:
            group_remaining = allocation[group] - used_by_group[group]
        else:
            group_remaining = 0
        if cost <= min(budget - used, group_remaining):
            selected.append(item)
            used += cost
            if allocation is not None and group in used_by_group:
                used_by_group[group] += cost
        else:
            omitted.append(item)
    recent_raw_budget = allocation["recent_raw"] if allocation else 0
    recent_raw_used = used_by_group["recent_raw"] if allocation else 0
    recent_raw_reserve = recent_raw_budget - recent_raw_used
    safety_reserve = allocation["safety"] if allocation else 0
    return ContextPlan(
        selected=tuple(selected), omitted=tuple(omitted), token_count=used, profile=profile,
        reserved_tokens=recent_raw_reserve + safety_reserve,
        recent_raw_budget_tokens=recent_raw_budget,
        recent_raw_used_tokens=recent_raw_used,
        recent_raw_reserved_tokens=recent_raw_reserve,
        safety_reserved_tokens=safety_reserve,
    )
