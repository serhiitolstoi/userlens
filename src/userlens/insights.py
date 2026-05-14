"""Deterministic insight extractors on a single blob dict. No LLM — pure logic."""

from __future__ import annotations

from datetime import date, datetime
from itertools import groupby
from typing import Any

TODAY = date(2026, 5, 14)


def extract_insights(blob: dict[str, Any], all_blobs: list[dict[str, Any]]) -> dict[str, Any]:
    """Return structured insight fields for a user."""
    # --- days_since_last ---
    ls_str: str = blob.get("ls", "")
    try:
        ls_date = datetime.strptime(ls_str[:10], "%Y-%m-%d").date()
        days_since_last = (TODAY - ls_date).days
    except (ValueError, TypeError):
        days_since_last = -1

    # --- first_seen / last_seen (date only) ---
    fs_str: str = blob.get("fs", "")
    first_seen = fs_str[:10] if fs_str else ""
    last_seen = ls_str[:10] if ls_str else ""

    # --- longest_gap_days ---
    sessions: list[Any] = blob.get("s", [])
    longest_gap_days = _compute_longest_gap(sessions)

    # --- power_score (0-100 percentile of te*sn) ---
    power_score = _compute_power_score(blob, all_blobs)

    # --- top_families ---
    fc: dict[str, int] = blob.get("fc", {})
    te: int = blob.get("te", 0)
    sorted_families = sorted(fc.items(), key=lambda x: x[1], reverse=True)
    top_families: list[dict[str, Any]] = [
        {
            "family": fam,
            "count": cnt,
            "pct": round(cnt * 100 / te) if te > 0 else 0,
        }
        for fam, cnt in sorted_families[:3]
    ]

    # --- stuck_signals ---
    stuck_signals = _compute_stuck_signals(sessions)

    # --- family_first_seen ---
    family_first_seen = _compute_family_first_seen(sessions)

    return {
        "power_score": power_score,
        "days_since_last": days_since_last,
        "longest_gap_days": longest_gap_days,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "top_families": top_families,
        "stuck_signals": stuck_signals,
        "family_first_seen": family_first_seen,
    }


def _compute_longest_gap(sessions: list[Any]) -> int:
    """Max gap in days between consecutive session timestamps."""
    if len(sessions) < 2:
        return 0
    timestamps = []
    for s in sessions:
        ts_str = s[1] if len(s) > 1 else ""
        try:
            ts = datetime.strptime(str(ts_str)[:19], "%Y-%m-%d %H:%M:%S")
            timestamps.append(ts)
        except (ValueError, TypeError):
            continue
    timestamps.sort()
    if len(timestamps) < 2:
        return 0
    max_gap = 0
    for i in range(1, len(timestamps)):
        gap = (timestamps[i] - timestamps[i - 1]).days
        max_gap = max(max_gap, gap)
    return max_gap


def _compute_power_score(blob: dict[str, Any], all_blobs: list[dict[str, Any]]) -> int:
    """0-100 percentile of te*sn among all_blobs."""
    if not all_blobs:
        return 0
    user_score = blob.get("te", 0) * blob.get("sn", 0)
    scores = [b.get("te", 0) * b.get("sn", 0) for b in all_blobs]
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    rank = sum(1 for s in scores_sorted if s < user_score)
    # percentile: fraction of users with strictly lower score
    percentile = round(rank * 100 / n) if n > 0 else 0
    return min(100, percentile)


def _compute_stuck_signals(sessions: list[Any]) -> list[dict[str, Any]]:
    """Find >=3 consecutive identical event names in any session."""
    results: list[dict[str, Any]] = []
    for s in sessions:
        session_id = s[0] if len(s) > 0 else ""
        events = s[2] if len(s) > 2 else []
        event_names = [e[1] for e in events if len(e) > 1]
        for event_name, group in groupby(event_names):
            count = sum(1 for _ in group)
            if count >= 3:
                results.append(
                    {
                        "session": str(session_id),
                        "event": str(event_name),
                        "count": count,
                    }
                )
    return results


def _compute_family_first_seen(sessions: list[Any]) -> dict[str, str]:
    """First timestamp each family appears, combining session ts + hh:mm offset."""
    family_first: dict[str, str] = {}
    for s in sessions:
        if len(s) < 3:
            continue
        session_ts_str = str(s[1])[:10]  # date portion: YYYY-MM-DD
        events = s[2]
        for e in events:
            if len(e) < 3:
                continue
            hhmm = str(e[0])  # "HH:MM"
            family = str(e[2])
            combined = f"{session_ts_str} {hhmm}"
            if family not in family_first or combined < family_first[family]:
                family_first[family] = combined
    return family_first
