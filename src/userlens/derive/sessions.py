"""Session derivation.

If schema.session_id column is present, trust it.
Otherwise split on gap > session_gap_minutes between consecutive events per user.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import polars as pl

from userlens.derive.properties import extract_event_props
from userlens.schema.types import ResolvedSchema


def derive_sessions(
    df: pl.DataFrame,
    schema: ResolvedSchema,
    family_assignment: dict[str, str],
    prop_cols: list[str],
    *,
    session_gap_minutes: int = 30,
) -> dict[str, list[list[Any]]]:
    """Return {user_id: [[session_id, ts_str, [[hh:mm, name, family, *props], ...]], ...]}.

    Sessions within each user are ordered by first-event timestamp.
    """
    gap = timedelta(minutes=session_gap_minutes)
    result: dict[str, list[list[Any]]] = {}

    for group in df.partition_by("user_id", maintain_order=True):
        user_id = str(group["user_id"][0])
        sessions: list[list[Any]] = []
        current: list[Any] | None = None
        last_ts: Any = None
        counter = 0

        for row in group.iter_rows(named=True):
            ts = row["timestamp"]
            name = str(row["event_name"])
            family = family_assignment.get(name, "other")
            event_entry: list[Any] = [_fmt_hhmm(ts), name, family]
            event_entry.extend(extract_event_props(row, prop_cols))

            if schema.session_id:
                sid = str(row.get(schema.session_id) or "")
                if current is None or current[0] != sid:
                    current = [sid, _fmt_ts(ts), []]
                    sessions.append(current)
                current[2].append(event_entry)
            else:
                new_session = current is None or (last_ts is not None and (ts - last_ts) > gap)
                if new_session:
                    counter += 1
                    current = [f"{user_id}_s{counter}", _fmt_ts(ts), []]
                    sessions.append(current)
                current[2].append(event_entry)  # type: ignore[index]
            last_ts = ts

        result[user_id] = sessions

    return result


def _fmt_ts(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return str(value.strftime("%Y-%m-%d %H:%M:%S"))
    return str(value)


def _fmt_hhmm(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return str(value.strftime("%H:%M"))
    s = str(value)
    return s[11:16] if len(s) >= 16 else s
