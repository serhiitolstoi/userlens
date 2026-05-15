from __future__ import annotations

import json
from pathlib import Path

from user_explorer.pipeline import PipelineOptions, run

FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOT_PATH = FIXTURES / "tiny_snapshot.json"


def test_tiny_runs_and_produces_blobs() -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    assert result.n_events == 20
    assert len(result.blobs) == 3

    user_ids = {b["u"] for b in result.blobs}
    assert user_ids == {"101", "102", "103"}

    by_user = {b["u"]: b for b in result.blobs}
    assert by_user["101"]["te"] == 7
    assert by_user["102"]["te"] == 9
    assert by_user["103"]["te"] == 4

    assert by_user["101"]["fs"] == "2026-04-01 09:00:00"
    assert by_user["101"]["ls"] == "2026-04-02 14:15:12"


def test_tiny_m2_blob_shape() -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    by_user = {b["u"]: b for b in result.blobs}

    blob101 = by_user["101"]
    assert "sn" in blob101
    assert "fc" in blob101
    assert "attrs" in blob101
    assert "s" in blob101

    # User 101: 3 sessions (09:00-09:01, 11:30, next-day 14:15)
    assert blob101["sn"] == 3

    # Events are in sessions, not flat
    first_session = blob101["s"][0]
    assert first_session[2][0][1] == "page_viewed"  # first event of first session
    assert first_session[2][0][2] == "view"  # family


def test_tiny_event_order_preserved() -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    by_user = {b["u"]: b for b in result.blobs}

    # User 102: first event in first session = page_viewed
    # last event in last session = checkout_completed
    sessions_102 = by_user["102"]["s"]
    assert sessions_102[0][2][0][1] == "page_viewed"
    assert sessions_102[-1][2][-1][1] == "checkout_completed"


def test_tiny_family_counts() -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    by_user = {b["u"]: b for b in result.blobs}

    fc_101 = by_user["101"]["fc"]
    # page_viewed(2), welcome_viewed(1), settings_opened(1) -> view=4? Let me check:
    # page_viewed x2, welcome_viewed x1, settings_opened x1 -> view family x4
    # signup_clicked x1 -> click x1
    # signup_submitted x1 -> submit x1
    # settings_closed x1 -> close x1
    assert fc_101.get("view", 0) == 4
    assert fc_101.get("click", 0) == 1
    assert fc_101.get("submit", 0) == 1
    assert fc_101.get("close", 0) == 1


def test_aliased_columns_resolve() -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "aliased.csv"))
    assert result.schema.user_id == "uid"
    assert result.schema.timestamp == "ts"
    assert result.schema.event_name == "event"
    assert len(result.blobs) == 2
    assert result.n_events == 5


def test_with_attrs_detects_user_attributes() -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "with_attrs.csv"))
    by_user = {b["u"]: b for b in result.blobs}

    assert by_user["201"]["attrs"].get("user_country") == "PL"
    assert by_user["201"]["attrs"].get("user_plan") == "premium"
    assert by_user["202"]["attrs"].get("user_country") == "UA"
    assert by_user["202"]["attrs"].get("user_plan") == "free"


def test_with_attrs_attribute_meta() -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "with_attrs.csv"))
    attr_keys = {m["key"] for m in result.meta["attributes"]}
    assert "user_country" in attr_keys
    assert "user_plan" in attr_keys


def test_meta_has_required_keys() -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    assert "schema" in result.meta
    assert "families" in result.meta
    assert "topEvents" in result.meta
    assert "generatedAt" in result.meta


def test_redact_cols_replaced() -> None:
    result = run(PipelineOptions(
        events_path=FIXTURES / "with_attrs.csv",
        redact_cols=("user_country",),
    ))
    by_user = {b["u"]: b for b in result.blobs}
    # user_country is a user attribute — should be redacted in attrs
    assert by_user["201"]["attrs"].get("user_country") == "<redacted>"
    assert by_user["202"]["attrs"].get("user_country") == "<redacted>"
    # user_plan not redacted
    assert by_user["201"]["attrs"].get("user_plan") == "premium"


def test_redact_unknown_col_is_noop() -> None:
    # Should not raise, just silently skip missing columns
    result = run(PipelineOptions(
        events_path=FIXTURES / "tiny.csv",
        redact_cols=("nonexistent_col",),
    ))
    assert len(result.blobs) == 3


def test_timezone_conversion() -> None:
    result_utc = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    result_tz = run(PipelineOptions(
        events_path=FIXTURES / "tiny.csv",
        timezone="Europe/Lisbon",
    ))
    # tiny.csv timestamps are in UTC; Europe/Lisbon is UTC+1 in summer
    # first session start should differ
    by_user_utc = {b["u"]: b for b in result_utc.blobs}
    by_user_tz = {b["u"]: b for b in result_tz.blobs}
    # With timezone applied, the displayed time differs from UTC
    # (exact offset depends on DST, but they should not be equal)
    assert by_user_utc["101"]["fs"] != by_user_tz["101"]["fs"]


def test_timezone_utc_no_change() -> None:
    # Applying UTC timezone to UTC data should produce the same display times
    result_default = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    result_utc = run(PipelineOptions(
        events_path=FIXTURES / "tiny.csv",
        timezone="UTC",
    ))
    by_default = {b["u"]: b for b in result_default.blobs}
    by_utc = {b["u"]: b for b in result_utc.blobs}
    assert by_default["101"]["fs"] == by_utc["101"]["fs"]


def test_golden_snapshot() -> None:
    """Pin the tiny.csv output shape. On first run writes the snapshot; on subsequent runs asserts equality."""
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    actual = json.dumps(result.blobs, sort_keys=True, indent=2, default=str)

    if not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.write_text(actual)
        return  # first run — snapshot written, test passes

    expected = SNAPSHOT_PATH.read_text()
    assert actual == expected, "Blob output changed — update snapshot if intentional"
