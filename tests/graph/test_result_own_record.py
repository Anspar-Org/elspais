# Verifies: REQ-d00294-A, REQ-d00294-B, REQ-d00294-C, REQ-d00294-D, REQ-d00294-F
"""Every record a producer wrote is held as a result of its own.

One test run in more than one environment is reported once for each of
them. The records agree about the test, the class and the line, so the
place the record was written in and its position there are what tell them
apart. Without that, the later record takes the place of the earlier one
and its verdict is lost.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from elspais.config.schema import TestTargetConfig
from elspais.graph.builder import GraphBuilder
from elspais.graph.factory import _ingest_target_results
from elspais.graph.GraphNode import NodeKind
from tests.core.graph_test_helpers import grammar_for

# One test, reported twice: the same suite ran on two devices. Nothing but
# the position in the file separates the two records.
_TWO_ENVIRONMENTS = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="checkout" tests="2">
  <testcase classname="tests.test_checkout" name="test_pays" time="0.5"/>
  <testcase classname="tests.test_checkout" name="test_pays" time="0.7">
    <failure message="timed out"/>
  </testcase>
</testsuite>
"""

# One suite, one test, reported on a runner's stdout: no artifact holds it.
_FLUTTER_STREAM = (
    '{"type":"suite","suite":{"id":0,"platform":"vm","path":"test/widget_test.dart"}}\n'
    '{"type":"testStart","test":{"id":1,"name":"renders","suiteID":0,'
    '"line":10,"column":5,"metadata":{},"root_line":10,"root_column":5}}\n'
    '{"type":"testDone","testID":1,"result":"success","hidden":false,"time":42}\n'
    '{"type":"testStart","test":{"id":2,"name":"renders","suiteID":0,'
    '"line":10,"column":5,"metadata":{},"root_line":10,"root_column":5}}\n'
    '{"type":"testDone","testID":2,"result":"failure","hidden":false,"time":43}\n'
    '{"type":"done","success":false,"time":44}\n'
)


def _builder(tmp_path: Path) -> GraphBuilder:
    return GraphBuilder(repo_root=tmp_path, namespace="REQ", resolver=grammar_for("REQ"))


# Verifies: REQ-d00294-A
def test_two_records_of_one_test_are_two_results(tmp_path: Path):
    """Two records of one test keep both verdicts, told apart by position."""
    artifact = tmp_path / "reports" / "junit.xml"
    artifact.parent.mkdir()
    artifact.write_text(_TWO_ENVIRONMENTS, encoding="utf-8")
    builder = _builder(tmp_path)
    target = TestTargetConfig(name="unit", reporter="junit", results="reports/junit.xml")

    count = _ingest_target_results(
        builder, target, _TWO_ENVIRONMENTS, tmp_path, str(artifact), namespace="REQ"
    )

    assert count == 2
    graph = builder.build()
    results = sorted(graph.iter_by_kind(NodeKind.RESULT), key=lambda n: n.id)
    assert [n.id for n in results] == [
        "result:REQ:reports/junit.xml:1",
        "result:REQ:reports/junit.xml:2",
    ]
    assert {n.get_field("status") for n in results} == {"passed", "failed"}


# Verifies: REQ-d00294-B
def test_a_stream_places_its_records_by_target(tmp_path: Path):
    """Results read from a runner's output are placed by the target."""
    builder = _builder(tmp_path)
    target = TestTargetConfig(name="widgets", reporter="flutter-machine", match="source")

    count = _ingest_target_results(builder, target, _FLUTTER_STREAM, tmp_path, "", namespace="REQ")

    assert count == 2
    graph = builder.build()
    results = sorted(graph.iter_by_kind(NodeKind.RESULT), key=lambda n: n.id)
    assert [n.id for n in results] == [
        "result:REQ:widgets/:1",
        "result:REQ:widgets/:2",
    ]
    assert {n.get_field("status") for n in results} == {"passed", "failed"}


# One artifact for each device: the glob's wildcard segment names the device.
_ONE_RECORD = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="checkout" tests="1">
  <testcase classname="tests.test_checkout" name="test_pays" time="0.5"/>
</testsuite>
"""

# One artifact for every browser: the suite says which one wrote each record.
_TWO_SUITES = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="checkout" hostname="chromium" tests="1">
    <testcase classname="tests.test_checkout" name="test_pays" time="0.5"/>
  </testsuite>
  <testsuite name="checkout" hostname="firefox" tests="1">
    <testcase classname="tests.test_checkout" name="test_pays" time="0.7">
      <failure message="timed out"/>
    </testcase>
  </testsuite>
</testsuites>
"""


def _write(tmp_path: Path, relative: str, text: str) -> Path:
    artifact = tmp_path / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(text, encoding="utf-8")
    return artifact


def _environments(builder: GraphBuilder) -> list[str | None]:
    graph = builder.build()
    results = sorted(graph.iter_by_kind(NodeKind.RESULT), key=lambda n: n.id)
    return [n.get_field("environment") for n in results]


# Verifies: REQ-d00294-C
def test_the_results_path_names_the_environment(tmp_path: Path):
    """The wildcard segment of the results glob is read as the environment."""
    builder = _builder(tmp_path)
    target = TestTargetConfig(
        name="devices",
        reporter="junit",
        results="evidence/*/journey-results.xml",
        environment="results-path",
    )

    for device in ("pixel-8", "iphone-15"):
        artifact = _write(tmp_path, f"evidence/{device}/journey-results.xml", _ONE_RECORD)
        _ingest_target_results(
            builder,
            target,
            _ONE_RECORD,
            tmp_path,
            str(artifact),
            namespace="REQ",
            results_pattern=target.results,
            results_base=tmp_path,
        )

    assert sorted(e for e in _environments(builder) if e) == ["iphone-15", "pixel-8"]
    assert builder.build().ingestion_faults() == []


# Verifies: REQ-d00294-C
def test_the_suite_hostname_names_the_environment(tmp_path: Path):
    """The suite's hostname is read as the environment where a target says so."""
    builder = _builder(tmp_path)
    target = TestTargetConfig(
        name="browsers",
        reporter="junit",
        results="test-results/junit.xml",
        environment="suite-hostname",
    )
    artifact = _write(tmp_path, "test-results/junit.xml", _TWO_SUITES)

    _ingest_target_results(
        builder,
        target,
        _TWO_SUITES,
        tmp_path,
        str(artifact),
        namespace="REQ",
        results_pattern=target.results,
        results_base=tmp_path,
    )

    assert _environments(builder) == ["chromium", "firefox"]


# Verifies: REQ-d00294-C
def test_no_declared_source_gives_no_environment(tmp_path: Path):
    """A hostname in the file is not an environment until a target says it is."""
    builder = _builder(tmp_path)
    target = TestTargetConfig(name="browsers", reporter="junit", results="test-results/junit.xml")
    artifact = _write(tmp_path, "test-results/junit.xml", _TWO_SUITES)

    _ingest_target_results(
        builder,
        target,
        _TWO_SUITES,
        tmp_path,
        str(artifact),
        namespace="REQ",
        results_pattern=target.results,
        results_base=tmp_path,
    )

    assert _environments(builder) == [None, None]
    assert builder.build().ingestion_faults() == []


# Verifies: REQ-d00294-D
@pytest.mark.parametrize(
    "pattern,relatives,expected_in_cause",
    [
        (
            "evidence/**/journey-results.xml",
            ["evidence/pixel-8/journey-results.xml", "evidence/iphone-15/journey-results.xml"],
            "`**`",
        ),
        (
            "evidence/*/run-*/results.xml",
            ["evidence/pixel-8/run-1/results.xml", "evidence/iphone-15/run-1/results.xml"],
            "2 wildcard",
        ),
    ],
)
def test_a_pattern_naming_no_one_segment_derives_none(
    tmp_path: Path, pattern: str, relatives: list[str], expected_in_cause: str
):
    """A pattern that cannot say which segment is the environment derives none.

    The pattern is one condition however many files it matched, so it is
    reported once rather than once for each of them.
    """
    builder = _builder(tmp_path)
    target = TestTargetConfig(
        name="devices", reporter="junit", results=pattern, environment="results-path"
    )

    for relative in relatives:
        artifact = _write(tmp_path, relative, _ONE_RECORD)
        _ingest_target_results(
            builder,
            target,
            _ONE_RECORD,
            tmp_path,
            str(artifact),
            namespace="REQ",
            results_pattern=pattern,
            results_base=tmp_path,
        )

    assert _environments(builder) == [None, None]
    faults = builder.build().ingestion_faults()
    assert len(faults) == 1
    assert expected_in_cause in faults[0].cause
    assert faults[0].target == "devices"
    assert faults[0].path == pattern


# Verifies: REQ-d00294-D
def test_a_format_carrying_no_hostname_says_so(tmp_path: Path):
    """A format with no suite hostname at all is reported as that, not as a blank one."""
    builder = _builder(tmp_path)
    target = TestTargetConfig(
        name="widgets",
        reporter="flutter-machine",
        match="source",
        environment="suite-hostname",
    )

    _ingest_target_results(builder, target, _FLUTTER_STREAM, tmp_path, "", namespace="REQ")

    assert _environments(builder) == [None, None]
    faults = builder.build().ingestion_faults()
    assert len(faults) == 1
    assert "carry no suite hostname" in faults[0].cause


# Verifies: REQ-d00294-D
def test_a_record_holding_no_hostname_derives_none(tmp_path: Path):
    """A declared hostname source that finds no hostname reports that it found none."""
    builder = _builder(tmp_path)
    target = TestTargetConfig(
        name="unit",
        reporter="junit",
        results="reports/junit.xml",
        environment="suite-hostname",
    )
    artifact = _write(tmp_path, "reports/junit.xml", _ONE_RECORD)

    _ingest_target_results(
        builder,
        target,
        _ONE_RECORD,
        tmp_path,
        str(artifact),
        namespace="REQ",
        results_pattern=target.results,
        results_base=tmp_path,
    )

    assert _environments(builder) == [None]
    faults = builder.build().ingestion_faults()
    assert len(faults) == 1
    assert "names no hostname" in faults[0].cause


# Verifies: REQ-d00294-D
def test_a_stream_declaring_a_path_source_derives_none(tmp_path: Path):
    """A runner's output has no results path, so no environment comes from one."""
    builder = _builder(tmp_path)
    target = TestTargetConfig(
        name="widgets",
        reporter="flutter-machine",
        match="source",
        environment="results-path",
    )

    _ingest_target_results(builder, target, _FLUTTER_STREAM, tmp_path, "", namespace="REQ")

    assert _environments(builder) == [None, None]
    faults = builder.build().ingestion_faults()
    assert len(faults) == 1
    assert "runner's output" in faults[0].cause


# Verifies: REQ-d00294-F
def test_a_result_is_named_the_same_with_and_without_an_environment(tmp_path: Path):
    """An environment sits beside the result, never inside the name it carries."""
    labels = []
    for source in ("", "suite-hostname"):
        builder = _builder(tmp_path)
        target = TestTargetConfig(
            name="browsers",
            reporter="junit",
            results="test-results/junit.xml",
            environment=source,
        )
        artifact = _write(tmp_path, "test-results/junit.xml", _TWO_SUITES)
        _ingest_target_results(
            builder,
            target,
            _TWO_SUITES,
            tmp_path,
            str(artifact),
            namespace="REQ",
            results_pattern=target.results,
            results_base=tmp_path,
        )
        graph = builder.build()
        labels.append(
            [n.label for n in sorted(graph.iter_by_kind(NodeKind.RESULT), key=lambda n: n.id)]
        )

    assert labels[0] == labels[1]


# Verifies: REQ-d00294-C
def test_an_unknown_environment_source_is_refused():
    """A target may only declare a source the tool reads."""
    with pytest.raises(ValidationError):
        TestTargetConfig(name="devices", reporter="junit", environment="hostname")


# A flutter suite saved to one file for each device, then read back by a
# pattern. The format usually arrives on a runner's output, and a target that
# saves it still has one artifact for each device.
_FLUTTER_ONE_RECORD = (
    '{"type":"suite","suite":{"id":0,"platform":"vm","path":"test/widget_test.dart"}}\n'
    '{"type":"testStart","test":{"id":1,"name":"renders","suiteID":0,'
    '"line":10,"column":5,"metadata":{},"root_line":10,"root_column":5}}\n'
    '{"type":"testDone","testID":1,"result":"%s","hidden":false,"time":42}\n'
)


# Verifies: REQ-d00294-A
def test_a_saved_stream_is_placed_by_its_artifact(tmp_path: Path):
    """Records saved to one file for each device do not take each other's place.

    The format carries no artifact when it arrives on a runner's output. Read
    back from files, each file is what separates its records from the next
    file's: every file counts its records from one, so without the artifact
    every device writes the same identity and one verdict survives.
    """
    builder = _builder(tmp_path)
    target = TestTargetConfig(
        name="widgets",
        reporter="flutter-machine",
        results="evidence/*/machine.json",
        match="source",
    )
    for device, verdict in (("pixel6", "success"), ("pixel8", "failure")):
        artifact = _write(
            tmp_path, f"evidence/{device}/machine.json", _FLUTTER_ONE_RECORD % verdict
        )
        _ingest_target_results(
            builder,
            target,
            artifact.read_text(encoding="utf-8"),
            tmp_path,
            str(artifact),
            namespace="REQ",
        )

    graph = builder.build()
    results = sorted(graph.iter_by_kind(NodeKind.RESULT), key=lambda n: n.id)
    assert [n.id for n in results] == [
        "result:REQ:evidence/pixel6/machine.json:1",
        "result:REQ:evidence/pixel8/machine.json:1",
    ]
    assert {n.get_field("status") for n in results} == {"passed", "failed"}


# Verifies: REQ-d00294-C
@pytest.mark.parametrize(
    ("pattern", "relative", "expected"),
    [
        ("evidence/*/junit.xml", "evidence/pixel6/junit.xml", "pixel6"),
        ("evidence/junit-*.xml", "evidence/junit-pixel6.xml", "pixel6"),
        ("evidence/*.xml", "evidence/pixel6.xml", "pixel6"),
    ],
)
def test_the_environment_is_what_the_wildcard_stood_for(
    tmp_path: Path, pattern: str, relative: str, expected: str
):
    """The environment is the matched part of the segment, not the whole segment.

    A pattern names the environment in the middle of a segment as readily as
    it names a whole one. Reading the whole segment would call the environment
    `junit-pixel6.xml` where the project means `pixel6`, and a name that
    reports the wrong thing is worse than no name at all.
    """
    builder = _builder(tmp_path)
    target = TestTargetConfig(
        name="devices",
        reporter="junit",
        results=pattern,
        environment="results-path",
        match="source",
    )
    artifact = _write(tmp_path, relative, _ONE_RECORD)
    _ingest_target_results(
        builder,
        target,
        _ONE_RECORD,
        tmp_path,
        str(artifact),
        namespace="REQ",
        results_pattern=pattern,
        results_base=tmp_path,
    )

    assert _environments(builder) == [expected]
