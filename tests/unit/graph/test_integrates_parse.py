# Verifies: REQ-d00252
"""Validates REQ-d00252-A: Integrates: is parsed and stored as integrates_refs."""
import textwrap
from pathlib import Path

from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind


def test_REQ_d00252_A_integrates_refs_stored(tmp_path):
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
    graph = build_graph(repo_root=Path(tmp_path), scan_code=False, scan_tests=False)
    node = next(n for n in graph.iter_by_kind(NodeKind.REQUIREMENT) if n.id == "REQ-d00001")
    assert node.get_field("integrates_refs") == ["REQ-evs-0007"]
