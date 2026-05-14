from __future__ import annotations

from pathlib import Path

import polars as pl

from userlens.derive.sessions import derive_sessions
from userlens.pipeline import PipelineOptions, run
from userlens.schema.types import ResolvedSchema

FIXTURES = Path(__file__).parent / "fixtures"


def _minimal_schema() -> ResolvedSchema:
    return ResolvedSchema(user_id="user_id", timestamp="timestamp", event_name="event_name")


def _make_df(rows: list[tuple[str, str, str]]) -> pl.DataFrame:
    df = pl.DataFrame(
        {
            "user_id": [r[0] for r in rows],
            "timestamp": [r[1] for r in rows],
            "event_name": [r[2] for r in rows],
        }
    )
    return df.with_columns(pl.col("timestamp").str.to_datetime(time_unit="us")).sort(
        ["user_id", "timestamp"]
    )


def test_single_session_when_gap_below_threshold() -> None:
    df = _make_df(
        [
            ("u1", "2026-04-01 10:00:00", "page_viewed"),
            ("u1", "2026-04-01 10:10:00", "item_clicked"),
            ("u1", "2026-04-01 10:20:00", "checkout_started"),
        ]
    )
    assignment = {"page_viewed": "view", "item_clicked": "click", "checkout_started": "start"}
    sessions = derive_sessions(df, _minimal_schema(), assignment, [])
    assert len(sessions["u1"]) == 1
    assert len(sessions["u1"][0][2]) == 3  # 3 events in one session


def test_gap_splits_into_two_sessions() -> None:
    df = _make_df(
        [
            ("u1", "2026-04-01 10:00:00", "page_viewed"),
            ("u1", "2026-04-01 10:31:00", "item_clicked"),  # 31-min gap -> new session
        ]
    )
    assignment = {"page_viewed": "view", "item_clicked": "click"}
    sessions = derive_sessions(df, _minimal_schema(), assignment, [], session_gap_minutes=30)
    assert len(sessions["u1"]) == 2
    assert sessions["u1"][0][2][0][1] == "page_viewed"
    assert sessions["u1"][1][2][0][1] == "item_clicked"


def test_exact_gap_does_not_split() -> None:
    df = _make_df(
        [
            ("u1", "2026-04-01 10:00:00", "page_viewed"),
            ("u1", "2026-04-01 10:30:00", "item_clicked"),  # exactly 30 min -> same session
        ]
    )
    assignment = {"page_viewed": "view", "item_clicked": "click"}
    sessions = derive_sessions(df, _minimal_schema(), assignment, [], session_gap_minutes=30)
    assert len(sessions["u1"]) == 1


def test_session_ids_are_stable_and_unique() -> None:
    df = _make_df(
        [
            ("u1", "2026-04-01 10:00:00", "a"),
            ("u1", "2026-04-01 11:00:00", "b"),
            ("u1", "2026-04-01 12:00:00", "c"),
        ]
    )
    assignment = {"a": "other", "b": "other", "c": "other"}
    sessions = derive_sessions(df, _minimal_schema(), assignment, [])
    sids = [s[0] for s in sessions["u1"]]
    assert len(set(sids)) == len(sids)  # all unique
    assert all(sid.startswith("u1_s") for sid in sids)


def test_with_attrs_fixture_produces_two_sessions_for_user202() -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "with_attrs.csv"))
    by_user = {b["u"]: b for b in result.blobs}
    # user 202: gap at 11:01 -> 11:35 = 34 min > 30 -> 2 sessions
    assert by_user["202"]["sn"] == 2
    # user 201: all events within 3 minutes -> 1 session
    assert by_user["201"]["sn"] == 1


def test_event_hhmm_format_in_session() -> None:
    df = _make_df([("u1", "2026-04-01 09:05:00", "page_viewed")])
    assignment = {"page_viewed": "view"}
    sessions = derive_sessions(df, _minimal_schema(), assignment, [])
    hhmm = sessions["u1"][0][2][0][0]
    assert hhmm == "09:05"
