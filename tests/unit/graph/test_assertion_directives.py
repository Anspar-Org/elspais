# Verifies: REQ-p00002-E, REQ-p00002-F, REQ-p00017-G, REQ-p00017-H, REQ-p00017-I
"""Assertion-level parsing directives, and RETIRED in particular.

An *Assertion* opening with a delimiter is addressing the parser, not stating
an obligation. These tests hold four things: that the grammar reads the
directive and leaves everything past its closer alone, that a directive the
tool does not recognize is reported rather than absorbed into prose, that a
retired *Assertion* leaves every denominator while keeping its letter, and
that a reference naming one reads as a reference to an *Assertion* that was
never written.

The round-trip case is load-bearing on its own: a rewrite that quietly edited
an author's commentary would be a worse defect than the counting error the
directive exists to fix.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from elspais.commands.health import check_spec_unknown_directive
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.metrics import direct_coverage_for
from elspais.graph.parsers.directives import (
    canonical_assertion_text,
    counted_assertion_labels,
    read_directive,
)
from elspais.graph.reference_faults import FaultClass
from elspais.graph.relations import EdgeKind
from elspais.graph.render import render_file
from elspais.utilities.findings import REGISTRY, Severity

CONFIG = """\
version = 5

[project]
namespace = "REQ"
name = "directives"

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[id-patterns.assertions]
label_style = "uppercase"
max_count = 26
multi_separator = "+"

[levels.prd]
rank = 1
letter = "p"
display_name = "Product"
implements = ["prd"]

[scanning.spec]
directories = ["spec"]
file_patterns = ["*.md"]

[scanning.code]
directories = ["src"]
file_patterns = []

[rules.format]
require_hash = false
"""

SPEC = """\
# REQ-p00001: Directive Fixture

**Level**: prd | **Status**: Active | **Implements**: -

## Assertions

A. The tool SHALL do the live thing.

B. <RETIRED> Superseded by REQ-p00001-A, which says it better.

C. <RETIRED>

D. [UNKNOWN-DIRECTIVE] The tool SHALL still read this as an assertion.

## Changelog

- 2026-08-24 | - | - | Fixture (<fixture@example.com>) | seed

*End* *Directive Fixture* | **Hash**: be282dfd
"""

CODE = """\
# Implements: REQ-p00001-A
def live():
    pass


# Implements: REQ-p00001-B
def retired():
    pass
"""


def _make_repo(root: Path, spec: str = SPEC, code: str = CODE) -> Path:
    """Write a one-requirement repository carrying the directive fixture."""
    (root / "spec").mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "spec" / "fixture.md").write_text(spec, encoding="utf-8")
    (root / "src" / "fixture.py").write_text(code, encoding="utf-8")
    (root / ".elspais.toml").write_text(CONFIG, encoding="utf-8")
    return root


@pytest.fixture
def built(tmp_path: Path):
    """The fixture repository, built."""
    _make_repo(tmp_path)
    federated = build_graph(repo_root=tmp_path)
    graph = next(iter(federated.iter_repos())).graph
    return tmp_path, federated, graph


def _assertions(graph) -> dict[str, object]:
    req = graph.find_by_id("REQ-p00001")
    return {
        child.get_field("label"): child
        for child in req.iter_children()
        if child.kind == NodeKind.ASSERTION
    }


class TestDirectiveGrammar:
    """Validates REQ-p00002-E: what encloses a directive, and what follows it."""

    # Verifies: REQ-p00002-E
    @pytest.mark.parametrize(("opener", "closer"), [("<", ">"), ("[", "]"), ("{", "}")])
    def test_REQ_p00002_E_every_admitted_pair_opens_a_directive(
        self, opener: str, closer: str
    ) -> None:
        """All three pairs are equals; picking one for the author would rewrite
        text that is already correct."""
        directive = read_directive(f"{opener}RETIRED{closer} and then some prose")
        assert directive is not None
        assert directive.name == "RETIRED"
        assert directive.recognized and directive.retired
        assert directive.opener == opener and directive.closer == closer
        # The delimiters the author chose survive the rendering.
        assert directive.render() == f"{opener}RETIRED{closer} and then some prose"

    # Verifies: REQ-p00002-E
    def test_REQ_p00002_E_content_after_the_closer_is_the_assertions_content(self) -> None:
        """A directive may prefix real content -- which is why the closer
        matters -- and that content is carried verbatim, spacing included."""
        directive = read_directive("<RETIRED>   Superseded by REQ-x-B.")
        assert directive is not None
        assert directive.content == "   Superseded by REQ-x-B."
        assert directive.render() == "<RETIRED>   Superseded by REQ-x-B."

    # Verifies: REQ-p00002-E
    def test_REQ_p00002_E_an_unclosed_opener_is_ordinary_text(self) -> None:
        """A directive needs both halves. An *Assertion* discussing `<` in prose
        has declared nothing, and reading one there would invent a defect."""
        assert read_directive("<RETIRED without its closer, SHALL stay prose") is None
        assert canonical_assertion_text("<RETIRED and on it goes") == "<RETIRED and on it goes"

    # Verifies: REQ-p00002-E
    @pytest.mark.parametrize("text", ["`code` SHALL run", '"quoted" SHALL hold', "*emph* SHALL be"])
    def test_REQ_p00002_E_other_openers_introduce_nothing(self, text: str) -> None:
        """Only the three pairs open a directive. An *Assertion* that begins
        with a backtick, a quote or an emphasis marker is formatted prose."""
        assert read_directive(text) is None

    # Verifies: REQ-p00002-E
    @pytest.mark.parametrize("spelling", ["RETIRED", "Retired", "retired", "ReTiReD"])
    def test_REQ_p00002_E_case_is_presentation_not_identity(self, spelling: str) -> None:
        """Every admitted case names the same directive, and rendering emits the
        one canonical spelling -- the identifier rule, applied to a directive."""
        directive = read_directive(f"<{spelling}>")
        assert directive is not None and directive.retired
        assert canonical_assertion_text(f"<{spelling}> with a note") == "<RETIRED> with a note"

    # Verifies: REQ-p00002-F
    def test_REQ_p00002_F_an_unrecognized_directive_is_never_respelled(self) -> None:
        """The tool has no canonical spelling to offer for a name it does not
        know, so normalizing one would rewrite an author's text on a guess."""
        text = "[Removed - superseded by REQ-x-B.] "
        directive = read_directive(text)
        assert directive is not None
        assert not directive.recognized and not directive.retired
        assert canonical_assertion_text(text) == text


class TestRetirementLeavesTheDenominators:
    """Validates REQ-p00017-G: a retired *Assertion* does not exist for coverage."""

    # Verifies: REQ-p00017-G
    def test_REQ_p00017_G_retired_assertions_leave_the_denominator(self, built) -> None:
        """Four *Assertions* are written; two are retired; two are counted."""
        _, _, graph = built
        req = graph.find_by_id("REQ-p00001")
        assert sorted(_assertions(graph)) == ["A", "B", "C", "D"]
        assert counted_assertion_labels(req) == ["A", "D"]
        assert req.get_metric("rollup_metrics").total_assertions == 2

    # Verifies: REQ-p00017-G
    def test_REQ_p00017_G_a_retired_assertion_takes_no_blanket_credit(self, tmp_path: Path) -> None:
        """A citation naming the requirement as a whole is a coverage
        calculation like any other, so a retired *Assertion* is outside it."""
        code = "# Implements: REQ-p00001\ndef whole_requirement():\n    pass\n"
        _make_repo(tmp_path, code=code)
        federated = build_graph(repo_root=tmp_path)
        graph = next(iter(federated.iter_repos())).graph
        by_label = _assertions(graph)
        assert direct_coverage_for(by_label["A"]) == 1
        assert direct_coverage_for(by_label["D"]) == 1
        assert direct_coverage_for(by_label["B"]) == 0
        assert direct_coverage_for(by_label["C"]) == 0

    # Verifies: REQ-p00002-F
    def test_REQ_p00002_F_an_unrecognized_directive_still_counts(self, built) -> None:
        """Reporting an unrecognized directive is not withdrawing the
        *Assertion*: only RETIRED does that, so D stays in the denominator."""
        _, _, graph = built
        assert "D" in counted_assertion_labels(graph.find_by_id("REQ-p00001"))


class TestReferencesToRetiredAssertions:
    """Validates REQ-p00017-H: such a reference reads as one to nothing."""

    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_a_reference_to_a_retired_assertion_does_not_resolve(self, built) -> None:
        """The fixture's code cites A (live) and B (retired). One binds."""
        _, _, graph = built
        by_label = _assertions(graph)
        assert direct_coverage_for(by_label["A"]) == 1
        assert direct_coverage_for(by_label["B"]) == 0
        implements = [
            edge
            for edge in graph.find_by_id("REQ-p00001").iter_outgoing_edges()
            if edge.kind == EdgeKind.IMPLEMENTS
        ]
        assert [edge.assertion_targets for edge in implements] == [["A"]]

    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_the_reference_surfaces_under_the_existing_vocabulary(self, built) -> None:
        """It reaches the class a reference to a nonexistent *Assertion* of an
        existing requirement reaches -- not a class of its own."""
        _, _, graph = built
        faults = [f for f in graph._broken_references if f.target_id == "REQ-p00001-B"]
        assert len(faults) == 1
        assert faults[0].fault_class == FaultClass.UNKNOWN_ASSERTION
        assert faults[0].edge_kind == EdgeKind.IMPLEMENTS.value


class TestLabelsStayAllocated:
    """Validates REQ-p00017-I: retirement never releases the letter."""

    # Verifies: REQ-p00017-I
    def test_REQ_p00017_I_the_next_label_skips_every_retired_letter(self, built) -> None:
        """B and C are retired and D is live: the next *Assertion* is E, never
        a letter a withdrawn obligation once bore."""
        _, _, graph = built
        assert graph._next_assertion_label(graph.find_by_id("REQ-p00001")) == "E"

    # Verifies: REQ-p00017-I
    def test_REQ_p00017_I_an_added_assertion_lands_past_the_retired_letters(self, built) -> None:
        """The allocation holds through the mutation path, not only the query."""
        _, _, graph = built
        graph.add_assertion("REQ-p00001", "The tool SHALL do a further thing.")
        assert sorted(_assertions(graph)) == ["A", "B", "C", "D", "E"]


class TestRoundTrip:
    """Validates REQ-p00002-E: a directive and its commentary survive a rewrite."""

    # Verifies: REQ-p00002-E
    def test_REQ_p00002_E_a_retired_assertion_round_trips_byte_for_byte(self, built) -> None:
        """Rendering the file back from the graph reproduces it exactly --
        commentary after the closer and the unrecognized directive included."""
        root, _, graph = built
        file_node = next(
            node
            for node in graph.all_nodes()
            if node.kind == NodeKind.FILE
            and (node.get_field("relative_path") or "").endswith("fixture.md")
        )
        rendered = render_file(file_node, resolver=graph._resolver)
        assert rendered == (root / "spec" / "fixture.md").read_text(encoding="utf-8")

    # Verifies: REQ-p00002-E
    def test_REQ_p00002_E_a_rewrite_canonicalizes_only_the_directives_case(
        self, tmp_path: Path
    ) -> None:
        """The one thing a rewrite may change about a recognized directive is
        its spelling; the commentary beside it is the author's."""
        spec = SPEC.replace(
            "B. <RETIRED> Superseded by REQ-p00001-A, which says it better.",
            "B. <retired> Superseded by REQ-p00001-A, which says it better.",
        )
        _make_repo(tmp_path, spec=spec)
        federated = build_graph(repo_root=tmp_path)
        graph = next(iter(federated.iter_repos())).graph
        file_node = next(
            node
            for node in graph.all_nodes()
            if node.kind == NodeKind.FILE
            and (node.get_field("relative_path") or "").endswith("fixture.md")
        )
        rendered = render_file(file_node, resolver=graph._resolver)
        assert "B. <RETIRED> Superseded by REQ-p00001-A, which says it better." in rendered
        assert "<retired>" not in rendered
        assert "D. [UNKNOWN-DIRECTIVE] The tool SHALL still read this as an assertion." in rendered


class TestUnrecognizedDirectiveIsReported:
    """Validates REQ-p00002-F: it is reported, never absorbed."""

    # Verifies: REQ-p00002-F
    def test_REQ_p00002_F_the_check_names_the_directive_and_its_location(self, built) -> None:
        """A finding an author cannot place is a finding they cannot act on, so
        it carries the file and the line as well as the name as written."""
        root, federated, _ = built
        from elspais.config import get_config

        check = check_spec_unknown_directive(federated, get_config(None, root))
        assert not check.passed
        assert [f.node_id for f in check.findings] == ["REQ-p00001-D"]
        finding = check.findings[0]
        assert "[UNKNOWN-DIRECTIVE]" in finding.message
        assert (finding.file_path or "").endswith("fixture.md")
        assert finding.line == 13

    # Verifies: REQ-p00002-F
    def test_REQ_p00002_F_a_recognized_directive_is_not_reported(self, built) -> None:
        """RETIRED is read, so it is not a finding: only a name the tool cannot
        act on is."""
        root, federated, _ = built
        from elspais.config import get_config

        check = check_spec_unknown_directive(federated, get_config(None, root))
        assert not any(f.node_id in {"REQ-p00001-B", "REQ-p00001-C"} for f in check.findings)

    # Verifies: REQ-d00212-P
    def test_REQ_d00212_P_the_severity_comes_from_the_registry(self, built) -> None:
        """The check reads its severity from the one authority, so a project
        that turns it down is obeyed and nothing is hardcoded."""
        root, federated, _ = built
        from elspais.config import get_config

        assert REGISTRY["spec.unknown_directive"].category == "spec"
        config = get_config(None, root)
        check = check_spec_unknown_directive(federated, config)
        assert check.severity == REGISTRY["spec.unknown_directive"].default

        config["rules"]["severity"] = {"spec.unknown_directive": Severity.OFF.value}
        assert check_spec_unknown_directive(federated, config).name == "spec.unknown_directive"
        assert check_spec_unknown_directive(federated, config).findings == []


class TestEstateRegression:
    """Validates REQ-p00017-G against the shape the estate actually holds."""

    # Verifies: REQ-p00017-G
    def test_REQ_p00017_G_a_wholly_retired_requirement_reports_no_assertions(
        self, tmp_path: Path
    ) -> None:
        """Every letter withdrawn means an empty denominator, not a
        permanently-uncovered one -- the counting defect this directive fixes."""
        spec = textwrap.dedent(
            """\
            # REQ-p00001: Wholly Retired

            **Level**: prd | **Status**: Active | **Implements**: -

            ## Assertions

            A. <RETIRED>

            B. <RETIRED>

            *End* *Wholly Retired* | **Hash**: 00000000
            """
        )
        _make_repo(tmp_path, spec=spec, code="")
        federated = build_graph(repo_root=tmp_path)
        graph = next(iter(federated.iter_repos())).graph
        req = graph.find_by_id("REQ-p00001")
        assert counted_assertion_labels(req) == []
        assert req.get_metric("rollup_metrics").total_assertions == 0


class TestRetirementThroughMutation:
    """Validates REQ-p00002-E: a mutation reads a directive as a file does."""

    # Verifies: REQ-p00002-E
    def test_REQ_p00002_E_retiring_by_mutation_leaves_the_denominator(self, built) -> None:
        """Text arriving through a mutation is read for a directive too."""
        _, _, graph = built
        graph.update_assertion("REQ-p00001-A", "<retired> Withdrawn in review.")
        req = graph.find_by_id("REQ-p00001")
        assert counted_assertion_labels(req) == ["D"]
        assert graph.find_by_id("REQ-p00001-A").get_label() == "<RETIRED> Withdrawn in review."

    # Verifies: REQ-p00002-E
    def test_REQ_p00002_E_undoing_a_retirement_restores_the_assertion(self, built) -> None:
        """Restoring the text restores what the text says: an *Assertion*
        brought back must rejoin the denominator it left."""
        _, _, graph = built
        graph.update_assertion("REQ-p00001-A", "<RETIRED> Withdrawn in review.")
        graph.undo_last()
        req = graph.find_by_id("REQ-p00001")
        assert counted_assertion_labels(req) == ["A", "D"]
        assert graph.find_by_id("REQ-p00001-A").get_label() == "The tool SHALL do the live thing."
