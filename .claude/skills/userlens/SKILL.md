---
name: userlens
description: Analyze a CSV/JSON/Parquet file of user events and open an interactive HTML report. Use when the user mentions analyzing event data, exploring user behavior, generating a user report, or working with Amplitude/Mixpanel/Segment/GA4/Heap exports.
---

# User Explorer skill

This skill is the canonical entry point for "analyze my event data" requests. It
delegates to the `user-explorer` MCP server, which already exposes the parsing
pipeline and the interactive HTML viewer as tools.

## When to invoke

Trigger on phrases like:
- "analyze events.csv"
- "generate a user report"
- "explore this Amplitude export"
- "/userlens path/to/events.csv"
- "show me what's in this product analytics data"
- "who are my top users in <file>"

## Requirements

The `user-explorer` MCP server must be registered. If the user runs into a
"tool not found" error, run once:

```bash
pip install "user-explorer[mcp] @ git+https://github.com/serhiitolstoi/userlens.git"
claude mcp add user-explorer --scope user -- python3 -m user_explorer mcp
```

Then restart Claude Code.

## How to handle the request

1. **Resolve the file path.** Accept an absolute or relative path. If the user
   didn't provide one, ask which file to analyze before going further.

2. **Default action — one call:**
   - Call `mcp__user-explorer__quick_report` with the file path.
   - The tool parses the events file, renders the full HTML viewer,
     and opens it in the user's browser automatically.
   - It returns: `output` (HTML path), `users_included`, `total_events`,
     `top_users` (5), `top_events` (5), `opened_in_browser` (bool).

3. **Narrate the result** in 2-4 lines:
   - File path of the generated HTML.
   - Total users / events / size.
   - The single most-active user (name + event count).
   - The single most-frequent event (name + count).
   - If `opened_in_browser` is false, give the user the path so they can open
     it themselves.

4. **Stop there.** Do NOT chain into `list_users` / `analyze_user` /
   `export_html` unless the user asks for filtering, scoping, or a deep dive.
   `quick_report` is the happy path.

## When to use other tools instead of quick_report

- User asks to **filter** (e.g. "only pro users", "only US users") → use
  `export_html` with the `filters` argument.
- User names a **specific user_id** ("tell me about usr_x") → use
  `analyze_user`.
- User asks "**who fired event X**" → use `find_users_by_event`.
- User wants **aggregate cohort stats only**, no HTML → use `summarize_cohort`.

## Common edge cases

- **File doesn't exist** → ask the user to confirm the path. Don't guess.
- **MCP server not connected** → surface the install commands above; don't
  attempt to fall back to manual CSV parsing (defeats the purpose of the skill).
- **No users matched filters** → tell the user the filter excluded everyone;
  suggest dropping or loosening the filter.

## Example interaction

> User: `/userlens examples/claude_product_analytics.csv`

You:
1. Call `mcp__user-explorer__quick_report(file="examples/claude_product_analytics.csv")`
2. Reply (concise):
   > Generated report for **8 users · 10,063 events** at `/Users/.../userexplorer_report.html` — opened in your browser.
   >
   > Top user: `usr_alex_chen` (3,672 events). Top event: `message_sent` (2,579×). Tell me which user or filter you want to dig into next.

Stop. Wait for follow-up.
