# Verifies: REQ-d00054-A
"""Conformance tests: Lark parser vs old pipeline produce identical ParsedContent.

Feeds fixture spec files through both the old line-claiming pipeline and the
new Lark grammar + transformer, asserting equivalence of the ParsedContent
output for requirements.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.parsers import ParseContext, ParserRegistry
from elspais.graph.parsers.journey import JourneyParser
from elspais.graph.parsers.lark import GrammarFactory
from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer
from elspais.graph.parsers.remainder import RemainderParser
from elspais.graph.parsers.requirement import RequirementParser
from elspais.utilities.patterns import IdPatternConfig, IdResolver

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"


@pytest.fixture
def hht_resolver():
    """IdResolver for standard HHT-like pattern (with short alias)."""
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
    return IdResolver(config)


def _old_pipeline(resolver: IdResolver):
    """Create old parser registry."""
    registry = ParserRegistry()
    registry.register(RequirementParser(resolver))
    registry.register(JourneyParser())
    registry.register(RemainderParser())
    return registry


def _new_pipeline(resolver: IdResolver):
    """Create new Lark parser + transformer."""
    factory = GrammarFactory(resolver)
    lark_parser = factory.get_requirement_parser()
    transformer = RequirementTransformer(resolver)
    return lark_parser, transformer


def _parse_old(content: str, resolver: IdResolver, file_path: str = "test.md"):
    """Parse with old pipeline, return requirement ParsedContent list."""
    registry = _old_pipeline(resolver)
    lines = [(i + 1, line) for i, line in enumerate(content.split("\n"))]
    ctx = ParseContext(file_path=file_path)
    results = list(registry.parse_all(lines, ctx))
    return [r for r in results if r.content_type == "requirement"]


def _parse_new(content: str, resolver: IdResolver):
    """Parse with new Lark pipeline, return requirement ParsedContent list."""
    lark_parser, transformer = _new_pipeline(resolver)
    if not content.endswith("\n"):
        content += "\n"
    tree = lark_parser.parse(content)
    results = transformer.transform(tree)
    return [r for r in results if r.content_type == "requirement"]


def _assert_req_equivalent(old, new, file_name: str = ""):
    """Assert two requirement ParsedContent objects are equivalent."""
    od, nd = old.parsed_data, new.parsed_data
    prefix = f"{file_name} {od['id']}: " if file_name else f"{od['id']}: "

    # Core fields
    for key in ["id", "title", "level", "status", "hash", "heading_level"]:
        assert od.get(key) == nd.get(key), f"{prefix}{key}: {od.get(key)!r} != {nd.get(key)!r}"

    # References
    for key in ["implements", "refines", "satisfies"]:
        assert od.get(key) == nd.get(key), f"{prefix}{key}: {od.get(key)!r} != {nd.get(key)!r}"

    # Assertions
    old_asserts = od.get("assertions", [])
    new_asserts = nd.get("assertions", [])
    assert len(old_asserts) == len(
        new_asserts
    ), f"{prefix}assertions count: {len(old_asserts)} != {len(new_asserts)}"
    for i, (oa, na) in enumerate(zip(old_asserts, new_asserts, strict=True)):
        assert (
            oa["label"] == na["label"]
        ), f"{prefix}assertion[{i}] label: {oa['label']!r} != {na['label']!r}"
        assert (
            oa["text"] == na["text"]
        ), f"{prefix}assertion[{i}] text: {oa['text']!r} != {na['text']!r}"


class TestLarkConformanceHHT:
    """Conformance tests using HHT-like fixtures."""

    @pytest.fixture(autouse=True)
    def _setup(self, hht_resolver):
        self.resolver = hht_resolver

    def _compare_file(self, spec_file: Path):
        content = spec_file.read_text()
        old_reqs = _parse_old(content, self.resolver, str(spec_file))
        new_reqs = _parse_new(content, self.resolver)
        assert len(old_reqs) == len(
            new_reqs
        ), f"{spec_file.name}: old={len(old_reqs)} new={len(new_reqs)} reqs"
        for old, new in zip(old_reqs, new_reqs, strict=True):
            _assert_req_equivalent(old, new, spec_file.name)

    def test_prd_core(self):
        self._compare_file(FIXTURES_DIR / "hht-like" / "spec" / "prd-core.md")

    def test_ops_deploy(self):
        self._compare_file(FIXTURES_DIR / "hht-like" / "spec" / "ops-deploy.md")

    def test_dev_impl(self):
        self._compare_file(FIXTURES_DIR / "hht-like" / "spec" / "dev-impl.md")

    def test_index_no_reqs(self):
        self._compare_file(FIXTURES_DIR / "hht-like" / "spec" / "INDEX.md")

    def test_assertions_fixture_prd(self):
        self._compare_file(FIXTURES_DIR / "assertions" / "spec" / "prd-sample.md")

    def test_assertions_fixture_dev(self):
        self._compare_file(FIXTURES_DIR / "assertions" / "spec" / "dev-impl.md")

    def test_invalid_broken_links(self):
        self._compare_file(FIXTURES_DIR / "invalid" / "broken-links" / "spec" / "broken.md")

    def test_invalid_circular_deps(self):
        self._compare_file(FIXTURES_DIR / "invalid" / "circular-deps" / "spec" / "circular.md")

    def test_invalid_missing_hash(self):
        self._compare_file(FIXTURES_DIR / "invalid" / "missing-hash" / "spec" / "missing.md")


class TestLarkTransformerDirectly:
    """Direct tests of Lark transformer output."""

    @pytest.fixture(autouse=True)
    def _setup(self, hht_resolver):
        self.resolver = hht_resolver
        factory = GrammarFactory(hht_resolver)
        self.parser = factory.get_requirement_parser()
        self.transformer = RequirementTransformer(hht_resolver)

    def _parse(self, content: str):
        if not content.endswith("\n"):
            content += "\n"
        tree = self.parser.parse(content)
        return self.transformer.transform(tree)

    def test_simple_requirement(self):
        content = """\
## REQ-p00001: Test Requirement
**Level**: PRD | **Status**: Active
Body text.
## Assertions
A. First assertion.
B. Second assertion.
*End* *Test Requirement* | **Hash**: abc12345
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        assert d["id"] == "REQ-p00001"
        assert d["title"] == "Test Requirement"
        assert d["level"] == "prd"
        assert d["status"] == "Active"
        assert d["hash"] == "abc12345"
        assert len(d["assertions"]) == 2
        assert d["assertions"][0]["label"] == "A"
        assert d["assertions"][1]["label"] == "B"

    def test_implements_refs_normalized(self):
        content = """\
## REQ-o00001: Ops Requirement
**Level**: OPS | **Implements**: p00001, p00002 | **Status**: Active
Body.
*End* *Ops Requirement*
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        assert d["implements"] == ["REQ-p00001", "REQ-p00002"]

    def test_remainder_between_requirements(self):
        content = """\
# Title
Some prose.
---
## REQ-p00001: First
**Level**: PRD | **Status**: Active
Body.
*End* *First* | **Hash**: aaa
---
## REQ-p00002: Second
**Level**: PRD | **Status**: Active
Body.
*End* *Second* | **Hash**: bbb
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        rems = [r for r in results if r.content_type == "remainder"]
        assert len(reqs) == 2
        assert len(rems) >= 2  # title/prose before first req, --- between

    def test_requirement_without_footer(self):
        content = """\
## REQ-p00001: No Footer
**Level**: PRD | **Status**: Draft
Body text without end marker.
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        assert d["id"] == "REQ-p00001"
        assert d["hash"] is None

    def test_named_sections_captured(self):
        content = """\
## REQ-p00001: With Sections
**Level**: PRD | **Status**: Active
Preamble text.
## Rationale
This is the rationale.
## Implementation Notes
Some implementation details.
*End* *With Sections* | **Hash**: xyz
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        sections = reqs[0].parsed_data["sections"]
        headings = [s["heading"] for s in sections]
        assert "preamble" in headings
        assert "Rationale" in headings
        assert "Implementation Notes" in headings

    def test_satisfies_field(self):
        content = """\
## REQ-d00001: Satisfies Test
**Level**: DEV | **Status**: Active
Satisfies: REQ-p00001, REQ-p00002
Body.
*End* *Satisfies Test*
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        assert reqs[0].parsed_data["satisfies"] == ["REQ-p00001", "REQ-p00002"]


class TestLarkMetadataFlexibility:
    """Tests for flexible metadata field matching (decoration + separators)."""

    @pytest.fixture(autouse=True)
    def _setup(self, hht_resolver):
        self.resolver = hht_resolver
        factory = GrammarFactory(hht_resolver)
        self.parser = factory.get_requirement_parser()
        self.transformer = RequirementTransformer(hht_resolver)

    def _parse(self, content: str):
        if not content.endswith("\n"):
            content += "\n"
        tree = self.parser.parse(content)
        return self.transformer.transform(tree)

    def _parse_req(self, content: str):
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        return reqs[0].parsed_data

    def test_bold_colon_separator(self):
        content = """\
## REQ-p00001: Test
**Level**: PRD | **Status**: Active
*End* *Test*
"""
        d = self._parse_req(content)
        assert d["level"] == "prd"
        assert d["status"] == "Active"

    def test_italic_colon_separator(self):
        content = """\
## REQ-p00001: Test
*Level*: PRD | *Status*: Active
*End* *Test*
"""
        d = self._parse_req(content)
        assert d["level"] == "prd"
        assert d["status"] == "Active"

    def test_underscore_equals_separator(self):
        content = """\
## REQ-p00001: Test
_Level_= PRD | _Status_= Active
*End* *Test*
"""
        d = self._parse_req(content)
        assert d["level"] == "prd"
        assert d["status"] == "Active"

    def test_plain_colon_separator(self):
        content = """\
## REQ-p00001: Test
Level: PRD | Status: Active
*End* *Test*
"""
        d = self._parse_req(content)
        assert d["level"] == "prd"
        assert d["status"] == "Active"

    def test_plain_space_separator(self):
        content = """\
## REQ-p00001: Test
Level PRD | Status Active
*End* *Test*
"""
        d = self._parse_req(content)
        assert d["level"] == "prd"
        assert d["status"] == "Active"

    def test_case_insensitive_field_names(self):
        content = """\
## REQ-p00001: Test
**level**: prd | **status**: draft
*End* *Test*
"""
        d = self._parse_req(content)
        assert d["level"] == "prd"
        assert d["status"] == "draft"

    def test_implements_with_decoration(self):
        content = """\
## REQ-o00001: Test
*Level*: OPS | *Status*: Active | *Implements*: REQ-p00001, REQ-p00002
*End* *Test*
"""
        d = self._parse_req(content)
        assert d["implements"] == ["REQ-p00001", "REQ-p00002"]

    def test_metadata_like_text_in_code_fence_is_remainder(self):
        """Metadata-like text outside a requirement must parse as remainder."""
        content = """\
Here is an example:

**Level**: PRD | **Status**: Active

That was just an example.
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 0
        rems = [r for r in results if r.content_type == "remainder"]
        assert len(rems) >= 1


class TestLarkAssertionSubHeadings:
    """Tests for assertion sub-headings within assertion blocks."""

    @pytest.fixture(autouse=True)
    def _setup(self, hht_resolver):
        self.resolver = hht_resolver
        factory = GrammarFactory(hht_resolver)
        self.parser = factory.get_requirement_parser()
        self.transformer = RequirementTransformer(hht_resolver)

    def _parse(self, content: str):
        if not content.endswith("\n"):
            content += "\n"
        tree = self.parser.parse(content)
        return self.transformer.transform(tree)

    def test_sub_headings_ignored_assertions_preserved(self):
        content = """\
## REQ-p00001: With Sub-Headings
**Level**: PRD | **Status**: Active

## Assertions

**Section 1**

A. First assertion.

**Section 2**

B. Second assertion.

C. Third assertion.

*End* *With Sub-Headings* | **Hash**: abc12345
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        assertions = d["assertions"]
        assert len(assertions) == 3
        assert assertions[0]["label"] == "A"
        assert assertions[1]["label"] == "B"
        assert assertions[2]["label"] == "C"

    def test_multiline_assertion_with_list_items(self):
        content = """\
## REQ-p00001: Multi-line
**Level**: PRD | **Status**: Active

## Assertions

A. This is a multi-line assertion

- line item 1
- line item 2
- line item 3

B. Simple assertion.

*End* *Multi-line* | **Hash**: def45678
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        assertions = d["assertions"]
        assert len(assertions) == 2
        # First assertion has continuation text
        assert "line item 1" in assertions[0]["text"]
        assert "line item 3" in assertions[0]["text"]
        assert assertions[1]["label"] == "B"


class TestLarkPerformance:
    """Verify LALR parser performance is acceptable."""

    @pytest.fixture(autouse=True)
    def _setup(self, hht_resolver):
        self.resolver = hht_resolver
        factory = GrammarFactory(hht_resolver)
        self.parser = factory.get_requirement_parser()

    def test_large_file_parses_under_100ms(self):
        """A 1000-line file should parse in well under 100ms with LALR."""
        import time

        # Generate a large synthetic spec file
        lines = []
        for i in range(50):
            lines.append(f"## REQ-p{i:05d}: Requirement {i}")
            lines.append("**Level**: PRD | **Status**: Active")
            lines.append("")
            lines.append("## Assertions")
            lines.append("")
            lines.append(f"A. Assertion for requirement {i}.")
            lines.append(f"B. Another assertion for requirement {i}.")
            lines.append("")
            lines.append("## Rationale")
            lines.append("")
            lines.append(f"Rationale text for requirement {i}.")
            lines.append("")
            lines.append(f"*End* *Requirement {i}* | **Hash**: {i:08x}")
            lines.append("---")
            lines.append("")

        content = "\n".join(lines) + "\n"
        assert len(content.splitlines()) > 700

        t0 = time.time()
        self.parser.parse(content)
        elapsed = time.time() - t0
        assert (
            elapsed < 0.1
        ), f"LALR parser took {elapsed:.3f}s on {len(content.splitlines())} lines"
