"""A change another document's declaration shadows is reported as such.

A repository's configuration is assembled from the documents it holds, and a
machine-local overlay layered over the committed file is the only way one
repository holds two today. Where both declare the same name, the overlay's
declaration is what every reader resolves to -- so a change to the committed
document is a change that moves nothing anybody can see. These cases pin the
disclosure that says so (REQ-d00299-G).

What is disclosed is deliberately thin: that the name resolves in another
document, and which document that is. Not what the other document declares.
REQ-d00290-B allows one coarse fact about a local override and its Rationale
bars putting the overlay's values back into the answers, so a disclosure
carrying them would report the arrangement it exists to keep out of view.
The fact being disclosed is about the WRITE -- it landed where nothing reads
-- not about the overlay's contents.

Where nothing shadows a change there is nothing to disclose, and the key is
absent rather than empty: a reader testing for it must not have to know that
an empty string means "not shadowed".
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from elspais.graph.declarations import find_declaration, iter_declarations
from elspais.graph.factory import build_graph
from elspais.graph.held_config import held_config, iter_config_nodes

_COMMITTED_TOML = """version = 5

[project]
name = "shadowed-scopes"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false

# The board reads the product tier, unless this machine says otherwise.
[scopes.board]
level = ["prd"]
status = ["Active"]

# Nothing overrides this one.
[scopes.lonely]
level = ["prd"]
"""

# Declares `board` again, and a name the committed document does not declare
# at all -- the second is how a name can be shadowed by something that was
# never in the committed file.
_OVERLAY_TOML = """[scopes.board]
level = ["dev"]

[scopes.local_only]
level = ["ops"]
"""

_REQS_MD = """## REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL report what it was asked for.

### Assertions

A. The system SHALL report what it was asked for.

*End* *Test Req* | **Hash**: ________
"""

_OVERLAY_NAME = ".elspais.local.toml"


def _make_project(tmp_path: Path, *, overlay: bool) -> Path:
    """A throwaway project, with or without a machine-local overlay."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_REQS_MD, encoding="utf-8")
    (project / ".elspais.toml").write_text(_COMMITTED_TOML, encoding="utf-8")
    if overlay:
        (project / _OVERLAY_NAME).write_text(_OVERLAY_TOML, encoding="utf-8")
    return project


def _graph_over(project: Path):
    """The one member's graph for a project held alone."""
    federated = build_graph(repo_root=project, scan_code=False, scan_tests=False)
    return next(iter(federated.iter_repos())).graph


@pytest.fixture
def layered(tmp_path: Path):
    """A graph whose repository holds a committed document and an overlay."""
    return _graph_over(_make_project(tmp_path, overlay=True))


@pytest.fixture
def unlayered(tmp_path: Path):
    """A graph whose repository holds the committed document alone."""
    return _graph_over(_make_project(tmp_path, overlay=False))


def _committed_node(graph):
    """The committed configuration document, which is read first."""
    nodes = iter_config_nodes(graph)
    assert nodes, "the graph holds no configuration document"
    committed = nodes[0]
    assert Path(str(committed.get_field("absolute_path"))).name == ".elspais.toml", (
        "the first document read is not the committed one"
    )
    return committed


def _committed_declaration(graph, name: str) -> Any:
    """The declaration the COMMITTED document makes under ``name``.

    ``find_declaration`` answers with the declaration a reader resolves to,
    which is the overlay's wherever both declare the name. These cases
    change the loser on purpose, so they address it through the document
    that declares it.
    """
    committed = _committed_node(graph)
    for node in iter_declarations(graph, "scopes"):
        owner = node.file_node()
        if owner is not None and owner.id == committed.id:
            if str(node.get_field("declared_name")).lower() == name.lower():
                return node
    raise AssertionError(f"the committed document declares no scope named '{name}'")


# Verifies: REQ-d00299-G
@pytest.mark.parametrize(
    ("change", "name"),
    [
        pytest.param(
            lambda graph: graph.update_declaration(
                _committed_declaration(graph, "board").id, {"level": ["ops"]}
            ),
            "board",
            id="update",
        ),
        pytest.param(
            lambda graph: graph.add_declaration(
                _committed_node(graph).id, "scopes", "local_only", {"level": ["prd"]}
            ),
            "local_only",
            id="add",
        ),
    ],
)
def test_REQ_d00299_G_a_shadowed_change_is_reported(
    layered, change: Callable[[Any], Any], name: str
) -> None:
    """The change goes through, and the report names the document that wins."""
    entry = change(layered)

    assert layered.mutation_log.last() is entry, "the change did not join the log"
    assert entry.after_state.get("shadowed_by") == _OVERLAY_NAME, (
        f"the change to '{name}' was not reported as shadowed: {entry.after_state}"
    )


# Verifies: REQ-d00299-G
def test_REQ_d00299_G_a_shadowed_change_leaves_the_configuration_as_it_was(layered) -> None:
    """What every reader resolves to is what the overlay declares, still.

    This is the fact the disclosure is about: the change was applied, and
    the configuration a consumer reads did not move.
    """
    before = held_config(layered)["scopes"]["board"]["level"]
    assert before == ["dev"], "the fixture's overlay does not win the name"

    entry = layered.update_declaration(
        _committed_declaration(layered, "board").id, {"level": ["ops"]}
    )

    assert held_config(layered)["scopes"]["board"]["level"] == ["dev"], (
        "the change to the shadowed document moved what a reader resolves to"
    )
    assert entry.after_state.get("shadowed_by") == _OVERLAY_NAME


# Verifies: REQ-d00299-G
def test_REQ_d00299_G_a_shadowed_removal_is_reported(layered) -> None:
    """Removing the loser removes nothing a reader can see, and says so."""
    entry = layered.delete_declaration(_committed_declaration(layered, "board").id)

    assert entry.after_state.get("shadowed_by") == _OVERLAY_NAME, (
        f"the removal was not reported as shadowed: {entry.after_state}"
    )
    assert find_declaration(layered, "scopes", "board") is not None, (
        "the name resolves nowhere, so the removal was not in fact shadowed"
    )
    assert held_config(layered)["scopes"]["board"]["level"] == ["dev"], (
        "removing the shadowed declaration changed what a reader resolves to"
    )


# Verifies: REQ-d00299-G
@pytest.mark.parametrize("graph_name", ["layered", "unlayered"])
def test_REQ_d00299_G_an_unshadowed_change_reports_nothing(request, graph_name: str) -> None:
    """A name no other document declares is not reported as shadowed.

    Run over both a repository holding an overlay that declares other names
    and one holding no overlay at all: neither shadows ``lonely``, and the
    key is absent rather than present and empty.
    """
    graph = request.getfixturevalue(graph_name)

    entry = graph.update_declaration(_committed_declaration(graph, "lonely").id, {"level": ["ops"]})

    assert "shadowed_by" not in entry.after_state, (
        f"an unshadowed change was reported as shadowed: {entry.after_state}"
    )
    assert held_config(graph)["scopes"]["lonely"]["level"] == ["ops"], (
        "an unshadowed change did not move what a reader resolves to"
    )
