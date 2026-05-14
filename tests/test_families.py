from __future__ import annotations

import polars as pl

from userlens.derive.families import derive_families


def _series(names: list[str]) -> pl.Series:
    return pl.Series("event_name", names)


def test_verb_suffix_assignments() -> None:
    s = _series(["page_viewed", "signup_clicked", "signup_submitted", "settings_closed"])
    assignment, registry = derive_families(s)
    assert assignment["page_viewed"] == "view"
    assert assignment["signup_clicked"] == "click"
    assert assignment["signup_submitted"] == "submit"
    assert assignment["settings_closed"] == "close"


def test_error_start_families() -> None:
    s = _series(["checkout_failed", "payment_started", "payment_succeeded"])
    assignment, _ = derive_families(s)
    assert assignment["checkout_failed"] == "error"
    assert assignment["payment_started"] == "start"
    assert assignment["payment_succeeded"] == "success"


def test_prefix_clustering_fires_with_enough_distinct_names() -> None:
    # 4 distinct names sharing "ai_" prefix, covers all events -> should cluster
    names = ["ai_reply", "ai_draft", "ai_retry", "ai_send"] * 10
    assignment, registry = derive_families(_series(names))
    assert all(assignment[n] == "ai" for n in ["ai_reply", "ai_draft", "ai_retry", "ai_send"])
    assert "ai" in registry


def test_prefix_clustering_skipped_below_minimum_distinct() -> None:
    # Only 2 distinct names with same prefix -> below PREFIX_MIN_DISTINCT=3
    names = ["ai_reply", "ai_draft"] * 10
    assignment, _ = derive_families(_series(names))
    # Neither matches verb suffix; prefix has only 2 distinct -> "other"
    assert assignment["ai_reply"] == "other"
    assert assignment["ai_draft"] == "other"


def test_no_families_flag() -> None:
    s = _series(["page_viewed", "item_clicked"])
    assignment, registry = derive_families(s, no_families=True)
    assert all(v == "other" for v in assignment.values())
    assert list(registry.keys()) == ["other"]


def test_hash_stable_colors() -> None:
    s = _series(["page_viewed", "item_clicked"])
    _, reg1 = derive_families(s)
    _, reg2 = derive_families(s)
    assert reg1["view"].color == reg2["view"].color
    assert reg1["click"].color == reg2["click"].color


def test_unknown_events_go_to_other() -> None:
    s = _series(["some_random_action", "another_weird_one"])
    assignment, registry = derive_families(s)
    assert assignment["some_random_action"] == "other"
    assert "other" in registry
