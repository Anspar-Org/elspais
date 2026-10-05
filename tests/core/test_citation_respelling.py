"""Respelling the citations in code and test files that a rename reaches.

A mutation that gives a requirement or an *Assertion* a new identifier
respells each code or test citation designating it, so the citation keeps
designating the same entity (REQ-p00017-B). A respelling that would read as
something else refuses the mutation (REQ-p00017-O). A save writes the
respelled citation and leaves every other line of the file as its author wrote
it (REQ-d00132-M).

Each test writes a small repository into ``tmp_path``, because what is under
test is observable only in the files a save writes and in the graph a build
reads from them.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

import elspais.graph.citation_respelling as citation_respelling
from elspais.graph.builder import DeletionWouldRepointError
from elspais.graph.citation_respelling import CitationRespellingRefused
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind
from elspais.graph.render import node_version, render_file, render_save

_CONFIG = """version = 5

[project]
name = "{name}"
namespace = "{namespace}"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "prd"]

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]
"""

_PRD = """# REQ-p00001: Parent

**Level**: prd | **Status**: Draft | **Implements**: -

## Assertions

A. The tool SHALL do alpha.

B. The tool SHALL do beta.

C. The tool SHALL do gamma.

D. The tool SHALL do delta.

*End* *Parent* | **Hash**: 00000000
---
"""

_DEV = """# REQ-d00001: Child

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The tool SHALL do child alpha.

B. The tool SHALL do child beta.

C. The tool SHALL do child gamma.

*End* *Child* | **Hash**: 00000000
---

# REQ-d00002: Sibling

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The tool SHALL do sibling alpha.

*End* *Sibling* | **Hash**: 00000000
---
"""

CODE = "src/m.py"
TEST = "tests/test_m.py"


def _write_repo(
    root: Path,
    files: dict[str, str],
    *,
    namespace: str = "REQ",
    extra_config: str = "",
    with_spec: bool = True,
) -> Path:
    """Write a git repository at *root* holding *files* beside the spec."""
    for directory in ("spec", "src", "tests"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    config = _CONFIG.format(name=namespace.lower(), namespace=namespace) + extra_config
    (root / ".elspais.toml").write_text(config, encoding="utf-8")
    if with_spec:
        (root / "spec" / "prd.md").write_text(_PRD, encoding="utf-8")
        (root / "spec" / "dev.md").write_text(_DEV, encoding="utf-8")
    for relative, text in files.items():
        (root / relative).write_bytes(text.encode("utf-8"))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def _project(tmp_path: Path, files: dict[str, str]) -> Path:
    return _write_repo(tmp_path / "repo", files)


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every file of the repository's own content, by repo-relative path."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for directory in ("spec", "src", "tests")
        for path in sorted((root / directory).rglob("*"))
        if path.is_file()
    }


def _file_node(graph, relative_path: str):
    (node,) = [
        node
        for node in graph.nodes_by_kind(NodeKind.FILE)
        if node.get_field("relative_path") == relative_path
    ]
    return node


def _citing_node(graph, kind: NodeKind):
    (node,) = list(graph.nodes_by_kind(kind))
    return node


def _resolver(graph):
    return graph.repo_for("REQ-p00001").graph.resolver


def _rename_requirement(old: str, new: str) -> Callable:
    return lambda graph: graph.rename_node(old, new)


def _rename_assertion(old: str, label: str) -> Callable:
    return lambda graph: graph.rename_assertion(old, label)


def _delete_assertion(assertion_id: str) -> Callable:
    return lambda graph: graph.delete_assertion(assertion_id)


def _code(citation: str) -> str:
    return f"import os\n\n{citation}\ndef f():\n    pass\n"


def _test(citation: str) -> str:
    return f"\n{citation}\ndef test_f():\n    pass\n"


# ─────────────────────────────────────────────────────────────────────────────
# A rename respells each code and test citation designating it (REQ-p00017-B)
# ─────────────────────────────────────────────────────────────────────────────

# Each case: the file the citation is in, the file before, the mutation, and
# the file a save writes.
RESPELLED_CASES = [
    pytest.param(
        CODE,
        _code("# Implements: REQ-d00001-c"),
        _rename_requirement("REQ-d00001", "REQ-d00009"),
        _code("# Implements: REQ-d00009-C"),
        id="code-label-case-canonicalized",
    ),
    pytest.param(
        TEST,
        _test("# Verifies: REQ-d001-A"),
        _rename_requirement("REQ-d00001", "REQ-d00009"),
        _test("# Verifies: REQ-d00009-A"),
        id="test-padding-canonicalized",
    ),
    pytest.param(
        CODE,
        _code("# Implements: REQ-p00001-A+B"),
        _rename_requirement("REQ-p00001", "REQ-p00009"),
        _code("# Implements: REQ-p00009-A+B"),
        id="code-multi-assertion-keeps-shape",
    ),
    pytest.param(
        TEST,
        _test("# Verifies: REQ-d00001-A+C"),
        _rename_assertion("REQ-d00001-C", "D"),
        _test("# Verifies: REQ-d00001-A+D"),
        id="test-assertion-rename-in-multi-assertion",
    ),
    pytest.param(
        CODE,
        _code("# Implements: REQ-d00002, REQ-d00001-A, REQ-p00001-B"),
        _rename_requirement("REQ-d00001", "REQ-d00009"),
        _code("# Implements: REQ-d00002, REQ-d00009-A, REQ-p00001-B"),
        id="code-other-items-untouched",
    ),
    pytest.param(
        TEST,
        _test("# Verifies: REQ-d00001-C,\n#   REQ-d00002"),
        _rename_requirement("REQ-d00002", "REQ-d00008"),
        _test("# Verifies: REQ-d00001-C,\n#   REQ-d00008"),
        id="test-continuation-line",
    ),
    pytest.param(
        CODE,
        _code("# Implements: REQ-d00001-C,\n#   REQ-d00002"),
        _rename_requirement("REQ-d00001", "REQ-d00009"),
        _code("# Implements: REQ-d00009-C,\n#   REQ-d00002"),
        id="code-opening-line-of-continued-list",
    ),
    pytest.param(
        TEST,
        _test("# Verifies: REQ-d00002-A\n# Verifies: REQ-d00001-B"),
        _rename_requirement("REQ-d00001", "REQ-d00009"),
        _test("# Verifies: REQ-d00002-A\n# Verifies: REQ-d00009-B"),
        id="test-cited-from-two-lines",
    ),
    pytest.param(
        TEST,
        _test("# Verifies: REQ-d00001-B\n# Verifies: REQ-d00002-A"),
        _rename_requirement("REQ-d00001", "REQ-d00009"),
        _test("# Verifies: REQ-d00009-B\n# Verifies: REQ-d00002-A"),
        id="test-cited-from-two-lines-first",
    ),
    pytest.param(
        CODE,
        _code("    # Implements: REQ-p00001-D"),
        _delete_assertion("REQ-p00001-B"),
        _code("    # Implements: REQ-p00001-C"),
        id="code-indented-follows-compaction",
    ),
]


class TestRenameRespellsCodeAndTestCitations:
    """Validates REQ-p00017-B for citations in code and test files."""

    @pytest.mark.parametrize("relative,before,mutate,after", RESPELLED_CASES)
    # Verifies: REQ-p00017-B
    def test_saved_file_names_the_new_identifier_and_nothing_else_changes(
        self, tmp_path: Path, relative: str, before: str, mutate: Callable, after: str
    ):
        root = _project(tmp_path, {relative: before})
        graph = build_graph(repo_root=root)

        mutate(graph)
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        assert (root / relative).read_text(encoding="utf-8") == after
        rebuilt = build_graph(repo_root=root)
        assert rebuilt.unresolved_references() == []

    # Verifies: REQ-p00017-B
    def test_rebuilt_citation_designates_the_renamed_entity(self, tmp_path: Path):
        """After the save, the code node implements the renamed requirement's
        *Assertion* and the test verifies it, as they did before the rename."""
        root = _project(
            tmp_path,
            {CODE: _code("# Implements: REQ-d00001-C"), TEST: _test("# Verifies: REQ-d00001-C")},
        )
        graph = build_graph(repo_root=root)

        graph.rename_node("REQ-d00001", "REQ-d00009")
        assert render_save(graph, repo_root=root)["success"] is True

        rebuilt = build_graph(repo_root=root)
        renamed = rebuilt.find_by_id("REQ-d00009")
        cited = {
            (edge.target.kind, tuple(edge.assertion_targets or ()))
            for edge in renamed.iter_outgoing_edges()
            if edge.target.kind in (NodeKind.CODE, NodeKind.TEST)
        }
        assert cited == {(NodeKind.CODE, ("C",)), (NodeKind.TEST, ("C",))}


# ─────────────────────────────────────────────────────────────────────────────
# A citation that designates nothing is left alone (REQ-p00017-B)
# ─────────────────────────────────────────────────────────────────────────────

LEFT_ALONE_CASES = [
    pytest.param(TEST, _test("# Implements: REQ-d00001-C"), id="implements-in-test-file"),
    pytest.param(CODE, _code("# Refines: REQ-d00001"), id="refines-in-code-file"),
]


class TestRefusedCitationsAreLeftAlone:
    """Validates REQ-p00017-B: only a citation that designates is respelled."""

    @pytest.mark.parametrize("relative,text", LEFT_ALONE_CASES)
    # Verifies: REQ-p00017-B
    def test_citation_under_a_keyword_the_file_refuses_is_not_respelled(
        self, tmp_path: Path, relative: str, text: str
    ):
        root = _project(tmp_path, {relative: text})
        graph = build_graph(repo_root=root)

        graph.rename_node("REQ-d00001", "REQ-d00009")
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        assert str(root / relative) not in result["files_modified"]
        assert (root / relative).read_text(encoding="utf-8") == text

    # Verifies: REQ-p00017-B
    def test_item_that_did_not_read_is_not_respelled(self, tmp_path: Path):
        """An item the grammar does not account for keeps its spelling; the
        item beside it that read is respelled."""
        before = _code("# Implements: REQ-d00001-A, REQ_d00001-B")
        root = _project(tmp_path, {CODE: before})
        graph = build_graph(repo_root=root)

        graph.rename_node("REQ-d00001", "REQ-d00009")
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        assert (root / CODE).read_text(encoding="utf-8") == _code(
            "# Implements: REQ-d00009-A, REQ_d00001-B"
        )


# ─────────────────────────────────────────────────────────────────────────────
# A respelling that would read wrong refuses the mutation (REQ-p00017-O)
# ─────────────────────────────────────────────────────────────────────────────


def _join_without_text(graph) -> None:
    """Join the code node to REQ-d00002 in memory; its comment never names it.

    The federation refuses a relationship change from code, so the join is
    made on the member graph, the one way this state is reachable.
    """
    member = graph.repo_for("REQ-d00002").graph
    member.add_edge(_citing_node(graph, NodeKind.CODE).id, "REQ-d00002", EdgeKind.IMPLEMENTS)


def _misspell_respelling(monkeypatch) -> Callable:
    original = citation_respelling._respell_text

    def wrong(text, path, successor, reader):
        result = original(text, path, successor, reader)
        if result is None:
            return None
        respelled, before, after = result
        return respelled.replace("REQ-d00008", "REQ-d00001"), before, after

    monkeypatch.setattr(citation_respelling, "_respell_text", wrong)
    return lambda graph: None


class TestRespellingThatReadsWrongIsRefused:
    """Validates REQ-p00017-O."""

    @pytest.mark.parametrize(
        "code_text,prepare",
        [
            pytest.param(
                _code("# Implements: REQ-d00001-A"),
                lambda monkeypatch: _join_without_text,
                id="joined-node-whose-text-does-not-name-it",
            ),
            pytest.param(
                _code("# Implements: REQ-d00002-A"),
                _misspell_respelling,
                id="respelled-text-reads-as-something-else",
            ),
        ],
    )
    # Verifies: REQ-p00017-O
    def test_refusal_names_file_and_line_and_changes_nothing(
        self, tmp_path: Path, monkeypatch, code_text: str, prepare: Callable
    ):
        root = _project(tmp_path, {CODE: code_text})
        graph = build_graph(repo_root=root)
        prepare(monkeypatch)(graph)
        code = _citing_node(graph, NodeKind.CODE)
        requirement = graph.find_by_id("REQ-d00002")
        texts_before = citation_respelling.citation_texts(code)
        versions_before = (node_version(code), node_version(requirement))
        logged = len(graph.mutation_log)

        with pytest.raises(CitationRespellingRefused) as refused:
            graph.rename_node("REQ-d00002", "REQ-d00008")

        assert f"{CODE}:3" in str(refused.value)
        assert graph.find_by_id("REQ-d00002") is requirement
        assert graph.find_by_id("REQ-d00008") is None
        assert graph.find_by_id("REQ-d00002-A") is not None
        assert len(graph.mutation_log) == logged
        assert citation_respelling.citation_texts(code) == texts_before
        assert (node_version(code), node_version(requirement)) == versions_before


# ─────────────────────────────────────────────────────────────────────────────
# Undo puts the citation back (REQ-o00062-G, REQ-d00134-F)
# ─────────────────────────────────────────────────────────────────────────────


class TestUndoRestoresRespelledCitations:
    """Validates REQ-o00062-G and REQ-d00134-F for respelled citations."""

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(_rename_requirement("REQ-d00001", "REQ-d00009"), id="rename-requirement"),
            pytest.param(_rename_assertion("REQ-d00001-C", "D"), id="rename-assertion"),
        ],
    )
    # Verifies: REQ-o00062-G
    def test_undo_restores_the_citation_text(self, tmp_path: Path, mutate: Callable):
        root = _project(
            tmp_path,
            {CODE: _code("# Implements: REQ-d00001-C"), TEST: _test("# Verifies: REQ-d00001-C")},
        )
        graph = build_graph(repo_root=root)
        code, test = _citing_node(graph, NodeKind.CODE), _citing_node(graph, NodeKind.TEST)
        before = (code.get_field("raw_text"), test.get_field("raw_text"))

        mutate(graph)
        assert (code.get_field("raw_text"), test.get_field("raw_text")) != before
        graph.undo_last()

        assert (code.get_field("raw_text"), test.get_field("raw_text")) == before

    # Verifies: REQ-d00134-F
    def test_save_after_undo_writes_no_code_or_test_file(self, tmp_path: Path):
        root = _project(
            tmp_path,
            {CODE: _code("# Implements: REQ-d00001-C"), TEST: _test("# Verifies: REQ-d00001-C")},
        )
        graph = build_graph(repo_root=root)
        on_disk = _snapshot(root)

        graph.rename_node("REQ-d00001", "REQ-d00009")
        graph.undo_last()
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        assert not {str(root / CODE), str(root / TEST)} & set(result["files_modified"])
        assert _snapshot(root) == on_disk


# ─────────────────────────────────────────────────────────────────────────────
# A citation in an associate's file and the write scope (REQ-d00253-G)
# ─────────────────────────────────────────────────────────────────────────────


class _Federation:
    def __init__(self, tmp_path: Path) -> None:
        self.associate = _write_repo(
            tmp_path / "lib",
            {
                CODE: _code("# Implements: REQ-d00001-C"),
                TEST: _test("# Verifies: REQ-d00001-A"),
            },
            namespace="LIB",
            with_spec=False,
        )
        self.root = _write_repo(
            tmp_path / "core",
            {},
            extra_config=(f'\n[associates.lib]\npath = "{self.associate}"\nnamespace = "LIB"\n'),
        )
        self.graph = build_graph(repo_root=self.root)
        self.before = {"core": _snapshot(self.root), "lib": _snapshot(self.associate)}


class TestAssociateCitationAndWriteScope:
    """Validates REQ-d00253-G for a citation respelled in an associate."""

    # Verifies: REQ-d00253-G
    def test_save_outside_the_write_scope_writes_nothing_and_keeps_the_work(self, tmp_path: Path):
        federation = _Federation(tmp_path)
        graph = federation.graph

        graph.rename_node("REQ-d00001", "REQ-d00009")
        code = _citing_node(graph, NodeKind.CODE)
        assert code.get_field("raw_text") == "# Implements: REQ-d00009-C"
        logged = len(graph.mutation_log)
        result = render_save(graph, repo_root=federation.root, write_associates=False)

        assert result["success"] is False
        assert result["code"] == "write_scope_declined"
        assert result["files_modified"] == []
        assert _snapshot(federation.root) == federation.before["core"]
        assert _snapshot(federation.associate) == federation.before["lib"]
        assert len(graph.mutation_log) == logged

    # Verifies: REQ-d00253-G, REQ-p00017-B
    def test_save_within_the_write_scope_writes_both_members(self, tmp_path: Path):
        federation = _Federation(tmp_path)
        graph = federation.graph

        graph.rename_node("REQ-d00001", "REQ-d00009")
        result = render_save(graph, repo_root=federation.root, write_associates=True)

        assert result["success"] is True, result.get("errors")
        dev = (federation.root / "spec" / "dev.md").read_text(encoding="utf-8")
        assert "# REQ-d00009: Child" in dev
        assert (federation.associate / CODE).read_text(encoding="utf-8") == _code(
            "# Implements: REQ-d00009-C"
        )
        assert (federation.associate / TEST).read_text(encoding="utf-8") == _test(
            "# Verifies: REQ-d00009-A"
        )


# ─────────────────────────────────────────────────────────────────────────────
# A save changes no line of a code or test file but the citations (REQ-d00132-M)
# ─────────────────────────────────────────────────────────────────────────────

_ROUND_TRIP_CODE = """
import os

# Implements: REQ-d00001-C, REQ-p00001-A+B
def f():

    pass


    # Implements: REQ-d00001
    def g():
        pass

# Implements: REQ-d00002
def h():
    pass
"""

_ROUND_TRIP_TEST = """

# Verifies: REQ-d00001-C,
#   REQ-p00001-B
def test_a():
    pass

# Verifies: REQ-p00001-A
# Verifies: REQ-d00001-A
def test_b():
    pass


def test_c():
    pass
"""


def _changed_lines(before: str, after: str) -> list[int]:
    old, new = before.split("\n"), after.split("\n")
    assert len(old) == len(new), "a respelling changes no line count"
    return [number for number, (a, b) in enumerate(zip(old, new, strict=True), start=1) if a != b]


class TestSaveChangesOnlyRespelledLines:
    """Validates REQ-d00132-M."""

    # Verifies: REQ-d00132-M
    def test_round_trip_changes_only_the_respelled_lines(self, tmp_path: Path):
        root = _project(tmp_path, {CODE: _ROUND_TRIP_CODE, TEST: _ROUND_TRIP_TEST})
        graph = build_graph(repo_root=root)

        graph.rename_node("REQ-d00001", "REQ-d00009")
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        code = (root / CODE).read_text(encoding="utf-8")
        test = (root / TEST).read_text(encoding="utf-8")
        assert _changed_lines(_ROUND_TRIP_CODE, code) == [4, 10]
        assert _changed_lines(_ROUND_TRIP_TEST, test) == [3, 9]
        assert "# Implements: REQ-d00009-C, REQ-p00001-A+B" in code.split("\n")
        assert "    # Implements: REQ-d00009" in code.split("\n")
        assert "# Verifies: REQ-d00009-C," in test.split("\n")
        assert "# Verifies: REQ-d00009-A" in test.split("\n")

    # Verifies: REQ-d00132-J
    def test_respelled_test_file_reports_no_part_changed_beyond_the_edits(self, tmp_path: Path):
        """The test file holds an uncited test function and a test cited from
        two stacked comments; the rename respells citations and nothing else,
        so no part is reported as changed beyond the edits."""
        root = _project(tmp_path, {TEST: _ROUND_TRIP_TEST})
        graph = build_graph(repo_root=root)

        graph.rename_node("REQ-d00001", "REQ-d00009")
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        assert str(root / TEST) in result["files_modified"]
        # The spec file is written too, and its sibling requirement's placeholder
        # hash is corrected there; that part is legitimately reported.
        assert [c for c in result["changed_beyond_edits"] if c["file"] == TEST] == []

    @pytest.mark.parametrize(
        "edit,line",
        [
            pytest.param(lambda text: text + "# appended later\n", 17, id="appended-line"),
            pytest.param(
                lambda text: text.replace("import os", "import sys"), 2, id="changed-line"
            ),
        ],
    )
    # Verifies: REQ-d00132-M
    def test_file_changed_on_disk_since_the_build_refuses_the_save(
        self, tmp_path: Path, edit: Callable[[str], str], line: int
    ):
        root = _project(tmp_path, {CODE: _ROUND_TRIP_CODE, TEST: _ROUND_TRIP_TEST})
        graph = build_graph(repo_root=root)
        (root / CODE).write_text(edit(_ROUND_TRIP_CODE), encoding="utf-8")
        on_disk = _snapshot(root)

        graph.rename_node("REQ-d00001", "REQ-d00009")
        logged = len(graph.mutation_log)
        result = render_save(graph, repo_root=root)

        assert result["success"] is False
        assert result["files_modified"] == []
        assert _snapshot(root) == on_disk
        assert any(error.startswith(f"{CODE}:{line}:") for error in result["errors"]), result[
            "errors"
        ]
        assert len(graph.mutation_log) == logged

    @pytest.mark.parametrize(
        "before,after",
        [
            pytest.param(
                b"# Implements: REQ-d00001-C\ndef f():\n    pass",
                b"# Implements: REQ-d00009-C\ndef f():\n    pass",
                id="no-final-newline",
            ),
            pytest.param(
                b"# Implements: REQ-d00001-C\r\ndef f():\r\n    pass\r\n",
                b"# Implements: REQ-d00009-C\r\ndef f():\r\n    pass\r\n",
                id="crlf-line-endings",
            ),
            pytest.param(
                b"\r\n# Verifies: REQ-d00001-C\r\ndef test_f():\r\n    pass",
                b"\r\n# Verifies: REQ-d00009-C\r\ndef test_f():\r\n    pass",
                id="crlf-and-no-final-newline",
            ),
        ],
    )
    # Verifies: REQ-d00132-M
    def test_line_endings_and_final_newline_save_back_byte_for_byte(
        self, tmp_path: Path, before: bytes, after: bytes
    ):
        relative = TEST if b"Verifies" in before else CODE
        root = _project(tmp_path, {relative: before.decode("utf-8")})
        graph = build_graph(repo_root=root)

        graph.rename_node("REQ-d00001", "REQ-d00009")
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        assert (root / relative).read_bytes() == after

    # Verifies: REQ-d00132-M
    def test_file_mixing_line_endings_is_not_rewritten(self, tmp_path: Path):
        root = _project(tmp_path, {CODE: "# Implements: REQ-d00001-C\r\ndef f():\n    pass\r\n"})
        graph = build_graph(repo_root=root)
        on_disk = _snapshot(root)

        graph.rename_node("REQ-d00001", "REQ-d00009")
        logged = len(graph.mutation_log)
        result = render_save(graph, repo_root=root)

        assert result["success"] is False
        assert result["files_modified"] == []
        assert _snapshot(root) == on_disk
        assert any(error.startswith(f"{CODE}:") for error in result["errors"]), result["errors"]
        assert len(graph.mutation_log) == logged


# ─────────────────────────────────────────────────────────────────────────────
# Deleting a requirement writes only its own file (REQ-d00132-I)
# ─────────────────────────────────────────────────────────────────────────────

_DRAFT_CITER = """# REQ-d00003: Draft citer

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00001-A

## Assertions

A. The tool SHALL do drafting.

*End* *Draft citer* | **Hash**: 00000000
---
"""


class TestDeletingARequirementWritesItsOwnFile:
    """Validates REQ-d00132-I for a deletion."""

    # Verifies: REQ-d00132-I
    def test_cited_requirements_file_is_not_written(self, tmp_path: Path):
        root = _project(tmp_path, {"spec/draft.md": _DRAFT_CITER})
        graph = build_graph(repo_root=root)
        prd = root / "spec" / "prd.md"
        prd_bytes, prd_mtime = prd.read_bytes(), prd.stat().st_mtime_ns

        graph.delete_requirement("REQ-d00003")
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        assert result["files_modified"] == [str(root / "spec" / "draft.md")]
        assert prd.read_bytes() == prd_bytes
        assert prd.stat().st_mtime_ns == prd_mtime


# ─────────────────────────────────────────────────────────────────────────────
# A code or test file renders as written (REQ-d00131-F, REQ-d00131-G)
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceFileRendersAsWritten:
    """Validates REQ-d00131-F and REQ-d00131-G for code and test files."""

    @pytest.mark.parametrize(
        "relative,text",
        [
            pytest.param(CODE, _ROUND_TRIP_CODE, id="code"),
            pytest.param(TEST, _ROUND_TRIP_TEST, id="test"),
        ],
    )
    # Verifies: REQ-d00131-G
    def test_render_file_reproduces_the_file(self, tmp_path: Path, relative: str, text: str):
        root = _project(tmp_path, {relative: text})
        graph = build_graph(repo_root=root)

        assert render_file(_file_node(graph, relative), _resolver(graph)) == text

    # Verifies: REQ-d00131-F
    def test_test_cited_from_two_comments_renders_both(self, tmp_path: Path):
        root = _project(tmp_path, {TEST: _ROUND_TRIP_TEST})
        graph = build_graph(repo_root=root)

        rendered = render_file(_file_node(graph, TEST), _resolver(graph)).split("\n")

        assert rendered[7:9] == ["# Verifies: REQ-p00001-A", "# Verifies: REQ-d00001-A"]


# ─────────────────────────────────────────────────────────────────────────────
# Deleting a cited Assertion of a provisional requirement (REQ-p00017-M)
# ─────────────────────────────────────────────────────────────────────────────


class TestDeletedAssertionCitedFromCodeStillRefuses:
    """Validates REQ-p00017-M: the deleted *Assertion* itself cannot be carried."""

    @pytest.mark.parametrize(
        "files,place",
        [
            pytest.param({CODE: _code("# Implements: REQ-p00001-B")}, f"{CODE}:3", id="code"),
            pytest.param({TEST: _test("# Verifies: REQ-p00001-B")}, f"{TEST}:2", id="test"),
        ],
    )
    # Verifies: REQ-p00017-M
    def test_deletion_is_refused_naming_the_citation(
        self, tmp_path: Path, files: dict[str, str], place: str
    ):
        root = _project(tmp_path, files)
        graph = build_graph(repo_root=root)
        on_disk = _snapshot(root)

        with pytest.raises(DeletionWouldRepointError) as refused:
            graph.delete_assertion("REQ-p00001-B")

        assert f"({place}) cites REQ-p00001-B" in str(refused.value)
        assert graph.find_by_id("REQ-p00001-D") is not None
        assert len(graph.mutation_log) == 0
        assert _snapshot(root) == on_disk


# ─────────────────────────────────────────────────────────────────────────────
# Renaming a journey respells the test citations of it and its steps
# (REQ-p00017-B)
# ─────────────────────────────────────────────────────────────────────────────

_JOURNEY_SCANNING = '\n[scanning.journey]\ndirectories = ["spec"]\n'

_JOURNEYS = """# User Journeys

---

### JNY-Flow-01: Flow

**Actor**: User
**Goal**: Finish the flow
Validates: REQ-d00001-A

## Steps

1. Open the page
2. Submit the form

*End* *JNY-Flow-01*
---
"""

_JOURNEY_TEST = """
# Verifies: JNY-Flow-01
def test_whole():
    pass

# Verifies: JNY-Flow-01/2
def test_step():
    pass
"""


def _journey_project(tmp_path: Path, test_text: str = _JOURNEY_TEST) -> Path:
    return _write_repo(
        tmp_path / "repo",
        {"spec/journeys.md": _JOURNEYS, TEST: test_text},
        extra_config=_JOURNEY_SCANNING,
    )


def _tests_under(node) -> set[str]:
    return {
        edge.target.get_label()
        for edge in node.iter_outgoing_edges()
        if edge.target.kind == NodeKind.TEST
    }


class TestRenamingAJourneyRespellsItsTestCitations:
    """Validates REQ-p00017-B for citations of a journey and its steps."""

    # Verifies: REQ-p00017-B
    def test_journey_and_step_citations_follow_the_rename(self, tmp_path: Path):
        root = _journey_project(tmp_path)
        graph = build_graph(repo_root=root)

        graph.rename_node("JNY-Flow-01", "JNY-Flow-02")
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        saved = (root / TEST).read_text(encoding="utf-8")
        assert saved == _JOURNEY_TEST.replace("JNY-Flow-01", "JNY-Flow-02")
        assert _changed_lines(_JOURNEY_TEST, saved) == [2, 6]
        rebuilt = build_graph(repo_root=root)
        assert rebuilt.unresolved_references() == []
        assert _tests_under(rebuilt.find_by_id("JNY-Flow-02")) == {"test_whole"}
        assert _tests_under(rebuilt.find_by_id("JNY-Flow-02/2")) == {"test_step"}


# ─────────────────────────────────────────────────────────────────────────────
# The list of unbound citations follows a rename (REQ-p00017-B)
# ─────────────────────────────────────────────────────────────────────────────

_UNBOUND_TEST = """# Verifies: REQ-d00001-B
VALUE = 1

# Verifies: REQ-d00001-A
def test_a():
    pass
"""


def _unbound(graph) -> list[tuple[str, int, tuple[str, ...]]]:
    return [(u.path, u.line, tuple(u.targets)) for u in graph.unbound_citations()]


class TestUnboundCitationsFollowARename:
    """Validates REQ-p00017-B for a citation that binds to no test."""

    # Verifies: REQ-p00017-B
    def test_unbound_list_follows_rename_save_and_undo(self, tmp_path: Path):
        root = _project(tmp_path, {TEST: _UNBOUND_TEST})
        graph = build_graph(repo_root=root)
        assert _unbound(graph) == [(TEST, 1, ("REQ-d00001-B",))]

        graph.rename_node("REQ-d00001", "REQ-d00009")

        assert _unbound(graph) == [(TEST, 1, ("REQ-d00009-B",))]
        for _name, member in graph._live_graphs():
            assert [tuple(u.targets) for u in member.unbound_citations()] == [("REQ-d00009-B",)]
        graph.undo_last()
        assert _unbound(graph) == [(TEST, 1, ("REQ-d00001-B",))]

        graph.rename_node("REQ-d00001", "REQ-d00009")
        in_memory = _unbound(graph)
        assert render_save(graph, repo_root=root)["success"] is True
        assert _unbound(build_graph(repo_root=root)) == in_memory


# ─────────────────────────────────────────────────────────────────────────────
# A rename onto an identifier an unresolved reference names (REQ-p00017-P)
# ─────────────────────────────────────────────────────────────────────────────

_SPEC_CITING_MISSING = """# REQ-d00003: Extra

**Level**: dev | **Status**: Active | **Implements**: REQ-p00077

## Assertions

A. The tool SHALL do extra.

*End* *Extra* | **Hash**: 00000000
---
"""

# Each case: the files, the extra configuration, the rename, the identifier
# renamed and the identifier taken, and the place the refusal must name.
NAMED_BY_UNRESOLVED_CASES = [
    pytest.param(
        {CODE: _code("# Implements: REQ-d00077-A")},
        "",
        _rename_requirement("REQ-d00002", "REQ-d00077"),
        ("REQ-d00002", "REQ-d00077"),
        f"({CODE}:3) names REQ-d00077-A",
        id="requirement-named-by-code",
    ),
    pytest.param(
        {CODE: _code("# Implements: REQ-d00001-E")},
        "",
        _rename_assertion("REQ-d00001-C", "E"),
        ("REQ-d00001-C", "REQ-d00001-E"),
        f"({CODE}:3) names REQ-d00001-E",
        id="assertion-named-by-code",
    ),
    pytest.param(
        {"spec/extra.md": _SPEC_CITING_MISSING},
        "",
        _rename_requirement("REQ-p00001", "REQ-p00077"),
        ("REQ-p00001", "REQ-p00077"),
        "REQ-d00003 (spec/extra.md:1) names REQ-p00077",
        id="requirement-named-by-a-requirement",
    ),
    pytest.param(
        {"spec/journeys.md": _JOURNEYS, TEST: _test("# Verifies: JNY-Flow-09")},
        _JOURNEY_SCANNING,
        _rename_requirement("JNY-Flow-01", "JNY-Flow-09"),
        ("JNY-Flow-01", "JNY-Flow-09"),
        f"({TEST}:2) names JNY-Flow-09",
        id="journey-named-by-test",
    ),
]


class TestRenameOntoAnUnresolvedReferenceIsRefused:
    """Validates REQ-p00017-P."""

    @pytest.mark.parametrize("files,extra,mutate,ids,named", NAMED_BY_UNRESOLVED_CASES)
    # Verifies: REQ-p00017-P
    def test_refusal_names_each_reference_and_changes_nothing(
        self,
        tmp_path: Path,
        files: dict[str, str],
        extra: str,
        mutate: Callable,
        ids: tuple[str, str],
        named: str,
    ):
        root = _write_repo(tmp_path / "repo", files, extra_config=extra)
        graph = build_graph(repo_root=root)
        old, new = ids
        renamed = graph.find_by_id(old)
        logged = len(graph.mutation_log)

        with pytest.raises(ValueError) as refused:
            mutate(graph)

        assert f"Cannot rename to {new}" in str(refused.value)
        assert named in str(refused.value), str(refused.value)
        assert graph.find_by_id(old) is renamed
        assert graph.find_by_id(new) is None
        assert len(graph.mutation_log) == logged

    # Verifies: REQ-p00017-P
    def test_fault_that_is_not_a_missing_target_does_not_block(self, tmp_path: Path):
        """A citation under a keyword the file refuses designates nothing, so
        the identifier it spells is free to take."""
        root = _project(tmp_path, {TEST: _test("# Implements: REQ-d00077")})
        graph = build_graph(repo_root=root)

        graph.rename_node("REQ-d00002", "REQ-d00077")

        assert graph.find_by_id("REQ-d00077") is not None
        assert graph.find_by_id("REQ-d00002") is None

    # Verifies: REQ-p00017-P
    def test_unresolved_reference_in_an_associate_refuses_a_root_rename(self, tmp_path: Path):
        associate = _write_repo(
            tmp_path / "lib",
            {CODE: _code("# Implements: REQ-d00077-A")},
            namespace="LIB",
            with_spec=False,
        )
        root = _write_repo(
            tmp_path / "core",
            {},
            extra_config=f'\n[associates.lib]\npath = "{associate}"\nnamespace = "LIB"\n',
        )
        graph = build_graph(repo_root=root)
        logged = len(graph.mutation_log)

        with pytest.raises(ValueError) as refused:
            graph.rename_node("REQ-d00002", "REQ-d00077")

        assert f"({CODE}:3) names REQ-d00077-A" in str(refused.value), str(refused.value)
        assert graph.find_by_id("REQ-d00002") is not None
        assert graph.find_by_id("REQ-d00077") is None
        assert len(graph.mutation_log) == logged


# ─────────────────────────────────────────────────────────────────────────────
# A relationship from code or a test changes only in its comment (REQ-o00062-U)
# ─────────────────────────────────────────────────────────────────────────────


def _edges_of(node) -> set[tuple]:
    return {
        (edge.source.id, edge.target.id, edge.kind, tuple(edge.assertion_targets or ()))
        for edge in (*node.iter_incoming_edges(), *node.iter_outgoing_edges())
    }


EDGE_CHANGES = [
    pytest.param(
        lambda graph, source: graph.add_edge(source, "REQ-d00002", EdgeKind.IMPLEMENTS),
        id="add_edge",
    ),
    pytest.param(lambda graph, source: graph.delete_edge(source, "REQ-d00001"), id="delete_edge"),
    pytest.param(
        lambda graph, source: graph.change_edge_kind(source, "REQ-d00001", EdgeKind.REFINES),
        id="change_edge_kind",
    ),
    pytest.param(
        lambda graph, source: graph.change_edge_targets(source, "REQ-d00001", ["B"]),
        id="change_edge_targets",
    ),
]

CITING_KINDS = [
    pytest.param(NodeKind.CODE, "Implements:", id="code"),
    pytest.param(NodeKind.TEST, "Verifies:", id="test"),
]


def _citing_project(tmp_path: Path) -> Path:
    return _project(
        tmp_path,
        {CODE: _code("# Implements: REQ-d00001-A"), TEST: _test("# Verifies: REQ-d00001-A")},
    )


class TestRelationshipFromACitationIsRefused:
    """Validates REQ-o00062-U."""

    @pytest.mark.parametrize("kind,keyword", CITING_KINDS)
    @pytest.mark.parametrize("change", EDGE_CHANGES)
    # Verifies: REQ-o00062-U
    def test_change_is_refused_pointing_at_the_comment(
        self, tmp_path: Path, kind: NodeKind, keyword: str, change: Callable
    ):
        graph = build_graph(repo_root=_citing_project(tmp_path))
        source = _citing_node(graph, kind)
        edges_before = _edges_of(source)
        logged = len(graph.mutation_log)

        with pytest.raises(ValueError) as refused:
            change(graph, source.id)

        assert f"Edit the `{keyword}` comment in the file" in str(refused.value)
        assert _edges_of(source) == edges_before
        assert len(graph.mutation_log) == logged

    # Verifies: REQ-o00062-U
    def test_relationship_from_a_requirement_is_still_changed(self, tmp_path: Path):
        graph = build_graph(repo_root=_citing_project(tmp_path))
        logged = len(graph.mutation_log)

        graph.add_edge("REQ-d00002", "REQ-d00001", EdgeKind.IMPLEMENTS)

        assert len(graph.mutation_log) == logged + 1
        assert any(
            edge.target.id == "REQ-d00002" and edge.kind == EdgeKind.IMPLEMENTS
            for edge in graph.find_by_id("REQ-d00001").iter_outgoing_edges()
        )

    @pytest.mark.parametrize("kind,keyword", CITING_KINDS)
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(
                lambda server, graph, source: server._mutate_add_edge(
                    graph, source, "REQ-d00002", "IMPLEMENTS"
                ),
                id="add_edge",
            ),
            pytest.param(
                lambda server, graph, source: server._mutate_delete_edge(
                    graph, source, "REQ-d00001", confirm=True
                ),
                id="delete_edge",
            ),
            pytest.param(
                lambda server, graph, source: server._mutate_change_edge_kind(
                    graph, source, "REQ-d00001", "REFINES"
                ),
                id="change_edge_kind",
            ),
            pytest.param(
                lambda server, graph, source: server._mutate_change_edge_targets(
                    graph, source, "REQ-d00001", ["B"]
                ),
                id="change_edge_targets",
            ),
        ],
    )
    # Verifies: REQ-o00062-U
    def test_tool_surface_reports_the_refusal(
        self, tmp_path: Path, kind: NodeKind, keyword: str, call: Callable
    ):
        server = pytest.importorskip("elspais.mcp.server")
        graph = build_graph(repo_root=_citing_project(tmp_path))
        source = _citing_node(graph, kind)
        logged = len(graph.mutation_log)

        result = call(server, graph, source.id)

        assert result["success"] is False
        assert f"Edit the `{keyword}` comment in the file" in result["error"]
        assert len(graph.mutation_log) == logged


# ─────────────────────────────────────────────────────────────────────────────
# A definition block after a section's prose renders after one blank line
# (REQ-d00131-B)
# ─────────────────────────────────────────────────────────────────────────────

_DEFINING = """# REQ-d00004: Defining

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The tool SHALL do defining.

## Rationale

Why it matters.

Requirement Location
: The file and line where a requirement is declared.

*End* *Defining* | **Hash**: 00000000
---
"""


def _requirement_block(text: str, header: str) -> list[str]:
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("*End*"))
    return lines[start : end + 1]


class TestDefinitionBlockAfterSectionProse:
    """Validates REQ-d00131-B for a headingless block within a requirement."""

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(lambda g: g.update_title("REQ-d00004", "Defined"), id="update_title"),
            pytest.param(
                lambda g: g.update_assertion("REQ-d00004-A", "The tool SHALL do more."),
                id="update_assertion",
            ),
        ],
    )
    # Verifies: REQ-d00131-B
    def test_rerendered_requirement_keeps_one_blank_line_before_the_term(
        self, tmp_path: Path, mutate: Callable
    ):
        root = _project(tmp_path, {"spec/defining.md": _DEFINING})
        graph = build_graph(repo_root=root)

        mutate(graph)
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        saved = (root / "spec" / "defining.md").read_text(encoding="utf-8")
        block = _requirement_block(saved, "# REQ-d00004:")
        term = block.index("Requirement Location")
        assert block[term - 2 : term + 2] == [
            "Why it matters.",
            "",
            "Requirement Location",
            ": The file and line where a requirement is declared.",
        ]
        assert not any(a == b == "" for a, b in zip(block, block[1:], strict=False)), block
