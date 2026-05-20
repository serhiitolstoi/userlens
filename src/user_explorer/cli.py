"""Command-line interface for User Explorer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from user_explorer import __version__
from user_explorer.io.reader import ReadError
from user_explorer.mcp_server import analyze_user_impl, list_users_impl
from user_explorer.mcp_server import main_mcp as _main_mcp
from user_explorer.pipeline import PipelineOptions, run
from user_explorer.schema.sniff import SchemaError
from user_explorer.server import serve as _serve
from user_explorer.viewer import render

EXIT_OK = 0
EXIT_OTHER = 1
EXIT_SCHEMA = 2
EXIT_EMPTY = 3


def _build_serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="user-explorer serve",
        description="Watch an events file and serve a live-updating HTML report.",
    )
    parser.add_argument("events_file", type=Path, help="Path to events file.")
    parser.add_argument("--port", type=int, default=7891, help="HTTP port (default 7891).")
    parser.add_argument(
        "--api",
        action="store_true",
        help="Also expose JSON REST endpoints at /api/.",
    )
    parser.add_argument(
        "--no-open", action="store_true", help="Don't open browser on start."
    )
    parser.add_argument("-o", "--out", default=None, help="HTML output path (default: temp file).")
    return parser


def _build_mcp_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="user-explorer mcp",
        description="Start the User Explorer MCP server. Requires: pip install 'user-explorer[mcp]'",  # noqa: E501
    )
    parser.add_argument(
        "events_file",
        nargs="?",
        default=None,
        help="Optional path to events file to pre-load.",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="user-explorer",
        description="Investigate any user in 30 seconds. "
        "Drop a CSV of events; get an interactive HTML.",
    )
    parser.add_argument("events", type=Path, help="Path to events file (CSV/Parquet/JSON/JSONL).")
    parser.add_argument("-o", "--out", default="userexplorer.html", help="Output HTML path.")
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
        "--redact",
        nargs="+",
        metavar="COL",
        default=None,
        help="Replace values in these columns with <redacted> before output.",
    )
    parser.add_argument(
        "--tz",
        default=None,
        metavar="TZ",
        help="Display timestamps in this IANA timezone (e.g. Europe/Lisbon, UTC).",
    )
    parser.add_argument(
        "--no-open", action="store_true", help="Write HTML but suppress auto-opening the browser."
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Emit a single JSON-line summary on stdout. Used by AI agents.",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Emit per-user JSON (all users, no HTML) on stdout. For AI agents / scripts.",
    )
    parser.add_argument(
        "--user",
        dest="user",
        default=None,
        metavar="USER_ID",
        help="Emit full JSON for a single user (no HTML) on stdout. For AI agents / scripts.",
    )
    parser.add_argument("--version", action="version", version=f"user-explorer {__version__}")

    return parser


def main(argv: list[str] | None = None) -> int:
    # Intercept `mcp` subcommand before the main parser sees it.
    # This avoids argparse confusing a file path with a subcommand name.
    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    if effective_argv and effective_argv[0] == "serve":
        serve_parser = _build_serve_parser()
        serve_args = serve_parser.parse_args(effective_argv[1:])
        _serve(
            events_path=serve_args.events_file,
            port=serve_args.port,
            api=serve_args.api,
            open_browser=not serve_args.no_open,
            out=Path(serve_args.out) if serve_args.out else None,
        )
        return EXIT_OK

    if effective_argv and effective_argv[0] == "mcp":
        mcp_parser = _build_mcp_parser()
        mcp_args = mcp_parser.parse_args(effective_argv[1:])
        _main_mcp(mcp_args.events_file)
        return EXIT_OK

    parser = build_parser()
    args = parser.parse_args(effective_argv)

    options = PipelineOptions(
        events_path=args.events,
        user_id_override=args.user_id,
        timestamp_override=args.timestamp,
        event_name_override=args.event_name,
        max_users=args.max_users,
        session_gap_minutes=args.session_gap,
        no_families=args.no_families,
        redact_cols=tuple(args.redact) if args.redact else (),
        timezone=args.tz,
    )

    try:
        result = run(options)
    except ReadError as e:
        msg = str(e)
        print(f"user-explorer: {msg}", file=sys.stderr)
        return EXIT_EMPTY if "empty" in msg.lower() else EXIT_OTHER
    except SchemaError as e:
        print(f"user-explorer: schema error: {e}", file=sys.stderr)
        return EXIT_SCHEMA

    # Structured JSON output for agents/scripts — no HTML, single JSON line on stdout.
    if args.user is not None:
        result_user = analyze_user_impl(result.blobs, result.meta, user_id=args.user)
        print(json.dumps(result_user, separators=(",", ":"), default=str))
        return EXIT_OTHER if "error" in result_user else EXIT_OK

    if args.profile:
        payload = {
            "schema": result.schema.as_mapping(),
            "users": list_users_impl(
                result.blobs, result.meta, limit=len(result.blobs)
            )["users"],
        }
        print(json.dumps(payload, separators=(",", ":"), default=str))
        return EXIT_OK

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
        f"user-explorer: wrote {out_path} — "
        f"{len(result.blobs)} users · {result.n_events} events · {result.elapsed_ms} ms",
        file=sys.stderr,
    )
    if args.redact:
        print(
            f"Note: columns redacted: {', '.join(args.redact)}. Other properties are verbatim.",
            file=sys.stderr,
        )
    else:
        print(
            "Note: output contains all event properties verbatim. "
            "Use --redact COL to hide sensitive columns before sharing.",
            file=sys.stderr,
        )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
