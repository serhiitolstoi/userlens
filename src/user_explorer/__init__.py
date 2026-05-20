"""User Explorer — turn an event log into per-user analytics + an HTML report.

Library usage::

    from pathlib import Path
    from user_explorer import run, PipelineOptions, render

    result = run(PipelineOptions(events_path=Path("events.csv")))
    render(result.blobs, result.meta, Path("report.html"), open_browser=False)

    # Or work with the structured data directly:
    from user_explorer import extract_insights
    insights = extract_insights(result.blobs[0], result.blobs)

Importing this package does not require the optional ``[mcp]`` extra.
"""

from user_explorer.insights import extract_insights
from user_explorer.io import read_events
from user_explorer.pipeline import PipelineOptions, PipelineResult, run
from user_explorer.version import __version__
from user_explorer.viewer import render

__all__ = [
    "PipelineOptions",
    "PipelineResult",
    "run",
    "render",
    "extract_insights",
    "read_events",
    "__version__",
]
