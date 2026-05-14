"""Classify extra DataFrame columns as user attributes or event properties.

User attribute heuristics (either condition sufficient):
  - Column name matches ^user_ or ^u_ prefix.
  - Values are constant per user_id AND global cardinality <= max_attr_cardinality.

Free-text columns (cardinality > 80% of rows) are silently skipped.
Everything else -> event property.
"""

from __future__ import annotations

import math
import re

import polars as pl

from userlens.schema.types import ResolvedSchema

_USER_PREFIX = re.compile(r"^(user_|u_)", re.IGNORECASE)


def classify_extras(
    df: pl.DataFrame,
    schema: ResolvedSchema,
) -> tuple[list[str], list[str]]:
    """Return (attr_cols, prop_cols) from schema.extras."""
    if not schema.extras:
        return [], []

    n_users = df.get_column("user_id").n_unique()
    max_card = min(50, int(math.sqrt(max(n_users, 1))) * 2 + 1)
    free_text_threshold = df.height * 0.8

    attr_cols: list[str] = []
    prop_cols: list[str] = []

    for col in schema.extras:
        series = df.get_column(col)
        n_unique = series.n_unique()

        if n_unique > free_text_threshold:
            continue  # skip free-text columns silently

        if _USER_PREFIX.match(col):
            attr_cols.append(col)
            continue

        # Constant-per-user check: every user has at most 1 distinct non-null value
        nunique_per_user = (
            df.select(["user_id", col])
            .group_by("user_id")
            .agg(pl.col(col).filter(pl.col(col).is_not_null()).n_unique().alias("n"))
            .get_column("n")
        )
        if bool((nunique_per_user <= 1).all()) and n_unique <= max_card:
            attr_cols.append(col)
        else:
            prop_cols.append(col)

    return attr_cols, prop_cols


def derive_attributes(
    df: pl.DataFrame,
    attr_cols: list[str],
) -> dict[str, dict[str, str]]:
    """Return {user_id: {col: value}} — first non-null value per user per attr."""
    if not attr_cols:
        return {}

    agg = df.group_by("user_id").agg([pl.col(c).drop_nulls().first().alias(c) for c in attr_cols])
    result: dict[str, dict[str, str]] = {}
    for row in agg.iter_rows(named=True):
        uid = str(row["user_id"])
        attrs = {c: str(row[c]) for c in attr_cols if row.get(c) is not None}
        if attrs:
            result[uid] = attrs
    return result


def build_attributes_meta(
    df: pl.DataFrame,
    attr_cols: list[str],
) -> list[dict[str, object]]:
    """Meta list for sidebar selects: [{key: "country", values: ["PL","UA"]}, ...]."""
    return [
        {
            "key": col,
            "values": [str(v) for v in df.get_column(col).drop_nulls().unique().sort().to_list()],
        }
        for col in attr_cols
    ]
