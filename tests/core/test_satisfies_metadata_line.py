# Validates REQ-p00014-A
"""Tests for `Satisfies` field acceptance on the piped metadata line.

Validates that:
1. `Satisfies` is accepted as a piped `_field` alongside Level/Status/Implements/Refines.
2. The `SATISFIES_FIELD` regex stops at PIPE (`[^|\\n]+`), matching its siblings,
   so it does not greedily consume subsequent fields on the same line.
3. The standalone `Satisfies: REQ-X` form (own line, no PIPE) continues to parse
   through the unified metadata-line path (single-field metadata_line); the
   parallel `satisfies_line` rule has been deleted.

The lark-pipeline helper mirrors `tests/core/test_satisfies.py::_parse_text`
to exercise the real parser + transformer (no mocks).
"""

from elspais.graph.parsers.lark import GrammarFactory
from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer
from elspais.utilities.patterns import IdPatternConfig, IdResolver


def _make_lark_pipeline():
    """Create Lark parser + transformer with default pattern config.

    Mirrors the helper in tests/core/test_satisfies.py.
    """
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
            },
        }
    )
    resolver = IdResolver(config)
    factory = GrammarFactory(resolver)
    lark_parser = factory.get_requirement_parser()
    transformer = RequirementTransformer(resolver)
    return lark_parser, transformer


def _parse_text(text: str):
    """Parse requirement text with Lark pipeline, return ParsedContent list."""
    lark_parser, transformer = _make_lark_pipeline()
    if not text.endswith("\n"):
        text += "\n"
    tree = lark_parser.parse(text)
    results = transformer.transform(tree)
    return [r for r in results if r.content_type == "requirement"]


class TestSatisfiesPipedMetadataLine:
    """Validates REQ-p00014-A: Satisfies on the piped metadata line.

    The Satisfies metadata field MUST be accepted on the piped metadata
    line alongside Level, Status, Implements, and Refines.
    """

    # Implements: REQ-p00014-A
    def test_REQ_p00014_A_piped_satisfies_single_target(self) -> None:
        """A piped metadata line containing Satisfies parses cleanly.

        Pre-fix: lark raises UnexpectedToken because SATISFIES_FIELD is
        not in the `_field` alternatives.
        """
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: Dev | **Status**: Active | **Refines**: REQ-p01051 | "
            "**Satisfies**: REQ-p00004\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        results = _parse_text(text)
        assert len(results) == 1
        data = results[0].parsed_data
        assert data["satisfies"] == ["REQ-p00004"]
        assert data["refines"] == ["REQ-p01051"]
        assert data["level"] == "dev"
        assert data["status"] == "Active"

    # Implements: REQ-p00014-A
    def test_REQ_p00014_A_piped_satisfies_multi_target(self) -> None:
        """Comma-separated multiple Satisfies targets all extracted."""
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: Dev | **Status**: Active | **Satisfies**: REQ-p00004, REQ-p00005\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        results = _parse_text(text)
        assert len(results) == 1
        assert results[0].parsed_data["satisfies"] == ["REQ-p00004", "REQ-p00005"]

    # Implements: REQ-p00014-A
    def test_REQ_p00014_A_piped_satisfies_first_position(self) -> None:
        """Satisfies as the FIRST field on the piped line.

        Verifies PIPE-stop: with the post-fix `[^|\\n]+` regex, Satisfies
        does not greedily consume Level/Status that follow it.
        """
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Satisfies**: REQ-p00004 | **Level**: Dev | **Status**: Active\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        results = _parse_text(text)
        assert len(results) == 1
        data = results[0].parsed_data
        assert data["satisfies"] == ["REQ-p00004"]
        assert data["level"] == "dev"
        assert data["status"] == "Active"

    # Implements: REQ-p00014-A
    def test_REQ_p00014_A_piped_satisfies_middle_position(self) -> None:
        """Satisfies in the MIDDLE of the piped line."""
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: Dev | **Satisfies**: REQ-p00004 | **Status**: Active\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        results = _parse_text(text)
        assert len(results) == 1
        data = results[0].parsed_data
        assert data["satisfies"] == ["REQ-p00004"]
        assert data["level"] == "dev"
        assert data["status"] == "Active"

    # Implements: REQ-p00014-A
    def test_REQ_p00014_A_piped_satisfies_last_position(self) -> None:
        """Satisfies as the LAST field on the piped line."""
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: Dev | **Status**: Active | **Satisfies**: REQ-p00004\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        results = _parse_text(text)
        assert len(results) == 1
        data = results[0].parsed_data
        assert data["satisfies"] == ["REQ-p00004"]
        assert data["level"] == "dev"
        assert data["status"] == "Active"

    # Implements: REQ-p00014-A
    def test_REQ_p00014_A_piped_satisfies_with_implements(self) -> None:
        """Implements and Satisfies coexist on the same piped line."""
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001 | "
            "**Satisfies**: REQ-p00004\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        results = _parse_text(text)
        assert len(results) == 1
        data = results[0].parsed_data
        assert data["implements"] == ["REQ-p00001"]
        assert data["satisfies"] == ["REQ-p00004"]

    # Implements: REQ-p00014-A
    def test_REQ_p00014_A_no_pipe_greedy_consumption(self) -> None:
        """Regression for the regex tightening: Satisfies must NOT eat past PIPE.

        Pre-fix, SATISFIES_FIELD uses `[^\\n]+` (greedy) and would swallow
        the entire rest of the line into the Satisfies token, polluting the
        extracted value with `REQ-A | **Status**: Active`. Post-fix, the
        regex uses `[^|\\n]+` matching the IMPLEMENTS_FIELD/REFINES_FIELD
        siblings, and the value is just the requirement id.
        """
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: Dev | **Satisfies**: REQ-p00004 | **Status**: Active\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        results = _parse_text(text)
        assert len(results) == 1
        data = results[0].parsed_data
        # The exact, untainted value:
        assert data["satisfies"] == ["REQ-p00004"]
        # And — critically — the satisfies value did NOT swallow Status:
        for v in data["satisfies"]:
            assert "|" not in v
            assert "status" not in v.lower()

    # Implements: REQ-p00014-A
    def test_REQ_p00014_A_standalone_satisfies_still_parses(self) -> None:
        """The standalone form `Satisfies: REQ-X` (own line, no PIPE) remains
        valid because `metadata_line: _field (PIPE _field)*` accepts a single
        SATISFIES_FIELD without pipes. The dedicated `satisfies_line` rule was
        deleted, but the surface behavior is preserved via the unified
        metadata-line path. This pins forward-compat for existing specs."""
        text = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: Dev | **Status**: Active\n"
            "\n"
            "Satisfies: REQ-p00004\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        results = _parse_text(text)
        assert len(results) == 1
        assert results[0].parsed_data["satisfies"] == ["REQ-p00004"]
