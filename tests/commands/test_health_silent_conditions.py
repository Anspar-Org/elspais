# Verifies: REQ-d00274, REQ-d00276, REQ-d00241
"""Checks that name three conditions the tool used to hold in silence.

Each is a condition the tool can see and the author cannot: a citation that
attached to no test, a test file nothing configured can run, and a file the
scan reached, declined to read, and that cites anyway. Each used to end in a
coverage figure that read the same as an honest zero.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.health import (
    check_unbound_citations,
    check_unlinked_tests,
    check_unrunnable_test_files,
    check_unscanned_keyword_files,
)
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind

SPEC = """\
### REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

#### Assertions

A. The thing SHALL happen.

B. The other thing SHALL happen.

*End* *Test Req* | **Hash**: ________
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _project(
    tmp_path: Path,
    *,
    test_patterns: str = '["test_*.py"]',
    test_skip_files: str = "[]",
    global_skip: str = "[]",
    targets: str = "",
) -> Path:
    """A one-requirement project scanning `src/` for code and `tests/` for tests."""
    _write(tmp_path / "spec" / "reqs.md", SPEC)
    _write(
        tmp_path / ".elspais.toml",
        f"""\
[project]
name = "silent-conditions"
namespace = "REQ"

[scanning]
skip = {global_skip}

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
file_patterns = ["*.py"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = {test_patterns}
skip_files = {test_skip_files}
{targets}
""",
    )
    _write(tmp_path / "src" / "app.py", "# Implements: REQ-p00001-A+B\ndef work():\n    pass\n")
    return tmp_path / ".elspais.toml"


def _build(tmp_path: Path, config_file: Path):
    return build_graph(config_path=config_file, repo_root=tmp_path)


def _config_of(graph):
    return graph.root_config


def _verifiers(graph) -> list[str]:
    """Every test the requirement is verified by.

    A `Verifies:` edge is carried by the REQUIREMENT node whichever assertion
    the citation named -- the assertion labels ride on the edge -- so this is
    where the credit either is or is not.
    """
    requirement = graph.find_by_id("REQ-p00001")
    assert requirement is not None, "The fixture requirement must have parsed"
    return [
        edge.target.id
        for edge in requirement.iter_outgoing_edges()
        if edge.kind == EdgeKind.VERIFIES
    ]


# ======================================================================
# REQ-d00274-G / -H: a citation that binds to no test
# ======================================================================


class TestCitationsThatBindToNoTest:
    """A citation with no test beneath it is named, and credits nothing.

    Such a citation used to build a TEST node at the comment's own line. No
    result can ever name that line, so the assertions it cited read as tested
    and never as passing -- which is exactly how a stale result reads, and the
    reflex it provokes (re-run the suite) cannot move it.
    """

    # Verifies: REQ-d00274-G
    def test_REQ_d00274_G_a_citation_above_a_class_is_reported(self, tmp_path: Path) -> None:
        """A comment above a class declaration attaches to no test.

        The class is not a test; only its methods are, and the pre-scan binds
        a comment to the declaration on the line below it. So a citation
        written above the class reached nothing.
        """
        config_file = _project(tmp_path)
        _write(
            tmp_path / "tests" / "test_thing.py",
            "def test_first():\n"
            "    assert True\n"
            "\n"
            "\n"
            "# Verifies: REQ-p00001-A\n"
            "class TestThing:\n"
            "    def test_one(self):\n"
            "        assert True\n",
        )
        graph = _build(tmp_path, config_file)

        check = check_unbound_citations(graph, _config_of(graph))

        assert not check.passed, "A citation that found no test must be reported"
        assert check.severity == "warning"
        assert len(check.findings) == 1
        finding = check.findings[0]
        assert finding.file_path == "tests/test_thing.py"
        assert finding.line == 5, "The finding names the line the citation was written on"
        assert "REQ-p00001-A" in finding.message

    # Verifies: REQ-d00274-H
    def test_REQ_d00274_H_such_a_citation_credits_no_coverage(self, tmp_path: Path) -> None:
        """The assertion it named is not tested by it.

        The whole cost of the condition is the credit: a coverage figure that
        rises on the strength of a citation nothing can produce a result for
        is worse than one that never rose.
        """
        config_file = _project(tmp_path)
        _write(
            tmp_path / "tests" / "test_thing.py",
            "def test_first():\n"
            "    assert True\n"
            "\n"
            "\n"
            "# Verifies: REQ-p00001-A\n"
            "class TestThing:\n"
            "    def test_one(self):\n"
            "        assert True\n",
        )
        graph = _build(tmp_path, config_file)

        verifiers = _verifiers(graph)
        assert verifiers == [], (
            f"A citation that attached to no test must confer no VERIFIES edge: {verifiers}"
        )

    # Verifies: REQ-d00274-H
    def test_REQ_d00274_H_the_credit_is_withheld_whatever_the_severity(
        self, tmp_path: Path
    ) -> None:
        """Turning the report off does not restore the coverage.

        What a citation credits is a fact about the citation; how loudly the
        project wants to hear about it is a separate decision, and one that
        must not be able to buy back a figure that was never earned.
        """
        config_file = _project(tmp_path)
        _write(
            tmp_path / ".elspais.local.toml",
            '[rules.severity]\n"tests.unbound_citation" = "off"\n',
        )
        _write(
            tmp_path / "tests" / "test_thing.py",
            "def test_first():\n"
            "    assert True\n"
            "\n"
            "\n"
            "# Verifies: REQ-p00001-A\n"
            "class TestThing:\n"
            "    def test_one(self):\n"
            "        assert True\n",
        )
        graph = _build(tmp_path, config_file)
        config = _config_of(graph)

        check = check_unbound_citations(graph, config)
        assert check.details.get("skipped") is True, "severity=off silences the report"

        assert _verifiers(graph) == [], (
            "severity=off silences the report; it does not restore the credit"
        )

    # Verifies: REQ-d00274-G
    def test_REQ_d00274_G_a_citation_on_its_test_is_not_reported(self, tmp_path: Path) -> None:
        """The ordinary annotation binds, and stays out of the report.

        A check that fires on the pattern the tool asks authors to use would
        be noise rather than a finding.
        """
        config_file = _project(tmp_path)
        _write(
            tmp_path / "tests" / "test_thing.py",
            "# Verifies: REQ-p00001-A\ndef test_one():\n    assert True\n",
        )
        graph = _build(tmp_path, config_file)

        check = check_unbound_citations(graph, _config_of(graph))
        assert check.passed, f"An annotation on its own test binds: {check.findings}"

        assert _verifiers(graph), "A citation that bound to a test still credits it"

    # Verifies: REQ-d00274-G
    def test_REQ_d00274_G_a_file_level_default_binds_to_every_test(self, tmp_path: Path) -> None:
        """A citation above the file's first definition is not unbound.

        It is the file-level default, which reaches every test the file
        declares. Reporting it would name a mechanism the tool provides as a
        defect.
        """
        config_file = _project(tmp_path)
        _write(
            tmp_path / "tests" / "test_thing.py",
            '"""Module docstring."""\n\n'
            "# Verifies: REQ-p00001-A\n\n"
            "def test_one():\n    assert True\n",
        )
        graph = _build(tmp_path, config_file)

        check = check_unbound_citations(graph, _config_of(graph))
        assert check.passed, f"A file-level default binds to the file's tests: {check.findings}"

        assert _verifiers(graph), "The file-level default reached the file's tests"

    # Verifies: REQ-d00274-G
    def test_REQ_d00274_G_a_default_in_a_file_with_no_tests_is_reported(
        self, tmp_path: Path
    ) -> None:
        """A file-level default reaching no test is a citation reaching nothing.

        Sitting above the first definition proves the citation IS the file
        default; it does not prove the default found anything to apply to.
        """
        config_file = _project(tmp_path)
        _write(
            tmp_path / "tests" / "test_helpers.py",
            "# Verifies: REQ-p00001-B\n\ndef make_thing():\n    return object()\n",
        )
        graph = _build(tmp_path, config_file)

        check = check_unbound_citations(graph, _config_of(graph))
        assert not check.passed, "A default in a file declaring no test reached no test"
        assert check.findings[0].file_path == "tests/test_helpers.py"

        assert _verifiers(graph) == [], "A default reaching no test credits nothing"

    # Verifies: REQ-d00241-E
    def test_REQ_d00241_E_a_file_whose_marker_bound_nothing_is_not_called_markerless(
        self, tmp_path: Path
    ) -> None:
        """Carrying no marker and carrying one that bound nothing are different.

        Telling the author of a file that carries a citation to add one sends
        them to write what is already there.
        """
        config_file = _project(tmp_path)
        _write(
            tmp_path / "tests" / "test_thing.py",
            "def test_first():\n"
            "    assert True\n"
            "\n"
            "\n"
            "# Verifies: REQ-p00001-A\n"
            "class TestThing:\n"
            "    def test_one(self):\n"
            "        assert True\n",
        )
        graph = _build(tmp_path, config_file)
        config = _config_of(graph)

        unlinked = check_unlinked_tests(graph, config)
        reported = {f.file_path for f in unlinked.findings}
        assert "tests/test_thing.py" not in reported, (
            "A file carrying a citation that bound nothing carries a marker"
        )
        unbound = check_unbound_citations(graph, config)
        assert {f.file_path for f in unbound.findings} == {"tests/test_thing.py"}


# ======================================================================
# REQ-d00276-E: a test file nothing configured can run
# ======================================================================


class TestTestFilesNoTargetCanExecute:
    """Scanning a directory raises Tested; running its tests is a separate say-so."""

    # Verifies: REQ-d00276-E
    def test_REQ_d00276_E_a_file_outside_every_target_is_reported(self, tmp_path: Path) -> None:
        """A target running from `app/` cannot execute a file under `tests/`.

        Adding the directory to the scanned set raised the Tested figure; no
        configured command can move Passing to follow it.
        """
        config_file = _project(
            tmp_path,
            targets=(
                "\n[[scanning.test.targets]]\n"
                'name = "flutter"\n'
                'cwd = "app"\n'
                'command = "flutter test"\n'
                'reporter = "flutter-machine"\n'
            ),
        )
        _write(
            tmp_path / "tests" / "test_thing.py",
            "# Verifies: REQ-p00001-A\ndef test_one():\n    assert True\n",
        )
        graph = _build(tmp_path, config_file)

        check = check_unrunnable_test_files(graph, _config_of(graph))

        assert not check.passed
        assert check.severity == "info"
        assert [f.file_path for f in check.findings] == ["tests/test_thing.py"]

    # Verifies: REQ-d00276-E
    def test_REQ_d00276_E_a_file_within_a_targets_reach_is_not_reported(
        self, tmp_path: Path
    ) -> None:
        """A target running from the repository root reaches everything."""
        config_file = _project(
            tmp_path,
            targets=(
                "\n[[scanning.test.targets]]\n"
                'name = "unit"\n'
                'command = "pytest tests/"\n'
                'reporter = "junit"\n'
                'results = ".results/junit.xml"\n'
            ),
        )
        _write(
            tmp_path / "tests" / "test_thing.py",
            "# Verifies: REQ-p00001-A\ndef test_one():\n    assert True\n",
        )
        graph = _build(tmp_path, config_file)

        check = check_unrunnable_test_files(graph, _config_of(graph))
        assert check.passed, f"A root-run target reaches every scanned file: {check.findings}"

    # Verifies: REQ-d00276-E
    def test_REQ_d00276_E_an_ingest_only_target_executes_nothing(self, tmp_path: Path) -> None:
        """A target with no command runs nothing, wherever it sits.

        Ingest-only is a legitimate configuration -- the schema says as much,
        for a CI run whose tests already executed elsewhere -- and it is
        exactly why nothing configured can run these files.
        """
        config_file = _project(
            tmp_path,
            targets=(
                "\n[[scanning.test.targets]]\n"
                'name = "ci-ingest"\n'
                'reporter = "junit"\n'
                'results = ".results/junit.xml"\n'
            ),
        )
        _write(
            tmp_path / "tests" / "test_thing.py",
            "# Verifies: REQ-p00001-A\ndef test_one():\n    assert True\n",
        )
        graph = _build(tmp_path, config_file)

        check = check_unrunnable_test_files(graph, _config_of(graph))
        assert not check.passed, "A target with no command executes nothing"
        assert [f.file_path for f in check.findings] == ["tests/test_thing.py"]

    # Verifies: REQ-d00276-E
    def test_REQ_d00276_E_the_severity_is_what_the_project_configures(self, tmp_path: Path) -> None:
        """A project that minds more than the default says so, and is heard."""
        config_file = _project(
            tmp_path,
            targets=(
                "\n[[scanning.test.targets]]\n"
                'name = "flutter"\n'
                'cwd = "app"\n'
                'command = "flutter test"\n'
                'reporter = "flutter-machine"\n'
            ),
        )
        _write(
            tmp_path / ".elspais.local.toml",
            '[rules.severity]\n"tests.unrunnable_file" = "error"\n',
        )
        _write(
            tmp_path / "tests" / "test_thing.py",
            "# Verifies: REQ-p00001-A\ndef test_one():\n    assert True\n",
        )
        graph = _build(tmp_path, config_file)

        check = check_unrunnable_test_files(graph, _config_of(graph))
        assert check.severity == "error"


# ======================================================================
# REQ-d00241-F / -G: files already collected, now reported
# ======================================================================


class TestUnscannedFilesCarryingAKeyword:
    """A citation written where the tool was not looking is worth saying."""

    # Verifies: REQ-d00241-F
    def test_REQ_d00241_F_a_declined_citing_file_is_reported(self, tmp_path: Path) -> None:
        """The finding names the file and the line, because that is its value.

        A count with no names says a citation was dropped somewhere, which is
        the same amount of help as saying nothing.
        """
        config_file = _project(tmp_path)
        _write(tmp_path / "src" / "notes.txt", "Notes\n\n# Implements: REQ-p00001\n")
        graph = _build(tmp_path, config_file)

        check = check_unscanned_keyword_files(graph, _config_of(graph))

        assert not check.passed
        assert check.severity == "info"
        assert len(check.findings) == 1
        finding = check.findings[0]
        assert (finding.file_path, finding.line) == ("src/notes.txt", 3)
        assert "Implements" in finding.message

    # Verifies: REQ-d00241-G
    def test_REQ_d00241_G_an_ignored_file_never_reaches_the_check(self, tmp_path: Path) -> None:
        """Excluding a file is also a decision about reporting.

        The project said not to look there, so a citation found there is not
        something to be told about.
        """
        config_file = _project(tmp_path, global_skip='["notes.txt"]')
        _write(tmp_path / "src" / "notes.txt", "Notes\n\n# Implements: REQ-p00001\n")
        graph = _build(tmp_path, config_file)

        check = check_unscanned_keyword_files(graph, _config_of(graph))
        assert check.passed, f"An excluded file must not be reported: {check.findings}"

    # Verifies: REQ-d00241-F
    def test_REQ_d00241_F_a_quiet_declined_file_is_not_reported(self, tmp_path: Path) -> None:
        """Passing over an ordinary file is not a finding."""
        config_file = _project(tmp_path)
        _write(tmp_path / "src" / "notes.txt", "Notes mentioning no requirement.\n")
        graph = _build(tmp_path, config_file)

        check = check_unscanned_keyword_files(graph, _config_of(graph))
        assert check.passed


# ======================================================================
# All three are configurable, and none is invented at its call site
# ======================================================================


# Verifies: REQ-d00285-D
@pytest.mark.parametrize(
    "name",
    ["tests.unbound_citation", "tests.unrunnable_file", "code.unscanned_keyword_file"],
)
def test_REQ_d00285_D_each_new_check_is_registered(name: str) -> None:
    """A finding outside the registry is one no project can configure."""
    from elspais.utilities.findings import REGISTRY, remedy_for, severity_for

    rule = REGISTRY[name]
    assert rule.description, "The published catalog is rendered from the description"
    assert remedy_for(name), "A check names its remedy, or names the absence of one"
    assert severity_for(name) == rule.default
    assert severity_for(name, {"rules": {"severity": {name: "error"}}}) == "error"


# Verifies: REQ-d00286-E
def test_REQ_d00286_E_no_new_check_reports_a_kind_the_graph_cannot_supply() -> None:
    """Every new check reads a record the graph publishes.

    The three accessors are the whole interface between the build that
    notices a condition and the check that reports it.
    """
    from elspais.graph.builder import TraceGraph

    graph = TraceGraph(repo_root=Path("."))
    assert graph.unbound_citations() == []
    assert graph.unscanned_keyword_files() == []


# Verifies: REQ-d00274-G
def test_REQ_d00274_G_a_bound_citation_still_produces_its_test_node(tmp_path: Path) -> None:
    """The report costs the ordinary case nothing.

    A change that withheld coverage from citations that DID bind would trade
    one silent wrong figure for another.
    """
    config_file = _project(tmp_path)
    _write(
        tmp_path / "tests" / "test_thing.py",
        "# Verifies: REQ-p00001-A\ndef test_one():\n    assert True\n",
    )
    graph = _build(tmp_path, config_file)

    tests = list(graph.nodes_by_kind(NodeKind.TEST))
    assert any("test_one" in n.id for n in tests), f"The test node is still built: {tests}"
