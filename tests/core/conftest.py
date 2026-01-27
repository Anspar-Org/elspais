"""Pytest fixtures for core tests."""

import pytest


@pytest.fixture
def sample_source_location():
    """Create a sample source location."""
    from elspais.graph import SourceLocation

    return SourceLocation(path="spec/prd-auth.md", line=10, end_line=25)


@pytest.fixture
def simple_graph():
    """Create a simple graph with one requirement."""
    from elspais.graph.builder import GraphBuilder
    from tests.core.graph_test_helpers import make_requirement

    builder = GraphBuilder()
    builder.add_parsed_content(make_requirement(
        "REQ-p00001",
        title="User Authentication",
        source_path="spec/prd-auth.md",
        start_line=10,
    ))
    return builder.build()


@pytest.fixture
def hierarchy_graph():
    """Graph with PRD -> OPS -> DEV hierarchy."""
    from elspais.graph.builder import GraphBuilder
    from tests.core.graph_test_helpers import make_requirement

    builder = GraphBuilder()
    builder.add_parsed_content(make_requirement("REQ-p00001", level="PRD"))
    builder.add_parsed_content(make_requirement("REQ-o00001", level="OPS", implements=["REQ-p00001"]))
    builder.add_parsed_content(make_requirement("REQ-d00001", level="DEV", implements=["REQ-o00001"]))
    return builder.build()
