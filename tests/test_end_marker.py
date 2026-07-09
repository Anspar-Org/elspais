# Verifies: REQ-d00131-B, REQ-d00131-E
"""Behavior tests for the unified *End* marker render/parse helpers.

Phase 3 of the DRY cleanup introduces a single render/parse pair for the
``*End*`` footer line that today is constructed inline in render.py /
spec_writer.py / builder.py and parsed by three separate regexes in
hasher.py / spec_writer.py / parsers/lark.

Anchors:

- REQ-d00131-B: REQUIREMENT render includes an ``*End*`` marker with hash.
- REQ-d00131-E: USER_JOURNEY render includes an end marker (no hash).

Contract under test (``elspais.graph.render``):

    @dataclass(frozen=True)
    class EndMarker:
        title: str
        hash_value: str | None

    def render_end_marker(title: str, hash_value: str | None) -> str: ...
    def parse_end_marker(line: str) -> EndMarker | None: ...
"""

from __future__ import annotations

import pytest

from elspais.graph.render import EndMarker, parse_end_marker, render_end_marker

# --------------------------------------------------------------------------- #
# Render: shape, not literal-string equality
# --------------------------------------------------------------------------- #


class TestRenderEndMarker:
    """Anchor: REQ-d00131-B / REQ-d00131-E.

    We assert the rendered line is single-line and structurally contains the
    title and (when present) the hash. We do not assert on the exact glyphs
    used for emphasis -- that's a constant, not behavior.
    """

    @pytest.mark.parametrize(
        "title, hash_value",
        [
            ("REQ-d00001", "abc12345"),
            ("REQ-p00050", "XXXXXXXX"),
            ("Render Protocol for Graph Nodes", "c004c62e"),
        ],
    )
    def test_render_with_hash_contains_title_and_hash(self, title: str, hash_value: str) -> None:
        line = render_end_marker(title, hash_value)
        assert "\n" not in line, "End marker must be a single line"
        assert title in line
        assert hash_value in line
        assert "Hash" in line, "Marker with hash must label the hash field"

    @pytest.mark.parametrize(
        "title",
        ["JNY-checkout-001", "REQ-d00131", "Some Journey With Spaces"],
    )
    def test_render_without_hash_omits_hash_segment(self, title: str) -> None:
        line = render_end_marker(title, None)
        assert "\n" not in line
        assert title in line
        # Journey-style line: no pipe separator and no Hash label.
        assert "|" not in line, "Journey-style end marker must not have a pipe segment"
        assert "Hash" not in line


# --------------------------------------------------------------------------- #
# Round-trip: render then parse yields the original EndMarker
# --------------------------------------------------------------------------- #


class TestRoundTrip:
    """The canonical correctness property: parse(render(x)) == x.

    HASH_VALUE_PATTERN is r"\\S+" so any non-whitespace token (hex,
    placeholder, TODO) must round-trip.
    """

    @pytest.mark.parametrize(
        "title, hash_value",
        [
            ("REQ-d00001", "abc12345"),
            ("REQ-d00131", "c004c62e"),
            ("REQ-p00050", "XXXXXXXX"),
            ("REQ-x", "TODO"),
            ("REQ-y", "________"),
            ("Title With Spaces", "deadbeef"),
            ("JNY-checkout-001", None),
            ("Some Journey", None),
        ],
    )
    def test_render_then_parse_round_trips(self, title: str, hash_value: str | None) -> None:
        rendered = render_end_marker(title, hash_value)
        parsed = parse_end_marker(rendered)
        assert parsed == EndMarker(title=title, hash_value=hash_value)


# --------------------------------------------------------------------------- #
# Parse: positive cases independent of the render side
# --------------------------------------------------------------------------- #


class TestParsePositive:
    def test_parses_title_containing_spaces(self) -> None:
        parsed = parse_end_marker("*End* *Some Title With Spaces* | **Hash**: abc12345")
        assert parsed == EndMarker(title="Some Title With Spaces", hash_value="abc12345")

    def test_journey_style_line_has_none_hash(self) -> None:
        parsed = parse_end_marker("*End* *JNY-checkout-001*")
        assert parsed == EndMarker(title="JNY-checkout-001", hash_value=None)

    @pytest.mark.parametrize("trail", [" ", "  ", "\t", " \t ", "   \t"])
    def test_tolerates_trailing_whitespace(self, trail: str) -> None:
        parsed = parse_end_marker(f"*End* *REQ-d00001* | **Hash**: abc12345{trail}")
        assert parsed == EndMarker(title="REQ-d00001", hash_value="abc12345")


# --------------------------------------------------------------------------- #
# Parse: negative cases
# --------------------------------------------------------------------------- #


class TestParseNegative:
    @pytest.mark.parametrize(
        "line",
        [
            "",
            "## Some header",
            "Just plain text with no markers at all",
            "*End*",  # partial: no title
            "*End* without stars around title",  # missing inner emphasis
            "End* *REQ-x*",  # missing leading asterisk
            "*Start* *REQ-x*",  # wrong sentinel
        ],
    )
    def test_non_end_lines_return_none(self, line: str) -> None:
        assert parse_end_marker(line) is None

    def test_malformed_pipe_without_hash_returns_none(self) -> None:
        # A line that declares a pipe segment but no **Hash**: value is
        # malformed. The Phase-3 implementer is expected to reject it rather
        # than silently coerce to hash_value=None, because update_hash_in_file
        # would otherwise have nothing to overwrite.
        assert parse_end_marker("*End* *REQ-x* |") is None
