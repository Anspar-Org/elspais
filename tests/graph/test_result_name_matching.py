# Verifies: REQ-d00284-A, REQ-d00284-B, REQ-d00284-C
"""How a result names the test that produced it.

A results file that names no source file leaves only a recorded name, and what
that name refers to is a fact about the tool that wrote it. These tests cover
the declaration of that form (A), the strict resolution of a name read as a
source file (B), and the report a result matching no single test produces (C).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from elspais.commands.health import check_unmatched_results
from elspais.config.schema import CLASSNAME_FORMS, TestTargetConfig
from elspais.graph.factory import _ingest_target_results, _tests_named
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers.results.registry import REPORTER_REGISTRY, ReporterSpec
from elspais.graph.relations import EdgeKind

_SPEC = """\
### REQ-p00001: Login

**Level**: PRD | **Status**: Active

The system SHALL let a user log in.

#### Assertions

A. The system SHALL accept valid credentials.

*End* *Login* | **Hash**: ________
"""

_TEST_SOURCE = """\
// Verifies: REQ-p00001-A
test('logs in', async () => {
  expect(true).toBe(true);
});
"""

_CONFIG = """\
version = 3

[project]
name = "namer"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["*.spec.ts"]

[[scanning.test.targets]]
name = "e2e"
reporter = "junit"
results = "{results}"
match = "source"
{cwd}{classname}"""


def _junit(*, classname: str, file_attr: str | None = None) -> str:
    """A JUnit report of one passing testcase, optionally naming its source."""
    attr = f' file="{file_attr}"' if file_attr else ""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>\n"
        '  <testsuite name="e2e" tests="1" failures="0">\n'
        f'    <testcase classname="{classname}" name="logs in" time="0.01"{attr}/>\n'
        "  </testsuite>\n"
        "</testsuites>\n"
    )


def _project(
    tmp_path: Path,
    *,
    declared: str = "",
    junit: str | None = None,
    test_files: tuple[str, ...] = ("tests/e2e/login.spec.ts",),
    results_dir: str = "results",
    cwd: str = "",
) -> Path:
    """An on-disk project: one requirement, scanned `.spec.ts` tests, one report.

    `declared` is the target's `classname` (empty leaves the reporter's own).
    `cwd` scopes the target; the report is written under `<cwd>/<results_dir>`.
    """
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")

    for rel in test_files:
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_TEST_SOURCE, encoding="utf-8")

    report_dir = project / cwd / results_dir if cwd else project / results_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "junit.xml").write_text(
        junit if junit is not None else _junit(classname="login.spec.ts"), encoding="utf-8"
    )

    (project / ".elspais.toml").write_text(
        _CONFIG.format(
            results=f"{results_dir}/junit.xml",
            cwd=f'cwd = "{cwd}"\n' if cwd else "",
            classname=f'classname = "{declared}"\n' if declared else "",
        ),
        encoding="utf-8",
    )
    return project


def _build(project: Path):
    from elspais.graph.factory import build_graph

    return build_graph(config_path=project / ".elspais.toml", repo_root=project, scan_code=False)


def _the_result(graph):
    results = list(graph.iter_by_kind(NodeKind.RESULT))
    assert len(results) == 1, [r.id for r in results]
    return results[0]


def _bound_tests(result) -> list[str]:
    """Repo-relative paths of the tests the result is bound to.

    A YIELDS edge is built ``test.link(result)``, so the test is the parent.
    """
    bound = []
    for parent in result.iter_parents(edge_kinds={EdgeKind.YIELDS}):
        file_node = parent.file_node()
        bound.append(file_node.get_field("relative_path") if file_node else parent.id)
    return sorted(bound)


# ---------------------------------------------------------------------------
# A -- each target declares how its results name the test that produced them
# ---------------------------------------------------------------------------


class _OneRecordParser:
    """A results parser emitting a single record naming no source file."""

    def parse(self, results_text: str, source_path: str = "") -> list[dict]:
        return [
            {
                "id": "report.xml:login.spec.ts::logs in",
                "name": "logs in",
                "classname": "login.spec.ts",
                "status": "passed",
                "test_id": "test:login/spec/ts.py::logs in",
            }
        ]


class _CollectingBuilder:
    def __init__(self) -> None:
        self.contents: list = []

    def add_parsed_content(self, content, file_node=None) -> None:
        self.contents.append(content)


# Verifies: REQ-d00284-A
@pytest.mark.parametrize(
    ("reporter_form", "declared", "resolved"),
    [
        ("source-file", "", True),  # empty target falls back to the reporter's form
        ("source-file", "python-module", False),  # the target overrides it away
        ("python-module", "source-file", True),  # the target overrides it in
        ("python-module", "", False),  # empty target falls back to the reporter's form
    ],
)
def test_target_declaration_overrides_the_reporters(
    monkeypatch, tmp_path, reporter_form, declared, resolved
):
    """The effective form is the target's where it declares one, else the reporter's."""
    spec = ReporterSpec(
        name="fake-reporter",
        channel="file",
        kind="results",
        parser_factory=_OneRecordParser,
        classname=reporter_form,
    )
    monkeypatch.setitem(REPORTER_REGISTRY, "fake-reporter", spec)

    builder = _CollectingBuilder()
    target = TestTargetConfig(name="t", reporter="fake-reporter", classname=declared)
    count = _ingest_target_results(
        builder,
        target,
        "",
        tmp_path,
        scanned_tests=frozenset({"tests/e2e/login.spec.ts"}),
    )

    assert count == 1
    data = builder.contents[0].parsed_data
    if resolved:
        assert data["test_id"] is None
        assert data["source_file"] == "tests/e2e/login.spec.ts"
    else:
        assert data["test_id"] == "test:login/spec/ts.py::logs in"
        assert data["source_file"] == ""


# Verifies: REQ-d00284-A
@pytest.mark.parametrize("form", ["", *CLASSNAME_FORMS])
def test_declared_form_is_accepted(form):
    assert TestTargetConfig(name="t", classname=form).classname == form


# Verifies: REQ-d00284-A
@pytest.mark.parametrize("form", ["source_file", "sourcefile", "python", "SOURCE-FILE", "junit"])
def test_undeclarable_form_is_refused(form):
    """A form outside the declarable set is a configuration error, not a guess."""
    with pytest.raises(ValidationError):
        TestTargetConfig(name="t", classname=form)


# ---------------------------------------------------------------------------
# B -- a name binds only where it picks out exactly one scanned test
# ---------------------------------------------------------------------------

_SCANNED = frozenset(
    {
        "tests/e2e/login.spec.ts",
        "tests/e2e/epistaxis-diary.spec.ts",
        "tests/smoke/checkout.spec.ts",
        "packages/app/tests/smoke/checkout.spec.ts",
    }
)


# Verifies: REQ-d00284-B
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # the whole repo-relative path
        ("tests/e2e/login.spec.ts", ["tests/e2e/login.spec.ts"]),
        # a bare basename reaches a test nested any depth below
        ("login.spec.ts", ["tests/e2e/login.spec.ts"]),
        # a name carrying directories still has to match them
        ("e2e/epistaxis-diary.spec.ts", ["tests/e2e/epistaxis-diary.spec.ts"]),
        # a suffix that is not a whole component is not a match
        ("diary.spec.ts", []),
        # a name naming nothing scanned
        ("logout.spec.ts", []),
        # every file the name picks out, in sorted order
        (
            "smoke/checkout.spec.ts",
            ["packages/app/tests/smoke/checkout.spec.ts", "tests/smoke/checkout.spec.ts"],
        ),
    ],
)
def test_tests_named_picks_out_whole_components(name, expected):
    assert _tests_named(name, _SCANNED) == expected


# Verifies: REQ-d00284-B
def test_undeclared_name_binds_to_nothing(tmp_path):
    """Left to the reporter's form, a `.spec.ts` name reads as a module path.

    Nothing in the repository answers to it, so the result binds to no test --
    the very silence REQ-d00284 is about.
    """
    result = _the_result(_build(_project(tmp_path)))

    assert _bound_tests(result) == []


# Verifies: REQ-d00284-B
def test_declared_name_binds_to_the_test_it_names(tmp_path):
    graph = _build(_project(tmp_path, declared="source-file"))
    result = _the_result(graph)

    assert _bound_tests(result) == ["tests/e2e/login.spec.ts"]
    assert result.get_field("source_file") == "tests/e2e/login.spec.ts"
    assert result.get_field("name_match") is None


# Verifies: REQ-d00284-B
def test_ambiguous_name_binds_to_neither(tmp_path):
    """Two scanned tests share the recorded name, so neither is the one that ran."""
    project = _project(
        tmp_path,
        declared="source-file",
        test_files=("tests/e2e/login.spec.ts", "tests/smoke/login.spec.ts"),
    )
    result = _the_result(_build(project))

    assert _bound_tests(result) == []
    assert result.get_field("name_match") == "ambiguous"
    assert result.get_field("name_candidates") == [
        "tests/e2e/login.spec.ts",
        "tests/smoke/login.spec.ts",
    ]


# Verifies: REQ-d00284-B
@pytest.mark.parametrize("declared", ["", "source-file", "python-module"])
def test_source_file_the_producer_named_is_untouched_by_the_declaration(tmp_path, declared):
    """The declaration governs only results whose producer named no source file.

    The recorded name here answers to nothing; the `file` attribute answers to
    the scanned test, and it is the one that decides.
    """
    project = _project(
        tmp_path,
        declared=declared,
        junit=_junit(classname="totally.bogus.module", file_attr="tests/e2e/login.spec.ts"),
    )
    result = _the_result(_build(project))

    assert _bound_tests(result) == ["tests/e2e/login.spec.ts"]
    assert result.get_field("name_match") is None


# Verifies: REQ-d00284-B
def test_name_matching_a_test_outside_the_target_binds_to_nothing(tmp_path):
    """The candidates are the tests scanned for this target, not every test.

    The one file answering to the recorded name sits outside the target's
    `cwd`, so it says nothing about where this result came from.
    """
    project = _project(tmp_path, declared="source-file", cwd="app")
    result = _the_result(_build(project))

    assert _bound_tests(result) == []
    assert result.get_field("name_match") == "unmatched"
    assert result.get_field("name_candidates") == []


# ---------------------------------------------------------------------------
# C -- a result matching no test is reported, saying which problem it is
# ---------------------------------------------------------------------------


# Verifies: REQ-d00284-C
def test_check_passes_when_every_result_binds(tmp_path):
    graph = _build(_project(tmp_path, declared="source-file"))
    assert len(list(graph.iter_by_kind(NodeKind.RESULT))) == 1, "the run ingested a result to check"

    check = check_unmatched_results(graph)

    assert check.name == "tests.unmatched_results"
    assert check.passed is True
    assert check.findings == []


# Verifies: REQ-d00284-C
def test_check_reports_a_name_that_picked_out_no_test(tmp_path):
    check = check_unmatched_results(_build(_project(tmp_path, declared="source-file", cwd="app")))

    assert check.name == "tests.unmatched_results"
    assert check.passed is False
    assert check.severity == "warning"
    assert len(check.findings) == 1
    message = check.findings[0].message
    assert "'login.spec.ts'" in message
    assert "matched no test" in message


# Verifies: REQ-d00284-C
def test_check_reports_a_name_that_picked_out_several_tests(tmp_path):
    project = _project(
        tmp_path,
        declared="source-file",
        test_files=("tests/e2e/login.spec.ts", "tests/smoke/login.spec.ts"),
    )
    check = check_unmatched_results(_build(project))

    assert check.passed is False
    assert len(check.findings) == 1
    message = check.findings[0].message
    assert "matched 2 tests" in message
    assert "tests/e2e/login.spec.ts" in message
    assert "tests/smoke/login.spec.ts" in message
