# Implements: REQ-d00069-A, REQ-d00069-C
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
    - DIRECT: High confidence - TEST verifies or CODE implements assertion
    - EXPLICIT: High confidence - REQ implements specific assertion(s) via syntax
    - INFERRED: Review recommended - REQ implements parent REQ (claims all assertions)
    - INDIRECT: TEST verifies whole REQ (all assertions implied)
    - UAT_EXPLICIT: JNY names specific assertion (Validates: REQ-xxx-A)
    - UAT_INFERRED: JNY names whole REQ (Validates: REQ-xxx), all assertions implied
    """

    DIRECT = "direct"  # TEST/CODE verifies/implements assertion
    EXPLICIT = "explicit"  # REQ implements specific assertions (e.g., REQ-100-A-B)
    INFERRED = "inferred"  # REQ implements parent REQ (all assertions implied)
    INDIRECT = "indirect"  # TEST verifies whole REQ (all assertions implied)
    UAT_EXPLICIT = "uat_explicit"  # JNY names specific assertion (Validates: REQ-xxx-A)
    UAT_INFERRED = (
        "uat_inferred"  # JNY names whole REQ (Validates: REQ-xxx), all assertions implied
    )


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
        referenced_pct: Percentage of assertions referenced by code/tests (0-100)
        assertion_coverage: Map of assertion label to coverage contributors
        direct_tested: Assertions covered specifically by TEST nodes
        validated: Assertions with passing RESULTs
        has_failures: True if any RESULT is failed/error
        uat_covered: Assertions with any UAT (JNY Validates) contribution
        uat_direct_covered: Assertions explicitly named in Validates:
        uat_inferred_covered: Assertions implied by whole-REQ Validates:
        uat_referenced_pct: uat_covered / total_assertions * 100
        uat_validated: Assertions covered by passing RESULT nodes via JNY
        uat_has_failures: True if any JNY-linked RESULT is failed/error
        uat_validated_pct: uat_validated / total_assertions * 100
    """

    total_assertions: int = 0
    covered_assertions: int = 0
    direct_covered: int = 0
    explicit_covered: int = 0
    inferred_covered: int = 0
    referenced_pct: float = 0.0
    assertion_coverage: dict[str, list[CoverageContribution]] = field(default_factory=dict)
    # Test-specific metrics
    direct_tested: int = 0  # Assertions with TEST coverage (not CODE)
    validated: int = 0  # Assertions with passing RESULTs
    has_failures: bool = False  # Any RESULT failed?
    # Indirect coverage metrics (whole-req tests covering all assertions)
    indirect_referenced_pct: float = 0.0  # Coverage % including INDIRECT source
    validated_with_indirect: int = 0  # Assertions validated when including indirect
    # UAT coverage (JNY Validates)
    uat_covered: int = 0  # assertions with any UAT contribution (union, for pct)
    uat_direct_covered: int = 0  # assertions explicitly named in Validates:
    uat_inferred_covered: int = 0  # assertions implied by whole-REQ Validates:
    uat_referenced_pct: float = 0.0  # uat_covered / total_assertions * 100
    uat_validated: int = 0  # assertions covered by passing RESULT nodes via JNY
    uat_has_failures: bool = False  # any JNY-linked RESULT is failed/error
    uat_validated_pct: float = 0.0  # uat_validated / total_assertions * 100 (fractional)

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
        counts (covered_assertions, direct_covered, etc.) and referenced_pct.
        """
        if self.total_assertions == 0:
            return

        # Track unique assertions by coverage source type
        direct_labels: set[str] = set()
        explicit_labels: set[str] = set()
        inferred_labels: set[str] = set()
        indirect_labels: set[str] = set()
        uat_explicit_labels: set[str] = set()
        uat_inferred_labels: set[str] = set()

        for label, contributions in self.assertion_coverage.items():
            for contrib in contributions:
                if contrib.source_type == CoverageSource.DIRECT:
                    direct_labels.add(label)
                elif contrib.source_type == CoverageSource.EXPLICIT:
                    explicit_labels.add(label)
                elif contrib.source_type == CoverageSource.INFERRED:
                    inferred_labels.add(label)
                elif contrib.source_type == CoverageSource.INDIRECT:
                    indirect_labels.add(label)
                elif contrib.source_type == CoverageSource.UAT_EXPLICIT:
                    uat_explicit_labels.add(label)
                elif contrib.source_type == CoverageSource.UAT_INFERRED:
                    uat_inferred_labels.add(label)

        # Count assertions with any coverage (strict: excludes INDIRECT)
        all_covered = direct_labels | explicit_labels | inferred_labels
        self.covered_assertions = len(all_covered)
        self.direct_covered = len(direct_labels)
        self.explicit_covered = len(explicit_labels)
        self.inferred_covered = len(inferred_labels)

        # Compute strict percentage (excludes INDIRECT)
        self.referenced_pct = (self.covered_assertions / self.total_assertions) * 100

        # Compute indirect percentage (includes INDIRECT)
        all_covered_with_indirect = all_covered | indirect_labels
        self.indirect_referenced_pct = (
            len(all_covered_with_indirect) / self.total_assertions
        ) * 100

        # Compute UAT coverage (JNY Validates)
        uat_all = uat_explicit_labels | uat_inferred_labels
        self.uat_covered = len(uat_all)
        self.uat_direct_covered = len(uat_explicit_labels)
        self.uat_inferred_covered = len(uat_inferred_labels)
        self.uat_referenced_pct = (self.uat_covered / self.total_assertions) * 100


__all__ = [
    "CoverageSource",
    "CoverageContribution",
    "RollupMetrics",
]
