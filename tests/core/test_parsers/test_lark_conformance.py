# Verifies: REQ-d00054-A
"""Conformance tests: Lark parser vs old pipeline produce identical ParsedContent.

Feeds fixture spec files through both the old line-claiming pipeline and the
new Lark grammar + transformer, asserting equivalence of the ParsedContent
output for requirements.
"""

from __future__ import annotations

import pytest

from elspais.graph.parsers.lark import GrammarFactory
from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer
from elspais.utilities.patterns import IdPatternConfig, IdResolver


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

    def test_hash_sub_headings_recognized(self):
        """### sub-headings inside ## Assertions are captured as sub-heading sections.

        CUR-1199: When assertions are grouped under ### markdown headings (rather
        than inline **bold**/*italic* markers), the parser must recognize the
        ### lines as sub-headings inside the assertion_block. All assertions
        must still be attributed and the ### text captured with
        heading_style="###".
        """
        content = """\
## REQ-p00001: With Hash Sub-Headings
**Level**: PRD | **Status**: Active

## Assertions

### Group A

A. First assertion in group A.

B. Second assertion in group A.

### Group B

C. Third assertion in group B.

*End* *With Hash Sub-Headings* | **Hash**: abc12345
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1, f"Expected exactly 1 requirement, got {len(reqs)}"
        d = reqs[0].parsed_data
        assertions = d["assertions"]
        assert len(assertions) == 3, (
            f"Expected 3 assertions, got {len(assertions)}: "
            f"{[a.get('label') for a in assertions]}"
        )
        assert (
            assertions[0]["label"] == "A"
        ), f"First assertion label should be A, got {assertions[0]['label']!r}"
        assert (
            assertions[1]["label"] == "B"
        ), f"Second assertion label should be B, got {assertions[1]['label']!r}"
        assert (
            assertions[2]["label"] == "C"
        ), f"Third assertion label should be C, got {assertions[2]['label']!r}"
        sections = d["sections"]
        hash_subs = [s for s in sections if s.get("heading_style") == "###"]
        assert len(hash_subs) == 2, (
            f"Expected 2 ### sub-heading sections, got {len(hash_subs)}: "
            f"{[(s.get('heading'), s.get('heading_style')) for s in sections]}"
        )
        headings = [s["heading"] for s in hash_subs]
        assert headings == [
            "Group A",
            "Group B",
        ], f"Expected sub-headings [Group A, Group B], got {headings}"

    def test_h4_sub_headings_recognized(self):
        """#### (4-hash) sub-headings inside ## Assertions are captured.

        CUR-1199: ###/####/#####/###### are all valid sub-heading styles inside
        the assertion_block, and the literal hash prefix is preserved in
        heading_style.
        """
        content = """\
## REQ-p00001: With H4 Sub-Headings
**Level**: PRD | **Status**: Active

## Assertions

#### Group A

A. First assertion in group A.

B. Second assertion in group A.

#### Group B

C. Third assertion in group B.

*End* *With H4 Sub-Headings* | **Hash**: abc12345
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1, f"Expected exactly 1 requirement, got {len(reqs)}"
        d = reqs[0].parsed_data
        assertions = d["assertions"]
        assert len(assertions) == 3, (
            f"Expected 3 assertions, got {len(assertions)}: "
            f"{[a.get('label') for a in assertions]}"
        )
        assert [a["label"] for a in assertions] == [
            "A",
            "B",
            "C",
        ], f"Expected labels [A, B, C], got {[a['label'] for a in assertions]}"
        sections = d["sections"]
        h4_subs = [s for s in sections if s.get("heading_style") == "####"]
        assert len(h4_subs) == 2, (
            f"Expected 2 #### sub-heading sections, got {len(h4_subs)}: "
            f"{[(s.get('heading'), s.get('heading_style')) for s in sections]}"
        )
        headings = [s["heading"] for s in h4_subs]
        assert headings == [
            "Group A",
            "Group B",
        ], f"Expected sub-headings [Group A, Group B], got {headings}"

    def test_mixed_inline_and_hash_sub_headings(self):
        """Mixing **bold**, *italic*, and ### sub-headings all parse correctly.

        CUR-1199: The three sub-heading styles must coexist in a single
        assertion_block. Each captured section preserves its original
        heading_style ("**", "*", or "###") and all assertions remain
        attributed.
        """
        content = """\
## REQ-p00001: Mixed Sub-Headings
**Level**: PRD | **Status**: Active

## Assertions

**Inline Bold**

A. First assertion.

*italic*

B. Second assertion.

### Hash

C. Third assertion.

*End* *Mixed Sub-Headings* | **Hash**: abc12345
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1, f"Expected exactly 1 requirement, got {len(reqs)}"
        d = reqs[0].parsed_data
        assertions = d["assertions"]
        assert [a["label"] for a in assertions] == ["A", "B", "C"], (
            "All three assertions must be attributed across mixed sub-heading styles; "
            f"got {[a['label'] for a in assertions]}"
        )
        sections = d["sections"]
        # Build {heading: heading_style} map filtered to our three sub-headings
        sub_map = {
            s["heading"]: s.get("heading_style")
            for s in sections
            if s.get("heading") in {"Inline Bold", "italic", "Hash"}
        }
        assert sub_map.get("Inline Bold") == "**", (
            f"**bold** sub-heading should have heading_style='**', "
            f"got {sub_map.get('Inline Bold')!r}; full sections: {sections}"
        )
        assert sub_map.get("italic") == "*", (
            f"*italic* sub-heading should have heading_style='*', "
            f"got {sub_map.get('italic')!r}; full sections: {sections}"
        )
        assert sub_map.get("Hash") == "###", (
            f"### sub-heading should have heading_style='###', "
            f"got {sub_map.get('Hash')!r}; full sections: {sections}"
        )


class TestLarkCaseInsensitiveHeaders:
    """Tests that ``## Assertions`` and ``## Changelog`` headers are
    recognized case-insensitively.

    Regression: previously, terminals matched only the exact
    capitalization ``Assertions``/``Changelog``. Lowercase or uppercase
    variants were lexed as ``SECTION_HDR`` (a generic named section) and
    then dropped by the transformer's ``heading.lower() in
    ("assertions", "changelog")`` filter -- silently losing assertion
    and changelog data. The grammar now uses character classes
    (``[Aa][Ss][Ss]...``) so any casing matches the structural keyword.
    """

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

    def test_lowercase_assertions_recognized(self):
        content = """\
## REQ-p00001: Lowercase Assertions
**Level**: PRD | **Status**: Active

## assertions

A. SHALL do A.

B. SHALL do B.

*End* *Lowercase Assertions* | **Hash**: abc12345
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1, f"Expected exactly 1 requirement, got {len(reqs)}"
        d = reqs[0].parsed_data
        assertions = d["assertions"]
        assert len(assertions) == 2, (
            f"Expected 2 assertions captured under lowercase '## assertions', "
            f"got {len(assertions)}: {[a.get('label') for a in assertions]}"
        )
        assert [a["label"] for a in assertions] == ["A", "B"]
        # Must NOT be misclassified as a named section.
        sections = d["sections"]
        assert not any(s.get("heading", "").lower() == "assertions" for s in sections), (
            f"'## assertions' must be parsed as the assertion block, not a "
            f"named section. Got sections: {sections}"
        )

    def test_uppercase_assertions_recognized(self):
        content = """\
## REQ-p00001: Uppercase Assertions
**Level**: PRD | **Status**: Active

## ASSERTIONS

A. SHALL do A.

B. SHALL do B.

*End* *Uppercase Assertions* | **Hash**: abc12345
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        assertions = d["assertions"]
        assert len(assertions) == 2, (
            f"Expected 2 assertions captured under '## ASSERTIONS', "
            f"got {len(assertions)}: {[a.get('label') for a in assertions]}"
        )
        assert [a["label"] for a in assertions] == ["A", "B"]
        sections = d["sections"]
        assert not any(s.get("heading", "").lower() == "assertions" for s in sections), (
            f"'## ASSERTIONS' must be parsed as the assertion block, not a "
            f"named section. Got sections: {sections}"
        )

    def test_mixed_case_assertions_recognized(self):
        content = """\
## REQ-p00001: Mixed Case Assertions
**Level**: PRD | **Status**: Active

## AsSeRtIoNs

A. SHALL do A.

B. SHALL do B.

*End* *Mixed Case Assertions* | **Hash**: abc12345
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        assertions = d["assertions"]
        assert len(assertions) == 2, (
            f"Expected 2 assertions captured under '## AsSeRtIoNs', "
            f"got {len(assertions)}: {[a.get('label') for a in assertions]}"
        )
        assert [a["label"] for a in assertions] == ["A", "B"]
        sections = d["sections"]
        assert not any(s.get("heading", "").lower() == "assertions" for s in sections), (
            f"'## AsSeRtIoNs' must be parsed as the assertion block, not a "
            f"named section. Got sections: {sections}"
        )

    def test_lowercase_changelog_recognized(self):
        content = """\
## REQ-p00001: Lowercase Changelog
**Level**: PRD | **Status**: Active

## Assertions

A. SHALL do A.

## changelog

- 2025-01-01 | abc12345 | 0 | Author (a@b) | reason

*End* *Lowercase Changelog* | **Hash**: def45678
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        changelog = d["changelog"]
        assert len(changelog) == 1, (
            f"Expected 1 changelog entry captured under '## changelog', "
            f"got {len(changelog)}: {changelog}"
        )
        assert changelog[0]["date"] == "2025-01-01", f"Changelog date mismatch: {changelog[0]}"

    def test_uppercase_changelog_recognized(self):
        content = """\
## REQ-p00001: Uppercase Changelog
**Level**: PRD | **Status**: Active

## Assertions

A. SHALL do A.

## CHANGELOG

- 2025-01-01 | abc12345 | 0 | Author (a@b) | reason

*End* *Uppercase Changelog* | **Hash**: def45678
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        changelog = d["changelog"]
        assert len(changelog) == 1, (
            f"Expected 1 changelog entry captured under '## CHANGELOG', "
            f"got {len(changelog)}: {changelog}"
        )
        assert changelog[0]["date"] == "2025-01-01"

    def test_named_section_about_assertions_not_misclassified(self):
        """Named sections that *contain* 'Assertions' as a substring (but
        do not equal it) must remain named sections.

        The negative lookahead in ``SECTION_HDR`` excludes only headings
        that EQUAL ``assertions``/``changelog`` (anchored with ``\\b``),
        not those that have those words as substrings.
        """
        content = """\
## REQ-p00001: Section Substring
**Level**: PRD | **Status**: Active

## Notes about Assertions

Some prose discussing assertions in general.

## Assertions

A. SHALL do A.

*End* *Section Substring* | **Hash**: abc12345
"""
        results = self._parse(content)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        d = reqs[0].parsed_data
        sections = d["sections"]
        headings = [s.get("heading") for s in sections]
        assert "Notes about Assertions" in headings, (
            f"'## Notes about Assertions' must remain a named section "
            f"(it does not equal 'Assertions'). Got headings: {headings}"
        )
        assertions = d["assertions"]
        assert len(assertions) == 1, (
            f"Expected 1 assertion under '## Assertions', got "
            f"{len(assertions)}: {[a.get('label') for a in assertions]}"
        )
        assert assertions[0]["label"] == "A"


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
