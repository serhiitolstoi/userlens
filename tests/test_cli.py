from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "user_explorer", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_quiet_emits_single_json_line() -> None:
    proc = _run([str(FIXTURES / "tiny.csv"), "--no-open", "--quiet"])
    assert proc.returncode == 0, proc.stderr
    line = proc.stdout.strip()
    assert "\n" not in line  # single line
    payload = json.loads(line)
    assert payload["users"] == 3
    assert payload["events"] == 20
    assert payload["schema"]["user_id"] == "user_id"


def test_schema_error_exit_code() -> None:
    bad = FIXTURES / "bad.csv"
    bad.write_text("a,b\n1,x\n2,y\n")
    try:
        proc = _run([str(bad), "--no-open", "--quiet"])
        assert proc.returncode == 2
    finally:
        bad.unlink(missing_ok=True)


def test_missing_file_exits_nonzero() -> None:
    proc = _run(["/tmp/does-not-exist-user-explorer.csv", "--quiet"])
    assert proc.returncode != 0


def test_default_mode_renders_html(tmp_path: Path) -> None:
    out = tmp_path / "out.html"
    proc = _run([str(FIXTURES / "tiny.csv"), "--no-open", "-o", str(out)])
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    html = out.read_text()
    assert "101" in html
    assert "page_viewed" in html
    # summary line goes to stderr
    assert "users" in proc.stderr or "wrote" in proc.stderr


def test_profile_emits_json() -> None:
    proc = _run([str(FIXTURES / "tiny.csv"), "--profile"])
    assert proc.returncode == 0, proc.stderr
    line = proc.stdout.strip()
    assert "\n" not in line  # single JSON line
    payload = json.loads(line)
    assert payload["schema"]["user_id"] == "user_id"
    assert len(payload["users"]) == 3
    sample = payload["users"][0]
    for key in ("user_id", "events", "sessions", "first_seen", "last_seen", "power_score"):
        assert key in sample


def test_user_flag_emits_json() -> None:
    proc = _run([str(FIXTURES / "tiny.csv"), "--user", "102"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert payload["user_id"] == "102"
    assert set(payload.keys()) >= {"stats", "insights", "sessions", "top_events"}
    # 102 fired checkout_completed in the fixture
    names = {e["name"] for e in payload["top_events"]}
    assert "checkout_completed" in names


def test_user_flag_unknown_user_nonzero() -> None:
    proc = _run([str(FIXTURES / "tiny.csv"), "--user", "does_not_exist"])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout.strip())
    assert "error" in payload
