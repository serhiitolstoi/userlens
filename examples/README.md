# Examples

## synthetic_saas.csv

A synthetic SaaS event log. 100 users, ~22,000 events, spanning ~10 months.

**Columns:** `user_id`, `timestamp`, `event_name`, `user_plan`, `user_country`, `user_source`, `user_industry`, `prop_key`, `prop_value`

- `user_plan`, `user_country`, `user_source`, `user_industry` are per-user attributes → userlens auto-detects them as sidebar filters
- `prop_key` / `prop_value` are event properties → appear as inline chips in the timeline

**Run it:**

```
userlens examples/synthetic_saas.csv
```

Opens the HTML report. Try filtering by plan, country, or industry in the sidebar. Look at the Heatmap tab to see activity patterns over time.

**For agents:**

```
userlens examples/synthetic_saas.csv --no-open --quiet
```

## Generating your own

From a Segment or Amplitude export:

```
userlens segment_export.csv --user-id userId --timestamp sentAt --event-name event
```

From a Postgres dump (after exporting to CSV):

```
userlens events_dump.csv --user-id actor_id --timestamp occurred_at --event-name action_type
```

See [docs/input-contract.md](../docs/input-contract.md) for the full alias table and column classification rules.
