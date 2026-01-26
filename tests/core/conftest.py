"""Pytest fixtures for arch3 tests."""

import pytest


@pytest.fixture
def sample_source_location():
    """Create a sample source location."""
    from elspais.arch3.Graph import SourceLocation

    return SourceLocation(path="spec/prd-auth.md", line=10, end_line=25)


@pytest.fixture
def sample_node():
    """Create a sample graph node."""
    from elspais.arch3.Graph import GraphNode, NodeKind, SourceLocation

    return GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="User Authentication",
        source=SourceLocation(path="spec/prd-auth.md", line=10),
    )
