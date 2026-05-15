"""Per-event property extraction helper."""

from __future__ import annotations

from typing import Any


def extract_event_props(row: dict[str, Any], prop_cols: list[str]) -> list[Any]:
    """Flatten prop_cols values from row into [key, val, key, val, ...] pairs.

    Skips None values.
    """
    out: list[Any] = []
    for col in prop_cols:
        v = row.get(col)
        if v is not None:
            out.extend([col, str(v)])
    return out
