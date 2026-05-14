# userlens

> **Investigate any user in 30 seconds.**

Drop a CSV of events → get a single HTML file with timelines, sessions, and filters. Runs locally. No accounts. No config. Works offline.

```
pip install userlens
userlens events.csv
```

That's it.

## Input

Three columns required: `user_id`, `timestamp`, `event_name`. Anything else is auto-detected (extra columns become filters or timeline properties). CSV, Parquet, JSON, and JSONL all work.

Common aliases are auto-mapped (`uid`, `ts`, `event`, etc.) — see [docs/input-contract.md](docs/input-contract.md).

## For AI agents (Cursor, Claude Code, internal tools)

```
userlens events.csv --no-open --quiet
# prints one JSON line: {"out":"userlens.html","users":...,"events":...}
```

See [docs/agent-usage.md](docs/agent-usage.md).

## Status

Alpha. v1.0 = file → HTML, per-user deep-dive. See the roadmap for what's next.

## License

MIT.
