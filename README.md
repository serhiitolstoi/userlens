# User Explorer

> **Investigate any user in 30 seconds.**

Drop a CSV of events → get a single HTML file with timelines, sessions, and filters.  
Runs locally. No accounts. No config. Works offline.

```
pip install user-explorer
user-explorer events.csv
```

That's it.

---

## What you get

- **Activity heatmap** — GitHub-style calendar colored by dominant event family
- **Session timeline** — every event with properties, collapsible by session
- **Sidebar filters** — one `<select>` per detected user attribute (`user_plan`, `user_country`, etc.)
- **Top events table** — ranked by count with family tags and percentages
- **Single self-contained HTML** — share it, host it, open it offline

## Input

Three columns required (or recognized aliases — see [input contract](docs/input-contract.md)):

| Canonical | Common aliases |
|---|---|
| `user_id` | `uid`, `userId`, `customer_id`, `distinct_id` |
| `timestamp` | `ts`, `time`, `event_time`, `occurred_at`, `created_at` |
| `event_name` | `event`, `name`, `action`, `type`, `event_type` |

Everything else is auto-classified: columns starting with `user_` (or constant per user) become sidebar filters; the rest become inline event property chips.

CSV, Parquet, JSON, and JSONL all work.

## CLI

```
user-explorer EVENTS_FILE [-o OUT] [--user-id COL] [--timestamp COL] [--event-name COL]
                          [--session-gap MINUTES] [--max-users N] [--no-families]
                          [--redact COL [COL ...]] [--tz TZ]
                          [--no-open] [--quiet]
```

| Flag | Default | Purpose |
|---|---|---|
| `-o` | `userexplorer.html` | Output path |
| `--session-gap` | `30` min | Gap for session splitting when no `session_id` column |
| `--max-users` | `5000` | Cap users in output |
| `--redact COL` | — | Replace values in named columns with `<redacted>` before writing HTML |
| `--tz TZ` | — | Display timestamps in this IANA timezone (e.g. `Europe/Lisbon`, `UTC`) |
| `--no-open` | off | Don't open browser after writing |
| `--quiet` | off | Emit one JSON line to stdout (for AI agents) |

**Exit codes:** `0` success · `2` schema error · `3` empty file · `1` other

## For AI agents

```bash
user-explorer events.csv --no-open --quiet
# → {"out":"userexplorer.html","users":91,"events":12480,"sessions":520,"elapsed_ms":1340,"schema":{...}}
```

See [docs/agent-usage.md](docs/agent-usage.md) for the full agent contract including MCP.

## Live server mode (v2.0)

Watch an events file and serve a live-updating HTML report over HTTP. Rebuilds automatically when the file changes:

```bash
user-explorer serve events.csv                  # http://localhost:7891
user-explorer serve events.csv --port 9000      # custom port
user-explorer serve events.csv --api            # also expose JSON REST endpoints
user-explorer serve events.csv --no-open        # don't auto-open browser
```

**REST API** (with `--api`):

```
GET  /                    → live HTML report
GET  /status              → JSON: {users, events, last_built, watching}
POST /api/list_users      → body: {limit?, sort_by?, filters?}
POST /api/analyze_user    → body: {user_id}
POST /api/taxonomy        → body: {}
POST /api/cohort          → body: {filters?}
POST /api/find_event      → body: {event_name, min_occurrences?}
POST /api/export_html     → body: {output, user_ids?, filters?}
```

This is the integration point for internal tools, Slack bots, or any HTTP-native system — call the endpoints, get structured JSON, optionally trigger `export_html` to generate a report and serve it via a pre-signed URL.

## MCP server (v2.0)

Query your event data directly from any MCP-compatible AI assistant (Claude Code, Cursor, Claude Desktop).

### Step 1 — Install

```bash
pip install "user-explorer[mcp] @ git+https://github.com/serhiitolstoi/userlens.git"
```

### Step 2 — Connect to your AI tool

**Claude Code** — run once in terminal:

```bash
claude mcp add user-explorer -- python3 -m user_explorer mcp
```

Verify:

```bash
claude mcp list
# user-explorer: python3 -m user_explorer mcp - ✓ Connected
```

**Cursor** — add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "user-explorer": {
      "command": "python3",
      "args": ["-m", "user_explorer", "mcp"]
    }
  }
}
```

Restart Cursor after saving.

### Step 3 — Use it

Ask Claude or Cursor in natural language:

```
List users from events.csv
Analyze user usr_alex_chen from events.csv
Export an HTML report for pro users from events.csv
```

**Available tools:**

| Tool | What it does |
|---|---|
| `list_users` | List users with power scores, filterable by attribute |
| `analyze_user` | Full session timeline + insights for one user |
| `get_event_taxonomy` | Event families, top events, schema |
| `summarize_cohort` | Aggregate stats for a filtered segment |
| `find_users_by_event` | Find users who fired a specific event (substring match) |
| `export_html` | Generate a focused HTML report for selected users |

**Agent workflow example:**

```
1. list_users(file, sort_by="power_score", filters='{"user_plan":"pro"}')
2. analyze_user(file, "usr_alex_chen")   ← deep-dive on a specific user
3. export_html(file, "report.html", user_ids=["usr_alex_chen", "usr_omar_f"])
```

The last step produces a standard User Explorer HTML with only the curated subset.

## Recipes

- [From Postgres](docs/recipes/from-postgres.md)
- [From Amplitude](docs/recipes/from-amplitude.md)
- [From Segment](docs/recipes/from-segment.md)

## Examples

```bash
# Try with the included synthetic Claude product analytics example
user-explorer examples/claude_product_analytics.csv
```

8 synthetic users, 10k events, Claude-product event schema with model/token properties.

## Install

```bash
pip install "user-explorer[mcp] @ git+https://github.com/serhiitolstoi/userlens.git"
```

For Parquet support:

```bash
pip install "user-explorer[mcp,parquet] @ git+https://github.com/serhiitolstoi/userlens.git"
```

Requires Python ≥ 3.10. Single mandatory dependency: [Polars](https://pola.rs/).

### Updating

When a new version is pushed to GitHub:

```bash
pip install --upgrade "user-explorer[mcp] @ git+https://github.com/serhiitolstoi/userlens.git"
```

## License

MIT
