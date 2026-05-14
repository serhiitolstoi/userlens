# Architecture

## Overview

userlens is a single-pass pipeline: read → sniff → materialize → classify → derive → build blobs → render HTML.

Each step is a pure function in its own module. The orchestrator (`pipeline.py`) wires them together and returns a `PipelineResult` dataclass before any HTML is written.

```
events.csv
    │
    ▼
io/reader.py          ← dispatches by extension (.csv, .parquet, .json, .jsonl)
    │  (lazy Polars scan)
    ▼
schema/sniff.py       ← alias lookup + content sniffing; exit 2 on ambiguity
    │  (ResolvedSchema)
    ▼
schema/types.py       ← materialize to canonical column names, parse timestamps
    │  (normalized DataFrame)
    ▼
derive/attributes.py  ← classify extras: user attribute vs event property
derive/sessions.py    ← trust session_id or gap-split at 30 min
derive/families.py    ← two-pass verb/prefix clustering → family labels + palette
    │
    ▼
transform/build.py    ← build one blob dict per user
    │  (list[dict])
    ▼
viewer/render.py      ← inject blobs + meta into template.html → write atomically
    │
    ▼
userlens.html         ← self-contained, no external dependencies
```

## Key design choices

### Polars, not pandas

Single mandatory dependency. 5–10× faster groupby and sort for the session-derivation step. Arrow-native for Parquet (no extra conversion). Lazy API avoids materializing the full DataFrame until after schema sniffing.

### No template engine

`template.html` contains exactly two sentinels: `/*__USERLENS_DATA__*/` and `/*__USERLENS_META__*/`. `render.py` does two `str.replace()` calls. No Jinja, no AST — one template, two slots.

### Data vs meta separation

- **Data blob** (`USERLENS_DATA`): list of per-user dicts. The viewer only loads one user's blob at a time.
- **Meta blob** (`USERLENS_META`): schema info, attribute definitions, family color palette, top-events table. Drives the generic UI — no hard-coded strings in the viewer beyond layout chrome.

This separation means the viewer is fully data-driven and works for any event schema without changes.

### Deterministic families

Family labels are derived purely from event names — no ML, no config. The two-pass heuristic:
1. Match the last token of the event name against a verb table (67 mappings).
2. For unmatched events: group by first token; if ≥3 distinct names share it and it covers ≥0.5% of events, promote the prefix to a family.

Family colors are `hash(name) % 12` into a fixed 12-hue palette. The same family name always maps to the same color across all runs and all files.

### Pipeline seam

`pipeline.run()` returns `PipelineResult` (blobs + meta) before rendering. The CLI calls `render()` on it. The future MCP server (v2) will call the same `pipeline.run()` and return JSON directly — HTML rendering becomes one optional call.

### Atomic writes

`render.py` writes to a temp file in the same directory, then calls `os.replace()`. No partial HTML is ever visible to the browser, even if the process crashes mid-write.

## Module map

```
src/userlens/
├── __init__.py          version, public API surface
├── __main__.py          python -m userlens entry point
├── cli.py               argparse wiring, exit code handling
├── pipeline.py          PipelineOptions, PipelineResult, run()
├── version.py           __version__ = "..."
│
├── io/
│   ├── __init__.py
│   ├── reader.py        dispatch by extension
│   ├── csv_reader.py    polars.scan_csv wrapper
│   ├── parquet_reader.py polars.scan_parquet wrapper
│   └── json_reader.py   scan_ndjson + array-of-objects JSON
│
├── schema/
│   ├── __init__.py
│   ├── aliases.py       ALIAS_TABLE: canonical → [alias, ...]
│   ├── sniff.py         resolve_schema(df, overrides) → ResolvedSchema
│   └── types.py         materialize(df, schema) → normalized DataFrame
│
├── derive/
│   ├── __init__.py
│   ├── attributes.py    classify_extras, derive_attributes, build_attributes_meta
│   ├── families.py      derive_families → (assignment dict, FamilyInfo registry)
│   ├── properties.py    extract_event_props → flat key/value list
│   └── sessions.py      derive_sessions → {user_id: [[session_id, ts, [events]]]}
│
├── transform/
│   ├── __init__.py
│   └── build.py         build_user_blobs → list[dict]
│
└── viewer/
    ├── __init__.py
    ├── render.py         render(blobs, meta, out_path)
    └── template.html     self-contained HTML viewer
```

## Blob shape reference

### Per-user blob (embedded as `USERLENS_DATA`)

```json
{
  "u": "user_123",
  "te": 42,
  "sn": 3,
  "fs": "2024-03-01 09:12",
  "ls": "2024-03-15 17:44",
  "fc": {"view": 20, "click": 15, "other": 7},
  "attrs": {"country": "PL", "plan": "premium"},
  "s": [
    ["user_123_s0", "2024-03-01", [
      ["09:12", "page_viewed", "view", "page", "/home"],
      ["09:14", "button_clicked", "click", "button", "signup"]
    ]],
    ["user_123_s1", "2024-03-05", [
      ["14:00", "form_submitted", "submit"]
    ]]
  ]
}
```

### Meta blob (embedded as `USERLENS_META`)

```json
{
  "schema": {"user_id": "user_id", "timestamp": "ts", "event_name": "event"},
  "attributes": [{"key": "country", "values": ["PL", "UA", "DE"]}],
  "families": {
    "view": {"color": "#3b82f6", "bg": "#dbeafe", "fg": "#1e40af", "label": "View"}
  },
  "topEvents": [{"name": "page_viewed", "count": 1200, "family": "view"}],
  "generatedAt": "2024-05-13T18:00:00Z"
}
```

## Performance

Target: 1M events × 10k users in <30s on a modern laptop.

Polars handles I/O, sort, sessionize, and groupby in <10s. JSON serialization dominates output time for large datasets. The timeline is capped at 500 events per user with a "show all" expander to keep HTML size manageable.

HTML size budget: <1 MB for 100 users × 20k events. Hard cap at 5k users (`--max-users`).
