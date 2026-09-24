# Verifies: REQ-d00285-G
"""An artifact ingestion produced nothing from is recorded, not dropped.

A results file that will not parse, a coverage report that is not there, a
target naming a reporter nothing reads: each leaves the graph short of
content, and a graph short of content reads exactly like a project where the
work was never done. These tests hold the tool to recording which of the two
happened, at the point that decided to drop it, with the file and the cause.
"""

from pathlib import Path

import pytest

from elspais.graph.parsers.results.coverage_json import CoverageJsonParser
from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser
from elspais.graph.parsers.results.junit_xml import JUnitXMLParser
from elspais.graph.parsers.results.lcov import LcovParser
from elspais.graph.parsers.results.pytest_json import PytestJSONParser

_SPEC = """\
### REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *Test Req* | **Hash**: ________
"""

_GOOD_JUNIT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests" tests="1" failures="0">
    <testcase classname="tests.test_thing" name="test_a" time="0.01"/>
  </testsuite>
</testsuites>
"""

_TRUNCATED_JUNIT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests" tests="1" failures="0">
    <testcase classname="tests.test_thing" name="test_a" time="0.01"/>
"""

_CONFIG_HEAD = """\
version = 5

[project]
name = "ingest"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
"""


def _project(tmp_path: Path, targets: str, results: dict[str, str] | None = None) -> Path:
    """An on-disk project with one requirement and the given target table."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    for rel, text in (results or {}).items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (project / ".elspais.toml").write_text(_CONFIG_HEAD + targets, encoding="utf-8")
    return project


def _build(project: Path):
    from elspais.graph.factory import build_graph

    return build_graph(
        config_path=project / ".elspais.toml",
        repo_root=project,
        scan_code=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# What each parser declines to read
# ─────────────────────────────────────────────────────────────────────────────


# Verifies: REQ-d00285-A, REQ-d00285-G
def test_junit_records_the_file_and_line_it_could_not_parse():
    parser = JUnitXMLParser()
    results = parser.parse(_TRUNCATED_JUNIT, "results/TEST-a.xml")

    assert results == []
    (diagnostic,) = list(parser.iter_diagnostics())
    assert diagnostic.path == "results/TEST-a.xml"
    assert diagnostic.line is not None
    assert "did not parse" in diagnostic.cause


# Verifies: REQ-d00285-G
def test_junit_records_a_document_holding_no_test_suite():
    parser = JUnitXMLParser()
    results = parser.parse("<report><item/></report>", "results/TEST-a.xml")

    assert results == []
    (diagnostic,) = list(parser.iter_diagnostics())
    assert "report" in diagnostic.cause


# Verifies: REQ-d00285-G
def test_a_parse_that_read_everything_records_nothing():
    parser = JUnitXMLParser()
    results = parser.parse(_GOOD_JUNIT, "results/TEST-a.xml")

    assert len(results) == 1
    assert list(parser.iter_diagnostics()) == []


# Verifies: REQ-d00285-G
def test_a_reused_parser_does_not_report_the_previous_artifacts_condition():
    """One parser instance reads several artifacts; the records follow the read."""
    parser = JUnitXMLParser()
    parser.parse(_TRUNCATED_JUNIT, "results/TEST-broken.xml")
    parser.parse(_GOOD_JUNIT, "results/TEST-good.xml")

    assert list(parser.iter_diagnostics()) == []


# Verifies: REQ-d00285-A, REQ-d00285-G
def test_pytest_json_records_the_line_the_decoder_stopped_at():
    parser = PytestJSONParser()
    results = parser.parse('{\n  "tests": [\n', "results/report.json")

    assert results == []
    (diagnostic,) = list(parser.iter_diagnostics())
    assert diagnostic.path == "results/report.json"
    assert diagnostic.line is not None


# Verifies: REQ-d00285-G
def test_pytest_json_records_a_document_in_a_shape_it_does_not_read():
    parser = PytestJSONParser()
    results = parser.parse('{"summary": {"passed": 3}}', "results/report.json")

    assert results == []
    (diagnostic,) = list(parser.iter_diagnostics())
    assert "tests" in diagnostic.cause


# Verifies: REQ-d00285-G
def test_coverage_json_records_what_it_could_not_parse():
    parser = CoverageJsonParser()

    assert parser.parse("{not json", "coverage/coverage.json") == {}
    (diagnostic,) = list(parser.iter_diagnostics())
    assert diagnostic.path == "coverage/coverage.json"
    assert "did not parse" in diagnostic.cause


# Verifies: REQ-d00285-G
def test_coverage_json_records_a_report_holding_no_files_mapping():
    parser = CoverageJsonParser()

    assert parser.parse('{"meta": {}}', "coverage/coverage.json") == {}
    (diagnostic,) = list(parser.iter_diagnostics())
    assert "files" in diagnostic.cause


# Verifies: REQ-d00285-A, REQ-d00285-G
def test_lcov_records_the_line_of_a_record_it_could_not_read():
    parser = LcovParser()
    content = "SF:lib/a.dart\nDA:1,1\nDA:two,1\nLF:2\nLH:1\nend_of_record\n"

    measured = parser.parse(content, "coverage/lcov.info")

    # The readable line is still measured; the unreadable one is reported.
    assert measured["lib/a.dart"]["line_coverage"] == {1: 1}
    (diagnostic,) = list(parser.iter_diagnostics())
    assert diagnostic.line == 3
    assert "DA" in diagnostic.cause


# Verifies: REQ-d00285-G
def test_lcov_records_a_report_naming_no_source_file():
    parser = LcovParser()

    assert parser.parse("TN:suite\nend_of_record\n", "coverage/lcov.info") == {}
    (diagnostic,) = list(parser.iter_diagnostics())
    assert "SF" in diagnostic.cause


# Verifies: REQ-d00285-G
def test_flutter_machine_records_output_that_carried_no_events():
    parser = FlutterMachineParser()

    assert parser.parse("Running tests...\nBuild failed.\n", "target:app") == []
    (diagnostic,) = list(parser.iter_diagnostics())
    assert "no JSON events" in diagnostic.cause


# Verifies: REQ-d00285-G
def test_flutter_machine_does_not_report_the_runners_own_chatter():
    """Non-JSON lines between events are that stream's normal traffic."""
    parser = FlutterMachineParser()
    content = (
        "Building application...\n"
        '{"type":"suite","suite":{"id":1,"path":"test/a_test.dart"}}\n'
        '{"type":"testStart","test":{"id":2,"suiteID":1,"name":"works","line":7}}\n'
        '{"type":"testDone","testID":2,"result":"success"}\n'
        '{"type":"done","success":true}\n'
    )

    results = parser.parse(content, "target:app")

    assert len(results) == 1
    assert list(parser.iter_diagnostics()) == []


# ─────────────────────────────────────────────────────────────────────────────
# What reaches the graph
# ─────────────────────────────────────────────────────────────────────────────


# Verifies: REQ-d00285-A, REQ-d00285-G
def test_an_unreadable_results_file_is_recorded_on_the_graph(tmp_path):
    """No results and an unreadable report are told apart on the graph."""
    from elspais.graph.GraphNode import NodeKind

    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "results/TEST-*.xml"
""",
        {"results/TEST-a.xml": _TRUNCATED_JUNIT},
    )
    graph = _build(project)

    assert list(graph.iter_by_kind(NodeKind.RESULT)) == []
    (fault,) = graph.ingestion_faults()
    assert fault.stage == "results"
    assert fault.target == "unit"
    assert fault.path == "results/TEST-a.xml"
    assert fault.line is not None
    assert "did not parse" in fault.cause


# Verifies: REQ-d00285-G
def test_a_readable_results_file_leaves_the_graph_with_no_faults(tmp_path):
    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "results/TEST-*.xml"
""",
        {"results/TEST-a.xml": _GOOD_JUNIT},
    )

    assert _build(project).ingestion_faults() == []


# Verifies: REQ-d00285-G, REQ-p00019-K
def test_a_reporter_nothing_reads_is_recorded_once(tmp_path):
    """A typo'd reporter name produces no results anywhere; say so, once."""
    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
reporter = "junitt"
results = "results/TEST-*.xml"
""",
        {"results/TEST-a.xml": _GOOD_JUNIT},
    )

    (fault,) = _build(project).ingestion_faults()
    assert fault.target == "unit"
    assert "junitt" in fault.cause
    assert "junit" in fault.cause  # the reader is told what it could have said


# Verifies: REQ-d00285-G
def test_a_results_pattern_matching_nothing_is_recorded(tmp_path):
    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "results/TEST-*.xml"
""",
    )

    (fault,) = _build(project).ingestion_faults()
    assert fault.stage == "results"
    assert fault.path == "results/TEST-*.xml"
    assert "no file matched" in fault.cause


# Verifies: REQ-d00285-G
def test_a_coverage_file_that_is_not_there_is_recorded(tmp_path):
    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
reporter = "lcov"
coverage = "coverage/lcov.info"
""",
    )

    (fault,) = _build(project).ingestion_faults()
    assert fault.stage == "coverage"
    assert fault.path == "coverage/lcov.info"
    assert fault.target == "unit"


# Verifies: REQ-d00285-G
def test_a_coverage_file_no_reader_recognises_is_recorded(tmp_path):
    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
reporter = "lcov"
coverage = "coverage/report.txt"
""",
        {"coverage/report.txt": "some other format\n"},
    )

    (fault,) = _build(project).ingestion_faults()
    assert fault.stage == "coverage"
    assert "format" in fault.cause


# Verifies: REQ-d00285-G
def test_a_coverage_report_the_reader_declined_reaches_the_graph(tmp_path):
    """A parser's own record of what it declined is lifted onto the graph."""
    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
reporter = "lcov"
coverage = "coverage/lcov.info"
""",
        {"coverage/lcov.info": "SF:lib/a.dart\nDA:two,1\nend_of_record\n"},
    )

    (fault,) = _build(project).ingestion_faults()
    assert fault.stage == "coverage"
    assert fault.line == 2
    assert fault.target == "unit"


# Verifies: REQ-d00285-G
def test_a_target_reaching_outside_the_repository_is_recorded(tmp_path):
    """The guard already refused it; what was missing was saying so."""
    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
cwd = "../elsewhere"
reporter = "junit"
results = "TEST-*.xml"
""",
    )

    (fault,) = _build(project).ingestion_faults()
    assert fault.stage == "target"
    assert fault.target == "unit"
    assert "outside the repository" in fault.cause


# Verifies: REQ-d00285-G
def test_a_project_declaring_no_targets_records_nothing(tmp_path):
    assert _build(_project(tmp_path, "")).ingestion_faults() == []


# ─────────────────────────────────────────────────────────────────────────────
# Content rules
# ─────────────────────────────────────────────────────────────────────────────


# Verifies: REQ-d00285-A, REQ-d00285-G
def test_a_content_rule_that_is_not_there_is_recorded(tmp_path):
    from elspais.content_rules import ContentRuleFault, load_content_rules

    faults: list[ContentRuleFault] = []
    rules = load_content_rules(
        {"rules": {"content_rules": ["spec/AUTHORING.md"]}}, tmp_path, faults
    )

    assert rules == []
    (fault,) = faults
    assert fault.path.endswith("AUTHORING.md")
    assert "no file there" in fault.cause


# Verifies: REQ-d00285-G
def test_a_content_rule_not_loaded_is_disclosed_without_a_collector(tmp_path, caplog):
    """A caller that asked for no records still does not get silence."""
    import logging

    from elspais.content_rules import load_content_rules

    with caplog.at_level(logging.WARNING):
        rules = load_content_rules({"rules": {"content_rules": ["spec/AUTHORING.md"]}}, tmp_path)

    assert rules == []
    assert any("AUTHORING.md" in record.getMessage() for record in caplog.records)


# Verifies: REQ-d00285-G
def test_a_readable_content_rule_records_nothing(tmp_path):
    from elspais.content_rules import ContentRuleFault, load_content_rules

    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "AUTHORING.md").write_text("# Rule\n\nWrite well.\n", encoding="utf-8")

    faults: list[ContentRuleFault] = []
    rules = load_content_rules(
        {"rules": {"content_rules": ["spec/AUTHORING.md"]}}, tmp_path, faults
    )

    assert len(rules) == 1
    assert faults == []


# ─────────────────────────────────────────────────────────────────────────────
# Reading a scanned file
# ─────────────────────────────────────────────────────────────────────────────


# Verifies: REQ-d00285-A, REQ-p00019-E
def test_a_file_that_cannot_be_decoded_is_named_in_the_failure(tmp_path):
    """A scan of thousands of files must not fail without saying which one."""
    from elspais.graph.deserializer import DomainFile, SourceReadError

    (tmp_path / "notes.md").write_bytes(b"# heading\n\xff\xfe not utf-8\n")

    with pytest.raises(SourceReadError) as caught:
        list(DomainFile(tmp_path, patterns=["*.md"]).iterate_sources())

    assert "notes.md" in str(caught.value)
    assert caught.value.path.name == "notes.md"


# ─────────────────────────────────────────────────────────────────────────────
# What the record is FOR: it is reported
# ─────────────────────────────────────────────────────────────────────────────


def _fault_check(project: Path, config: dict | None = None):
    from elspais.commands.health import check_ingestion_faults

    return check_ingestion_faults(_build(project), config)


_UNPARSEABLE_TARGET = """
[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "results/TEST-*.xml"
"""


# Verifies: REQ-p00019-H, REQ-d00285-A
def test_a_recorded_fault_is_reported_with_its_file_and_line(tmp_path):
    """A record nobody is told about is only marginally better than a drop.

    The finding NAMES the artifact and the line: a count would leave the
    reader the search the tool already performed (REQ-d00285-A).
    """
    project = _project(tmp_path, _UNPARSEABLE_TARGET, {"results/TEST-a.xml": _TRUNCATED_JUNIT})

    check = _fault_check(project)

    assert check.name == "tests.ingestion_fault"
    assert check.passed is False
    (finding,) = check.findings
    assert finding.file_path == "results/TEST-a.xml"
    assert finding.line is not None
    assert "results/TEST-a.xml" in finding.message
    assert "did not parse" in finding.message
    assert finding.location() == f"results/TEST-a.xml:{finding.line}"


# Verifies: REQ-p00019-H
def test_a_fault_with_no_file_names_the_target_it_arose_under(tmp_path):
    """A reporter name nothing matches names no file. The target is the
    location there is, and saying it beats saying nothing."""
    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
reporter = "junitt"
results = "results/TEST-*.xml"
""",
        {"results/TEST-a.xml": _GOOD_JUNIT},
    )

    (finding,) = _fault_check(project).findings
    assert "target unit" in finding.message
    assert "junitt" in finding.message


# Verifies: REQ-p00019-H
def test_a_build_that_read_everything_reports_a_passing_check(tmp_path):
    project = _project(tmp_path, _UNPARSEABLE_TARGET, {"results/TEST-a.xml": _GOOD_JUNIT})

    check = _fault_check(project)
    assert check.passed is True
    assert check.findings == []


# Verifies: REQ-d00285-B, REQ-d00285-D, REQ-d00285-E
def test_the_severity_is_the_one_the_project_configures(tmp_path):
    """The default is `warning`; the project decides otherwise through the
    ONE path the registry declares, and `off` stops the reporting."""
    from elspais.utilities.findings import NO_KNOWN_REMEDY, REGISTRY, remedy_for

    project = _project(tmp_path, _UNPARSEABLE_TARGET, {"results/TEST-a.xml": _TRUNCATED_JUNIT})

    assert REGISTRY["tests.ingestion_fault"].default == "warning"
    assert _fault_check(project).severity == "warning"

    raised = _fault_check(project, {"rules": {"severity": {"tests.ingestion_fault": "error"}}})
    assert raised.severity == "error"

    silenced = _fault_check(project, {"rules": {"severity": {"tests.ingestion_fault": "off"}}})
    assert silenced.details.get("skipped") is True
    assert silenced.findings == []

    # No command repairs an artifact that would not parse, and the finding
    # says so rather than sending the reader to a surface that reports the
    # condition again (REQ-d00285-B).
    assert remedy_for("tests.ingestion_fault") == NO_KNOWN_REMEDY


# Verifies: REQ-p00019-H
def test_every_recorded_fault_reaches_the_report(tmp_path):
    """Two targets, two faults, two findings: nothing is collapsed away."""
    project = _project(
        tmp_path,
        """
[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "results/TEST-*.xml"

[[scanning.test.targets]]
name = "cover"
reporter = "lcov"
coverage = "coverage/lcov.info"
""",
    )

    graph = _build(project)
    check = _fault_check(project)
    assert len(check.findings) == len(graph.ingestion_faults()) == 2
    assert {f.file_path for f in check.findings} == {
        "results/TEST-*.xml",
        "coverage/lcov.info",
    }
    assert check.details["count"] == 2


# Verifies: REQ-p00019-H
def test_the_check_runs_with_the_other_test_checks(tmp_path):
    """A check nothing invokes reports nothing."""
    from elspais.commands.health import run_test_checks

    project = _project(tmp_path, _UNPARSEABLE_TARGET, {"results/TEST-a.xml": _TRUNCATED_JUNIT})
    names = {c.name for c in run_test_checks(_build(project), config={})}
    assert "tests.ingestion_fault" in names


class TestPartialReads:
    """A file read in part yields what it could, and says the total is unknown.

    Re-analysing the source is what produces the statement set. Without it
    the executed lines are still known and the total is not, so the pair
    must be reported as what they are rather than as a complete measurement.
    """

    @staticmethod
    def _coverage_db(tmp_path, source: Path, executed: list[int]):
        """A coverage data file recording lines against ``source``."""
        import coverage

        cov = coverage.Coverage(data_file=str(tmp_path / ".coverage"))
        cov.start()
        cov.stop()
        data = cov.get_data()
        data.add_lines({str(source): executed})
        cov.save()
        return tmp_path / ".coverage"

    # Verifies: REQ-d00254-P
    def test_REQ_d00254_P_lines_that_ran_survive_a_source_that_will_not_parse(self, tmp_path):
        """The lines a run executed are known whatever the source does at
        report time. Discarding them because the file will not parse would
        lose evidence over a defect in a different part of the pipeline.
        """
        from elspais.graph.parsers.results.coverage_sqlite import CoverageSqliteParser

        template = tmp_path / "page.html.j2"
        template.write_text("{# not python #}\n<div>{{ x }}</div>\n")
        db = self._coverage_db(tmp_path, template, [1, 2, 3])

        result = CoverageSqliteParser().parse("", str(db))[str(template)]

        assert result["covered_lines"] == 3
        assert set(result["line_coverage"]) == {1, 2, 3}

    # Verifies: REQ-d00254-Q
    def test_REQ_d00254_Q_a_partial_read_declares_no_total(self, tmp_path):
        """Setting the total to the number of lines that ran would make the
        file read as fully covered -- indistinguishable from a real complete
        measurement, and the most reassuring value available.
        """
        from elspais.graph.parsers.results.coverage_sqlite import CoverageSqliteParser

        template = tmp_path / "page.html.j2"
        template.write_text("{# not python #}\n<div>{{ x }}</div>\n")
        db = self._coverage_db(tmp_path, template, [1, 2, 3])

        result = CoverageSqliteParser().parse("", str(db))[str(template)]

        assert result["source_analysed"] is False
        assert result["executable_lines"] != result["covered_lines"]

    # Verifies: REQ-d00254-Q
    def test_REQ_d00254_Q_the_condition_is_recorded_as_partial(self, tmp_path):
        """Which of the two conditions occurred is known only where the
        decision was made. A caller counting records afterwards cannot tell
        an artifact that yielded little from one that yielded nothing.
        """
        from elspais.graph.parsers.results.coverage_sqlite import CoverageSqliteParser

        template = tmp_path / "page.html.j2"
        template.write_text("{# not python #}\n")
        db = self._coverage_db(tmp_path, template, [1])

        parser = CoverageSqliteParser()
        parser.parse("", str(db))

        (diagnostic,) = [d for d in parser.iter_diagnostics() if d.path == str(template)]
        assert diagnostic.partial is True

    # Verifies: REQ-d00254-Q
    def test_REQ_d00254_Q_an_unanalysed_file_leaves_the_line_coverage_figure(self):
        """Both sums must skip it. Excluding the total but keeping the lines
        that ran would raise the figure by exactly the lines whose size is
        unknown -- worse than counting it whole.
        """
        from elspais.graph.annotators import count_code_coverage

        class _Node:
            def __init__(self, fields):
                self._fields = fields

            def get_field(self, name):
                return self._fields.get(name)

        class _Graph:
            def iter_by_kind(self, kind):
                return iter(
                    [
                        _Node(
                            {"executable_lines": 10, "line_coverage": dict.fromkeys(range(5), 1)}
                        ),
                        _Node(
                            {
                                "source_analysed": False,
                                "executable_lines": 0,
                                "line_coverage": dict.fromkeys(range(90), 1),
                            }
                        ),
                    ]
                )

            def nodes_by_kind(self, kind):
                return iter([])

        result = count_code_coverage(_Graph())

        assert result["total_executable_lines"] == 10
        assert result["total_covered_lines"] == 5
        assert result["unmeasured_files"] == 1
