# Implements: REQ-d00069-A, REQ-d00069-C
"""Coverage metrics data structures.

This module defines the data structures for centralized coverage tracking:
- CoverageSource: Enum indicating where coverage originated
- CoverageContribution: A single coverage claim on an assertion
- CoverageDimension: Uniform metrics for one coverage dimension
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
class CoverageDimension:
    """Uniform coverage metrics for one dimension.

    Each of the 5 coverage dimensions (implemented, tested, verified,
    uat_covered, uat_verified) uses this same structure.

    Attributes:
        total: Total assertions in the requirement
        direct: Assertions covered by targeted references (assertion-level)
        indirect: Assertions covered when including blanket/whole-req references
        has_failures: True if any result is failed/error (verified dims only)
    """

    total: int = 0
    direct: int = 0
    indirect: int = 0
    has_failures: bool = False

    @property
    def direct_pct(self) -> float:
        """Percentage of assertions with direct coverage."""
        return (self.direct / self.total * 100) if self.total else 0.0

    @property
    def indirect_pct(self) -> float:
        """Percentage of assertions with any coverage (direct + blanket)."""
        return (self.indirect / self.total * 100) if self.total else 0.0

    @property
    def tier(self) -> str:
        """Classify into a tier key for color/severity mapping.

        Returns one of: 'failing', 'full-direct', 'full-indirect',
        'partial', 'none'.
        """
        if self.has_failures:
            return "failing"
        if self.direct >= self.total > 0:
            return "full-direct"
        if self.indirect >= self.total > 0:
            return "full-indirect"
        if self.direct > 0 or self.indirect > 0:
            return "partial"
        return "none"


def _dim(total: int = 0) -> CoverageDimension:
    """Factory helper for default CoverageDimension with total pre-set."""
    return CoverageDimension(total=total)


@dataclass
class RollupMetrics:
    """Aggregated coverage metrics for a requirement.

    Computed once during graph annotation and stored in node._metrics.
    Provides both aggregate counts and per-assertion detail.

    The 6 CoverageDimension instances provide uniform access:
    - implemented: CODE/REQ coverage of assertions
    - tested: TEST nodes exist for assertions
    - verified: TEST results passing for assertions
    - uat_coverage: JNY Validates coverage of assertions
    - uat_verified: JNY results passing for assertions
    - code_tested: Implementation lines covered by tests (total=lines, not assertions)
    """

    total_assertions: int = 0
    assertion_coverage: dict[str, list[CoverageContribution]] = field(default_factory=dict)

    # The 6 uniform coverage dimensions
    implemented: CoverageDimension = field(default_factory=CoverageDimension)
    tested: CoverageDimension = field(default_factory=CoverageDimension)
    verified: CoverageDimension = field(default_factory=CoverageDimension)
    uat_coverage: CoverageDimension = field(default_factory=CoverageDimension)
    uat_verified: CoverageDimension = field(default_factory=CoverageDimension)
    code_tested: CoverageDimension = field(default_factory=CoverageDimension)

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

        Call this after adding all contributions to populate the implemented
        and uat_coverage dimensions from contribution data. The tested,
        verified, and uat_verified dimensions are populated separately by
        populate_test_dimensions() (called from annotate_coverage()).
        """
        if self.total_assertions == 0:
            return

        n = self.total_assertions

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

        # ── Populate dimensions from contribution data ──
        uat_all = uat_explicit_labels | uat_inferred_labels
        # Implemented: direct = assertion-targeted (DIRECT + EXPLICIT),
        #              indirect = all (DIRECT + EXPLICIT + INFERRED)
        impl_direct = direct_labels | explicit_labels
        impl_indirect = impl_direct | inferred_labels
        self.implemented = CoverageDimension(
            total=n,
            direct=len(impl_direct),
            indirect=len(impl_indirect),
        )

        # UAT Coverage: direct = assertion-targeted (UAT_EXPLICIT),
        #               indirect = all (UAT_EXPLICIT + UAT_INFERRED)
        self.uat_coverage = CoverageDimension(
            total=n,
            direct=len(uat_explicit_labels),
            indirect=len(uat_all),
        )

        # tested, verified, uat_verified are populated by annotate_coverage()
        # after this method runs, because they need label-set data from the
        # annotator (tested_labels, validated_labels, etc.)

    def populate_test_dimensions(
        self,
        *,
        tested_direct: int,
        tested_indirect: int,
        verified_direct: int,
        verified_indirect: int,
        verified_failures: bool,
        uat_verified_direct: int,
        uat_verified_indirect: int,
        uat_verified_failures: bool,
    ) -> None:
        """Populate tested, verified, and uat_verified dimensions.

        Called by annotate_coverage() after finalize() with the label-set
        counts from the annotator's tracking variables.
        """
        n = self.total_assertions
        self.tested = CoverageDimension(total=n, direct=tested_direct, indirect=tested_indirect)
        self.verified = CoverageDimension(
            total=n,
            direct=verified_direct,
            indirect=verified_indirect,
            has_failures=verified_failures,
        )
        self.uat_verified = CoverageDimension(
            total=n,
            direct=uat_verified_direct,
            indirect=uat_verified_indirect,
            has_failures=uat_verified_failures,
        )


__all__ = [
    "CoverageDimension",
    "CoverageSource",
    "CoverageContribution",
    "RollupMetrics",
]
