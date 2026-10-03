"""Deleting an *Assertion* of a provisional or aspirational requirement.

The requirement is still being drafted, so the *Assertion* is removed and each
later one takes the label before its own (REQ-p00017-L). References the graph
holds follow their *Assertion* (REQ-p00017-B), the mutation records the
former-to-successor mapping (REQ-p00017-C), and a deletion that would leave a
reference designating something else is refused (REQ-p00017-M).

Each test writes a small repository into ``tmp_path`` because what is under
test is observable only through the parsed citations of other files and
through a save and rebuild.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from elspais.graph.builder import DeletionWouldRepointError
from elspais.graph.comments import CommentEvent, CommentThread
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.render import render_file, render_save

_CONFIG = """version = 5

[project]
name = "compaction"
namespace = "REQ"

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

[scanning.journey]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]
"""

_NUMERIC_SERIES = """
[id-patterns.assertions]
label_style = "numeric_1based"
max_count = 99
"""

_LETTER_TEXTS = {
    "A": "The tool SHALL do alpha.",
    "B": "The tool SHALL do beta.",
    "C": "The tool SHALL do gamma.",
    "D": "The tool SHALL do delta.",
}

PARENT = "REQ-p00001"

# The default configuration places Draft in the provisional role and Roadmap
# in the aspirational role; both delete by removing and compacting.
COMPACTING_STATUSES = [
    pytest.param("Draft", id="provisional"),
    pytest.param("Roadmap", id="aspirational"),
]


def _prd(status: str, texts: dict[str, str]) -> str:
    assertions = "".join(f"{label}. {text}\n\n" for label, text in texts.items())
    return (
        f"# {PARENT}: Parent\n\n"
        f"**Level**: prd | **Status**: {status} | **Implements**: -\n\n"
        "## Assertions\n\n"
        f"{assertions}"
        "## Rationale\n\n"
        "Why it matters.\n\n"
        "*End* *Parent* | **Hash**: 00000000\n---\n"
    )


# A title and a paragraph above the citing requirement, so its header -- its
# *Requirement Location* -- is neither the file's first line nor the line
# holding the citation.
_DEV_PREAMBLE = "# Child requirements\n\nIntroduction.\n\n"
_DEV_HEADER_LINE_AFTER_PREAMBLE = 5


def _dev(cites: str, preamble: str = "") -> str:
    return (
        f"{preamble}"
        "# REQ-d00001: Child\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: {cites}\n\n"
        "## Assertions\n\n"
        "A. The tool SHALL do child.\n\n"
        "*End* *Child* | **Hash**: 00000000\n---\n"
    )


def _journey(validates: str) -> str:
    return (
        "# Journeys\n\n"
        "### JNY-001: Flow\n\n"
        "**Actor**: User\n"
        "**Goal**: Finish the flow\n"
        f"Validates: {validates}\n\n"
        "## Steps\n\n"
        "1. Go\n\n"
        "*End* *Flow*\n---\n"
    )


def _write_project(
    tmp_path: Path,
    *,
    status: str = "Draft",
    texts: dict[str, str] | None = None,
    numeric: bool = False,
    dev_cites: str | None = None,
    dev_preamble: str = "",
    journey_validates: str | None = None,
    code_cites: str | None = None,
    test_cites: str | None = None,
) -> Path:
    """Write a repository whose REQ-p00001 carries *texts*, cited as asked."""
    root = tmp_path / "repo"
    for directory in ("spec", "src", "tests"):
        (root / directory).mkdir(parents=True)
    config = _CONFIG + (_NUMERIC_SERIES if numeric else "")
    (root / ".elspais.toml").write_text(config, encoding="utf-8")
    (root / "spec" / "prd.md").write_text(_prd(status, texts or _LETTER_TEXTS), encoding="utf-8")
    if dev_cites:
        (root / "spec" / "dev.md").write_text(_dev(dev_cites, dev_preamble), encoding="utf-8")
    if journey_validates:
        (root / "spec" / "journeys.md").write_text(_journey(journey_validates), encoding="utf-8")
    code = f"# Implements: {code_cites}\n" if code_cites else ""
    (root / "src" / "m.py").write_text(f"{code}def f():\n    pass\n", encoding="utf-8")
    test = f"# Verifies: {test_cites}\n" if test_cites else ""
    (root / "tests" / "test_m.py").write_text(
        f"\n{test}def test_f():\n    pass\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def _assertions(graph) -> list[tuple[str, str, str]]:
    """REQ-p00001's assertions in render order, as (id, label, text)."""
    parent = graph.find_by_id(PARENT)
    edges = sorted(
        (edge for edge in parent.iter_outgoing_edges() if edge.target.kind == NodeKind.ASSERTION),
        key=lambda edge: edge.metadata.get("render_order", 0.0),
    )
    return [(e.target.id, e.target.get_field("label"), e.target.get_label()) for e in edges]


def _cited_labels(graph, citing_id: str) -> list[str]:
    """The labels of REQ-p00001 that *citing_id* cites."""
    citing = graph.find_by_id(citing_id)
    return sorted(
        label
        for edge in citing.iter_incoming_edges()
        if edge.source.id == PARENT
        for label in edge.assertion_targets
    )


def _root_graph(federated):
    return federated.repo_for(PARENT).graph


# ─────────────────────────────────────────────────────────────────────────────
# Removal and compaction (REQ-p00017-L)
# ─────────────────────────────────────────────────────────────────────────────


class TestDeletionCompactsTheLabelSeries:
    """Validates REQ-p00017-L."""

    @pytest.mark.parametrize("status", COMPACTING_STATUSES)
    @pytest.mark.parametrize(
        "deleted,expected",
        [
            pytest.param(
                "A",
                [("A", _LETTER_TEXTS["B"]), ("B", _LETTER_TEXTS["C"]), ("C", _LETTER_TEXTS["D"])],
                id="first",
            ),
            pytest.param(
                "B",
                [("A", _LETTER_TEXTS["A"]), ("B", _LETTER_TEXTS["C"]), ("C", _LETTER_TEXTS["D"])],
                id="middle",
            ),
            pytest.param(
                "D",
                [("A", _LETTER_TEXTS["A"]), ("B", _LETTER_TEXTS["B"]), ("C", _LETTER_TEXTS["C"])],
                id="last",
            ),
        ],
    )
    # Verifies: REQ-p00017-L
    def test_REQ_p00017_L_later_assertions_take_the_preceding_label(
        self, tmp_path: Path, status: str, deleted: str, expected: list[tuple[str, str]]
    ):
        """The deleted text is gone and each later text moves down one label."""
        graph = build_graph(repo_root=_write_project(tmp_path, status=status))

        graph.delete_assertion(f"{PARENT}-{deleted}")

        assert [(label, text) for _id, label, text in _assertions(graph)] == expected
        assert [node_id for node_id, _l, _t in _assertions(graph)] == [
            f"{PARENT}-{label}" for label, _t in expected
        ]
        assert graph.find_by_id(f"{PARENT}-D") is None
        assert _LETTER_TEXTS[deleted] in {n.get_label() for n in graph.deleted_nodes()}

    # Verifies: REQ-p00017-L
    def test_REQ_p00017_L_multi_character_labels_move_in_series_order(self, tmp_path: Path):
        """Labels 1..12 with 9 deleted: 10, 11 and 12 become 9, 10 and 11, in
        the order of the series rather than of the spelling."""
        texts = {str(n): f"The tool SHALL do thing {n}." for n in range(1, 13)}
        root = _write_project(tmp_path, texts=texts, numeric=True)
        graph = build_graph(repo_root=root)

        graph.delete_assertion(f"{PARENT}-9")

        labels = [(label, text) for _id, label, text in _assertions(graph)]
        assert labels == [(str(n), texts[str(n)]) for n in range(1, 9)] + [
            ("9", texts["10"]),
            ("10", texts["11"]),
            ("11", texts["12"]),
        ]
        assert graph.find_by_id(f"{PARENT}-12") is None


# ─────────────────────────────────────────────────────────────────────────────
# References held in the graph follow their Assertion (REQ-p00017-B)
# ─────────────────────────────────────────────────────────────────────────────


class TestReferencesFollowTheirAssertion:
    """Validates REQ-p00017-B under compaction."""

    # Verifies: REQ-p00017-B, REQ-p00017-L
    def test_REQ_p00017_B_multi_character_citation_follows_in_memory_and_on_disk(
        self, tmp_path: Path
    ):
        """A requirement citing 11 cites 10 once 9 is deleted -- in memory,
        in the saved file, and after a rebuild, where it resolves to the
        same text it designated before."""
        texts = {str(n): f"The tool SHALL do thing {n}." for n in range(1, 13)}
        root = _write_project(tmp_path, texts=texts, numeric=True, dev_cites=f"{PARENT}-11")
        graph = build_graph(repo_root=root)
        assert _cited_labels(graph, "REQ-d00001") == ["11"]

        graph.delete_assertion(f"{PARENT}-9")

        assert _cited_labels(graph, "REQ-d00001") == ["10"]
        result = render_save(graph, repo_root=root)
        assert result["success"] is True, result.get("errors")
        dev_text = (root / "spec" / "dev.md").read_text(encoding="utf-8")
        assert f"**Implements**: {PARENT}-10" in dev_text
        assert f"{PARENT}-11" not in dev_text

        rebuilt = build_graph(repo_root=root)
        assert _cited_labels(rebuilt, "REQ-d00001") == ["10"]
        assert rebuilt.find_by_id(f"{PARENT}-10").get_label() == texts["11"]
        assert not any(f.source_id == "REQ-d00001" for f in rebuilt.unresolved_references())

    # Verifies: REQ-p00017-B
    def test_REQ_p00017_B_citing_requirement_and_journey_files_are_rewritten(self, tmp_path: Path):
        """After B is deleted, the requirement citing C and the journey
        validating D are saved under C's and D's new labels, and both resolve
        to the texts they designated before."""
        root = _write_project(tmp_path, dev_cites=f"{PARENT}-C", journey_validates=f"{PARENT}-D")
        graph = build_graph(repo_root=root)

        entry = graph.delete_assertion(f"{PARENT}-B")

        assert entry.after_state["journeys_reconciled"] == ["JNY-001"]
        result = render_save(graph, repo_root=root)
        assert result["success"] is True, result.get("errors")
        assert {Path(p).name for p in result["files_modified"]} == {
            "prd.md",
            "dev.md",
            "journeys.md",
        }
        dev_text = (root / "spec" / "dev.md").read_text(encoding="utf-8")
        assert f"**Implements**: {PARENT}-B" in dev_text
        journey_text = (root / "spec" / "journeys.md").read_text(encoding="utf-8")
        assert f"Validates: {PARENT}-C" in journey_text.splitlines()

        rebuilt = build_graph(repo_root=root)
        assert _cited_labels(rebuilt, "REQ-d00001") == ["B"]
        assert rebuilt.find_by_id(f"{PARENT}-B").get_label() == _LETTER_TEXTS["C"]
        assert _cited_labels(rebuilt, "JNY-001") == ["C"]
        assert rebuilt.find_by_id(f"{PARENT}-C").get_label() == _LETTER_TEXTS["D"]
        assert rebuilt.unresolved_references() == []


# ─────────────────────────────────────────────────────────────────────────────
# The former-to-successor mapping (REQ-p00017-C)
# ─────────────────────────────────────────────────────────────────────────────


class TestDeletionRecordsTheIdentifierMapping:
    """Validates REQ-p00017-C."""

    # Verifies: REQ-p00017-C
    def test_REQ_p00017_C_entry_maps_every_former_id_to_its_successor(self, tmp_path: Path):
        graph = build_graph(repo_root=_write_project(tmp_path))

        graph.delete_assertion(f"{PARENT}-B")

        (entry,) = list(graph.mutation_log.iter_entries())
        assert entry.operation == "delete_assertion"
        assert entry.target_id == f"{PARENT}-B"
        assert entry.before_state["disposition"] == "removed"
        assert entry.before_state["renames"] == [
            {
                "old_id": f"{PARENT}-C",
                "new_id": f"{PARENT}-B",
                "old_label": "C",
                "new_label": "B",
            },
            {
                "old_id": f"{PARENT}-D",
                "new_id": f"{PARENT}-C",
                "old_label": "D",
                "new_label": "C",
            },
        ]

    # Verifies: REQ-p00017-C
    def test_REQ_p00017_C_deleting_the_last_maps_only_the_removal(self, tmp_path: Path):
        graph = build_graph(repo_root=_write_project(tmp_path))

        entry = graph.delete_assertion(f"{PARENT}-D")

        assert entry.before_state["disposition"] == "removed"
        assert entry.before_state["renames"] == []


# ─────────────────────────────────────────────────────────────────────────────
# A deletion that would repoint a reference is refused (REQ-p00017-M)
# ─────────────────────────────────────────────────────────────────────────────


def _code_id(graph) -> str:
    (node,) = list(graph.iter_by_kind(NodeKind.CODE))
    return node.id


def _test_id(graph) -> str:
    (node,) = list(graph.iter_by_kind(NodeKind.TEST))
    return node.id


# Each case: the project's citations, the assertion to delete, and the
# references the refusal must name as (citer, "path:line", cited assertion).
# The citing requirement is placed at its *Requirement Location*, the header
# line declaring its identifier; a code or test citation at the comment line
# that holds it.
REFUSED_CASES = [
    pytest.param(
        {"dev_cites": f"{PARENT}-B"},
        "B",
        [("REQ-d00001", "spec/dev.md:1", "B")],
        id="deleted-cited-by-requirement",
    ),
    pytest.param(
        {"dev_cites": f"{PARENT}-B", "dev_preamble": _DEV_PREAMBLE},
        "B",
        [("REQ-d00001", f"spec/dev.md:{_DEV_HEADER_LINE_AFTER_PREAMBLE}", "B")],
        id="deleted-cited-by-requirement-below-a-preamble",
    ),
    pytest.param(
        {"journey_validates": f"{PARENT}-B"},
        "B",
        [("JNY-001", None, "B")],
        id="deleted-cited-by-journey",
    ),
    pytest.param(
        {"code_cites": f"{PARENT}-B"},
        "B",
        [("<code>", "src/m.py:1", "B")],
        id="deleted-cited-by-code",
    ),
    pytest.param(
        {"code_cites": f"{PARENT}-C"},
        "B",
        [("<code>", "src/m.py:1", "C")],
        id="moved-cited-by-code",
    ),
    pytest.param(
        {"test_cites": f"{PARENT}-D"},
        "B",
        [("<test>", "tests/test_m.py:2", "D")],
        id="moved-cited-by-test",
    ),
    pytest.param(
        {"dev_cites": f"{PARENT}-B", "code_cites": f"{PARENT}-C"},
        "B",
        [("REQ-d00001", "spec/dev.md:1", "B"), ("<code>", "src/m.py:1", "C")],
        id="each-reference-named",
    ),
]


class TestDeletionThatWouldRepointIsRefused:
    """Validates REQ-p00017-M."""

    @pytest.mark.parametrize("citations,deleted,named", REFUSED_CASES)
    # Verifies: REQ-p00017-M
    def test_REQ_p00017_M_refusal_names_the_reason_and_each_reference(
        self, tmp_path: Path, citations: dict, deleted: str, named: list
    ):
        graph = build_graph(repo_root=_write_project(tmp_path, **citations))
        parent = graph.find_by_id(PARENT)
        before = _assertions(graph)
        hash_before = parent.get_field("hash")
        logged = len(graph.mutation_log)

        with pytest.raises(DeletionWouldRepointError) as refused:
            graph.delete_assertion(f"{PARENT}-{deleted}")

        message = str(refused.value)
        assert message.startswith(f"Cannot delete {PARENT}-{deleted}: {PARENT} is in the ")
        assert "renumbers the later ones" in message
        assert message.endswith("Remove or retarget them first.")
        for citer, place, label in named:
            resolve = {"<code>": _code_id, "<test>": _test_id}.get(citer)
            citer_id = resolve(graph) if resolve else citer
            reference = f" cites {PARENT}-{label}"
            if place is None:
                assert f"{citer_id} (" in message and reference in message, message
            else:
                assert f"{citer_id} ({place}){reference}" in message, message
        assert _assertions(graph) == before
        assert parent.get_field("hash") == hash_before
        assert len(graph.mutation_log) == logged

    # Verifies: REQ-p00017-M
    def test_REQ_p00017_M_comments_on_the_deleted_assertion_refuse(self, tmp_path: Path):
        """A comment thread anchored on the deleted assertion would move to
        the assertion that takes its label, so the deletion is refused."""
        graph = build_graph(repo_root=_write_project(tmp_path))
        source = ".elspais/comments/spec/prd.md.json"
        _root_graph(graph).add_comment_thread(
            CommentThread(
                root=CommentEvent(
                    event="comment",
                    id="c-20260101-abcdef",
                    anchor=f"{PARENT}#B",
                    author="Reviewer",
                    author_id="reviewer@example.com",
                    date="2026-01-01",
                    text="Is this right?",
                )
            ),
            source,
        )
        before = _assertions(graph)

        with pytest.raises(DeletionWouldRepointError) as refused:
            graph.delete_assertion(f"{PARENT}-B")

        assert f"comments ({source}) are anchored on {PARENT}-B" in str(refused.value)
        assert _assertions(graph) == before
        assert len(graph.mutation_log) == 0

    @pytest.mark.parametrize(
        "citations,cited_after",
        [
            pytest.param({"dev_cites": f"{PARENT}-C"}, ("REQ-d00001", ["B"]), id="requirement"),
            pytest.param({"journey_validates": f"{PARENT}-C"}, ("JNY-001", ["B"]), id="journey"),
        ],
    )
    # Verifies: REQ-p00017-M, REQ-p00017-B
    def test_REQ_p00017_M_a_moved_assertion_cited_where_the_tool_writes_is_not_refused(
        self, tmp_path: Path, citations: dict, cited_after: tuple[str, list[str]]
    ):
        """Control: a citation the tool carries to the new label does not
        stop the deletion; it follows its assertion instead."""
        graph = build_graph(repo_root=_write_project(tmp_path, **citations))

        graph.delete_assertion(f"{PARENT}-B")

        citer, labels = cited_after
        assert _cited_labels(graph, citer) == labels
        assert graph.find_by_id(f"{PARENT}-B").get_label() == _LETTER_TEXTS["C"]


# ─────────────────────────────────────────────────────────────────────────────
# Undoing a compaction (REQ-o00062-P)
# ─────────────────────────────────────────────────────────────────────────────


class TestUndoingACompaction:
    """Validates REQ-o00062-P for a removal with compaction."""

    @pytest.mark.parametrize("deleted", ["A", "B"], ids=["first", "second"])
    # Verifies: REQ-o00062-P
    def test_REQ_o00062_P_undo_restores_labels_texts_citations_and_position(
        self, tmp_path: Path, deleted: str
    ):
        root = _write_project(tmp_path, dev_cites=f"{PARENT}-C", journey_validates=f"{PARENT}-D")
        graph = build_graph(repo_root=root)
        parent = graph.find_by_id(PARENT)
        files = [
            graph.find_by_id(f"file:REQ:spec/{name}")
            for name in ("prd.md", "dev.md", "journeys.md")
        ]
        resolver = _root_graph(graph).resolver
        rendered = [render_file(f, resolver) for f in files]
        journey_body = graph.find_by_id("JNY-001").get_field("body")
        before = _assertions(graph)
        hash_before = parent.get_field("hash")

        graph.delete_assertion(f"{PARENT}-{deleted}")
        graph.undo_last()

        assert _assertions(graph) == before
        assert parent.get_field("hash") == hash_before
        assert _cited_labels(graph, "REQ-d00001") == ["C"]
        assert _cited_labels(graph, "JNY-001") == ["D"]
        assert graph.find_by_id("JNY-001").get_field("body") == journey_body
        assert [render_file(f, resolver) for f in files] == rendered
        for node_id, _label, text in before:
            assert graph.find_by_id(node_id).get_label() == text
            assert graph.repo_for(node_id) is graph.repo_for(PARENT)
        assert all(n.id != f"{PARENT}-{deleted}" for n in graph.deleted_nodes())
