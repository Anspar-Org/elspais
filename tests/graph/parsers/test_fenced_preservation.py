# Validates REQ-d00247-A
"""Tests for fenced-code-block preservation across the lark spec parse-render path.

These tests pin the post-fix behavior of the lark spec dispatcher
(`FileDispatcher.dispatch_spec` / `RequirementTransformer.transform`) at the
intersection of fenced-code preprocessing and REMAINDER text capture.

The pipeline preprocesses spec content with `_neutralize_fenced_blocks()`,
which replaces non-blank lines inside ``` ``` ``` fences with the literal
placeholder `<!-- fenced -->`. That placeholder is meant to be ephemeral --
parser input only -- so the grammar does not mistake fenced examples for
real requirement/journey syntax.

The bug: the same neutralized buffer is currently passed both to the parser
AND to `transformer.transform(tree, source=...)`. The transformer's REMAINDER
nodes capture text from `source` (token text and `_source_lines`), so the
literal `<!-- fenced -->` ends up in REMAINDER `raw_text` and is persisted to
disk on render. Round-trip = silent corruption.

The fix: capture the original (un-preprocessed) content before neutralization
and pass the original to `transformer.transform()` as `source`, so REMAINDER
nodes capture the original verbatim text.

These tests are expected to FAIL until that fix is applied. The final
project-wide grep test (TestProjectSpecRegression) is expected to PASS today
because elspais's own self-spec contains no fenced REMAINDER content -- it
guards against the post-fix invariant being broken by future regressions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.parsers.lark import FileDispatcher, GrammarFactory
from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer
from elspais.utilities.patterns import IdPatternConfig, IdResolver


@pytest.fixture
def resolver() -> IdResolver:
    """IdResolver for standard HHT-like pattern."""
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


def _parse(content: str, resolver: IdResolver) -> list:
    """Run the production Lark spec dispatch path against `content`.

    Uses FileDispatcher.dispatch_spec() rather than the bare transformer so
    we exercise the same `_neutralize_fenced_blocks` -> parse -> transform
    flow that runs in `elspais fix` and cause the round-trip corruption.
    """
    dispatcher = FileDispatcher(resolver)
    return dispatcher.dispatch_spec(content)


def _parse_via_transformer(content: str, resolver: IdResolver) -> list:
    """Bare-transformer parse path (no neutralization) -- baseline regression."""
    factory = GrammarFactory(resolver)
    parser = factory.get_requirement_parser()
    transformer = RequirementTransformer(resolver)
    if not content.endswith("\n"):
        content += "\n"
    tree = parser.parse(content)
    return transformer.transform(tree, source=content)


def _remainder_texts(results: list) -> list[str]:
    """Collect all REMAINDER raw_text strings from a parse result."""
    return [r.raw_text for r in results if r.content_type == "remainder"]


def _all_remainder_text(results: list) -> str:
    """Concatenate every REMAINDER raw_text into one string for membership checks."""
    return "\n".join(_remainder_texts(results))


# ---------------------------------------------------------------------------
# 1. Basic fenced preservation (REQ + REMAINDER with a Python fence).
# ---------------------------------------------------------------------------


_BASIC_FENCED_SPEC = (
    "# REQ-p00001: Fence Preservation Test\n"
    "**Level**: PRD | **Status**: Active\n"
    "\n"
    "## Assertions\n"
    "\n"
    "A. The system SHALL do something.\n"
    "\n"
    "*End* *REQ-p00001* | **Hash**: TODO\n"
    "\n"
    "Some prose.\n"
    "\n"
    "```python\n"
    "def hello():\n"
    '    print("**not bold**")\n'
    "    return `code`\n"
    "```\n"
    "\n"
    "More prose.\n"
)


class TestBasicFencePreservation:
    """Validates REQ-d00247-A: triple-backtick fence content is preserved verbatim."""

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_python_fence_content_preserved(self, resolver: IdResolver) -> None:
        """Fenced Python source must round-trip through REMAINDER unchanged."""
        results = _parse(_BASIC_FENCED_SPEC, resolver)
        all_text = _all_remainder_text(results)
        assert "def hello():" in all_text, (
            f"Fenced 'def hello():' line lost from REMAINDER raw_text. "
            f"REMAINDER blocks: {_remainder_texts(results)!r}"
        )
        assert "**not bold**" in all_text, (
            f"Fenced '**not bold**' string lost from REMAINDER raw_text. "
            f"REMAINDER blocks: {_remainder_texts(results)!r}"
        )
        assert "`code`" in all_text, (
            f"Fenced inline-backtick `code` lost from REMAINDER raw_text. "
            f"REMAINDER blocks: {_remainder_texts(results)!r}"
        )

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_neutralization_placeholder_not_in_remainder(
        self, resolver: IdResolver
    ) -> None:
        """The literal `<!-- fenced -->` must NOT appear in any REMAINDER raw_text."""
        results = _parse(_BASIC_FENCED_SPEC, resolver)
        for r in results:
            if r.content_type != "remainder":
                continue
            assert "<!-- fenced -->" not in r.raw_text, (
                f"Neutralization placeholder leaked into REMAINDER raw_text "
                f"(lines {r.start_line}-{r.end_line}): {r.raw_text!r}"
            )


# ---------------------------------------------------------------------------
# 2. Multiple fence marker styles.
# ---------------------------------------------------------------------------


class TestMultipleFenceMarkers:
    """Validates REQ-d00247-A: backtick and tilde fences both preserve content.

    NOTE: `_neutralize_fenced_blocks` currently only recognizes ``` fences.
    Tilde fences (~~~) are NOT neutralized today, so their content reaches the
    parser literally. The expectation is still that any content inside a fence
    -- regardless of marker style -- is preserved verbatim in REMAINDER.
    """

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_backtick_fence_preserves_content(self, resolver: IdResolver) -> None:
        spec = (
            "# REQ-p00001: Backtick Fence\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do something.\n"
            "\n"
            "*End* *REQ-p00001* | **Hash**: TODO\n"
            "\n"
            "```\n"
            "BACKTICK_PAYLOAD_LINE_1\n"
            "BACKTICK_PAYLOAD_LINE_2\n"
            "```\n"
        )
        results = _parse(spec, resolver)
        all_text = _all_remainder_text(results)
        assert (
            "BACKTICK_PAYLOAD_LINE_1" in all_text
        ), f"Backtick-fence payload line 1 lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "BACKTICK_PAYLOAD_LINE_2" in all_text
        ), f"Backtick-fence payload line 2 lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "<!-- fenced -->" not in all_text
        ), f"Neutralization placeholder leaked. REMAINDERs: {_remainder_texts(results)!r}"

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_tilde_fence_preserves_content(self, resolver: IdResolver) -> None:
        spec = (
            "# REQ-p00001: Tilde Fence\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do something.\n"
            "\n"
            "*End* *REQ-p00001* | **Hash**: TODO\n"
            "\n"
            "~~~\n"
            "TILDE_PAYLOAD_LINE_1\n"
            "TILDE_PAYLOAD_LINE_2\n"
            "~~~\n"
        )
        results = _parse(spec, resolver)
        all_text = _all_remainder_text(results)
        assert (
            "TILDE_PAYLOAD_LINE_1" in all_text
        ), f"Tilde-fence payload line 1 lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "TILDE_PAYLOAD_LINE_2" in all_text
        ), f"Tilde-fence payload line 2 lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "<!-- fenced -->" not in all_text
        ), f"Neutralization placeholder leaked. REMAINDERs: {_remainder_texts(results)!r}"


# ---------------------------------------------------------------------------
# 3. Fence containing REQ-like example syntax.
# ---------------------------------------------------------------------------


_FENCE_WITH_REQ_EXAMPLE = (
    "# REQ-p00001: Real Requirement\n"
    "**Level**: PRD | **Status**: Active\n"
    "\n"
    "## Assertions\n"
    "\n"
    "A. The system SHALL be the only real REQ here.\n"
    "\n"
    "*End* *REQ-p00001* | **Hash**: TODO\n"
    "\n"
    "Documentation that shows an example REQ in a fence:\n"
    "\n"
    "```\n"
    "# REQ-p99999: Example Requirement (illustration only)\n"
    "**Level**: PRD | **Status**: Active\n"
    "\n"
    "## Assertions\n"
    "\n"
    "A. This is example text inside a fence and SHALL NOT be parsed.\n"
    "\n"
    "*End* *REQ-p99999* | **Hash**: TODO\n"
    "```\n"
)


class TestFenceWithRequirementExample:
    """Validates REQ-d00247-A: fence example REQ syntax neither parses nor corrupts.

    Two halves of the contract:
      (a) Neutralization succeeds: the fenced REQ-p99999 example does NOT get
          parsed as a real requirement. (Without neutralization the lark grammar
          would happily match it, polluting the requirements set.)
      (b) The literal example text is still preserved verbatim in REMAINDER --
          because the `source` parameter the transformer reads from must be
          the original content, not the neutralized buffer.
    """

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_fenced_example_req_not_parsed_as_requirement(
        self, resolver: IdResolver
    ) -> None:
        results = _parse(_FENCE_WITH_REQ_EXAMPLE, resolver)
        req_ids: list[str] = []
        for r in results:
            if r.content_type == "requirement":
                req_id = r.parsed_data.get("id") or r.parsed_data.get("requirement_id")
                if req_id:
                    req_ids.append(req_id)
        assert "REQ-p99999" not in req_ids, (
            f"Fenced example 'REQ-p99999' was parsed as a real requirement -- "
            f"neutralization is broken. Found requirement IDs: {req_ids!r}"
        )
        # Sanity: the real requirement IS parsed.
        assert (
            "REQ-p00001" in req_ids
        ), f"Real requirement 'REQ-p00001' was not parsed. Found IDs: {req_ids!r}"

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_fenced_example_req_text_preserved_in_remainder(
        self, resolver: IdResolver
    ) -> None:
        results = _parse(_FENCE_WITH_REQ_EXAMPLE, resolver)
        all_text = _all_remainder_text(results)
        assert "# REQ-p99999: Example Requirement (illustration only)" in all_text, (
            f"Fenced example REQ header lost from REMAINDER raw_text. "
            f"REMAINDER blocks: {_remainder_texts(results)!r}"
        )
        assert "*End* *REQ-p99999* | **Hash**: TODO" in all_text, (
            f"Fenced example *End* marker lost from REMAINDER raw_text. "
            f"REMAINDER blocks: {_remainder_texts(results)!r}"
        )
        assert "<!-- fenced -->" not in all_text, (
            f"Neutralization placeholder leaked into REMAINDER. "
            f"REMAINDER blocks: {_remainder_texts(results)!r}"
        )


# ---------------------------------------------------------------------------
# 4. Blank lines inside a fence are preserved.
# ---------------------------------------------------------------------------


class TestBlankLinesInFence:
    """Validates REQ-d00247-A: blank lines inside a fence pass through verbatim."""

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_blank_lines_in_fence_preserved(self, resolver: IdResolver) -> None:
        # Construct a fence with a deliberate blank line in the middle.
        spec = (
            "# REQ-p00001: Blank Lines In Fence\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do something.\n"
            "\n"
            "*End* *REQ-p00001* | **Hash**: TODO\n"
            "\n"
            "```\n"
            "FENCE_LINE_BEFORE_BLANK\n"
            "\n"
            "FENCE_LINE_AFTER_BLANK\n"
            "```\n"
        )
        results = _parse(spec, resolver)
        all_text = _all_remainder_text(results)
        assert (
            "FENCE_LINE_BEFORE_BLANK" in all_text
        ), f"Pre-blank fence line lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "FENCE_LINE_AFTER_BLANK" in all_text
        ), f"Post-blank fence line lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "<!-- fenced -->" not in all_text
        ), f"Neutralization placeholder leaked. REMAINDERs: {_remainder_texts(results)!r}"
        # The original three fence-content lines (non-blank, blank, non-blank)
        # must appear together across the joined REMAINDER stream as the
        # original literal text. (Blank lines may legitimately split the
        # content across separate REMAINDER blocks; what matters for round-
        # trip preservation is the joined sequence.)
        original_fence_payload = "FENCE_LINE_BEFORE_BLANK\n\nFENCE_LINE_AFTER_BLANK"
        assert original_fence_payload in all_text, (
            f"Blank-line-preserving fence payload not found in joined REMAINDER "
            f"stream. REMAINDERs: {_remainder_texts(results)!r}"
        )


# ---------------------------------------------------------------------------
# 5. CRLF line endings.
# ---------------------------------------------------------------------------


class TestCrlfLineEndings:
    """Validates REQ-d00247-A: CRLF input round-trips through REMAINDER faithfully.

    `_neutralize_fenced_blocks` splits/joins on `\\n`, leaving any `\\r` at the
    end of each line intact. The original-source path therefore should also
    retain those `\\r` characters in REMAINDER raw_text.
    """

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_crlf_fence_content_preserved(self, resolver: IdResolver) -> None:
        # Mixed-line-ending input: LF for the requirement portion (so the
        # grammar parses cleanly), CRLF for the fence content. This isolates
        # the source-capture path: `_neutralize_fenced_blocks` splits/joins on
        # '\n' only, so the trailing '\r' on each fence line is retained in
        # the source string. After the fix passes the *original* content as
        # `source`, the REMAINDER raw_text must contain the original CRLF
        # bytes verbatim.
        prefix = (
            "# REQ-p00001: CRLF Test\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do something.\n"
            "\n"
            "*End* *REQ-p00001* | **Hash**: TODO\n"
            "\n"
        )
        fence_block_crlf = "```\r\nCRLF_FENCE_PAYLOAD\r\n```\r\n"
        spec = prefix + fence_block_crlf
        results = _parse(spec, resolver)
        all_text = _all_remainder_text(results)
        assert (
            "CRLF_FENCE_PAYLOAD" in all_text
        ), f"CRLF fence payload lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "<!-- fenced -->" not in all_text
        ), f"Neutralization placeholder leaked. REMAINDERs: {_remainder_texts(results)!r}"
        # The trailing `\r` from the original CRLF line should still be present
        # somewhere in REMAINDER raw_text -- it is part of the original source.
        assert "CRLF_FENCE_PAYLOAD\r" in all_text, (
            f"Trailing '\\r' from CRLF source lost on REMAINDER capture. "
            f"REMAINDERs: {_remainder_texts(results)!r}"
        )


# ---------------------------------------------------------------------------
# 6. Unclosed fence at EOF.
# ---------------------------------------------------------------------------


class TestUnclosedFence:
    """Validates REQ-d00247-A: an unclosed fence still preserves its content."""

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_unclosed_fence_content_preserved(self, resolver: IdResolver) -> None:
        spec = (
            "# REQ-p00001: Unclosed Fence\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do something.\n"
            "\n"
            "*End* *REQ-p00001* | **Hash**: TODO\n"
            "\n"
            "Documentation with an unclosed fence:\n"
            "\n"
            "```\n"
            "UNCLOSED_FENCE_PAYLOAD_LINE_1\n"
            "UNCLOSED_FENCE_PAYLOAD_LINE_2\n"
        )
        # Parse should succeed (no exception).
        results = _parse(spec, resolver)
        all_text = _all_remainder_text(results)
        assert (
            "UNCLOSED_FENCE_PAYLOAD_LINE_1" in all_text
        ), f"Unclosed-fence payload line 1 lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "UNCLOSED_FENCE_PAYLOAD_LINE_2" in all_text
        ), f"Unclosed-fence payload line 2 lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "<!-- fenced -->" not in all_text
        ), f"Neutralization placeholder leaked. REMAINDERs: {_remainder_texts(results)!r}"


# ---------------------------------------------------------------------------
# 7. Baseline: spec without any fences.
# ---------------------------------------------------------------------------


class TestNoFenceBaseline:
    """Validates REQ-d00247-A: the no-fence path remains intact (regression guard).

    Sanity check that the post-fix transformer still captures plain REMAINDER
    content correctly when there are no fences anywhere in the file.
    """

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_no_fence_remainder_preserved(self, resolver: IdResolver) -> None:
        spec = (
            "# REQ-p00001: Plain Spec\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do something.\n"
            "\n"
            "*End* *REQ-p00001* | **Hash**: TODO\n"
            "\n"
            "PLAIN_REMAINDER_PAYLOAD line one.\n"
            "PLAIN_REMAINDER_PAYLOAD line two.\n"
        )
        results = _parse(spec, resolver)
        all_text = _all_remainder_text(results)
        assert (
            "PLAIN_REMAINDER_PAYLOAD line one." in all_text
        ), f"Plain REMAINDER line 1 lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert (
            "PLAIN_REMAINDER_PAYLOAD line two." in all_text
        ), f"Plain REMAINDER line 2 lost. REMAINDERs: {_remainder_texts(results)!r}"
        assert "<!-- fenced -->" not in all_text, (
            f"Neutralization placeholder somehow appeared in fence-free spec. "
            f"REMAINDERs: {_remainder_texts(results)!r}"
        )


# ---------------------------------------------------------------------------
# 8. Project-wide invariant: no `<!-- fenced -->` literal in spec/.
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_DIR = _REPO_ROOT / "spec"


class TestProjectSpecRegression:
    """Validates REQ-d00247-A: no spec file under `spec/` carries `<!-- fenced -->`.

    Post-fix invariant: if the bug ever reappears (e.g. neutralized buffer
    re-routed into REMAINDER, then `elspais fix` round-trips a fenced spec)
    the placeholder will be persisted to disk. This scan catches that.

    Today this test is expected to PASS because elspais's own self-spec
    contains no fenced REMAINDER content -- the bug is dormant in this repo.
    """

    # Implements: REQ-d00247-A
    def test_REQ_d00247_A_no_neutralization_placeholder_in_spec_files(self) -> None:
        assert _SPEC_DIR.is_dir(), f"spec/ directory not found at {_SPEC_DIR}"
        offenders: list[tuple[Path, list[int]]] = []
        for md_file in _SPEC_DIR.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if "<!-- fenced -->" not in text:
                continue
            line_hits = [
                lineno
                for lineno, line in enumerate(text.splitlines(), start=1)
                if "<!-- fenced -->" in line
            ]
            offenders.append((md_file.relative_to(_REPO_ROOT), line_hits))
        assert not offenders, (
            "Found neutralization placeholder '<!-- fenced -->' persisted in "
            "spec/*.md file(s) -- this indicates the lark spec parser leaked "
            "neutralized fence content into REMAINDER raw_text on a previous "
            f"render_save(). Offenders: {offenders!r}"
        )
