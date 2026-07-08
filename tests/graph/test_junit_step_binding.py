# Verifies: REQ-d00254-G, REQ-d00256-E
"""Step-scope RESULT->TEST binding for source-matched JUnit results.

Regression tests for the conflation bug: multiple per-step ``<testcase>``
elements in one JUnit file carrying a ``file`` attribute but NO ``line``
attribute all used to fan out to every TEST in that source file, so each
journey step displayed all steps' results. The builder now resolves a
source-matched result whose name embeds exactly ONE ``<journey>/N`` step id
to the TEST(s) that VERIFIES that STEP (``match_scope == "step"``); names
with no step id, or with two different step ids, still fall through to the
file-scope fanout (``match_scope == "file"``).

Uses the on-disk ``tests/fixtures/journey-uat/junit-step-binding`` fixture:
a 2-step journey, ONE test source file with per-step ``Verifies:`` tests,
and a ``[[scanning.test.targets]]`` junit results file (match = "source")
whose testcases have ``file=`` but no ``line=``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "journey-uat" / "junit-step-binding"

STEP1_NAME = "Login Flow › JNY-OQ-Login-01/1: open login page"
STEP2_NAME = "Login Flow › JNY-OQ-Login-01/2: enter credentials"
NO_STEP_NAME = "Login Flow › smoke check without a step id"
AMBIGUOUS_NAME = "Login Flow › JNY-OQ-Login-01/1 and JNY-OQ-Login-01/2 combined"


@pytest.fixture(scope="module")
def step_binding_graph(tmp_path_factory):
    """Copy the junit-step-binding fixture and build its graph (read-only)."""
    from elspais.graph.factory import build_graph

    dest = tmp_path_factory.mktemp("junit-step-binding") / "proj"
    shutil.copytree(_FIXTURE, dest)
    fg = build_graph(repo_root=dest)
    return fg._repos[fg._root_repo].graph


def _test_node(graph, function_name: str):
    """Find the scanned TEST node for a fixture test function."""
    for node in graph.iter_by_kind(NodeKind.TEST):
        if node.id.endswith(f"::{function_name}"):
            return node
    raise AssertionError(f"no TEST node found for {function_name}")


def _result_names(test_node) -> set[str]:
    return {
        c.get_field("name")
        for c in test_node.iter_children()
        if c.kind == NodeKind.RESULT
    }


def _result_by_name(graph, name: str):
    for node in graph.iter_by_kind(NodeKind.RESULT):
        if node.get_field("name") == name:
            return node
    raise AssertionError(f"no RESULT node named {name!r}")


# Verifies: REQ-d00254-G, REQ-d00256-E
@pytest.mark.parametrize("name", [STEP1_NAME, STEP2_NAME])
def test_step_result_has_step_match_scope(step_binding_graph, name):
    """A testcase whose name embeds exactly one step id binds at step scope."""
    result = _result_by_name(step_binding_graph, name)
    assert result.get_field("match_scope") == "step"


# Verifies: REQ-d00254-G, REQ-d00256-E
def test_step_results_are_not_conflated_across_steps(step_binding_graph):
    """Each step's verifying TEST holds its own RESULT and not its sibling's.

    This is the conflation regression: with no ``line`` attribute both
    per-step results used to fan out to BOTH tests in the file.
    """
    test1 = _test_node(step_binding_graph, "test_step1")
    test2 = _test_node(step_binding_graph, "test_step2")

    names1 = _result_names(test1)
    names2 = _result_names(test2)

    assert STEP1_NAME in names1
    assert STEP2_NAME not in names1, "step 1's test must not hold step 2's result"
    assert STEP2_NAME in names2
    assert STEP1_NAME not in names2, "step 2's test must not hold step 1's result"


# Verifies: REQ-d00254-G
@pytest.mark.parametrize(
    "name",
    [NO_STEP_NAME, AMBIGUOUS_NAME],
    ids=["no-step-id", "two-different-step-ids"],
)
def test_non_step_results_fall_back_to_file_scope(step_binding_graph, name):
    """No step id (or an ambiguous pair) falls through to file-scope fanout."""
    result = _result_by_name(step_binding_graph, name)
    assert result.get_field("match_scope") == "file"

    # File scope still fans out to every TEST in the source file.
    test1 = _test_node(step_binding_graph, "test_step1")
    test2 = _test_node(step_binding_graph, "test_step2")
    assert name in _result_names(test1)
    assert name in _result_names(test2)


# Verifies: REQ-d00254-F
def test_target_results_carry_result_file_provenance(step_binding_graph):
    """RESULTs ingested from a junit target record the results artifact.

    ``result_file`` is the repo-relative results path; ``result_line`` is the
    1-based line of the ``<testcase>`` element in the pretty-printed XML.
    """
    step1 = _result_by_name(step_binding_graph, STEP1_NAME)
    step2 = _result_by_name(step_binding_graph, STEP2_NAME)
    assert step1.get_field("result_file") == "results.xml"
    assert step2.get_field("result_file") == "results.xml"
    # Testcases sit on lines 3 and 4 of the fixture's results.xml.
    assert step1.get_field("result_line") == 3
    assert step2.get_field("result_line") == 4
