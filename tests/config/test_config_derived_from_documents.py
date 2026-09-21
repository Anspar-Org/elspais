"""The configuration a consumer reads is derived from the held documents.

A repository's configuration documents are graph content. These cases check
that the values a consumer reads are a view over those documents rather than
a second, independent reading of the same files: for a corpus of real
configurations the dictionary derived through the held nodes is the
dictionary ``load_config`` produces, key for key; the derivation is callable
with no graph in existence, because reading configuration is what tells the
builder where to look; and a derivation cached on a node is recomputed once
the document it was derived from changes.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
import tomlkit

from elspais.config import (
    config_document_paths,
    derive_config,
    load_config,
    parse_toml_document,
)
from elspais.graph.factory import build_graph, create_file_node
from elspais.graph.GraphNode import FileType, NodeKind
from elspais.graph.held_config import config_from_nodes, held_config

REPO_ROOT = Path(__file__).resolve().parents[2]

_SPEC = """\
## REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL read its configuration once.

### Assertions

A. The system SHALL read its configuration once.

*End* *Test Req* | **Hash**: ________
"""

# A hand-written configuration: comments, a trailing comment, blank lines
# and a key order nobody would produce mechanically.
_PLAIN = """\
version = 5

# The project this repository declares.
[project]
name = "derived"          # trailing comment
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false
"""

# The committed half of the overlay pair: it declares a scope the overlay
# replaces, so the overlay has something to win.
_COMMITTED_WITH_OVERLAY = """\
version = 5

[project]
name = "derived"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false

[output]
formats = ["text"]
"""

_OVERLAY = """\
# Machine-local: a value that differs per machine.
[output]
formats = ["json"]
"""

# The same settings the overlay pair assembles to, written into one
# committed file. REQ-d00290-A says the two must land in the same place.
_ASSEMBLED = """\
version = 5

[project]
name = "derived"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false

[output]
formats = ["json"]
"""

# User-declared levels REPLACE the default levels rather than merging into
# them, so this configuration must derive to a [levels] table holding the
# user's keys and no default key beside them.
_CUSTOM_LEVELS = """\
version = 5

[project]
name = "derived"
namespace = "REQ"

[levels.product]
rank = 1
letter = "p"
implements = []

[levels.build]
rank = 2
letter = "d"
implements = ["build", "product"]

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false
"""


def _make_project(tmp_path: Path, committed: str, overlay: str | None = None) -> Path:
    """An on-disk project carrying *committed* and, where given, an overlay."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    (project / ".elspais.toml").write_text(committed, encoding="utf-8")
    if overlay is not None:
        (project / ".elspais.local.toml").write_text(overlay, encoding="utf-8")
    return project


def _graph_for(project: Path):
    """The single TraceGraph built for *project*."""
    federated = build_graph(repo_root=project, scan_code=False, scan_tests=False)
    return next(iter(federated.iter_repos())).graph


def _nodes_for(config_path: Path, repo_root: Path, namespace: str) -> list:
    """CONFIG nodes for the documents read at *config_path*, in read order.

    Built without a full graph: this repository's own configuration is the
    corpus entry that matters most and scanning the whole estate to reach
    its two documents would say nothing extra.
    """
    nodes = []
    for path in config_document_paths(config_path):
        node = create_file_node(path, repo_root, FileType.CONFIG, namespace)
        node.set_field("config_document", parse_toml_document(path.read_text(encoding="utf-8")))
        nodes.append(node)
    return nodes


_CORPUS = {
    "plain": (_PLAIN, None),
    "with-overlay": (_COMMITTED_WITH_OVERLAY, _OVERLAY),
    "custom-levels": (_CUSTOM_LEVELS, None),
}


# Verifies: REQ-d00299-B
@pytest.mark.parametrize("case", sorted(_CORPUS))
def test_REQ_d00299_B_derived_through_the_nodes_equals_load_config(tmp_path, case):
    """The dictionary derived through the held nodes is load_config's, key for key."""
    committed, overlay = _CORPUS[case]
    project = _make_project(tmp_path, committed, overlay)
    graph = _graph_for(project)

    expected = load_config(project / ".elspais.toml")
    derived = held_config(graph)

    assert derived == expected
    assert sorted(derived) == sorted(expected)


# Verifies: REQ-d00299-B
def test_REQ_d00299_B_this_repository_derives_to_its_own_loaded_config():
    """This repository's own configuration derives through its held documents."""
    config_path = REPO_ROOT / ".elspais.toml"
    expected = load_config(config_path)
    nodes = _nodes_for(config_path, REPO_ROOT, expected["project"]["namespace"])

    assert config_from_nodes(nodes) == expected


# Verifies: REQ-d00299-B
def test_REQ_d00299_B_user_levels_replace_default_levels(tmp_path):
    """A user-declared [levels] table replaces the defaults through the node too.

    The replace-don't-merge rule is the one place the derivation is not a
    plain deep merge, so a derivation that lost it would still pass a
    careless equality check against a configuration that declares no levels.
    """
    project = _make_project(tmp_path, _CUSTOM_LEVELS)
    derived = held_config(_graph_for(project))

    assert sorted(derived["levels"]) == ["build", "product"]


# Verifies: REQ-d00299-B
# Verifies: REQ-d00290-A
def test_REQ_d00290_A_overlay_derives_to_the_assembled_committed_file(tmp_path):
    """An overlay pair derives to what one committed file holding the result does."""
    layered = _make_project(tmp_path / "layered", _COMMITTED_WITH_OVERLAY, _OVERLAY)
    assembled = _make_project(tmp_path / "assembled", _ASSEMBLED)

    assert held_config(_graph_for(layered)) == held_config(_graph_for(assembled))


# Verifies: REQ-d00299-B
def test_REQ_d00299_B_derivation_is_callable_with_no_graph(tmp_path):
    """The derivation is a pure function over documents, reachable without a graph.

    ``get_config`` runs before any graph exists — reading the configuration
    is what tells the builder where to look — so a derivation that needed
    one would make building one impossible.
    """
    project = _make_project(tmp_path, _COMMITTED_WITH_OVERLAY, _OVERLAY)
    config_path = project / ".elspais.toml"

    documents: list[tuple[Path, Any]] = [
        (path, parse_toml_document(path.read_text(encoding="utf-8")))
        for path in config_document_paths(config_path)
    ]

    assert derive_config(documents) == load_config(config_path)


# Verifies: REQ-d00299-B
def test_REQ_d00299_B_reading_configuration_needs_no_graph_module():
    """Importing the config module does not bring the graph with it.

    The guard is structural rather than behavioural, and it is the one the
    purity of the derivation rests on: a module-level import of the graph
    would not fail any single call, it would fail the first command that
    reads configuration in order to decide what graph to build. The two
    deliberate imports the module does make are inside functions, reached
    only by callers that already hold a graph.
    """
    source = (REPO_ROOT / "src" / "elspais" / "config" / "__init__.py").read_text(encoding="utf-8")
    at_import_time = set()
    for statement in ast.parse(source).body:
        if isinstance(statement, ast.Import):
            at_import_time.update(alias.name for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom) and statement.module:
            at_import_time.add(statement.module)

    assert not [name for name in at_import_time if name.startswith("elspais.graph")]


# Verifies: REQ-d00299-B
def test_REQ_d00299_B_a_changed_document_is_derived_again(tmp_path):
    """A cached derivation is recomputed once the document it came from changes."""
    project = _make_project(tmp_path, _PLAIN)
    graph = _graph_for(project)

    first = held_config(graph)
    assert first["project"]["name"] == "derived"
    # The cache exists: nothing changed, so the same dictionary comes back.
    assert held_config(graph) is first

    node = next(
        n for n in graph.iter_roots(NodeKind.FILE) if n.get_field("file_type") is FileType.CONFIG
    )
    document = node.get_field("config_document")
    document["project"]["name"] = "renamed"

    second = held_config(graph)
    assert second["project"]["name"] == "renamed"
    assert second is not first


# Verifies: REQ-d00299-B
def test_REQ_d00299_B_a_changed_overlay_is_derived_again(tmp_path):
    """A change to the overlay invalidates the derivation cached for the pair."""
    project = _make_project(tmp_path, _COMMITTED_WITH_OVERLAY, _OVERLAY)
    graph = _graph_for(project)

    assert held_config(graph)["output"]["formats"] == ["json"]

    overlay_node = next(
        n
        for n in graph.iter_roots(NodeKind.FILE)
        if n.get_field("file_type") is FileType.CONFIG
        and n.get_field("absolute_path").endswith(".elspais.local.toml")
    )
    overlay_node.set_field("config_document", tomlkit.parse('[output]\nformats = ["text"]\n'))

    assert held_config(graph)["output"]["formats"] == ["text"]
