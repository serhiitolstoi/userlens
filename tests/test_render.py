from __future__ import annotations

from pathlib import Path

from user_explorer.pipeline import PipelineOptions, run
from user_explorer.viewer.render import render

FIXTURES = Path(__file__).parent / "fixtures"


def test_render_writes_html(tmp_path: Path) -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    out = tmp_path / "out.html"
    render(result.blobs, result.meta, out, open_browser=False)

    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "User Explorer" in html


def test_render_embeds_user_ids(tmp_path: Path) -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    out = tmp_path / "out.html"
    render(result.blobs, result.meta, out, open_browser=False)

    html = out.read_text(encoding="utf-8")
    for uid in ("101", "102", "103"):
        assert uid in html


def test_render_sentinels_replaced(tmp_path: Path) -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    out = tmp_path / "out.html"
    render(result.blobs, result.meta, out, open_browser=False)

    html = out.read_text(encoding="utf-8")
    assert "/*__USERLENS_DATA__*/" not in html
    assert "/*__USERLENS_META__*/" not in html


def test_render_embeds_event_names(tmp_path: Path) -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    out = tmp_path / "out.html"
    render(result.blobs, result.meta, out, open_browser=False)

    html = out.read_text(encoding="utf-8")
    assert "page_viewed" in html
    assert "checkout_completed" in html


def test_render_embeds_families(tmp_path: Path) -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    out = tmp_path / "out.html"
    render(result.blobs, result.meta, out, open_browser=False)

    html = out.read_text(encoding="utf-8")
    assert '"view"' in html or "'view'" in html


def test_render_with_attrs(tmp_path: Path) -> None:
    result = run(PipelineOptions(events_path=FIXTURES / "with_attrs.csv"))
    out = tmp_path / "out.html"
    render(result.blobs, result.meta, out, open_browser=False)

    html = out.read_text(encoding="utf-8")
    assert "user_country" in html
    assert "PL" in html
    assert "UA" in html
