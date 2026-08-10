# Verifies: REQ-d00269-E
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

import pytest

from elspais.graph.parsers.lark import FileDispatcher
from elspais.utilities.patterns import IdPatternConfig, IdResolver


@pytest.fixture
def dispatcher() -> FileDispatcher:
    """Dispatcher over a standard REQ-p/o/d identifier grammar."""
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
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


class TestAnIdentifierIsFoundWhereverInTheTargetItSits:
    """REQ-d00269-D -- the target is searched before it is given up on.

    Position recognises the line, so the target may be written any way at
    all -- and a section banner writes the prose first. Recording the whole
    remainder without looking inside it loses an edge to a requirement that
    exists, which is the failure REQ-d00269-D exists to prevent.
    """

    # Verifies: REQ-d00269-D
    def test_REQ_d00269_D_prose_before_an_identifier_in_code_resolves_to_it(
        self, dispatcher: FileDispatcher
    ) -> None:
        source = "# Implements: Shared flags apply globally (REQ-p00001-B)\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == ["REQ-p00001-B"]

    # Verifies: REQ-d00269-D
    def test_REQ_d00269_D_prose_before_an_identifier_in_a_test_resolves_to_it(
        self, dispatcher: FileDispatcher
    ) -> None:
        """The two dispatch paths take different branches, so both are held."""
        source = (
            "# Verifies: Exit code is worst-of-all sections (REQ-p00001-C)\n"
            "def test_exit_code():\n"
            "    assert True\n"
        )

        assert _verifies(dispatcher, source) == ["REQ-p00001-C"]

    # Verifies: REQ-d00269-D
    def test_REQ_d00269_D_multi_assertion_survives_the_leading_prose(
        self, dispatcher: FileDispatcher
    ) -> None:
        source = "# Implements: some prose REQ-p00001-A+B\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == ["REQ-p00001-A+B"]

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

        Searching the target is what finds an identifier written late, not a
        licence to discard a target that holds none: a reference the tool
        cannot read still has to read as a reference.
        """
        source = f"# Implements: {target}\ndef impl():\n    pass\n"

        assert _implements(dispatcher, source) == [target]
