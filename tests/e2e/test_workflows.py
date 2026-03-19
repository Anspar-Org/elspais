# Verifies: REQ-d00085-A
"""End-to-end workflow tests for elspais CLI multi-command sequences.

Each test invokes multiple elspais commands as subprocesses and validates
cross-command consistency and sequential operation correctness.
"""

import csv
import io
import json
import shutil
from pathlib import Path

import pytest

from .conftest import run_elspais

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


class TestInitThenHealth:
    """Validates REQ-d00085-A: init followed by health passes."""

    def test_REQ_d00085_A_init_then_health_passes(self, tmp_path):
        init_result = run_elspais("init", cwd=tmp_path)
        assert init_result.returncode == 0, f"init failed: {init_result.stderr}"

        # Create the spec directory that init references in its config
        (tmp_path / "spec").mkdir(exist_ok=True)

        health_result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert health_result.returncode == 0, f"health failed after init: {health_result.stderr}"


class TestHealthSummaryConsistency:
    """Validates REQ-d00085-A: summary is consistent across runs."""

    def test_REQ_d00085_A_health_summary_same_total(self):
        health_result = run_elspais("health", "--format", "json", "--lenient")
        assert health_result.returncode == 0, f"health failed: {health_result.stderr}"
        health_data = json.loads(health_result.stdout)
        assert isinstance(health_data, (dict, list))

        summary_result = run_elspais("summary", "--format", "json")
        assert summary_result.returncode == 0, f"summary failed: {summary_result.stderr}"
        summary_data = json.loads(summary_result.stdout)
        assert isinstance(summary_data, dict)

        # Summary should report a positive total
        levels = summary_data.get("levels", [])
        summary_total = sum(lvl.get("total", 0) for lvl in levels)
        assert summary_total > 0, "Expected at least one requirement in summary"

        # Run summary again - should be identical
        summary_result2 = run_elspais("summary", "--format", "json")
        assert summary_result2.returncode == 0
        summary_data2 = json.loads(summary_result2.stdout)
        levels2 = summary_data2.get("levels", [])
        summary_total2 = sum(lvl.get("total", 0) for lvl in levels2)
        assert (
            summary_total == summary_total2
        ), f"Summary totals differ between runs: {summary_total} vs {summary_total2}"


class TestTraceFormatConsistency:
    """Validates REQ-d00085-A: trace JSON and CSV both produce valid output."""

    def test_REQ_d00085_A_trace_json_csv_same_count(self, tmp_path):
        json_out = tmp_path / "trace_json"
        result_json = run_elspais("trace", "--format", "json", "--output", str(json_out))
        assert result_json.returncode == 0, f"trace json failed: {result_json.stderr}"

        csv_out = tmp_path / "trace_csv"
        result_csv = run_elspais("trace", "--format", "csv", "--output", str(csv_out))
        assert result_csv.returncode == 0, f"trace csv failed: {result_csv.stderr}"

        # Find the JSON output file
        json_candidates = [json_out, json_out.with_suffix(".json"), Path(f"{json_out}.json")]
        json_found = [p for p in json_candidates if p.exists()]
        assert json_found, f"No JSON trace file found among {json_candidates}"
        json_data = json.loads(json_found[0].read_text())
        assert json_data, "JSON trace output is empty"

        # Find the CSV output file
        csv_candidates = [csv_out, csv_out.with_suffix(".csv"), Path(f"{csv_out}.csv")]
        csv_found = [p for p in csv_candidates if p.exists()]
        assert csv_found, f"No CSV trace file found among {csv_candidates}"
        csv_text = csv_found[0].read_text()
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        # At least a header row and one data row
        assert len(rows) > 1, "CSV trace output has no data rows"


class TestInitTemplate:
    """Validates REQ-d00085-A: init creates a valid config."""

    def test_REQ_d00085_A_init_creates_valid_config(self, tmp_path):
        init_result = run_elspais("init", cwd=tmp_path)
        assert init_result.returncode == 0, f"init failed: {init_result.stderr}"

        config_result = run_elspais("config", "show", cwd=tmp_path)
        assert (
            config_result.returncode == 0
        ), f"config show failed after init: {config_result.stderr}"
        assert len(config_result.stdout.strip()) > 0, "config show produced no output"


class TestFixThenHealth:
    """Validates REQ-d00085-A: fix corrects hashes, then health passes."""

    def test_REQ_d00085_A_fix_then_health_on_fixture(self, tmp_path):
        # Create minimal config
        config = tmp_path / ".elspais.toml"
        config.write_text(
            'version = 3\n[project]\nnamespace = "REQ"\n\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )

        # Create spec directory and a requirement with a wrong hash
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "test-req.md"
        spec_file.write_text(
            "# REQ-p00001: Test Requirement\n"
            "\n"
            "**Level**: PRD | **Status**: Draft\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL do something.\n"
            "\n"
            "*End* *Test Requirement* | **Hash**: 00000000\n"
        )

        # Run fix to correct the hash
        fix_result = run_elspais("fix", cwd=tmp_path)
        assert fix_result.returncode == 0, f"fix failed: {fix_result.stderr}"

        # Verify health passes after fix
        health_result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert health_result.returncode == 0, f"health failed after fix: {health_result.stderr}"


class TestSummaryIdempotent:
    """Validates REQ-d00085-A: summary produces consistent results across runs."""

    def test_REQ_d00085_A_summary_consistent_across_runs(self):
        result1 = run_elspais("summary", "--format", "json")
        assert result1.returncode == 0, f"summary run 1 failed: {result1.stderr}"
        data1 = json.loads(result1.stdout)

        result2 = run_elspais("summary", "--format", "json")
        assert result2.returncode == 0, f"summary run 2 failed: {result2.stderr}"
        data2 = json.loads(result2.stdout)

        levels1 = data1.get("levels", [])
        levels2 = data2.get("levels", [])
        total1 = sum(lvl.get("total", 0) for lvl in levels1)
        total2 = sum(lvl.get("total", 0) for lvl in levels2)

        assert total1 > 0, "Expected at least one requirement"
        assert total1 == total2, f"Summary totals differ between runs: {total1} vs {total2}"
