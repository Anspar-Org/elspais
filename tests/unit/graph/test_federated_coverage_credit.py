# Verifies: REQ-d00269-A, REQ-d00269-B
"""Coverage credit crossing a repository boundary.

A federation of two real on-disk repositories, where every traceability
keyword valid in a consumer repository names a target in the library
repository. The library requirement's rollup is the measurement: it must
report the coverage those references justify, and the library built on its
own must be unaffected.
"""

from __future__ import annotations

import pytest

from elspais.graph.annotators import annotate_coverage, annotate_journey_verification
from elspais.graph.factory import _derive_credit_config, _validate_config, build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.metrics import integrates_rollup
from elspais.graph.relations import EdgeKind
from tests.federation_repos import _git, make_repo

LIB_TOML = """version = 3

[project]
name = "lib"
namespace = "LIB"

[levels.prd]
rank = 1
implements = []

[levels.dev]
rank = 2
implements = ["prd", "dev"]

[scanning.test]
enabled = true
"""

APP_TOML = """version = 3

[project]
name = "app"
namespace = "APP"

[levels.prd]
rank = 1
implements = []

[levels.dev]
rank = 2
implements = ["prd", "dev"]

[scanning.test]
enabled = true

[[scanning.test.targets]]
name = "pytest"
reporter = "junit"
results = "results/*.xml"
match = "source"

[associates.lib]
path = "../lib"
namespace = "LIB"
"""

LIB_SPEC = """# Lib spec

## LIB-d00001: Library thing

**Status**: active

The library shall do a thing.

### Assertions

A. The system SHALL do the A thing.

B. The system SHALL do the B thing.

C. The system SHALL do the C thing.

D. The system SHALL do the D thing.

*End*

## LIB-d00003: Library integrated thing

**Status**: active

The library shall provide an integrated thing.

### Assertions

A. The system SHALL integrate the A thing.

*End*
"""

LIB_CODE = '''"""Lib code."""


# Implements: LIB-d00003-A
def lib_integrated():
    return 0
'''

APP_SPEC = """# App spec

## APP-d00003: App integrating thing

**Status**: active

**Integrates**: LIB-d00003

The app shall integrate the library thing.

### Assertions

A. The system SHALL rely on the library.

*End*
"""

APP_REFINE = """# App refinement

## APP-d00002: Refining thing

**Status**: active

**Refines**: LIB-d00001-C

The app shall refine the C thing.

### Assertions

A. The system SHALL refine.

*End*
"""

APP_JNY = """# User Journeys

---

### JNY-OQ-App-01: App journey

**Actor**: End User
**Goal**: Exercise the library

## Validates

Validates: LIB-d00001-D

*End* *JNY-OQ-App-01*
---
"""

APP_CODE = '''"""App code."""


# Implements: LIB-d00001-A
def do_a():
    return 1


# Implements: APP-d00002-A
def app_refiner():
    return 3
'''

APP_TEST = '''"""App tests."""


# Verifies: LIB-d00001-B
def test_lib_b():
    assert True
'''

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1" failures="0" errors="0">
<testcase classname="tests.test_lib" name="test_lib_b" file="tests/test_lib.py" line="4"/>
</testsuite></testsuites>
"""


@pytest.fixture(scope="module")
def federation(tmp_path_factory):
    """Two on-disk repos: a library, and an app that references it."""
    base = tmp_path_factory.mktemp("fed")
    lib = make_repo(base, "lib", namespace="LIB", config_text=LIB_TOML)
    (lib / "spec" / "reqs.md").write_text(LIB_SPEC, encoding="utf-8")
    (lib / "src").mkdir()
    (lib / "src" / "lib_impl.py").write_text(LIB_CODE, encoding="utf-8")
    _git(lib, "add", "-A")
    _git(lib, "commit", "-m", "spec")

    app = make_repo(base, "app", namespace="APP", config_text=APP_TOML)
    (app / "spec" / "reqs.md").write_text(APP_SPEC, encoding="utf-8")
    (app / "spec" / "refine.md").write_text(APP_REFINE, encoding="utf-8")
    (app / "spec" / "journey.md").write_text(APP_JNY, encoding="utf-8")
    (app / "src").mkdir()
    (app / "src" / "impl.py").write_text(APP_CODE, encoding="utf-8")
    (app / "tests").mkdir()
    (app / "tests" / "test_lib.py").write_text(APP_TEST, encoding="utf-8")
    (app / "results").mkdir()
    (app / "results" / "junit.xml").write_text(JUNIT, encoding="utf-8")
    _git(app, "add", "-A")
    _git(app, "commit", "-m", "code")
    return app, lib


@pytest.fixture(scope="module")
def federated(federation):
    app, _lib = federation
    return build_graph(repo_root=app)


@pytest.fixture(scope="module")
def alone(federation):
    _app, lib = federation
    return build_graph(repo_root=lib)


def _metrics(graph, req_id):
    return graph.find_by_id(req_id).get_metric("rollup_metrics")


# Verifies: REQ-d00269-A, REQ-d00269-B
@pytest.mark.parametrize(
    "dimension,label,covered",
    [
        # consumer CODE --Implements--> library assertion A; C is covered in
        # the same dimension by the refining requirement (its own test below).
        ("implemented", "A", {"A", "C"}),
        ("tested", "B", {"B"}),  # consumer TEST --Verifies--> library assertion
        ("verified", "B", {"B"}),  # that test's passing result
        ("uat_coverage", "D", {"D"}),  # consumer JNY --Validates--> library assertion
    ],
)
def test_cross_repo_evidence_credits_the_named_assertion(federated, dimension, label, covered):
    """Evidence recorded in the app credits exactly the library assertion it names."""
    dim = getattr(_metrics(federated, "LIB-d00001"), dimension)
    assert dim.direct_pct_by_label[label] == 1.0
    assert {lbl for lbl, v in dim.direct_pct_by_label.items() if v > 0} == covered


# Verifies: REQ-d00269-A
def test_cross_repo_refines_conducts_coverage(federated):
    """A refining requirement in the app conducts its own coverage into the
    library assertion it refines -- which only one computation spanning both
    repositories can do."""
    dim = _metrics(federated, "LIB-d00001").implemented
    assert dim.direct_pct_by_label["C"] == 1.0


# Verifies: REQ-d00269-B
def test_cross_repo_edge_hangs_off_the_owning_requirement(federated):
    """The edge carries the same shape as a same-repository one: it is
    outgoing from the requirement that owns the assertion, and it names that
    assertion."""
    req = federated.find_by_id("LIB-d00001")
    shapes = {
        (e.kind, tuple(e.assertion_targets))
        for e in req.iter_outgoing_edges()
        if e.kind != EdgeKind.STRUCTURES
    }
    assert (EdgeKind.IMPLEMENTS, ("A",)) in shapes
    assert (EdgeKind.VERIFIES, ("B",)) in shapes
    assert (EdgeKind.REFINES, ("C",)) in shapes
    assert (EdgeKind.VALIDATES, ("D",)) in shapes

    assertion = federated.find_by_id("LIB-d00001-A")
    hung_on_assertion = [
        e.kind for e in assertion.iter_outgoing_edges() if e.kind != EdgeKind.STRUCTURES
    ]
    assert hung_on_assertion == []


# Verifies: REQ-d00269-A
def test_library_built_alone_is_unaffected(alone):
    """The library on its own has no such evidence and must report none."""
    metrics = _metrics(alone, "LIB-d00001")
    for dimension in ("implemented", "tested", "verified", "uat_coverage"):
        dim = getattr(metrics, dimension)
        assert dim.direct == 0.0
        assert dim.indirect == 0.0
    assert metrics.assertion_coverage == {}


# Verifies: REQ-d00269-A
def test_recomputation_does_not_double_count(federated):
    """Coverage over a wired federation is idempotent, so a surface may
    recompute without inflating the numbers."""
    before = _metrics(federated, "LIB-d00001")
    snapshot = {
        d: (getattr(before, d).direct, getattr(before, d).indirect)
        for d in ("implemented", "tested", "verified", "uat_coverage")
    }
    contributions = {k: len(v) for k, v in before.assertion_coverage.items()}

    targets = []
    for entry in federated._repos.values():
        if entry.graph is not None and entry.config is not None:
            targets.extend(_validate_config(entry.config).scanning.test.targets)
    annotate_journey_verification(federated)
    annotate_coverage(federated, _derive_credit_config(targets))

    after = _metrics(federated, "LIB-d00001")
    assert {d: (getattr(after, d).direct, getattr(after, d).indirect) for d in snapshot} == snapshot
    assert {k: len(v) for k, v in after.assertion_coverage.items()} == contributions


# Verifies: REQ-d00269-A
def test_integrates_credit_stays_with_its_overlay(federated):
    """An `Integrates:` reference credits the consumer through its own live
    rollup. Recomputing coverage over the wired federation must not fold the
    same library evidence into the consumer's own dimensions as well."""
    consumer = federated.find_by_id("APP-d00003")
    own = consumer.get_metric("rollup_metrics")
    assert own.implemented.direct == 0.0
    assert own.implemented.indirect == 0.0
    assert own.assertion_coverage == {}

    inherited = integrates_rollup(consumer)
    assert inherited.implemented_covered == 1.0
    assert inherited.implemented_total == 1


# Verifies: REQ-d00269-B
def test_foreign_reference_is_not_left_broken(federated):
    """A reference the federation resolves is no longer a broken reference in
    the repository that wrote it."""
    app_graph = federated._repos["app"].graph
    unresolved = {
        (b.source_id, b.target_id)
        for b in app_graph._broken_references
        if b.target_id.startswith("LIB-")
    }
    assert unresolved == set()


# Verifies: REQ-d00269-B
def test_cross_repo_nodes_are_reachable_from_the_library_requirement(federated):
    """The library requirement reaches the app's evidence nodes directly, so
    one traversal serves both repositories."""
    req = federated.find_by_id("LIB-d00001")
    reached = {e.target.kind for e in req.iter_outgoing_edges()}
    assert NodeKind.CODE in reached
    assert NodeKind.TEST in reached
    assert NodeKind.USER_JOURNEY in reached
