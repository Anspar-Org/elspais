# Verifies: REQ-d00252
"""Validates REQ-d00252-A: a requirement's Integrates: line renders from the stored field."""
import textwrap
from pathlib import Path

from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.render import render_file, render_node


def _build(tmp_path):
    (tmp_path / ".elspais.toml").write_text(
        textwrap.dedent(
            """
            version = 3
            [project]
            name = "demo"
            namespace = "REQ"
            [levels.dev]
            rank = 1
            letter = "d"
            implements = ["dev"]
            [scanning.spec]
            directories = ["spec"]
            """
        ).strip()
    )
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "dev.md").write_text(
        textwrap.dedent(
            """
            # REQ-d00001: Consumer requirement

            **Level**: dev | **Status**: Active | **Integrates**: REQ-evs-0007

            ## Assertions

            A. The consumer SHALL integrate the upstream service.
            """
        ).strip()
    )
    return build_graph(repo_root=Path(tmp_path), scan_code=False, scan_tests=False)


def test_REQ_d00252_A_integrates_line_rendered(tmp_path):
    graph = _build(tmp_path)
    node = next(n for n in graph.iter_by_kind(NodeKind.REQUIREMENT) if n.id == "REQ-d00001")
    text = render_node(node)
    assert "**Integrates**: REQ-evs-0007" in text


def test_REQ_d00252_A_integrates_round_trips(tmp_path):
    graph = _build(tmp_path)
    file_node = next(iter(graph.iter_roots(NodeKind.FILE)))
    assert "**Integrates**: REQ-evs-0007" in render_file(file_node)
