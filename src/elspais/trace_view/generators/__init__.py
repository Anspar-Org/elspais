# Implements: REQ-int-d00001-A (trace_view package structure)
"""
elspais.trace_view.generators - Output format generators.

Provides Markdown and CSV generators (no dependencies).
HTML generator is in the html/ subpackage (requires jinja2).
"""

from elspais.trace_view.generators.markdown import generate_markdown
from elspais.trace_view.generators.csv import generate_csv

__all__ = ["generate_markdown", "generate_csv"]
