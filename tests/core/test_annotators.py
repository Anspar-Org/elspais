"""Tests for Graph Annotators."""

from elspais.graph import NodeKind
from elspais.graph.annotators import (
    annotate_display_info,
    annotate_git_state,
    annotate_implementation_files,
    collect_topics,
    count_by_level,
    count_by_repo,
    count_implementation_files,
    get_implementation_status,
)
from elspais.graph.GraphNode import GraphNode, SourceLocation
from elspais.utilities.git import GitChangeInfo
from tests.core.graph_test_helpers import build_graph, make_requirement


class TestAnnotateGitState:
    """Tests for annotate_git_state function."""

    def test_REQ_d00050_E_git_state_is_idempotent(self):
        """REQ-d00050-E: Annotator functions SHALL be idempotent."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/prd.md", line=1),
        )
        git_info = GitChangeInfo(
            modified_files={"spec/prd.md"},
            branch_changed_files={"spec/prd.md"},
        )

        # First call
        annotate_git_state(node, git_info)
        first_uncommitted = node.get_metric("is_uncommitted")
        first_modified = node.get_metric("is_modified")
        first_branch_changed = node.get_metric("is_branch_changed")

        # Second call - should produce same results
        annotate_git_state(node, git_info)
        second_uncommitted = node.get_metric("is_uncommitted")
        second_modified = node.get_metric("is_modified")
        second_branch_changed = node.get_metric("is_branch_changed")

        assert first_uncommitted == second_uncommitted
        assert first_modified == second_modified
        assert first_branch_changed == second_branch_changed

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
        )
        node.set_field("id", "REQ-p00001")
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

    def test_handles_assertion_id_format(self):
        """Handles requirement ID with assertion suffix for move detection."""
        # Assertion nodes (REQ-xxx-A) should be skipped
        node = GraphNode(
            id="REQ-p00001-A",
            kind=NodeKind.ASSERTION,
            source=SourceLocation(path="spec/prd.md", line=5),
        )
        git_info = GitChangeInfo(
            committed_req_locations={"p00001": "spec/old.md"},
        )

        # Should not raise and should not annotate
        annotate_git_state(node, git_info)

        assert node.get_metric("is_moved") is None


class TestAnnotateDisplayInfo:
    """Tests for annotate_display_info function."""

    def test_REQ_d00050_E_display_info_is_idempotent(self):
        """REQ-d00050-E: Annotator functions SHALL be idempotent."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=SourceLocation(path="spec/roadmap/future.md", line=1),
        )
        node.set_field("repo_prefix", "CAL")

        # First call
        annotate_display_info(node)
        first_roadmap = node.get_metric("is_roadmap")
        first_prefix = node.get_metric("repo_prefix")
        first_filename = node.get_metric("display_filename")

        # Second call - should produce same results
        annotate_display_info(node)
        second_roadmap = node.get_metric("is_roadmap")
        second_prefix = node.get_metric("repo_prefix")
        second_filename = node.get_metric("display_filename")

        assert first_roadmap == second_roadmap
        assert first_prefix == second_prefix
        assert first_filename == second_filename

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
        )
        node.set_field("is_conflict", True)
        node.set_field("conflict_with", "REQ-p00001__conflict")

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
        )
        node.set_field("repo_prefix", "CAL")

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
        )
        node.set_metric("implementation_files", [("src/old.py", 1)])
        impl_files = [("src/new.py", 2)]

        annotate_implementation_files(node, impl_files)

        files = node.get_metric("implementation_files")
        assert len(files) == 2
        assert ("src/old.py", 1) in files
        assert ("src/new.py", 2) in files


class TestCountByLevel:
    """Tests for count_by_level function."""

    def test_counts_by_level(self):
        """Counts requirements by level."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", status="Active"),
            make_requirement("REQ-o00001", level="OPS", status="Active"),
            make_requirement("REQ-d00001", level="DEV", status="Deprecated"),
        )

        counts = count_by_level(graph)

        assert counts["active"]["PRD"] == 1
        assert counts["active"]["OPS"] == 1
        assert counts["active"]["DEV"] == 0  # Deprecated
        assert counts["all"]["DEV"] == 1


class TestCountByRepo:
    """Tests for count_by_repo function."""

    def test_counts_by_repo(self):
        """Counts requirements by repo prefix."""
        graph = build_graph(
            make_requirement("REQ-p00001", status="Active"),
            make_requirement("REQ-CAL-p00001", status="Active"),
        )
        # Annotate with repo prefixes using public API
        node1 = graph.find_by_id("REQ-p00001")
        node1.set_metric("repo_prefix", "CORE")
        node2 = graph.find_by_id("REQ-CAL-p00001")
        node2.set_metric("repo_prefix", "CAL")

        counts = count_by_repo(graph)

        assert counts["CORE"]["active"] == 1
        assert counts["CAL"]["active"] == 1


class TestCountImplementationFiles:
    """Tests for count_implementation_files function."""

    def test_counts_total_files(self):
        """Counts total implementation files."""
        graph = build_graph(
            make_requirement("REQ-p00001"),
            make_requirement("REQ-p00002"),
        )
        # Set implementation files using public API
        node1 = graph.find_by_id("REQ-p00001")
        node1.set_metric("implementation_files", [("a.py", 1), ("b.py", 2)])
        node2 = graph.find_by_id("REQ-p00002")
        node2.set_metric("implementation_files", [("c.py", 3)])

        total = count_implementation_files(graph)

        assert total == 3


class TestCollectTopics:
    """Tests for collect_topics function."""

    def test_collects_topics_from_filenames(self):
        """Extracts topics from file stems."""
        graph = build_graph(
            make_requirement("REQ-p00001", source_path="spec/prd-authentication.md"),
            make_requirement("REQ-p00002", source_path="spec/prd-billing.md"),
        )

        topics = collect_topics(graph)

        assert "authentication" in topics
        assert "billing" in topics


class TestGetImplementationStatus:
    """Tests for get_implementation_status function."""

    def test_full_coverage(self):
        """Returns Full when coverage is 100%."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_metric("coverage_pct", 100)

        status = get_implementation_status(node)

        assert status == "Full"

    def test_partial_coverage(self):
        """Returns Partial when coverage is between 0 and 100."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_metric("coverage_pct", 50)

        status = get_implementation_status(node)

        assert status == "Partial"

    def test_unimplemented(self):
        """Returns Unimplemented when coverage is 0."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_metric("coverage_pct", 0)

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

    def test_boundary_99_is_partial(self):
        """Coverage of 99% is still Partial, not Full."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_metric("coverage_pct", 99)

        status = get_implementation_status(node)

        assert status == "Partial"

    def test_boundary_1_is_partial(self):
        """Coverage of 1% is Partial, not Unimplemented."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_metric("coverage_pct", 1)

        status = get_implementation_status(node)

        assert status == "Partial"


class TestAggregateIterationBehavior:
    """Tests for REQ-d00051-F: Aggregate functions iteration behavior."""

    def test_REQ_d00051_F_count_by_level_uses_all_nodes(self):
        """REQ-d00051-F: count_by_level SHALL NOT duplicate iteration."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", status="Active"),
            make_requirement("REQ-o00001", level="OPS", status="Active"),
            make_requirement("REQ-d00001", level="DEV", status="Active"),
        )

        # Call multiple times - should always return same result
        counts1 = count_by_level(graph)
        counts2 = count_by_level(graph)

        assert counts1 == counts2
        # Total should match node count (3 requirements)
        total = sum(counts1["all"].values())
        assert total == 3

    def test_REQ_d00051_F_count_by_repo_uses_all_nodes(self):
        """REQ-d00051-F: count_by_repo SHALL NOT duplicate iteration."""
        graph = build_graph(
            make_requirement("REQ-p00001", status="Active"),
            make_requirement("REQ-p00002", status="Active"),
        )
        # Set metrics for all nodes
        for node in graph.all_nodes():
            if node.kind == NodeKind.REQUIREMENT:
                node.set_metric("repo_prefix", "CORE")

        counts1 = count_by_repo(graph)
        counts2 = count_by_repo(graph)

        assert counts1 == counts2

    def test_REQ_d00051_F_collect_topics_uses_all_nodes(self):
        """REQ-d00051-F: collect_topics SHALL NOT duplicate iteration."""
        graph = build_graph(
            make_requirement("REQ-p00001", source_path="spec/prd-auth.md"),
            make_requirement("REQ-p00002", source_path="spec/prd-billing.md"),
        )

        topics1 = collect_topics(graph)
        topics2 = collect_topics(graph)

        assert topics1 == topics2
        # Should have exactly 2 unique topics
        assert len(topics1) == 2
