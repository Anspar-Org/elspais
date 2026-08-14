# Verifies: REQ-d00054-A
"""Conformance tests: Lark reference parser vs old CodeParser/TestParser.

Tests that the new Lark-based reference grammar + transformer produces
equivalent ParsedContent to the old line-claiming parsers for code and
test files.
"""

from __future__ import annotations

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.graph.parsers.lark import GrammarFactory
from elspais.graph.parsers.lark.transformers.reference import ReferenceTransformer
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
def resolver():
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
    return IdResolver(config)


@pytest.fixture
def code_parser(resolver):
    factory = GrammarFactory(resolver)
    return factory.get_reference_parser()


def _parse_code(content, resolver, code_parser):
    """Parse as code_ref."""
    if not content.endswith("\n"):
        content += "\n"
    tree = code_parser.parse(content)
    tx = ReferenceTransformer(resolver, "code_ref")
    return tx.transform(tree)


def _parse_test(content, resolver, code_parser, **kwargs):
    """Parse as test_ref."""
    if not content.endswith("\n"):
        content += "\n"
    tree = code_parser.parse(content)
    tx = ReferenceTransformer(resolver, "test_ref", **kwargs)
    return tx.transform(tree)


class TestCodeRefParsing:
    """Test code reference parsing via Lark grammar."""

    def test_single_implements(self, resolver, code_parser):
        content = "# Implements: REQ-p00001\ndef foo(): pass\n"
        results = _parse_code(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "code_ref"]
        assert len(refs) == 1
        assert refs[0].parsed_data["implements"] == ["REQ-p00001"]
        assert refs[0].parsed_data["verifies"] == []

    def test_single_verifies(self, resolver, code_parser):
        content = "# Verifies: REQ-p00001-A\ndef foo(): pass\n"
        results = _parse_code(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "code_ref"]
        assert len(refs) == 1
        assert refs[0].parsed_data["verifies"] == ["REQ-p00001-A"]
        assert refs[0].parsed_data["implements"] == []

    def test_multiple_refs_comma_separated(self, resolver, code_parser):
        content = "# Implements: REQ-p00001, REQ-p00002\n"
        results = _parse_code(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "code_ref"]
        assert len(refs) == 1
        assert refs[0].parsed_data["implements"] == ["REQ-p00001", "REQ-p00002"]

    def test_block_header_and_refs(self, resolver, code_parser):
        content = """\
# IMPLEMENTS REQUIREMENTS:
#   REQ-d00050: First
#   REQ-d00051: Second
def foo(): pass
"""
        results = _parse_code(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "code_ref"]
        assert len(refs) == 1
        assert refs[0].parsed_data["implements"] == ["REQ-d00050", "REQ-d00051"]
        assert refs[0].start_line == 1
        assert refs[0].end_line == 3

    def test_js_style_comments(self, resolver, code_parser):
        content = "// Implements: REQ-p00001\nfunction foo() {}\n"
        results = _parse_code(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "code_ref"]
        assert len(refs) == 1
        assert refs[0].parsed_data["implements"] == ["REQ-p00001"]

    def test_no_refs_in_plain_code(self, resolver, code_parser):
        content = "def foo():\n    return 42\n"
        results = _parse_code(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "code_ref"]
        assert len(refs) == 0


class TestTestRefParsing:
    """Test test reference parsing via Lark grammar."""

    def test_verifies_comment(self, resolver, code_parser):
        content = "# Verifies: REQ-p00001\ndef test_something(): pass\n"
        results = _parse_test(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "test_ref"]
        assert len(refs) >= 1
        assert refs[0].parsed_data["verifies"] == ["REQ-p00001"]

    def test_test_name_pattern(self, resolver, code_parser):
        content = "def test_foo_REQ_p00001_A(): pass\n"
        results = _parse_test(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "test_ref"]
        assert len(refs) >= 1
        # Find the one from test name
        name_refs = [r for r in refs if "REQ-p00001" in str(r.parsed_data.get("verifies", []))]
        assert len(name_refs) >= 1

    def test_file_default_verifies(self, resolver, code_parser):
        content = "def test_unlinked(): pass\n"
        results = _parse_test(
            content,
            resolver,
            code_parser,
            file_default_verifies=["REQ-p00001"],
            all_test_funcs=[(1, "test_unlinked", None)],
        )
        refs = [r for r in results if r.content_type == "test_ref"]
        assert len(refs) >= 1
        # Unlinked test function should inherit file defaults
        assert refs[0].parsed_data["file_default_verifies"] == ["REQ-p00001"]

    def test_block_verifies(self, resolver, code_parser):
        content = """\
-- VERIFIES REQUIREMENTS:
--   REQ-p00001: First test
--   REQ-p00002: Second test
"""
        results = _parse_test(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "test_ref"]
        assert len(refs) == 1
        assert "REQ-p00001" in refs[0].parsed_data["verifies"]
        assert "REQ-p00002" in refs[0].parsed_data["verifies"]
