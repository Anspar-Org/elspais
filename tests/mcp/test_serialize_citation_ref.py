"""How a serialized node spells the citation it makes of an assertion.

The ``ref_id`` a parent entry carries is an identifier, so it is spelled
through the grammar of the repository owning the cited requirement and names
every label the edge names. The project here configures ``/`` between a
requirement and its first label and ``&`` between labels, so a spelling that
assumed the defaults would be visibly wrong.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from elspais.graph.factory import build_graph
from elspais.mcp.server import _serialize_node_generic
from elspais.utilities.patterns import GrammarUnavailable

_CONFIG = """\
version = 5

[project]
name = "slashes"
namespace = "REQ"

[id-patterns.assertions]
label_style = "uppercase"
separator = "/"
multi_separator = "&"

[levels.prd]
rank = 1
letter = "p"
implements = []

[levels.dev]
rank = 2
letter = "d"
implements = ["dev", "prd"]

[scanning.spec]
directories = ["spec"]
"""

_SPEC = """\
# REQ-p00001: Widget

**Level**: prd | **Status**: Active

## Assertions

A. The system SHALL frob.

B. The system SHALL twiddle.

C. The system SHALL polish.

*End* *Widget* | **Hash**: 00000000
---

# REQ-d00001: Widget implementation

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001/A

## Assertions

A. The system SHALL flush.

*End* *Widget implementation* | **Hash**: 00000000
---
"""


@pytest.fixture
def slash_graph(tmp_path: Path):
    (tmp_path / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "requirements.md").write_text(_SPEC, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return build_graph(repo_root=tmp_path)


def _parent_entry(serialized: dict, parent_id: str) -> dict:
    entries = [p for p in serialized["parents"] if p["id"] == parent_id]
    assert len(entries) == 1, serialized["parents"]
    return entries[0]


class TestCitationRefSpelling:
    @pytest.mark.parametrize(
        "labels, expected",
        [
            pytest.param(None, "REQ-p00001/A", id="one-label-as-built"),
            pytest.param(["A", "B"], "REQ-p00001/A&B", id="two-labels-on-one-edge"),
        ],
    )
    # Verifies: REQ-p00014-U
    def test_REQ_p00014_U_ref_id_is_spelled_through_the_owning_grammar(
        self, slash_graph, labels, expected
    ):
        """A citation of assertions is spelled with the configured separators
        and names every label its edge carries."""
        if labels is not None:
            slash_graph.change_edge_targets("REQ-d00001", "REQ-p00001", labels)
        child = slash_graph.find_by_id("REQ-d00001")
        resolver = slash_graph.repo_for_node(child).graph.resolver

        entry = _parent_entry(_serialize_node_generic(child, slash_graph), "REQ-p00001")

        assert entry["ref_id"] == expected
        assert entry["ref_id"] == resolver.make_assertion_ref(
            "REQ-p00001", list(entry["assertion_targets"])
        )

    # Verifies: REQ-p00014-U
    def test_REQ_p00014_U_ref_id_without_a_grammar_is_refused(self, slash_graph):
        """Without the graph holding the grammar, an assertion citation cannot
        be spelled, and the serializer says so rather than assuming one."""
        child = slash_graph.find_by_id("REQ-d00001")

        with pytest.raises(GrammarUnavailable):
            _serialize_node_generic(child, None)

    # Verifies: REQ-p00014-U
    def test_REQ_p00014_U_whole_requirement_citation_needs_no_grammar(self, slash_graph):
        """Control: a node citing no assertion serializes without a grammar,
        so the refusal above is about spelling an assertion reference."""
        parent = slash_graph.find_by_id("REQ-p00001")

        serialized = _serialize_node_generic(parent, None)

        assert serialized["parents"] == []
