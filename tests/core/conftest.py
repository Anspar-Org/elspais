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
    builder.add_parsed_content(
        make_requirement(
            "REQ-p00001",
            title="User Authentication",
            source_path="spec/prd-auth.md",
            start_line=10,
        )
    )
    return builder.build()


@pytest.fixture
def hierarchy_graph():
    """Graph with PRD -> OPS -> DEV hierarchy."""
    from elspais.graph.builder import GraphBuilder
    from tests.core.graph_test_helpers import make_requirement

    builder = GraphBuilder()
    builder.add_parsed_content(make_requirement("REQ-p00001", level="PRD"))
    builder.add_parsed_content(
        make_requirement("REQ-o00001", level="OPS", implements=["REQ-p00001"])
    )
    builder.add_parsed_content(
        make_requirement("REQ-d00001", level="DEV", implements=["REQ-o00001"])
    )
    return builder.build()


@pytest.fixture
def builder():
    """Fresh GraphBuilder instance."""
    from elspais.graph.builder import GraphBuilder

    return GraphBuilder()


@pytest.fixture
def graph_with_assertions():
    """Requirement with A, B, C assertions."""
    from tests.core.graph_test_helpers import build_graph, make_requirement

    return build_graph(
        make_requirement(
            "REQ-p00001",
            title="Requirement with assertions",
            level="PRD",
            assertions=[
                {"label": "A", "text": "First assertion"},
                {"label": "B", "text": "Second assertion"},
                {"label": "C", "text": "Third assertion"},
            ],
        )
    )


@pytest.fixture
def comprehensive_graph():
    """Graph with requirements, code refs, and test refs."""
    from tests.core.graph_test_helpers import (
        build_graph,
        make_code_ref,
        make_requirement,
        make_test_ref,
    )

    return build_graph(
        make_requirement("REQ-p00001", level="PRD", title="Product requirement"),
        make_requirement("REQ-o00001", level="OPS", implements=["REQ-p00001"]),
        make_requirement("REQ-d00001", level="DEV", implements=["REQ-o00001"]),
        make_code_ref(["REQ-d00001"], source_path="src/auth.py", start_line=10),
        make_test_ref(["REQ-d00001"], source_path="tests/test_auth.py", start_line=5),
    )


@pytest.fixture
def git_modified_files():
    """GitChangeInfo with modified files."""
    from elspais.utilities.git import GitChangeInfo

    return GitChangeInfo(
        modified_files={"spec/prd-auth.md", "spec/ops-api.md"},
        untracked_files=set(),
        branch_changed_files=set(),
        committed_req_locations={"REQ-p00001": "spec/prd-auth.md"},
    )


@pytest.fixture
def git_untracked_files():
    """GitChangeInfo with untracked files."""
    from elspais.utilities.git import GitChangeInfo

    return GitChangeInfo(
        modified_files=set(),
        untracked_files={"spec/new-feature.md", "spec/roadmap/future.md"},
        branch_changed_files=set(),
        committed_req_locations={},
    )
