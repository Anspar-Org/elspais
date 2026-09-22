"""A configuration written back differs from the one read only where it changed.

Tasks 4 to 6 made a ``[scopes.NAME]`` declaration addressable, writable and
refusable. This module pins what makes any of that usable: a configuration
file is written by hand and carries comments explaining why a setting is
what it is, so a writer that reformats such a file on its way past is a
writer nobody can let near one (REQ-d00299-C).

Every case builds a throwaway project whose ``.elspais.toml`` is
deliberately awkward -- comments above tables, comments beside settings,
comments above individual settings, blank lines, three scope declarations
in a deliberate order and a further table after them -- changes exactly one
thing through the graph, saves, and asks what else moved. The comparison is
made outside the changed declaration's own lines, because that is the region
a change is allowed to rewrite and the only one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from elspais.graph.declarations import find_declaration
from elspais.graph.factory import build_graph
from elspais.graph.held_config import held_config, iter_config_nodes
from elspais.graph.render import render_save

# Deliberately awkward. Every comment here is a fact about the project that
# no derived value carries, so every one of them is something a save can
# lose.
_PROJECT_TOML = """# The tool's configuration for this project. Hand-written.
version = 5

[project]
name = "save-fidelity"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = false

# The reports this project publishes, in the order they are reviewed.
[scopes.board]
level = ["prd"]  # only the product tier
status = ["Active"]  # nothing retired

# What the auditor reads, which is not what the board reads.
[scopes.auditor]
# The auditor reads the whole estate, not one tier.
level = ["prd", "dev"]
status = ["Active"]

# The engineers' own view.
[scopes.engineering]
level = ["dev"]

# Where generated documents are put.
[output]
dir = "_generated"
"""

_REQS_MD = """## REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL report what it was asked for.

### Assertions

A. The system SHALL report what it was asked for.

*End* *Test Req* | **Hash**: ________
"""


def _make_project(tmp_path: Path) -> Path:
    """A throwaway project whose configuration is worth preserving."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_REQS_MD, encoding="utf-8")
    (project / ".elspais.toml").write_text(_PROJECT_TOML, encoding="utf-8")
    return project


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """The throwaway project, one per case, as its configuration is rewritten."""
    return _make_project(tmp_path)


def _federated(project: Path):
    """A federation over the project, which is what a save is given."""
    return build_graph(repo_root=project, scan_code=False, scan_tests=False)


def _graph(federated):
    """The one member graph the throwaway project has."""
    return next(iter(federated.iter_repos())).graph


def _config_node(graph):
    """The one configuration document the graph under test holds."""
    nodes = iter_config_nodes(graph)
    assert len(nodes) == 1, f"expected one configuration document, got {len(nodes)}"
    return nodes[0]


def _declaration_id(graph, name: str) -> str:
    """The id of the scope declared under ``name``."""
    node = find_declaration(graph, "scopes", name)
    assert node is not None, f"the project declares no scope named {name!r}"
    return node.id


def _save(federated, project: Path) -> str:
    """Save, insisting it succeeded, and return what reached disk."""
    result = render_save(federated, project)
    assert result["errors"] == [], result["errors"]
    assert result["success"] is True
    assert result["saved_count"] == 1, (
        f"the configuration document was not among the dirty files: {result['skipped']}"
    )
    return (project / ".elspais.toml").read_text(encoding="utf-8")


def _table_span(text: str, header: str) -> tuple[int, int]:
    """The lines a declaration's own table occupies.

    From its header line to the first blank line or next table header after
    it. A comment above the header belongs to whatever it describes and a
    blank line separates declarations, so neither is inside the span: both
    are bytes a change to this declaration must leave alone.
    """
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.strip() == header]
    assert len(starts) == 1, f"expected one {header} line in the document, found {len(starts)}"
    start = starts[0]
    end = start + 1
    while end < len(lines) and lines[end].strip() != "" and not lines[end].startswith("["):
        end += 1
    return start, end


def _outside(text: str, header: str) -> str:
    """Everything the document says apart from that one declaration's table."""
    lines = text.splitlines(keepends=True)
    start, end = _table_span(text, header)
    return "".join(lines[:start] + lines[end:])


def _without_declaration(text: str, header: str) -> str:
    """The document with that declaration, and the blank line after it, gone."""
    lines = text.splitlines(keepends=True)
    start, end = _table_span(text, header)
    if end < len(lines) and lines[end].strip() == "":
        end += 1
    return "".join(lines[:start] + lines[end:])


def _trimmed(text: str) -> str:
    """The text with trailing blank lines settled, so only real moves differ."""
    return text.rstrip("\n") + "\n"


def _difference(before: str, after: str) -> str:
    """What the document used to say and no longer does, or where it moved.

    A diff of two configuration files is unreadable in a failure message.
    The lines that went missing are usually the whole story; where nothing
    went missing, the first line that is not where it was is.
    """
    remaining = list(after.splitlines())
    missing = []
    for line in before.splitlines():
        if line in remaining:
            remaining.remove(line)
        else:
            missing.append(line)
    if missing:
        return "lines no longer in the document: " + "; ".join(repr(line) for line in missing)

    was = before.splitlines()
    now = after.splitlines()
    for index, (old, new) in enumerate(zip(was, now, strict=False)):
        if old != new:
            return f"line {index + 1} was {old!r} and is now {new!r}"
    return f"the document is {len(now) - len(was)} lines longer than it was"


def _add(federated, graph) -> None:
    federated.add_declaration(
        _config_node(graph).id, "scopes", "newcomer", {"level": ["ops"], "status": ["Draft"]}
    )


def _change(federated, graph) -> None:
    federated.update_declaration(
        _declaration_id(graph, "board"), {"level": ["ops"], "status": ["Active"]}
    )


def _rename(federated, graph) -> None:
    federated.rename_declaration(_declaration_id(graph, "board"), "governance")


def _remove(federated, graph) -> None:
    federated.delete_declaration(_declaration_id(graph, "auditor"))


_MUTATIONS: dict[str, Callable[[Any, Any], None]] = {
    "add": _add,
    "change": _change,
    "rename": _rename,
    "remove": _remove,
}


# Verifies: REQ-d00299-C
def test_REQ_d00299_C_an_added_declaration_leaves_the_rest_of_the_document_alone(
    project: Path,
) -> None:
    """A scope added through the graph adds its table and nothing else."""
    federated = _federated(project)
    _add(federated, _graph(federated))

    written = _save(federated, project)

    assert "[scopes.newcomer]" in written, "the added declaration did not reach disk"
    assert "# Where generated documents are put.\n[output]\n" in written, (
        "adding a declaration took the comment introducing the table after it: "
        + _difference(_PROJECT_TOML, written)
    )
    rest = _without_declaration(written, "[scopes.newcomer]")
    assert _trimmed(rest) == _trimmed(_PROJECT_TOML), (
        "adding a declaration rewrote bytes outside it: " + _difference(_PROJECT_TOML, rest)
    )


# Verifies: REQ-d00299-C
def test_REQ_d00299_C_a_changed_declaration_leaves_the_rest_of_the_document_alone(
    project: Path,
) -> None:
    """Changing one scope rewrites that scope's table and no other byte."""
    federated = _federated(project)
    _change(federated, _graph(federated))

    written = _save(federated, project)

    assert 'level = ["ops"]' in written, "the change did not reach disk"
    before = _outside(_PROJECT_TOML, "[scopes.board]")
    after = _outside(written, "[scopes.board]")
    assert after == before, "changing one declaration rewrote bytes outside it: " + _difference(
        before, after
    )


# Verifies: REQ-d00299-C
def test_REQ_d00299_C_a_renamed_declaration_leaves_the_rest_of_the_document_alone(
    project: Path,
) -> None:
    """A rename respells one header and leaves the declarations around it."""
    federated = _federated(project)
    _rename(federated, _graph(federated))

    written = _save(federated, project)

    assert "[scopes.governance]" in written, "the rename did not reach disk"
    assert "[scopes.board]" not in written, "the old name is still declared on disk"
    before = _outside(_PROJECT_TOML, "[scopes.board]")
    after = _outside(written, "[scopes.governance]")
    assert after == before, "renaming a declaration rewrote bytes outside it: " + _difference(
        before, after
    )


# Verifies: REQ-d00299-C
def test_REQ_d00299_C_a_removed_declaration_leaves_the_declarations_around_it_alone(
    project: Path,
) -> None:
    """Removing a scope takes its table, and takes nothing that follows it.

    What follows it is the comment introducing the next declaration, which
    describes that declaration and not the one removed.
    """
    federated = _federated(project)
    _remove(federated, _graph(federated))

    written = _save(federated, project)

    assert "[scopes.auditor]" not in written, "the removal did not reach disk"
    assert "# The engineers' own view." in written, (
        "removing a declaration took the comment introducing the next one: "
        + _difference(_PROJECT_TOML, written)
    )
    expected = _without_declaration(_PROJECT_TOML, "[scopes.auditor]")
    assert _trimmed(written) == _trimmed(expected), (
        "removing a declaration disturbed the declarations around it: "
        + _difference(expected, written)
    )


# Verifies: REQ-d00299-C
@pytest.mark.parametrize(
    "comment",
    [
        pytest.param('level = ["ops"]  # only the product tier', id="on-the-changed-setting"),
        pytest.param('status = ["Active"]  # nothing retired', id="on-the-unchanged-setting"),
    ],
)
def test_REQ_d00299_C_an_inline_comment_survives_a_change_to_the_declaration(
    project: Path, comment: str
) -> None:
    """A comment written beside a setting is why the setting is what it is.

    Only ``level`` changes here. The comment beside ``status`` is the
    important half: nobody touched that setting, so nothing may touch the
    note explaining it.
    """
    federated = _federated(project)
    _change(federated, _graph(federated))

    written = _save(federated, project)

    assert comment in written, (
        f"the change lost the inline comment: expected a line reading {comment!r}. "
        + _difference(_PROJECT_TOML, written)
    )


# Verifies: REQ-d00299-C
def test_REQ_d00299_C_a_comment_above_an_unchanged_setting_survives_a_change(
    project: Path,
) -> None:
    """A comment above one setting outlives a change to a different setting.

    ``status`` is what changes in the auditor's scope; the note above
    ``level`` explains a setting the change never named.
    """
    federated = _federated(project)
    graph = _graph(federated)
    federated.update_declaration(
        _declaration_id(graph, "auditor"),
        {"level": ["prd", "dev"], "status": ["Draft"]},
    )

    written = _save(federated, project)

    assert 'status = ["Draft"]' in written, "the change did not reach disk"
    assert "# The auditor reads the whole estate, not one tier." in written, (
        "the change lost the comment above a setting it never named: "
        + _difference(_PROJECT_TOML, written)
    )


# Verifies: REQ-d00299-C
def test_REQ_d00299_C_a_document_nobody_changed_is_never_written(project: Path) -> None:
    """Reading a configuration is not a reason to rewrite it."""
    path = project / ".elspais.toml"
    before_bytes = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns

    federated = _federated(project)
    result = render_save(federated, project)

    assert result["errors"] == []
    assert result["saved_count"] == 0, f"a save with nothing pending wrote {result['saved_count']}"
    assert str(path) not in result["files_modified"]
    assert path.read_bytes() == before_bytes, (
        "a save with nothing pending rewrote the configuration: "
        + _difference(before_bytes.decode("utf-8"), path.read_text(encoding="utf-8"))
    )
    assert path.stat().st_mtime_ns == before_mtime, (
        "a save with nothing pending touched the configuration file"
    )


# Verifies: REQ-d00299-C
@pytest.mark.parametrize("mutation", sorted(_MUTATIONS))
def test_REQ_d00299_C_a_saved_document_reloads_to_the_same_configuration(
    project: Path, mutation: str
) -> None:
    """What was saved is what a fresh read of the file derives."""
    federated = _federated(project)
    graph = _graph(federated)
    _MUTATIONS[mutation](federated, graph)
    expected = held_config(graph)["scopes"]

    _save(federated, project)

    reread = _graph(_federated(project))
    assert held_config(reread)["scopes"] == expected, (
        f"the document saved after a {mutation} reloaded to a different configuration"
    )
