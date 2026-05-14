# Recipe: Postgres event table

## Typical schema

Most product databases have an events table like:

```sql
CREATE TABLE events (
  id          BIGSERIAL PRIMARY KEY,
  user_id     TEXT        NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  event_type  TEXT        NOT NULL,
  properties  JSONB,
  -- common extras
  session_id  TEXT,
  platform    TEXT,
  country     TEXT
);
```

## Export to CSV

### Quick export (psql)

```bash
psql $DATABASE_URL -c "\COPY (
  SELECT
    user_id,
    occurred_at  AS timestamp,
    event_type   AS event_name,
    session_id,
    platform     AS user_platform,
    country      AS user_country,
    properties->>'page'    AS page,
    properties->>'feature' AS feature
  FROM events
  WHERE occurred_at >= NOW() - INTERVAL '90 days'
  ORDER BY occurred_at
) TO 'events_export.csv' CSV HEADER"
```

Column naming tips:
- Prefix user-level columns with `user_` so userlens detects them as sidebar filters (`user_platform`, `user_country`).
- Flatten the JSONB properties you care about into named columns — they become inline event chips.

### Run userlens

```
userlens events_export.csv
```

userlens auto-maps `occurred_at` → `timestamp` and `event_type` → `event_name` via alias lookup.

## Filtering to specific users

For deep-dive investigation:

```sql
\COPY (
  SELECT user_id, occurred_at AS timestamp, event_type AS event_name, ...
  FROM events
  WHERE user_id = ANY(ARRAY['user_123', 'user_456', 'user_789'])
  ORDER BY occurred_at
) TO 'cohort.csv' CSV HEADER
```

## Performance on large tables

For tables with 10M+ rows, add a time-range filter and ensure `occurred_at` is indexed:

```sql
CREATE INDEX IF NOT EXISTS events_ts_idx ON events (occurred_at DESC);
```

The export query with a 90-day window on an indexed table typically completes in seconds even on large datasets.

## Handling JSONB properties at scale

Instead of flattening in SQL, export the raw JSONB as a string column and let userlens skip it (high-cardinality columns are auto-skipped with a warning). Flatten only the properties you want as chips.
