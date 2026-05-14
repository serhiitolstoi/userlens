from __future__ import annotations

import polars as pl
import pytest

from userlens.schema import sniff_schema
from userlens.schema.sniff import SchemaError


def test_canonical_columns_resolved_by_alias() -> None:
    df = pl.DataFrame(
        {
            "user_id": ["1", "2"],
            "timestamp": ["2026-04-01 09:00:00", "2026-04-01 10:00:00"],
            "event_name": ["view", "click"],
        }
    )
    sniffed = sniff_schema(df)
    assert sniffed.schema.user_id == "user_id"
    assert sniffed.schema.timestamp == "timestamp"
    assert sniffed.schema.event_name == "event_name"
    assert sniffed.schema.session_id is None


def test_aliases_resolved() -> None:
    df = pl.DataFrame(
        {
            "uid": ["1", "2"],
            "ts": ["2026-04-01 09:00:00", "2026-04-01 10:00:00"],
            "event": ["view", "click"],
        }
    )
    sniffed = sniff_schema(df)
    assert sniffed.schema.user_id == "uid"
    assert sniffed.schema.timestamp == "ts"
    assert sniffed.schema.event_name == "event"


def test_session_id_alias_detected() -> None:
    df = pl.DataFrame(
        {
            "user_id": ["1"],
            "timestamp": ["2026-04-01 09:00:00"],
            "event_name": ["view"],
            "sid": ["abc"],
        }
    )
    sniffed = sniff_schema(df)
    assert sniffed.schema.session_id == "sid"


def test_explicit_override_wins() -> None:
    df = pl.DataFrame(
        {
            "user_id": ["1"],
            "actor_id": ["A"],  # would also match user_id alias
            "timestamp": ["2026-04-01 09:00:00"],
            "event_name": ["view"],
        }
    )
    sniffed = sniff_schema(df, user_id_override="actor_id")
    assert sniffed.schema.user_id == "actor_id"


def test_override_to_missing_column_raises() -> None:
    df = pl.DataFrame(
        {
            "user_id": ["1"],
            "timestamp": ["2026-04-01 09:00:00"],
            "event_name": ["view"],
        }
    )
    with pytest.raises(SchemaError, match="not found"):
        sniff_schema(df, user_id_override="nope")


def test_missing_required_raises() -> None:
    df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    with pytest.raises(SchemaError, match="Could not identify"):
        sniff_schema(df)


def test_extras_carried_through() -> None:
    df = pl.DataFrame(
        {
            "user_id": ["1"],
            "timestamp": ["2026-04-01 09:00:00"],
            "event_name": ["view"],
            "user_country": ["PL"],
            "page_url": ["/home"],
        }
    )
    sniffed = sniff_schema(df)
    assert set(sniffed.schema.extras) == {"user_country", "page_url"}
