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

`-o -` writes HTML to stdout (useful for piping), but is incompatible with `--quiet`.

## Column overrides for agent use

When the event log has non-standard column names, pass them explicitly to avoid schema sniffing:

```
user-explorer events.csv --user-id actor_id --timestamp occurred_at --event-name track --no-open --quiet
```

## Reserved flags (not yet implemented)

These flags are reserved. The parser recognises them and prints "coming soon":

- `--profile` — emit per-user JSON blobs without HTML
- `--user USER_ID` — emit blob for a single user
- `--serve` — self-hosted mode with file-watch (v2)
- `--llm-summarize` — LLM narrative generation (v2.1)
- `--diff` — compare two event files (v3)

## MCP Server (v2.0)

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

Available tools: `list_users`, `analyze_user`, `get_event_taxonomy`, `summarize_cohort`, `find_users_by_event`.
