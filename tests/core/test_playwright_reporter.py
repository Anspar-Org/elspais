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
