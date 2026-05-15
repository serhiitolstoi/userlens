"""user-explorer serve — file-watch HTTP server + optional JSON REST API.

Usage:
    user-explorer serve events.csv                 # file-watch + static HTML on :7891
    user-explorer serve events.csv --port 9000     # custom port
    user-explorer serve events.csv --api           # also exposes JSON REST endpoints
    user-explorer serve events.csv --no-open       # don't open browser

Static mode:
    GET /            → serves the latest generated HTML (auto-regenerated on file change)
    GET /status      → JSON: {users, events, elapsed_ms, last_built, watching}

REST API mode (--api):
    POST /api/list_users       body: {limit?, sort_by?, filters?}
    POST /api/analyze_user     body: {user_id}
    POST /api/taxonomy         body: {}
    POST /api/cohort           body: {filters?}
    POST /api/find_event       body: {event_name, min_occurrences?}
    POST /api/export_html      body: {output, user_ids?, filters?}
"""

from __future__ import annotations

import http.server
import json
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from user_explorer.mcp_server import (
    analyze_user_impl,
    export_html_impl,
    find_users_by_event_impl,
    get_event_taxonomy_impl,
    list_users_impl,
    summarize_cohort_impl,
)
from user_explorer.pipeline import PipelineOptions, run
from user_explorer.viewer import render

_POLL_INTERVAL = 2.0  # seconds between mtime checks


class _State:
    """Shared mutable state between the watcher thread and the HTTP handler."""

    def __init__(self, events_path: Path, out_path: Path) -> None:
        self.events_path = events_path
        self.out_path = out_path
        self.lock = threading.Lock()
        self.last_mtime: float = 0.0
        self.last_built: str = ""
        self.users: int = 0
        self.events: int = 0
        self.elapsed_ms: int = 0
        self.error: str = ""
        # Cached blobs + meta for API calls
        self.blobs: list[dict[str, Any]] = []
        self.meta: dict[str, Any] = {}

    def build(self) -> None:
        """Regenerate the HTML from the events file."""
        try:
            result = run(PipelineOptions(events_path=self.events_path, max_users=None))
            render(result.blobs, result.meta, self.out_path, open_browser=False)
            with self.lock:
                self.users = len(result.blobs)
                self.events = result.n_events
                self.elapsed_ms = result.elapsed_ms
                self.last_built = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self.blobs = result.blobs
                self.meta = result.meta
                self.error = ""
            print(
                f"  rebuilt → {self.users} users · {self.events} events · {self.elapsed_ms} ms",
                file=sys.stderr,
                flush=True,
            )
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
            print(f"  build error: {exc}", file=sys.stderr, flush=True)

    def check_and_rebuild(self) -> None:
        """Rebuild if mtime changed."""
        try:
            mtime = self.events_path.stat().st_mtime
        except OSError:
            return
        if mtime != self.last_mtime:
            self.last_mtime = mtime
            self.build()


def _watch_loop(state: _State) -> None:
    """Background thread: poll file mtime and rebuild on change."""
    while True:
        state.check_and_rebuild()
        time.sleep(_POLL_INTERVAL)


def _make_handler(state: _State, api: bool) -> type[http.server.BaseHTTPRequestHandler]:
    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # suppress default access log
            pass

        def _send_json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, path: Path) -> None:
            try:
                body = path.read_bytes()
            except OSError:
                self.send_error(503, "Report not yet generated")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return {}
            try:
                result: dict[str, Any] = json.loads(self.rfile.read(length))
                return result
            except (json.JSONDecodeError, ValueError):
                return {}

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send_html(state.out_path)
            elif path == "/status":
                with state.lock:
                    self._send_json(
                        {
                            "users": state.users,
                            "events": state.events,
                            "elapsed_ms": state.elapsed_ms,
                            "last_built": state.last_built,
                            "watching": str(state.events_path),
                            "error": state.error,
                        }
                    )
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            if not api:
                self.send_error(404, "Start with --api to enable REST endpoints")
                return
            path = self.path.split("?")[0]
            body = self._read_body()
            with state.lock:
                blobs = state.blobs
                meta = state.meta
            if not blobs:
                self._send_json({"error": "data not yet loaded"}, 503)
                return

            try:
                if path == "/api/list_users":
                    result = list_users_impl(
                        blobs, meta,
                        limit=body.get("limit", 50),
                        sort_by=body.get("sort_by", "events"),
                        filters=body.get("filters", "{}"),
                    )
                elif path == "/api/analyze_user":
                    result = analyze_user_impl(blobs, meta, user_id=body["user_id"])
                elif path == "/api/taxonomy":
                    result = get_event_taxonomy_impl(blobs, meta)
                elif path == "/api/cohort":
                    result = summarize_cohort_impl(
                        blobs, meta, filters=body.get("filters", "{}")
                    )
                elif path == "/api/find_event":
                    result = find_users_by_event_impl(
                        blobs, meta,
                        event_name=body["event_name"],
                        min_occurrences=body.get("min_occurrences", 1),
                        limit=body.get("limit", 20),
                    )
                elif path == "/api/export_html":
                    result = export_html_impl(
                        blobs, meta,
                        output=body.get("output", "report.html"),
                        user_ids=body.get("user_ids"),
                        filters=body.get("filters", "{}"),
                    )
                else:
                    self.send_error(404)
                    return
                self._send_json(result)
            except KeyError as exc:
                self._send_json({"error": f"missing field: {exc}"}, 400)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)

        def do_OPTIONS(self) -> None:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

    return _Handler


def serve(
    events_path: Path,
    port: int = 7891,
    api: bool = False,
    open_browser: bool = True,
    out: Path | None = None,
) -> None:
    """Start the file-watch server. Blocks until Ctrl-C."""
    out_path = out or Path(tempfile.mktemp(suffix=".html", prefix="userexplorer_"))

    state = _State(events_path, out_path)

    # Initial build before server starts
    print(f"user-explorer serve: watching {events_path}", file=sys.stderr)
    print("  building initial report…", file=sys.stderr, flush=True)
    state.check_and_rebuild()

    # Start watcher thread
    t = threading.Thread(target=_watch_loop, args=(state,), daemon=True)
    t.start()

    # Start HTTP server
    handler = _make_handler(state, api)
    httpd = http.server.HTTPServer(("127.0.0.1", port), handler)

    url = f"http://localhost:{port}"
    lines = [f"  serving at {url}"]
    if api:
        endpoints = "list_users,analyze_user,taxonomy,cohort,find_event,export_html"
        lines.append(f"  REST API at {url}/api/{{{endpoints}}}")
    lines.append("  press Ctrl-C to stop")
    print("\n".join(lines), file=sys.stderr)

    if open_browser and state.out_path.exists():
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nuser-explorer serve: stopped.", file=sys.stderr)
    finally:
        httpd.server_close()
