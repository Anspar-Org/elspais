# Verifies: REQ-d00258-C, REQ-d00258-M
"""The one work-list verdict `gaps` and the health coverage checks both reach.

Neither surface may decide for itself which assertions still want evidence:
REQ-d00258-C binds a surface reaching a coverage verdict to the one shared
aggregation, and REQ-d00258-M says that verdict is read on the immediate
direct measure. When each surface derived it separately they disagreed -- a
requirement a journey validated by name only was listed by `gaps unvalidated`
with its uncovered assertions while the health `uat.coverage` check passed
green.

This repository configures no level with `expects_validation`, so the
canonical fixtures cannot reach the UAT branch at all; every graph here is
built from a project written for the purpose.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from elspais.commands.gaps import collect_gaps
from elspais.commands.health import check_uat_coverage
from elspais.config import load_config
from elspais.graph.factory import build_graph

_JOURNEY_UAT_FIX = Path(__file__).parents[1] / "fixtures" / "journey-uat"

# A project whose `prd` level expects validation, so the UAT branch of both
# surfaces is live (REQ-d00258-F).
_UAT_CONFIG = """
version = 3

[project]
name = "work-list-verdict"
namespace = "REQ"

[levels.prd]
rank = 1
expects_validation = true
implements = []

[levels.dev]
rank = 2
implements = ["prd"]
"""

# Three requirements differing only in how a journey cites them: one named by
# a journey that names the REQUIREMENT alone, one no journey visits, one whose
# journey names every *Assertion*.
_UAT_SPEC = """# Requirements

## REQ-p00001: Blanket Journey Target

**Level**: PRD | **Status**: Active | **Implements**: -

A journey names this requirement but neither of its assertions.

### Assertions

A. Alpha SHALL hold.

B. Beta SHALL hold.

*End* *Blanket Journey Target* | **Hash**: 00000000

## REQ-p00002: Unvisited

**Level**: PRD | **Status**: Active | **Implements**: -

No journey names this requirement at all.

### Assertions

A. Alpha SHALL hold.

B. Beta SHALL hold.

*End* *Unvisited* | **Hash**: 00000000

## REQ-p00003: Named Per Assertion

**Level**: PRD | **Status**: Active | **Implements**: -

A journey names each *Assertion* of this requirement.

### Assertions

A. Alpha SHALL hold.

B. Beta SHALL hold.

*End* *Named Per Assertion* | **Hash**: 00000000
"""

_UAT_JOURNEYS = """# User Journeys

## JNY-001: Blanket Journey

**Actor**: user | **Goal**: exercise the requirement as a whole
Validates: REQ-p00001

### Step 1

Do the thing.

*End* *JNY-001* | **Hash**: 00000000

## JNY-003: Per-Assertion Journey

**Actor**: user | **Goal**: exercise each assertion
Validates: REQ-p00003-A+B

### Step 1

Do the thing.

*End* *JNY-003* | **Hash**: 00000000
"""


@pytest.fixture(scope="module")
def uat_project(tmp_path_factory: pytest.TempPathFactory):
    """Build the expects_validation project once; return (graph, config)."""
    root = tmp_path_factory.mktemp("uat-verdict")
    (root / ".elspais.toml").write_text(_UAT_CONFIG)
    (root / "spec").mkdir()
    (root / "spec" / "requirements.md").write_text(_UAT_SPEC)
    (root / "spec" / "journeys.md").write_text(_UAT_JOURNEYS)
    graph = build_graph(
        config_path=root / ".elspais.toml",
        repo_root=root,
        scan_code=False,
        scan_tests=False,
    )
    return graph, load_config(root / ".elspais.toml")


# Verifies: REQ-d00258-C, REQ-d00258-F, REQ-d00258-M
def test_gaps_and_health_agree_about_a_blanket_journey(uat_project) -> None:
    """Both surfaces report the SAME assertions for a blanket `Validates:`.

    REQ-d00258-F names `gaps unvalidated` and the health `uat.coverage` check
    together as the two ways a UAT gap is reported, and REQ-d00258-C requires
    one verdict behind both. A journey naming only the requirement leaves
    every *Assertion* uncited on the immediate direct measure (REQ-d00258-M),
    so the two must name the same assertions -- the assertions are read out of
    the gap entry and looked for in the health finding rather than restated,
    so either surface drifting from the other fails this.
    """
    graph, cfg = uat_project

    entries = {e.req_id: e for e in collect_gaps(graph, set(), cfg).unvalidated}
    assert "REQ-p00001" in entries
    labels = sorted(label for _aid, label, _frac in entries["REQ-p00001"].assertions)
    assert labels == ["A", "B"]
    assert [aid for aid, _label, _frac in entries["REQ-p00001"].assertions] == [
        "REQ-p00001-A",
        "REQ-p00001-B",
    ]

    check = check_uat_coverage(graph, set(), cfg)
    findings = [f for f in check.findings if f.node_id == "REQ-p00001"]
    assert len(findings) == 1, "health must report the requirement gaps lists"
    assert f"assertion(s) {', '.join(labels)}" in findings[0].message
    assert not check.passed


# Verifies: REQ-d00258-C, REQ-d00258-M
@pytest.mark.parametrize(
    ("req_id", "attached", "uncovered"),
    [
        # No journey visits it: nothing is attached, and every *Assertion* is
        # work.
        ("REQ-p00002", False, {"A": 0.0, "B": 0.0}),
        # A journey names the requirement: evidence IS attached here, and
        # every *Assertion* is still work.
        ("REQ-p00001", True, {"A": 0.0, "B": 0.0}),
        # A journey names each *Assertion*: attached, and nothing left.
        ("REQ-p00003", True, {}),
    ],
)
def test_attached_and_needs_work_are_independent_signals(
    uat_project, req_id: str, attached: bool, uncovered: dict[str, float]
) -> None:
    """`attached` and `needs_work` answer different questions.

    Whether ANY evidence sits at the requirement (read on the immediate
    measures) does not settle whether every *Assertion* has a citation naming
    it (read on the work-list measure, REQ-d00258-M). A surface reading only
    the first says nothing about a blanket-validated requirement, which is
    exactly how the two surfaces came to disagree.
    """
    from elspais.graph.aggregation import work_verdict

    graph, _cfg = uat_project
    rollup = graph.find_by_id(req_id).get_metric("rollup_metrics")

    verdict = work_verdict(rollup, "uat_coverage", ["A", "B"])

    assert verdict.attached is attached
    assert verdict.uncovered == uncovered
    assert verdict.needs_work is bool(uncovered)


# Verifies: REQ-d00069-M, REQ-d00255-C, REQ-d00258-I, REQ-d00258-M
def test_partial_uat_verification_is_uncovered_and_keeps_its_fraction(
    tmp_path: Path,
) -> None:
    """A partly verified journey is still work, and says how far it got.

    The `untested-step` fixture's journey has three steps of which two are
    verified by passing tests, so it credits `uat_verified` in proportion
    (REQ-d00255-C, REQ-d00069-M). Two thirds is not covered (REQ-d00258-M),
    and the fraction is carried so a worklist can tell it from an *Assertion*
    with no evidence at all.

    The same call exercises the relative denominator (REQ-d00258-I): the
    fixture's journey names assertion A only, so B -- outside `uat_coverage`
    -- is not reported as a verification gap, though it is uncovered when the
    dimension is read absolutely.
    """
    from elspais.graph.aggregation import work_verdict

    dest = tmp_path / "proj"
    shutil.copytree(_JOURNEY_UAT_FIX / "untested-step", dest)
    spec = dest / "spec" / "requirements.md"
    spec.write_text(
        spec.read_text().replace(
            "A. The system SHALL accept valid credentials.",
            "A. The system SHALL accept valid credentials.\n\n"
            "B. The system SHALL refuse invalid credentials.",
        )
    )
    graph = build_graph(repo_root=dest)
    rollup = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics")

    restricted = work_verdict(
        rollup, "uat_verified", ["A", "B"], restrict_to_dimension="uat_coverage"
    )
    assert set(restricted.uncovered) == {"A"}
    assert restricted.uncovered["A"] == pytest.approx(2 / 3)
    assert restricted.attached is True

    absolute = work_verdict(rollup, "uat_verified", ["A", "B"])
    assert absolute.uncovered["B"] == 0.0


# --- The relative denominator on the implemented/tested chain --------------

_CHAIN_CONFIG = """
version = 3

[project]
name = "work-list-chain"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]
"""

_CHAIN_SPEC = """# Requirements

## REQ-d00001: Partly Built

**Level**: dev | **Status**: Active | **Implements**: -

One *Assertion* is built and untested; the other is not built at all.

### Assertions

A. Alpha SHALL hold.

B. Beta SHALL hold.

*End* *Partly Built* | **Hash**: 00000000
"""


# Verifies: REQ-d00258-I, REQ-d00258-M
def test_unimplemented_assertion_is_not_a_testing_gap(tmp_path: Path) -> None:
    """Testing gaps are measured over what is implemented (REQ-d00258-I).

    A is implemented and untested; B is not built at all. B is an
    implementation gap, and reporting it as a testing gap as well would
    measure a figure over a denominator it is not in. Both the verdict and
    the `gaps` surface reading it hold that line.
    """
    from elspais.graph.aggregation import work_verdict

    root = tmp_path / "proj"
    (root / "spec").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / ".elspais.toml").write_text(_CHAIN_CONFIG)
    (root / "spec" / "requirements.md").write_text(_CHAIN_SPEC)
    (root / "src" / "mod.py").write_text("# Implements: REQ-d00001-A\ndef alpha():\n    pass\n")

    graph = build_graph(config_path=root / ".elspais.toml", repo_root=root)
    cfg = load_config(root / ".elspais.toml")
    rollup = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics")

    restricted = work_verdict(rollup, "tested", ["A", "B"], restrict_to_dimension="implemented")
    assert set(restricted.uncovered) == {"A"}
    # Read absolutely the unbuilt *Assertion* is untested too -- the
    # denominator is what keeps it out of the testing worklist.
    assert set(work_verdict(rollup, "tested", ["A", "B"]).uncovered) == {"A", "B"}

    data = collect_gaps(graph, set(), cfg)
    untested = {e.req_id: [label for _aid, label, _frac in e.assertions] for e in data.untested}
    uncovered = {e.req_id: [label for _aid, label, _frac in e.assertions] for e in data.uncovered}
    assert untested == {"REQ-d00001": ["A"]}
    assert uncovered == {"REQ-d00001": ["B"]}
