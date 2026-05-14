"""Command-line interface for userlens."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from userlens import __version__
from userlens.io.reader import ReadError
from userlens.pipeline import PipelineOptions, run
from userlens.schema.sniff import SchemaError
from userlens.viewer import render

EXIT_OK = 0
EXIT_OTHER = 1
EXIT_SCHEMA = 2
EXIT_EMPTY = 3

# Flags reserved for future versions; accepted but not yet active.
_COMING_SOON: dict[str, str] = {
    "--profile": "v2 (structured JSON output per user)",
    "--user": "v2 (single-user JSON output)",
    "--mcp": "v2 (MCP server mode)",
    "--serve": "v2 (self-hosted file-watch mode)",
    "--llm-summarize": "v2.1 (LLM narrative generation)",
    "--diff": "v3 (compare two event files)",
    "--redact": "v1.1 (redact named property columns)",
    "--tz": "v1.1 (explicit timezone)",
    "--cohort": "v1.1 (cohort summary tab)",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="userlens",
        description="Investigate any user in 30 seconds. "
        "Drop a CSV of events; get an interactive HTML.",
    )
    parser.add_argument("events", type=Path, help="Path to events file (CSV/Parquet/JSON/JSONL).")
    parser.add_argument("-o", "--out", default="userlens.html", help="Output HTML path.")
    parser.add_argument("--user-id", dest="user_id", default=None, help="Explicit user_id column.")
    parser.add_argument(
        "--timestamp", dest="timestamp", default=None, help="Explicit timestamp column."
    )
    parser.add_argument(
        "--event-name", dest="event_name", default=None, help="Explicit event_name column."
    )
    parser.add_argument(
        "--session-gap",
        type=int,
        default=30,
        help="Session boundary in minutes when no session_id column (default 30).",
    )
    parser.add_argument(
        "--max-users", type=int, default=5000, help="Cap users in output (default 5000)."
    )
    parser.add_argument("--no-families", action="store_true", help="Skip family clustering.")
    parser.add_argument(
        "--no-open", action="store_true", help="Write HTML but suppress auto-opening the browser."
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Emit a single JSON-line summary on stdout. Used by AI agents.",
    )
    parser.add_argument("--version", action="version", version=f"userlens {__version__}")

    # Reserved flags — accepted so they print a helpful message instead of an argparse error
    for flag in _COMING_SOON:
        dest = f"_reserved_{flag.lstrip('-').replace('-', '_')}"
        parser.add_argument(
            flag, dest=dest, nargs="?", const=True, default=None, help=argparse.SUPPRESS
        )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Check if any reserved flag was passed
    for flag, roadmap in _COMING_SOON.items():
        attr = f"_reserved_{flag.lstrip('-').replace('-', '_')}"
        if getattr(args, attr, None) is not None:
            print(f"userlens: {flag} is coming soon ({roadmap})", file=sys.stderr)
            return EXIT_OK

    options = PipelineOptions(
        events_path=args.events,
        user_id_override=args.user_id,
        timestamp_override=args.timestamp,
        event_name_override=args.event_name,
        max_users=args.max_users,
        session_gap_minutes=args.session_gap,
        no_families=args.no_families,
    )

    try:
        result = run(options)
    except ReadError as e:
        msg = str(e)
        print(f"userlens: {msg}", file=sys.stderr)
        return EXIT_EMPTY if "empty" in msg.lower() else EXIT_OTHER
    except SchemaError as e:
        print(f"userlens: schema error: {e}", file=sys.stderr)
        return EXIT_SCHEMA

    if args.quiet:
        summary = {
            "out": args.out,
            "users": len(result.blobs),
            "events": result.n_events,
            "sessions": result.n_sessions,
            "elapsed_ms": result.elapsed_ms,
            "schema": result.schema.as_mapping(),
        }
        print(json.dumps(summary, separators=(",", ":")))
        return EXIT_OK

    # Default: render HTML, optionally open browser.
    for note in result.schema_notes:
        print(f"  {note}", file=sys.stderr)

    out_path = Path(args.out)
    render(result.blobs, result.meta, out_path, open_browser=not args.no_open)

    print(
        f"userlens: wrote {out_path} — "
        f"{len(result.blobs)} users · {result.n_events} events · {result.elapsed_ms} ms",
        file=sys.stderr,
    )
    print(
        "Note: output contains all event properties verbatim. Inspect before sharing.",
        file=sys.stderr,
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
