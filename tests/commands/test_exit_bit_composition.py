# Verifies: REQ-d00085
"""Tests for bitfield exit code composition."""
from elspais.commands.report import EXIT_BIT


class TestExitBitAllocation:
    def test_checks_is_bit_0(self) -> None:
        assert EXIT_BIT["checks"] == 1

    def test_summary_is_bit_1(self) -> None:
        assert EXIT_BIT["summary"] == 2

    def test_trace_is_bit_2(self) -> None:
        assert EXIT_BIT["trace"] == 4

    def test_changed_is_bit_3(self) -> None:
        assert EXIT_BIT["changed"] == 8

    def test_gap_sections_share_bit_4(self) -> None:
        for name in ("uncovered", "untested", "unvalidated", "failing", "gaps"):
            assert EXIT_BIT[name] == 16

    def test_bits_dont_overlap(self) -> None:
        seen = set()
        for name in ("checks", "summary", "trace", "changed"):
            bit = EXIT_BIT[name]
            assert bit not in seen
            seen.add(bit)

    def test_or_composition(self) -> None:
        result = EXIT_BIT["checks"] | EXIT_BIT["gaps"]
        assert result == 17
        assert result & EXIT_BIT["checks"]
        assert result & EXIT_BIT["gaps"]
        assert not (result & EXIT_BIT["summary"])
