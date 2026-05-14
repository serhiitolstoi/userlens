"""Tests for MCP server _impl functions and file cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from userlens.mcp_server import (
    _load_file,
    analyze_user_impl,
    export_html_impl,
    find_users_by_event_impl,
    get_event_taxonomy_impl,
    list_users_impl,
    summarize_cohort_impl,
)

FIXTURES = Path(__file__).parent / "fixtures"
TINY = str(FIXTURES / "tiny.csv")
WITH_ATTRS = str(FIXTURES / "with_attrs.csv")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_tiny() -> tuple[list[dict], dict]:
    return _load_file(TINY)


def _load_with_attrs() -> tuple[list[dict], dict]:
    return _load_file(WITH_ATTRS)


# ---------------------------------------------------------------------------
# test_list_users_basic
# ---------------------------------------------------------------------------

def test_list_users_basic() -> None:
    blobs, meta = _load_tiny()
    result = list_users_impl(blobs, meta)
    assert result["total"] >= 1
    assert len(result["users"]) >= 1
    for u in result["users"]:
        assert "user_id" in u
        assert "events" in u
        assert "sessions" in u


# ---------------------------------------------------------------------------
# test_analyze_user
# ---------------------------------------------------------------------------

def test_analyze_user() -> None:
    blobs, meta = _load_tiny()
    user_id = blobs[0]["u"]
    result = analyze_user_impl(blobs, meta, user_id=user_id)
    assert result["user_id"] == user_id
    assert "insights" in result
    assert "sessions" in result
    assert isinstance(result["sessions"], list)
    assert len(result["sessions"]) > 0
    # Check session event expansion
    first_session = result["sessions"][0]
    assert "events" in first_session
    if first_session["events"]:
        ev = first_session["events"][0]
        assert "time" in ev
        assert "name" in ev
        assert "family" in ev
        assert "props" in ev


def test_analyze_user_not_found() -> None:
    blobs, meta = _load_tiny()
    result = analyze_user_impl(blobs, meta, user_id="NONEXISTENT_USER_99999")
    assert "error" in result


# ---------------------------------------------------------------------------
# test_taxonomy
# ---------------------------------------------------------------------------

def test_taxonomy() -> None:
    blobs, meta = _load_tiny()
    result = get_event_taxonomy_impl(blobs, meta)
    assert "schema" in result
    schema = result["schema"]
    # Schema must have user_id key
    assert "user_id" in schema
    assert len(result["top_events"]) > 0
    assert result["total_users"] == 3
    assert result["total_events"] == 20


# ---------------------------------------------------------------------------
# test_cache_hit
# ---------------------------------------------------------------------------

def test_cache_hit() -> None:
    """Two loads of the same file should return the same object (cached)."""
    blobs1, meta1 = _load_file(TINY)
    blobs2, meta2 = _load_file(TINY)
    assert blobs1 is blobs2
    assert meta1 is meta2


# ---------------------------------------------------------------------------
# test_find_by_event
# ---------------------------------------------------------------------------

def test_find_by_event() -> None:
    blobs, meta = _load_tiny()
    # "page_viewed" exists in tiny.csv for multiple users
    result = find_users_by_event_impl(blobs, meta, event_name="page_viewed")
    assert result["total_matched"] >= 1
    assert len(result["users"]) >= 1
    for u in result["users"]:
        assert "user_id" in u
        assert "occurrences" in u
        assert u["occurrences"] >= 1


def test_find_by_event_substring() -> None:
    blobs, meta = _load_tiny()
    # "checkout" appears in user 102's events
    result = find_users_by_event_impl(blobs, meta, event_name="checkout")
    assert result["total_matched"] >= 1
    user_ids = [u["user_id"] for u in result["users"]]
    assert "102" in user_ids


def test_find_by_event_case_insensitive() -> None:
    blobs, meta = _load_tiny()
    result_lower = find_users_by_event_impl(blobs, meta, event_name="page_viewed")
    result_upper = find_users_by_event_impl(blobs, meta, event_name="PAGE_VIEWED")
    assert result_lower["total_matched"] == result_upper["total_matched"]


# ---------------------------------------------------------------------------
# test_filters
# ---------------------------------------------------------------------------

def test_filters_by_attribute() -> None:
    blobs, meta = _load_with_attrs()
    # Filter to only premium plan users
    result = list_users_impl(blobs, meta, filters='{"user_plan": "premium"}')
    assert result["filtered_total"] >= 1
    for u in result["users"]:
        assert u["attrs"].get("user_plan") == "premium"


def test_filters_by_country() -> None:
    blobs, meta = _load_with_attrs()
    result = list_users_impl(blobs, meta, filters='{"user_country": "UA"}')
    assert result["filtered_total"] >= 1
    for u in result["users"]:
        assert u["attrs"].get("user_country") == "UA"


def test_filters_no_match() -> None:
    blobs, meta = _load_with_attrs()
    result = list_users_impl(blobs, meta, filters='{"user_plan": "enterprise"}')
    assert result["filtered_total"] == 0
    assert len(result["users"]) == 0


# ---------------------------------------------------------------------------
# test_summarize_cohort
# ---------------------------------------------------------------------------

def test_summarize_cohort_basic() -> None:
    blobs, meta = _load_tiny()
    result = summarize_cohort_impl(blobs, meta)
    assert result["total_users"] == 3
    assert result["filtered_users"] == 3
    assert result["total_events"] == 20
    assert result["avg_events_per_user"] > 0
    assert result["median_sessions"] > 0


def test_summarize_cohort_filtered() -> None:
    blobs, meta = _load_with_attrs()
    result = summarize_cohort_impl(blobs, meta, filters='{"user_plan": "free"}')
    assert result["filtered_users"] < result["total_users"]


# ---------------------------------------------------------------------------
# test_list_users_sort
# ---------------------------------------------------------------------------

def test_list_users_sort_by_sessions() -> None:
    blobs, meta = _load_tiny()
    result = list_users_impl(blobs, meta, sort_by="sessions")
    sessions = [u["sessions"] for u in result["users"]]
    assert sessions == sorted(sessions, reverse=True)


def test_list_users_limit() -> None:
    blobs, meta = _load_tiny()
    result = list_users_impl(blobs, meta, limit=2)
    assert len(result["users"]) <= 2
    assert result["total"] == 3


# ---------------------------------------------------------------------------
# test_export_html
# ---------------------------------------------------------------------------

def test_export_html_all_users(tmp_path: Path) -> None:
    blobs, meta = _load_tiny()
    out = str(tmp_path / "out.html")
    result = export_html_impl(blobs, meta, output=out)
    assert "error" not in result
    assert result["users_included"] == len(blobs)
    assert Path(out).exists()
    assert result["size_bytes"] > 1000


def test_export_html_subset(tmp_path: Path) -> None:
    blobs, meta = _load_tiny()
    first_uid = blobs[0]["u"]
    out = str(tmp_path / "subset.html")
    result = export_html_impl(blobs, meta, output=out, user_ids=[first_uid])
    assert "error" not in result
    assert result["users_included"] == 1
    assert result["user_ids"] == [first_uid]
    # HTML should contain the user_id string
    html = Path(out).read_text()
    assert first_uid in html


def test_export_html_missing_user(tmp_path: Path) -> None:
    blobs, meta = _load_tiny()
    out = str(tmp_path / "miss.html")
    result = export_html_impl(blobs, meta, output=out, user_ids=["nonexistent_user"])
    assert "error" in result


def test_export_html_with_filter(tmp_path: Path) -> None:
    blobs, meta = _load_file(WITH_ATTRS)
    out = str(tmp_path / "filtered.html")
    # with_attrs.csv has user_country column — pick the first user's country as filter
    first_country = blobs[0]["attrs"].get("user_country", "")
    if not first_country:
        pytest.skip("no user_country in with_attrs fixture")
    result = export_html_impl(blobs, meta, output=out,
                              filters=f'{{"user_country": "{first_country}"}}')
    assert "error" not in result
    assert result["users_included"] >= 1
