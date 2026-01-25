# Implements: REQ-int-d00002-B (HTML generation requires jinja2)
"""
elspais.trace_view.html - Interactive HTML generation.

Requires: pip install elspais[trace-view]
"""


def _check_jinja2():
    try:
        import jinja2  # noqa: F401

        return True
    except ImportError:
        return False


JINJA2_AVAILABLE = _check_jinja2()

if JINJA2_AVAILABLE:
    from elspais.trace_view.html.generator import HTMLGenerator

    __all__ = ["HTMLGenerator", "JINJA2_AVAILABLE"]
else:
    __all__ = ["JINJA2_AVAILABLE"]

    class HTMLGenerator:
        """Placeholder when jinja2 is not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "HTMLGenerator requires Jinja2. " "Install with: pip install elspais[trace-view]"
            )
