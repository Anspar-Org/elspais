# Validates: REQ-p00013-B, REQ-p00080-A
"""End-to-end subprocess tests for elspais CLI commands.

Each test invokes the elspais binary as a subprocess and validates
return codes, output format, and content.
"""

import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from .conftest import requires_pandoc, requires_xelatex, run_elspais

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


class TestVersion:
    """Validates REQ-p00013-B: version command output."""

    def test_REQ_p00013_B_version_returns_zero(self):
        result = run_elspais("version")
        assert result.returncode == 0

    def test_REQ_p00013_B_version_output_contains_number(self):
        result = run_elspais("version")
        assert "." in result.stdout, f"Expected version number in output: {result.stdout!r}"


class TestDoctor:
    """Validates REQ-p00013-B: doctor command diagnostics."""

    def test_REQ_p00013_B_doctor_returns_zero(self):
        result = run_elspais("doctor")
        assert result.returncode == 0

    def test_REQ_p00013_B_doctor_json_valid(self):
        result = run_elspais("doctor", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))


class TestSummary:
    """Validates REQ-p00013-B: summary command output formats."""

    def test_REQ_p00013_B_summary_text_returns_zero(self):
        result = run_elspais("summary")
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_REQ_p00013_B_summary_json_valid(self):
        result = run_elspais("summary", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_REQ_p00013_B_summary_csv_returns_zero(self):
        result = run_elspais("summary", "--format", "csv")
        assert result.returncode == 0


class TestTrace:
    """Validates REQ-p00013-B: trace command output formats."""

    def test_REQ_p00013_B_trace_json_valid(self, tmp_path):
        out = tmp_path / "trace"
        result = run_elspais("trace", "--format", "json", "--output", str(out))
        assert result.returncode == 0
        candidates = [out, out.with_suffix(".json"), Path(f"{out}.json")]
        found = [p for p in candidates if p.exists()]
        assert found, f"No trace output file found among {candidates}"
        data = json.loads(found[0].read_text())
        assert isinstance(data, (dict, list))

    def test_REQ_p00013_B_trace_csv_returns_zero(self, tmp_path):
        out = tmp_path / "trace"
        result = run_elspais("trace", "--format", "csv", "--output", str(out))
        assert result.returncode == 0

    def test_REQ_p00013_B_trace_html_creates_file(self, tmp_path):
        out = tmp_path / "trace"
        result = run_elspais("trace", "--format", "html", "--output", str(out))
        if result.returncode != 0 and "jinja2" in result.stderr.lower():
            pytest.skip("trace-view extra (jinja2) not installed")
        assert result.returncode == 0
        candidates = [out, out.with_suffix(".html"), Path(f"{out}.html")]
        found = [p for p in candidates if p.exists()]
        assert found, f"No HTML trace file found among {candidates}"

    def test_REQ_p00013_B_trace_markdown_creates_file(self, tmp_path):
        out = tmp_path / "trace"
        result = run_elspais("trace", "--format", "markdown", "--output", str(out))
        assert result.returncode == 0
        candidates = [out, out.with_suffix(".md"), Path(f"{out}.md")]
        found = [p for p in candidates if p.exists()]
        assert found, f"No markdown trace file found among {candidates}"


class TestGraph:
    """Validates REQ-p00013-B: graph command output."""

    def test_REQ_p00013_B_graph_returns_zero(self):
        result = run_elspais("graph")
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


class TestConfig:
    """Validates REQ-p00013-B: config subcommands."""

    def test_REQ_p00013_B_config_show_returns_zero(self):
        result = run_elspais("config", "show")
        assert result.returncode == 0

    def test_REQ_p00013_B_config_path_returns_toml(self):
        result = run_elspais("config", "path")
        assert result.returncode == 0
        assert ".toml" in result.stdout

    def test_REQ_p00013_B_config_get_namespace(self):
        result = run_elspais("config", "get", "project.namespace")
        assert result.returncode == 0
        assert "REQ" in result.stdout


class TestExample:
    """Validates REQ-p00013-B: example command output."""

    def test_REQ_p00013_B_example_returns_zero(self):
        result = run_elspais("example")
        assert result.returncode == 0

    def test_REQ_p00013_B_example_ids_shows_req_ids(self):
        result = run_elspais("example", "ids")
        assert result.returncode == 0
        assert "REQ" in result.stdout


class TestDocs:
    """Validates REQ-p00013-B: docs command output."""

    def test_REQ_p00013_B_docs_lists_topics_in_help(self):
        result = run_elspais("docs", "--help")
        assert result.returncode == 0
        assert "quickstart" in result.stdout

    def test_REQ_p00013_B_docs_quickstart_plain(self):
        result = run_elspais("docs", "quickstart", "--plain")
        assert result.returncode == 0
        assert len(result.stdout) > 100


class TestChanged:
    """Validates REQ-p00013-B: changed command."""

    def test_REQ_p00013_B_changed_returns_zero(self):
        result = run_elspais("changed")
        assert result.returncode == 0


class TestRules:
    """Validates REQ-p00013-B: rules command output."""

    def test_REQ_p00013_B_rules_list_returns_zero(self):
        result = run_elspais("rules", "list")
        assert result.returncode == 0
        output = result.stdout.lower()
        assert any(
            term in output for term in ["implements", "->", "rule", "hierarchy"]
        ), f"Expected hierarchy rule content in: {result.stdout[:200]}"


class TestHealth:
    """Validates REQ-p00013-B: health command output formats."""

    def test_REQ_p00013_B_health_lenient_returns_zero(self):
        result = run_elspais("health", "--lenient")
        assert result.returncode == 0

    def test_REQ_p00013_B_health_json_valid(self):
        result = run_elspais("health", "--format", "json", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))

    def test_REQ_p00013_B_health_markdown_returns_zero(self):
        result = run_elspais("health", "--format", "markdown", "--lenient")
        assert result.returncode == 0

    def test_REQ_p00013_B_health_spec_only_returns_zero(self):
        result = run_elspais("health", "--spec", "--lenient")
        assert result.returncode == 0

    def test_REQ_p00013_B_health_junit_produces_valid_xml(self):
        result = run_elspais("health", "--format", "junit", "--lenient")
        assert result.returncode == 0
        root = ET.fromstring(result.stdout)
        assert root.tag == "testsuites"

    def test_REQ_p00013_B_health_junit_has_testsuites(self):
        result = run_elspais("health", "--format", "junit", "--lenient")
        assert result.returncode == 0
        root = ET.fromstring(result.stdout)
        suites = root.findall("testsuite")
        assert len(suites) >= 1, "Expected at least one <testsuite> element"

    def test_REQ_p00013_B_health_sarif_produces_valid_json(self):
        result = run_elspais("health", "--format", "sarif", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["version"] == "2.1.0"
        assert "$schema" in data

    def test_REQ_p00013_B_health_sarif_has_runs(self):
        result = run_elspais("health", "--format", "sarif", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["runs"]) == 1
        assert data["runs"][0]["tool"]["driver"]["name"] == "elspais"

    def test_REQ_p00013_B_health_junit_output_to_file(self, tmp_path):
        out = tmp_path / "health.xml"
        result = run_elspais("health", "--format", "junit", "--lenient", "-o", str(out))
        assert result.returncode == 0
        assert out.exists(), f"Expected {out} to be created"
        root = ET.parse(str(out)).getroot()
        assert root.tag == "testsuites"

    def test_REQ_p00013_B_health_sarif_output_to_file(self, tmp_path):
        out = tmp_path / "health.sarif"
        result = run_elspais("health", "--format", "sarif", "--lenient", "-o", str(out))
        assert result.returncode == 0
        assert out.exists(), f"Expected {out} to be created"
        data = json.loads(out.read_text())
        assert data["version"] == "2.1.0"

    def test_REQ_p00013_B_health_include_passing_details(self):
        result = run_elspais("health", "--include-passing-details", "--lenient")
        assert result.returncode == 0


class TestInit:
    """Validates REQ-p00013-B: init command creates config."""

    def test_REQ_p00013_B_init_creates_toml(self, tmp_path):
        result = run_elspais("init", cwd=tmp_path)
        assert result.returncode == 0
        toml_file = tmp_path / ".elspais.toml"
        assert toml_file.exists(), f"Expected .elspais.toml in {tmp_path}"


class TestFix:
    """Validates REQ-p00013-B: fix command dry-run."""

    def test_REQ_p00013_B_fix_dry_run_no_crash(self):
        result = run_elspais("fix", "--dry-run")
        # fix may return 0 (nothing to fix) or 1 (issues found); just shouldn't crash
        assert result.returncode in (
            0,
            1,
        ), f"fix --dry-run crashed with rc={result.returncode}: {result.stderr}"


class TestPdf:
    """Validates REQ-p00080-A: PDF generation end-to-end."""

    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_A_generates_pdf(self, tmp_path):
        out = tmp_path / "test-output.pdf"
        result = run_elspais("pdf", "--output", str(out))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists(), "PDF file was not created"
        assert out.stat().st_size > 0, "PDF file is empty"
        with open(out, "rb") as f:
            assert f.read(4) == b"%PDF"

    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_F_generates_overview_pdf(self, tmp_path):
        out = tmp_path / "overview.pdf"
        result = run_elspais("pdf", "--overview", "--output", str(out))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()
        assert out.stat().st_size > 0
        with open(out, "rb") as f:
            assert f.read(4) == b"%PDF"
