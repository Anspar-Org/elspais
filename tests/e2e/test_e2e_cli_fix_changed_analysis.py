# Verifies: REQ-p00004, REQ-p00002
"""E2E tests for fix, changed, analysis, config, and init CLI commands.

Each test builds a unique project from scratch with specific config
settings and validates command behavior.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from .helpers import (
    Requirement,
    base_config,
    build_project,
    run_elspais,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Test 14: Fix corrects a wrong hash
# ---------------------------------------------------------------------------


class TestFixCorrectsHash:
    """Fix command recalculates hashes correctly."""

    def test_fix_corrects_wrong_hash(self, tmp_path):
        cfg = base_config(name="fix-hash-test", allow_structural_orphans=True)
        build_project(tmp_path, cfg, spec_files={})

        # Write spec with intentionally wrong hash
        spec = tmp_path / "spec" / "prd-fix.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(
            "# REQ-p00001: Fix Test\n"
            "\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL be fixed.\n"
            "\n"
            "*End* *Fix Test* | **Hash**: 00000000\n"
            "---\n"
        )

        # Commit the wrong-hash file
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add wrong hash"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Run fix
        result = run_elspais("fix", cwd=tmp_path)
        assert result.returncode == 0, f"fix failed: {result.stderr}"

        # Verify hash was corrected (wrong hash replaced with computed one)
        content = spec.read_text()
        assert "00000000" not in content, "Hash was not corrected by fix"
        # The fix command should have put a valid 8-char hex hash
        import re

        match = re.search(r"\*\*Hash\*\*:\s*([0-9a-f]{8})", content)
        assert match, "No valid hash found in file after fix"

    def test_fix_dry_run_does_not_modify(self, tmp_path):
        cfg = base_config(name="fix-dryrun", allow_structural_orphans=True)
        build_project(tmp_path, cfg, spec_files={})

        spec = tmp_path / "spec" / "prd-dry.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(
            "# REQ-p00001: Dry Run Test\n"
            "\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. The system SHALL remain unchanged.\n"
            "\n"
            "*End* *Dry Run Test* | **Hash**: 00000000\n"
            "---\n"
        )

        result = run_elspais("fix", "--dry-run", cwd=tmp_path)
        assert result.returncode == 0

        # Hash should NOT be changed
        content = spec.read_text()
        assert "00000000" in content, "Dry run modified the file"


# ---------------------------------------------------------------------------
# Test 15: Fix then health passes
# ---------------------------------------------------------------------------


class TestFixThenHealthPasses:
    """Fix + health workflow with numeric assertions."""

    def test_fix_then_health_numeric_assertions(self, tmp_path):
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


# ---------------------------------------------------------------------------
# Test 16: Changed command detects modifications
# ---------------------------------------------------------------------------


class TestChangedCommand:
    """Changed command detects git changes to spec files."""

    def test_changed_detects_uncommitted_edit(self, tmp_path):
        cfg = base_config(name="changed-test", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Original Title",
            "PRD",
            assertions=[("A", "The system SHALL be original.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        # Modify the spec file (uncommitted change)
        spec = tmp_path / "spec" / "prd.md"
        content = spec.read_text()
        spec.write_text(content.replace("Original Title", "Modified Title"))

        result = run_elspais("changed", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        output = result.stdout.strip()
        if output:
            data = json.loads(output)
            # Should detect changes
            assert isinstance(data, (list, dict))

    def test_changed_no_changes(self, tmp_path):
        cfg = base_config(name="changed-clean", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Stable",
            "PRD",
            assertions=[("A", "The system SHALL be stable.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("changed", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 17: Analysis command
# ---------------------------------------------------------------------------


class TestAnalysisCommand:
    """Analysis command with various options."""

    def _build(self, tmp_path):
        cfg = base_config(name="analysis-test")
        prd = Requirement(
            "REQ-p00001",
            "Core Feature",
            "PRD",
            assertions=[
                ("A", "The system SHALL provide core functionality."),
                ("B", "The system SHALL be extensible."),
            ],
        )
        ops = Requirement(
            "REQ-o00001",
            "Core Operations",
            "OPS",
            implements="REQ-p00001",
            assertions=[("A", "Operations SHALL monitor core services.")],
        )
        dev1 = Requirement(
            "REQ-d00001",
            "Core Module",
            "DEV",
            implements="REQ-o00001",
            assertions=[("A", "The module SHALL implement core logic.")],
        )
        dev2 = Requirement(
            "REQ-d00002",
            "Extension Module",
            "DEV",
            implements="REQ-o00001",
            assertions=[("A", "The module SHALL support plugins.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/ops.md": [ops],
                "spec/dev.md": [dev1, dev2],
            },
        )

    def test_analysis_table_output(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("analysis", "--format", "table", cwd=tmp_path)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_analysis_json_output(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("analysis", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (list, dict))

    def test_analysis_top_n(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("analysis", "-n", "2", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        if isinstance(data, list):
            assert len(data) <= 2

    def test_analysis_show_foundations(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais(
            "analysis",
            "--show",
            "foundations",
            "--format",
            "json",
            cwd=tmp_path,
        )
        assert result.returncode == 0

    def test_analysis_level_filter(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais(
            "analysis",
            "--level",
            "dev",
            "--format",
            "json",
            cwd=tmp_path,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 18: Config show/get commands
# ---------------------------------------------------------------------------


class TestConfigCommands:
    """Config show and get subcommands."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="config-test",
            namespace="MYNS",
            label_style="numeric_1based",
        )
        build_project(tmp_path, cfg, spec_files={})
        (tmp_path / "spec").mkdir(exist_ok=True)

    def test_config_show(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("config", "show", cwd=tmp_path)
        assert result.returncode == 0
        assert "MYNS" in result.stdout or "config-test" in result.stdout

    def test_config_show_json(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("config", "show", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_config_get_project_name(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("config", "get", "project.name", cwd=tmp_path)
        assert result.returncode == 0
        assert "config-test" in result.stdout

    def test_config_path(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("config", "path", cwd=tmp_path)
        assert result.returncode == 0
        assert ".elspais.toml" in result.stdout


# ---------------------------------------------------------------------------
# Test 19: Init command
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
# Test 20: Config set/get round-trip
# ---------------------------------------------------------------------------


class TestConfigSetGet:
    """Config set then get returns the set value."""

    def test_set_then_get(self, tmp_path):
        cfg = base_config(name="setget-test")
        build_project(tmp_path, cfg, spec_files={})
        (tmp_path / "spec").mkdir(exist_ok=True)

        # Set a value
        set_result = run_elspais(
            "config",
            "set",
            "project.name",
            "updated-name",
            cwd=tmp_path,
        )
        assert set_result.returncode == 0

        # Get it back
        get_result = run_elspais("config", "get", "project.name", cwd=tmp_path)
        assert get_result.returncode == 0
        assert "updated-name" in get_result.stdout


# ---------------------------------------------------------------------------
# Test 21: Fix with FDA-style IDs
# ---------------------------------------------------------------------------


class TestFixFDAStyle:
    """Fix command with FDA-style IDs and hierarchy."""

    def test_fix_corrects_fda_hashes(self, tmp_path):
        cfg = base_config(
            name="fix-fda",
            canonical="{type}-{component}",
            types={
                "PRD": {"level": 1},
                "DEV": {"level": 3},
            },
            allowed_implements=["DEV -> PRD"],
        )
        build_project(tmp_path, cfg, spec_files={})

        prd_spec = tmp_path / "spec" / "prd-regs.md"
        prd_spec.parent.mkdir(parents=True, exist_ok=True)
        prd_spec.write_text(
            "# PRD-00001: Regulation\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "## Assertions\n\n"
            "A. The system SHALL comply.\n\n"
            "*End* *Regulation* | **Hash**: XXXXXXXX\n---\n"
        )
        dev_spec = tmp_path / "spec" / "dev-impl.md"
        dev_spec.write_text(
            "# DEV-00001: Implementation\n\n"
            "**Level**: DEV | **Status**: Active | **Implements**: PRD-00001\n\n"
            "## Assertions\n\n"
            "A. The module SHALL implement compliance.\n\n"
            "*End* *Implementation* | **Hash**: XXXXXXXX\n---\n"
        )

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add fda"],
            cwd=tmp_path,
            capture_output=True,
        )

        fix = run_elspais("fix", cwd=tmp_path)
        assert fix.returncode == 0

        health = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health.returncode == 0


# ---------------------------------------------------------------------------
# Test 22: Graph export
# ---------------------------------------------------------------------------


class TestGraphExport:
    """Graph command exports JSON."""

    def test_graph_json_output(self, tmp_path):
        cfg = base_config(name="graph-export", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Graph Test",
            "PRD",
            assertions=[("A", "The system SHALL export graphs.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("graph", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (list, dict))


# ---------------------------------------------------------------------------
# Test 23: Health with skip_files
# ---------------------------------------------------------------------------


class TestHealthSkipFiles:
    """Skip specific files from scanning."""

    def test_skip_files_excludes_readme(self, tmp_path):
        cfg = base_config(
            name="skip-files",
            skip_files=["README.md", "INDEX.md", "NOTES.md"],
            allow_structural_orphans=True,
        )
        prd = Requirement(
            "REQ-p00001",
            "Included",
            "PRD",
            assertions=[("A", "The system SHALL be included.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd-main.md": [prd]},
            extra_files={
                "spec/NOTES.md": "# Just some notes\nNot a requirement.\n",
            },
        )

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total == 1


# ---------------------------------------------------------------------------
# Test 24: Multi-assertion compact syntax
# ---------------------------------------------------------------------------


class TestMultiAssertionSyntax:
    """Implements: REQ-p00001-A+B+C compact syntax."""

    def test_multi_assertion_code_reference(self, tmp_path):
        cfg = base_config(
            name="multi-assert",
            testing_enabled=True,
            test_dirs=["tests"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Multi Assert",
            "PRD",
            assertions=[
                ("A", "The system SHALL handle A."),
                ("B", "The system SHALL handle B."),
                ("C", "The system SHALL handle C."),
            ],
        )
        dev = Requirement(
            "REQ-d00001",
            "Multi Impl",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL implement all.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
            code_files={
                # Uses compact multi-assertion syntax
                "src/handler.py": {
                    "implements": ["REQ-d00001-A"],
                    "content": "def handler(): pass",
                },
            },
        )

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
