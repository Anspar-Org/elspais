# Implements: REQ-p00006-A, REQ-p00006-B, REQ-p00006-C
# Implements: REQ-p00050-B
# Implements: REQ-d00052-A, REQ-d00052-D, REQ-d00052-E, REQ-d00052-F
# Implements: REQ-d00070-A, REQ-d00070-B
"""HTML Generator for traceability reports.

This module generates interactive HTML traceability views from TraceGraph.
Uses Jinja2 templates for rich interactive output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais import __version__
from elspais.graph.aggregation import (
    HEADLINE_MEASURE,
    assertion_measures,
    dimension_measures,
    measure_phrase,
    relative_tier_for,
)
from elspais.graph.parsers.patterns import JNY_ID_PATTERN
from elspais.html.theme import get_catalog
from elspais.utilities.patterns import INSTANCE_SEPARATOR

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph
    from elspais.graph.GraphNode import GraphNode
    from elspais.graph.metrics import CoverageDimension


@dataclass
class TreeRow:
    """Represents a single row in the tree view."""

    id: str
    display_id: str
    title: str
    level: str
    status: str
    coverage: str  # "none", "partial", "full"
    topic: str
    depth: int
    parent_id: str | None
    assertions: list[str]  # Assertion letters like ["A", "B"]
    is_leaf: bool
    is_changed: bool
    is_uncommitted: bool
    is_unsaved: bool
    has_children: bool
    has_failures: bool
    is_associated: bool  # From sponsor/associated repository
    validation_color: str = ""  # val-green/val-yellow-green/val-yellow/val-red/val-orange or ""
    validation_tip: str = ""  # Hover tooltip explaining the validation color
    result_status: str = ""  # For RESULT: passed/failed/error/skipped


@dataclass
class JourneyItem:
    """Represents a user journey for display."""

    id: str
    title: str
    description: str
    actor: str | None = None
    goal: str | None = None
    context: str | None = None
    descriptor: str = ""  # Extracted from ID: JNY-{descriptor}-{number}
    file: str = ""  # Source file path
    file_id: str = ""  # FILE node ID for mutations
    file_line: int | None = None  # parse_line for source link
    preamble: str = ""  # body_lines joined
    sections: list[dict[str, str]] = field(default_factory=list)  # [{name, content}]
    referenced_reqs: list[str] = field(default_factory=list)  # REQs via VALIDATES edges


@dataclass
class ViewStats:
    """Statistics for the header display."""

    prd_count: int = 0
    ops_count: int = 0
    dev_count: int = 0
    total_count: int = 0
    code_count: int = 0  # Number of unique CODE nodes in the graph
    test_count: int = 0  # Number of unique TEST nodes in the graph
    test_result_count: int = 0  # Number of RESULT nodes
    test_passed_count: int = 0  # Number of passed RESULT nodes
    test_failed_count: int = 0  # Number of failed RESULT nodes
    associated_count: int = 0
    journey_count: int = 0
    assertion_count: int = 0  # Total unique assertions


# ── Severity-driven coverage tiers ──

# `neutral` (the forced N/A override, REQ-d00258-H) sits at the same low
# priority as `info` so it never out-ranks a real gap (error/warning) for the
# combined worst-severity — a genuine gap still wins the combined badge/bucket.
SEVERITY_PRIORITY: dict[str, int] = {"error": 0, "warning": 1, "info": 2, "neutral": 2, "ok": 3}


def _severity_color(severity: str) -> str:
    """Resolve a severity name to its theme-catalog color_key (REQ-d00258-D)."""
    from elspais.html.theme import get_catalog

    try:
        return get_catalog().by_key(f"severity.{severity}").color_key
    except KeyError:
        return ""


# Dimension labels (the "Implemented/Tested/Passing/UAT Covered/UAT Passed"
# vocabulary, REQ-d00258-B) now live in a single per-relationship source:
# elspais.config.status_words.get_status_words(config).

# Tooltip definitions for card-view badges
DIMENSION_TIPS: dict[str, str] = {
    "implemented": "Assertions with Implements references in CODE",
    "tested": "Assertions referenced by TEST nodes",
    "verified": "Assertions with passing test results or line-coverage credit",
    "uat_coverage": "Assertions covered by journey Validates references",
    "uat_verified": "Assertions with passing journey verification",
}

# Worst-severity → filter bucket (design 2026-07-02 §2.3): the bucket honors
# each dimension's configured severity, so info-severity gaps (e.g. UAT "missing"
# under the default config) do not drag the bucket below "full". A "failing"
# tier on any dimension is an overlay checked before the severity mapping.
_SEVERITY_TO_BUCKET: dict[str, str] = {
    "error": "missing",
    "warning": "partial",
    "info": "full",
    # `neutral` (N/A override, REQ-d00258-H) is non-dragging exactly like `info`:
    # a not-applicable dimension must never pull the combined bucket below "full".
    "neutral": "full",
    "ok": "full",
}

# Tier descriptions for tooltip text
_TIER_DESCRIPTIONS: dict[str, str] = {
    "failing": "test failures detected",
    "full": "fully covered",
    # "partially covered", NOT "some assertions covered": partial can also
    # mean ALL assertions credited at fractional strength (e.g. a validating
    # journey with 5/7 steps verified), where "some assertions" misleads.
    "partial": "partially covered",
    "missing": "no coverage",
}

# Ordered list of dimension keys (matches CoverageDimension attrs on RollupMetrics)
DIMENSION_KEYS = ("implemented", "tested", "verified", "uat_coverage", "uat_verified")


def _tier_to_severity(tier: str, severity_config: Any) -> str:
    """Map a CoverageDimension tier to a severity string using config.

    Tiers are the unified single-word vocabulary (full/partial/failing/missing),
    which are exactly the CoverageSeverityConfig field names (REQ-d00258).
    """
    return getattr(severity_config, tier, "error")


def compute_coverage_tiers(node: GraphNode, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute per-dimension severity colors and combined worst-of-all.

    Uses each CoverageDimension's tier property, maps through config
    severity to determine badge color.

    Args:
        node: A GraphNode with pre-computed rollup_metrics.
        config: Project config dict (from load_config()). If None, uses defaults.

    Returns:
        Dict with keys: impl_color, impl_tip, impl_tier, tested_color, tested_tip,
        tested_tier, verified_color, verified_tip, verified_tier, uat_cov_color,
        uat_cov_tip, uat_cov_tier, uat_ver_color, uat_ver_tip, uat_ver_tier,
        combined_color, combined_tip, combined_bucket.
        All empty strings only if the node has no rollup / no assertions.
        Badges render for EVERY status (REQ-d00258, Phase 3); the status only
        gates whether a `missing` Implemented tier is a red gap (status expects
        implementation) or a neutral grey one (it does not).
    """
    from elspais.config.schema import CoverageConfig, CoverageSeverityConfig
    from elspais.config.status_words import get_status_words
    from elspais.graph.metrics import tested_partition

    empty: dict[str, Any] = {
        "impl_color": "",
        "impl_tip": "",
        "impl_tier": "",
        "tested_color": "",
        "tested_tip": "",
        "tested_tier": "",
        "verified_color": "",
        "verified_tip": "",
        "verified_tier": "",
        "uat_cov_color": "",
        "uat_cov_tip": "",
        "uat_cov_tier": "",
        "uat_ver_color": "",
        "uat_ver_tip": "",
        "uat_ver_tier": "",
        "combined_color": "",
        "combined_tip": "",
        "combined_bucket": "",
        "expects_validation": False,
    }

    # Coverage badges ALWAYS render, regardless of status (REQ-d00258, Phase 3).
    # Suppressing badges for coverage-excluded statuses is retired: a Draft or
    # Deprecated requirement now shows its coverage. The only status-sensitive
    # projection is the ``Implemented`` dimension's gap severity, gated below on
    # ``status_expects_implementation``.
    from elspais.config import status_expects_implementation
    from elspais.graph.metrics import RollupMetrics, tested_and_passing

    rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
    if not rollup or rollup.total_assertions == 0:
        return empty

    # Get coverage severity config
    cov_config = CoverageConfig()
    if config:
        rules = config.get("rules", {})
        if isinstance(rules, dict):
            cov_raw = rules.get("coverage", {})
            if isinstance(cov_raw, dict):
                cov_config = CoverageConfig(
                    **{
                        # ``status_words`` is a flat dict[str, str] label-override
                        # map (REQ-d00258), not a per-dimension severity block --
                        # pass it through un-wrapped so it validates.
                        k: (
                            v
                            if k == "status_words" or not isinstance(v, dict)
                            else CoverageSeverityConfig(**v)
                        )
                        for k, v in cov_raw.items()
                    }
                )
            elif hasattr(cov_raw, "implemented"):
                cov_config = cov_raw
        elif hasattr(rules, "coverage"):
            cov_config = rules.coverage

    # Per-level UAT expectation (REQ-d00258-F). By default a UAT `missing` tier is
    # soft (config `_uat_severity` sets missing="info") so a journey-less
    # requirement is not dragged below "full". When the requirement's level
    # `expects_validation`, that absence is a REAL gap: override the UAT
    # severity config so `missing` resolves to "error" (-> red badge + drags
    # combined_bucket). Partial stays "warning" regardless (from 1a7fc2c7).
    from elspais.config import level_expects_validation

    expects_validation = level_expects_validation(config or {}, node.level)
    uat_cov_cfg = cov_config.uat_coverage
    uat_ver_cfg = cov_config.uat_verified
    if expects_validation:
        uat_cov_cfg = uat_cov_cfg.model_copy(update={"missing": "error"})
        uat_ver_cfg = uat_ver_cfg.model_copy(update={"missing": "error"})

    # The chain of relative denominators (REQ-d00258-I) is NOT derived here.
    # Coverage aggregation has ONE home (`graph/aggregation.py`), so which
    # label-set a chained dimension is measured over -- and whether it is
    # chained at all -- is answered by `relative_tier_for`, the same helper the
    # shared tier buckets read. The badge and the rollup therefore cannot
    # disagree about what a dimension counts.
    #
    # Map dimension key -> (CoverageDimension, CoverageSeverityConfig, prefix).
    # The dimension is carried for the hover text only; the tier comes from the
    # shared helper, whose "verified" numerator is tested_and_passing()
    # (REQ-d00258-N): what the declared tests returned, with an assertion its
    # own tests failed excluded from the figures. Line coverage credits nothing
    # here; it is reported as its own dimension (REQ-d00254-B).
    passing = tested_and_passing(rollup)
    dim_map = [
        ("implemented", rollup.implemented, cov_config.implemented, "impl"),
        ("tested", rollup.tested, cov_config.tested, "tested"),
        ("verified", passing, cov_config.verified, "verified"),
        ("uat_coverage", rollup.uat_coverage, uat_cov_cfg, "uat_cov"),
        ("uat_verified", rollup.uat_verified, uat_ver_cfg, "uat_ver"),
    ]

    status_words = get_status_words(config)

    result: dict[str, Any] = {}
    worst_severity_priority = 999
    worst_severity = ""
    worst_color = ""
    any_failing = False
    tip_parts: list[str] = []

    # The measure the badge scores: TOTAL, each *Assertion* counted once at the
    # greatest of its four measures (REQ-d00069-N). Headlining it is what
    # REQ-d00258-A asks of every reporting surface; the four measures behind it
    # are published in the hover text below rather than hinted at by a marker
    # (REQ-d00258-J).
    measure = HEADLINE_MEASURE
    for dim_key, dim, sev_cfg, prefix in dim_map:
        tier, is_na = relative_tier_for(rollup, dim_key, measure=measure)
        # A `missing` tier that is N/A (empty relative denominator) is neutral:
        # nothing to measure, so it resolves to the `neutral` severity (GREY,
        # REQ-d00258-H) regardless of the dimension's configured `missing`
        # severity. A non-N/A `missing` is a real gap and uses the configured
        # severity.
        neutral = tier == "missing" and is_na
        # The `Implemented` gap is only a REAL (red) gap when the requirement's
        # status expects implementation (REQ-d00258, Phase 3). For a status that
        # does not (e.g. Draft/Deprecated by default), a missing implemented tier
        # renders NEUTRAL grey -- badges still show, but the absence is not
        # flagged as a defect.
        if (
            dim_key == "implemented"
            and tier == "missing"
            and not status_expects_implementation(config or {}, node.status)
        ):
            neutral = True
        # The forced-neutral override renders GREY (`neutral` severity), matching
        # the per-assertion `missing` standing and the user's green/yellow/red/grey
        # palette -- NOT the yellow-green `info` severity, which is a real
        # "fully-covered-including-indirect" state (REQ-d00258-H). This is a color
        # change only: the tier stays `missing` and the dimension stays
        # non-dragging for combined-bucket purposes (neutral maps to "full").
        #
        # SEVERITY drives the combined bucket (`_SEVERITY_TO_BUCKET`) and the
        # `elspais checks` gate; it is computed exactly as before so those two
        # jobs are unchanged.
        severity = "neutral" if neutral else _tier_to_severity(tier, sev_cfg)
        # COLOR is decoupled from severity (REQ-d00258-D): it resolves from the
        # coverage STANDING through the theme catalog -- the SAME source the
        # per-*Assertion* badges use -- so a given standing is one color
        # everywhere (full->green, partial->yellow, failing->red), regardless of
        # the dimension's configured severity. This kills the
        # `uat partial=info -> yellow-green` bug: a partial badge is always
        # yellow. The ONE deliberate exception: a `missing` standing renders RED
        # only when it is a hard REQUIRED gap (resolved severity == "error");
        # every other missing (soft info/warning, or N/A neutral) renders GREY.
        # Severity therefore no longer recolors full/partial/failing.
        if tier == "missing":
            color = _severity_color("error") if severity == "error" else _standing_color("missing")
        else:
            color = _standing_color(tier)
        label = status_words[dim_key]
        desc = _TIER_DESCRIPTIONS.get(tier, tier)

        # Implements: REQ-d00069-L, REQ-d00258-A, REQ-d00258-J
        # The four measures behind the headline standing, published in the
        # hover text. A marker standing in for a measure the badge does not
        # show is retired (REQ-d00258-J): a reader who wants to know what
        # produced the figure reads the measures themselves.
        tip = f"{label}: {desc} — {measure_phrase(dimension_measures(dim))}"
        # Implements: REQ-d00258-O
        # The Tested badge is where the breakdown belongs on this surface: it
        # qualifies that figure and introduces no badge of its own.
        if prefix == "tested":
            part = tested_partition(rollup)
            if part.tested:
                tip += (
                    f" — {part.passed} passed, {part.failed} failed,"
                    f" {part.awaiting} awaiting a result"
                )

        result[f"{prefix}_color"] = color
        result[f"{prefix}_tip"] = tip
        result[f"{prefix}_tier"] = tier

        # Track worst severity for combined
        sev_pri = SEVERITY_PRIORITY.get(severity, 999)
        if sev_pri < worst_severity_priority:
            worst_severity_priority = sev_pri
            worst_severity = severity
            worst_color = color

        if tier == "failing":
            any_failing = True

        tip_parts.append(tip)

    result["combined_color"] = worst_color
    result["combined_tip"] = " | ".join(tip_parts)
    # Failing overlay first, else severity-aware bucket (design §2.3):
    # info/ok gaps (e.g. UAT dims by default) still bucket "full".
    if any_failing:
        result["combined_bucket"] = "failing"
    else:
        result["combined_bucket"] = _SEVERITY_TO_BUCKET.get(worst_severity, "missing")

    # Surface the per-level UAT expectation so the viewer can gate the two UAT
    # header badges: a journey-less expects_validation requirement still shows a
    # (red) UAT badge; a non-expecting one shows none (REQ-d00258-F).
    result["expects_validation"] = expects_validation

    return result


# The semantic per-assertion coverage "standings" (REQ-d00258-G). These are the
# tokens the server emits per assertion per dimension; their COLORS are NOT
# defined here -- they live in the theme catalog ([coverage_standing.*] in
# theme.toml) and are resolved through it, exactly as severity colors are
# (REQ-d00258-D). This keeps the standing->color association configurable and
# out of the badge logic.
COVERAGE_STANDINGS = ("full", "partial", "failing", "missing")


def _standing_color(standing: str) -> str:
    """Resolve a coverage standing to its theme-catalog color_key (REQ-d00258-G).

    Mirrors ``_severity_color``: the association lives in the catalog
    (``[coverage_standing.*]``), never hard-coded here.
    """
    from elspais.html.theme import get_catalog

    try:
        return get_catalog().by_key(f"coverage_standing.{standing}").color_key
    except KeyError:
        return ""


def compute_assertion_coverage_states(
    node: GraphNode, config: dict[str, Any] | None = None
) -> dict[str, dict[str, str]]:
    """Project each requirement dimension's coverage down to per-*Assertion* standings.

    Returns ``{label: {implemented, tested, verified, uat_coverage,
    uat_verified: standing}}`` where ``standing`` is one of ``"full"``,
    ``"partial"``, ``"failing"``, ``"missing"`` (a SEMANTIC token, not a color --
    the viewer resolves the color through the theme catalog). The standings are
    read from the SAME ``rollup_metrics`` per-label fields that drive the
    requirement-level badges (``compute_coverage_tiers``), so the two levels can
    never disagree (REQ-d00258-G): if every assertion is ``"full"`` the
    requirement dimension is a full tier; if any assertion is ``"failing"`` the
    dimension ``has_failures``.

    Dimension -> RollupMetrics source:
      - implemented  : ``implemented`` total measure
      - tested       : ``tested`` total measure
      - verified     : ``tested_and_passing(rollup)`` union per label (+ its
                       ``failing_labels``, so red lands only on the assertion
                       that itself failed)
      - uat_coverage : ``uat_coverage`` total measure
      - uat_verified : ``uat_verified`` total measure (+ its
                       ``failing_labels``)

    Standing rule: ``full`` at ~100%, ``partial`` at 0<f<1 with no own failure,
    ``failing`` when this assertion itself failed (``label in failing_labels``),
    ``missing`` otherwise. An assertion is NEVER reddened by a failing SIBLING
    (REQ-d00258-G).
    No coverage is recomputed here -- only the pre-computed per-label fractions
    are projected. Returns ``{}`` only for a node with no rollup / no assertions
    (same gate as ``compute_coverage_tiers``); standings compute for EVERY
    status (REQ-d00258, Phase 3).
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.metrics import tested_and_passing

    # Per-assertion standings ALWAYS compute, regardless of status (REQ-d00258,
    # Phase 3). The coverage-excluded suppression is retired to match
    # ``compute_coverage_tiers``.
    rollup = node.get_metric("rollup_metrics")
    if not rollup or rollup.total_assertions == 0:
        return {}

    labels: list[str] = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            label = child.get_field("label", "")
            if label:
                labels.append(label)

    from elspais.graph.aggregation import measure_by_label

    eps = 1e-9

    def _frac(dim: CoverageDimension, label: str) -> float:
        """This *Assertion*'s TOTAL coverage on ``dim``.

        The greatest of its four measures (REQ-d00069-N), so an *Assertion*
        covered more than one way is counted once and the pill headlines the
        same figure the requirement badge does (REQ-d00258-A). Which measures
        produced it is published beside the standing rather than hinted at
        (REQ-d00258-J) -- see ``compute_assertion_coverage_measures``.
        """
        return measure_by_label(dim, HEADLINE_MEASURE).get(label, 0.0)

    def _simple_standing(dim: CoverageDimension, label: str) -> str:
        f = _frac(dim, label)
        if f >= 1.0 - eps:
            return "full"
        if f > eps:
            return "partial"
        return "missing"

    def _passing_standing(passing: CoverageDimension, label: str) -> str:
        """Passing/verified standing gated on THIS assertion's own failure.

        A failure lands on this assertion only when the assertion itself failed
        (``label in passing.failing_labels``) -- NOT merely because a sibling
        assertion, covered by a different (non-failing) test/journey, failed and
        set the requirement-wide ``has_failures`` flag (REQ-d00258-G). The
        requirement-level badge still goes red for any failing assertion via the
        dimension-wide ``has_failures`` in ``compute_coverage_tiers``.

        The failure is read BEFORE the credit, because credit does not answer
        it: line coverage never observes a verdict, so a failing test whose
        lines were executed leaves this assertion at full credit and failing at
        once. Reading credit first would paint it green while the Passing
        figures beside it exclude it (REQ-d00258-N), which is the same
        disagreement REQ-d00258-G exists to prevent.
        """
        if label in passing.failing_labels:
            return "failing"
        f = _frac(passing, label)
        if f >= 1.0 - eps:
            return "full"
        if f > eps:
            return "partial"
        return "missing"

    passing = tested_and_passing(rollup)
    states: dict[str, dict[str, str]] = {}
    for label in labels:
        states[label] = {
            "implemented": _simple_standing(rollup.implemented, label),
            "tested": _simple_standing(rollup.tested, label),
            "verified": _passing_standing(passing, label),
            "uat_coverage": _simple_standing(rollup.uat_coverage, label),
            "uat_verified": _passing_standing(rollup.uat_verified, label),
        }
    return states


# Implements: REQ-d00069-L, REQ-d00258-A, REQ-d00258-G, REQ-d00258-J
def compute_assertion_coverage_measures(node: GraphNode) -> dict[str, dict[str, str]]:
    """The measures behind each per-*Assertion* standing, ready to display.

    Returns ``{label: {dimension: phrase}}``, the phrase naming all four
    measures of REQ-d00069-L for that *Assertion* on that dimension: what a
    citation named (direct or whole-requirement) crossed with where the
    evidence sits (attached here, or conducted up a `Refines:` chain).

    A pill headlines the TOTAL standing, and this is how a reader sees what
    produced it (REQ-d00258-G). It replaces the retired ``~`` caveat, which
    stood in for a measure the pill did not show (REQ-d00258-J). The phrase is
    composed HERE, from the one shared vocabulary, so the viewer never spells a
    second wording for measures the CLI already names.

    'verified' reads ``tested_and_passing`` and 'uat_verified' its own
    dimension, matching exactly what ``compute_assertion_coverage_states``
    scored, so the measures shown can never belong to a different figure than
    the standing beside them.
    """
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.metrics import tested_and_passing

    rollup = node.get_metric("rollup_metrics")
    if not rollup or rollup.total_assertions == 0:
        return {}
    labels = [
        c.get_field("label", "")
        for c in node.iter_children()
        if c.kind == NodeKind.ASSERTION and c.get_field("label", "")
    ]
    dims = {
        "implemented": rollup.implemented,
        "tested": rollup.tested,
        "verified": tested_and_passing(rollup),
        "uat_coverage": rollup.uat_coverage,
        "uat_verified": rollup.uat_verified,
    }
    return {
        label: {
            dim_key: measure_phrase(assertion_measures(dim, label), as_percent=True)
            for dim_key, dim in dims.items()
        }
        for label in labels
    }


# Implements: REQ-p00006-A
def compute_validation_color(
    node: GraphNode, config: dict[str, Any] | None = None
) -> tuple[str, str]:
    """Compute a validation quality color for a requirement's Active status badge.

    Backward-compatible wrapper around compute_coverage_tiers().
    Returns the combined (worst-of-all) color and tooltip.

    Args:
        node: A GraphNode with pre-computed rollup_metrics.
        config: Optional project config dict.

    Returns:
        Tuple of (css_class_suffix, reason_text). Both empty if no color applies.
    """
    tiers = compute_coverage_tiers(node, config)
    return (tiers["combined_color"], tiers["combined_tip"])


class HTMLGenerator:
    """Generates interactive HTML traceability view from TraceGraph.

    Uses Jinja2 templates to render a rich, interactive tree view with:
    - Hierarchical expand/collapse
    - Multiple view modes (flat/hierarchical)
    - Git change detection
    - Coverage indicators
    - Filtering and search

    Args:
        graph: The TraceGraph containing all requirement data.
        version: Version string for display (defaults to elspais package version).
    """

    def __init__(
        self,
        graph: FederatedGraph,
        base_path: str = "",
        version: str | None = None,
        repo_name: str | None = None,
        namespace: str | None = None,
        config: dict | None = None,
    ) -> None:
        self.graph = graph
        self.base_path = base_path
        self.version = version if version is not None else __version__
        self.repo_name = repo_name
        self.config = config or {}
        # Pull the REQ-id prefix from config when callers don't pass it
        # explicitly. ``load_config()`` guarantees ``[project].namespace``
        # is non-empty; for the no-config-file degraded path the schema
        # default ("REQ") flows through here unchanged.
        if namespace is None:
            namespace = self.config.get("project", {}).get("namespace") or "REQ"
        self.namespace = namespace

    def generate(self, embed_content: bool = False) -> str:
        """Generate the complete HTML report.

        Args:
            embed_content: If True, embed full requirement content as JSON.

        Returns:
            Complete HTML document as string.
        """
        try:
            from jinja2 import Environment, PackageLoader, select_autoescape

            env = Environment(
                loader=PackageLoader("elspais.html", "templates"),
                autoescape=select_autoescape(["html", "xml"]),
            )
            template = env.get_template("trace_unified.html.j2")
        except ImportError as err:
            raise ImportError(
                "HTMLGenerator requires the trace-view extra. "
                "Install with: pip install elspais[trace-view]"
            ) from err

        # Annotation must happen AFTER graph construction, BEFORE output generation.
        # Generators may add additional annotations specific to their output format.
        self._annotate_git_state()

        # Build data structures
        stats = self._compute_stats()
        rows = self._build_tree_rows()
        journeys = self._collect_journeys()
        statuses = self._collect_unique_values("status")
        topics = self._collect_unique_values("topic")
        tree_data = self._build_tree_data() if embed_content else {}

        # Collect source files with syntax highlighting for inline viewer
        source_files = self._collect_source_files() if embed_content else {}
        pygments_css = self._get_pygments_css() if source_files else ""
        pygments_css_dark = self._get_pygments_css_dark() if source_files else ""

        # Build embedded data indexes for view-mode apiFetch adapter
        node_index = self._build_node_index() if embed_content else {}
        coverage_index = self._build_coverage_index() if embed_content else {}
        status_data = self._build_status_data() if embed_content else {}

        # Update journey count in stats
        stats.journey_count = len(journeys)

        # Build dynamic category catalogs (levels/namespaces/statuses with
        # resolved colors). Same shape used by the live viewer routes.
        from elspais.config.schema import ElspaisConfig
        from elspais.view_model import build_levels, build_namespaces, build_statuses

        try:
            typed_cfg = ElspaisConfig.model_validate(self.config)
        except Exception:
            typed_cfg = ElspaisConfig.model_validate({})
        levels_ctx = build_levels(typed_cfg)
        namespaces_ctx = build_namespaces(typed_cfg, self.graph)
        statuses_ctx = build_statuses(typed_cfg, candidates=sorted(statuses))

        # Render template
        html_content = template.render(
            mode="view",
            stats=stats,
            rows=rows,
            journeys=journeys,
            statuses=statuses_ctx,
            topics=sorted(topics),
            tree_data=tree_data,
            source_files=source_files,
            pygments_css=pygments_css,
            pygments_css_dark=pygments_css_dark,
            node_index=node_index,
            coverage_index=coverage_index,
            status_data=status_data,
            version=self.version,
            base_path=self.base_path,
            repo_name=(
                self.repo_name or (Path(self.base_path).name if self.base_path else "elspais")
            ),
            catalog=get_catalog(),
            default_hidden_statuses=[],
            levels=levels_ctx,
            namespaces=namespaces_ctx,
        )

        return html_content

    def _annotate_git_state(self) -> None:
        """Apply git state and display annotations to all requirement nodes.

        Uses the shared annotate_graph_git_state() for git detection,
        then applies display info annotations separately.
        """
        from elspais.graph import NodeKind
        from elspais.graph.annotators import annotate_display_info, annotate_graph_git_state

        # Standard annotation sequence: git_state -> display_info.
        # This order matters: display_info may depend on git state.
        annotate_graph_git_state(self.graph)

        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            annotate_display_info(node)

    def _is_associated(self, node: GraphNode) -> bool:
        """Check if a node is from an associated/sponsor repository.

        Associated requirements come from sponsor repos, identified by:
        - ID containing associated prefix (e.g., REQ-CAL-p00001)
        - Path containing 'sponsor' or 'associated'
        - Path outside the base_path (different repo)
        - Or marked with an associated field
        """
        # Check if ID has a different namespace than the core project.
        # Associated IDs have a different prefix (e.g., REQ-CAL-p00001 when
        # core namespace is "REQ"). Detect by checking if the ID starts with
        # "{namespace}-" followed by an uppercase segment (the associate prefix).
        import re

        core_prefix = f"{self.namespace}-"
        if node.id.startswith(core_prefix):
            after_prefix = node.id[len(core_prefix) :]
            # Associated: namespace-ASSOC-type (ASSOC is 2+ uppercase letters)
            if re.match(r"^[A-Z]{2,}-[a-z]", after_prefix):
                return True

        # Implements: REQ-d00129-D
        _fn = node.file_node()
        if not _fn:
            return False

        _rp = _fn.get_field("relative_path") or ""
        path = _rp.lower()
        # Check for common associated repo patterns
        if "sponsor" in path or "associated" in path:
            return True

        # Check if path is outside base_path (different repo)
        if self.base_path:
            try:
                # If the source path doesn't start with base_path, it's from a different repo
                source_path = Path(_rp).resolve()
                base = Path(self.base_path).resolve()
                if not str(source_path).startswith(str(base)):
                    return True
            except (ValueError, OSError):
                pass

        # Check if node has associated field set
        if node.get_field("associated", False):
            return True

        return False

    def _compute_stats(self) -> ViewStats:
        """Compute statistics for the header.

        REQ-d00258-C: level counts and assertion counts derive from the
        shared aggregation module (graph/aggregation.py) on the per-*Assertion*
        total, so the viewer header agrees with CLI summary and MCP
        get_project_summary. Node-kind tallies (CODE/TEST/RESULT) and the
        viewer-specific associated-repo count are simple index counts, not
        coverage rollups, and stay local.
        """
        from elspais.graph import NodeKind
        from elspais.graph.aggregation import aggregate_by_level

        stats = ViewStats()

        for agg in aggregate_by_level(self.graph, self.config):
            level = agg.level.upper()
            if level == "PRD":
                stats.prd_count = agg.total_requirements
            elif level == "OPS":
                stats.ops_count = agg.total_requirements
            elif level == "DEV":
                stats.dev_count = agg.total_requirements
            stats.total_count += agg.total_requirements
            stats.assertion_count += agg.total_assertions

        # Viewer-specific: associated-repo requirement count (repo
        # attribution, not a coverage rollup — stays a local index count).
        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            if self._is_associated(node):
                stats.associated_count += 1

        # Count CODE nodes
        for _ in self.graph.nodes_by_kind(NodeKind.CODE):
            stats.code_count += 1

        # Count TEST nodes
        for _ in self.graph.nodes_by_kind(NodeKind.TEST):
            stats.test_count += 1

        # Count RESULT nodes
        for node in self.graph.nodes_by_kind(NodeKind.RESULT):
            stats.test_result_count += 1
            status = (node.get_field("status", "") or "").lower()
            if status in ("passed", "pass", "success"):
                stats.test_passed_count += 1
            elif status in ("failed", "fail", "failure", "error"):
                stats.test_failed_count += 1

        return stats

    def _build_tree_rows(self) -> list[TreeRow]:
        """Build flat list of rows representing the hierarchical tree.

        Nodes can appear multiple times if they have multiple parents.
        Uses DFS traversal to maintain parent-child ordering.
        """
        from elspais.graph import NodeKind

        rows: list[TreeRow] = []
        visited_at_depth: dict[tuple[str, int, str | None], bool] = {}
        visited_node_ids: set[str] = set()  # Track all rendered node IDs

        from elspais.config import default_level_keys

        _level_keys = list((self.config.get("levels") or {}).keys()) or default_level_keys()
        level_prefixes = tuple(f"{k.lower()}-" for k in _level_keys)

        def get_topic(node: GraphNode) -> str:
            """Extract topic from file path."""
            _fn = node.file_node()
            if not _fn:
                return ""
            path = _fn.get_field("relative_path") or ""
            # Extract filename without extension
            # e.g., "spec/prd-system.md" -> "prd-system" -> "system"
            filename = Path(path).stem
            for prefix in level_prefixes:
                if filename.lower().startswith(prefix):
                    return filename[len(prefix) :]
            return filename

        def is_roadmap(node: GraphNode) -> bool:
            """Check if node is from a roadmap file."""
            _fn = node.file_node()
            if not _fn:
                return False
            return "roadmap" in (_fn.get_field("relative_path") or "").lower()

        def compute_coverage(node: GraphNode) -> tuple[str, bool]:
            """Get coverage status and failure flag from pre-computed metrics.

            Uses RollupMetrics computed by annotate_coverage(). Reports on the
            per-*Assertion* total (REQ-d00069-N) -- the greatest of an
            *Assertion*'s four measures -- like every other coverage headline
            (REQ-d00258-A).

            Returns:
                Tuple of (coverage_status, has_failures), coverage_status
                being "none", "partial", or "full".
            """
            from elspais.graph.metrics import RollupMetrics, tested_and_passing

            rollup: RollupMetrics | None = node.get_metric("rollup_metrics")

            if not rollup or rollup.total_assertions == 0:
                # No assertions - check if any code references the req directly
                has_code = False
                for child in node.iter_children():
                    if child.kind == NodeKind.CODE:
                        has_code = True
                        break
                return ("full" if has_code else "none", False)

            dim = rollup.implemented
            pct = (dim.covered / dim.total * 100) if dim.total else 0.0
            if pct <= 0:
                cov = "none"
            elif pct < 100:
                cov = "partial"
            else:
                cov = "full"

            # Passing-dimension failures, so an lcov-side failure is seen
            # as well as a result-verified one (REQ-d00258-N).
            return (cov, tested_and_passing(rollup).has_failures)

        def get_assertion_letters(node: GraphNode, parent_id: str | None) -> list[str]:
            """Get assertion letters that this node implements from a specific parent."""
            if not parent_id:
                return []

            letters: list[str] = []
            for edge in node.iter_incoming_edges():
                if edge.source.id == parent_id and edge.assertion_targets:
                    letters.extend(edge.assertion_targets)
            return sorted(set(letters))

        def has_req_children(node: GraphNode) -> bool:
            """Check if node has requirement children (for tree expand/collapse)."""
            for child in node.iter_children():
                if child.kind == NodeKind.REQUIREMENT:
                    return True
            return False

        def has_code_children(node: GraphNode) -> bool:
            """Check if node has code children."""
            for child in node.iter_children():
                if child.kind == NodeKind.CODE:
                    return True
            return False

        def has_test_children(node: GraphNode) -> bool:
            """Check if node has test children."""
            for child in node.iter_children():
                if child.kind == NodeKind.TEST:
                    return True
            return False

        def has_test_result_children(node: GraphNode) -> bool:
            """Check if node has test result children."""
            for child in node.iter_children():
                if child.kind == NodeKind.RESULT:
                    return True
            return False

        def traverse(
            node: GraphNode,
            depth: int,
            parent_id: str | None,
            parent_assertions: list[str] | None = None,
            ancestor_ids: frozenset[str] | None = None,
        ) -> None:
            """DFS traversal to build rows."""
            # Detect cycles - if this node is already an ancestor, skip
            if ancestor_ids and node.id in ancestor_ids:
                return

            # Avoid duplicate (id, depth, parent) entries
            key = (node.id, depth, parent_id)
            if key in visited_at_depth:
                return
            visited_at_depth[key] = True

            # Process requirements, code, test, and test_result nodes
            if node.kind not in (
                NodeKind.REQUIREMENT,
                NodeKind.CODE,
                NodeKind.TEST,
                NodeKind.RESULT,
            ):
                return

            is_code = node.kind == NodeKind.CODE
            is_test = node.kind == NodeKind.TEST
            is_test_result = node.kind == NodeKind.RESULT
            is_impl_node = is_code or is_test or is_test_result  # Implementation/evidence nodes
            coverage, has_failures = ("none", False) if is_impl_node else compute_coverage(node)
            val_color, val_tip = ("", "") if is_impl_node else compute_validation_color(node)
            assertion_letters = (
                get_assertion_letters(node, parent_id)
                if parent_assertions is None
                else parent_assertions
            )

            # Get result status for RESULT nodes
            result_status = ""
            if is_test_result:
                result_status = (node.get_field("status", "") or "").lower()

            # Determine has_children based on node kind
            if is_test:
                # TEST nodes can have RESULT children
                node_has_children = has_test_result_children(node)
            elif is_test_result:
                # RESULT nodes don't have children
                node_has_children = False
            else:
                # REQ and CODE nodes
                node_has_children = (
                    has_req_children(node) or has_code_children(node) or has_test_children(node)
                )

            # Create row
            row = TreeRow(
                id=f"{node.id}_{depth}_{parent_id or 'root'}",  # Unique key for multi-parent
                display_id=node.id,
                title=node.get_label() or "",
                level=(node.level or "").upper() if not is_impl_node else "",
                status=(node.status or "").upper() if not is_impl_node else "",
                coverage=coverage,
                validation_color=val_color,
                validation_tip=val_tip,
                topic=get_topic(node) if not is_impl_node else "",
                depth=depth,
                parent_id=(
                    f"{parent_id}_{depth - 1}_"
                    f"{rows[-1].parent_id if rows and depth > 0 else 'root'}"
                    if parent_id and depth > 0
                    else None
                ),
                assertions=assertion_letters,
                is_leaf=not has_req_children(node) and not is_impl_node,
                is_changed=node.get_metric("is_branch_changed", False),
                is_uncommitted=node.get_metric("is_uncommitted", False)
                or node.get_metric("is_untracked", False),
                is_unsaved=False,
                has_children=node_has_children,
                has_failures=has_failures,
                is_associated=self._is_associated(node) if not is_impl_node else False,
                result_status=result_status,
            )

            # Fix parent_id to reference actual row id
            if parent_id and depth > 0:
                # Find the parent row we just added
                for prev_row in reversed(rows):
                    if prev_row.display_id == parent_id and prev_row.depth == depth - 1:
                        row.parent_id = prev_row.id
                        break

            rows.append(row)
            visited_node_ids.add(node.id)

            # Traverse children - requirements first, then code/tests
            # First, aggregate all assertion targets per child to avoid duplicates
            child_assertions: dict[str, tuple[GraphNode, set[str]]] = {}
            children_without_assertions: list[GraphNode] = []

            for edge in node.iter_outgoing_edges():
                child = edge.target
                if child.kind == NodeKind.REQUIREMENT:
                    if edge.assertion_targets:
                        # Aggregate assertion targets for this child
                        if child.id not in child_assertions:
                            child_assertions[child.id] = (child, set())
                        child_assertions[child.id][1].update(edge.assertion_targets)
                    else:
                        # Track children without assertion-specific edges
                        if child.id not in child_assertions:
                            children_without_assertions.append(child)

            # Build children_to_visit list: assertion-specific children first
            children_to_visit: list[tuple[GraphNode, list[str] | None]] = []
            for _child_id, (child, assertions) in child_assertions.items():
                # Convert set to sorted list
                children_to_visit.append((child, sorted(assertions)))

            # Add children without assertion targets
            # (only if they don't have assertion-specific edges)
            for child in children_without_assertions:
                if child.id not in child_assertions:
                    children_to_visit.append((child, None))

            # Add code, test, and test_result children
            for child in node.iter_children():
                if child.kind == NodeKind.CODE:
                    children_to_visit.append((child, None))
                elif child.kind == NodeKind.TEST:
                    children_to_visit.append((child, None))
                elif child.kind == NodeKind.RESULT:
                    # RESULT children of TEST nodes
                    children_to_visit.append((child, None))

            # Sort children: assertion-specific first (by letter), then general (by ID)
            # Key: (has_assertions=False sorts before True, assertion_letters, node_id)
            def sort_key(item: tuple[GraphNode, list[str] | None]) -> tuple:
                child, assertions = item
                if assertions:
                    # Has assertion targets: sort by letters first (A, B, C...)
                    return (0, sorted(assertions), child.id)
                else:
                    # No assertion targets: sort after assertion-specific children
                    return (1, [], child.id)

            children_to_visit.sort(key=sort_key)

            current_ancestors = (ancestor_ids or frozenset()) | {node.id}
            for child, assertions in children_to_visit:
                traverse(child, depth + 1, node.id, assertions, current_ancestors)

        # Start traversal from roots
        for root in self.graph.iter_roots():
            if root.kind == NodeKind.REQUIREMENT:
                traverse(root, 0, None)

        # Add unvisited TEST nodes (orphan or not reached from root traversal)
        # These appear as root-level items with their RESULT children
        for node in self.graph.nodes_by_kind(NodeKind.TEST):
            if node.id in visited_node_ids:
                continue

            row = TreeRow(
                id=f"{node.id}_0_root",
                display_id=node.id,
                title=node.get_label() or "",
                level="",
                status="",
                coverage="none",
                topic="",
                depth=0,
                parent_id=None,
                assertions=[],
                is_leaf=False,
                is_changed=False,
                is_uncommitted=False,
                is_unsaved=False,
                has_children=has_test_result_children(node),
                has_failures=False,
                is_associated=False,
                result_status="",
            )
            rows.append(row)
            visited_node_ids.add(node.id)

            # Render RESULT children under this TEST node
            for child in node.iter_children():
                if child.kind == NodeKind.RESULT:
                    child_result_status = (child.get_field("status", "") or "").lower()

                    child_row = TreeRow(
                        id=f"{child.id}_1_{node.id}",
                        display_id=child.id,
                        title=child.get_label() or "",
                        level="",
                        status="",
                        coverage="none",
                        topic="",
                        depth=1,
                        parent_id=row.id,
                        assertions=[],
                        is_leaf=True,
                        is_changed=False,
                        is_uncommitted=False,
                        is_unsaved=False,
                        has_children=False,
                        has_failures=child_result_status in ("failed", "fail", "failure", "error"),
                        is_associated=False,
                        result_status=child_result_status,
                    )
                    rows.append(child_row)
                    visited_node_ids.add(child.id)

        # Add orphan RESULT nodes (not visited via any TEST parent)
        for node in self.graph.nodes_by_kind(NodeKind.RESULT):
            if node.id in visited_node_ids:
                continue

            result_status = (node.get_field("status", "") or "").lower()

            # Create a short display ID from test name
            test_name = node.get_field("name", "") or ""
            classname = node.get_field("classname", "") or ""
            if test_name:
                display_id = test_name
            elif classname:
                display_id = classname.split(".")[-1]
            else:
                display_id = (
                    node.id.split(INSTANCE_SEPARATOR)[-1]
                    if INSTANCE_SEPARATOR in node.id
                    else node.id[-30:]
                )

            row = TreeRow(
                id=f"{node.id}_0_root",
                display_id=display_id,
                title=node.get_label() or "",
                level="",
                status="",
                coverage="none",
                topic="",
                depth=0,
                parent_id=None,
                assertions=[],
                is_leaf=True,
                is_changed=False,
                is_uncommitted=False,
                is_unsaved=False,
                has_children=False,
                has_failures=result_status in ("failed", "fail", "failure", "error"),
                is_associated=False,
                result_status=result_status,
            )
            rows.append(row)

        return rows

    def _collect_unique_values(self, field_name: str) -> set[str]:
        """Collect unique values for a field across all requirements."""
        from elspais.graph import NodeKind

        values: set[str] = set()
        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            if field_name == "status":
                val = (node.status or "").upper()
            elif field_name == "topic":
                val = self._get_topic_for_node(node)
            else:
                val = node.get_field(field_name, "")
            if val:
                values.add(val)
        return values

    def _get_topic_for_node(self, node: GraphNode) -> str:
        """Extract topic from file path."""
        _fn = node.file_node()
        if not _fn:
            return ""
        path = _fn.get_field("relative_path") or ""
        filename = Path(path).stem
        for prefix in ("prd-", "ops-", "dev-"):
            if filename.lower().startswith(prefix):
                return filename[len(prefix) :]
        return filename

    def _build_tree_data(self) -> dict[str, Any]:
        """Build tree data structure for embedded JSON."""
        from elspais.graph import NodeKind

        data: dict[str, Any] = {}
        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            vc, vt = compute_validation_color(node)
            data[node.id] = {
                "id": node.id,
                "label": node.get_label(),
                "uuid": node.uuid,
                "level": (node.level or "").upper(),
                "status": node.status,
                "hash": node.hash,
                "validation_color": vc,
                "validation_tip": vt,
                "source": {
                    "path": (
                        node.file_node().get_field("relative_path") if node.file_node() else None
                    ),
                    "line": node.get_field("parse_line"),
                },
            }
        return data

    def _build_node_index(self) -> dict[str, Any]:
        """Build node index for embedded JSON — matches /api/node/<id> response shape.

        Delegates to the MCP server's _serialize_node_generic() to produce
        identical JSON as the live API, ensuring view mode and edit mode
        see the same data structure.
        """
        from elspais.mcp.server import _serialize_node_generic

        index: dict[str, Any] = {}
        for node in self.graph.all_nodes():
            index[node.id] = _serialize_node_generic(node, self.graph)
        return index

    def _build_coverage_index(self) -> dict[str, Any]:
        """Build per-requirement coverage index for embedded JSON.

        Each entry is keyed by requirement ID and contains both test coverage
        (matching /api/test-coverage/<id>) and code coverage
        (matching /api/code-coverage/<id>) response shapes.
        """
        from elspais.graph import NodeKind
        from elspais.mcp.server import (
            _get_assertion_code_map,
            _get_assertion_refines_map,
            _get_assertion_test_map,
        )

        index: dict[str, Any] = {}
        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            index[node.id] = {
                "test": _get_assertion_test_map(self.graph, node.id),
                "code": _get_assertion_code_map(self.graph, node.id),
                "code_implements": _get_assertion_code_map(
                    self.graph, node.id, edge_kind="implements"
                ),
                "refines": _get_assertion_refines_map(self.graph, node.id),
            }
        return index

    def _build_status_data(self) -> dict[str, Any]:
        """Build graph status data for embedded JSON — matches /api/status response shape."""
        from elspais.mcp.server import _get_graph_status

        return _get_graph_status(self.graph)

    def _collect_source_files(self) -> dict[str, Any]:
        """Collect source file contents with syntax highlighting for inline viewer.

        Walks all graph nodes, reads unique source files, and applies Pygments
        syntax highlighting at generation time. The pre-highlighted HTML is
        embedded in the output so the browser needs no JS highlighting library.

        Returns:
            Dict mapping file paths to their content data:
            {path: {lines: [highlighted_html_per_line], language: str, raw: str}}
        """
        from elspais.html.highlighting import MAX_FILE_SIZE, highlight_file_content

        # Collect unique source paths from all nodes
        paths: set[str] = set()
        for node in self.graph.all_nodes():
            _fn = node.file_node()
            _rp = _fn.get_field("relative_path") if _fn else None
            if _rp:
                paths.add(_rp)

        result: dict[str, Any] = {}
        for path in sorted(paths):
            try:
                file_path = Path(path)
                if not file_path.is_absolute() and self.graph.repo_root:
                    file_path = self.graph.repo_root / file_path
                if not file_path.is_file():
                    continue

                # Skip files that are too large
                if file_path.stat().st_size > MAX_FILE_SIZE:
                    continue

                # Skip binary files (check first 8KB for null bytes)
                with open(file_path, "rb") as f:
                    chunk = f.read(8192)
                    if b"\x00" in chunk:
                        continue

                raw_content = file_path.read_text(encoding="utf-8", errors="replace")
                result[path] = highlight_file_content(path, raw_content)
            except (OSError, UnicodeDecodeError):
                continue

        return result

    def _get_pygments_css(self) -> str:
        """Generate Pygments CSS theme for syntax highlighting.

        Returns CSS rules scoped under .highlight for the file viewer panel.
        Returns empty string if Pygments is not installed.
        """
        from elspais.html.highlighting import get_pygments_css

        return get_pygments_css()

    def _get_pygments_css_dark(self) -> str:
        """Generate dark-theme Pygments CSS for syntax highlighting.

        Returns CSS rules scoped under .theme-dark .highlight for the
        file viewer panel when dark theme is active.
        Returns empty string if Pygments is not installed.
        """
        from elspais.html.highlighting import get_pygments_css

        return get_pygments_css(style="monokai", scope=".theme-dark .highlight")

    def _collect_journeys(self) -> list[JourneyItem]:
        """Collect all user journey nodes for the journeys tab."""
        from elspais.graph import NodeKind
        from elspais.graph.relations import EdgeKind

        journeys: list[JourneyItem] = []

        for node in self.graph.nodes_by_kind(NodeKind.USER_JOURNEY):
            # Extract description from body or other fields
            description = node.get_field("body", "") or node.get_field("description", "")
            if not description and node.get_label():
                # Use label as title, look for body content
                description = ""

            # Extract actor and goal fields from parsed journey data
            actor = node.get_field("actor")
            goal = node.get_field("goal")

            # Extract descriptor from journey ID: JNY-{descriptor}-{number}
            descriptor = ""
            match = JNY_ID_PATTERN.match(node.id)
            if match:
                descriptor = match.group("descriptor")

            # Extract file from FILE parent node
            file = ""
            _fn = node.file_node()
            if _fn:
                _rp = _fn.get_field("relative_path") or ""
                file = Path(_rp).name if _rp else ""

            # Extract referenced requirements from incoming VALIDATES edges
            referenced_reqs = sorted(
                e.source.id for e in node.iter_incoming_edges() if e.kind == EdgeKind.VALIDATES
            )

            # Structured fields for edit mode
            context = node.get_field("context")
            body_lines = node.get_field("body_lines", [])
            preamble = "\n".join(body_lines) if body_lines else ""
            sections = node.get_field("sections", [])
            file_id = _fn.id if _fn else ""
            file_line = node.get_field("parse_line")

            journeys.append(
                JourneyItem(
                    id=node.id,
                    title=node.get_label() or node.id,
                    description=description,
                    actor=actor,
                    goal=goal,
                    context=context,
                    descriptor=descriptor,
                    file=file,
                    file_id=file_id,
                    file_line=file_line,
                    preamble=preamble,
                    sections=sections,
                    referenced_reqs=referenced_reqs,
                )
            )

        # Sort by ID for consistent ordering
        journeys.sort(key=lambda j: j.id)
        return journeys


__all__ = ["HTMLGenerator", "compute_validation_color"]
