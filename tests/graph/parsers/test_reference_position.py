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

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.graph.parsers.lark import FileDispatcher
from elspais.utilities.patterns import IdPatternConfig, IdResolver


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
