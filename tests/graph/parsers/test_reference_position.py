# Verifies: REQ-d00269-E, REQ-d00269-G
"""Position, not shape, decides whether a *Traceability* keyword refers.

A keyword introduces a reference only where it is the first content of a
comment.  Nothing about the target's spelling is consulted, so a foreign
identifier written where a reference belongs is read (and later reported
as unresolvable), while the same keyword written mid-line, inside inline
backticks, or inside a fenced block names a keyword instead of invoking
one.

The probe strings below are single-line Python literals on purpose: a
line-initial keyword in this file's own source would itself be scanned as
a reference by the rule under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import make_file_id
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.reference_faults import FaultCode
from elspais.graph.relations import EdgeKind
from elspais.graph.render import render_file
from elspais.utilities.patterns import IdPatternConfig, IdResolver
from tests.core.graph_test_helpers import grammar_for


def _validated(config: dict) -> dict:
    """Return ``config`` after checking a configuration file could hold it.

    ``IdPatternConfig.from_dict`` takes a raw dictionary and never consults the
    config schema, so a fixture built here could describe a repository no
    ``.elspais.toml`` can produce -- and pin grammar behaviour no user can
    reach. Every fixture is therefore validated the way a file on disk is,
    before any resolver is built from it.
    """
    ElspaisConfig.model_validate(config)
    return config


@pytest.fixture
def dispatcher() -> FileDispatcher:
    """Dispatcher over a standard REQ-p/o/d identifier grammar."""
    config = IdPatternConfig.from_dict(
        _validated(
            {
                "project": {"namespace": "REQ"},
                "levels": {
                    "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
                    "ops": {"rank": 2, "letter": "o", "implements": ["ops", "prd"]},
                    "dev": {"rank": 3, "letter": "d", "implements": ["dev", "ops", "prd"]},
                },
                "id-patterns": {
                    "canonical": "{namespace}-{level.letter}{component}",
                    "aliases": {"short": "{level.letter}{component}"},
                    "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                    "assertions": {"label_style": "uppercase", "max_count": 26},
                },
            }
        )
    )
    return FileDispatcher(IdResolver(config))


def _implements(dispatcher: FileDispatcher, source: str) -> list[str]:
    """Every target read out of a code file's ``Implements:`` references."""
    targets: list[str] = []
    for parsed in dispatcher.dispatch_code(source, "demo.py"):
        if parsed.content_type == "code_ref":
            targets.extend(parsed.parsed_data.get("implements", []))
    return targets


def _remainder_text(results) -> str:
    """The concatenated raw text of every REMAINDER the dispatch produced."""
    return "\n".join(p.raw_text for p in results if p.content_type == "remainder")


_FENCED_CODE = '"""\n```\n# Implements: widget-42\n```\n"""\ndef fenced():\n    pass\n'


class TestAKeywordOpeningACommentRefers:
    """The canonical position -- and the target's shape is not consulted."""

    @pytest.mark.parametrize(
        "target",
        [
            "widget-42",  # lowercase namespace: no shape rule would admit it
            "REQ-p00001",  # an identifier this repository's own grammar claims
        ],
    )
    def test_REQ_d00269_E_first_content_of_a_comment_is_a_reference(
        self, dispatcher: FileDispatcher, target: str
    ) -> None:
        source = f"# Implements: {target}\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == [target]


class TestAKeywordElsewhereDoesNotRefer:
    """Every other position names the keyword rather than invoking it."""

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param("x = 1  # Implements: nope\n", id="trailing-comment"),
            pytest.param("# The Implements: keyword links code\n", id="mid-line-prose"),
            pytest.param("# `Implements: quoted`\n", id="inline-backticks"),
            pytest.param(_FENCED_CODE, id="fenced-block"),
        ],
    )
    def test_REQ_d00269_E_keyword_out_of_position_is_not_a_reference(
        self, dispatcher: FileDispatcher, source: str
    ) -> None:
        assert _implements(dispatcher, source) == []


class TestAStringLiteralIsNotAComment:
    """REQ-d00269-E's "inline-quoted" text covers Python string literals too.

    The fence exemption only catches markdown fences; a line-initial
    keyword inside a Python triple-quoted string is otherwise
    indistinguishable from a real comment to a line-based scanner.
    """

    def test_REQ_d00269_E_a_same_type_keyword_in_a_docstring_creates_no_edge(
        self, dispatcher: FileDispatcher
    ) -> None:
        """The silent case: a real annotation-shaped line inside a string literal."""
        source = "\n".join(
            [
                "def helper():",
                '    """Example of how to annotate:',
                "",
                "# Implements: REQ-p00001",
                '    """',
                "    return 1",
            ]
        )

        assert _implements(dispatcher, source) == []

    def test_REQ_d00269_E_a_real_comment_still_binds(self, dispatcher: FileDispatcher) -> None:
        """The guard against over-correction: ordinary annotations keep working."""
        source = "\n".join(
            [
                "# Implements: REQ-p00001",
                "def helper():",
                "    return 1",
            ]
        )

        assert _implements(dispatcher, source) == ["REQ-p00001"]

    def test_REQ_d00269_E_a_same_type_keyword_in_a_module_docstring_sets_no_file_default(
        self, dispatcher: FileDispatcher
    ) -> None:
        """The file-level default-verifies pass reads the parse tree before

        the transformer runs, and must exclude quoted lines itself rather
        than relying on the transformer's own exclusion downstream.
        """
        source = "\n".join(
            [
                '"""Example of how to annotate a test module:',
                "",
                "# Verifies: REQ-p00001",
                '"""',
                "def test_thing():",
                "    assert True",
            ]
        )

        assert _verifies(dispatcher, source) == []

    # Verifies: REQ-d00269-E
    def test_a_default_argument_string_literal_does_not_silence_a_test_name_reference(
        self, dispatcher: FileDispatcher
    ) -> None:
        """``test_name_ref`` reads the function name, not a comment.

        A line that merely opens a literal -- the opening quote reached
        after real code, as in a default argument -- is not interior to
        it. A `def test_REQ_...` line carrying a default string argument
        must not be excluded on that account, or a same-type, in-position
        reference (the underscored test name itself) is silently dropped.
        """
        source = 'def test_REQ_p00001_widget(label="x"):\n    assert widget(label)\n'

        assert _verifies(dispatcher, source) == ["REQ-p00001"]

    # Verifies: REQ-d00269-E
    def test_a_test_name_line_interior_to_a_docstring_binds_nothing(
        self, dispatcher: FileDispatcher
    ) -> None:
        """The mirror of the case above: genuinely interior still excludes.

        A `def test_REQ_...` line written as an example inside a docstring
        is interior to that literal, not merely sharing a line with one --
        it must not bind, the same as any other keyword-shaped line
        written as documentation rather than code.
        """
        source = "\n".join(
            [
                "def helper():",
                '    """Example naming convention:',
                "    def test_REQ_p00001_widget():",
                "        pass",
                '    """',
                "    return 1",
            ]
        )

        assert _verifies(dispatcher, source) == []

    # Verifies: REQ-d00269-E
    def test_a_string_literal_on_an_earlier_line_does_not_silence_a_later_comment(
        self, dispatcher: FileDispatcher
    ) -> None:
        """The comment-shaped exclusion is scoped to the line it actually quotes.

        A code line carrying a string literal is marked quoted; the
        following line is an ordinary ``# Implements:`` comment and must
        still bind, pinning the boundary from the other direction.
        """
        source = "\n".join(
            [
                'x = "value"',
                "# Implements: REQ-p00001",
                "def foo():",
                "    pass",
            ]
        )

        assert _implements(dispatcher, source) == ["REQ-p00001"]


class TestTheFenceExemptionHoldsOnBothDispatchPaths:
    """Test files quote syntax as readily as code files do."""

    def test_REQ_d00269_E_fenced_verifies_in_a_test_file_is_not_a_reference(
        self, dispatcher: FileDispatcher
    ) -> None:
        source = "```\n# Verifies: widget-42\n```\ndef test_thing():\n    assert True\n"

        results = dispatcher.dispatch_test(source, "tests/test_demo.py")

        verified = [
            target
            for parsed in results
            if parsed.content_type == "test_ref"
            for target in parsed.parsed_data.get("verifies", [])
        ]
        assert verified == []

    def test_REQ_d00269_E_a_demoted_line_survives_verbatim_in_the_remainder(
        self, dispatcher: FileDispatcher
    ) -> None:
        """Demotion must leave the text alone -- it is written back to disk."""
        results = dispatcher.dispatch_code(_FENCED_CODE, "demo.py")

        assert "# Implements: widget-42" in _remainder_text(results)


def _verifies(dispatcher: FileDispatcher, source: str) -> list[str]:
    """Every target read out of a test file's ``Verifies:`` references."""
    targets: list[str] = []
    for parsed in dispatcher.dispatch_test(source, "tests/test_demo.py"):
        if parsed.content_type == "test_ref":
            targets.extend(parsed.parsed_data.get("verifies", []))
    return targets


def _spec_implements(dispatcher: FileDispatcher, target: str) -> list[str]:
    """Every target a requirement's ``Implements:`` metadata line names."""
    source = f"# REQ-d00001: Demo\n\n**Level**: dev\n**Implements**: {target}\n\nBody.\n"
    return [
        ref
        for parsed in dispatcher.dispatch_spec(source, "spec/demo.md")
        if parsed.content_type == "requirement"
        for ref in parsed.parsed_data.get("implements", [])
    ]


class TestTheTargetIsASeparatedListOfReferences:
    """Validates REQ-d00269-G: the supported spelling of a target.

    Each item may name an *Assertion* and may name several at once, and a
    list may mix the plain form with the labelled one. Both the code
    annotation and the *Requirement* metadata line read the same list, so
    an author who learns one spelling has learned the other.
    """

    _LISTS = [
        pytest.param("REQ-p00001", ["REQ-p00001"], id="bare"),
        pytest.param("REQ-p00001-A", ["REQ-p00001-A"], id="labelled"),
        pytest.param("REQ-p00001-A+B", ["REQ-p00001-A+B"], id="multi-assertion"),
        pytest.param(
            "REQ-p00001, REQ-p00002",
            ["REQ-p00001", "REQ-p00002"],
            id="list",
        ),
        pytest.param(
            "REQ-p00001-A+B, REQ-p00002",
            ["REQ-p00001-A+B", "REQ-p00002"],
            id="mixed-list",
        ),
    ]

    # Verifies: REQ-d00269-G
    @pytest.mark.parametrize(("target", "expected"), _LISTS)
    def test_REQ_d00269_G_a_code_annotation_reads_the_whole_list(
        self, dispatcher: FileDispatcher, target: str, expected: list[str]
    ) -> None:
        source = f"# Implements: {target}\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == expected

    # Verifies: REQ-d00269-G
    @pytest.mark.parametrize(("target", "expected"), _LISTS)
    def test_REQ_d00269_G_a_test_annotation_reads_the_whole_list(
        self, dispatcher: FileDispatcher, target: str, expected: list[str]
    ) -> None:
        """The two dispatch paths take different branches, so both are held."""
        source = f"# Verifies: {target}\ndef test_thing():\n    assert True\n"

        assert _verifies(dispatcher, source) == expected

    # Verifies: REQ-d00269-G
    @pytest.mark.parametrize(("target", "expected"), _LISTS)
    def test_REQ_d00269_G_a_metadata_line_reads_the_whole_list(
        self, dispatcher: FileDispatcher, target: str, expected: list[str]
    ) -> None:
        assert _spec_implements(dispatcher, target) == expected


class TestATargetHoldingMoreThanReferencesIsUnresolved:
    """Validates REQ-d00269-G: no identifier is picked out of prose.

    An identifier the author never named is worse than no edge at all: it
    is evidence attached to the wrong *Requirement*, and nothing reports
    it. So a target that is not a list of references resolves to nothing,
    and the line goes out on the unresolved-reference channel carrying
    what its author actually wrote.
    """

    # Verifies: REQ-d00269-G
    def test_REQ_d00269_G_a_foreign_identifier_sharing_the_namespace_is_not_read(
        self, dispatcher: FileDispatcher
    ) -> None:
        """``XREQ-d00001`` holds ``REQ-d00001``; it names a different estate."""
        source = "# Implements: XREQ-d00001\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == ["XREQ-d00001"]

    # Verifies: REQ-d00269-G
    def test_REQ_d00269_G_prose_around_an_identifier_is_not_read_in_code(
        self, dispatcher: FileDispatcher
    ) -> None:
        source = "# Implements: Shared flags apply globally (REQ-p00001-B)\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == ["Shared flags apply globally (REQ-p00001-B)"]

    # Verifies: REQ-d00269-G
    def test_REQ_d00269_G_prose_around_an_identifier_is_not_read_in_a_test(
        self, dispatcher: FileDispatcher
    ) -> None:
        """The two dispatch paths take different branches, so both are held."""
        source = "# Verifies: some prose (REQ-p00001-A)\ndef test_exit_code():\n    assert True\n"

        assert _verifies(dispatcher, source) == ["some prose (REQ-p00001-A)"]

    # Verifies: REQ-d00269-G
    def test_REQ_d00269_G_one_unreadable_item_leaves_the_whole_line_unresolved(
        self, dispatcher: FileDispatcher
    ) -> None:
        """The line is the unit: a target part-read is a target misread."""
        source = "# Implements: REQ-p00001 and see XREQ-d00002\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == ["REQ-p00001 and see XREQ-d00002"]

    # Verifies: REQ-d00269-G
    def test_REQ_d00269_G_trailing_prose_after_a_readable_reference_is_not_read(
        self, dispatcher: FileDispatcher
    ) -> None:
        source = "# Implements: REQ-p00001 -- the flag path\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == ["REQ-p00001 -- the flag path"]

    # Verifies: REQ-d00269-D
    @pytest.mark.parametrize(
        "target",
        [
            "widget-42 has no identifier",
            "the caching strategy described above",
        ],
    )
    def test_REQ_d00269_D_a_target_holding_no_identifier_keeps_its_raw_text(
        self, dispatcher: FileDispatcher, target: str
    ) -> None:
        """The fallback is the population REQ-d00269-F reports; it must survive.

        Refusing to read an identifier out of prose is not a licence to drop
        the line: a reference the tool cannot read still has to read as a
        reference, or a *Requirement* whose evidence was discarded looks
        exactly like one that never had any.
        """
        source = f"# Implements: {target}\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == [target]


def _spec_requirement(dispatcher: FileDispatcher, source: str) -> dict:
    """The ``parsed_data`` of the one *Requirement* a spec source holds."""
    requirements = [
        parsed
        for parsed in dispatcher.dispatch_spec(source, "spec/demo.md")
        if parsed.content_type == "requirement"
    ]
    assert len(requirements) == 1, f"fixture must hold exactly one requirement; got {requirements}"
    return requirements[0].parsed_data


def _spec_source(metadata: str, *, body: str = "Body text here.") -> str:
    """A one-requirement spec file whose metadata block is ``metadata``."""
    return f"# REQ-d00002: Demo\n\n{metadata}\n\n{body}\n"


def _trailing_separator_verdicts(parsed: dict) -> list:
    """Every verdict the parse recorded naming the trailing-separator fault."""
    return [
        key
        for key, (_fault_class, codes) in parsed.get("reference_verdicts", {}).items()
        if FaultCode.TRAILING_SEPARATOR in codes
    ]


class TestAMetadataListContinuesOntoTheNextLine:
    """Validates REQ-d00269-H over a *Requirement*'s metadata block.

    H names two places a list may continue: "the next line of the same
    comment block, or the next line of the same metadata block". Only the
    first was built, so a metadata list ending with the separator dropped
    everything below it -- and reported the separator as one that introduced
    nothing while a continuation line sat directly beneath it, sending its
    author to delete the comma and leave the dropped references dead.

    Continuation is a line-joining concern, so the strongest statement of it
    is equivalence: a folded list binds exactly what the same list written on
    one line binds.
    """

    _KEYWORDS = [
        pytest.param("Implements", "implements", id="implements"),
        pytest.param("Refines", "refines", id="refines"),
    ]

    # Verifies: REQ-d00269-H
    @pytest.mark.parametrize(("keyword", "field"), _KEYWORDS)
    def test_REQ_d00269_H_a_folded_list_binds_what_the_one_line_form_binds(
        self, dispatcher: FileDispatcher, keyword: str, field: str
    ) -> None:
        folded = _spec_requirement(
            dispatcher,
            _spec_source(f"**Level**: dev\n**{keyword}**: REQ-d00001-A,\nREQ-d00001-B"),
        )
        one_line = _spec_requirement(
            dispatcher,
            _spec_source(f"**Level**: dev\n**{keyword}**: REQ-d00001-A, REQ-d00001-B"),
        )

        assert folded[field] == ["REQ-d00001-A", "REQ-d00001-B"]
        assert folded[field] == one_line[field]

    # Verifies: REQ-d00269-H
    def test_REQ_d00269_H_a_folded_list_reports_no_trailing_separator(
        self, dispatcher: FileDispatcher
    ) -> None:
        """H's third sentence conditions the report on having no line to
        continue onto. Reporting it anyway is the misleading half of the
        defect: the author is told to delete the separator, which is the one
        edit that turns a recoverable list into a silently truncated one.
        """
        parsed = _spec_requirement(
            dispatcher,
            _spec_source("**Level**: dev\n**Implements**: REQ-d00001-A,\nREQ-d00001-B"),
        )

        assert _trailing_separator_verdicts(parsed) == []

    # Verifies: REQ-d00269-H
    def test_REQ_d00269_H_a_chain_of_three_lines_binds_every_reference(
        self, dispatcher: FileDispatcher
    ) -> None:
        parsed = _spec_requirement(
            dispatcher,
            _spec_source(
                "**Level**: dev\n**Implements**: REQ-d00001-A,\nREQ-d00001-B,\nREQ-d00001-C"
            ),
        )

        assert parsed["implements"] == ["REQ-d00001-A", "REQ-d00001-B", "REQ-d00001-C"]

    # Verifies: REQ-d00269-H
    def test_REQ_d00269_H_a_list_ending_the_metadata_block_still_folds(
        self, dispatcher: FileDispatcher
    ) -> None:
        """The ordinary spelling in this estate puts the whole metadata block
        on one pipe-separated line, so the continued list is the last field
        of that line rather than a line of its own.
        """
        parsed = _spec_requirement(
            dispatcher,
            _spec_source(
                "**Level**: dev | **Status**: Active | **Implements**: REQ-d00001-A,\nREQ-d00001-B"
            ),
        )

        assert parsed["implements"] == ["REQ-d00001-A", "REQ-d00001-B"]
        assert parsed["status"] == "Active"

    # Verifies: REQ-d00269-H
    def test_REQ_d00269_H_a_folded_line_is_not_also_preamble_text(
        self, dispatcher: FileDispatcher
    ) -> None:
        """A line read as the list's content is not also prose: emitting it
        both ways would render the references a second time as body text.
        """
        parsed = _spec_requirement(
            dispatcher,
            _spec_source("**Level**: dev\n**Implements**: REQ-d00001-A,\nREQ-d00001-B"),
        )

        preamble = [s["content"] for s in parsed["sections"] if s["heading"] == "preamble"]
        assert preamble == ["Body text here."]


class TestALineThatMayNotContinueAMetadataList:
    """Validates REQ-d00269-H's two exclusions over a metadata block.

    Neither a line holding no content nor a line whose own first content is a
    *Traceability* keyword may continue a list. In both cases the list ends
    where it was written, binds what it holds, and -- H's third sentence --
    the separator that introduced nothing is reported.
    """

    # Verifies: REQ-d00269-H
    def test_REQ_d00269_H_a_blank_line_does_not_continue_a_list(
        self, dispatcher: FileDispatcher
    ) -> None:
        parsed = _spec_requirement(
            dispatcher,
            _spec_source(
                "**Level**: dev\n**Implements**: REQ-d00001-A,",
                body="REQ-d00001-B\n\nBody text here.",
            ),
        )

        assert parsed["implements"] == ["REQ-d00001-A"]
        assert _trailing_separator_verdicts(parsed), "the separator must still be reported"

    # Verifies: REQ-d00269-H
    def test_REQ_d00269_H_a_line_opening_with_a_keyword_does_not_continue_a_list(
        self, dispatcher: FileDispatcher
    ) -> None:
        """The second declaration is a declaration, not an item holding a
        space: it binds its own references, and the list above it ends.
        """
        parsed = _spec_requirement(
            dispatcher,
            _spec_source(
                "**Level**: dev\n**Implements**: REQ-d00001-A,\n**Refines**: REQ-d00001-B"
            ),
        )

        assert parsed["implements"] == ["REQ-d00001-A"]
        assert parsed["refines"] == ["REQ-d00001-B"]
        assert _trailing_separator_verdicts(parsed), "the separator must still be reported"

    # Verifies: REQ-d00269-H, REQ-d00269-E
    @pytest.mark.parametrize(
        "continuation",
        [
            pytest.param("**Verifies**: REQ-d00001-B", id="emphasised"),
            pytest.param("Verifies: REQ-d00001-B", id="plain"),
            pytest.param("verifies: REQ-d00001-B", id="lowercase"),
        ],
    )
    def test_REQ_d00269_H_a_keyword_a_metadata_block_does_not_hold_still_excludes(
        self, dispatcher: FileDispatcher, continuation: str
    ) -> None:
        """``Verifies`` is not a *Requirement* metadata field, so this line is
        read as prose rather than as another field -- the path where H's
        keyword exclusion is actually decided rather than settled by the
        grammar's shape. What a keyword is does not depend on its case
        (REQ-d00269-E), so the lowercase spelling excludes the line too.
        """
        parsed = _spec_requirement(
            dispatcher,
            _spec_source(f"**Level**: dev\n**Implements**: REQ-d00001-A,\n{continuation}"),
        )

        assert parsed["implements"] == ["REQ-d00001-A"]
        assert _trailing_separator_verdicts(parsed), "the separator must still be reported"
        preamble = [s["content"] for s in parsed["sections"] if s["heading"] == "preamble"]
        assert preamble == [f"{continuation}\n\nBody text here."]


_ROUNDTRIP_CONFIG = """\
[project]
name = "metadata-continuation"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""

# The consumer's ``Implements`` list is folded across two physical lines.
# Its targets are authored in the same file, so the rendered list is derived
# from live edges rather than from a resurrected broken-reference field.
_ROUNDTRIP_SPEC = """\
# Continuation Round-Trip Fixture

## REQ-p00001: First Anchor

**Level**: PRD | **Status**: Active | **Implements**: -

The first anchor SHALL anchor the hierarchy.

### Assertions

A. The first anchor SHALL expose capability alpha.

*End* *First Anchor* | **Hash**: 00000000

---

## REQ-p00002: Second Anchor

**Level**: PRD | **Status**: Active | **Implements**: -

The second anchor SHALL anchor the hierarchy.

### Assertions

A. The second anchor SHALL expose capability beta.

*End* *Second Anchor* | **Hash**: 00000000

---

## REQ-o00001: Folded Implementer

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00001,
REQ-p00002

The implementer SHALL cite both anchors across two lines.

### Assertions

A. The implementer SHALL do its work.

*End* *Folded Implementer* | **Hash**: 00000000

---
"""


# The same fixture citing ASSERTIONS rather than whole requirements. Rendering
# a labelled citation has to compose an identifier, which needs the configured
# assertion separator -- so this is the shape that exercises the round-trip's
# harder half rather than assuming it behaves like the unlabelled one.
_ROUNDTRIP_SPEC_LABELLED = _ROUNDTRIP_SPEC.replace(
    "**Implements**: REQ-p00001,\nREQ-p00002",
    "**Implements**: REQ-p00001-A,\nREQ-p00002-A",
)

# A citation naming an *Assertion* does NOT produce an edge to the assertion
# node: it produces an edge to the owning requirement carrying the labels in
# ``assertion_targets``. The pair is asserted rather than a composed
# identifier, because spelling one needs the configured separators and a test
# has no business composing an identifier by hand.
_ROUNDTRIP_TARGETS = {
    "whole-requirement": (
        {("REQ-p00001", ()), ("REQ-p00002", ())},
        _ROUNDTRIP_SPEC,
    ),
    "assertion-labelled": (
        {("REQ-p00001", ("A",)), ("REQ-p00002", ("A",))},
        _ROUNDTRIP_SPEC_LABELLED,
    ),
}


def _implements_citations(graph, node_id: str) -> set[tuple[str, tuple[str, ...]]]:
    """Each IMPLEMENTS citation the named *Requirement* declared, as the
    requirement it named paired with the assertion labels it named on it."""
    node = graph.find_by_id(node_id)
    assert node is not None, f"fixture node {node_id} is missing"
    return {
        (edge.source.id, tuple(edge.assertion_targets))
        for edge in node.iter_incoming_edges()
        if edge.kind is EdgeKind.IMPLEMENTS
    }


def _build_continuation_graph(root: Path, spec_text: str = _ROUNDTRIP_SPEC):
    (root / ".elspais.toml").write_text(_ROUNDTRIP_CONFIG, encoding="utf-8")
    spec_dir = root / "spec"
    spec_dir.mkdir(exist_ok=True)
    (spec_dir / "reqs.md").write_text(spec_text, encoding="utf-8")
    return build_graph(
        config_path=root / ".elspais.toml",
        repo_root=root,
        scan_code=False,
        scan_tests=False,
    )


def _implements_targets(graph, node_id: str) -> set[str]:
    """Every *Assertion* the named *Requirement*'s IMPLEMENTS edges reach.

    Storage inverts the declaration direction, so the cited node is the
    edge's source: the citing requirement's INCOMING IMPLEMENTS edges are
    the ones its own ``Implements`` list declared.
    """
    node = graph.find_by_id(node_id)
    assert node is not None, f"fixture node {node_id} is missing"
    return {
        edge.source.id for edge in node.iter_incoming_edges() if edge.kind is EdgeKind.IMPLEMENTS
    }


class TestAFoldedMetadataListSurvivesARoundTrip:
    """Validates REQ-d00269-H: a folded list is readable, renderable and
    re-readable.

    Reading the continuation is only half the obligation -- a list the tool
    reads but cannot write back would lose the references on the next save.
    The rendered form collapses onto one line, which is the intended
    canonicalization and not a defect, so what is held here is the set of
    references, not the line breaks.
    """

    @pytest.mark.parametrize(
        ("expected", "spec_text"),
        list(_ROUNDTRIP_TARGETS.values()),
        ids=list(_ROUNDTRIP_TARGETS),
    )
    # Verifies: REQ-d00269-H
    def test_REQ_d00269_H_a_folded_list_binds_both_targets_in_the_graph(
        self, tmp_path: Path, expected: set[str], spec_text: str
    ) -> None:
        graph = _build_continuation_graph(tmp_path, spec_text)

        assert _implements_citations(graph, "REQ-o00001") == expected

    @pytest.mark.parametrize(
        ("expected", "spec_text"),
        list(_ROUNDTRIP_TARGETS.values()),
        ids=list(_ROUNDTRIP_TARGETS),
    )
    # Verifies: REQ-d00269-H
    def test_REQ_d00269_H_a_folded_list_re_parses_to_the_same_references(
        self, tmp_path: Path, expected: set[str], spec_text: str
    ) -> None:
        graph = _build_continuation_graph(tmp_path, spec_text)
        file_node = graph.find_by_id(make_file_id("REQ", "spec/reqs.md"))
        assert file_node is not None, "the fixture's FILE node is missing"

        # A labelled citation cannot be spelled without the configured
        # assertion separator, so the resolver is required rather than
        # optional here (``GrammarUnavailable`` otherwise).
        rendered = render_file(file_node, resolver=grammar_for("REQ"))
        rebuilt_root = tmp_path / "rebuilt"
        (rebuilt_root / "spec").mkdir(parents=True)
        (rebuilt_root / ".elspais.toml").write_text(_ROUNDTRIP_CONFIG, encoding="utf-8")
        (rebuilt_root / "spec" / "reqs.md").write_text(rendered, encoding="utf-8")
        rebuilt = build_graph(
            config_path=rebuilt_root / ".elspais.toml",
            repo_root=rebuilt_root,
            scan_code=False,
            scan_tests=False,
        )

        assert _implements_citations(rebuilt, "REQ-o00001") == expected
