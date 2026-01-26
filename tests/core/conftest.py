"""Pytest fixtures for core tests."""

import pytest


@pytest.fixture
def sample_source_location():
    """Create a sample source location."""
    from elspais.graph import SourceLocation

    return SourceLocation(path="spec/prd-auth.md", line=10, end_line=25)


@pytest.fixture
def sample_node():
    """Create a sample graph node."""
    from elspais.graph import GraphNode, NodeKind, SourceLocation

    return GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="User Authentication",
        source=SourceLocation(path="spec/prd-auth.md", line=10),
    )
