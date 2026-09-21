"""A repository's configuration documents are held in its graph.

The configuration is read before anything else and decides how the rest is
read. These cases check that the document it was read from is kept — as a
FILE node of the CONFIG type, carrying the parsed document, rendering back
to the bytes it was read from — and that a FILE node of a type no walk
names reaches none of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import FileType, NodeKind, make_file_id

_SPEC = """\
## REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL hold the *Widget* it was configured with.

### Assertions

A. The system SHALL hold the *Widget* it was configured with.

*End* *Test Req* | **Hash**: ________
"""

_CODE = """\
# A comment naming the Widget, so the term scan has something to find.
def widget():
    return 1
"""

# Comments, blank lines and a non-default key order: what a hand-written
# configuration looks like, and what a writer must not reformat.
_CONFIG = """\
version = 5

# The project this repository declares.
[project]
name = "config-held"      # trailing comment
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

# A Widget lives here too, in a comment the term scan must not read.
[scanning.code]
directories = ["src"]

[scanning.test]
enabled = false
"""

_OVERLAY = """\
# Machine-local overlay: a path that differs per machine.
version = 5

[project]
name = "config-held"
namespace = "REQ"
"""


def _make_project(tmp_path: Path, *, overlay: bool = False) -> Path:
    """An on-disk project with a spec, a code file and a configuration."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    (project / "src").mkdir(parents=True)
    (project / "src" / "widget.py").write_text(_CODE, encoding="utf-8")
    (project / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    if overlay:
        (project / ".elspais.local.toml").write_text(_OVERLAY, encoding="utf-8")
    return project


def _graph_for(project: Path):
    """The single TraceGraph built for *project*."""
    federated = build_graph(repo_root=project, scan_code=True, scan_tests=False)
    return next(iter(federated.iter_repos())).graph, federated


def _config_nodes(graph) -> list:
    return [
        node
        for node in graph.iter_roots(NodeKind.FILE)
        if node.get_field("file_type") == FileType.CONFIG
    ]


# Verifies: REQ-d00299-A
def test_REQ_d00299_A_committed_document_is_held_as_a_file_node(tmp_path: Path) -> None:
    """The document read for a repository is a FILE node in its graph."""
    project = _make_project(tmp_path)
    graph, _ = _graph_for(project)

    expected_id = make_file_id("REQ", ".elspais.toml")
    node = graph.find_by_id(expected_id)

    assert node is not None, "no node was held for the configuration that was read"
    assert node.kind == NodeKind.FILE
    assert node.get_field("file_type") == FileType.CONFIG
    assert node.get_field("relative_path") == ".elspais.toml"


# Verifies: REQ-d00299-A
def test_REQ_d00299_A_overlay_is_held_where_one_exists(tmp_path: Path) -> None:
    """A machine-local overlay is a document read for the repository too."""
    project = _make_project(tmp_path, overlay=True)
    graph, _ = _graph_for(project)

    held = {node.get_field("relative_path") for node in _config_nodes(graph)}

    assert held == {".elspais.toml", ".elspais.local.toml"}


# Verifies: REQ-d00299-A
def test_REQ_d00299_A_no_node_is_invented_for_an_absent_overlay(tmp_path: Path) -> None:
    """Where no overlay exists, nothing stands in for one."""
    project = _make_project(tmp_path)
    graph, _ = _graph_for(project)

    held = {node.get_field("relative_path") for node in _config_nodes(graph)}

    assert held == {".elspais.toml"}
    assert graph.find_by_id(make_file_id("REQ", ".elspais.local.toml")) is None


# Verifies: REQ-d00299-A
def test_REQ_d00299_A_node_carries_the_parsed_document(tmp_path: Path) -> None:
    """The node holds the document, not a dictionary of its values."""
    project = _make_project(tmp_path)
    graph, _ = _graph_for(project)

    node = graph.find_by_id(make_file_id("REQ", ".elspais.toml"))
    document = node.get_field("config_document")

    assert isinstance(document, tomlkit.TOMLDocument)
    assert document["project"]["name"] == "config-held"


# Verifies: REQ-d00299-A
@pytest.mark.parametrize("overlay", [False, True])
def test_REQ_d00299_A_held_document_renders_to_the_source_bytes(
    tmp_path: Path, overlay: bool
) -> None:
    """Rendering a held document reproduces the file it was read from.

    Byte for byte, comments and spacing included: a configuration is
    written by hand, and a writer that reformats one on its way past is a
    writer nobody can let near it.
    """
    from elspais.graph.render import render_file

    project = _make_project(tmp_path, overlay=overlay)
    graph, _ = _graph_for(project)

    for node in _config_nodes(graph):
        source = Path(node.get_field("absolute_path")).read_text(encoding="utf-8")
        assert render_file(node) == source


# Verifies: REQ-d00131-R
def test_REQ_d00131_R_term_scan_does_not_read_a_configuration_document(
    tmp_path: Path,
) -> None:
    """The term scan names CODE and TEST, so a CONFIG document is not read.

    The same term sits in a comment in the code file and in a comment in
    the configuration. Finding the first and not the second is what shows
    the walk acted on the types it names rather than on every FILE node.
    """
    from elspais.graph.term_scanner import scan_graph
    from elspais.graph.terms import TermDictionary, TermEntry

    project = _make_project(tmp_path)
    graph, _ = _graph_for(project)

    terms = TermDictionary()
    terms.add(
        TermEntry(
            term="Widget",
            definition="A thing under test.",
            indexed=True,
            defined_in="REQ-p00001",
            namespace="REQ",
        )
    )
    scan_graph(terms, graph, namespace="REQ")

    files = {ref.node_id for entry in terms.iter_all() for ref in entry.references}

    assert make_file_id("REQ", "src/widget.py") in files, (
        "the scan found nothing in the code file, so it proves nothing about config"
    )
    assert make_file_id("REQ", ".elspais.toml") not in files


# Verifies: REQ-d00131-R
def test_REQ_d00131_R_uncited_walk_does_not_report_a_configuration_document(
    tmp_path: Path,
) -> None:
    """`collect_uncited` names CODE and TEST; a CONFIG document cites nothing."""
    from elspais.commands.uncited import collect_uncited

    project = _make_project(tmp_path)
    _, federated = _graph_for(project)

    data = collect_uncited(federated)
    reported = {entry.file for entry in (*data.code, *data.tests)}

    assert ".elspais.toml" not in reported


# Verifies: REQ-d00131-R
def test_REQ_d00131_R_health_test_file_walk_does_not_reach_a_configuration_document(
    tmp_path: Path,
) -> None:
    """The unrunnable-test-file check names TEST and leaves other types alone."""
    from elspais.commands.health import check_unrunnable_test_files

    project = _make_project(tmp_path)
    _, federated = _graph_for(project)

    check = check_unrunnable_test_files(federated, None)
    reported = {finding.file_path for finding in check.findings}

    assert ".elspais.toml" not in reported
