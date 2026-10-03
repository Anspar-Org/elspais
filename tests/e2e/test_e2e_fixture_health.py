# Verifies: REQ-p00002
"""E2E health check validation on test fixtures.

Invokes `elspais checks` as a subprocess on each fixture project, verifying
the CLI produces correct JSON output and exit codes, and that every fixture
passes its own health checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import FIXTURES_DIR, load_fixture, requires_elspais, run_elspais

# Fixtures that have their own .elspais.toml and spec/ directory
FIXTURE_DIRS = sorted(
    d
    for d in FIXTURES_DIR.iterdir()
    if d.is_dir() and (d / ".elspais.toml").exists() and (d / "spec").exists()
)

pytestmark = [pytest.mark.e2e, requires_elspais]


@pytest.fixture(scope="module", params=FIXTURE_DIRS, ids=[d.name for d in FIXTURE_DIRS])
def fixture_dir(request, tmp_path_factory) -> Path:
    """A copy of one fixture that is its own git repository.

    The CLI runs from the git root of the directory it is started in. Inside
    the checkout that root is the checkout, so a check started in
    ``tests/fixtures/<name>`` would judge the checkout instead. The copy is
    a repository of its own, so the CLI's root is the fixture.
    """
    dest = tmp_path_factory.mktemp(f"fixture-health-{request.param.name}")
    return load_fixture(request.param.name, dest)


class TestFixtureHealthE2E:
    """Validates REQ-p00002: elspais health CLI works on fixture projects."""

    def test_REQ_p00002_checks_read_the_fixture(self, fixture_dir) -> None:
        """The configuration the CLI reads is the fixture's own."""
        result = run_elspais("config", "path", cwd=fixture_dir)

        assert result.returncode == 0, result.stderr
        assert Path(result.stdout.strip()).resolve().parent == fixture_dir.resolve(), (
            f"expected {fixture_dir}/.elspais.toml, the CLI read {result.stdout.strip()}"
        )

    def test_REQ_p00002_health_json_no_errors(self, fixture_dir) -> None:
        """elspais health --format json exits cleanly with no error-level failures."""
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=fixture_dir)

        assert result.returncode == 0, (
            f"elspais health failed on {fixture_dir.name} "
            f"(exit {result.returncode}):\n{result.stderr or result.stdout}"
        )

        data = json.loads(result.stdout)
        assert data["summary"]["failed"] == 0, (
            f"Fixture {fixture_dir.name} has {data['summary']['failed']} error(s)"
        )

    def test_REQ_p00002_health_text_output(self, fixture_dir) -> None:
        """elspais health produces readable text output."""
        result = run_elspais("checks", "--lenient", cwd=fixture_dir)

        assert result.returncode == 0, (
            f"elspais health failed on {fixture_dir.name}:\n{result.stderr}"
        )
        # Text output should contain section headers
        assert "SPEC" in result.stdout or "spec" in result.stdout.lower()

    def test_REQ_p00002_health_spec_only(self, fixture_dir) -> None:
        """elspais health --spec runs only spec checks."""
        result = run_elspais("checks", "--spec", "--format", "json", "--lenient", cwd=fixture_dir)

        assert result.returncode == 0
        data = json.loads(result.stdout)
        categories = {c["category"] for c in data["checks"]}
        # --spec should only produce spec-category checks -- "references" is
        # part of that family (run_spec_checks emits both), not a code/tests
        # category leaking in.
        assert categories <= {"spec", "references"}, f"Expected only spec checks, got: {categories}"

    def test_REQ_p00002_health_formats(self, fixture_dir) -> None:
        """elspais health supports multiple output formats without crashing."""
        for fmt in ("text", "json", "markdown", "junit", "sarif"):
            result = run_elspais("checks", "--format", fmt, "--lenient", cwd=fixture_dir)
            assert result.returncode == 0, (
                f"Format {fmt} failed on {fixture_dir.name}:\n{result.stderr}"
            )
            assert len(result.stdout) > 0, f"Format {fmt} produced empty output"
