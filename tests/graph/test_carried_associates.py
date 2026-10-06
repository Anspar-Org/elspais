"""Carried provenance across a federation.

A run of the invoking repository's targets executes no target of another
member, so a selection of fresh targets leaves every associate result
carried. Two members may each declare a target of one name, and the carried
tally counts those as two targets rather than one.

The project here is a root repository (namespace REQ) federating one
associate (namespace ASC). Both declare a target named ``a``; the root also
declares ``b`` and the associate ``z``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from elspais.graph.aggregation import collect_coverage
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind, parse_structural_id
from tests.core.graph_test_helpers import record_run

_SPEC = """\
# Requirements

---

### {ns}-d00001: {ns} One

The system SHALL do one.

## Assertions

A. The system SHALL do one.

*End* *{ns} One*
---

### {ns}-d00002: {ns} Two

The system SHALL do two.

## Assertions

A. The system SHALL do two.

*End* *{ns} Two*
---
"""

_CONFIG = """\
version = 5

[project]
name = "{name}"
namespace = "{ns}"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{{namespace}}-{{level.letter}}{{component}}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]

[[scanning.test.targets]]
name = "a"
reporter = "junit"
results = "results.xml"
match = "source"

[[scanning.test.targets]]
name = "{second}"
reporter = "junit"
results = "results.xml"
match = "source"

[rules.hierarchy]
allow_circular = false
allow_structural_orphans = true

[rules.format]
require_hash = false
require_assertions = false
require_status = false
{extra}"""

_ASSOCIATE_DECLARATION = """
[associates.asc]
path = "../assoc"
namespace = "ASC"
"""

_RESULTS = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="{suite}" tests="1">
  <testcase name="{test}" classname="tests.{test}" time="0.01"/>
</testsuite>
"""


def _make_repo(
    root: Path,
    *,
    name: str,
    ns: str,
    second: str,
    tests: tuple[str, str],
    extra: str = "",
) -> None:
    """Write one repository: two requirements, each verified by one target.

    ``tests`` names the test of target ``a`` and of target ``second``. Each
    repository spells its own test names, because a test node id is not
    namespaced and two members holding one test name would collide.
    """
    (root / "spec").mkdir(parents=True)
    (root / "spec" / "reqs.md").write_text(_SPEC.format(ns=ns), encoding="utf-8")
    (root / "tests").mkdir()
    for number, test in enumerate(tests, start=1):
        (root / "tests" / f"{test}.py").write_text(
            f"# Verifies: {ns}-d0000{number}-A\ndef {test}():\n    pass\n",
            encoding="utf-8",
        )
    (root / ".elspais.toml").write_text(
        _CONFIG.format(name=name, ns=ns, second=second, extra=extra), encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    # Each target's results come from a run of this tree, so they are fresh
    # and only the fresh-target selection carries any of them.
    for target, test in zip(("a", second), tests, strict=True):
        record_run(
            root, target, {"results.xml": _RESULTS.format(suite=f"{name}-{target}", test=test)}
        )


@pytest.fixture
def federation(tmp_path: Path) -> Path:
    """A root repository federating one associate; returns the root."""
    root = tmp_path / "root"
    _make_repo(
        root,
        name="root",
        ns="REQ",
        second="b",
        tests=("test_root_a", "test_root_b"),
        extra=_ASSOCIATE_DECLARATION,
    )
    _make_repo(
        tmp_path / "assoc",
        name="assoc",
        ns="ASC",
        second="z",
        tests=("test_asc_a", "test_asc_z"),
    )
    return root


def _build(root: Path, fresh_targets: set[str] | None):
    return build_graph(
        config_path=root / ".elspais.toml",
        repo_root=root,
        fresh_targets=fresh_targets,
    )


def _results_by_member(graph) -> dict[str, dict[str, bool]]:
    """Each member's RESULT nodes as ``{namespace: {target: carried}}``."""
    found: dict[str, dict[str, bool]] = {}
    for node in graph.iter_by_kind(NodeKind.RESULT):
        namespace = parse_structural_id(node.id)[1]
        found.setdefault(namespace, {})[node.get_field("target")] = bool(node.get_field("carried"))
    return found


# Verifies: REQ-d00323-D
@pytest.mark.parametrize(
    "fresh_targets",
    [
        pytest.param({"a"}, id="root-target-sharing-the-associate-target-name"),
        pytest.param({"b"}, id="root-target-of-its-own-name"),
        pytest.param(set(), id="no-target-fresh"),
    ],
)
def test_every_associate_result_is_carried_when_a_run_names_fresh_targets(
    federation: Path, fresh_targets: set[str]
) -> None:
    """Naming a root target fresh, even ``a``, freshens no associate result."""
    results = _results_by_member(_build(federation, fresh_targets))

    assert results["ASC"] == {"a": True, "z": True}
    assert results["REQ"] == {t: t not in fresh_targets for t in ("a", "b")}


# Verifies: REQ-d00323-D
def test_no_result_is_carried_when_a_run_names_no_fresh_targets(federation: Path) -> None:
    """A read that names no selection marks nothing carried in any member."""
    results = _results_by_member(_build(federation, None))

    assert results == {"REQ": {"a": False, "b": False}, "ASC": {"a": False, "z": False}}


# Verifies: REQ-d00323-D
def test_an_associate_requirement_credited_by_a_carried_result_is_marked_carried(
    federation: Path,
) -> None:
    """The associate's own target ``a`` is carried though the root's ``a`` ran."""
    graph = _build(federation, {"a"})

    assert graph.find_by_id("ASC-d00001").get_metric("rollup_metrics").verified.carried
    root_one = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics").verified
    assert root_one.carried is False


# Verifies: REQ-d00323-E
@pytest.mark.parametrize(
    ("fresh_targets", "total", "carried"),
    [
        # Root a fresh; root b, associate a and associate z carried. Counted by
        # name alone, the two `a` targets would collapse into one.
        pytest.param({"a"}, 4, 3, id="shared-name-fresh-in-root"),
        pytest.param(set(), 4, 4, id="all-carried"),
        pytest.param({"a", "b"}, 4, 2, id="every-root-target-fresh"),
    ],
)
def test_the_carried_tally_counts_each_member_target_separately(
    federation: Path, fresh_targets: set[str], total: int, carried: int
) -> None:
    """Two members' targets of one name are two targets in the tally."""
    payload = collect_coverage(_build(federation, fresh_targets))

    assert payload["total_result_targets"] == total
    assert payload["carried_result_targets"] == carried


# Verifies: REQ-d00323-E
def test_the_tally_is_absent_when_a_run_names_no_fresh_targets(federation: Path) -> None:
    """Without a selection there is no carried provenance to state."""
    payload = collect_coverage(_build(federation, None))

    assert "total_result_targets" not in payload
    assert "carried_result_targets" not in payload
