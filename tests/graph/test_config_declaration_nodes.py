"""A scope a project declares under a name is a node of its own.

A declaration was a key in a table, reachable only by reading the whole
document. These cases check that each one is held as a node beneath the
configuration document that declares it, addressable by the name it was
declared under, carrying both halves of what it declares and a version
that follows its own declaration and no neighbour's.

The last case pins the convention that breaks here: for a spec file the
CONTAINS children in render_order ARE the file's text, and for a
configuration document they are not. The document is the text, and these
children exist for addressing and versioning alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.declarations import (
    declared_settings,
    find_declaration,
    iter_declarations,
)
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import FileType, NodeKind
from elspais.graph.relations import EdgeKind
from elspais.graph.render import node_version, render_file, render_node

_SPEC = """\
## REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL report what it was asked for.

### Assertions

A. The system SHALL report what it was asked for.

*End* *Test Req* | **Hash**: ________
"""


def _config(audit_level: str = "dev") -> str:
    """A hand-written configuration declaring two scopes.

    ``sponsor`` carries both halves REQ-d00280-C speaks of -- the
    requirements a report is about and the values it states -- and
    ``audit`` carries only a selection, so the two are told apart by what
    they declare as well as by their names.
    """
    return f"""\
version = 5

# The project this repository declares.
[project]
name = "declared-scopes"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false

# What a sponsor reads: the product tier, and how much of it is built.
[scopes.sponsor]
level = ["prd"]
status = ["Active"]
values = ["implemented.immediate_direct"]

# What an auditor reads.
[scopes.audit]
level = ["{audit_level}"]
"""


def _make_project(tmp_path: Path, *, audit_level: str = "dev") -> Path:
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    (project / ".elspais.toml").write_text(_config(audit_level), encoding="utf-8")
    return project


def _graph_for(project: Path):
    federated = build_graph(repo_root=project, scan_code=False, scan_tests=False)
    return next(iter(federated.iter_repos())).graph


def _config_node(graph):
    nodes = [
        node
        for node in graph.iter_roots(NodeKind.FILE)
        if node.get_field("file_type") is FileType.CONFIG
    ]
    assert len(nodes) == 1, f"expected one configuration document, got {len(nodes)}"
    return nodes[0]


# Verifies: REQ-d00299-D
def test_REQ_d00299_D_each_declaration_is_a_node_addressable_by_name(tmp_path: Path) -> None:
    """Two declarations yield two nodes beneath the document declaring them."""
    graph = _graph_for(_make_project(tmp_path))
    config_node = _config_node(graph)

    children = [
        edge.target for edge in config_node.iter_outgoing_edges() if edge.kind == EdgeKind.CONTAINS
    ]
    assert {node.kind for node in children} == {NodeKind.DECLARATION}
    assert {node.get_field("declared_name") for node in children} == {"sponsor", "audit"}
    assert {node.get_field("declares_table") for node in children} == {"scopes"}

    for name in ("sponsor", "audit"):
        found = find_declaration(graph, "scopes", name)
        assert found is not None, f"no declaration addressable as {name!r}"
        assert found.get_field("declared_name") == name
        assert graph.find_by_id(found.id) is found

    assert find_declaration(graph, "scopes", "nobody") is None
    assert len(list(iter_declarations(graph, "scopes"))) == 2


# Verifies: REQ-d00299-D
def test_REQ_d00299_D_both_halves_read_from_the_node(tmp_path: Path) -> None:
    """The requirements selected and the values stated are on the node."""
    graph = _graph_for(_make_project(tmp_path))

    sponsor = find_declaration(graph, "scopes", "sponsor")
    assert sponsor is not None
    settings = declared_settings(sponsor)
    assert settings["level"] == ["prd"]
    assert settings["status"] == ["Active"]
    assert settings["values"] == ["implemented.immediate_direct"]

    audit = find_declaration(graph, "scopes", "audit")
    assert audit is not None
    audit_settings = declared_settings(audit)
    assert audit_settings["level"] == ["dev"]
    assert "values" not in audit_settings


# Verifies: REQ-d00299-D
def test_REQ_d00299_D_version_follows_its_own_declaration(tmp_path: Path) -> None:
    """A neighbour's change moves a neighbour's version and no other."""
    project = _make_project(tmp_path, audit_level="dev")
    before = _graph_for(project)
    sponsor_before = node_version(find_declaration(before, "scopes", "sponsor"))
    audit_before = node_version(find_declaration(before, "scopes", "audit"))

    (project / ".elspais.toml").write_text(_config(audit_level="ops"), encoding="utf-8")
    after = _graph_for(project)
    sponsor_after = node_version(find_declaration(after, "scopes", "sponsor"))
    audit_after = node_version(find_declaration(after, "scopes", "audit"))

    assert audit_after != audit_before, "a changed declaration kept its version"
    assert sponsor_after == sponsor_before, (
        "a declaration's version moved because a neighbouring declaration changed; "
        "two editors of different scopes would collide"
    )


# Verifies: REQ-d00299-D
def test_REQ_d00299_D_rebuild_from_unchanged_content_keeps_versions(tmp_path: Path) -> None:
    """A routine rebuild does not invalidate a token a client holds."""
    project = _make_project(tmp_path)
    first = {
        node.get_field("declared_name"): node_version(node)
        for node in iter_declarations(_graph_for(project), "scopes")
    }
    second = {
        node.get_field("declared_name"): node_version(node)
        for node in iter_declarations(_graph_for(project), "scopes")
    }
    assert first == second
    assert len(first) == 2


# Verifies: REQ-d00299-D
def test_REQ_d00299_D_render_ignores_the_declaration_children(tmp_path: Path) -> None:
    """The document is the text; its CONTAINS children are not."""
    project = _make_project(tmp_path)
    graph = _graph_for(project)
    config_node = _config_node(graph)

    contained = [
        edge.target for edge in config_node.iter_outgoing_edges() if edge.kind == EdgeKind.CONTAINS
    ]
    assert contained, "the case is vacuous unless the node has children to ignore"

    assert render_file(config_node) == (project / ".elspais.toml").read_text(encoding="utf-8")

    # And a declaration has no text of its own to be rendered to: asking for
    # one is asking the wrong node, not asking for an empty answer.
    with pytest.raises(ValueError, match="not rendered independently"):
        render_node(contained[0])
