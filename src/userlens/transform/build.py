"""Normalize the events DataFrame and build per-user blobs.

M1 blobs are minimal (identity, totals, flat event list).
M2 enriches by passing sessions_by_user, family_assignment, and attrs_by_user.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from userlens.schema.types import ResolvedSchema


def normalize_dataframe(df: pl.DataFrame, schema: ResolvedSchema) -> pl.DataFrame:
    """Rename canonical columns to their canonical names; cast types where needed."""
    renames: dict[str, str] = {}
    if schema.user_id != "user_id":
        renames[schema.user_id] = "user_id"
    if schema.timestamp != "timestamp":
        renames[schema.timestamp] = "timestamp"
    if schema.event_name != "event_name":
        renames[schema.event_name] = "event_name"
    if schema.session_id and schema.session_id != "session_id":
        renames[schema.session_id] = "session_id"

    out = df.rename(renames) if renames else df

    # Cast user_id to string for stable JSON keys.
    out = out.with_columns(pl.col("user_id").cast(pl.Utf8))

    # Parse timestamps if they're strings; leave datetime/int alone.
    ts_dtype = out.schema["timestamp"]
    if ts_dtype in (pl.Utf8, pl.String):
        out = out.with_columns(pl.col("timestamp").str.to_datetime(strict=False, time_unit="us"))
    elif ts_dtype.is_integer():
        # Epoch seconds vs millis: infer from magnitude.
        max_val = out.get_column("timestamp").max()
        if isinstance(max_val, (int, float)) and max_val > 1e12:
            out = out.with_columns(pl.from_epoch("timestamp", time_unit="ms"))
        else:
            out = out.with_columns(pl.from_epoch("timestamp", time_unit="s"))

    out = out.sort(["user_id", "timestamp"])
    return out


def build_user_blobs(
    df: pl.DataFrame,
    schema: ResolvedSchema,
    *,
    max_users: int | None = None,
    sessions_by_user: dict[str, list[list[Any]]] | None = None,
    family_assignment: dict[str, str] | None = None,
    attrs_by_user: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Produce one blob per user.

    When sessions_by_user and family_assignment are provided (M2+), the blob
    includes sn, fc, attrs, and s. Otherwise falls back to M1 flat events list.
    """
    user_ids = df.get_column("user_id").unique().sort()
    if max_users is not None and user_ids.len() > max_users:
        user_ids = user_ids.head(max_users)
    keep = user_ids.to_list()

    df_filtered = df.filter(pl.col("user_id").is_in(keep))

    if sessions_by_user is not None and family_assignment is not None:
        grouped = (
            df_filtered.group_by("user_id", maintain_order=True)
            .agg(
                pl.len().alias("te"),
                pl.col("timestamp").min().alias("fs"),
                pl.col("timestamp").max().alias("ls"),
                pl.col("event_name").alias("en_list"),
            )
            .sort("user_id")
        )
        blobs: list[dict[str, Any]] = []
        for row in grouped.iter_rows(named=True):
            uid = str(row["user_id"])
            sessions = sessions_by_user.get(uid, [])
            fc: dict[str, int] = {}
            for en in row["en_list"]:
                fam = family_assignment.get(str(en), "other")
                fc[fam] = fc.get(fam, 0) + 1
            blobs.append(
                {
                    "u": uid,
                    "te": int(row["te"]),
                    "sn": len(sessions),
                    "fs": _fmt_ts(row["fs"]),
                    "ls": _fmt_ts(row["ls"]),
                    "fc": fc,
                    "attrs": (attrs_by_user or {}).get(uid, {}),
                    "s": sessions,
                }
            )
        return blobs

    # M1 fallback: flat event list
    grouped_m1 = (
        df_filtered.group_by("user_id", maintain_order=True)
        .agg(
            pl.len().alias("te"),
            pl.col("timestamp").min().alias("fs"),
            pl.col("timestamp").max().alias("ls"),
            pl.col("timestamp").alias("ts_list"),
            pl.col("event_name").alias("en_list"),
        )
        .sort("user_id")
    )
    blobs_m1: list[dict[str, Any]] = []
    for row in grouped_m1.iter_rows(named=True):
        events = [[_fmt_ts(t), str(e)] for t, e in zip(row["ts_list"], row["en_list"], strict=True)]
        blobs_m1.append(
            {
                "u": str(row["user_id"]),
                "te": int(row["te"]),
                "fs": _fmt_ts(row["fs"]),
                "ls": _fmt_ts(row["ls"]),
                "events": events,
            }
        )
    return blobs_m1


def _fmt_ts(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return str(value.strftime("%Y-%m-%d %H:%M:%S"))
    return str(value)
