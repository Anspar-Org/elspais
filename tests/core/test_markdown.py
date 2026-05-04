# Validates REQ-d00246-A
"""Tests for strip_emphasis() in elspais.utilities.markdown.

Validates REQ-d00246-A: The codebase provides a strip_emphasis(s: str) -> str
utility in utilities/markdown.py that strips balanced pairs of `**`, `__`, `*`,
and `_` from the start and end of `s`, in order of width (widest first). Outer
whitespace is trimmed. Unbalanced wrappers leave the string intact. The function
is idempotent.
"""

from elspais.utilities.markdown import strip_emphasis


class TestStripEmphasisBalanced:
    """Validates REQ-d00246-A: balanced emphasis wrappers are stripped."""

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_strips_double_asterisks(self) -> None:
        assert strip_emphasis("**Foo**") == "Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_strips_double_underscores(self) -> None:
        assert strip_emphasis("__Foo__") == "Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_strips_single_asterisks(self) -> None:
        assert strip_emphasis("*Foo*") == "Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_strips_single_underscores(self) -> None:
        assert strip_emphasis("_Foo_") == "Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_strips_triple_asterisks(self) -> None:
        # *** = ** + *, both balanced
        assert strip_emphasis("***Foo***") == "Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_strips_quadruple_asterisks(self) -> None:
        # **** = two ** pairs
        assert strip_emphasis("****Foo****") == "Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_strips_octuple_asterisks(self) -> None:
        # The glossary-pollution pattern from Bug 2.
        assert strip_emphasis("********Foo********") == "Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_strips_nested_mixed_wrappers(self) -> None:
        assert strip_emphasis("**__Foo__**") == "Foo"


class TestStripEmphasisUnbalanced:
    """Validates REQ-d00246-A: unbalanced wrappers leave the string intact."""

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_unbalanced_mismatched_marker_types(self) -> None:
        assert strip_emphasis("*Foo_") == "*Foo_"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_unbalanced_only_left_double(self) -> None:
        assert strip_emphasis("**Foo") == "**Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_unbalanced_only_right_double(self) -> None:
        assert strip_emphasis("Foo**") == "Foo**"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_unbalanced_only_left_triple(self) -> None:
        assert strip_emphasis("***Foo") == "***Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_unbalanced_asymmetric_widths(self) -> None:
        # Left * doesn't pair with right **.
        assert strip_emphasis("*Foo**") == "*Foo**"


class TestStripEmphasisEdgeCases:
    """Validates REQ-d00246-A: edge cases for empty, whitespace, plain, and unicode inputs."""

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_empty_string(self) -> None:
        assert strip_emphasis("") == ""

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_whitespace_only_trimmed(self) -> None:
        assert strip_emphasis("   ") == ""

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_plain_text_unchanged(self) -> None:
        assert strip_emphasis("Foo") == "Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_outer_whitespace_trimmed_around_wrappers(self) -> None:
        assert strip_emphasis("  **Foo**  ") == "Foo"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_internal_emphasis_untouched(self) -> None:
        # No boundary match -- internal markers are preserved.
        assert strip_emphasis("plain *italic* text") == "plain *italic* text"

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_only_emphasis_markers_double(self) -> None:
        # Balanced empty wrappers collapse to empty string.
        assert strip_emphasis("**") == ""

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_only_emphasis_markers_quadruple(self) -> None:
        assert strip_emphasis("****") == ""

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_unicode_content(self) -> None:
        assert strip_emphasis("**café**") == "café"


class TestStripEmphasisIdempotent:
    """Validates REQ-d00246-A: strip_emphasis is idempotent across the matrix."""

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_idempotent_double_asterisks(self) -> None:
        first = strip_emphasis("**Foo**")
        assert strip_emphasis(first) == first

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_idempotent_triple_asterisks(self) -> None:
        first = strip_emphasis("***Foo***")
        assert strip_emphasis(first) == first

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_idempotent_octuple_asterisks(self) -> None:
        first = strip_emphasis("********Foo********")
        assert strip_emphasis(first) == first

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_idempotent_nested_mixed(self) -> None:
        first = strip_emphasis("**__Foo__**")
        assert strip_emphasis(first) == first

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_idempotent_unbalanced_unchanged(self) -> None:
        first = strip_emphasis("*Foo**")
        assert strip_emphasis(first) == first

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_idempotent_outer_whitespace(self) -> None:
        first = strip_emphasis("  **Foo**  ")
        assert strip_emphasis(first) == first

    # Implements: REQ-d00246-A
    def test_REQ_d00246_A_idempotent_plain_text(self) -> None:
        first = strip_emphasis("Foo")
        assert strip_emphasis(first) == first
