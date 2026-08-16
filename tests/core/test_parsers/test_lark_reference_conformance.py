# Verifies: REQ-d00054-A
"""Conformance tests: Lark reference parser vs old CodeParser/TestParser.

Tests that the new Lark-based reference grammar + transformer produces
equivalent ParsedContent to the old line-claiming parsers for code and
test files.
"""

from __future__ import annotations

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.graph.parsers.lark import FileDispatcher, GrammarFactory
from elspais.graph.parsers.lark.transformers.reference import ReferenceTransformer
from elspais.graph.reference_faults import FaultCode
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


@pytest.fixture
def parse_code(resolver, code_parser):
    """Parse *content* as a code file, returning ``(results, transformer)``.

    The transformer is returned alongside the ``ParsedContent`` list so a
    test can inspect ``transformer.style_findings`` -- a fact about the
    file that never travels on the results themselves.
    """

    def _parse(content):
        text = content if content.endswith("\n") else content + "\n"
        tree = code_parser.parse(text)
        tx = ReferenceTransformer(resolver, "code_ref")
        return tx.transform(tree), tx

    return _parse


def _all_refs(result) -> set[str]:
    """Every reference-shaped string surfacing anywhere in a parse result.

    ``result`` is the ``(results, transformer)`` pair ``parse_code``
    returns.  Implements/verifies/forbidden all count -- a test asking "is
    this identifier bound anywhere" should not have to know which keyword
    was used or whether the keyword was refused for this file's kind.
    """
    results, _tx = result
    found: set[str] = set()
    for r in results:
        found.update(r.parsed_data.get("implements", []) or [])
        found.update(r.parsed_data.get("verifies", []) or [])
        found.update(r.parsed_data.get("forbidden", []) or [])
    return found


def _diagnostics(result):
    """The transformer's reported faults for a parse result.

    ``result`` is the ``(results, transformer)`` pair ``parse_code``
    returns -- a diagnostic is a fact about the file, not about any single
    ``ParsedContent``, so it lives on the transformer rather than on a
    result entry.
    """
    _results, tx = result
    return tx.faults


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

    # Verifies: REQ-d00269-G
    def test_a_partly_unmatched_scanned_line_binds_the_good_item(self, resolver, code_parser):
        """A defect in one item is evidence about that item, not the list:
        the item the grammar cannot account for is reported (carried
        through in ``implements`` and named in ``reference_verdicts``)
        while the item that did resolve still binds -- salvage, not
        all-or-nothing rejection."""
        content = "# Implements: REQ-p00001, GARBAGE-999\ndef foo(): pass\n"
        results = _parse_code(content, resolver, code_parser)
        refs = [r for r in results if r.content_type == "code_ref"]
        assert len(refs) == 1
        assert "REQ-p00001" in refs[0].parsed_data["implements"], (
            "the item that resolved must still bind; got " f"{refs[0].parsed_data['implements']}"
        )
        assert "GARBAGE-999" in refs[0].parsed_data["implements"], (
            "the faulted item stays in the list so the builder can report "
            f"it as a broken reference; got {refs[0].parsed_data['implements']}"
        )
        assert "GARBAGE-999" in refs[0].parsed_data["reference_verdicts"], (
            "the faulted item's verdict must reach the builder; got "
            f"{refs[0].parsed_data['reference_verdicts']}"
        )


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

    # Verifies: REQ-d00269-G
    def test_a_partly_unmatched_file_default_binds_the_good_item(self, resolver):
        """A second salvage site, distinct from ``_handle_unresolved_ref``:
        ``FileDispatcher.dispatch_test`` reads a file-level ``Verifies:``
        comment into ``file_default_verifies`` through its own loop. One
        unmatched item in that list must not cost the item that did
        resolve -- every unlinked test function still inherits the good
        reference as its default.

        Driven through the real ``FileDispatcher.dispatch_test`` pipeline
        (prescan, tree parse, the file-level extraction loop, then the
        transformer's third pass for unlinked test functions) rather than a
        reimplementation of the loop, so this fails if the loop's salvage
        behaviour is ever weakened back to all-or-nothing.

        The file-level comment sits far enough above ``test_something`` that
        the AST pre-scan's forward-looking comment/function binding does not
        attach it as the function's own annotation -- keeping this test on
        the file-default path (the third pass) rather than the
        already-covered per-function path in ``_handle_unresolved_ref``.

        Salvage is only honest because the item that did *not* resolve is
        still reported somewhere: the same line also goes through the
        transformer's ordinary ``single_ref`` handling (``_handle_unresolved_ref``),
        which produces its own ``test_ref`` entry (unattached to any
        function) carrying ``GARBAGE-999`` in both ``verifies`` and
        ``reference_verdicts`` -- that is this test's other half.
        """
        content = (
            "# Verifies: REQ-p00001, GARBAGE-999\n"
            "import time\n\n\n\n\n\n\n"
            "def test_something():\n"
            "    assert True\n"
        )
        dispatcher = FileDispatcher(resolver)
        items = dispatcher.dispatch_test(content, file_path="tests/test_demo.py")

        unlinked = [
            r
            for r in items
            if r.content_type == "test_ref"
            and r.parsed_data.get("function_name") == "test_something"
        ]
        assert len(unlinked) == 1, f"expected one entry for test_something; got {items}"
        assert unlinked[0].parsed_data["file_default_verifies"] == ["REQ-p00001"], (
            "the item that resolved must still populate the file-level "
            f"default; got {unlinked[0].parsed_data}"
        )
        assert unlinked[0].parsed_data["verifies"] == ["REQ-p00001"]

        # The faulted sibling is not simply dropped: the file-level line's
        # own single_ref entry (function_name is None -- it belongs to no
        # function) carries it forward for reporting.
        file_level = [
            r
            for r in items
            if r.content_type == "test_ref" and r.parsed_data.get("function_name") is None
        ]
        assert len(file_level) == 1, f"expected one file-level entry; got {items}"
        assert "GARBAGE-999" in file_level[0].parsed_data["verifies"], (
            "the faulted item must still reach a reportable entry, not "
            f"vanish once salvaged from the default; got {file_level[0].parsed_data}"
        )
        assert "GARBAGE-999" in file_level[0].parsed_data["reference_verdicts"], (
            "its verdict must ride alongside so the builder can report it "
            f"as a broken reference; got {file_level[0].parsed_data}"
        )


# Verifies: REQ-d00269-E
@pytest.mark.parametrize("spelling", ["Implements", "IMPLEMENTS", "implements", "ImPlEmEnTs"])
def test_a_keyword_is_recognised_in_any_case(parse_code, spelling):
    result = parse_code(f"# {spelling}: REQ-d00001\ndef f():\n    return 1\n")
    assert "REQ-d00001" in _all_refs(result)


# Verifies: REQ-d00272-G
def test_a_non_canonical_keyword_still_binds(parse_code):
    result = parse_code("# implements: REQ-d00001\ndef f():\n    return 1\n")
    assert "REQ-d00001" in _all_refs(result)
    _results, tx = result
    assert (1, FaultCode.KEYWORD_WRONG_CASE) in tx.style_findings


# Verifies: REQ-d00269-E
def test_a_space_before_the_colon_is_not_a_keyword(parse_code):
    result = parse_code("# Implements : REQ-d00001\ndef f():\n    return 1\n")
    assert "REQ-d00001" not in _all_refs(result)


# Verifies: REQ-d00269-E
@pytest.mark.parametrize(
    "header,opens",
    [
        ("# IMPLEMENTS REQUIREMENTS:", True),
        ("# Implements Requirements:", True),
        ("# IMPLEMENTS REQUIREMENTS", False),
        ("# IMPLEMENTS REQUIREMENT:", False),
    ],
)
def test_the_legacy_block_header_is_strict_about_everything_but_case(parse_code, header, opens):
    result = parse_code(f"{header}\n#   REQ-d00001\ndef f():\n    return 1\n")
    assert ("REQ-d00001" in _all_refs(result)) is opens


# Verifies: REQ-d00272-G
def test_no_space_after_the_comment_marker_still_binds(parse_code):
    result = parse_code("#Implements: REQ-d00001\ndef f():\n    return 1\n")
    assert "REQ-d00001" in _all_refs(result)
    _results, tx = result
    assert (1, FaultCode.KEYWORD_NO_MARKER_SPACE) in tx.style_findings


# Verifies: REQ-d00272-G
def test_markdown_emphasis_in_a_code_comment_still_binds(parse_code):
    result = parse_code("# **Implements**: REQ-d00001\ndef f():\n    return 1\n")
    assert "REQ-d00001" in _all_refs(result)
    _results, tx = result
    assert (1, FaultCode.KEYWORD_MARKDOWN_EMPHASIS_OFF_MARKDOWN) in tx.style_findings


# Verifies: REQ-d00272-B
def test_a_stray_leading_asterisk_on_the_target_does_not_bind(parse_code):
    """A malformed target must stay malformed, not be laundered by the
    emphasis-stripping fix.

    The fix for markdown-emphasis-wrapped keywords must strip only the
    keyword's own closing "**", never any leading "*" that is part of what
    the author actually wrote as the target -- otherwise an ordinary typo
    silently becomes a clean edge, which is the exact defect this work
    exists to remove.
    """
    results, tx = parse_code("# Implements: *REQ-d00001\ndef f():\n    return 1\n")
    assert "REQ-d00001" not in _all_refs((results, tx))
    refs = [r for r in results if r.content_type == "code_ref"]
    assert len(refs) == 1
    verdicts = refs[0].parsed_data.get("reference_verdicts", {})
    assert (
        "*REQ-d00001" in verdicts
    ), f"the stray asterisk must survive verbatim in the reported target; got {verdicts}"


# Verifies: REQ-d00272-G
def test_the_canonical_form_records_no_style_finding(parse_code):
    result = parse_code("# Implements: REQ-d00001\ndef f():\n    return 1\n")
    _results, tx = result
    assert tx.style_findings == []


# Verifies: REQ-d00272-H
def test_a_keyword_introducing_nothing_is_admitted_and_reported(parse_code):
    """An empty declaration is recognised, not silently folded into remainder."""
    results, tx = parse_code("# Implements:\ndef f():\n    return 1\n")
    assert not _all_refs((results, tx))
    assert len(tx.faults) == 1
    ref_item, line_num, keyword = tx.faults[0]
    assert line_num == 1
    assert keyword == "implements"
    assert FaultCode.EMPTY_REFERENCE_LIST in ref_item.codes


# Verifies: REQ-d00269-H
def test_a_trailing_separator_continues_onto_the_next_comment_line(parse_code):
    result = parse_code(
        "# Implements: REQ-d00001,\n" "#             REQ-d00002\n" "def f():\n    return 1\n"
    )
    refs = _all_refs(result)
    assert "REQ-d00001" in refs
    assert "REQ-d00002" in refs


# Verifies: REQ-d00269-H
def test_a_separator_with_nothing_to_continue_onto_binds_what_precedes_it(parse_code):
    result = parse_code("# Implements: REQ-d00001,\ndef f():\n    return 1\n")
    assert "REQ-d00001" in _all_refs(result)


# Verifies: REQ-d00269-H
def test_a_continuation_without_a_separator_is_an_orphan(parse_code):
    """No separator means line 1 is a complete list and line 2 stands alone."""
    result = parse_code(
        "# Implements: REQ-d00001\n" "#             REQ-d00002\n" "def f():\n    return 1\n"
    )
    refs = _all_refs(result)
    assert "REQ-d00001" in refs
    assert "REQ-d00002" not in refs


# Verifies: REQ-d00269-H, REQ-p00019-A
def test_an_orphan_reference_line_is_never_silent(parse_code):
    """The standing defect: this produced no node, no remainder, no diagnostic.

    ``REQ-d00272-H`` is a keyword introducing no content -- a different
    defect from this one, which is a bare identifier line with no keyword
    above it at all -- so the fault this line raises is cited to
    REQ-d00269-H (the continuation rule that defines the orphan category)
    and REQ-p00019-A (the never-silent obligation), not to REQ-d00272-H.
    """
    result = parse_code("def f():\n    #   REQ-d00001\n    return 1\n")
    assert _diagnostics(result), "an orphan reference must be reported"
