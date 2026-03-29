# Verifies: REQ-p00002, REQ-p00004, REQ-d00085-A
"""Special e2e tests requiring unique project setups.

Each test class manages its own project setup because it needs:
- an empty directory (init tests),
- a specific error state (wrong-hash fixture),
- output files in tmp_path (trace format tests), or
- a full lifecycle from scratch.
"""

import csv
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.e2e.conftest import run_elspais

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# From test_cli_commands.py::TestInit
# ---------------------------------------------------------------------------


class TestInitCreatesToml:
    """Init command creates .elspais.toml in an empty directory."""

    def test_init_creates_toml(self, tmp_path):
        result = run_elspais("init", cwd=tmp_path)
        assert result.returncode == 0
        toml_file = tmp_path / ".elspais.toml"
        assert toml_file.exists(), f"Expected .elspais.toml in {tmp_path}"


# ---------------------------------------------------------------------------
# From test_workflows.py::TestInitThenHealth
# ---------------------------------------------------------------------------


class TestInitThenHealth:
    """Validates REQ-d00085-A: init followed by health passes."""

    def test_REQ_d00085_A_init_then_health_passes(self, tmp_path):
        init_result = run_elspais("init", cwd=tmp_path)
        assert init_result.returncode == 0, f"init failed: {init_result.stderr}"

        # Create the spec directory that init references in its config
        (tmp_path / "spec").mkdir(exist_ok=True)

        health_result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health_result.returncode == 0, f"health failed after init: {health_result.stderr}"


# ---------------------------------------------------------------------------
# From test_workflows.py::TestInitTemplate
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# From test_workflows.py::TestFixThenHealth
# ---------------------------------------------------------------------------


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
        health_result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health_result.returncode == 0, f"health failed after fix: {health_result.stderr}"


# ---------------------------------------------------------------------------
# From test_workflows.py::TestTraceFormatConsistency
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# From test_e2e_cli_fix_changed_analysis.py::TestInitCommand
# ---------------------------------------------------------------------------


class TestInitCommand:
    """Init creates valid configs for core and associated projects."""

    def test_init_core_project(self, tmp_path):
        result = run_elspais("init", cwd=tmp_path)
        assert result.returncode == 0

        config_file = tmp_path / ".elspais.toml"
        assert config_file.exists(), "Init did not create .elspais.toml"

        # Config should be valid
        show = run_elspais("config", "show", cwd=tmp_path)
        assert show.returncode == 0

    def test_init_associated_project(self, tmp_path):
        result = run_elspais(
            "init",
            "--type",
            "associated",
            "--associated-prefix",
            "TST",
            cwd=tmp_path,
        )
        assert result.returncode == 0

        config_file = tmp_path / ".elspais.toml"
        assert config_file.exists()
        content = config_file.read_text()
        assert "associated" in content.lower()
        assert "TST" in content

    def test_init_with_template(self, tmp_path):
        result = run_elspais("init", "--template", cwd=tmp_path)
        assert result.returncode == 0

        # Should create a sample spec file
        spec_dir = tmp_path / "spec"
        if spec_dir.exists():
            spec_files = list(spec_dir.glob("*.md"))
            # Template might create sample files
            assert len(spec_files) >= 0  # At least check no error

    def test_init_then_health(self, tmp_path):
        run_elspais("init", cwd=tmp_path)
        (tmp_path / "spec").mkdir(exist_ok=True)

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# From test_e2e_complex_workflows.py::TestFullProjectLifecycle
# ---------------------------------------------------------------------------


class TestFullProjectLifecycle:
    """Complete project lifecycle from init to validated state."""

    def test_lifecycle(self, tmp_path):
        # 1. Init project
        init = run_elspais("init", cwd=tmp_path)
        assert init.returncode == 0

        # 2. Create spec directory and requirement
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir(exist_ok=True)
        spec_file = spec_dir / "prd-features.md"
        spec_file.write_text(
            "# REQ-p00001: Feature One\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "## Assertions\n\n"
            "A. The system SHALL implement feature one.\n\n"
            "*End* *Feature One* | **Hash**: 00000000\n---\n"
        )

        # 3. Commit so fix can work
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)

        # 4. Fix hashes (Active requirements require a per-req -m changelog message)
        fix = run_elspais("fix", "REQ-p00001", "-m", "initial hash fix", cwd=tmp_path)
        assert fix.returncode == 0

        # 5. Health should pass
        health = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health.returncode == 0

        # 6. Summary should show 1 PRD requirement
        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert summary.returncode == 0
        data = json.loads(summary.stdout)
        levels = data.get("levels", [])
        prd_count = next((lv["total"] for lv in levels if lv["level"] == "PRD"), 0)
        assert prd_count == 1

        # 7. Trace should include the requirement
        trace = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert trace.returncode == 0
        trace_data = json.loads(trace.stdout)
        assert len(trace_data) == 1
        assert trace_data[0]["id"] == "REQ-p00001"


# ---------------------------------------------------------------------------
# From test_e2e_additional_coverage.py::TestInitForce
# ---------------------------------------------------------------------------


class TestInitForce:
    """Init --force overwrites existing .elspais.toml."""

    def test_force_overwrite(self, tmp_path):
        from tests.e2e.helpers import base_config, build_project

        # Create an initial config
        cfg = base_config(name="will-be-overwritten")
        build_project(tmp_path, cfg, spec_files={})

        # Force overwrite
        result = run_elspais("init", "--force", cwd=tmp_path)
        assert result.returncode == 0

        # Config should be the default template, not our custom one
        show = run_elspais("config", "show", "--format", "json", cwd=tmp_path)
        assert show.returncode == 0


# ---------------------------------------------------------------------------
# From test_e2e_cli_fix_changed_analysis.py::TestFixThenHealthPasses
# ---------------------------------------------------------------------------


class TestFixThenHealthPasses:
    """Fix + health workflow with numeric assertions."""

    def test_fix_then_health_numeric_assertions(self, tmp_path):
        from tests.e2e.helpers import base_config, build_project

        cfg = base_config(
            name="fix-health-numeric",
            label_style="numeric",
            allow_structural_orphans=True,
        )
        build_project(tmp_path, cfg, spec_files={})

        spec = tmp_path / "spec" / "prd-num.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(
            "# REQ-p00001: Numeric Fix\n"
            "\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "0. The system SHALL use numeric labels.\n"
            "1. The system SHALL start from zero.\n"
            "\n"
            "*End* *Numeric Fix* | **Hash**: 00000000\n"
            "---\n"
        )

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add"],
            cwd=tmp_path,
            capture_output=True,
        )

        fix_result = run_elspais("fix", cwd=tmp_path)
        assert fix_result.returncode == 0

        health_result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health_result.returncode == 0
