# Verifies: REQ-d00254-G
"""A result binds to its test by recorded identity, never by reading its name.

The discriminating case: the runner reports a test whose name embeds a
requirement identifier, under a parametrized variant name. The result
attaches to the test node the reported identity denotes, and contributes no
requirement reference of its own -- every reference the test carries is
declared in its own source file, by the `Verifies:` comment above it.
"""

from pathlib import Path

from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind

_SPEC = """\
### REQ-p00001: Login

**Level**: PRD | **Status**: Active

The system SHALL let a user log in.

#### Assertions

A. The system SHALL accept valid credentials.

*End* *Login* | **Hash**: ________

### REQ-p00002: Logout

**Level**: PRD | **Status**: Active

The system SHALL let a user log out.

#### Assertions

A. The system SHALL end the session.

B. The system SHALL clear the session cookie.

*End* *Logout* | **Hash**: ________
"""

# Both references are declared in the comment; the function name embeds
# REQ-p00001-A and declares nothing by doing so (REQ-d00269-L), which is
# what makes the name available as a decoy for the result-matching below.
_TEST_FILE = """\
# Verifies: REQ-p00001-A, REQ-p00002-B
def test_REQ_p00001_A_login():
    assert True
"""

_JUNIT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests" tests="1" failures="0">
    <testcase classname="tests.test_thing" name="test_REQ_p00001_A_login[case-1]" time="0.01"/>
  </testsuite>
</testsuites>
"""

_CONFIG = """\
version = 5

[project]
name = "identity-match"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]

[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "results/TEST-*.xml"
match = "source"
"""

_TEST_NODE_ID = "test:tests/test_thing.py::test_REQ_p00001_A_login"


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_thing.py").write_text(_TEST_FILE, encoding="utf-8")
    (project / "results").mkdir(parents=True)
    (project / "results" / "TEST-unit.xml").write_text(_JUNIT, encoding="utf-8")
    (project / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    return project


def _build(tmp_path: Path):
    from elspais.graph.factory import build_graph

    project = _project(tmp_path)
    return build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )


def _the_test_node(graph):
    node = graph.find_by_id(_TEST_NODE_ID)
    assert node is not None, sorted(n.id for n in graph.iter_by_kind(NodeKind.TEST))
    return node


# Verifies: REQ-d00254-G
def test_result_binds_to_the_test_its_reported_identity_denotes(tmp_path):
    """Parametrized variant and name-embedded identifier notwithstanding, identity wins."""
    graph = _build(tmp_path)

    test_node = _the_test_node(graph)
    yielded = [e.target for e in test_node.iter_outgoing_edges() if e.kind == EdgeKind.YIELDS]

    assert len(yielded) == 1, "the run's single result belongs to the test that produced it"
    assert yielded[0].get_field("status") == "passed"
    assert yielded[0].get_field("name") == "test_REQ_p00001_A_login[case-1]"


# Verifies: REQ-d00254-G
def test_result_contributes_no_requirement_reference(tmp_path):
    """A result's only relation is to its test; the identifier in its name is inert."""
    graph = _build(tmp_path)

    results = list(graph.iter_by_kind(NodeKind.RESULT))
    assert len(results) == 1
    result = results[0]

    assert [e.kind for e in result.iter_incoming_edges()] == [EdgeKind.YIELDS]
    assert [e.kind for e in result.iter_outgoing_edges()] == []


# Verifies: REQ-d00254-G
def test_references_come_from_the_test_source_file(tmp_path):
    """Both of this test's references are declared in its own source file.

    REQ-p00001 and REQ-p00002 are both named by the `Verifies:` comment
    above the function. The results artifact adds nothing to either -- and
    neither does the function name, which embeds REQ-p00001-A and declares
    nothing by doing so, so the set below is the comment's list exactly.
    """
    graph = _build(tmp_path)

    test_node = _the_test_node(graph)
    verifiers = {
        e.source.id for e in test_node.iter_incoming_edges() if e.kind == EdgeKind.VERIFIES
    }

    assert verifiers == {"REQ-p00001", "REQ-p00002"}
