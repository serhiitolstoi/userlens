"""Resolve which columns play the role of user_id / timestamp / event_name / session_id.

Strategy, in order:
  1. Honor explicit overrides (from CLI flags).
  2. Match header names against the alias table.
  3. Content-sniff a sample of values to make educated guesses.
  4. Give up with a precise actionable error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import polars as pl

from user_explorer.schema.aliases import find_canonical
from user_explorer.schema.types import ResolvedSchema

SAMPLE_ROWS = 1000


class SchemaError(ValueError):
    """Raised when the required schema cannot be resolved."""


@dataclass(frozen=True)
class SniffedSchema:
    schema: ResolvedSchema
    notes: tuple[str, ...]  # human-readable notes about how each column was resolved


def sniff_schema(
    sample: pl.DataFrame,
    *,
    user_id_override: str | None = None,
    timestamp_override: str | None = None,
    event_name_override: str | None = None,
) -> SniffedSchema:
    columns = sample.columns
    notes: list[str] = []
    assigned: dict[str, str] = {}

    # 1. Honor explicit overrides.
    for canonical, override in (
        ("user_id", user_id_override),
        ("timestamp", timestamp_override),
        ("event_name", event_name_override),
    ):
        if override is None:
            continue
        if override not in columns:
            raise SchemaError(
                f"--{canonical.replace('_', '-')}={override!r} not found in columns: {columns}"
            )
        assigned[canonical] = override
        notes.append(f"{canonical} = {override!r} (explicit override)")

    # 2. Alias-table match on remaining roles.
    remaining_columns = [c for c in columns if c not in assigned.values()]
    for col in remaining_columns:
        alias_role = find_canonical(col)
        if alias_role is None or alias_role in assigned:
            continue
        assigned[alias_role] = col
        notes.append(f"{alias_role} = {col!r} (alias match)")

    # 3. Content-sniff for any required role still unassigned.
    unresolved_required = [r for r in ("user_id", "timestamp", "event_name") if r not in assigned]
    if unresolved_required:
        candidates_unused = [c for c in columns if c not in assigned.values()]
        guesses = _content_sniff(sample, candidates_unused)
        for role in unresolved_required:
            guessed = guesses.get(role)
            if guessed is None:
                continue
            assigned[role] = guessed
            notes.append(f"{role} = {guessed!r} (content-sniffed)")

    # 4. Validate required roles are all resolved.
    missing = [r for r in ("user_id", "timestamp", "event_name") if r not in assigned]
    if missing:
        raise SchemaError(
            "Could not identify required column(s): "
            + ", ".join(missing)
            + f". Available columns: {columns}. "
            f"Pass {' '.join(f'--{m.replace(chr(95), chr(45))}=COL' for m in missing)} to override."
        )

    canonical_cols = set(assigned.values())
    extras = tuple(c for c in columns if c not in canonical_cols)
    schema = ResolvedSchema(
        user_id=assigned["user_id"],
        timestamp=assigned["timestamp"],
        event_name=assigned["event_name"],
        session_id=assigned.get("session_id"),
        extras=extras,
    )
    return SniffedSchema(schema=schema, notes=tuple(notes))


def _content_sniff(sample: pl.DataFrame, candidates: list[str]) -> dict[str, str]:
    """For each unresolved required role, pick the best candidate column by content.

    Heuristics:
      - timestamp: parseable as ISO-8601 OR epoch seconds/millis on >=80% of non-null values.
      - user_id: high cardinality but not nearly unique; numeric or short string.
      - event_name: low cardinality categorical string.
    Each column is assigned to at most one role; first-priority role wins.
    """
    n = sample.height
    if n == 0:
        return {}

    scores: dict[str, dict[str, float]] = {}
    for col in candidates:
        s = sample.get_column(col).drop_nulls()
        if s.is_empty():
            continue
        scores[col] = {
            "timestamp": _timestamp_score(s),
            "user_id": _user_id_score(s, n),
            "event_name": _event_name_score(s, n),
        }

    chosen: dict[str, str] = {}
    used: set[str] = set()
    # Greedy: for each role, pick the column with highest score above threshold.
    for role, threshold in (("timestamp", 0.8), ("user_id", 0.5), ("event_name", 0.5)):
        best_col: str | None = None
        best_score: float = threshold
        for col, role_scores in scores.items():
            if col in used:
                continue
            score = role_scores[role]
            if score > best_score:
                best_score = score
                best_col = col
        if best_col is not None:
            chosen[role] = best_col
            used.add(best_col)
    return chosen


def _timestamp_score(s: pl.Series) -> float:
    n = s.len()
    if n == 0:
        return 0.0
    parsed = 0
    for v in s.head(SAMPLE_ROWS).to_list():
        if _is_parseable_timestamp(v):
            parsed += 1
    return parsed / min(n, SAMPLE_ROWS)


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")


def _is_parseable_timestamp(v: Any) -> bool:
    if isinstance(v, datetime):
        return True
    if isinstance(v, (int, float)):
        x = float(v)
        # Epoch seconds (~1.5e9 for 2017+) or millis (~1.5e12).
        return 1_000_000_000 < x < 4_000_000_000 or 1_000_000_000_000 < x < 4_000_000_000_000
    if isinstance(v, str):
        if _ISO_RE.match(v.strip()):
            return True
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return True
        except (ValueError, TypeError):
            return False
    return False


def _user_id_score(s: pl.Series, total_rows: int) -> float:
    """High score when cardinality is moderate-to-high but not equal to row count."""
    unique = s.n_unique()
    if unique <= 1:
        return 0.0
    ratio = unique / total_rows
    # Sweet spot: cardinality between ~1% and ~80% of row count.
    if 0.001 <= ratio <= 0.9:
        return 0.6 + 0.3 * min(ratio / 0.5, 1.0)
    return 0.0


def _event_name_score(s: pl.Series, total_rows: int) -> float:
    """Low-cardinality categorical string column."""
    if s.dtype not in (pl.Utf8, pl.String, pl.Categorical):
        return 0.0
    unique = s.n_unique()
    if unique == 0 or unique > 500:
        return 0.0
    ratio = unique / total_rows
    if ratio > 0.5:
        return 0.0
    # Prefer columns with 2-200 distinct values.
    if 2 <= unique <= 200:
        return 0.7
    return 0.3
