# Implements: REQ-d00069-A, REQ-d00069-C
"""Coverage metrics data structures.

This module defines the data structures for centralized coverage tracking:
- CoverageSource: Enum indicating where coverage originated
- CoverageContribution: A single coverage claim on an assertion
- CoverageDimension: Uniform metrics for one coverage dimension
- RollupMetrics: Aggregated metrics for a requirement node

It also exposes lightweight inherited-coverage query helpers used by the
template / Satisfies pattern (CUR-1353 Phase 5):

- direct_coverage_for(node): count coverage evidence on a node, dispatched
  by NodeKind. For ASSERTIONs, walks the parent REQ's outgoing
  IMPLEMENTS/VERIFIES/VALIDATES edges filtered by ``assertion_targets``.
  For REQUIREMENTs, counts outgoing coverage edges directly. For CODE,
  TEST, FILE, and JOURNEY nodes, counts incoming coverage edges.
- inherited_coverage_for(node): for an INSTANCE node, return the template
  original's direct coverage; for any other node, fall back to direct.
- satisfier_rollup(node): combine a satisfier REQ's own concrete-assertion
  coverage with the inherited coverage from the templates it satisfies.

These helpers are queries over the live graph -- they do not persist any
new metric on the node, so the INSTANCE coverage story stays consistent
with the "instance coverage == template coverage" invariant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.GraphNode import GraphNode


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
    direct_labels: set[str] = field(default_factory=set)
    indirect_labels: set[str] = field(default_factory=set)

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
            direct_labels=set(impl_direct),
            indirect_labels=set(impl_indirect),
        )

        # UAT Coverage: direct = assertion-targeted (UAT_EXPLICIT),
        #               indirect = all (UAT_EXPLICIT + UAT_INFERRED)
        self.uat_coverage = CoverageDimension(
            total=n,
            direct=len(uat_explicit_labels),
            indirect=len(uat_all),
            direct_labels=set(uat_explicit_labels),
            indirect_labels=set(uat_all),
        )

        # tested, verified, uat_verified are populated by annotate_coverage()
        # after this method runs, because they need label-set data from the
        # annotator (tested_labels, validated_labels, etc.)

    def populate_test_dimensions(
        self,
        *,
        tested_direct_labels: set[str],
        tested_indirect_labels: set[str],
        verified_direct_labels: set[str],
        verified_indirect_labels: set[str],
        verified_failures: bool,
        uat_verified_direct_labels: set[str],
        uat_verified_indirect_labels: set[str],
        uat_verified_failures: bool,
    ) -> None:
        """Populate tested, verified, and uat_verified dimensions.

        Called by annotate_coverage() after finalize() with the label sets
        from the annotator's tracking variables.
        """
        n = self.total_assertions
        tested_all = tested_direct_labels | tested_indirect_labels
        self.tested = CoverageDimension(
            total=n,
            direct=len(tested_direct_labels),
            indirect=len(tested_all),
            direct_labels=set(tested_direct_labels),
            indirect_labels=set(tested_all),
        )
        verified_all = verified_direct_labels | verified_indirect_labels
        self.verified = CoverageDimension(
            total=n,
            direct=len(verified_direct_labels),
            indirect=len(verified_all),
            has_failures=verified_failures,
            direct_labels=set(verified_direct_labels),
            indirect_labels=set(verified_all),
        )
        uat_all = uat_verified_direct_labels | uat_verified_indirect_labels
        self.uat_verified = CoverageDimension(
            total=n,
            direct=len(uat_verified_direct_labels),
            indirect=len(uat_all),
            has_failures=uat_verified_failures,
            direct_labels=set(uat_verified_direct_labels),
            indirect_labels=set(uat_all),
        )


# ──────────────────────────────────────────────────────────────────────────
# Inherited-coverage query helpers (CUR-1353 Phase 5 / REQ-p00014-K)
# ──────────────────────────────────────────────────────────────────────────


# Implements: REQ-p00014-K
def direct_coverage_for(node: GraphNode) -> int:
    """Count coverage-contributing evidence for ``node``.

    The edge model used by the builder wires IMPLEMENTS/VERIFIES/VALIDATES
    edges as **outgoing** from the parent REQUIREMENT to CODE/TEST/JNY
    nodes, carrying ``assertion_targets`` to scope the coverage to a
    subset of the parent's assertions. So a node's "direct coverage" is
    not just its inbound edges -- for an ASSERTION we have to walk the
    parent REQ's outgoing coverage edges and count those whose
    ``assertion_targets`` contains this assertion's label (or is empty,
    meaning whole-REQ blanket coverage).

    For non-ASSERTION nodes, the direction matters and is dispatched by
    :class:`NodeKind`:

    - ``REQUIREMENT``: count only **outgoing** coverage edges (REQ ->
      CODE/TEST/JNY is the wiring convention).
    - All other kinds (``CODE``, ``TEST``, ``FILE``, ``JOURNEY``, ...):
      count only **incoming** coverage edges -- i.e. the evidence
      *received* by this node. This avoids miscounting an outgoing
      IMPLEMENTS edge from a CODE node as "the CODE node being covered".

    Args:
        node: Any graph node.

    Returns:
        The count of coverage-contributing evidence for this node.
    """
    from elspais.graph.GraphNode import NodeKind

    if node.kind == NodeKind.ASSERTION:
        label = node.get_field("label")
        count = 0
        for parent in node.iter_parents():
            if parent.kind != NodeKind.REQUIREMENT:
                continue
            for edge in parent.iter_outgoing_edges():
                if not edge.kind.contributes_to_coverage():
                    continue
                # Edge with no assertion_targets covers all assertions (blanket).
                # Edge with assertion_targets covers only those labels.
                if not edge.assertion_targets or label in edge.assertion_targets:
                    count += 1
        return count

    if node.kind == NodeKind.REQUIREMENT:
        # REQ -> CODE/TEST/JNY is the outgoing convention.
        return sum(1 for e in node.iter_outgoing_edges() if e.kind.contributes_to_coverage())

    # CODE, TEST, FILE, JOURNEY, ... -- count incoming evidence-of-coverage edges.
    return sum(1 for e in node.iter_incoming_edges() if e.kind.contributes_to_coverage())


# Implements: REQ-p00014-K
def inherited_coverage_for(node: GraphNode) -> int:
    """Return coverage for ``node``, inheriting from the template if INSTANCE.

    For an ``INSTANCE`` node, walks the outbound ``INSTANCE`` edge to find
    the template original and returns *that* node's
    :func:`direct_coverage_for` count. For any other node, returns
    ``direct_coverage_for(node)`` unchanged.

    This implements the "instance coverage == template coverage" invariant
    without persisting a derived metric on the INSTANCE node: it stays a
    query over the live graph, so the answer is always consistent with
    the current state of the template's inbound IMPLEMENTS/VERIFIES edges.

    Args:
        node: Any graph node.

    Returns:
        The inherited or direct coverage count.
    """
    from elspais.graph.relations import EdgeKind, Stereotype

    if node.get_field("stereotype") != Stereotype.INSTANCE:
        return direct_coverage_for(node)
    for edge in node.iter_outgoing_edges():
        if edge.kind == EdgeKind.INSTANCE:
            return direct_coverage_for(edge.target)
    return 0


@dataclass(frozen=True)
class SatisfierRollup:
    """Result of :func:`satisfier_rollup`.

    Attributes:
        covered: Number of assertions (own + template) with coverage > 0.
        total: Total assertions counted (own concrete + cloned template).
    """

    covered: int
    total: int

    @property
    def covered_fraction(self) -> float:
        """Fraction in ``[0, 1]``; ``0.0`` when ``total == 0``."""
        return self.covered / self.total if self.total else 0.0


# Implements: REQ-p00014-K
def satisfier_rollup(node: GraphNode) -> SatisfierRollup:
    """Combine a satisfier REQ's own and inherited coverage.

    Walks two layers:

    1. Own concrete-assertion coverage: every STRUCTURES child that is
       an ASSERTION with :func:`direct_coverage_for` > 0.
    2. Inherited template coverage: for each outbound ``SATISFIES`` edge
       (declaring REQ -> cloned root), walk that clone's STRUCTURES
       children (the instance assertions), and count each whose
       :func:`inherited_coverage_for` is > 0.

    The denominator is ``len(own_assertions) + len(template_assertions)``,
    so a satisfier that adds its own assertion *on top of* a fully
    covered template only reports full coverage once that own assertion
    is also covered. This makes satisfier-specific work visible without
    discarding the cross-cutting evidence the template already provides.

    Args:
        node: A satisfier REQUIREMENT node (declaring `Satisfies:`).

    Returns:
        A :class:`SatisfierRollup` with combined counts and fraction.
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind

    own_assertions = [
        c
        for c in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        if c.kind == NodeKind.ASSERTION
    ]
    own_covered = sum(1 for a in own_assertions if direct_coverage_for(a) > 0)

    satisfied_clones = [
        e.target for e in node.iter_outgoing_edges() if e.kind == EdgeKind.SATISFIES
    ]
    template_assertions: list[GraphNode] = []
    for clone in satisfied_clones:
        for ce in clone.iter_outgoing_edges():
            if ce.kind == EdgeKind.STRUCTURES and ce.target.kind == NodeKind.ASSERTION:
                template_assertions.append(ce.target)
    template_covered = sum(1 for a in template_assertions if inherited_coverage_for(a) > 0)

    total = len(own_assertions) + len(template_assertions)
    covered = own_covered + template_covered
    return SatisfierRollup(covered=covered, total=total)


@dataclass(frozen=True)
class IntegratesRollup:
    """Coverage/verification a consumer REQ inherits across INTEGRATES edges.

    Derived live by reading each library child's own persisted RollupMetrics.
    Nothing is persisted on the consumer node -- the INTEGRATES edge is the
    provenance (REQ-d00252-D).
    """

    implemented_covered: int
    implemented_total: int
    verified_covered: int
    verified_total: int

    @property
    def has_integrations(self) -> bool:
        return self.implemented_total > 0


# Implements: REQ-d00252
def integrates_rollup(node: GraphNode) -> IntegratesRollup:
    """Inherit implemented/verified status from library nodes via INTEGRATES.

    For each outgoing INTEGRATES edge (consumer REQ -> library node), read the
    library node's finalized ``rollup_metrics`` (computed in its own repo) and
    fold its implemented and verified dimensions in. A consumer REQ with no
    INTEGRATES edges yields all zeros.
    """
    from elspais.graph.relations import EdgeKind

    impl_c = impl_t = ver_c = ver_t = 0
    for edge in node.iter_outgoing_edges():
        if edge.kind != EdgeKind.INTEGRATES:
            continue
        metrics = edge.target.get_metric("rollup_metrics")
        if metrics is None:
            continue
        impl_c += metrics.implemented.indirect
        impl_t += metrics.implemented.total
        ver_c += metrics.verified.indirect
        ver_t += metrics.verified.total
    return IntegratesRollup(
        implemented_covered=impl_c,
        implemented_total=impl_t,
        verified_covered=ver_c,
        verified_total=ver_t,
    )


__all__ = [
    "CoverageDimension",
    "CoverageSource",
    "CoverageContribution",
    "IntegratesRollup",
    "RollupMetrics",
    "SatisfierRollup",
    "direct_coverage_for",
    "inherited_coverage_for",
    "integrates_rollup",
    "satisfier_rollup",
]
