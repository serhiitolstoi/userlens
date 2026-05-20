# Agent Usage

User Explorer is designed to be called from AI agents (Claude Code, Cursor, internal tools).

## Machine-readable output

Pass `--no-open --quiet` to suppress browser launch and emit a single JSON line to stdout:

```
$ user-explorer events.csv --no-open --quiet
{"out":"userexplorer.html","users":91,"events":12480,"sessions":520,"schema":{"user_id":"user_id","timestamp":"ts","event_name":"event"},"elapsed_ms":1340}
```

The line is always valid JSON. Parse it with any JSON library.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `out` | string | Absolute path to the rendered HTML file |
| `users` | int | Number of unique users in the output |
| `events` | int | Total event count after deduplication |
| `sessions` | int | Total session count |
| `schema` | object | Resolved column mapping (`canonical → actual_col`) |
| `elapsed_ms` | int | Wall-clock time for the full pipeline |

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Unexpected error |
| `2` | Schema error (column not found or ambiguous) |
| `3` | Empty file (zero rows after parsing) |

## Recommended invocation pattern

```python
import json
import subprocess

result = subprocess.run(
    ["user-explorer", "events.csv", "--no-open", "--quiet", "-o", "report.html"],
    capture_output=True, text=True, check=False,
)
if result.returncode != 0:
    raise RuntimeError(f"user-explorer failed (exit {result.returncode}): {result.stderr}")

payload = json.loads(result.stdout.strip())
print(f"Report for {payload['users']} users at {payload['out']}")
```

## Controlling output path

```
user-explorer events.csv --no-open --quiet -o /tmp/report.html
```

## Structured JSON output (no HTML)

For agents and scripts that want the actual data — not just a summary or an HTML file —
two flags emit structured JSON to stdout and skip rendering entirely:

### `--profile` — all users

```
$ user-explorer events.csv --profile
{"schema":{"user_id":"uid","timestamp":"ts","event_name":"event"},"users":[{"user_id":"u1","events":3672,"sessions":94,"first_seen":"2025-01-01 16:11:00","last_seen":"2025-05-21 12:46:24","attrs":{"user_plan":"pro"},"power_score":88}, ...]}
```

Each entry in `users`:

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | User identifier |
| `events` | int | Total events for this user |
| `sessions` | int | Session count |
| `first_seen` / `last_seen` | string | Timestamps (first/last event) |
| `attrs` | object | Detected user attributes |
| `power_score` | int | 0–100 percentile of `events × sessions` across all users |

### `--user USER_ID` — one user, full detail

```
$ user-explorer events.csv --user u1
{"user_id":"u1","attrs":{...},"stats":{"events":...,"sessions":...},"insights":{...},"sessions":[...],"top_events":[...]}
```

Returns the same shape as the MCP `analyze_user` tool: stats, deterministic insights
(power score, recency, longest gap, top families, stuck signals), every session with
expanded events, and a ranked `top_events` table.

If the user is not found, prints `{"error":"User 'X' not found"}` and exits non-zero.

Both flags honour `--user-id` / `--timestamp` / `--event-name` overrides and emit a single
machine-parseable JSON line (no stderr schema notes).

## Column overrides for agent use

When the event log has non-standard column names, pass them explicitly to avoid schema sniffing:

```
user-explorer events.csv --user-id actor_id --timestamp occurred_at --event-name track --no-open --quiet
```

## MCP Server

Start the server:

```
user-explorer mcp events.csv
```

MCP config (Claude Desktop / Cursor / any MCP client):

```json
{
  "mcpServers": {
    "user-explorer": {
      "command": "user-explorer",
      "args": ["mcp", "/path/to/events.csv"]
    }
  }
}
```

Every tool takes a `file` argument (absolute path to the events file).

| Tool | Key args | Returns |
|------|----------|---------|
| `quick_report` ⭐ | `file`, `output?`, `filters?` | Renders HTML, opens browser, returns `{output, top_users, top_events, total_events, ...}`. Use first for "analyze this". |
| `list_users` | `file`, `limit?`, `sort_by?`, `filters?` | `{users:[{user_id, events, sessions, first_seen, last_seen, attrs, power_score}], total, filtered_total}` |
| `analyze_user` | `file`, `user_id` | `{user_id, attrs, stats, insights, sessions, top_events}` or `{error}` |
| `get_event_taxonomy` | `file` | `{schema, families, top_events, total_events, total_users}` |
| `summarize_cohort` | `file`, `filters?` | `{filtered_users, total_events, avg_events_per_user, median_sessions, top_events, family_distribution, power_users}` |
| `find_users_by_event` | `file`, `event_name`, `min_occurrences?`, `limit?` | `{pattern, users:[{user_id, occurrences, attrs}], total_matched}` |
| `export_html` | `file`, `output`, `user_ids?`, `filters?`, `auto_open?` | `{output, users_included, user_ids, total_events, size_bytes}` |

`filters` is a JSON string of attribute equality checks, e.g. `'{"user_plan":"pro"}'`.

The same `*_impl` functions back the CLI `--profile`/`--user` flags and the `serve --api`
REST endpoints, so the JSON contract is identical across all three surfaces.
