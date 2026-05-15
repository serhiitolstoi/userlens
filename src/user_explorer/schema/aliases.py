"""Canonical column aliases. Matched case-insensitively."""

ALIASES: dict[str, frozenset[str]] = {
    "user_id": frozenset(
        {
            "user_id",
            "userid",
            "uid",
            "user",
            "u",
            "customer_id",
            "customerid",
            "actor_id",
            "actorid",
            "distinct_id",
            "distinctid",
            "anonymous_id",
            "anonymousid",
            "person_id",
            "personid",
        }
    ),
    "timestamp": frozenset(
        {
            "timestamp",
            "ts",
            "time",
            "datetime",
            "event_time",
            "eventtime",
            "occurred_at",
            "occurredat",
            "created_at",
            "createdat",
            "happened_at",
            "happenedat",
            "_time",
        }
    ),
    "event_name": frozenset(
        {
            "event_name",
            "eventname",
            "event",
            "name",
            "action",
            "type",
            "event_type",
            "eventtype",
            "track",
            "trackname",
        }
    ),
    "session_id": frozenset(
        {
            "session_id",
            "sessionid",
            "sid",
            "session",
            "sess_id",
            "sessid",
        }
    ),
}


def find_canonical(header: str) -> str | None:
    """Return the canonical column name (user_id / timestamp / event_name / session_id)
    that this header is an alias for. Case-insensitive. None if no match."""
    needle = header.strip().lower()
    for canonical, aliases in ALIASES.items():
        if needle in aliases:
            return canonical
    return None
