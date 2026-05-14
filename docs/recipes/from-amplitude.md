# Recipe: Amplitude export

## Export from Amplitude

**Data → Export Data → Export Events**. Choose CSV format and a date range. Amplitude exports a zip of CSVs — unzip first.

Typical Amplitude CSV columns:

| Amplitude column | userlens canonical |
|---|---|
| `user_id` | `user_id` (direct match) |
| `event_time` | `timestamp` |
| `event_type` | `event_name` |
| `session_id` | `session_id` (trusted directly) |
| `device_id` | (use as `user_id` for anonymous) |

## Run userlens

Amplitude's columns match userlens aliases directly — no overrides needed for most exports:

```
userlens amplitude_export.csv
```

If userlens can't auto-detect (e.g. column names differ in your export config):

```
userlens amplitude_export.csv \
  --user-id user_id \
  --timestamp event_time \
  --event-name event_type
```

## Using session_id

Amplitude exports include `session_id`. userlens detects and trusts it automatically — sessions won't be re-derived from gaps. You'll see exact Amplitude sessions in the timeline.

## Merging multiple export files

Amplitude splits large exports into multiple CSVs. Merge before running:

```bash
# macOS / Linux
head -1 export_part1.csv > merged.csv
tail -n +2 export_part1.csv >> merged.csv
tail -n +2 export_part2.csv >> merged.csv
# ... repeat for all parts

userlens merged.csv
```

Or with DuckDB:

```sql
COPY (
  SELECT * FROM read_csv_auto('export_*.csv', union_by_name=true)
) TO 'merged.csv' (HEADER, DELIMITER ',');
```

## Event properties

Amplitude flattens event properties into columns prefixed with `event_properties.`. userlens picks them up as event property chips automatically.

User properties prefixed with `user_properties.` are constant per user and will be detected as attribute filters in the sidebar.
