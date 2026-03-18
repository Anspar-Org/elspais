# Verifies: REQ-p00013-C
"""Self-validation end-to-end tests for elspais CLI.

Runs elspais against its own repository to verify the tool
passes its own checks — the ultimate dogfooding test.
"""

import json
import shutil
from pathlib import Path

import pytest

from .conftest import REPO_ROOT, run_elspais

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


class TestHealthSelfValidation:
    """Validates REQ-p00013-C: health command passes on own repo."""

    def test_REQ_p00013_C_health_passes(self):
        result = run_elspais("health", "--lenient")
        assert result.returncode == 0, f"health --lenient failed: {result.stderr}"

    def test_REQ_p00013_C_health_json_zero_errors(self):
        result = run_elspais("health", "--format", "json", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert (
            data["summary"]["failed"] == 0
        ), f"Expected 0 failures, got {data['summary']['failed']}"

    def test_REQ_p00013_C_health_is_healthy(self):
        result = run_elspais("health", "--format", "json", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["healthy"] is True, f"Expected healthy=true, got {data!r}"


class TestDoctorSelfValidation:
    """Validates REQ-p00013-C: doctor command passes on own repo."""

    def test_REQ_p00013_C_doctor_passes(self):
        result = run_elspais("doctor")
        assert result.returncode == 0, f"doctor failed: {result.stderr}"


class TestSummarySelfValidation:
    """Validates REQ-p00013-C: summary reflects real repo content."""

    @pytest.fixture()
    def summary_data(self):
        result = run_elspais("summary", "--format", "json")
        assert result.returncode == 0
        return json.loads(result.stdout)

    def test_REQ_p00013_C_summary_has_all_levels(self, summary_data):
        level_names = {entry["level"] for entry in summary_data["levels"]}
        for expected in ("PRD", "OPS", "DEV"):
            assert (
                expected in level_names
            ), f"Missing level {expected} in summary; found {level_names}"

    def test_REQ_p00013_C_summary_nonzero_counts(self, summary_data):
        for entry in summary_data["levels"]:
            assert entry["total"] > 0, f"Level {entry['level']} has total=0"

    def test_REQ_p00013_C_summary_has_assertions(self, summary_data):
        for entry in summary_data["levels"]:
            assert entry["total_assertions"] > 0, f"Level {entry['level']} has total_assertions=0"


class TestTraceSelfValidation:
    """Validates REQ-p00013-C: trace output contains requirements and tests."""

    @pytest.fixture()
    def trace_data(self, tmp_path):
        out = tmp_path / "trace"
        result = run_elspais("trace", "--format", "json", "--output", str(out))
        assert result.returncode == 0, f"trace failed: {result.stderr}"
        candidates = [out, out.with_suffix(".json"), Path(f"{out}.json")]
        found = [p for p in candidates if p.exists()]
        assert found, f"No trace output file found among {candidates}"
        return json.loads(found[0].read_text())

    def test_REQ_p00013_C_trace_json_has_requirements(self, trace_data):
        text = json.dumps(trace_data).lower()
        assert "req" in text, "Trace JSON contains no requirement references"

    def test_REQ_p00013_C_trace_json_has_tests(self, trace_data):
        text = json.dumps(trace_data).lower()
        assert "test" in text, "Trace JSON contains no test references"


class TestGraphSelfValidation:
    """Validates REQ-p00013-C: graph command produces meaningful output."""

    def test_REQ_p00013_C_graph_has_node_kinds(self):
        result = run_elspais("graph")
        assert result.returncode == 0, f"graph failed: {result.stderr}"
        output = result.stdout.lower()
        assert len(output.strip()) > 0, "graph produced empty output"
        assert "req" in output, "graph output contains no requirement references"


class TestSubdirDetection:
    """Validates REQ-p00013-C: git root auto-detection from subdirectory."""

    def test_REQ_p00013_C_works_from_subdirectory(self):
        subdir = REPO_ROOT / "tests"
        result = run_elspais("health", "--lenient", cwd=subdir)
        assert result.returncode == 0, f"health --lenient failed from subdirectory: {result.stderr}"
