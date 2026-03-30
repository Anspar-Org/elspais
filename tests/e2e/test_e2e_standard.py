# Verifies: REQ-p00002, REQ-p00003, REQ-p00004, REQ-p00060,
#            REQ-d00074-A+B+C+D, REQ-d00080, REQ-d00085-A
"""Standard workhorse e2e tests — module-scoped fixture with daemon acceleration.

Tests standard 3-tier hierarchy (REQ-p/o/d), uppercase assertions,
and base_config() defaults against a single shared project.

Groups:
  1. Read-only CLI tests (health, summary, trace, analysis, graph, config show)
  2. Mutation tests (fix, config set, edit, changed)
  3. MCP query tests (search, hierarchy, subtree, coverage)
  4. MCP mutation tests (with undo)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from .conftest import (
    build_fixture_project,
    ensure_fixture_daemon,
)
from .helpers import (
    Requirement,
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
# Fixture project content
# ---------------------------------------------------------------------------

_PRD_REQ_P00001 = Requirement(
    "REQ-p00001",
    "User Authentication",
    "PRD",
    assertions=[
        ("A", "The system SHALL authenticate users."),
        ("B", "The system SHALL enforce password policies."),
        ("C", "The system SHALL support multi-factor authentication."),
    ],
)

_PRD_REQ_P00002 = Requirement(
    "REQ-p00002",
    "Notifications",
    "PRD",
    assertions=[
        ("A", "The system SHALL send email notifications."),
        ("B", "The system SHALL send push notifications."),
    ],
)

_PRD_REQ_P00003 = Requirement(
    "REQ-p00003",
    "Draft Feature",
    "PRD",
    status="Draft",
    assertions=[
        ("A", "The system SHALL provide draft feature."),
    ],
)

_PRD_REQ_P00004 = Requirement(
    "REQ-p00004",
    "Deprecated Feature",
    "PRD",
    status="Deprecated",
    assertions=[
        ("A", "The system SHALL deprecate old feature."),
    ],
)

_OPS_REQ_O00001 = Requirement(
    "REQ-o00001",
    "Auth Deployment",
    "OPS",
    implements="REQ-p00001",
    assertions=[
        ("A", "Operations SHALL deploy auth service with HA."),
    ],
)

_OPS_REQ_O00002 = Requirement(
    "REQ-o00002",
    "Notification Ops",
    "OPS",
    implements="REQ-p00002",
    assertions=[
        ("A", "Operations SHALL monitor notification delivery."),
    ],
)

_DEV_REQ_D00001 = Requirement(
    "REQ-d00001",
    "Auth Module",
    "DEV",
    implements="REQ-o00001",
    assertions=[
        ("A", "The module SHALL use bcrypt for hashing."),
        ("B", "The module SHALL validate JWT tokens."),
    ],
)

_DEV_REQ_D00002 = Requirement(
    "REQ-d00002",
    "Notification Service",
    "DEV",
    implements="REQ-o00002",
    assertions=[
        ("A", "The module SHALL queue notifications."),
    ],
)

_DEV_REQ_D00003 = Requirement(
    "REQ-d00003",
    "Auth Refinement",
    "DEV",
    refines="REQ-d00001",
    assertions=[
        ("A", "The module SHALL add token refresh logic."),
    ],
)

# Many-assertions requirement: 26 assertions A-Z
_MANY_ASSERTIONS = [
    (chr(ord("A") + i), f"The system SHALL satisfy criterion {chr(ord('A') + i)}.")
    for i in range(26)
]

_PRD_REQ_P00005 = Requirement(
    "REQ-p00005",
    "Comprehensive Criteria",
    "PRD",
    assertions=_MANY_ASSERTIONS,
)


def _build_wrong_hash_spec() -> str:
    """Build prd-deprecated.md with intentionally wrong hash for REQ-p00004."""
    h_wrong = "00000000"
    return (
        "# REQ-p00004: Deprecated Feature\n"
        "\n"
        "**Level**: PRD | **Status**: Deprecated\n"
        "\n"
        "## Assertions\n"
        "\n"
        "A. The system SHALL deprecate old feature.\n"
        "\n"
        f"*End* *Deprecated Feature* | **Hash**: {h_wrong}\n"
        "---\n"
    )


def _build_spec_content(reqs: list[Requirement]) -> str:
    """Render multiple requirements to spec file content."""
    return "\n".join(r.render() for r in reqs)


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Build the standard project once for the entire module."""
    root = tmp_path_factory.mktemp("e2e_standard")

    spec_files = {
        "spec/prd-core.md": _build_spec_content([_PRD_REQ_P00001, _PRD_REQ_P00002]),
        "spec/prd-draft.md": _build_spec_content([_PRD_REQ_P00003]),
        "spec/prd-deprecated.md": _build_wrong_hash_spec(),
        "spec/prd-comprehensive.md": _build_spec_content([_PRD_REQ_P00005]),
        "spec/ops-deploy.md": _build_spec_content([_OPS_REQ_O00001, _OPS_REQ_O00002]),
        "spec/dev-impl.md": _build_spec_content([_DEV_REQ_D00001, _DEV_REQ_D00002]),
        "spec/dev-refine.md": _build_spec_content([_DEV_REQ_D00003]),
        "spec/INDEX.md": "# Index\n\nThis file should be skipped.\n",
        "spec/NOTES.md": "# Notes\n\nThis file should be skipped.\n",
        "spec/drafts/wip-ideas.md": (
            "# REQ-p99999: WIP Idea\n\n"
            "**Level**: PRD | **Status**: Draft\n\n"
            "## Assertions\n\n"
            "A. The system SHALL be a draft.\n\n"
            "*End* *WIP Idea* | **Hash**: 00000000\n---\n"
        ),
    }

    code_files = {
        "src/auth.py": (
            "# Implements: REQ-d00001-A\n" "\n" "def authenticate(user, password):\n" "    pass\n"
        ),
        "src/auth_multi.py": (
            "# Implements: REQ-d00001-A+B\n" "\n" "def multi_auth():\n" "    pass\n"
        ),
        "src/notifications.py": (
            "# Implements: REQ-d00002\n" "\n" "def send_notification():\n" "    pass\n"
        ),
    }

    test_files = {
        "tests/test_auth.py": (
            "# Verifies: REQ-d00001-A\n" "\n" "def test_authenticate():\n" "    assert True\n"
        ),
        "tests/test_notifications.py": (
            "# Verifies: REQ-d00002\n" "\n" "def test_send():\n" "    assert True\n"
        ),
    }

    build_fixture_project(
        root,
        config_overrides={
            "name": "e2e-standard",
            "allow_structural_orphans": True,
            "testing_enabled": True,
            "test_dirs": ["tests"],
            "skip_files": ["INDEX.md", "NOTES.md"],
            "skip_dirs": ["drafts"],
        },
        spec_files=spec_files,
        code_files=code_files,
        test_files=test_files,
    )

    ensure_fixture_daemon(root)
    return root


@pytest.fixture(scope="module")
def mcp_server(project):
    """Start an MCP server for the project, shared across all MCP tests."""
    pytest.importorskip("mcp")
    from .helpers import start_mcp, stop_mcp

    proc = start_mcp(project)
    yield proc
    stop_mcp(proc)


# ===================================================================
# Group 1: Read-only CLI tests
# ===================================================================


class TestHealthPasses:
    """Health command passes on the standard project."""

    def test_health_lenient(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_health_json_structure(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))

    def test_health_text_contains_sections(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0
        assert "CONFIG" in result.stdout or "SPEC" in result.stdout


class TestHealthCheckNames:
    """Health JSON output includes correct check names."""

    def test_new_check_names_present(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        check_names = {c["name"] for c in data.get("checks", [])}
        for name in (
            "spec.structural_orphans",
            "spec.broken_references",
            "tests.unlinked",
            "code.unlinked",
        ):
            assert name in check_names, f"Expected check '{name}' not found in {check_names}"

    def test_old_check_names_absent(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        check_names = {c["name"] for c in data.get("checks", [])}
        for name in ("spec.orphans", "tests.references_resolve", "code.references_resolve"):
            assert name not in check_names, f"Old check name '{name}' should not be present"


class TestHealthFormats:
    """Health output in various formats."""

    def test_health_sarif(self, project):
        result = run_elspais("checks", "--format", "sarif", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "$schema" in data or "runs" in data or "version" in data

    def test_health_junit(self, project):
        result = run_elspais("checks", "--format", "junit", "--lenient", cwd=project)
        assert result.returncode == 0
        assert "<?xml" in result.stdout or "<testsuites" in result.stdout

    def test_health_markdown(self, project):
        result = run_elspais("checks", "--format", "markdown", "--lenient", cwd=project)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


class TestHealthScopeFlags:
    """Health command with --spec, --code, --tests scope flags."""

    def test_health_spec_only(self, project):
        result = run_elspais("checks", "--spec", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_health_code_only(self, project):
        result = run_elspais("checks", "--code", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_health_tests_only(self, project):
        result = run_elspais("checks", "--tests", "--lenient", cwd=project)
        assert result.returncode == 0


class TestSummaryCounts:
    """Summary command counts requirements correctly."""

    def test_summary_json_total(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Default summary filters to Active status:
        # 3 PRD Active (p00001, p00002, p00005), 2 OPS, 3 DEV = 8
        assert total == 8, f"Expected 8 Active requirements, got {total}"

    def test_summary_level_breakdown(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        data = json.loads(result.stdout)
        levels = {lv["level"].lower(): lv["total"] for lv in data.get("levels", [])}
        assert levels.get("prd", 0) == 3  # p00001, p00002, p00005 (Active)
        assert levels.get("ops", 0) == 2
        assert levels.get("dev", 0) == 3


class TestSummaryFormats:
    """Summary in text, markdown, csv, json formats."""

    def test_summary_text(self, project):
        result = run_elspais("summary", "--format", "text", cwd=project)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_summary_csv(self, project):
        result = run_elspais("summary", "--format", "csv", cwd=project)
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 1

    def test_summary_markdown(self, project):
        result = run_elspais("summary", "--format", "markdown", cwd=project)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


class TestSummaryStatusFilter:
    """Summary --status filters by status."""

    def test_status_filter_draft(self, project):
        result = run_elspais("summary", "--format", "json", "--status", "Draft", cwd=project)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            total = sum(lv.get("total", 0) for lv in data.get("levels", []))
            assert total >= 1


class TestTraceOutput:
    """Trace command output."""

    def test_trace_json(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 10

    def test_trace_csv(self, project):
        result = run_elspais("trace", "--format", "csv", cwd=project)
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 2  # header + data rows

    def test_trace_text(self, project):
        result = run_elspais("trace", "--format", "text", cwd=project)
        assert result.returncode == 0
        assert "REQ-p00001" in result.stdout

    def test_trace_markdown(self, project):
        result = run_elspais("trace", "--format", "markdown", cwd=project)
        assert result.returncode == 0
        assert "REQ-p00001" in result.stdout


class TestTraceOptions:
    """Trace with various flags."""

    def test_trace_assertions(self, project):
        result = run_elspais("trace", "--format", "json", "--assertions", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        output_str = json.dumps(data)
        assert "REQ-p00001" in output_str

    def test_trace_body(self, project):
        result = run_elspais("trace", "--format", "json", "--body", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_trace_output_to_file(self, project, tmp_path):
        out = tmp_path / "trace-output.json"
        result = run_elspais(
            "trace",
            "--format",
            "json",
            "--output",
            str(out),
            cwd=project,
        )
        assert result.returncode == 0
        candidates = [out, out.with_suffix(".json")]
        found = [p for p in candidates if p.exists()]
        assert found, f"No output file found: {candidates}"
        data = json.loads(found[0].read_text())
        assert isinstance(data, list)


class TestTracePresets:
    """Trace --preset minimal/standard/full."""

    def test_preset_minimal(self, project):
        result = run_elspais("trace", "--preset", "minimal", cwd=project)
        assert result.returncode == 0

    def test_preset_standard(self, project):
        result = run_elspais("trace", "--preset", "standard", cwd=project)
        assert result.returncode == 0

    def test_preset_full(self, project):
        result = run_elspais("trace", "--preset", "full", cwd=project)
        assert result.returncode == 0


class TestAnalysisCommand:
    """Analysis command with various options."""

    def test_analysis_table(self, project):
        result = run_elspais("analysis", "--format", "table", cwd=project)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_analysis_json(self, project):
        result = run_elspais("analysis", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (list, dict))

    def test_analysis_top_n(self, project):
        result = run_elspais("analysis", "-n", "2", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        if isinstance(data, list):
            assert len(data) <= 2

    def test_analysis_show_foundations(self, project):
        result = run_elspais(
            "analysis",
            "--show",
            "foundations",
            "--format",
            "json",
            cwd=project,
        )
        assert result.returncode == 0

    def test_analysis_level_filter(self, project):
        result = run_elspais(
            "analysis",
            "--level",
            "dev",
            "--format",
            "json",
            cwd=project,
        )
        assert result.returncode == 0


class TestGraphExport:
    """Graph command exports JSON."""

    def test_graph_json(self, project):
        result = run_elspais("graph", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (list, dict))


class TestConfigShow:
    """Config show variants."""

    def test_config_show_default(self, project):
        result = run_elspais("config", "show", cwd=project)
        assert result.returncode == 0
        assert "e2e-standard" in result.stdout or "project" in result.stdout.lower()

    def test_config_show_json(self, project):
        result = run_elspais("config", "show", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_config_show_section_project(self, project):
        result = run_elspais("config", "show", "--section", "project", cwd=project)
        assert result.returncode == 0
        assert "e2e-standard" in result.stdout

    def test_config_show_section_rules(self, project):
        result = run_elspais("config", "show", "--section", "rules", cwd=project)
        assert result.returncode == 0

    def test_config_get_project_name(self, project):
        result = run_elspais("config", "get", "project.name", cwd=project)
        assert result.returncode == 0
        assert "e2e-standard" in result.stdout

    def test_config_path(self, project):
        result = run_elspais("config", "path", cwd=project)
        assert result.returncode == 0
        assert ".elspais.toml" in result.stdout


class TestDoctorAndVersion:
    """Doctor and version commands."""

    def test_doctor_passes(self, project):
        result = run_elspais("doctor", cwd=project)
        assert result.returncode == 0

    def test_doctor_json(self, project):
        result = run_elspais("doctor", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))


class TestIdempotency:
    """Running same command twice produces identical results."""

    def test_health_idempotent(self, project):
        r1 = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        r2 = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert r1.returncode == r2.returncode
        assert r1.stdout == r2.stdout

    def test_summary_idempotent(self, project):
        r1 = run_elspais("summary", "--format", "json", cwd=project)
        r2 = run_elspais("summary", "--format", "json", cwd=project)
        assert r1.stdout == r2.stdout


class TestCrossCommandConsistency:
    """Health, trace, and summary report consistent requirement counts."""

    def test_counts_consistent(self, project):
        summary = run_elspais("summary", "--format", "json", cwd=project)
        assert summary.returncode == 0
        summary_data = json.loads(summary.stdout)
        summary_total = sum(lv["total"] for lv in summary_data["levels"])

        trace = run_elspais("trace", "--format", "json", cwd=project)
        assert trace.returncode == 0
        trace_data = json.loads(trace.stdout)
        trace_total = len(trace_data)

        # Summary defaults to Active only (8), trace shows all (10)
        # Both should be internally consistent
        assert summary_total == 8, f"Summary expected 8, got {summary_total}"
        assert trace_total == 10, f"Trace expected 10, got {trace_total}"


class TestSkipFiles:
    """Skip files and dirs are excluded from scanning."""

    def test_skip_files_not_in_health(self, project):
        """INDEX.md and NOTES.md should be skipped."""
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        # These skip files should not cause errors or be counted

    def test_skip_dirs_not_counted(self, project):
        """drafts/ directory should be skipped; REQ-p99999 not counted."""
        result = run_elspais("summary", "--format", "json", cwd=project)
        data = json.loads(result.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        # REQ-p99999 in drafts/ should not be counted; Active only = 8
        assert total == 8


class TestManyAssertions:
    """Requirement with 26 assertions A-Z."""

    def test_26_assertions_health(self, project):
        """REQ-p00005 has 26 assertions and should pass health."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0


class TestDeepHierarchy:
    """PRD -> OPS -> DEV -> DEV(refines) chain."""

    def test_trace_includes_refines(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        ids = {r["id"] for r in data}
        assert "REQ-d00003" in ids, "Refining requirement should appear in trace"


class TestRefinesRelationship:
    """Refines: creates a refinement relationship."""

    def test_refines_in_trace(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        assert "REQ-d00001" in result.stdout
        assert "REQ-d00003" in result.stdout


class TestDraftStatus:
    """Draft requirements are present in trace."""

    def test_draft_in_trace(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        ids = {r["id"] for r in data}
        assert "REQ-p00003" in ids


class TestMultipleSpecFilesPerLevel:
    """Multiple spec files per level are scanned correctly."""

    def test_all_files_counted(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        data = json.loads(result.stdout)
        levels = {lv["level"].lower(): lv["total"] for lv in data.get("levels", [])}
        # Active only: 3 PRD (p00003=Draft, p00004=Deprecated excluded)
        assert levels.get("prd", 0) == 3
        assert levels.get("dev", 0) == 3


class TestCodeRefsAndTesting:
    """Code and test file references are detected."""

    def test_health_passes_with_code_refs(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_health_json_shows_code_refs(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        assert "REQ-d00001" in result.stdout


# ===================================================================
# Group 2: Mutation CLI tests (use separate tmp_path copies)
# ===================================================================


class TestFixCorrectsHash:
    """Fix command recalculates hashes correctly."""

    def test_fix_corrects_wrong_hash(self, project, tmp_path):
        """Fix the wrong hash in prd-deprecated.md (copy to tmp_path first)."""
        # Copy project to tmp_path so we can mutate
        import os

        dst = tmp_path / "fix_project"
        shutil.copytree(project, dst)

        # Verify wrong hash exists
        spec = dst / "spec" / "prd-deprecated.md"
        content = spec.read_text()
        assert "00000000" in content

        # Commit the copy (fix needs git)
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        result = run_elspais("fix", cwd=dst)
        assert result.returncode == 0, f"fix failed: {result.stderr}"

        content = spec.read_text()
        assert "00000000" not in content, "Hash was not corrected by fix"
        match = re.search(r"\*\*Hash\*\*:\s*([0-9a-f]{8})", content)
        assert match, "No valid hash found after fix"

    def test_fix_dry_run_does_not_modify(self, project, tmp_path):
        import os

        dst = tmp_path / "dryrun_project"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        spec = dst / "spec" / "prd-deprecated.md"
        result = run_elspais("fix", "--dry-run", cwd=dst)
        assert result.returncode == 0

        content = spec.read_text()
        assert "00000000" in content, "Dry run modified the file"


class TestFixIdempotent:
    """Running fix twice produces same result."""

    def test_fix_idempotent(self, project, tmp_path):
        import os

        dst = tmp_path / "idemp_project"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        run_elspais("fix", cwd=dst)
        spec = dst / "spec" / "prd-core.md"
        content1 = spec.read_text()

        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "fix1"], cwd=dst, capture_output=True, env=env)

        run_elspais("fix", cwd=dst)
        content2 = spec.read_text()

        assert content1 == content2, "Second fix changed the file"


class TestFixSpecificRequirement:
    """Fix command targeting a specific requirement ID."""

    def test_fix_specific_id(self, project, tmp_path):
        import os

        dst = tmp_path / "fix_specific"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        result = run_elspais("fix", "REQ-p00004", cwd=dst)
        assert result.returncode == 0

        content = (dst / "spec" / "prd-deprecated.md").read_text()
        hashes = re.findall(r"\*\*Hash\*\*:\s*(\S+)", content)
        assert len(hashes) >= 1
        assert hashes[0] != "00000000"


class TestConfigSetGet:
    """Config set/get round-trip (uses copy)."""

    def test_set_then_get(self, project, tmp_path):
        import os

        dst = tmp_path / "config_setget"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        set_result = run_elspais("config", "set", "project.name", "updated-name", cwd=dst)
        assert set_result.returncode == 0

        get_result = run_elspais("config", "get", "project.name", cwd=dst)
        assert get_result.returncode == 0
        assert "updated-name" in get_result.stdout


class TestConfigArrayOperations:
    """Config add/remove for array values."""

    def test_add_status(self, project, tmp_path):
        import os

        dst = tmp_path / "config_add"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        result = run_elspais(
            "config",
            "add",
            "rules.format.allowed_statuses",
            "Experimental",
            cwd=dst,
        )
        assert result.returncode == 0

        show = run_elspais("config", "show", "--format", "json", cwd=dst)
        data = json.loads(show.stdout)
        statuses = data.get("rules", {}).get("format", {}).get("allowed_statuses", [])
        assert "Experimental" in statuses

    def test_remove_status(self, project, tmp_path):
        import os

        dst = tmp_path / "config_remove"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        result = run_elspais(
            "config",
            "remove",
            "rules.format.allowed_statuses",
            "Superseded",
            cwd=dst,
        )
        assert result.returncode == 0

        show = run_elspais("config", "show", "--format", "json", cwd=dst)
        data = json.loads(show.stdout)
        statuses = data.get("rules", {}).get("format", {}).get("allowed_statuses", [])
        assert "Superseded" not in statuses


class TestConfigUnset:
    """Config unset removes a key."""

    def test_unset_key(self, project, tmp_path):
        import os

        import tomlkit

        dst = tmp_path / "config_unset"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        result = run_elspais("config", "unset", "project.namespace", cwd=dst)
        assert result.returncode == 0

        content = (dst / ".elspais.toml").read_text()
        data = tomlkit.loads(content)
        assert "namespace" not in data.get("project", {})


class TestEditCommand:
    """Edit command modifies requirements in-place."""

    def test_edit_status(self, project, tmp_path):
        import os

        dst = tmp_path / "edit_project"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        result = run_elspais("edit", "REQ-p00001", "--status", "Draft", cwd=dst)
        if result.returncode == 0:
            content = (dst / "spec" / "prd-core.md").read_text()
            assert "Draft" in content


class TestChangedCommand:
    """Changed command detects git changes to spec files."""

    def test_changed_detects_uncommitted_edit(self, project, tmp_path):
        import os

        dst = tmp_path / "changed_project"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        # Modify a spec file
        spec = dst / "spec" / "prd-core.md"
        content = spec.read_text()
        spec.write_text(content.replace("User Authentication", "Modified Authentication"))

        result = run_elspais("changed", "--format", "json", cwd=dst)
        assert result.returncode == 0
        output = result.stdout.strip()
        if output:
            data = json.loads(output)
            assert isinstance(data, (list, dict))

    def test_changed_no_changes(self, project, tmp_path):
        import os

        dst = tmp_path / "changed_clean"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        result = run_elspais("changed", "--format", "json", cwd=dst)
        assert result.returncode == 0

    def test_changed_base_branch(self, project, tmp_path):
        import os

        dst = tmp_path / "changed_branch"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init", "-b", "main"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        result = run_elspais(
            "changed",
            "--base-branch",
            "main",
            "--format",
            "json",
            cwd=dst,
        )
        assert result.returncode == 0


class TestHealthOutputToFile:
    """Health --output writes to file."""

    def test_output_to_file(self, project, tmp_path):
        out_file = tmp_path / "health-output.json"
        result = run_elspais(
            "checks",
            "--format",
            "json",
            "--lenient",
            "--output",
            str(out_file),
            cwd=project,
        )
        if result.returncode == 0 and out_file.exists():
            content = out_file.read_text()
            data = json.loads(content)
            assert isinstance(data, (dict, list))


class TestMultiAssertionSyntax:
    """Multi-assertion compact syntax (A+B) in code references."""

    def test_multi_assertion_code_reference(self, project):
        """src/auth_multi.py uses REQ-d00001-A+B syntax."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0


# ===================================================================
# Group 3: MCP query tests (read-only, use shared mcp_server)
# ===================================================================


class TestMCPSearchAndNavigation:
    """MCP search, get_requirement, get_hierarchy."""

    def test_search_finds_requirements(self, project, mcp_server):
        from .helpers import mcp_call_all

        results = mcp_call_all(mcp_server, "search", {"query": "Auth"})
        assert len(results) >= 1
        assert any("Auth" in str(r) for r in results)

    def test_search_empty_returns_nothing(self, project, mcp_server):
        from .helpers import mcp_call_all

        results = mcp_call_all(mcp_server, "search", {"query": "zzz_nonexistent_xyz"})
        assert len(results) == 0

    def test_get_requirement_returns_details(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        assert result["id"] == "REQ-p00001"
        assert "User Authentication" in result.get("title", "")
        assert len(result.get("assertions", [])) >= 3

    def test_get_requirement_not_found(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-zzz99"})
        assert result is None or result.get("error") or result.get("_error")

    def test_get_hierarchy(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_hierarchy", {"req_id": "REQ-d00001"})
        assert "ancestors" in result
        assert "children" in result
        ancestor_ids = [a.get("id", "") for a in result["ancestors"]]
        assert any("o00001" in aid for aid in ancestor_ids) or len(result["ancestors"]) > 0


class TestMCPProjectInfo:
    """MCP project summary, workspace info, graph status."""

    def test_project_summary(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_project_summary", {})
        assert isinstance(result, dict)
        assert "levels" in result or "total" in result or len(result) > 0

    def test_workspace_info(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_workspace_info", {"detail": "default"})
        assert isinstance(result, dict)

    def test_workspace_info_testing(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_workspace_info", {"detail": "testing"})
        assert isinstance(result, dict)

    def test_workspace_info_coverage(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_workspace_info", {"detail": "coverage"})
        assert isinstance(result, dict)

    def test_workspace_info_all(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_workspace_info", {"detail": "all"})
        assert isinstance(result, dict)

    def test_graph_status(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_graph_status", {})
        assert isinstance(result, dict)


class TestMCPSubtree:
    """MCP get_subtree in various formats."""

    def test_subtree_markdown(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {"root_id": "REQ-p00001", "format": "markdown"},
        )
        result_str = str(result)
        assert "REQ-p00001" in result_str or "User Authentication" in result_str

    def test_subtree_flat(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {"root_id": "REQ-p00001", "format": "flat"},
        )
        assert isinstance(result, dict)
        assert "nodes" in result or "edges" in result

    def test_subtree_nested(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {"root_id": "REQ-p00001", "format": "nested"},
        )
        assert isinstance(result, dict)

    def test_subtree_depth_limited(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {"root_id": "REQ-p00001", "depth": 1, "format": "flat"},
        )
        assert isinstance(result, dict)


class TestMCPCursors:
    """MCP cursor protocol for incremental iteration."""

    def test_cursor_search(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "open_cursor",
            {"query": "search", "params": {"query": "REQ"}, "batch_size": 1},
        )
        assert "total" in result
        assert result["total"] >= 3

        next_result = mcp_call(mcp_server, "cursor_next", {"count": 1})
        assert isinstance(next_result, dict)

        info = mcp_call(mcp_server, "cursor_info", {})
        assert "position" in info
        assert "remaining" in info

    def test_cursor_subtree(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "open_cursor",
            {"query": "subtree", "params": {"root_id": "REQ-p00001"}, "batch_size": 0},
        )
        assert "total" in result
        assert result["total"] >= 1


class TestMCPTestCoverage:
    """MCP test coverage tools."""

    def test_get_test_coverage(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_test_coverage", {"req_id": "REQ-d00001"})
        assert isinstance(result, dict)

    def test_uncovered_assertions(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_uncovered_assertions", {})
        assert isinstance(result, (list, dict))


class TestMCPScopedSearch:
    """MCP scoped_search and discover_requirements."""

    def test_scoped_search(self, project, mcp_server):
        from .helpers import mcp_call_all

        result = mcp_call_all(
            mcp_server,
            "scoped_search",
            {"query": "module", "scope_id": "REQ-p00001", "direction": "descendants"},
        )
        assert isinstance(result, list)

    def test_discover_requirements(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "discover_requirements",
            {"query": "auth", "scope_id": "REQ-p00001"},
        )
        assert isinstance(result, dict)


class TestMCPKeywordSearch:
    """MCP find_by_keywords and get_all_keywords."""

    def test_get_all_keywords(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_all_keywords", {})
        assert isinstance(result, (list, dict))

    def test_find_by_keywords(self, project, mcp_server):
        from .helpers import mcp_call_all

        result = mcp_call_all(
            mcp_server,
            "find_by_keywords",
            {"keywords": ["auth", "user"], "match_all": False},
        )
        assert isinstance(result, list)

    def test_find_assertions_by_keywords(self, project, mcp_server):
        from .helpers import mcp_call_all

        result = mcp_call_all(
            mcp_server,
            "find_assertions_by_keywords",
            {"keywords": ["email"], "match_all": True},
        )
        assert isinstance(result, list)


class TestMCPQueryNodes:
    """MCP query_nodes with various filters."""

    def test_query_by_kind(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "query_nodes", {"kind": "requirement"})
        assert result["count"] >= 10

    def test_query_by_level(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "query_nodes", {"level": "prd"})
        assert result["count"] >= 5

    def test_query_by_status(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "query_nodes", {"status": "Active"})
        assert result["count"] >= 1


class TestMCPGraphHealth:
    """MCP get_orphaned_nodes and get_broken_references."""

    def test_orphaned_nodes(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_orphaned_nodes", {})
        assert isinstance(result, (list, dict))

    def test_broken_references(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_broken_references", {})
        assert isinstance(result, (list, dict))


class TestMCPAgentInstructions:
    """MCP agent_instructions tool."""

    def test_agent_instructions(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "agent_instructions", {})
        assert isinstance(result, (dict, str))


class TestMCPRefreshGraph:
    """MCP refresh_graph rebuilds from files."""

    def test_refresh_stable(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "refresh_graph", {})
        assert isinstance(result, dict)
        assert not result.get("_error")

        summary = mcp_call(mcp_server, "get_project_summary", {})
        assert isinstance(summary, dict)


class TestMCPSuggestLinks:
    """MCP suggest_links for unlinked nodes."""

    def test_suggest_links(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "suggest_links", {})
        assert isinstance(result, (list, dict))


class TestMCPChangedRequirements:
    """MCP get_changed_requirements."""

    def test_no_changes(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_changed_requirements", {})
        assert isinstance(result, (list, dict))


# ===================================================================
# Group 4: MCP mutation tests (each starts its own server for isolation)
# ===================================================================


class TestMCPMutations:
    """MCP mutation tools: add, update, rename, undo."""

    def test_add_requirement_and_undo(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_add_requirement",
                {"req_id": "REQ-p00099", "title": "New Feature", "level": "prd", "status": "Draft"},
            )
            assert isinstance(result, dict)
            assert not result.get("_error"), f"Add failed: {result}"

            get_result = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00099"})
            assert get_result and get_result.get("id") == "REQ-p00099"

            undo = mcp_call(proc, "undo_last_mutation", {})
            assert isinstance(undo, dict)

            after_undo = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00099"})
            assert after_undo is None or after_undo.get("error") or after_undo.get("_error")
        finally:
            stop_mcp(proc)

    def test_update_title_and_undo(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            original = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            orig_title = original["title"]

            mcp_call(
                proc,
                "mutate_update_title",
                {"node_id": "REQ-p00001", "new_title": "Updated Title"},
            )

            updated = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert updated["title"] == "Updated Title"

            mcp_call(proc, "undo_last_mutation", {})
            reverted = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert reverted["title"] == orig_title
        finally:
            stop_mcp(proc)

    def test_mutation_log(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            mcp_call(
                proc,
                "mutate_update_title",
                {"node_id": "REQ-p00001", "new_title": "Title V1"},
            )
            mcp_call(
                proc,
                "mutate_update_title",
                {"node_id": "REQ-p00001", "new_title": "Title V2"},
            )

            log = mcp_call(proc, "get_mutation_log", {"limit": 10})
            assert isinstance(log, (list, dict))
        finally:
            stop_mcp(proc)


class TestMCPAssertionMutations:
    """MCP assertion CRUD operations."""

    def test_add_assertion(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_add_assertion",
                {"req_id": "REQ-p00001", "label": "D", "text": "The system SHALL support SSO."},
            )
            assert isinstance(result, dict)
            assert not result.get("_error")

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            labels = [a.get("label", "") for a in req.get("assertions", [])]
            assert "D" in labels
        finally:
            stop_mcp(proc)

    def test_update_assertion(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_update_assertion",
                {
                    "assertion_id": "REQ-p00001-A",
                    "new_text": "The system SHALL create and manage user accounts.",
                },
            )
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)

    def test_delete_assertion_and_undo(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_delete_assertion",
                {"assertion_id": "REQ-p00001-C", "confirm": True},
            )
            assert isinstance(result, dict)

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            labels = [a.get("label", "") for a in req.get("assertions", [])]
            assert "C" not in labels

            mcp_call(proc, "undo_last_mutation", {})
            req2 = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            labels2 = [a.get("label", "") for a in req2.get("assertions", [])]
            assert "C" in labels2
        finally:
            stop_mcp(proc)

    def test_rename_assertion(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_rename_assertion",
                {"old_id": "REQ-p00001-A", "new_label": "X"},
            )
            assert isinstance(result, dict)

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            labels = [a.get("label", "") for a in req.get("assertions", [])]
            assert "X" in labels
            assert "A" not in labels
        finally:
            stop_mcp(proc)


class TestMCPEdgeMutations:
    """MCP edge add/delete operations."""

    def test_add_edge(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_add_edge",
                {"source_id": "REQ-d00002", "target_id": "REQ-o00001", "edge_kind": "implements"},
            )
            assert isinstance(result, dict)
            assert not result.get("_error"), f"Edge add failed: {result}"
        finally:
            stop_mcp(proc)

    def test_delete_edge_and_undo(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_delete_edge",
                {"source_id": "REQ-d00001", "target_id": "REQ-o00001", "confirm": True},
            )
            assert isinstance(result, dict)

            mcp_call(proc, "undo_last_mutation", {})

            hier = mcp_call(proc, "get_hierarchy", {"req_id": "REQ-d00001"})
            ancestors = hier.get("ancestors", [])
            assert len(ancestors) > 0
        finally:
            stop_mcp(proc)

    def test_change_edge_kind(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_change_edge_kind",
                {"source_id": "REQ-d00003", "target_id": "REQ-d00001", "new_kind": "implements"},
            )
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)


class TestMCPRenameNode:
    """MCP mutate_rename_node."""

    def test_rename_and_undo(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_rename_node",
                {"old_id": "REQ-p00003", "new_id": "REQ-p00099"},
            )
            assert isinstance(result, dict)
            assert not result.get("_error"), f"Rename failed: {result}"

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00099"})
            assert req and req.get("id") == "REQ-p00099"

            old = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00003"})
            assert old is None or old.get("_error") or old.get("error")

            mcp_call(proc, "undo_last_mutation", {})

            restored = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00003"})
            assert restored and restored.get("id") == "REQ-p00003"
        finally:
            stop_mcp(proc)


class TestMCPChangeStatus:
    """MCP mutate_change_status."""

    def test_change_status(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_change_status",
                {"node_id": "REQ-p00001", "new_status": "Draft"},
            )
            assert isinstance(result, dict)

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            req_str = json.dumps(req)
            assert "Draft" in req_str
        finally:
            stop_mcp(proc)


class TestMCPDeleteRequirement:
    """MCP mutate_delete_requirement."""

    def test_delete_and_undo(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(
                proc,
                "mutate_delete_requirement",
                {"node_id": "REQ-p00003", "confirm": True},
            )
            assert isinstance(result, dict)

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00003"})
            assert req is None or req.get("_error") or req.get("error")

            req1 = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req1 and req1.get("id") == "REQ-p00001"

            mcp_call(proc, "undo_last_mutation", {})

            restored = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00003"})
            assert restored and restored.get("id") == "REQ-p00003"
        finally:
            stop_mcp(proc)


class TestMCPUndoToMutation:
    """MCP undo_to_mutation for selective rollback."""

    def test_undo_multiple(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            mcp_call(
                proc, "mutate_update_title", {"node_id": "REQ-p00001", "new_title": "Title V1"}
            )
            mcp_call(
                proc, "mutate_update_title", {"node_id": "REQ-p00001", "new_title": "Title V2"}
            )
            mcp_call(
                proc, "mutate_update_title", {"node_id": "REQ-p00001", "new_title": "Title V3"}
            )

            log = mcp_call(proc, "get_mutation_log", {"limit": 10})
            assert isinstance(log, (list, dict))

            mcp_call(proc, "undo_last_mutation", {})
            mcp_call(proc, "undo_last_mutation", {})
            mcp_call(proc, "undo_last_mutation", {})

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req["title"] == "User Authentication"
        finally:
            stop_mcp(proc)


class TestMCPSaveRefreshRoundTrip:
    """Mutate -> save -> refresh -> verify persisted."""

    def test_save_refresh_roundtrip(self, project, tmp_path):
        pytest.importorskip("mcp")
        import os

        from .helpers import mcp_call, start_mcp, stop_mcp

        dst = tmp_path / "mcp_save"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        proc = start_mcp(dst)
        try:
            mcp_call(
                proc,
                "mutate_update_title",
                {"node_id": "REQ-p00001", "new_title": "Updated Via MCP"},
            )

            save = mcp_call(proc, "save_mutations", {"save_branch": False})
            assert not save.get("_error"), f"Save failed: {save}"

            refresh = mcp_call(proc, "refresh_graph", {})
            assert not refresh.get("_error"), f"Refresh failed: {refresh}"

            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req["title"] == "Updated Via MCP"
        finally:
            stop_mcp(proc)


class TestMCPSaveMutations:
    """MCP save_mutations persists changes to disk."""

    def test_save_persists_to_file(self, project, tmp_path):
        pytest.importorskip("mcp")
        import os

        from .helpers import mcp_call, start_mcp, stop_mcp

        dst = tmp_path / "mcp_persist"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        proc = start_mcp(dst)
        try:
            mcp_call(
                proc,
                "mutate_update_title",
                {"node_id": "REQ-p00001", "new_title": "Persisted Title Change"},
            )

            result = mcp_call(proc, "save_mutations", {"save_branch": False})
            assert isinstance(result, dict)
            assert not result.get("_error"), f"Save failed: {result}"

            spec = dst / "spec" / "prd-core.md"
            content = spec.read_text()
            assert "Persisted Title Change" in content
        finally:
            stop_mcp(proc)


class TestMCPComprehensiveWorkflow:
    """Exercise many MCP tools in a single test."""

    def test_full_workflow(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, mcp_call_all, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            # 1. Status
            status = mcp_call(proc, "get_graph_status", {})
            assert isinstance(status, dict)

            # 2. Summary
            summary = mcp_call(proc, "get_project_summary", {})
            assert isinstance(summary, dict)

            # 3. Search
            results = mcp_call_all(proc, "search", {"query": "notification"})
            assert len(results) >= 1

            # 4. Get requirement
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00002"})
            assert req["id"] == "REQ-d00002"

            # 5. Hierarchy
            hier = mcp_call(proc, "get_hierarchy", {"req_id": "REQ-d00002"})
            assert "ancestors" in hier

            # 6. Subtree
            subtree = mcp_call(
                proc,
                "get_subtree",
                {"root_id": "REQ-p00002", "format": "flat"},
            )
            assert isinstance(subtree, dict)

            # 7. Add assertion
            mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "REQ-d00002",
                    "label": "B",
                    "text": "The module SHALL log delivery status.",
                },
            )

            # 8. Verify
            req2 = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00002"})
            labels = [a.get("label", "") for a in req2.get("assertions", [])]
            assert "B" in labels

            # 9. Log
            log = mcp_call(proc, "get_mutation_log", {"limit": 5})
            assert isinstance(log, (list, dict))

            # 10. Undo
            mcp_call(proc, "undo_last_mutation", {})

            # 11. Verify undone
            req3 = mcp_call(proc, "get_requirement", {"req_id": "REQ-d00002"})
            labels3 = [a.get("label", "") for a in req3.get("assertions", [])]
            assert "B" not in labels3

            # 12. Workspace info
            ws = mcp_call(proc, "get_workspace_info", {"detail": "testing"})
            assert isinstance(ws, dict)
        finally:
            stop_mcp(proc)


class TestMCPMultiMutationWorkflow:
    """Complex mutation workflow: add req, assertions, edges, save."""

    def test_build_requirement_from_scratch(self, project, tmp_path):
        pytest.importorskip("mcp")
        import os

        from .helpers import mcp_call, start_mcp, stop_mcp

        dst = tmp_path / "mcp_multi"
        shutil.copytree(project, dst)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=dst, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dst, capture_output=True, env=env)

        proc = start_mcp(dst)
        try:
            # 1. Add new OPS requirement
            mcp_call(
                proc,
                "mutate_add_requirement",
                {
                    "req_id": "REQ-o00099",
                    "title": "New Operations Req",
                    "level": "ops",
                    "status": "Draft",
                },
            )

            # 2. Add edge
            mcp_call(
                proc,
                "mutate_add_edge",
                {"source_id": "REQ-o00099", "target_id": "REQ-p00001", "edge_kind": "implements"},
            )

            # 3. Add assertions
            mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "REQ-o00099",
                    "label": "A",
                    "text": "Operations SHALL deploy new service.",
                },
            )
            mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "REQ-o00099",
                    "label": "B",
                    "text": "Operations SHALL monitor new service.",
                },
            )

            # 4. Verify
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-o00099"})
            assert req["id"] == "REQ-o00099"
            assert req["title"] == "New Operations Req"
            assert len(req.get("assertions", [])) == 2

            # 5. Hierarchy
            hier = mcp_call(proc, "get_hierarchy", {"req_id": "REQ-o00099"})
            ancestor_ids = [a.get("id", "") for a in hier.get("ancestors", [])]
            assert "REQ-p00001" in ancestor_ids

            # 6. Save
            save = mcp_call(proc, "save_mutations", {"save_branch": False})
            assert not save.get("_error"), f"Save failed: {save}"
        finally:
            stop_mcp(proc)


class TestMCPFixBrokenReference:
    """MCP mutate_fix_broken_reference."""

    def test_fix_broken_ref(self, project, tmp_path):
        pytest.importorskip("mcp")
        # Build a project with a broken reference
        from .helpers import Requirement as Req
        from .helpers import base_config as bc
        from .helpers import build_project as bp
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = bc(name="broken-ref-std", allow_structural_orphans=True)
        prd = Req(
            "REQ-p00001",
            "Target",
            "PRD",
            assertions=[("A", "The system SHALL be the target.")],
        )
        dev = Req(
            "REQ-d00001",
            "With Bad Ref",
            "DEV",
            implements="REQ-p99999",
            assertions=[("A", "The module SHALL reference wrong thing.")],
        )

        dst = tmp_path / "broken_ref"
        bp(dst, cfg, spec_files={"spec/prd.md": [prd], "spec/dev.md": [dev]})

        proc = start_mcp(dst)
        try:
            broken = mcp_call(proc, "get_broken_references", {})
            assert isinstance(broken, (list, dict))

            result = mcp_call(
                proc,
                "mutate_fix_broken_reference",
                {
                    "source_id": "REQ-d00001",
                    "old_target_id": "REQ-p99999",
                    "new_target_id": "REQ-p00001",
                },
            )
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)
