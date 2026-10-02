# Verifies: REQ-d00132-K
"""``spec.needs_rewrite`` reports the parts of a file outside any requirement.

Validates REQ-d00132-K: building the graph brings a term occurrence into its
canonical marked form in a journey and in file-level prose as it does in a
requirement, and the check reports each part whose text that changed, so the
reader learns of it before a save writes it. ``elspais fix`` writes the
canonical form, after which the check passes.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

_CONFIG_TOML = """\
version = 5

[project]
name = "needs-rewrite-prose"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.journey]
directories = ["spec"]

[terms]
markup_styles = ["*", "**"]
"""

_GLOSSARY = """# Glossary

Widget
: A thing the tool makes.
"""

_PROSE_SPEC = """# Dev

## Widget notes

Every Widget is counted.
"""

_JOURNEY_SPEC = """# Journeys

### JNY-001: Count Things

**Actor**: Operator
**Goal**: Count each Widget made today

## Steps

1. Operator counts the Widget

*End* *Count Things*
"""


def _write_project(root: Path) -> Path:
    (root / ".elspais.toml").write_text(_CONFIG_TOML, encoding="utf-8")
    spec = root / "spec"
    spec.mkdir()
    (spec / "glossary.md").write_text(_GLOSSARY, encoding="utf-8")
    (spec / "prose.md").write_text(_PROSE_SPEC, encoding="utf-8")
    (spec / "journeys.md").write_text(_JOURNEY_SPEC, encoding="utf-8")
    return spec


def _check(root: Path):
    from elspais.commands.health import check_spec_needs_rewrite
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    graph = build_graph(repo_root=root)
    return check_spec_needs_rewrite(graph, get_config(None, root))


def _run_fix(root: Path) -> int:
    """Run the bulk fix path with cwd pinned to the project root."""
    from elspais.commands.fix_cmd import run

    args = argparse.Namespace(
        req_id=None,
        dry_run=False,
        spec_dir=root / "spec",
        config=root / ".elspais.toml",
        verbose=False,
        quiet=False,
        message=None,
    )
    old_cwd = os.getcwd()
    os.chdir(root)
    try:
        return run(args)
    finally:
        os.chdir(old_cwd)


class TestNeedsRewriteReportsProseAndJourneys:
    """Validates REQ-d00132-K."""

    # Verifies: REQ-d00132-K
    def test_REQ_d00132_K_prose_and_a_journey_with_an_unmarked_term_are_reported(
        self, tmp_path: Path
    ):
        _write_project(tmp_path)

        check = _check(tmp_path)

        assert not check.passed, check.message
        by_node = {f.node_id: f for f in check.findings}
        assert "JNY-001" in by_node, check.findings
        prose = [n for n in by_node if n and n.startswith("rem:")]
        assert len(prose) == 1, check.findings
        assert by_node[prose[0]].file_path == "spec/prose.md"
        assert by_node["JNY-001"].file_path == "spec/journeys.md"
        assert all("non_canonical_term" in f.message for f in check.findings), check.findings
        assert len(check.findings) == 2, check.findings

    # Verifies: REQ-d00132-K
    def test_REQ_d00132_K_fix_writes_the_canonical_form_and_the_check_passes(
        self, tmp_path: Path, capsys
    ):
        spec = _write_project(tmp_path)

        assert _run_fix(tmp_path) == 0, capsys.readouterr()

        out = capsys.readouterr().out
        assert "canonicalize term Widget -> *Widget*" in out, out
        assert "Every *Widget* is counted." in (spec / "prose.md").read_text(encoding="utf-8")
        journey = (spec / "journeys.md").read_text(encoding="utf-8")
        assert "counts the *Widget*" in journey, journey
        assert "## Widget notes" in (spec / "prose.md").read_text(encoding="utf-8")
        check = _check(tmp_path)
        assert check.passed, check.findings
