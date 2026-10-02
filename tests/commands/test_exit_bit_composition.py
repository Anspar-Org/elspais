# Verifies: REQ-d00085
"""Tests for bitfield exit code composition."""

from elspais.commands.report import EXIT_BIT


class TestExitBitAllocation:
    def test_bits_dont_overlap(self) -> None:
        """Verify no two command names share the same bit value."""
        # The gap listings are one report narrowed five ways and share a bit.
        gap_family = {"uncovered", "untested", "unvalidated", "failing", "gaps"}
        assert len({EXIT_BIT[name] for name in gap_family}) == 1
        seen: dict[int, str] = {}
        for name, bit in EXIT_BIT.items():
            assert bit > 0 and bit & (bit - 1) == 0, f"{name}'s bit {bit} is not one bit"
            owner = "gaps" if name in gap_family else name
            assert seen.get(bit, owner) == owner, f"{name} and {seen[bit]} share bit {bit}"
            seen[bit] = owner

    # Verifies: REQ-d00085-C, REQ-d00272-P
    def test_every_composable_graph_section_has_a_bit(self) -> None:
        """A composed section without a bit would fail silently: its failure
        sets nothing in the exit code."""
        from elspais.commands.report import COMPOSABLE_SECTIONS

        for name in COMPOSABLE_SECTIONS:
            assert name in EXIT_BIT, f"{name} has no exit bit"
        assert EXIT_BIT["unresolved"] != EXIT_BIT["malformed"]

    def test_or_composition(self) -> None:
        """Verify bitfield composition works correctly."""
        result = EXIT_BIT["checks"] | EXIT_BIT["gaps"]
        assert result & EXIT_BIT["checks"]
        assert result & EXIT_BIT["gaps"]
        assert not (result & EXIT_BIT["summary"])
