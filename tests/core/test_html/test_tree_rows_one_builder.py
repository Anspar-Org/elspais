# Verifies: REQ-p00006-A, REQ-p00006-B
"""The navigation tree is drawn from one builder, whatever serves the page.

A page that embeds its data and a page served by the viewer draw the same
tree. Two builders drifted apart: the embedded one returned a map keyed by
requirement where every reader of the rows expects a list, so the tree drew
nothing and said nothing about why.
"""

from __future__ import annotations

import json
import re

import pytest

from elspais.html.generator import HTMLGenerator
from elspais.view_model import build_tree_rows
from tests.core.graph_test_helpers import build_graph, make_journey, make_requirement


@pytest.fixture
def graph():
    return build_graph(
        make_requirement(
            "REQ-p00001",
            level="PRD",
            title="Product Requirement",
            assertions=[{"label": "A", "text": "First assertion"}],
            source_path="spec/prd.md",
        ),
        make_journey("JNY-LOGIN-01", title="Login Flow", source_path="spec/journeys.md"),
    )


# Verifies: REQ-p00006-A
def test_the_embedded_rows_are_a_list(graph):
    """A page embeds its rows in the shape its readers iterate.

    Every reader takes the rows as a list. A map passes the emptiness guard,
    because a map has no length, and each loop over it then runs no times --
    so the tree is blank and nothing reports a fault.
    """
    html = HTMLGenerator(graph).generate(embed_content=True)

    embedded = json.loads(re.search(r'id="tree-data">(.*?)</script>', html, re.S).group(1))

    assert isinstance(embedded, list), f"rows must be a list, got {type(embedded).__name__}"
    assert embedded, "a graph holding requirements yields rows"


# Verifies: REQ-p00006-A
def test_the_embedded_rows_are_the_rows_the_route_serves(graph):
    """One builder answers for both pages, so the two cannot disagree."""
    html = HTMLGenerator(graph).generate(embed_content=True)

    embedded = json.loads(re.search(r'id="tree-data">(.*?)</script>', html, re.S).group(1))
    served = build_tree_rows(graph, {})

    assert embedded == served


# Verifies: REQ-p00006-B
def test_a_journey_reaches_the_tree(graph):
    """A journey is a row of its own, beside the requirements."""
    rows = build_tree_rows(graph, {})

    kinds = {row["kind"] for row in rows}
    assert kinds == {"requirement", "journey"}
