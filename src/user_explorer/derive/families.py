"""Two-pass deterministic event family detection.

Pass 1: verb-suffix matching on the last token of the event name.
Pass 2: first-token prefix clustering for remaining unassigned events.
Cap at MAX_FAMILIES; overflow -> "other".
Colors are hash-stable: same family name = same color across all runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import polars as pl

_SPLIT_RE = re.compile(r"[_.\-: ]+")

# 12-hue palette: (color, bg, fg) per slot
_PALETTE: list[tuple[str, str, str]] = [
    ("#3B82F6", "#DBEAFE", "#1E40AF"),
    ("#10B981", "#D1FAE5", "#065F46"),
    ("#F59E0B", "#FEF3C7", "#92400E"),
    ("#EF4444", "#FEE2E2", "#991B1B"),
    ("#8B5CF6", "#EDE9FE", "#5B21B6"),
    ("#EC4899", "#FCE7F3", "#9D174D"),
    ("#06B6D4", "#CFFAFE", "#164E63"),
    ("#F97316", "#FFEDD5", "#9A3412"),
    ("#84CC16", "#ECFCCB", "#3F6212"),
    ("#6366F1", "#E0E7FF", "#3730A3"),
    ("#14B8A6", "#CCFBF1", "#134E4A"),
    ("#A855F7", "#F3E8FF", "#6B21A8"),
]
_OTHER: tuple[str, str, str] = ("#9CA3AF", "#F3F4F6", "#374151")

_VERB_FAMILIES: dict[str, str] = {
    "viewed": "view",
    "opened": "view",
    "shown": "view",
    "displayed": "view",
    "rendered": "view",
    "impression": "view",
    "clicked": "click",
    "tapped": "click",
    "selected": "click",
    "pressed": "click",
    "chose": "click",
    "submitted": "submit",
    "sent": "submit",
    "posted": "submit",
    "created": "submit",
    "completed": "submit",
    "closed": "close",
    "dismissed": "close",
    "cancelled": "close",
    "canceled": "close",
    "abandoned": "close",
    "failed": "error",
    "error": "error",
    "exception": "error",
    "denied": "error",
    "started": "start",
    "began": "start",
    "init": "start",
    "succeeded": "success",
    "ok": "success",
    "success": "success",
    "received": "success",
    "loaded": "success",
    "fetched": "success",
    "resolved": "success",
    "copied": "click",
    "toggled": "click",
    "dragged": "click",
    "scrolled": "click",
    "searched": "click",
    "filtered": "click",
    "sorted": "click",
    "edited": "submit",
    "updated": "submit",
    "saved": "submit",
    "uploaded": "submit",
    "used": "submit",
    "invoked": "submit",
    "triggered": "submit",
    "executed": "submit",
    "generated": "submit",
    "requested": "submit",
    "downloaded": "click",
    "exported": "submit",
    "imported": "submit",
    "archived": "close",
    "deleted": "close",
    "removed": "close",
    "revoked": "close",
}

MAX_FAMILIES = 12
_PREFIX_MIN_DISTINCT = 3
_PREFIX_MIN_SHARE = 0.005


@dataclass(frozen=True)
class FamilyInfo:
    color: str
    bg: str
    fg: str
    label: str


def derive_families(
    event_names: pl.Series,
    *,
    no_families: bool = False,
) -> tuple[dict[str, str], dict[str, FamilyInfo]]:
    """Return (assignment, registry).

    assignment: {event_name: family_name}
    registry:   {family_name: FamilyInfo}
    """
    unique_names = [str(e) for e in event_names.drop_nulls().unique().to_list()]

    if no_families:
        c, bg, fg = _OTHER
        return (
            {n: "other" for n in unique_names},
            {"other": FamilyInfo(color=c, bg=bg, fg=fg, label="Other")},
        )

    total = max(event_names.len(), 1)

    # Pass 1: verb-suffix
    assignment: dict[str, str] = {}
    for name in unique_names:
        tokens = [t.lower() for t in _SPLIT_RE.split(name) if t]
        if tokens and tokens[-1] in _VERB_FAMILIES:
            assignment[name] = _VERB_FAMILIES[tokens[-1]]

    # Build count map for pass 2 share calculation
    count_map: dict[str, int] = {}
    for row in event_names.value_counts().iter_rows():
        count_map[str(row[0])] = int(row[1])

    # Pass 2: first-token prefix for still-unassigned events
    prefix_groups: dict[str, list[str]] = {}
    for name in unique_names:
        if name in assignment:
            continue
        tokens = [t.lower() for t in _SPLIT_RE.split(name) if t]
        if tokens:
            prefix_groups.setdefault(tokens[0], []).append(name)

    for prefix, names in prefix_groups.items():
        if len(names) < _PREFIX_MIN_DISTINCT:
            continue
        if sum(count_map.get(n, 0) for n in names) / total < _PREFIX_MIN_SHARE:
            continue
        for name in names:
            assignment[name] = prefix

    # Remainder -> "other"
    for name in unique_names:
        assignment.setdefault(name, "other")

    # Sort named families; cap at MAX_FAMILIES
    named = sorted({v for v in assignment.values() if v != "other"})
    if len(named) > MAX_FAMILIES:
        overflow = set(named[MAX_FAMILIES:])
        for name in list(assignment):
            if assignment[name] in overflow:
                assignment[name] = "other"
        named = named[:MAX_FAMILIES]

    # Build registry with hash-stable color slots
    registry: dict[str, FamilyInfo] = {}
    for fam in named:
        c, bg, fg = _PALETTE[hash(fam) % len(_PALETTE)]
        registry[fam] = FamilyInfo(color=c, bg=bg, fg=fg, label=fam.replace("_", " ").title())
    if any(v == "other" for v in assignment.values()):
        c, bg, fg = _OTHER
        registry["other"] = FamilyInfo(color=c, bg=bg, fg=fg, label="Other")

    return assignment, registry
