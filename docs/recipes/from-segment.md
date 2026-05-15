# Recipe: Segment export

## Export from Segment

In your Segment workspace: **Connections → Sources → your source → Debugger → Export** (or use the Segment Public API to pull an event stream CSV).

The resulting file typically has these columns:

| Segment column | User Explorer canonical |
|---|---|
| `userId` | `user_id` |
| `sentAt` | `timestamp` |
| `event` | `event_name` |
| `anonymousId` | (skip — use `userId`) |
| `properties.*` flattened | event properties |

## Run User Explorer

```
user-explorer segment_export.csv \
  --user-id userId \
  --timestamp sentAt \
  --event-name event
```

If the export has `anonymousId` but no `userId` (anonymous traffic):

```
user-explorer segment_export.csv \
  --user-id anonymousId \
  --timestamp sentAt \
  --event-name event
```

## Flattened properties

Segment exports flatten `properties` into dot-notation columns (`properties.page`, `properties.revenue`). User Explorer treats each as an event property chip automatically — no extra config needed.

## Large exports

Segment exports for active workspaces can be millions of rows. User Explorer handles up to ~5M events comfortably. For larger volumes:

```
# Filter to a time window first
user-explorer segment_export.csv --max-users 1000 -o segment_sample.html
```

Or pre-filter with a tool like DuckDB:

```sql
COPY (
  SELECT * FROM read_csv_auto('segment_export.csv')
  WHERE sentAt >= '2024-01-01'
  AND userId IS NOT NULL
) TO 'filtered.csv' (HEADER, DELIMITER ',');
```

Then run User Explorer on `filtered.csv`.
