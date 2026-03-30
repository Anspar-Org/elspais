# Verifies: REQ-d00085
"""Tests for bitfield exit code composition."""
from elspais.commands.report import EXIT_BIT


class TestExitBitAllocation:
    def test_bits_dont_overlap(self) -> None:
        """Verify no two command names share the same bit value."""
        seen = set()
        for name in ("checks", "summary", "trace", "changed"):
            bit = EXIT_BIT[name]
            assert bit not in seen, f"Duplicate bit for {name}"
            seen.add(bit)

    def test_or_composition(self) -> None:
        """Verify bitfield composition works correctly."""
        result = EXIT_BIT["checks"] | EXIT_BIT["gaps"]
        assert result & EXIT_BIT["checks"]
        assert result & EXIT_BIT["gaps"]
        assert not (result & EXIT_BIT["summary"])
