"""Orchestrator: events file -> per-user blobs -> meta.

Pipeline steps:
  1. Read      — load file into DataFrame
  2. Sniff     — resolve column schema from aliases / content
  3. Normalize — canonical column names, cast types, sort
  4. Classify  — split extra columns into user attrs vs event props
  5. Families  — two-pass event family detection
  6. Sessions  — gap-based or column-based session derivation
  7. Attributes— per-user attribute dicts
  8. Blobs     — assemble one dict per user (M2 shape)
  9. Meta      — top-level meta blob for the HTML viewer (M3)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from userlens.derive import (
    build_attributes_meta,
    classify_extras,
    derive_attributes,
    derive_families,
    derive_sessions,
)
from userlens.io import read_events
from userlens.io.reader import sample_for_sniff
from userlens.schema import sniff_schema
from userlens.schema.types import ResolvedSchema
from userlens.transform import build_user_blobs, normalize_dataframe


@dataclass(frozen=True)
class PipelineOptions:
    events_path: Path
    user_id_override: str | None = None
    timestamp_override: str | None = None
    event_name_override: str | None = None
    max_users: int | None = 5000
    session_gap_minutes: int = 30
    no_families: bool = False


@dataclass(frozen=True)
class PipelineResult:
    schema: ResolvedSchema
    schema_notes: tuple[str, ...]
    blobs: list[dict[str, Any]]
    meta: dict[str, Any]
    elapsed_ms: int
    n_events: int
    n_sessions: int


def run(options: PipelineOptions) -> PipelineResult:
    start = time.monotonic()

    df = read_events(options.events_path)
    sample = sample_for_sniff(df)
    sniffed = sniff_schema(
        sample,
        user_id_override=options.user_id_override,
        timestamp_override=options.timestamp_override,
        event_name_override=options.event_name_override,
    )

    normalized = normalize_dataframe(df, sniffed.schema)

    # M2: derive enrichment
    attr_cols, prop_cols = classify_extras(normalized, sniffed.schema)
    family_assignment, family_registry = derive_families(
        normalized.get_column("event_name"),
        no_families=options.no_families,
    )
    sessions_by_user = derive_sessions(
        normalized,
        sniffed.schema,
        family_assignment,
        prop_cols,
        session_gap_minutes=options.session_gap_minutes,
    )
    attrs_by_user = derive_attributes(normalized, attr_cols)
    attrs_meta = build_attributes_meta(normalized, attr_cols)

    blobs = build_user_blobs(
        normalized,
        sniffed.schema,
        max_users=options.max_users,
        sessions_by_user=sessions_by_user,
        family_assignment=family_assignment,
        attrs_by_user=attrs_by_user,
    )

    # Top events by count (for meta / M3 sidebar)
    top_events = _build_top_events(normalized, family_assignment)

    meta: dict[str, Any] = {
        "schema": sniffed.schema.as_mapping(),
        "attributes": attrs_meta,
        "families": {
            fam: {"color": info.color, "bg": info.bg, "fg": info.fg, "label": info.label}
            for fam, info in family_registry.items()
        },
        "topEvents": top_events,
        "generatedAt": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    n_sessions = sum(b["sn"] for b in blobs)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return PipelineResult(
        schema=sniffed.schema,
        schema_notes=sniffed.notes,
        blobs=blobs,
        meta=meta,
        elapsed_ms=elapsed_ms,
        n_events=normalized.height,
        n_sessions=n_sessions,
    )


def _build_top_events(
    df: pl.DataFrame,
    family_assignment: dict[str, str],
    top_n: int = 50,
) -> list[dict[str, Any]]:
    counts = df.get_column("event_name").value_counts(sort=True).head(top_n)
    result = []
    for row in counts.iter_rows():
        name, count = str(row[0]), int(row[1])
        result.append(
            {
                "name": name,
                "count": count,
                "family": family_assignment.get(name, "other"),
            }
        )
    return result
