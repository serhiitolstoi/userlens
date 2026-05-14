# userlens

> **Investigate any user in 30 seconds.**

Drop a CSV of events → get a single HTML file with timelines, sessions, and filters.  
Runs locally. No accounts. No config. Works offline.

```
pip install userlens
userlens events.csv
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
userlens EVENTS_FILE [-o OUT] [--user-id COL] [--timestamp COL] [--event-name COL]
                     [--session-gap MINUTES] [--max-users N] [--no-families]
                     [--no-open] [--quiet]
```

| Flag | Default | Purpose |
|---|---|---|
| `-o` | `userlens.html` | Output path |
| `--session-gap` | `30` min | Gap for session splitting when no `session_id` column |
| `--max-users` | `5000` | Cap users in output |
| `--no-open` | off | Don't open browser after writing |
| `--quiet` | off | Emit one JSON line to stdout (for AI agents) |

**Exit codes:** `0` success · `2` schema error · `3` empty file · `1` other

## For AI agents

```bash
userlens events.csv --no-open --quiet
# → {"out":"userlens.html","users":91,"events":12480,"sessions":520,"elapsed_ms":1340,"schema":{...}}
```

See [docs/agent-usage.md](docs/agent-usage.md) for the full agent contract including MCP.

## Live server mode (v2.0)

Watch an events file and serve a live-updating HTML report over HTTP. Rebuilds automatically when the file changes:

```bash
userlens serve events.csv                  # http://localhost:7891
userlens serve events.csv --port 9000      # custom port
userlens serve events.csv --api            # also expose JSON REST endpoints
userlens serve events.csv --no-open        # don't auto-open browser
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

Query your event data directly from any MCP-compatible AI assistant (Claude Desktop, Cursor, Claude Code):

```bash
pip install 'userlens[mcp]'
userlens mcp /path/to/events.csv
```

MCP config:

```json
{
  "mcpServers": {
    "userlens": {
      "command": "userlens",
      "args": ["mcp", "/path/to/events.csv"]
    }
  }
}
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

The last step produces a standard userlens HTML with only the curated subset.

## Recipes

- [From Postgres](docs/recipes/from-postgres.md)
- [From Amplitude](docs/recipes/from-amplitude.md)
- [From Segment](docs/recipes/from-segment.md)

## Examples

```bash
# Try with the included synthetic Claude product analytics example
userlens examples/claude_product_analytics.csv
```

8 synthetic users, 10k events, Claude-product event schema with model/token properties.

## Install

```bash
pip install userlens                   # core (CSV/JSON/JSONL)
pip install 'userlens[parquet]'        # + Parquet support
pip install 'userlens[mcp]'            # + MCP server
```

Requires Python ≥ 3.10. Single mandatory dependency: [Polars](https://pola.rs/).

## License

MIT
