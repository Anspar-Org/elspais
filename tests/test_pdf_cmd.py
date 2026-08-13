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
        fed = FederatedGraph.from_single(
            graph, config={"project": {"name": "test", "namespace": "REQ"}}, repo_root=repo_root
        )

        captured = {}

        def fake_render_pdf(markdown, **kwargs):
            captured["kwargs"] = kwargs
            return 0

        args = parse_args(["pdf"])

        # A real MarkdownAssembler is used deliberately: the resource-path
        # set is the assembler's to own, so a mocked assembler would hide
        # whether the command actually consults it.
        with (
            patch("elspais.commands.pdf_cmd._check_tool", return_value="/usr/bin/x"),
            patch("elspais.graph.factory.build_graph", return_value=fed),
            patch("elspais.pdf.renderer.render_pdf", side_effect=fake_render_pdf),
        ):
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

        root_entry = RepoEntry(
            name="root",
            graph=root_graph,
            config={"project": {"name": "root", "namespace": "REQ"}},
            repo_root=root_dir,
        )
        assoc_entry = RepoEntry(
            name="assoc",
            graph=assoc_graph,
            # A distinct namespace: two members of one federation may not
            # declare the same one.
            config={"project": {"name": "assoc", "namespace": "ASSOC"}},
            repo_root=assoc_dir,
        )
        fed = FederatedGraph([root_entry, assoc_entry], root_repo="root")

        captured = {}

        def fake_render_pdf(markdown, **kwargs):
            captured["kwargs"] = kwargs
            return 0

        args = parse_args(["pdf"])

        with (
            patch("elspais.commands.pdf_cmd._check_tool", return_value="/usr/bin/x"),
            patch("elspais.graph.factory.build_graph", return_value=fed),
            patch("elspais.pdf.renderer.render_pdf", side_effect=fake_render_pdf),
        ):
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


# ─────────────────────────────────────────────────────────────────────────────
# Degradation disclosure (REQ-p00080-K)
# ─────────────────────────────────────────────────────────────────────────────


def _fed_with_missing_image(tmp_path: Path):
    """Federated graph whose associate spec references a missing image."""
    from tests.test_pdf_assembler import _make_federated_overview_graph

    fed, root_dir, assoc_dir = _make_federated_overview_graph(tmp_path)
    assoc_md = assoc_dir / "spec" / "prd-assoc.md"
    assoc_md.write_text(
        assoc_md.read_text(encoding="utf-8") + "\n![gone](missing/nope.png)\n",
        encoding="utf-8",
    )
    return fed


class TestDegradationDisclosure:
    """Validates REQ-p00080-K: when referenced content was omitted from the
    compiled document, the completion report discloses the degradation
    rather than reporting unqualified success.

    A bare "PDF written to <path>" over a document missing an image it was
    asked to carry tells the reader nothing is wrong, so the completion line
    is qualified whenever anything was left out.
    """

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_missing_image_disclosed_in_completion_report(self, tmp_path, capsys):
        """The diagnostic goes to stderr and the success line is qualified."""
        from elspais.commands import pdf_cmd

        fed = _fed_with_missing_image(tmp_path)
        args = parse_args(["pdf"])

        with (
            patch("elspais.commands.pdf_cmd._check_tool", return_value="/usr/bin/x"),
            patch("elspais.graph.factory.build_graph", return_value=fed),
            patch("elspais.pdf.renderer.render_pdf", return_value=0),
        ):
            rc = pdf_cmd.run(args)

        captured = capsys.readouterr()
        assert rc == 0
        # The unresolvable reference is reported to the operator.
        assert "missing/nope.png" in captured.err
        assert "spec/prd-assoc.md" in captured.err
        # The success line survives but no longer claims unqualified success.
        assert "PDF written to" in captured.out
        assert "INCOMPLETE" in captured.out

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_clean_run_reports_unqualified_success(self, tmp_path, capsys):
        """Regression guard: nothing degraded means no disclosure noise."""
        from elspais.commands import pdf_cmd
        from tests.test_pdf_assembler import _make_federated_overview_graph

        fed, _root_dir, _assoc_dir = _make_federated_overview_graph(tmp_path)
        args = parse_args(["pdf", "--output", "clean.pdf"])

        with (
            patch("elspais.commands.pdf_cmd._check_tool", return_value="/usr/bin/x"),
            patch("elspais.graph.factory.build_graph", return_value=fed),
            patch("elspais.pdf.renderer.render_pdf", return_value=0),
        ):
            rc = pdf_cmd.run(args)

        captured = capsys.readouterr()
        assert rc == 0
        assert "PDF written to clean.pdf" in captured.out
        assert "INCOMPLETE" not in captured.out
        assert "INCOMPLETE" not in captured.err


class TestPandocReportedOmissions:
    """Validates REQ-p00080-K: content only pandoc noticed was missing is
    folded into the same completion report as the assembler's own findings.

    The assembler recognises the reference shapes it can resolve; pandoc meets
    every other shape and drops what it cannot fetch, warning and exiting 0.
    Left there, the command prints unqualified success over a document that is
    provably short an image. Both sources feed one count, deduplicated by the
    reference they name -- a reference the assembler already reported also
    draws a pandoc warning, and counting it twice would misstate the damage as
    surely as counting it zero times.
    """

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_pandoc_only_omission_qualifies_the_completion_line(
        self, tmp_path, capsys
    ):
        """No assembler diagnostic, one pandoc-dropped resource: the success
        line is still qualified and the resource is named on stderr.
        """
        from elspais.commands import pdf_cmd
        from tests.test_pdf_assembler import _make_federated_overview_graph

        fed, _root_dir, _assoc_dir = _make_federated_overview_graph(tmp_path)
        args = parse_args(["pdf", "--output", "out.pdf"])

        def fake_render_pdf(markdown, **kwargs):
            collector = kwargs.get("unfetched")
            assert collector is not None, (
                "the command must hand render_pdf a collector, or pandoc's own "
                "findings can never reach the completion report"
            )
            collector.append("art/photo.webp")
            return 0

        with (
            patch("elspais.commands.pdf_cmd._check_tool", return_value="/usr/bin/x"),
            patch("elspais.graph.factory.build_graph", return_value=fed),
            patch("elspais.pdf.renderer.render_pdf", side_effect=fake_render_pdf),
        ):
            rc = pdf_cmd.run(args)

        captured = capsys.readouterr()
        assert rc == 0
        assert "PDF written to out.pdf" in captured.out
        assert "INCOMPLETE" in captured.out, (
            f"a document pandoc dropped an image from was reported as an "
            f"unqualified success: {captured.out!r}"
        )
        assert (
            "art/photo.webp" in captured.err
        ), f"the dropped resource was not named to the operator: {captured.err!r}"

    # Verifies: REQ-p00080-K
    def test_REQ_p00080_K_reference_reported_by_both_sources_counts_once(self, tmp_path, capsys):
        """The assembler's diagnostic and pandoc's warning for the SAME
        reference are one omission, not two.
        """
        from elspais.commands import pdf_cmd

        fed = _fed_with_missing_image(tmp_path)
        args = parse_args(["pdf", "--output", "out.pdf"])

        def fake_render_pdf(markdown, **kwargs):
            collector = kwargs.get("unfetched")
            assert collector is not None, (
                "the command must hand render_pdf a collector, or pandoc's own "
                "findings can never reach the completion report"
            )
            # Pandoc warns about exactly the reference the assembler already
            # reported -- the ordinary case, not a contrived one.
            collector.append("missing/nope.png")
            return 0

        with (
            patch("elspais.commands.pdf_cmd._check_tool", return_value="/usr/bin/x"),
            patch("elspais.graph.factory.build_graph", return_value=fed),
            patch("elspais.pdf.renderer.render_pdf", side_effect=fake_render_pdf),
        ):
            rc = pdf_cmd.run(args)

        captured = capsys.readouterr()
        assert rc == 0
        assert "INCOMPLETE: 1 reference omitted" in captured.out, (
            f"one reference reported by two sources must count once: " f"{captured.out!r}"
        )
