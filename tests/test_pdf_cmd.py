# Verifies: REQ-p00080-A, REQ-p00080-F
"""Tests for the pdf CLI command registration and tool checks.

Validates REQ-p00080-A: The tool SHALL provide an elspais pdf CLI command.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from elspais.cli import parse_args
from elspais.commands.pdf_cmd import _check_tool
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry


class TestPdfCommandRegistration:
    """Validates REQ-p00080-A: CLI command registration."""

    def test_REQ_p00080_A_pdf_command_registered(self):
        """pdf subcommand is recognized by the parser."""
        args = parse_args(["pdf"])
        assert args.command == "pdf"

    def test_REQ_p00080_A_output_default(self):
        """--output defaults to spec-output.pdf."""
        args = parse_args(["pdf"])
        assert args.output == Path("spec-output.pdf")

    def test_REQ_p00080_A_output_custom(self):
        """--output accepts a custom path."""
        args = parse_args(["pdf", "--output", "my-doc.pdf"])
        assert args.output == Path("my-doc.pdf")

    def test_REQ_p00080_A_engine_default(self):
        """--engine defaults to xelatex."""
        args = parse_args(["pdf"])
        assert args.engine == "xelatex"

    def test_REQ_p00080_A_engine_custom(self):
        """--engine accepts a custom engine."""
        args = parse_args(["pdf", "--engine", "lualatex"])
        assert args.engine == "lualatex"

    def test_REQ_p00080_A_template_default(self):
        """--template defaults to None."""
        args = parse_args(["pdf"])
        assert args.template is None

    def test_REQ_p00080_A_template_custom(self):
        """--template accepts a path."""
        args = parse_args(["pdf", "--template", "custom.latex"])
        assert args.template == Path("custom.latex")

    def test_REQ_p00080_A_title_default(self):
        """--title defaults to None."""
        args = parse_args(["pdf"])
        assert args.title is None

    def test_REQ_p00080_A_title_custom(self):
        """--title accepts a string."""
        args = parse_args(["pdf", "--title", "My Specs"])
        assert args.title == "My Specs"


class TestToolAvailability:
    """Validates REQ-p00080-A: Tool availability checks."""

    def test_REQ_p00080_A_check_tool_found(self):
        """_check_tool returns a path for known commands."""
        result = _check_tool("python3")
        assert result is not None

    def test_REQ_p00080_A_check_tool_not_found(self):
        """_check_tool returns None for missing commands."""
        result = _check_tool("nonexistent_tool_xyz_12345")
        assert result is None

    def test_REQ_p00080_A_run_fails_without_pandoc(self):
        """run() returns 1 when pandoc is not found."""
        from elspais.commands.pdf_cmd import run

        args = parse_args(["pdf"])
        with patch("elspais.commands.pdf_cmd._check_tool", return_value=None):
            rc = run(args)
        assert rc == 1

    def test_REQ_p00080_A_run_fails_without_engine(self):
        """run() returns 1 when engine is not found but pandoc is."""
        from elspais.commands.pdf_cmd import run

        args = parse_args(["pdf"])

        def selective_check(name):
            if name == "pandoc":
                return "/usr/bin/pandoc"
            return None

        with patch("elspais.commands.pdf_cmd._check_tool", side_effect=selective_check):
            rc = run(args)
        assert rc == 1


class TestOverviewArgs:
    """Validates REQ-p00080-F: --overview and --max-depth CLI arguments."""

    def test_REQ_p00080_F_overview_flag_registered(self):
        """The --overview flag is available on the pdf parser."""
        args = parse_args(["pdf", "--overview"])
        assert args.overview is True

    def test_REQ_p00080_F_overview_default_false(self):
        """The --overview flag defaults to False."""
        args = parse_args(["pdf"])
        assert args.overview is False

    def test_REQ_p00080_F_max_depth_registered(self):
        """The --max-depth flag is available on the pdf parser."""
        args = parse_args(["pdf", "--max-depth", "2"])
        assert args.max_depth == 2

    def test_REQ_p00080_F_max_depth_default_none(self):
        """The --max-depth flag defaults to None."""
        args = parse_args(["pdf"])
        assert args.max_depth is None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers for the resource-path test class below
# ─────────────────────────────────────────────────────────────────────────────


def _make_graph_with_req(repo_root: Path, node_id: str) -> TraceGraph:
    """Build a minimal TraceGraph with a single requirement node."""
    g = TraceGraph(repo_root=repo_root)
    node = GraphNode(id=node_id, kind=NodeKind.REQUIREMENT, label="T")
    node._content = {"level": "PRD", "status": "Active", "hash": "deadbeef"}
    g._roots = [node]
    g._index = {node_id: node}
    return g


class TestResourcePathsCallSite:
    """Validates REQ-p00080-C: pdf command forwards every repo's root and
    spec/ directory to render_pdf via resource_paths, de-duplicated.
    """

    def test_REQ_p00080_C_single_repo_forwards_root_and_spec(self, tmp_path):
        """A federation-of-one yields exactly two resource paths: the repo
        root and <repo_root>/spec, both fully resolved.
        """
        from elspais.commands import pdf_cmd

        repo_root = tmp_path / "solo"
        repo_root.mkdir()
        (repo_root / "spec").mkdir()

        graph = _make_graph_with_req(repo_root, "REQ-p00001")
        fed = FederatedGraph.from_single(graph, config={}, repo_root=repo_root)

        captured = {}

        def fake_render_pdf(markdown, **kwargs):
            captured["kwargs"] = kwargs
            return 0

        args = parse_args(["pdf"])

        with (
            patch("elspais.commands.pdf_cmd._check_tool", return_value="/usr/bin/x"),
            patch("elspais.graph.factory.build_graph", return_value=fed),
            patch("elspais.pdf.assembler.MarkdownAssembler") as MockAsm,
            patch("elspais.pdf.renderer.render_pdf", side_effect=fake_render_pdf),
        ):
            MockAsm.return_value.assemble.return_value = "# fake"
            rc = pdf_cmd.run(args)

        assert rc == 0
        rp = captured["kwargs"]["resource_paths"]
        assert isinstance(rp, list)
        assert all(isinstance(p, Path) for p in rp)
        expected_root = repo_root.resolve()
        expected_spec = (repo_root / "spec").resolve()
        assert expected_root in rp
        assert expected_spec in rp
        # No duplicates.
        assert len(rp) == len(set(rp))
        # Exactly the two expected entries for a single-repo federation.
        assert set(rp) == {expected_root, expected_spec}

    def test_REQ_p00080_C_multi_repo_forwards_all_repos_dedup(self, tmp_path):
        """Each repo in a multi-repo federation contributes its repo_root
        and <repo_root>/spec. Duplicates (across or within repos) are
        collapsed.
        """
        from elspais.commands import pdf_cmd

        root_dir = tmp_path / "root"
        assoc_dir = tmp_path / "assoc"
        (root_dir / "spec").mkdir(parents=True)
        (assoc_dir / "spec").mkdir(parents=True)

        root_graph = _make_graph_with_req(root_dir, "REQ-p00001")
        assoc_graph = _make_graph_with_req(assoc_dir, "REQ-a00001")

        root_entry = RepoEntry(name="root", graph=root_graph, config={}, repo_root=root_dir)
        assoc_entry = RepoEntry(name="assoc", graph=assoc_graph, config={}, repo_root=assoc_dir)
        fed = FederatedGraph([root_entry, assoc_entry], root_repo="root")

        captured = {}

        def fake_render_pdf(markdown, **kwargs):
            captured["kwargs"] = kwargs
            return 0

        args = parse_args(["pdf"])

        with (
            patch("elspais.commands.pdf_cmd._check_tool", return_value="/usr/bin/x"),
            patch("elspais.graph.factory.build_graph", return_value=fed),
            patch("elspais.pdf.assembler.MarkdownAssembler") as MockAsm,
            patch("elspais.pdf.renderer.render_pdf", side_effect=fake_render_pdf),
        ):
            MockAsm.return_value.assemble.return_value = "# fake"
            rc = pdf_cmd.run(args)

        assert rc == 0
        rp = captured["kwargs"]["resource_paths"]
        expected = {
            root_dir.resolve(),
            (root_dir / "spec").resolve(),
            assoc_dir.resolve(),
            (assoc_dir / "spec").resolve(),
        }
        assert set(rp) == expected
        # No duplicates and ordering preserved (root pair before assoc pair).
        assert len(rp) == len(set(rp))
        assert rp.index(root_dir.resolve()) < rp.index(assoc_dir.resolve())
