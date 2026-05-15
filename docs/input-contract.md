# Input Contract

User Explorer accepts a single flat event log. One row = one event.

## Supported formats

| Extension | Notes |
|-----------|-------|
| `.csv` | Standard comma-separated, UTF-8 |
| `.parquet` | Requires `pip install user-explorer[parquet]` |
| `.json` | Array of objects (`[{...}, ...]`) |
| `.jsonl` / `.ndjson` | One JSON object per line |

## Required columns

Three columns must be present (or resolvable via aliases):

| Canonical name | Recognized aliases |
|----------------|--------------------|
| `user_id` | uid, userId, user, u, customer_id, actor_id, distinct_id, anonymous_id |
| `timestamp` | ts, time, datetime, event_time, occurred_at, created_at, _time |
| `event_name` | event, name, action, type, event_type, track |

Alias matching is case-insensitive. If a column name is ambiguous or absent, User Explorer exits with code 2 and suggests the appropriate override flag.

### Explicit overrides

```
user-explorer events.csv --user-id uid --timestamp created_at --event-name action
```

## Optional columns

### session_id

| Canonical name | Recognized aliases |
|----------------|--------------------|
| `session_id` | sid, session, sess_id |

If present, User Explorer trusts it directly. If absent, sessions are derived by splitting on gaps larger than `--session-gap` minutes (default: 30).

### User attributes

Any column that is:
- Named with a `user_` or `u_` prefix, **or**
- Constant per `user_id` **and** has global cardinality ≤ min(50, √n_users × 2)

…becomes a user attribute. Attributes appear as `<select>` filter dropdowns in the sidebar and as chips in the per-user card.

Examples: `user_country`, `user_plan`, `u_segment`, `plan` (if constant per user).

### Event properties

Every other column that isn't classified as a user attribute becomes an event property. Properties appear as inline `key:value` chips in the timeline row.

Columns with cardinality ≈ n_rows (e.g., a UUID per event) are skipped with a warning — they would clutter every chip without analytical value.

## Timestamp formats

Auto-detected in this order:
1. ISO 8601 strings: `2024-03-15T14:22:00`, `2024-03-15 14:22:00`, `2024-03-15`
2. Unix epoch seconds (detected by magnitude: values < 2×10¹⁰)
3. Unix epoch milliseconds (values ≥ 2×10¹⁰)

All timestamps are treated as UTC-naive. Mixed-timezone strings are parsed as-is with a warning. Use `--tz` (v1.1) for explicit timezone handling.

## Schema resolution output

User Explorer always prints the resolved schema before processing:

```
schema: user_id=uid  timestamp=created_at  event_name=action  session_id=(none)
```

Exit code 2 on ambiguity, with a precise suggestion:
```
Error: could not resolve timestamp column. Candidates: created_at, updated_at
Hint: pass --timestamp created_at
```

## Limits and warnings

| Limit | Default | Override |
|-------|---------|---------|
| Max users | 5,000 | `--max-users N` |
| Max timeline events per user | 500 (show-more expander) | — |
| Max families | 12 (overflow → `other`) | `--no-families` |
| Max event property value length | 200 chars (truncated at ingest) | — |

## Privacy note

User Explorer embeds all event properties verbatim in the output HTML. The tool prints a reminder on every run:

```
Note: output contains all event properties. Inspect before sharing.
```

`--redact COL [COL ...]` (v1.1) replaces named property values with `<redacted>` before serialization.
