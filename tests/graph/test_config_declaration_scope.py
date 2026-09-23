"""A configuration document is changeable only in the repository being served.

Tasks 4 to 7 made a ``[scopes.NAME]`` declaration addressable, writable,
refusable and saveable, all of it within one repository. A federation holds
a configuration document for every member, so those same mutations can be
aimed at an associate's checkout -- a repository the tool is reading, not
serving. These cases pin the refusal that stops them (REQ-d00299-F).

The read half needs no refusal and is kept here deliberately: a federation
really does hold one document per member, and that is what makes the
refusal a restriction on writing rather than an absence of anything to
write to.

The refusal names the repository the tool IS serving, because the mistake
this forecloses is not knowing which checkout an edit would land in; being
told a write was refused without being told where writes go leaves the
operator exactly where they started.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import tomlkit

from elspais.graph.declarations import find_declaration
from elspais.graph.factory import build_graph
from elspais.graph.federated import is_associate_owned
from elspais.graph.held_config import iter_config_nodes

_HOST_TOML = """version = 5

[project]
name = "host"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false

[scopes.board]
level = ["prd"]
status = ["Active"]

[associates.lib]
path = "../lib"
namespace = "LIB"
"""

_LIB_TOML = """version = 5

[project]
name = "lib"
namespace = "LIB"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false

[scopes.library]
level = ["prd"]
status = ["Active"]
"""

_REQS_MD = """## {req_id}: Test Req

**Level**: PRD | **Status**: Active

The system SHALL report what it was asked for.

### Assertions

A. The system SHALL report what it was asked for.

*End* *Test Req* | **Hash**: ________
"""

_OVERLAY = ".elspais.local.toml"


def _make_federation(tmp_path: Path) -> Path:
    """A host repository declaring one associate beside it.

    Returns:
        The host's directory, which is the repository the tool serves.
    """
    host = tmp_path / "host"
    lib = tmp_path / "lib"
    (host / "spec").mkdir(parents=True)
    (lib / "spec").mkdir(parents=True)
    (host / "spec" / "reqs.md").write_text(_REQS_MD.format(req_id="REQ-p00001"), encoding="utf-8")
    (lib / "spec" / "reqs.md").write_text(_REQS_MD.format(req_id="LIB-p00001"), encoding="utf-8")
    (host / ".elspais.toml").write_text(_HOST_TOML, encoding="utf-8")
    (lib / ".elspais.toml").write_text(_LIB_TOML, encoding="utf-8")
    return host


@pytest.fixture
def federation(tmp_path: Path):
    """A two-member federation, served from the host."""
    return build_graph(repo_root=_make_federation(tmp_path), scan_code=False, scan_tests=False)


def _member(federated, namespace: str):
    """The federation member declaring ``namespace``."""
    for entry in federated.iter_repos():
        if entry.namespace == namespace:
            return entry
    raise AssertionError(f"the federation holds no member declaring '{namespace}'")


def _config_node(graph):
    """The one configuration document a member's graph holds."""
    nodes = iter_config_nodes(graph)
    assert len(nodes) == 1, f"expected one configuration document, got {len(nodes)}"
    return nodes[0]


def _document_text(graph) -> str:
    """The configuration document exactly as it would be written back."""
    return tomlkit.dumps(_config_node(graph).get_field("config_document"))


def _pending(federated) -> dict[str, int]:
    """What each member's own log holds, keyed by namespace."""
    return {entry.namespace: len(entry.graph.mutation_log) for entry in federated.iter_repos()}


def _declaration_id(graph, name: str) -> str:
    """The id of the declaration a member makes under ``name``."""
    node = find_declaration(graph, "scopes", name)
    assert node is not None, f"the member declares no scope named '{name}'"
    return node.id


# The four mutations, each aimed at the member whose scope is named. Written
# as callables over (federated, graph, scope) so one sweep covers both the
# refused direction and the permitted one.
_MUTATIONS: list[Any] = [
    pytest.param(
        lambda federated, graph, scope: federated.add_declaration(
            _config_node(graph).id, "scopes", "auditor", {"level": ["prd"]}
        ),
        id="add",
    ),
    pytest.param(
        lambda federated, graph, scope: federated.update_declaration(
            _declaration_id(graph, scope), {"level": ["dev"]}
        ),
        id="update",
    ),
    pytest.param(
        lambda federated, graph, scope: federated.rename_declaration(
            _declaration_id(graph, scope), "council"
        ),
        id="rename",
    ),
    pytest.param(
        lambda federated, graph, scope: federated.delete_declaration(_declaration_id(graph, scope)),
        id="delete",
    ),
]


# Verifies: REQ-d00299-F
def test_REQ_d00299_F_a_federation_holds_a_document_for_each_member(federation) -> None:
    """Every member's configuration is held, and only one is the served one.

    The read half. A refusal on writing means nothing unless the documents
    an associate's writes would reach are really there to be reached.
    """
    held = {entry.namespace: _config_node(entry.graph) for entry in federation.iter_repos()}

    assert set(held) == {"REQ", "LIB"}, "the federation does not hold both members"
    assert held["REQ"].id == "file:REQ:.elspais.toml"
    assert held["LIB"].id == "file:LIB:.elspais.toml"

    assert federation.root_repo_namespace == "REQ", "the host is not the repository served"
    assert not is_associate_owned(federation, held["REQ"]), (
        "the served repository's own document reads as an associate's"
    )
    assert is_associate_owned(federation, held["LIB"]), (
        "an associate's document reads as the served repository's own"
    )


# Verifies: REQ-d00299-F
@pytest.mark.parametrize("mutate", _MUTATIONS)
def test_REQ_d00299_F_a_change_aimed_at_another_repository_is_refused(
    federation, mutate: Callable[..., Any]
) -> None:
    """A write into an associate's checkout does not happen.

    The associate's document is compared as text rather than as values,
    because a refusal that reflowed the file it declined to change would
    have rewritten a repository the tool is only reading.
    """
    associate = _member(federation, "LIB").graph
    before = _document_text(associate)
    pending = _pending(federation)

    with pytest.raises(ValueError) as refusal:
        mutate(federation, associate, "library")

    message = str(refusal.value)
    assert federation.root_repo_namespace in message, (
        f"the refusal does not name the repository being served: {message}"
    )
    assert "serv" in message.lower(), (
        f"the refusal does not say that writing is scoped to the served repository: {message}"
    )

    assert _document_text(associate) == before, "a refused change edited an associate's document"
    assert _pending(federation) == pending, "a refused change joined a mutation log"


# Verifies: REQ-d00299-F
@pytest.mark.parametrize("mutate", _MUTATIONS)
def test_REQ_d00299_F_a_change_aimed_at_the_served_repository_goes_through(
    federation, mutate: Callable[..., Any]
) -> None:
    """The refusal is about which repository, not about changing at all."""
    host = _member(federation, "REQ").graph
    associate = _member(federation, "LIB").graph
    host_before = _document_text(host)
    associate_before = _document_text(associate)
    pending = _pending(federation)

    entry = mutate(federation, host, "board")

    assert entry.after_state["file_id"] == _config_node(host).id, (
        "the change was recorded against a document other than the served one"
    )
    assert len(host.mutation_log) == pending["REQ"] + 1, "the change did not join the host's log"
    assert len(associate.mutation_log) == pending["LIB"], (
        "a change to the served repository was recorded against an associate"
    )
    assert _document_text(associate) == associate_before, (
        "a change to the served repository edited an associate's document"
    )
    assert _document_text(host) != host_before, (
        "the change was permitted but the served repository's document did not move"
    )


# Verifies: REQ-d00299-F
def test_REQ_d00299_F_the_served_repository_keeps_its_own_documents_only(
    federation, tmp_path: Path
) -> None:
    """A change to the served repository leaves the associate's file on disk alone."""
    host = _member(federation, "REQ").graph
    associate_path = tmp_path / "lib" / ".elspais.toml"
    on_disk = associate_path.read_text(encoding="utf-8")

    federation.add_declaration(_config_node(host).id, "scopes", "auditor", {"level": ["prd"]})

    assert associate_path.read_text(encoding="utf-8") == on_disk, (
        "a change to the served repository reached an associate's file on disk"
    )
    assert _OVERLAY not in {path.name for path in (tmp_path / "lib").iterdir()}, (
        "a change to the served repository wrote an overlay into an associate"
    )
