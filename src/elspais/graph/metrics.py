"""Coverage metrics data structures.

This module defines the data structures for centralized coverage tracking:
- CoverageSource: Enum indicating where coverage originated
- CoverageContribution: A single coverage claim on an assertion
- RollupMetrics: Aggregated metrics for a requirement node
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CoverageSource(Enum):
    """Source type for coverage contributions.

    Different sources have different confidence levels:
    - DIRECT: High confidence - TEST validates or CODE implements assertion
    - EXPLICIT: High confidence - REQ implements specific assertion(s) via syntax
    - INFERRED: Review recommended - REQ implements parent REQ (claims all assertions)
    """

    DIRECT = "direct"  # TEST/CODE validates/implements assertion
    EXPLICIT = "explicit"  # REQ implements specific assertions (e.g., REQ-100-A-B)
    INFERRED = "inferred"  # REQ implements parent REQ (all assertions implied)


@dataclass
class CoverageContribution:
    """A single coverage contribution to an assertion.

    Tracks which node claims to cover an assertion and how.

    Attributes:
        source_id: ID of the node providing coverage (TEST, CODE, or REQ)
        source_type: How the coverage was determined
        assertion_label: The assertion label being covered (e.g., "A", "B")
    """

    source_id: str
    source_type: CoverageSource
    assertion_label: str


@dataclass
class RollupMetrics:
    """Aggregated coverage metrics for a requirement.

    Computed once during graph annotation and stored in node._metrics.
    Provides both aggregate counts and per-assertion detail.

    Attributes:
        total_assertions: Number of assertions in this requirement
        covered_assertions: Number with at least one coverage contributor
        direct_covered: Assertions covered by TEST or CODE nodes
        explicit_covered: Assertions covered by REQ with assertion syntax
        inferred_covered: Assertions covered by REQ without assertion syntax
        coverage_pct: Percentage of assertions covered (0-100)
        assertion_coverage: Map of assertion label to coverage contributors
        direct_tested: Assertions covered specifically by TEST nodes
        validated: Assertions with passing TEST_RESULTs
        has_failures: True if any TEST_RESULT is failed/error
    """

    total_assertions: int = 0
    covered_assertions: int = 0
    direct_covered: int = 0
    explicit_covered: int = 0
    inferred_covered: int = 0
    coverage_pct: float = 0.0
    assertion_coverage: dict[str, list[CoverageContribution]] = field(default_factory=dict)
    # Test-specific metrics
    direct_tested: int = 0  # Assertions with TEST coverage (not CODE)
    validated: int = 0  # Assertions with passing TEST_RESULTs
    has_failures: bool = False  # Any TEST_RESULT failed?

    def add_contribution(self, contribution: CoverageContribution) -> None:
        """Add a coverage contribution for an assertion.

        Args:
            contribution: The coverage contribution to add.
        """
        label = contribution.assertion_label
        if label not in self.assertion_coverage:
            self.assertion_coverage[label] = []
        self.assertion_coverage[label].append(contribution)

    def finalize(self) -> None:
        """Compute aggregate counts after all contributions are added.

        Call this after adding all contributions to update the aggregate
        counts (covered_assertions, direct_covered, etc.) and coverage_pct.
        """
        if self.total_assertions == 0:
            return

        # Track unique assertions by coverage source type
        direct_labels: set[str] = set()
        explicit_labels: set[str] = set()
        inferred_labels: set[str] = set()

        for label, contributions in self.assertion_coverage.items():
            for contrib in contributions:
                if contrib.source_type == CoverageSource.DIRECT:
                    direct_labels.add(label)
                elif contrib.source_type == CoverageSource.EXPLICIT:
                    explicit_labels.add(label)
                elif contrib.source_type == CoverageSource.INFERRED:
                    inferred_labels.add(label)

        # Count assertions with any coverage
        all_covered = direct_labels | explicit_labels | inferred_labels
        self.covered_assertions = len(all_covered)
        self.direct_covered = len(direct_labels)
        self.explicit_covered = len(explicit_labels)
        self.inferred_covered = len(inferred_labels)

        # Compute percentage
        self.coverage_pct = (self.covered_assertions / self.total_assertions) * 100


__all__ = [
    "CoverageSource",
    "CoverageContribution",
    "RollupMetrics",
]
