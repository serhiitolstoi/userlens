"""MCP server for userlens — exposes pipeline results as MCP tools."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from userlens.insights import extract_insights
from userlens.pipeline import PipelineOptions, run
from userlens.viewer import render

try:
    from mcp.server.fastmcp import FastMCP

    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False

# Blob list type alias for readability
_Blobs = list[dict[str, Any]]

# ---------------------------------------------------------------------------
# File cache: key = (resolved_path_str, mtime, size), max 3 entries (LRU-ish)
# ---------------------------------------------------------------------------
_CACHE: dict[tuple[str, float, int], tuple[_Blobs, dict[str, Any]]] = {}
_CACHE_ORDER: list[tuple[str, float, int]] = []
_CACHE_MAX = 3


def _load_file(file: str) -> tuple[_Blobs, dict[str, Any]]:
    """Load and cache pipeline results for *file*. Cache keyed by (path, mtime, size)."""
    path = Path(file).resolve()
    stat = path.stat()
    key = (str(path), stat.st_mtime, stat.st_size)

    if key in _CACHE:
        return _CACHE[key]

    result = run(PipelineOptions(events_path=path, max_users=None))
    blobs: _Blobs = result.blobs
    meta: dict[str, Any] = result.meta

    # Evict oldest entry if at capacity
    while len(_CACHE_ORDER) >= _CACHE_MAX:
        oldest = _CACHE_ORDER.pop(0)
        _CACHE.pop(oldest, None)

    _CACHE[key] = (blobs, meta)
    _CACHE_ORDER.append(key)
    return blobs, meta


# ---------------------------------------------------------------------------
# Attribute filter helper
# ---------------------------------------------------------------------------


def _apply_filters(blobs: _Blobs, filters_json: str) -> _Blobs:
    """Filter blobs by attribute key=value pairs from a JSON string."""
    try:
        filters: dict[str, str] = json.loads(filters_json) if filters_json.strip() else {}
    except json.JSONDecodeError:
        filters = {}
    if not filters:
        return blobs
    out: _Blobs = []
    for b in blobs:
        attrs: dict[str, Any] = b.get("attrs", {})
        if all(str(attrs.get(k, "")) == str(v) for k, v in filters.items()):
            out.append(b)
    return out


# ---------------------------------------------------------------------------
# Pure _impl functions (testable without MCP)
# ---------------------------------------------------------------------------


def list_users_impl(
    blobs: _Blobs,
    meta: dict[str, Any],
    limit: int = 50,
    sort_by: str = "events",
    filters: str = "{}",
) -> dict[str, Any]:
    """List users with summary stats."""
    filtered = _apply_filters(blobs, filters)
    insights_cache = {b["u"]: extract_insights(b, blobs) for b in blobs}

    def sort_key(b: dict[str, Any]) -> Any:
        if sort_by == "sessions":
            return b.get("sn", 0)
        if sort_by == "first_seen":
            return b.get("fs", "")
        if sort_by == "last_seen":
            return b.get("ls", "")
        return b.get("te", 0)  # default: events

    sorted_blobs = sorted(filtered, key=sort_key, reverse=sort_by not in ("first_seen",))
    page = sorted_blobs[:limit]

    users = []
    for b in page:
        uid: str = b["u"]
        ins: dict[str, Any] = insights_cache.get(uid, {})
        users.append(
            {
                "user_id": uid,
                "events": b.get("te", 0),
                "sessions": b.get("sn", 0),
                "first_seen": b.get("fs", ""),
                "last_seen": b.get("ls", ""),
                "attrs": b.get("attrs", {}),
                "power_score": ins.get("power_score", 0),
            }
        )

    return {
        "users": users,
        "total": len(blobs),
        "filtered_total": len(filtered),
    }


def analyze_user_impl(
    blobs: _Blobs,
    meta: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    """Full analysis of a single user."""
    blob = next((b for b in blobs if b["u"] == user_id), None)
    if blob is None:
        return {"error": f"User '{user_id}' not found"}

    insights = extract_insights(blob, blobs)

    # Expand compact session format
    sessions_expanded: list[dict[str, Any]] = []
    for s in blob.get("s", []):
        sid = s[0] if len(s) > 0 else ""
        ts = s[1] if len(s) > 1 else ""
        raw_events: list[Any] = s[2] if len(s) > 2 else []
        events_expanded: list[dict[str, Any]] = []
        for e in raw_events:
            hhmm: str = str(e[0]) if len(e) > 0 else ""
            name: str = str(e[1]) if len(e) > 1 else ""
            family: str = str(e[2]) if len(e) > 2 else ""
            # remaining elements are k1, v1, k2, v2 ...
            props: dict[str, Any] = {}
            extras: list[Any] = list(e[3:])
            for i in range(0, len(extras) - 1, 2):
                props[str(extras[i])] = extras[i + 1]
            events_expanded.append(
                {
                    "time": hhmm,
                    "name": name,
                    "family": family,
                    "props": props,
                }
            )
        sessions_expanded.append({"id": sid, "ts": ts, "events": events_expanded})

    # Top events by count
    event_counter: Counter[str] = Counter()
    family_of: dict[str, str] = {}
    for s in sessions_expanded:
        ev_list: list[dict[str, Any]] = s["events"]
        for e in ev_list:
            ev_name: str = e["name"]
            ev_family: str = e["family"]
            event_counter[ev_name] += 1
            family_of[ev_name] = ev_family

    top_events = [
        {"name": name, "count": cnt, "family": family_of.get(name, "")}
        for name, cnt in event_counter.most_common()
    ]

    return {
        "user_id": user_id,
        "attrs": blob.get("attrs", {}),
        "stats": {
            "events": blob.get("te", 0),
            "sessions": blob.get("sn", 0),
            "first_seen": blob.get("fs", ""),
            "last_seen": blob.get("ls", ""),
        },
        "insights": insights,
        "sessions": sessions_expanded,
        "top_events": top_events,
    }


def get_event_taxonomy_impl(
    blobs: _Blobs,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Return schema, family definitions, and top events from meta."""
    schema: dict[str, Any] = meta.get("schema", {})
    families_raw: dict[str, Any] = meta.get("families", {})
    top_events_raw: list[Any] = meta.get("topEvents", [])
    total_events = sum(b.get("te", 0) for b in blobs)
    total_users = len(blobs)

    # Compute pct for top events
    top_events = []
    for ev in top_events_raw:
        count: int = ev.get("count", 0)
        pct = round(count * 100 / total_events) if total_events > 0 else 0
        top_events.append(
            {
                "name": ev.get("name", ""),
                "count": count,
                "family": ev.get("family", ""),
                "pct": pct,
            }
        )

    # families: keep only color and label
    families: dict[str, dict[str, str]] = {}
    for fam, info in families_raw.items():
        families[fam] = {
            "color": info.get("color", ""),
            "label": info.get("label", fam),
        }

    return {
        "schema": schema,
        "families": families,
        "top_events": top_events,
        "total_events": total_events,
        "total_users": total_users,
    }


def summarize_cohort_impl(
    blobs: _Blobs,
    meta: dict[str, Any],
    filters: str = "{}",
) -> dict[str, Any]:
    """Cohort-level summary with optional attribute filters."""
    filtered = _apply_filters(blobs, filters)
    total_users = len(blobs)
    filtered_users = len(filtered)

    if not filtered:
        return {
            "total_users": total_users,
            "filtered_users": 0,
            "total_events": 0,
            "avg_events_per_user": 0,
            "median_sessions": 0,
            "top_events": [],
            "family_distribution": {},
            "power_users": [],
        }

    total_events = sum(b.get("te", 0) for b in filtered)
    avg_events = round(total_events / filtered_users, 1) if filtered_users else 0

    session_counts = sorted(b.get("sn", 0) for b in filtered)
    median_sessions = statistics.median(session_counts) if session_counts else 0

    event_counter: Counter[str] = Counter()
    family_dist: Counter[str] = Counter()
    for b in filtered:
        for s in b.get("s", []):
            events: list[Any] = s[2] if len(s) > 2 else []
            for e in events:
                if len(e) > 1:
                    event_counter[str(e[1])] += 1
                if len(e) > 2:
                    family_dist[str(e[2])] += 1

    top_events = [{"name": name, "count": cnt} for name, cnt in event_counter.most_common(20)]

    # Power users: top 10 by te*sn
    all_insights = {b["u"]: extract_insights(b, blobs) for b in filtered}
    power_users_sorted = sorted(
        filtered,
        key=lambda b: b.get("te", 0) * b.get("sn", 0),
        reverse=True,
    )[:10]
    power_users = [
        {
            "user_id": b["u"],
            "events": b.get("te", 0),
            "sessions": b.get("sn", 0),
            "power_score": all_insights[b["u"]].get("power_score", 0),
        }
        for b in power_users_sorted
    ]

    return {
        "total_users": total_users,
        "filtered_users": filtered_users,
        "total_events": total_events,
        "avg_events_per_user": avg_events,
        "median_sessions": median_sessions,
        "top_events": top_events,
        "family_distribution": dict(family_dist),
        "power_users": power_users,
    }


def export_html_impl(
    blobs: _Blobs,
    meta: dict[str, Any],
    output: str,
    user_ids: list[str] | None = None,
    filters: str = "{}",
) -> dict[str, Any]:
    """Render an HTML report for a selected subset of users.

    Filters are applied first, then user_ids (if provided) further restrict the set.
    """
    filtered = _apply_filters(blobs, filters)

    if user_ids:
        id_set = set(user_ids)
        filtered = [b for b in filtered if b["u"] in id_set]
        missing = id_set - {b["u"] for b in filtered}
        if missing:
            return {"error": f"User(s) not found: {sorted(missing)}"}

    if not filtered:
        return {"error": "No users matched the given filters/user_ids"}

    out_path = Path(output)
    render(filtered, meta, out_path, open_browser=False)

    return {
        "output": str(out_path.resolve()),
        "users_included": len(filtered),
        "user_ids": [b["u"] for b in filtered],
        "total_events": sum(b.get("te", 0) for b in filtered),
        "size_bytes": out_path.stat().st_size,
    }


def find_users_by_event_impl(
    blobs: _Blobs,
    meta: dict[str, Any],
    event_name: str,
    min_occurrences: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """Find users who triggered events matching a substring pattern."""
    pattern = event_name.lower()
    matched: list[dict[str, Any]] = []
    for b in blobs:
        occurrences = 0
        for s in b.get("s", []):
            events: list[Any] = s[2] if len(s) > 2 else []
            for e in events:
                if len(e) > 1 and pattern in str(e[1]).lower():
                    occurrences += 1
        if occurrences >= min_occurrences:
            matched.append(
                {"user_id": b["u"], "occurrences": occurrences, "attrs": b.get("attrs", {})}
            )

    matched.sort(key=lambda x: x["occurrences"], reverse=True)
    return {
        "pattern": event_name,
        "users": matched[:limit],
        "total_matched": len(matched),
    }


# ---------------------------------------------------------------------------
# MCP server wiring
# ---------------------------------------------------------------------------


def main_mcp(events_file: str | None = None) -> None:
    if not _MCP_AVAILABLE:
        raise ImportError(
            "mcp package not installed. Install with: pip install 'userlens[mcp]'"
        )

    mcp = FastMCP("userlens")

    @mcp.tool()
    def list_users(
        file: str,
        limit: int = 50,
        sort_by: str = "events",
        filters: str = "{}",
    ) -> dict[str, Any]:
        """List users from an events file with summary stats.

        Args:
            file: Path to events file (CSV/JSON/Parquet).
            limit: Max users to return (default 50).
            sort_by: Sort field — 'events', 'sessions', 'first_seen', 'last_seen'.
            filters: JSON string of attribute filters e.g. '{"user_plan": "pro"}'.
        """
        blobs, meta = _load_file(file)
        return list_users_impl(blobs, meta, limit=limit, sort_by=sort_by, filters=filters)

    @mcp.tool()
    def analyze_user(file: str, user_id: str) -> dict[str, Any]:
        """Full analysis of a single user: stats, insights, sessions, top events.

        Args:
            file: Path to events file.
            user_id: The user to analyze.
        """
        blobs, meta = _load_file(file)
        return analyze_user_impl(blobs, meta, user_id=user_id)

    @mcp.tool()
    def get_event_taxonomy(file: str) -> dict[str, Any]:
        """Return event schema, family definitions, and top events.

        Args:
            file: Path to events file.
        """
        blobs, meta = _load_file(file)
        return get_event_taxonomy_impl(blobs, meta)

    @mcp.tool()
    def summarize_cohort(file: str, filters: str = "{}") -> dict[str, Any]:
        """Cohort-level summary with optional attribute filters.

        Args:
            file: Path to events file.
            filters: JSON string of attribute filters e.g. '{"user_country": "US"}'.
        """
        blobs, meta = _load_file(file)
        return summarize_cohort_impl(blobs, meta, filters=filters)

    @mcp.tool()
    def find_users_by_event(
        file: str,
        event_name: str,
        min_occurrences: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Find users who triggered events matching a substring pattern (case-insensitive).

        Args:
            file: Path to events file.
            event_name: Substring to match against event names.
            min_occurrences: Minimum occurrences required (default 1).
            limit: Max users to return (default 20).
        """
        blobs, meta = _load_file(file)
        return find_users_by_event_impl(
            blobs, meta, event_name=event_name, min_occurrences=min_occurrences, limit=limit
        )

    @mcp.tool()
    def export_html(
        file: str,
        output: str = "report.html",
        user_ids: list[str] | None = None,
        filters: str = "{}",
    ) -> dict[str, Any]:
        """Generate a self-contained HTML report for a selected subset of users.

        Use this after list_users/analyze_user to build a focused HTML report.

        Args:
            file: Path to events file.
            output: Output HTML path (default 'report.html').
            user_ids: Optional list of specific user IDs to include.
            filters: Optional JSON attribute filters e.g. '{"user_plan": "pro"}'.
        """
        blobs, meta = _load_file(file)
        return export_html_impl(blobs, meta, output=output, user_ids=user_ids, filters=filters)

    mcp.run(transport="stdio")
