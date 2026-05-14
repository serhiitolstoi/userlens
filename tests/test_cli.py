from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "userlens", *args],
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
    proc = _run(["/tmp/does-not-exist-userlens.csv", "--quiet"])
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
