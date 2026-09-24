# Verifies: REQ-d00294-C, REQ-d00254-G
"""The shipped Playwright reporter names each test's source and its project.

Playwright's own reporter writes a test's name and its class, and it keeps the
test's location for the message of a failure. A result then binds to every
test in a file rather than to the one that produced it, and every project's
records read alike. The shipped reporter writes the location and the project,
which is what lets a reader tell the records apart and bind each one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_REPORTER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "elspais"
    / "recipes"
    / "playwright-junit-reporter.mjs"
)

_DRIVER = """\
import Reporter from './playwright-junit-reporter.mjs';
const root = process.cwd();
const cases = JSON.parse(process.argv[2]);
const r = new Reporter({ outputFile: 'junit.xml' });
r.onBegin({ rootDir: root });
for (const c of cases) {
    r.onTestEnd(
        { titlePath: () => ['', c.project, c.file, c.title],
          location: { file: `${root}/${c.file}`, line: c.line, column: 1 } },
        { duration: 500, status: c.status, error: c.message ? { message: c.message } : undefined }
    );
}
r.onEnd();
"""


def _run(tmp_path: Path, cases: list[dict]) -> ET.Element:
    """Run the reporter over *cases* and return the report it wrote."""
    shutil.copy(_REPORTER, tmp_path / _REPORTER.name)
    (tmp_path / "drive.mjs").write_text(_DRIVER, encoding="utf-8")
    subprocess.run(
        ["node", "drive.mjs", json.dumps(cases)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return ET.parse(tmp_path / "junit.xml").getroot()


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


# Verifies: REQ-d00254-G
@pytest.mark.e2e
def test_each_record_names_the_source_of_its_test(tmp_path: Path):
    """A record names the file its test is in and the line it starts on."""
    root = _run(
        tmp_path,
        [
            {
                "project": "chromium",
                "file": "e2e/checkout.spec.ts",
                "title": "pays",
                "line": 12,
                "status": "passed",
            }
        ],
    )

    case = root.find(".//testcase")
    assert case.get("file") == "e2e/checkout.spec.ts"
    assert case.get("line") == "12"


# Verifies: REQ-d00294-C
@pytest.mark.e2e
def test_each_project_writes_its_own_suite(tmp_path: Path):
    """One test in two projects writes one record in each, under its project."""
    root = _run(
        tmp_path,
        [
            {
                "project": "chromium",
                "file": "e2e/a.spec.ts",
                "title": "pays",
                "line": 3,
                "status": "passed",
            },
            {
                "project": "firefox",
                "file": "e2e/a.spec.ts",
                "title": "pays",
                "line": 3,
                "status": "failed",
                "message": "timed out",
            },
        ],
    )

    suites = root.findall("testsuite")
    assert sorted(s.get("hostname") for s in suites) == ["chromium", "firefox"]
    failing = [s for s in suites if s.get("hostname") == "firefox"][0]
    assert failing.find(".//failure") is not None


# Verifies: REQ-d00254-G
@pytest.mark.e2e
def test_a_skipped_test_is_recorded_as_skipped(tmp_path: Path):
    """A test that did not run is recorded as skipped, not as a failure."""
    root = _run(
        tmp_path,
        [
            {
                "project": "chromium",
                "file": "e2e/a.spec.ts",
                "title": "on mobile",
                "line": 9,
                "status": "skipped",
            }
        ],
    )

    assert root.find(".//testcase/skipped") is not None
    assert root.find(".//testcase/failure") is None


# A driver that hands the reporter what Playwright hands it: one test object
# per test per project, `onTestEnd` once for every ATTEMPT of it, and a config
# whose `rootDir` is the test directory rather than the project.
_ATTEMPT_DRIVER = """\
import path from 'node:path';
import Reporter from './playwright-junit-reporter.mjs';
const spec = JSON.parse(process.argv[2]);
const here = process.cwd();
const r = new Reporter(spec.options || {});
const tests = spec.tests.map((c) => ({
    expectedStatus: c.expectedStatus || 'passed',
    titlePath: () => ['', c.project, c.file, c.title],
    location: { file: path.join(here, c.file), line: c.line, column: 1 },
    attempts: c.attempts,
}));
r.onBegin(
    { rootDir: path.join(here, spec.testDir || '.'),
      configFile: spec.configFile ? path.join(here, spec.configFile) : undefined },
    { allTests: () => tests }
);
for (const t of tests) {
    for (const a of t.attempts) {
        r.onTestEnd(t, { duration: 100, status: a.status,
                         error: a.message ? { message: a.message } : undefined });
    }
}
r.onEnd();
"""


def _run_attempts(tmp_path: Path, spec: dict, report: str = "junit.xml") -> tuple[str, Path]:
    """Drive the reporter through *spec*; return the report text and its path."""
    shutil.copy(_REPORTER, tmp_path / _REPORTER.name)
    (tmp_path / "drive.mjs").write_text(_ATTEMPT_DRIVER, encoding="utf-8")
    subprocess.run(
        ["node", "drive.mjs", json.dumps(spec)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    written = tmp_path / report
    return written.read_text(encoding="utf-8"), written


def _case(title: str, attempts: list[dict], **extra) -> dict:
    return {
        "project": "chromium",
        "file": "tests/a.spec.ts",
        "title": title,
        "line": 4,
        "attempts": attempts,
        **extra,
    }


# Verifies: REQ-d00294-A, REQ-d00294-E
@pytest.mark.e2e
@pytest.mark.parametrize(
    "case,expected",
    [
        (
            _case("flaky", [{"status": "failed", "message": "first try"}, {"status": "passed"}]),
            "passed",
        ),
        (
            _case(
                "expected failure", [{"status": "failed", "message": "x"}], expectedStatus="failed"
            ),
            "passed",
        ),
        (
            _case(
                "always fails",
                [{"status": "failed", "message": "a"}, {"status": "failed", "message": "b"}],
            ),
            "failed",
        ),
        (_case("never ran", []), "skipped"),
    ],
    ids=["flaky", "test-fail", "retried-failure", "never-reached"],
)
def test_one_record_carries_the_outcome_of_every_attempt(tmp_path: Path, case, expected):
    """A test writes one record per project, carrying the outcome Playwright judges.

    Writing an attempt as a record would hand the tool a failing result for a
    test the runner itself calls passed.
    """
    from elspais.graph.parsers.results.junit_xml import JUnitXMLParser

    text, _ = _run_attempts(tmp_path, {"tests": [case]})

    records = JUnitXMLParser().parse(text, "junit.xml")
    assert [r["status"] for r in records] == [expected]


# Verifies: REQ-d00294-E
@pytest.mark.e2e
def test_a_failure_message_carrying_terminal_colour_still_parses(tmp_path: Path):
    """An `expect()` message holds ANSI escapes; the report must still be read.

    One unreadable character loses every record in the file, the failing one
    included.
    """
    from elspais.graph.parsers.results.junit_xml import JUnitXMLParser

    message = "Error: \u001b[2mexpect(\u001b[22m\u001b[31mreceived\u001b[39m\u0001).toBe(2)"
    text, _ = _run_attempts(
        tmp_path,
        {
            "tests": [
                _case("fails", [{"status": "failed", "message": message}]),
                _case("passes", [{"status": "passed"}], line=9),
            ]
        },
    )

    ET.fromstring(text)
    parser = JUnitXMLParser()
    records = parser.parse(text, "junit.xml")
    assert sorted(r["status"] for r in records) == ["failed", "passed"]
    assert list(parser.iter_diagnostics()) == []
    failing = [r for r in records if r["status"] == "failed"][0]
    assert "\u001b" not in failing["message"]
    assert "received" in failing["message"]


# Verifies: REQ-d00294-A
@pytest.mark.e2e
def test_paths_are_read_from_the_config_directory_not_the_test_directory(tmp_path: Path):
    """`rootDir` is Playwright's test directory; the report and `file` follow the config.

    Relative to the test directory, `file` names a path the tool cannot find
    and the report lands where no `results` pattern points.
    """
    (tmp_path / "e2e").mkdir()
    text, written = _run_attempts(
        tmp_path,
        {
            "configFile": "e2e/playwright.config.ts",
            "testDir": "e2e/tests",
            "options": {"outputFile": "out/junit.xml"},
            "tests": [_case("passes", [{"status": "passed"}], file="e2e/tests/a.spec.ts")],
        },
        report="e2e/out/junit.xml",
    )

    assert written.exists()
    assert not (tmp_path / "e2e" / "tests" / "out" / "junit.xml").exists()
    case = ET.fromstring(text).find(".//testcase")
    assert case.get("file") == "tests/a.spec.ts"
    assert case.get("line") == "4"


# Verifies: REQ-d00294-A
def test_the_recipes_suggested_target_declares_its_line_origin():
    """The reporter counts lines from one and JUnit declares zero, so the snippet says so."""
    header = _REPORTER.read_text(encoding="utf-8").split("import ", 1)[0]
    assert "line_base   = 1" in header or "line_base = 1" in header
