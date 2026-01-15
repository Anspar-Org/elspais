# Implements: REQ-int-d00001-A (trace_view package at src/elspais/trace_view/)
"""
elspais.trace_view - Interactive traceability matrix generation.

This package provides enhanced traceability features including:
- Interactive HTML generation with collapsible hierarchies
- Implementation file scanning
- Git state tracking (uncommitted, modified, moved files)
- Review system with comment threads and approval workflows

Optional dependencies:
- pip install elspais[trace-view] for HTML generation (requires jinja2)
- pip install elspais[trace-review] for review server (requires flask)
"""

from elspais.trace_view.models import TraceViewRequirement, TestInfo, GitChangeInfo
from elspais.trace_view.generators.base import TraceViewGenerator

__all__ = [
    "TraceViewRequirement",
    "TestInfo",
    "GitChangeInfo",
    "TraceViewGenerator",
    "generate_markdown",
    "generate_csv",
    "generate_html",
]


def generate_markdown(requirements, **kwargs):
    """Generate Markdown traceability matrix."""
    from elspais.trace_view.generators.markdown import generate_markdown as _gen
    return _gen(requirements, **kwargs)


def generate_csv(requirements, **kwargs):
    """Generate CSV traceability matrix."""
    from elspais.trace_view.generators.csv import generate_csv as _gen
    return _gen(requirements, **kwargs)


def generate_html(requirements, **kwargs):
    """Generate interactive HTML traceability matrix.

    Requires jinja2: pip install elspais[trace-view]
    """
    try:
        from elspais.trace_view.html import HTMLGenerator
    except ImportError as e:
        raise ImportError(
            "HTML generation requires Jinja2. "
            "Install with: pip install elspais[trace-view]"
        ) from e
    return HTMLGenerator(requirements, **kwargs).generate()
