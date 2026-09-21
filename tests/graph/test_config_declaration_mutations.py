"""A scope a project declares can be added, changed, renamed and removed.

Task 4 made a ``[scopes.NAME]`` declaration addressable; nothing about a
configuration was writable through the graph. These cases pin the four
mutations that write one: each edits the held ``TOMLDocument`` through the
node, so the derived configuration moves with it, each joins the one
mutation log and is reversed by the one undo path, and each marks the
document dirty so the existing save path writes it.

The undo cases compare the document's text byte for byte rather than the
values derived from it, because a document holds comments, key order and
spacing that no derivation carries: an undo that restored the values and
reflowed the file would have rewritten a project's configuration behind it.

Matching a declared name ignores case, so two names differing only in case
are one name. Declaring the second is refused rather than silently made to
shadow the first.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, ClassVar

import pytest
import tomlkit

from elspais.graph.declarations import (
    declared_settings,
    find_declaration,
    iter_declarations,
)
from elspais.graph.factory import build_graph
from elspais.graph.held_config import held_config, iter_config_nodes

# An id no document declares anything under. Spelled the way a declaration
# id is spelled so the refusal is about the declaration being absent and not
# about the string being unreadable.
_MISSING_ID = "decl:REQ:.elspais.toml:scopes:nobody"

_SPONSOR: dict[str, Any] = {
    "level": ["prd"],
    "status": ["Active"],
    "values": ["implemented.immediate_direct"],
}


def _config_node(graph):
    """The one configuration document the graph under test holds."""
    nodes = iter_config_nodes(graph)
    assert len(nodes) == 1, f"expected one configuration document, got {len(nodes)}"
    return nodes[0]


def _document_text(graph) -> str:
    """The configuration document exactly as it would be written back."""
    return tomlkit.dumps(_config_node(graph).get_field("config_document"))


def _scopes(graph) -> dict[str, Any]:
    """The scopes the derived configuration states."""
    return copy.deepcopy(held_config(graph).get("scopes", {}))


def _declared_names(graph) -> set[str]:
    """Every scope name the graph holds a declaration node for."""
    return {node.get_field("declared_name") for node in iter_declarations(graph, "scopes")}


@pytest.mark.incremental
class TestScopeDeclarationMutations:
    """Add, change, rename and remove one declaration, then undo all four.

    The canonical fixture declares no scopes, so the chain starts from none
    and ends there. Each forward step records the document's text, the
    derived scopes and the pending count as they stood before it, and the
    undo steps walk back through those records in reverse.
    """

    text_before: ClassVar[dict[str, str]] = {}
    scopes_before: ClassVar[dict[str, dict[str, Any]]] = {}
    names_before: ClassVar[dict[str, set[str]]] = {}
    pending_before: ClassVar[dict[str, int]] = {}

    def _record(self, step: str, graph) -> None:
        self.text_before[step] = _document_text(graph)
        self.scopes_before[step] = _scopes(graph)
        self.names_before[step] = _declared_names(graph)
        self.pending_before[step] = len(graph.mutation_log)

    # Verifies: REQ-d00299-D
    def test_REQ_d00299_D_an_added_declaration_is_stated_by_the_configuration(
        self, mutable_graph
    ) -> None:
        """A scope added through the graph is one the derived config states."""
        graph = mutable_graph
        assert "sponsor" not in _scopes(graph), "the chain must start with no such scope"
        self._record("add", graph)

        entry = graph.add_declaration(_config_node(graph).id, "scopes", "sponsor", _SPONSOR)

        assert graph.mutation_log.last() is entry, "the mutation did not join the log"
        assert len(graph.mutation_log) == self.pending_before["add"] + 1

        declared = _scopes(graph)["sponsor"]
        assert declared["level"] == ["prd"]
        assert declared["status"] == ["Active"]
        assert declared["values"] == ["implemented.immediate_direct"]

        node = find_declaration(graph, "scopes", "sponsor")
        assert node is not None, "the added declaration is not addressable by name"
        assert declared_settings(node)["level"] == ["prd"]

    # Verifies: REQ-d00299-D
    @pytest.mark.parametrize("spelling", ["SPONSOR", "Sponsor", "sPoNsOr"])
    def test_REQ_d00299_D_a_name_colliding_only_in_case_is_refused(
        self, mutable_graph, spelling: str
    ) -> None:
        """Two names differing only in case are one name, so the second is refused."""
        graph = mutable_graph
        text = _document_text(graph)
        pending = len(graph.mutation_log)

        with pytest.raises(ValueError, match="(?i)sponsor"):
            graph.add_declaration(_config_node(graph).id, "scopes", spelling, {"level": ["ops"]})

        assert _document_text(graph) == text, "a refused declaration edited the document"
        assert len(graph.mutation_log) == pending, "a refused declaration joined the log"
        assert set(_scopes(graph)) == {"sponsor"}

    # Verifies: REQ-d00299-D
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(
                lambda graph: graph.update_declaration(_MISSING_ID, {"level": ["ops"]}),
                id="update",
            ),
            pytest.param(
                lambda graph: graph.rename_declaration(_MISSING_ID, "elsewhere"),
                id="rename",
            ),
            pytest.param(lambda graph: graph.delete_declaration(_MISSING_ID), id="delete"),
        ],
    )
    def test_REQ_d00299_D_a_declaration_the_graph_does_not_hold_is_refused(
        self, mutable_graph, call
    ) -> None:
        """Addressing a declaration that is not there names nothing to change."""
        graph = mutable_graph
        text = _document_text(graph)
        pending = len(graph.mutation_log)

        with pytest.raises(KeyError):
            call(graph)

        assert _document_text(graph) == text
        assert len(graph.mutation_log) == pending

    # Verifies: REQ-d00299-D
    def test_REQ_d00299_D_a_changed_declaration_changes_the_configuration(
        self, mutable_graph
    ) -> None:
        """What a scope selects follows the change, and the name does not move."""
        graph = mutable_graph
        self._record("change", graph)
        node = find_declaration(graph, "scopes", "sponsor")
        assert node is not None, "the add step did not leave a declaration to change"

        entry = graph.update_declaration(node.id, {"level": ["ops"], "status": ["Draft"]})

        assert graph.mutation_log.last() is entry
        assert len(graph.mutation_log) == self.pending_before["change"] + 1

        declared = _scopes(graph)["sponsor"]
        assert declared["level"] == ["ops"]
        assert declared["status"] == ["Draft"]
        assert declared["values"] == [], "a setting the change omitted was kept"
        assert declared_settings(find_declaration(graph, "scopes", "sponsor"))["level"] == ["ops"]

    # Verifies: REQ-d00299-D
    def test_REQ_d00299_D_a_renamed_declaration_resolves_under_its_new_name(
        self, mutable_graph
    ) -> None:
        """The old name resolves nowhere; the new one carries what was declared."""
        graph = mutable_graph
        self._record("rename", graph)
        node = find_declaration(graph, "scopes", "sponsor")
        assert node is not None, "the earlier steps did not leave a declaration to rename"

        entry = graph.rename_declaration(node.id, "auditor")

        assert graph.mutation_log.last() is entry
        assert len(graph.mutation_log) == self.pending_before["rename"] + 1

        assert find_declaration(graph, "scopes", "sponsor") is None, "the old name still resolves"
        renamed = find_declaration(graph, "scopes", "auditor")
        assert renamed is not None, "the new name resolves nowhere"
        assert renamed.get_field("declared_name") == "auditor"
        assert declared_settings(renamed)["level"] == ["ops"], "the rename lost what was declared"

        scopes = _scopes(graph)
        assert "sponsor" not in scopes
        assert scopes["auditor"]["level"] == ["ops"]

    # Verifies: REQ-d00299-D
    def test_REQ_d00299_D_a_removed_declaration_resolves_nowhere(self, mutable_graph) -> None:
        """A removed scope is gone from the configuration and from the index."""
        graph = mutable_graph
        self._record("remove", graph)
        node = find_declaration(graph, "scopes", "auditor")
        assert node is not None, "the rename step did not leave a declaration to remove"

        entry = graph.delete_declaration(node.id)

        assert graph.mutation_log.last() is entry
        assert len(graph.mutation_log) == self.pending_before["remove"] + 1

        assert find_declaration(graph, "scopes", "auditor") is None
        assert "auditor" not in _scopes(graph)
        assert "auditor" not in _declared_names(graph)

    # Verifies: REQ-d00299-D
    @pytest.mark.parametrize("step", ["remove", "rename", "change", "add"])
    def test_REQ_d00299_D_undo_leaves_the_document_as_it_was(
        self, mutable_graph, step: str
    ) -> None:
        """Each mutation is reversed, down to the document's own spelling."""
        graph = mutable_graph
        assert step in self.text_before, "the forward step this undoes did not run"

        undone = graph.undo_last()

        assert undone is not None, "there was nothing left to undo"
        assert _document_text(graph) == self.text_before[step], (
            f"undoing the {step} left the configuration document rewritten"
        )
        assert _scopes(graph) == self.scopes_before[step]
        assert _declared_names(graph) == self.names_before[step]
        assert len(graph.mutation_log) == self.pending_before[step]


def _make_project(tmp_path: Path) -> Path:
    """A throwaway project declaring no scopes, to be saved over."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(
        "## REQ-p00001: Test Req\n"
        "\n"
        "**Level**: PRD | **Status**: Active\n"
        "\n"
        "The system SHALL report what it was asked for.\n"
        "\n"
        "### Assertions\n"
        "\n"
        "A. The system SHALL report what it was asked for.\n"
        "\n"
        "*End* *Test Req* | **Hash**: ________\n",
        encoding="utf-8",
    )
    (project / ".elspais.toml").write_text(
        "version = 5\n"
        "\n"
        "[project]\n"
        'name = "declared-scopes"\n'
        'namespace = "REQ"\n'
        "\n"
        "[scanning.spec]\n"
        'directories = ["spec"]\n'
        "\n"
        "[scanning.test]\n"
        "enabled = false\n",
        encoding="utf-8",
    )
    return project


# Verifies: REQ-d00299-D
def test_REQ_d00299_D_a_saved_declaration_is_written_to_the_document(tmp_path: Path) -> None:
    """The pending count falls on save, and the file states the new scope.

    Saved on a throwaway project rather than the canonical fixture, because
    a save writes to disk and the canonical fixture is a committed file.
    """
    from elspais.graph.render import render_save

    project = _make_project(tmp_path)
    federated = build_graph(repo_root=project, scan_code=False, scan_tests=False)
    graph = next(iter(federated.iter_repos())).graph

    # Declared through the federation, as every save-bound mutation is: a
    # save reads the federated log, and a mutation recorded only on a
    # member's own graph is one the save would discard without writing.
    federated.add_declaration(_config_node(graph).id, "scopes", "sponsor", _SPONSOR)
    assert len(graph.mutation_log) == 1

    result = render_save(federated, project)

    assert result["errors"] == []
    assert result["success"] is True
    assert result["saved_count"] == 1, "the configuration document was not among the dirty files"
    assert len(graph.mutation_log) == 0, "the pending count did not fall on save"

    written = (project / ".elspais.toml").read_text(encoding="utf-8")
    assert "[scopes.sponsor]" in written
    assert 'level = ["prd"]' in written
    # The document that was edited is what was written: reading it back
    # states the same scope.
    reread = build_graph(repo_root=project, scan_code=False, scan_tests=False)
    reread_graph = next(iter(reread.iter_repos())).graph
    assert held_config(reread_graph)["scopes"]["sponsor"]["level"] == ["prd"]
