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


def test_render_heatmap_highlight_filter_present(tmp_path: Path) -> None:
    """Clicking an event chip must filter the heatmap to events of that name.

    Regression guard for a real bug: the heatmap-cell counting loop must
    short-circuit when ``highlightEvent`` is set and the current event name
    doesn't match. Without this line, the chip 'solo' state has no visible
    effect on the heatmap and all events still contribute to cell totals.
    """
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    out = tmp_path / "out.html"
    render(result.blobs, result.meta, out, open_browser=False)

    html = out.read_text(encoding="utf-8")
    # The filter line short-circuits the per-event counting inside renderHeatmap.
    assert "highlightEvent && name!==highlightEvent" in html, (
        "renderHeatmap must filter events to the highlighted one when a chip is solo'd"
    )
    # Chip click handler must toggle highlightEvent.
    assert "highlightEvent = highlightEvent===n ? null : n" in html, (
        "Event-chip click must toggle highlightEvent so the heatmap re-renders filtered"
    )
    # Timeline rows must receive .hl-ev class on the highlighted event for visual cohesion.
    assert "hl-ev" in html, "Timeline event rows must support a highlight CSS class"


def test_render_flow_uses_session_paths_not_2grams(tmp_path: Path) -> None:
    """Flow tab must show full session-path signatures, not 2-gram transitions.

    Regression guard: the old implementation grouped by consecutive event
    pairs (a→b), which gave a misleading view. The new implementation groups
    sessions by their head+tail signature so similar full flows aggregate.
    """
    result = run(PipelineOptions(events_path=FIXTURES / "tiny.csv"))
    out = tmp_path / "out.html"
    render(result.blobs, result.meta, out, open_browser=False)

    html = out.read_text(encoding="utf-8")
    # New Flow rendering hallmarks
    assert "signatureOf" in html, "Flow must derive a per-session signature"
    assert "distinct path" in html, "Flow header must reference 'distinct paths'"
    # The header tracks the analyzed-session count — matches both "session analyzed"
    # and "sessions analyzed" depending on plural.
    assert "} analyzed" in html, "Flow header must include sessions-analyzed count"
    # Old 2-gram-only string should not be the primary grouping any more.
    assert "unique transition" not in html, "Flow must not regress to 2-gram transitions"
