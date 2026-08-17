# Verifies: REQ-d00269-F, REQ-p00019-J, REQ-p00019-K, REQ-d00241-E
"""The reference checks report each class under a description true of it."""

from __future__ import annotations

import pathlib

import pytest

from elspais.commands.health import run_checks
from elspais.graph.reference_faults import FaultClass


def _names(checks):
    return {c.name for c in checks}


@pytest.fixture(scope="module")
def repo_root():
    return pathlib.Path(__file__).resolve().parents[2]


# A code file carrying one item of each fault class:
#   - "not a reference" has a space, so it never reads as an identifier
#     at all: MALFORMED.
#   - "ZZZ-d00001-A" is identifier-shaped but no configured repository
#     declares the "ZZZ" namespace: UNKNOWN_NAMESPACE.
#   - "REQ-d09999" is claimed by this repo's own grammar but names no
#     requirement it holds: UNKNOWN_REQUIREMENT.
#   - "REQ-d00001-Z" claims an existing requirement but a label it does
#     not carry: UNKNOWN_ASSERTION.
#   - "Refines:" is not a valid keyword in a code file: FORBIDDEN.
_CODE = """# Implements: not a reference
def f1():
    pass


# Implements: ZZZ-d00001-A
def f2():
    pass


# Implements: REQ-d09999
def f3():
    pass


# Implements: REQ-d00001-Z
def f4():
    pass


# Refines: REQ-d00001
def f5():
    pass


# REQ-d00001-A: this prose cites a requirement without declaring anything,
# which is a relationship its author appears to intend and has not spelled.
def f6():
    pass
"""


@pytest.fixture(scope="module")
def _project_dir(tmp_path_factory, repo_root):
    tmp_path = tmp_path_factory.mktemp("faulted")
    (tmp_path / ".elspais.toml").write_text((repo_root / ".elspais.toml").read_text())
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "r.md").write_text(
        "# REQ-d00001: Thing\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. The system SHALL do a thing.\n\n"
        "B. The system SHALL do another.\n\n"
        "*End* *Thing* | **Hash**: 00000000\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "m.py").write_text(_CODE)
    return tmp_path


@pytest.fixture(scope="module")
def faulted_graph(_project_dir):
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    config_path = _project_dir / ".elspais.toml"
    return build_graph(
        load_config(config_path),
        config_path=config_path,
        repo_root=_project_dir,
        scan_code=True,
        scan_tests=False,
    )


@pytest.fixture
def config(_project_dir):
    from elspais.config import load_config

    return load_config(_project_dir / ".elspais.toml")


# Verifies: REQ-p00019-J
def test_a_malformed_item_is_not_reported_as_an_unclaimed_repository(faulted_graph, config):
    checks = run_checks(faulted_graph, config)
    malformed = next(c for c in checks if c.name == "references.malformed")
    assert any("not a reference" in f.message for f in malformed.findings)
    ns = next(c for c in checks if c.name == "references.unknown_namespace")
    assert not any("not a reference" in f.message for f in ns.findings)


# Verifies: REQ-d00269-F
def test_each_class_carries_its_own_severity(faulted_graph, config):
    config["rules"]["references"]["unknown_namespace"] = "ok"
    config["rules"]["references"]["malformed"] = "error"
    checks = run_checks(faulted_graph, config)
    assert next(c for c in checks if c.name == "references.unknown_namespace").severity == "ok"
    assert next(c for c in checks if c.name == "references.malformed").severity == "error"


# Verifies: REQ-p00019-K
def test_a_fault_is_reported_under_one_check_only(faulted_graph, config):
    checks = run_checks(faulted_graph, config)
    seen = []
    for c in checks:
        if c.name.startswith("references."):
            seen.extend(f.message for f in c.findings)
    assert len(seen) == len(set(seen))


# Verifies: REQ-d00241-E
def test_a_file_whose_references_all_failed_is_not_called_unmarked(faulted_graph, config):
    checks = run_checks(faulted_graph, config)
    no_trace = next(c for c in checks if c.name == "code.no_traceability")
    assert not any("m.py" in f.message for f in no_trace.findings)


# Verifies: REQ-d00269-F, REQ-p00019-J
def test_every_fault_class_is_populated_by_this_fixture(faulted_graph, config):
    """Sanity check on the fixture itself: every class this test file
    exercises actually produced a fault, so the assertions above are not
    vacuously true."""
    checks = run_checks(faulted_graph, config)
    for name in (
        "references.malformed",
        "references.unknown_namespace",
        "references.unknown_requirement",
        "references.unknown_assertion",
        "references.forbidden",
    ):
        check = next(c for c in checks if c.name == name)
        assert check.findings, f"{name} produced no finding; fixture no longer exercises it"


# Verifies: REQ-p00019-K
def test_reference_fault_classes_partition_the_broken_references(faulted_graph):
    """Every broken reference the graph recorded lands in exactly one of
    the five classes -- the classification is total, not merely disjoint
    on the fixture's five hand-picked examples."""
    all_classes = {f.fault_class for f in faulted_graph.broken_references()}
    assert all_classes <= set(FaultClass)


# Verifies: REQ-d00272-O
def test_an_informal_citation_is_reported_as_an_undeclared_relationship(faulted_graph, config):
    """Nothing about the comment is malformed, so it must not be reported
    as a malformed reference -- that would name a defect its author does
    not have."""
    checks = run_checks(faulted_graph, config)
    undeclared = next(c for c in checks if c.name == "references.undeclared")
    assert any("REQ-d00001-A" in f.message for f in undeclared.findings)
    malformed = next(c for c in checks if c.name == "references.malformed")
    assert not any("appears to be intended" in f.message for f in malformed.findings)


# Verifies: REQ-d00272-O
def test_an_informal_citation_produces_no_relationship(faulted_graph):
    """Reading intent as a declaration is the failure this vocabulary
    exists to prevent: the citing comment must credit nothing."""
    from elspais.graph import EdgeKind

    node = faulted_graph.find_by_id("REQ-d00001")
    assert node is not None
    citing = [
        e.target.id
        for e in node.iter_edges_by_kind(EdgeKind.IMPLEMENTS)
        if "f6" in str(e.target.id)
    ]
    assert not citing


# Verifies: REQ-d00272-O
def test_the_undeclared_check_carries_its_own_severity(faulted_graph, config):
    config["rules"]["references"]["undeclared"] = "error"
    checks = run_checks(faulted_graph, config)
    assert next(c for c in checks if c.name == "references.undeclared").severity == "error"


# Verifies: REQ-d00272-O, REQ-d00252-K
def test_an_undeclared_finding_names_its_file_and_line(faulted_graph, config):
    checks = run_checks(faulted_graph, config)
    undeclared = next(c for c in checks if c.name == "references.undeclared")
    hit = next(f for f in undeclared.findings if "REQ-d00001-A" in f.message)
    assert hit.file_path and hit.file_path.endswith("m.py")
    assert hit.line
