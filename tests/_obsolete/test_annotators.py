# Implements: REQ-d00050, REQ-d00051, REQ-o00051
"""Tests for core/annotators.py - composable node annotation functions.

REQ-d00050: Node Annotator Functions
REQ-d00051: Graph Aggregate Functions
REQ-o00051: Composable Annotation Design
"""

from pathlib import Path

import pytest

from elspais.core.graph import NodeKind, SourceLocation, TraceGraph, TraceNode
from elspais.core.graph_builder import TraceGraphBuilder
from elspais.core.models import Assertion, Requirement


def create_test_requirement(
    req_id: str = "REQ-d00001",
    title: str = "Test Requirement",
    level: str = "DEV",
    status: str = "Active",
    implements: list[str] | None = None,
    file_path: Path | None = None,
    is_conflict: bool = False,
    conflict_with: str | None = None,
    repo_prefix: str | None = None,
) -> Requirement:
    """Helper to create test requirements."""
    req = Requirement(
        id=req_id,
        title=title,
        level=level,
        status=status,
        implements=implements or [],
        body="Test body",
        rationale="Test rationale",
        hash="abc12345",
        file_path=file_path or Path("spec/test.md"),
        line_number=10,
    )
    # Set optional attributes
    req.is_conflict = is_conflict
    req.conflict_with = conflict_with
    if repo_prefix:
        req.repo_prefix = repo_prefix
    return req


def build_test_graph(requirements: list[Requirement]) -> TraceGraph:
    """Build a TraceGraph from requirements."""
    builder = TraceGraphBuilder(repo_root=Path("."))
    reqs_dict = {req.id: req for req in requirements}
    builder.add_requirements(reqs_dict)
    return builder.build()


class TestAnnotateGitState:
    """Test annotate_git_state function."""

    def test_annotate_git_state_no_git_info(self):
        """Test with git_info=None - all states default to False."""
        from elspais.core.annotators import annotate_git_state

        req = create_test_requirement()
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        annotate_git_state(node, None)

        assert node.metrics["is_uncommitted"] is False
        assert node.metrics["is_untracked"] is False
        assert node.metrics["is_branch_changed"] is False
        assert node.metrics["is_moved"] is False
        assert node.metrics["is_modified"] is False
        assert node.metrics["is_new"] is False

    def test_annotate_git_state_untracked_file(self):
        """Test with untracked file - is_uncommitted, is_untracked, is_new should be True."""
        from elspais.core.annotators import annotate_git_state
        from elspais.core.git import GitChangeInfo

        req = create_test_requirement(file_path=Path("spec/new-file.md"))
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        git_info = GitChangeInfo(
            untracked_files={"spec/new-file.md"},
            modified_files=set(),
            branch_changed_files=set(),
            committed_req_locations={},
        )
        annotate_git_state(node, git_info)

        assert node.metrics["is_uncommitted"] is True
        assert node.metrics["is_untracked"] is True
        assert node.metrics["is_new"] is True
        assert node.metrics["is_modified"] is False

    def test_annotate_git_state_modified_file(self):
        """Test with modified file - is_uncommitted, is_modified should be True."""
        from elspais.core.annotators import annotate_git_state
        from elspais.core.git import GitChangeInfo

        req = create_test_requirement(file_path=Path("spec/existing.md"))
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        git_info = GitChangeInfo(
            untracked_files=set(),
            modified_files={"spec/existing.md"},
            branch_changed_files=set(),
            committed_req_locations={},
        )
        annotate_git_state(node, git_info)

        assert node.metrics["is_uncommitted"] is True
        assert node.metrics["is_modified"] is True
        assert node.metrics["is_untracked"] is False
        assert node.metrics["is_new"] is False

    def test_annotate_git_state_branch_changed(self):
        """Test with file changed vs main branch."""
        from elspais.core.annotators import annotate_git_state
        from elspais.core.git import GitChangeInfo

        req = create_test_requirement(file_path=Path("spec/feature.md"))
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        git_info = GitChangeInfo(
            untracked_files=set(),
            modified_files=set(),
            branch_changed_files={"spec/feature.md"},
            committed_req_locations={},
        )
        annotate_git_state(node, git_info)

        assert node.metrics["is_branch_changed"] is True
        assert node.metrics["is_uncommitted"] is False

    def test_annotate_git_state_moved_requirement(self):
        """Test with requirement moved from different file."""
        from elspais.core.annotators import annotate_git_state
        from elspais.core.git import GitChangeInfo

        req = create_test_requirement(
            req_id="REQ-d00001",
            file_path=Path("spec/new-location.md"),
        )
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        git_info = GitChangeInfo(
            untracked_files=set(),
            modified_files=set(),
            branch_changed_files=set(),
            committed_req_locations={"d00001": "spec/old-location.md"},
        )
        annotate_git_state(node, git_info)

        assert node.metrics["is_moved"] is True

    def test_annotate_git_state_skips_non_requirement_nodes(self):
        """Test that non-REQUIREMENT nodes are skipped."""
        from elspais.core.annotators import annotate_git_state

        # Create an assertion node manually
        node = TraceNode(
            id="REQ-d00001-A",
            kind=NodeKind.ASSERTION,
            label="Assertion A",
            source=SourceLocation(path="spec/test.md", line=10),
        )
        node.metrics = {}

        annotate_git_state(node, None)

        # Should not have added any metrics
        assert "is_uncommitted" not in node.metrics


class TestAnnotateDisplayInfo:
    """Test annotate_display_info function."""

    def test_annotate_display_info_normal_requirement(self):
        """Test normal requirement display info."""
        from elspais.core.annotators import annotate_display_info

        req = create_test_requirement(file_path=Path("spec/01-authentication.md"))
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        annotate_display_info(node)

        assert node.metrics["is_roadmap"] is False
        assert node.metrics["is_conflict"] is False
        assert node.metrics["display_filename"] == "01-authentication"
        assert node.metrics["file_name"] == "01-authentication.md"
        assert node.metrics["repo_prefix"] == "CORE"

    def test_annotate_display_info_roadmap_requirement(self):
        """Test roadmap requirement detection."""
        from elspais.core.annotators import annotate_display_info

        req = create_test_requirement(file_path=Path("spec/roadmap/future-feature.md"))
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        annotate_display_info(node)

        assert node.metrics["is_roadmap"] is True

    def test_annotate_display_info_conflict_requirement(self):
        """Test conflict requirement detection."""
        from elspais.core.annotators import annotate_display_info

        # Create a requirement with conflict attributes set and test directly
        req = Requirement(
            id="REQ-d00002",
            title="Conflict Requirement",
            level="DEV",
            status="Active",
            implements=[],
            body="Test body",
            rationale="",
            hash="abc12345",
            file_path=Path("spec/test.md"),
            line_number=10,
        )
        req.is_conflict = True
        req.conflict_with = "REQ-d00001"

        # Create node directly to test annotator in isolation
        node = TraceNode(
            id=req.id,
            kind=NodeKind.REQUIREMENT,
            label=req.title,
            source=SourceLocation(path="spec/test.md", line=10),
            requirement=req,
        )
        node.metrics = {}

        annotate_display_info(node)

        assert node.metrics["is_conflict"] is True
        assert node.metrics["conflict_with"] == "REQ-d00001"

    def test_annotate_display_info_with_repo_prefix(self):
        """Test repo prefix handling."""
        from elspais.core.annotators import annotate_display_info

        req = create_test_requirement(repo_prefix="CAL")
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        annotate_display_info(node)

        assert node.metrics["repo_prefix"] == "CAL"

    def test_annotate_display_info_no_file_path(self):
        """Test with no file path."""
        from elspais.core.annotators import annotate_display_info

        req = create_test_requirement()
        req.file_path = None
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        annotate_display_info(node)

        assert node.metrics["display_filename"] == ""
        assert node.metrics["file_name"] == ""


class TestAnnotateImplementationFiles:
    """Test annotate_implementation_files function."""

    def test_annotate_implementation_files_single(self):
        """Test adding a single implementation file."""
        from elspais.core.annotators import annotate_implementation_files

        req = create_test_requirement()
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        annotate_implementation_files(node, [("src/auth.py", 42)])

        assert node.metrics["implementation_files"] == [("src/auth.py", 42)]

    def test_annotate_implementation_files_multiple(self):
        """Test adding multiple implementation files."""
        from elspais.core.annotators import annotate_implementation_files

        req = create_test_requirement()
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        annotate_implementation_files(node, [("src/auth.py", 42), ("src/login.py", 100)])

        assert node.metrics["implementation_files"] == [
            ("src/auth.py", 42),
            ("src/login.py", 100),
        ]

    def test_annotate_implementation_files_extends_existing(self):
        """Test that files extend existing list."""
        from elspais.core.annotators import annotate_implementation_files

        req = create_test_requirement()
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        annotate_implementation_files(node, [("src/auth.py", 42)])
        annotate_implementation_files(node, [("src/login.py", 100)])

        assert node.metrics["implementation_files"] == [
            ("src/auth.py", 42),
            ("src/login.py", 100),
        ]

    def test_annotate_implementation_files_skips_non_requirement(self):
        """Test that non-REQUIREMENT nodes are skipped."""
        from elspais.core.annotators import annotate_implementation_files

        node = TraceNode(
            id="REQ-d00001-A",
            kind=NodeKind.ASSERTION,
            label="Assertion A",
            source=SourceLocation(path="spec/test.md", line=10),
        )
        node.metrics = {}

        annotate_implementation_files(node, [("src/auth.py", 42)])

        assert "implementation_files" not in node.metrics


class TestCountByLevel:
    """Test count_by_level aggregate function."""

    def test_count_by_level_single_requirement(self):
        """Test counting a single requirement."""
        from elspais.core.annotators import count_by_level

        req = create_test_requirement(level="DEV", status="Active")
        graph = build_test_graph([req])

        counts = count_by_level(graph)

        assert counts["active"]["DEV"] == 1
        assert counts["all"]["DEV"] == 1
        assert counts["active"]["PRD"] == 0
        assert counts["active"]["OPS"] == 0

    def test_count_by_level_multiple_levels(self):
        """Test counting requirements across levels."""
        from elspais.core.annotators import count_by_level

        reqs = [
            create_test_requirement(req_id="REQ-p00001", level="PRD"),
            create_test_requirement(req_id="REQ-o00001", level="OPS"),
            create_test_requirement(req_id="REQ-d00001", level="DEV"),
            create_test_requirement(req_id="REQ-d00002", level="DEV"),
        ]
        graph = build_test_graph(reqs)

        counts = count_by_level(graph)

        assert counts["active"]["PRD"] == 1
        assert counts["active"]["OPS"] == 1
        assert counts["active"]["DEV"] == 2
        assert counts["all"]["DEV"] == 2

    def test_count_by_level_excludes_deprecated(self):
        """Test that deprecated requirements are in 'all' but not 'active'."""
        from elspais.core.annotators import count_by_level

        reqs = [
            create_test_requirement(req_id="REQ-d00001", level="DEV", status="Active"),
            create_test_requirement(req_id="REQ-d00002", level="DEV", status="Deprecated"),
        ]
        graph = build_test_graph(reqs)

        counts = count_by_level(graph)

        assert counts["active"]["DEV"] == 1
        assert counts["all"]["DEV"] == 2


class TestCountByRepo:
    """Test count_by_repo aggregate function."""

    def test_count_by_repo_default_core(self):
        """Test that default repo prefix is CORE."""
        from elspais.core.annotators import annotate_display_info, count_by_repo

        req = create_test_requirement()
        graph = build_test_graph([req])

        # Need to annotate first to set repo_prefix in metrics
        for node in graph.all_nodes():
            if node.kind == NodeKind.REQUIREMENT:
                annotate_display_info(node)

        counts = count_by_repo(graph)

        assert "CORE" in counts
        assert counts["CORE"]["active"] == 1
        assert counts["CORE"]["all"] == 1

    def test_count_by_repo_multiple_repos(self):
        """Test counting across multiple repos."""
        from elspais.core.annotators import annotate_display_info, count_by_repo

        reqs = [
            create_test_requirement(req_id="REQ-d00001"),
            create_test_requirement(req_id="REQ-CAL-d00001", repo_prefix="CAL"),
            create_test_requirement(req_id="REQ-TTN-d00001", repo_prefix="TTN"),
        ]
        graph = build_test_graph(reqs)

        # Annotate to set repo_prefix
        for node in graph.all_nodes():
            if node.kind == NodeKind.REQUIREMENT:
                annotate_display_info(node)

        counts = count_by_repo(graph)

        assert counts["CORE"]["active"] == 1
        assert counts["CAL"]["active"] == 1
        assert counts["TTN"]["active"] == 1


class TestCountImplementationFiles:
    """Test count_implementation_files aggregate function."""

    def test_count_implementation_files_empty(self):
        """Test with no implementation files."""
        from elspais.core.annotators import count_implementation_files

        req = create_test_requirement()
        graph = build_test_graph([req])

        count = count_implementation_files(graph)

        assert count == 0

    def test_count_implementation_files_with_files(self):
        """Test counting implementation files."""
        from elspais.core.annotators import (
            annotate_implementation_files,
            count_implementation_files,
        )

        reqs = [
            create_test_requirement(req_id="REQ-d00001"),
            create_test_requirement(req_id="REQ-d00002"),
        ]
        graph = build_test_graph(reqs)

        # Add implementation files to nodes
        node1 = graph.find_by_id("REQ-d00001")
        node2 = graph.find_by_id("REQ-d00002")
        annotate_implementation_files(node1, [("src/auth.py", 10), ("src/login.py", 20)])
        annotate_implementation_files(node2, [("src/user.py", 30)])

        count = count_implementation_files(graph)

        assert count == 3


class TestCollectTopics:
    """Test collect_topics aggregate function."""

    def test_collect_topics_single(self):
        """Test collecting a single topic."""
        from elspais.core.annotators import collect_topics

        req = create_test_requirement(file_path=Path("spec/01-authentication.md"))
        graph = build_test_graph([req])

        topics = collect_topics(graph)

        assert topics == ["authentication"]

    def test_collect_topics_multiple(self):
        """Test collecting multiple topics."""
        from elspais.core.annotators import collect_topics

        reqs = [
            create_test_requirement(req_id="REQ-d00001", file_path=Path("spec/01-authentication.md")),
            create_test_requirement(req_id="REQ-d00002", file_path=Path("spec/02-authorization.md")),
            create_test_requirement(req_id="REQ-d00003", file_path=Path("spec/03-validation.md")),
        ]
        graph = build_test_graph(reqs)

        topics = collect_topics(graph)

        assert topics == ["authentication", "authorization", "validation"]

    def test_collect_topics_unique(self):
        """Test that topics are unique."""
        from elspais.core.annotators import collect_topics

        reqs = [
            create_test_requirement(req_id="REQ-d00001", file_path=Path("spec/01-authentication.md")),
            create_test_requirement(req_id="REQ-d00002", file_path=Path("spec/01-authentication.md")),
        ]
        graph = build_test_graph(reqs)

        topics = collect_topics(graph)

        assert topics == ["authentication"]

    def test_collect_topics_no_prefix(self):
        """Test topic extraction with no numeric prefix."""
        from elspais.core.annotators import collect_topics

        req = create_test_requirement(file_path=Path("spec/requirements.md"))
        graph = build_test_graph([req])

        topics = collect_topics(graph)

        assert topics == ["requirements"]


class TestGetImplementationStatus:
    """Test get_implementation_status function."""

    def test_get_implementation_status_full(self):
        """Test full implementation status (coverage >= 100%)."""
        from elspais.core.annotators import get_implementation_status

        node = TraceNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="Test Requirement",
            source=SourceLocation(path="spec/test.md", line=10),
        )
        node.metrics = {"coverage_pct": 100}

        status = get_implementation_status(node)

        assert status == "Full"

    def test_get_implementation_status_partial(self):
        """Test partial implementation status (0 < coverage < 100)."""
        from elspais.core.annotators import get_implementation_status

        node = TraceNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="Test Requirement",
            source=SourceLocation(path="spec/test.md", line=10),
        )
        node.metrics = {"coverage_pct": 50}

        status = get_implementation_status(node)

        assert status == "Partial"

    def test_get_implementation_status_unimplemented(self):
        """Test unimplemented status (coverage == 0)."""
        from elspais.core.annotators import get_implementation_status

        node = TraceNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="Test Requirement",
            source=SourceLocation(path="spec/test.md", line=10),
        )
        node.metrics = {"coverage_pct": 0}

        status = get_implementation_status(node)

        assert status == "Unimplemented"

    def test_get_implementation_status_no_coverage(self):
        """Test with no coverage_pct metric (defaults to 0)."""
        from elspais.core.annotators import get_implementation_status

        node = TraceNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="Test Requirement",
            source=SourceLocation(path="spec/test.md", line=10),
        )
        node.metrics = {}

        status = get_implementation_status(node)

        assert status == "Unimplemented"


class TestComposablePattern:
    """Test the composable annotation pattern (REQ-o00051)."""

    def test_annotation_pipeline(self):
        """Test that annotations can be composed in sequence."""
        from elspais.core.annotators import (
            annotate_display_info,
            annotate_git_state,
            annotate_implementation_files,
        )

        req = create_test_requirement(file_path=Path("spec/roadmap/feature.md"))
        graph = build_test_graph([req])

        # Apply annotations in sequence (like a pipeline)
        for node in graph.all_nodes():
            if node.kind == NodeKind.REQUIREMENT:
                # Phase 1: Git state
                annotate_git_state(node, None)
                # Phase 2: Display info
                annotate_display_info(node)
                # Phase 3: Implementation files
                annotate_implementation_files(node, [("src/feature.py", 10)])

        # Verify all annotations were applied
        node = graph.find_by_id("REQ-d00001")
        assert "is_uncommitted" in node.metrics  # From git state
        assert "is_roadmap" in node.metrics  # From display info
        assert node.metrics["is_roadmap"] is True
        assert "implementation_files" in node.metrics  # From impl files
        assert node.metrics["implementation_files"] == [("src/feature.py", 10)]

    def test_annotators_are_idempotent(self):
        """Test that annotators can be called multiple times safely."""
        from elspais.core.annotators import annotate_display_info

        req = create_test_requirement()
        graph = build_test_graph([req])
        node = graph.find_by_id("REQ-d00001")

        # Call twice
        annotate_display_info(node)
        first_metrics = dict(node.metrics)
        annotate_display_info(node)
        second_metrics = dict(node.metrics)

        # Should produce same result
        assert first_metrics == second_metrics
