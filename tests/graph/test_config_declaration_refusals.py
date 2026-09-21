"""A change that would leave a configuration the tool cannot load is refused.

Task 5 made a ``[scopes.NAME]`` declaration writable through the graph, and
a write that parses is not therefore a write that loads: ``tomlkit`` edits
structure rather than text, so a change cannot produce an unparseable
document, but it can readily produce one that parses and then fails schema
validation. These cases pin the refusal that closes that path -- the tool
cannot be disabled from its own interface.

The refusal is judged against ``derive_config``, the one function that
decides whether a configuration loads, so there is one answer to that
question and the refusal at the change cannot drift from the refusal at the
read. What it judges is shape, not meaning: a scope selecting a level no
project declares is unusual and loads, so it is not refused here.

Each case builds a throwaway project of its own. A refusal leaves nothing
behind by definition, and a project per case is what makes "the document is
byte-identical afterwards" an assertion about this change alone.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import tomlkit

from elspais.graph.declarations import find_declaration, iter_declarations
from elspais.graph.factory import build_graph
from elspais.graph.held_config import held_config, iter_config_nodes

_PROJECT_TOML = """version = 5

[project]
name = "declared-scopes"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false

[scopes.sponsor]
level = ["prd"]
status = ["Active"]
"""

_REQS_MD = """## REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL report what it was asked for.

### Assertions

A. The system SHALL report what it was asked for.

*End* *Test Req* | **Hash**: ________
"""


def _make_project(tmp_path: Path) -> Path:
    """A throwaway project declaring one valid scope, to be changed badly."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_REQS_MD, encoding="utf-8")
    (project / ".elspais.toml").write_text(_PROJECT_TOML, encoding="utf-8")
    return project


@pytest.fixture
def graph(tmp_path: Path):
    """A graph over a throwaway project, holding one scope declaration."""
    project = _make_project(tmp_path)
    federated = build_graph(repo_root=project, scan_code=False, scan_tests=False)
    return next(iter(federated.iter_repos())).graph


def _config_node(graph):
    """The one configuration document the graph under test holds."""
    nodes = iter_config_nodes(graph)
    assert len(nodes) == 1, f"expected one configuration document, got {len(nodes)}"
    return nodes[0]


def _document_text(graph) -> str:
    """The configuration document exactly as it would be written back."""
    return tomlkit.dumps(_config_node(graph).get_field("config_document"))


def _declared_names(graph) -> set[str]:
    """Every scope name the graph holds a declaration node for."""
    return {node.get_field("declared_name") for node in iter_declarations(graph, "scopes")}


def _sponsor_id(graph) -> str:
    """The id of the declaration the fixture project makes."""
    node = find_declaration(graph, "scopes", "sponsor")
    assert node is not None, "the fixture project declares no scope to change"
    return node.id


def _add_unknown_key(graph) -> Any:
    return graph.add_declaration(_config_node(graph).id, "scopes", "auditor", {"levl": ["prd"]})


def _update_unknown_key(graph) -> Any:
    return graph.update_declaration(_sponsor_id(graph), {"levl": ["prd"]})


def _add_wrong_type(graph) -> Any:
    return graph.add_declaration(_config_node(graph).id, "scopes", "auditor", {"level": "prd"})


def _update_wrong_type(graph) -> Any:
    return graph.update_declaration(_sponsor_id(graph), {"level": "prd"})


def _add_malformed_name(graph) -> Any:
    return graph.add_declaration(
        _config_node(graph).id, "scopes", "not a name!", {"level": ["prd"]}
    )


def _rename_to_malformed_name(graph) -> Any:
    return graph.rename_declaration(_sponsor_id(graph), "not a name!")


# Each case is a change the schema will not admit, paired with what the
# refusal has to name for a project to know what to write instead.
_REFUSED = [
    pytest.param(_add_unknown_key, ["levl"], id="add-unknown-key"),
    pytest.param(_update_unknown_key, ["levl"], id="update-unknown-key"),
    pytest.param(_add_wrong_type, ["level"], id="add-wrong-type"),
    pytest.param(_update_wrong_type, ["level"], id="update-wrong-type"),
    pytest.param(_add_malformed_name, ["not a name!"], id="add-malformed-name"),
    pytest.param(_rename_to_malformed_name, ["not a name!"], id="rename-to-malformed-name"),
]


# Verifies: REQ-d00299-E
@pytest.mark.parametrize(("change", "named"), _REFUSED)
def test_REQ_d00299_E_a_change_the_schema_refuses_is_refused(graph, change, named) -> None:
    """The change does not go through, the document is as it was, and the
    refusal names the setting or name at fault."""
    before = _document_text(graph)

    with pytest.raises(ValueError) as refusal:
        change(graph)

    message = str(refusal.value)
    for fragment in named:
        assert fragment in message, f"the refusal does not name {fragment!r}: {message}"

    assert _document_text(graph) == before, "a refused change edited the document"


# Verifies: REQ-d00299-E
@pytest.mark.parametrize(("change", "named"), _REFUSED)
def test_REQ_d00299_E_a_refused_change_leaves_the_configuration_as_it_was(
    graph, change, named
) -> None:
    """What a consumer reads afterwards is what it read before."""
    before = copy.deepcopy(held_config(graph))

    with pytest.raises(ValueError):
        change(graph)

    assert held_config(graph) == before, "a refused change moved the derived configuration"


# Verifies: REQ-d00299-E
@pytest.mark.parametrize(("change", "named"), _REFUSED)
def test_REQ_d00299_E_a_refused_change_is_not_pending(graph, change, named) -> None:
    """Nothing joins the mutation log, and no declaration comes or goes."""
    pending = len(graph.mutation_log)
    names = _declared_names(graph)

    with pytest.raises(ValueError):
        change(graph)

    assert len(graph.mutation_log) == pending, "a refused change joined the mutation log"
    assert _declared_names(graph) == names, "a refused change added or removed a declaration"


# Verifies: REQ-d00299-E
def test_REQ_d00299_E_a_valid_but_unusual_change_is_not_refused(graph) -> None:
    """The schema constrains shape, not meaning.

    A scope selecting a level and a status no project declares is a
    configuration the tool loads, so refusing it here would refuse a change
    the read admits -- two answers to one question.
    """
    entry = graph.add_declaration(
        _config_node(graph).id,
        "scopes",
        "auditor",
        {"level": ["nonexistent"], "status": ["Invented"]},
    )

    assert graph.mutation_log.last() is entry
    declared = held_config(graph)["scopes"]["auditor"]
    assert declared["level"] == ["nonexistent"]
    assert declared["status"] == ["Invented"]
