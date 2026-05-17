# Implements: REQ-p00014-E
"""Tests for the author-declared ``**Template**`` metadata-line marker.

Phase 1 of CUR-1353 (cross-repo template support): authors mark a
requirement as a template by adding the no-value ``**Template**`` flag
to the pipe-separated metadata line. The parser sets
``stereotype=Stereotype.TEMPLATE`` on the resulting node, and
``render_node`` round-trips the flag back to disk.

Coverage / validation logic is out of scope for Phase 1.
"""

from __future__ import annotations

import pytest

from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers.lark import GrammarFactory
from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer
from elspais.graph.relations import Stereotype
from elspais.utilities.patterns import IdPatternConfig, IdResolver
from tests.core.graph_test_helpers import build_graph, make_requirement


def _make_lark_pipeline():
    """Create Lark parser + transformer with standard HHT-like pattern."""
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


def _parse_requirement(md: str):
    """Parse a single requirement block. Returns the requirement ParsedContent."""
    lark_parser, transformer = _make_lark_pipeline()
    if not md.endswith("\n"):
        md += "\n"
    tree = lark_parser.parse(md)
    results = transformer.transform(tree)
    reqs = [r for r in results if r.content_type == "requirement"]
    assert len(reqs) == 1, f"Expected exactly one requirement, got {len(reqs)}"
    return reqs[0]


# ---------------------------------------------------------------------------
# 1. Parser sets parsed_data["template"]
# ---------------------------------------------------------------------------


class TestTemplateFlagParsing:
    """Parser detects the ``**Template**`` flag on the metadata line."""

    # Implements: REQ-p00014-E
    def test_template_flag_sets_field_true(self) -> None:
        """A metadata line containing ``**Template**`` sets parsed_data['template']."""
        md = (
            "## REQ-p80001: Electronic Signature Standard\n"
            "\n"
            "**Level**: PRD | **Status**: Active | **Template**\n"
            "\n"
            "*End* *Electronic Signature Standard* | **Hash**: 00000000\n"
        )
        result = _parse_requirement(md)
        assert result.parsed_data["template"] is True
        # Ensure other fields still parse correctly alongside the flag.
        assert result.parsed_data["level"] == "prd"
        assert result.parsed_data["status"] == "Active"

    # Implements: REQ-p00014-E
    def test_template_flag_absent_defaults_false(self) -> None:
        """A requirement without ``**Template**`` has template=False in parsed_data."""
        md = (
            "## REQ-p00001: Regular Requirement\n"
            "\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "*End* *Regular Requirement* | **Hash**: 00000000\n"
        )
        result = _parse_requirement(md)
        assert result.parsed_data["template"] is False

    # Implements: REQ-p00014-E
    @pytest.mark.parametrize(
        "decoration",
        [
            "**Template**",
            "*Template*",
            "_Template_",
            "Template",
        ],
    )
    def test_template_flag_decoration_variants(self, decoration: str) -> None:
        """Markdown decoration on the flag (``**``, ``*``, ``_``, bare) all map to True."""
        md = (
            "## REQ-p80001: Template Variants\n"
            "\n"
            f"**Level**: PRD | **Status**: Active | {decoration}\n"
            "\n"
            "*End* *Template Variants* | **Hash**: 00000000\n"
        )
        result = _parse_requirement(md)
        assert result.parsed_data["template"] is True

    # Implements: REQ-p00014-E
    @pytest.mark.parametrize(
        "metadata_line",
        [
            "**Template** | **Level**: PRD | **Status**: Active",
            "**Level**: PRD | **Template** | **Status**: Active",
            "**Level**: PRD | **Status**: Active | **Template**",
        ],
    )
    def test_template_flag_anywhere_on_line(self, metadata_line: str) -> None:
        """The ``**Template**`` flag is recognized in any position on the metadata line."""
        md = (
            "## REQ-p80001: Position Test\n"
            "\n"
            f"{metadata_line}\n"
            "\n"
            "*End* *Position Test* | **Hash**: 00000000\n"
        )
        result = _parse_requirement(md)
        assert result.parsed_data["template"] is True
        assert result.parsed_data["level"] == "prd"
        assert result.parsed_data["status"] == "Active"


# ---------------------------------------------------------------------------
# 2. Builder sets Stereotype.TEMPLATE on the requirement and its assertions
# ---------------------------------------------------------------------------


class TestTemplateStereotypeSeat:
    """Builder applies ``Stereotype.TEMPLATE`` to TEMPLATE-flagged REQs and assertions."""

    # Implements: REQ-p00014-E
    def test_template_flag_sets_requirement_stereotype(self) -> None:
        """When parsed_data['template'] is True, the REQUIREMENT node is TEMPLATE."""
        template = make_requirement(
            "REQ-p80001",
            title="Template Requirement",
            assertions=[{"label": "A", "text": "obligation one"}],
        )
        template.parsed_data["template"] = True
        graph = build_graph(template)

        node = graph.find_by_id("REQ-p80001")
        assert node is not None
        assert node.kind == NodeKind.REQUIREMENT
        assert node.get_field("stereotype") == Stereotype.TEMPLATE

    # Implements: REQ-p00014-E
    def test_template_flag_propagates_to_assertions(self) -> None:
        """Assertions on a TEMPLATE requirement inherit the TEMPLATE stereotype."""
        template = make_requirement(
            "REQ-p80001",
            title="Template With Assertions",
            assertions=[
                {"label": "A", "text": "obligation one"},
                {"label": "B", "text": "obligation two"},
            ],
        )
        template.parsed_data["template"] = True
        graph = build_graph(template)

        root = graph.find_by_id("REQ-p80001")
        assert root is not None
        assertion_nodes = [c for c in root.iter_children() if c.kind == NodeKind.ASSERTION]
        assert len(assertion_nodes) == 2
        for a in assertion_nodes:
            assert (
                a.get_field("stereotype") == Stereotype.TEMPLATE
            ), f"Assertion {a.id} should inherit TEMPLATE stereotype"


# ---------------------------------------------------------------------------
# 3. Render emits **Template** when the stereotype is TEMPLATE; omits otherwise
# ---------------------------------------------------------------------------


class TestTemplateRoundTripRender:
    """``render_node`` round-trips ``**Template**`` based on the node's stereotype."""

    # Implements: REQ-p00014-E
    def test_render_emits_template_marker(self) -> None:
        """A REQ with Stereotype.TEMPLATE renders ``**Template**`` on the metadata line."""
        from elspais.graph.render import render_node

        req = make_requirement(
            "REQ-p80001",
            title="Template Req",
            level="PRD",
            status="Active",
            assertions=[{"label": "A", "text": "an obligation"}],
        )
        req.parsed_data["template"] = True
        graph = build_graph(req)
        node = graph.find_by_id("REQ-p80001")
        assert node is not None
        assert node.get_field("stereotype") == Stereotype.TEMPLATE

        rendered = render_node(node)
        # The metadata line is the third line (header, blank, metadata).
        meta_line = next(line for line in rendered.split("\n") if line.startswith("**Level**:"))
        assert (
            "**Template**" in meta_line
        ), f"Expected '**Template**' on metadata line, got: {meta_line!r}"

    # Implements: REQ-p00014-E
    def test_render_omits_template_marker_for_concrete(self) -> None:
        """A CONCRETE REQ must NOT have ``**Template**`` on its rendered metadata line."""
        from elspais.graph.render import render_node

        req = make_requirement(
            "REQ-p00001",
            title="Concrete Req",
            level="PRD",
            status="Active",
            assertions=[{"label": "A", "text": "an obligation"}],
        )
        # parsed_data["template"] is absent → builder leaves stereotype CONCRETE
        graph = build_graph(req)
        node = graph.find_by_id("REQ-p00001")
        assert node is not None
        assert node.get_field("stereotype") == Stereotype.CONCRETE

        rendered = render_node(node)
        assert (
            "**Template**" not in rendered
        ), f"CONCRETE REQ rendering should not include **Template**: {rendered!r}"


# ---------------------------------------------------------------------------
# 4. Satisfies canonicalization: bare input parses, bold form is canonical output
# ---------------------------------------------------------------------------


class TestSatisfiesAcceptedInBothForms:
    """Both ``Satisfies: REQ-X`` and ``**Satisfies**: REQ-X`` parse identically.

    Phase 1 canonicalizes render output to the bold form to match
    ``**Implements**:`` / ``**Refines**:`` convention. The parser
    continues to accept either input form.
    """

    # Implements: REQ-p00014-E
    @pytest.mark.parametrize(
        "satisfies_line",
        [
            "Satisfies: REQ-p80001",
            "**Satisfies**: REQ-p80001",
        ],
    )
    def test_both_forms_parse_identically(self, satisfies_line: str) -> None:
        """The bare and bold forms of Satisfies produce the same parsed value."""
        md = (
            "## REQ-p00044: Document Management\n"
            "\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            f"{satisfies_line}\n"
            "\n"
            "*End* *Document Management* | **Hash**: 00000000\n"
        )
        result = _parse_requirement(md)
        assert result.parsed_data["satisfies"] == ["REQ-p80001"]

    # Implements: REQ-p00014-E
    def test_render_emits_bold_satisfies(self) -> None:
        """Rendering a REQ with Satisfies produces the canonical ``**Satisfies**:`` form."""
        from elspais.graph.render import render_node

        # Build a graph with a template and a declaring REQ that satisfies it,
        # so the declaring node has satisfies_refs and renders the Satisfies line.
        template = make_requirement(
            "REQ-p80001",
            title="Template",
            assertions=[{"label": "A", "text": "obligation"}],
        )
        template.parsed_data["template"] = True
        declaring = make_requirement(
            "REQ-p00044",
            title="Subsystem",
            satisfies=["REQ-p80001"],
        )
        graph = build_graph(template, declaring)
        node = graph.find_by_id("REQ-p00044")
        assert node is not None

        rendered = render_node(node)
        # Canonical output uses bold form.
        assert (
            "**Satisfies**: REQ-p80001" in rendered
        ), f"Expected canonical '**Satisfies**: ...' in output, got: {rendered!r}"
        # And the bare form should NOT appear (would mean we double-rendered or
        # left the legacy line).
        for line in rendered.split("\n"):
            if line.startswith("Satisfies:"):
                pytest.fail(
                    f"Bare 'Satisfies:' line should not appear in canonical output: {line!r}"
                )
