"""Tests for Graph Annotators."""

import pytest

from elspais.graph import NodeKind
from elspais.graph.GraphNode import GraphNode, SourceLocation
from elspais.graph.builder import TraceGraph
from elspais.utilities.git import GitChangeInfo
from elspais.graph.annotators import (
    annotate_git_state,
    annotate_display_info,
    annotate_implementation_files,
    count_by_level,
    count_by_repo,
    count_implementation_files,
    collect_topics,
    get_implementation_status,
)


class TestAnnotateGitState:
    """Tests for annotate_git_state function."""

    def test_annotates_uncommitted(self):
        """Marks node as uncommitted when file is modified."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/prd.md", line=1),
        )
        git_info = GitChangeInfo(
            modified_files={"spec/prd.md"},
        )

        annotate_git_state(node, git_info)

        assert node.get_metric("is_uncommitted") is True
        assert node.get_metric("is_modified") is True
        assert node.get_metric("is_untracked") is False

    def test_annotates_untracked(self):
        """Marks node as untracked when file is new."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/new.md", line=1),
        )
        git_info = GitChangeInfo(
            untracked_files={"spec/new.md"},
        )

        annotate_git_state(node, git_info)

        assert node.get_metric("is_uncommitted") is True
        assert node.get_metric("is_untracked") is True
        assert node.get_metric("is_new") is True

    def test_annotates_branch_changed(self):
        """Marks node when file differs from main branch."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/prd.md", line=1),
        )
        git_info = GitChangeInfo(
            branch_changed_files={"spec/prd.md"},
        )

        annotate_git_state(node, git_info)

        assert node.get_metric("is_branch_changed") is True

    def test_annotates_moved(self):
        """Marks node as moved when file location changed."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/new.md", line=1),
            _content={"id": "REQ-p00001"},
        )
        git_info = GitChangeInfo(
            committed_req_locations={"p00001": "spec/old.md"},
        )

        annotate_git_state(node, git_info)

        assert node.get_metric("is_moved") is True

    def test_defaults_to_false(self):
        """All git states default to False when no git info."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/prd.md", line=1),
        )

        annotate_git_state(node, None)

        assert node.get_metric("is_uncommitted") is False
        assert node.get_metric("is_modified") is False
        assert node.get_metric("is_untracked") is False
        assert node.get_metric("is_branch_changed") is False
        assert node.get_metric("is_moved") is False
        assert node.get_metric("is_new") is False

    def test_skips_non_requirement_nodes(self):
        """Does not annotate non-requirement nodes."""
        node = GraphNode(
            id="REQ-p00001-A",
            kind=NodeKind.ASSERTION,
        )
        git_info = GitChangeInfo(modified_files={"spec/prd.md"})

        annotate_git_state(node, git_info)

        assert node.get_metric("is_uncommitted") is None


class TestAnnotateDisplayInfo:
    """Tests for annotate_display_info function."""

    def test_annotates_roadmap(self):
        """Marks node as roadmap when in roadmap directory."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/roadmap/future.md", line=1),
        )

        annotate_display_info(node)

        assert node.get_metric("is_roadmap") is True

    def test_annotates_not_roadmap(self):
        """Marks node as not roadmap when not in roadmap directory."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/prd.md", line=1),
        )

        annotate_display_info(node)

        assert node.get_metric("is_roadmap") is False

    def test_annotates_conflict(self):
        """Marks node as conflict when is_conflict is True."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            _content={"is_conflict": True, "conflict_with": "REQ-p00001__conflict"},
        )

        annotate_display_info(node)

        assert node.get_metric("is_conflict") is True
        assert node.get_metric("conflict_with") == "REQ-p00001__conflict"

    def test_annotates_display_filename(self):
        """Stores display-friendly filename info."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/prd-authentication.md", line=1),
        )

        annotate_display_info(node)

        assert node.get_metric("display_filename") == "prd-authentication"
        assert node.get_metric("file_name") == "prd-authentication.md"

    def test_annotates_repo_prefix(self):
        """Stores repo prefix from content."""
        node = GraphNode(
            id="REQ-CAL-p00001",
            kind=NodeKind.REQUIREMENT,
            _content={"repo_prefix": "CAL"},
        )

        annotate_display_info(node)

        assert node.get_metric("repo_prefix") == "CAL"

    def test_defaults_to_core_prefix(self):
        """Defaults to CORE when no repo prefix."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
        )

        annotate_display_info(node)

        assert node.get_metric("repo_prefix") == "CORE"


class TestAnnotateImplementationFiles:
    """Tests for annotate_implementation_files function."""

    def test_adds_implementation_files(self):
        """Stores implementation file references."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
        )
        impl_files = [("src/auth.py", 42), ("src/login.py", 10)]

        annotate_implementation_files(node, impl_files)

        assert node.get_metric("implementation_files") == impl_files

    def test_appends_to_existing(self):
        """Appends to existing implementation files."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            _metrics={"implementation_files": [("src/old.py", 1)]},
        )
        impl_files = [("src/new.py", 2)]

        annotate_implementation_files(node, impl_files)

        assert len(node.get_metric("implementation_files")) == 2


class TestCountByLevel:
    """Tests for count_by_level function."""

    def test_counts_by_level(self):
        """Counts requirements by level."""
        graph = TraceGraph()
        graph._index = {
            "REQ-p00001": GraphNode(
                id="REQ-p00001",
                kind=NodeKind.REQUIREMENT,
                _content={"level": "PRD", "status": "Active"},
            ),
            "REQ-o00001": GraphNode(
                id="REQ-o00001",
                kind=NodeKind.REQUIREMENT,
                _content={"level": "OPS", "status": "Active"},
            ),
            "REQ-d00001": GraphNode(
                id="REQ-d00001",
                kind=NodeKind.REQUIREMENT,
                _content={"level": "DEV", "status": "Deprecated"},
            ),
        }

        counts = count_by_level(graph)

        assert counts["active"]["PRD"] == 1
        assert counts["active"]["OPS"] == 1
        assert counts["active"]["DEV"] == 0  # Deprecated
        assert counts["all"]["DEV"] == 1


class TestCountByRepo:
    """Tests for count_by_repo function."""

    def test_counts_by_repo(self):
        """Counts requirements by repo prefix."""
        node1 = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            _content={"status": "Active"},
            _metrics={"repo_prefix": "CORE"},
        )
        node2 = GraphNode(
            id="REQ-CAL-p00001",
            kind=NodeKind.REQUIREMENT,
            _content={"status": "Active"},
            _metrics={"repo_prefix": "CAL"},
        )
        graph = TraceGraph()
        graph._index = {"REQ-p00001": node1, "REQ-CAL-p00001": node2}

        counts = count_by_repo(graph)

        assert counts["CORE"]["active"] == 1
        assert counts["CAL"]["active"] == 1


class TestCountImplementationFiles:
    """Tests for count_implementation_files function."""

    def test_counts_total_files(self):
        """Counts total implementation files."""
        node1 = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            _metrics={"implementation_files": [("a.py", 1), ("b.py", 2)]},
        )
        node2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            _metrics={"implementation_files": [("c.py", 3)]},
        )
        graph = TraceGraph()
        graph._index = {"REQ-p00001": node1, "REQ-p00002": node2}

        total = count_implementation_files(graph)

        assert total == 3


class TestCollectTopics:
    """Tests for collect_topics function."""

    def test_collects_topics_from_filenames(self):
        """Extracts topics from file stems."""
        node1 = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/prd-authentication.md", line=1),
        )
        node2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/prd-billing.md", line=1),
        )
        graph = TraceGraph()
        graph._index = {"REQ-p00001": node1, "REQ-p00002": node2}

        topics = collect_topics(graph)

        assert "authentication" in topics
        assert "billing" in topics


class TestGetImplementationStatus:
    """Tests for get_implementation_status function."""

    def test_full_coverage(self):
        """Returns Full when coverage is 100%."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            _metrics={"coverage_pct": 100},
        )

        status = get_implementation_status(node)

        assert status == "Full"

    def test_partial_coverage(self):
        """Returns Partial when coverage is between 0 and 100."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            _metrics={"coverage_pct": 50},
        )

        status = get_implementation_status(node)

        assert status == "Partial"

    def test_unimplemented(self):
        """Returns Unimplemented when coverage is 0."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            _metrics={"coverage_pct": 0},
        )

        status = get_implementation_status(node)

        assert status == "Unimplemented"

    def test_defaults_to_unimplemented(self):
        """Defaults to Unimplemented when no coverage metric."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
        )

        status = get_implementation_status(node)

        assert status == "Unimplemented"
