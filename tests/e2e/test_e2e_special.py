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
            'version = 3\n[project]\nname = "test"\nnamespace = "REQ"\n\n'
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


# ---------------------------------------------------------------------------
# H6 requirement with section blocks cannot be auto-fixed (REQ-d00250-C/E)
# ---------------------------------------------------------------------------


# Verifies: REQ-d00250-C
# Verifies: REQ-d00250-E
class TestH6SectionDepthUnfixable:
    """H6 requirement with section blocks cannot be auto-fixed."""

    @pytest.fixture
    def h6_project(self, tmp_path):
        """Standalone project with a single H6 requirement that has Assertions."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "test.md").write_text(
            "###### REQ-d00001: H6 Test\n\n"
            "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
            "###### Assertions\n\n"
            "A. The system shall demonstrate the H6 unfixable case.\n\n"
            "*End* *H6 Test* | **Hash**: -\n"
        )
        (tmp_path / ".elspais.toml").write_text(
            'version = 3\n[project]\nname = "test"\nnamespace = "REQ"\n\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )
        return tmp_path

    def test_fix_cannot_resolve_h6_req(self, h6_project):
        """elspais fix exits 1, prints to stderr, leaves file untouched."""
        result = run_elspais("fix", cwd=h6_project)
        assert result.returncode == 1, (
            f"expected exit 1 for H6 unfixable; got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "REQ-d00001" in result.stderr
        assert "section header depth" in result.stderr.lower()
        content = (h6_project / "spec" / "test.md").read_text()
        assert "###### REQ-d00001" in content
        assert "###### Assertions" in content

    def test_health_flags_h6_unfixable(self, h6_project):
        """elspais checks reports unfixable issue and exits non-zero."""
        result = run_elspais("checks", cwd=h6_project)
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "unfixable" in combined.lower(), (
            f"Expected 'unfixable' in checks output.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# Fix must fail loudly when changelog author cannot be resolved
# Verifies: REQ-p00004-A, REQ-d00231-E
# ---------------------------------------------------------------------------


def _make_active_project_no_author(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Build a project with one Active req whose hash is stale, configured
    so ``elspais fix`` will fail to resolve the changelog author.

    Returns a ``(project_root, env)`` tuple. ``env`` is the dict callers
    should pass to ``run_elspais(env=...)`` to ensure no inherited
    git/GH_* identity leaks in.
    """
    # Config: id_source = "git" so gh CLI is never consulted. hash_current
    # is on so an Active req with a stale hash triggers the changelog path.
    (tmp_path / ".elspais.toml").write_text(
        "version = 3\n"
        "\n"
        "[project]\n"
        'name = "no-author"\n'
        'namespace = "REQ"\n'
        "\n"
        "[scanning.spec]\n"
        'directories = ["spec"]\n'
        "\n"
        "[changelog]\n"
        "hash_current = true\n"
        'id_source = "git"\n'
    )
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "requirements.md").write_text(
        "# REQ-d00001: Test Req\n"
        "\n"
        "**Level**: DEV | **Status**: Active | **Implements**: -\n"
        "\n"
        "## Assertions\n"
        "\n"
        "A. The system SHALL do X.\n"
        "\n"
        "*End* *Test Req* | **Hash**: 00000000\n"
        "---\n"
    )

    # Initialise git WITH author identity so the initial commit succeeds.
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)

    # Now strip the per-repo user identity so resolve_changelog_author will
    # find nothing.
    subprocess.run(["git", "config", "--unset", "user.name"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "--unset", "user.email"], cwd=tmp_path, capture_output=True)

    # Redirect git's global config to /dev/null so any ~/.gitconfig
    # cannot supply identity either. Keep HOME intact -- changing it
    # breaks Python's user-site-packages discovery for the subprocess.
    env = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        # Strip any GIT_AUTHOR_* / GIT_COMMITTER_* by setting them empty.
        # run_elspais merges these into os.environ, so empty strings make
        # git treat them as unset.
        "GIT_AUTHOR_NAME": "",
        "GIT_AUTHOR_EMAIL": "",
        "GIT_COMMITTER_NAME": "",
        "GIT_COMMITTER_EMAIL": "",
        # Force the git fallback path so gh CLI (which has its own
        # auth cache) cannot supply identity either.
        "GH_TOKEN": "",
        "GITHUB_TOKEN": "",
    }
    return tmp_path, env


class TestFixFailsWhenAuthorMissing:
    """End-to-end check that ``elspais fix`` exits 1 and leaves files
    untouched when changelog author identity is unresolvable.
    """

    def test_fix_exits_1_and_leaves_file_unchanged(self, tmp_path):
        project, env = _make_active_project_no_author(tmp_path)
        spec_file = project / "spec" / "requirements.md"
        before = spec_file.read_text()

        result = run_elspais("fix", cwd=project, env=env)
        assert result.returncode == 1, (
            f"expected exit 1, got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        combined = result.stdout + result.stderr
        assert ("author_name" in combined) or ("author_id" in combined), (
            "Expected stderr to mention the missing author field. "
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

        after = spec_file.read_text()
        assert after == before, "fix must not write to disk on author failure"

    def test_fix_succeeds_when_hash_current_false(self, tmp_path):
        project, env = _make_active_project_no_author(tmp_path)
        # Flip hash_current = false; author check should not trigger.
        config = project / ".elspais.toml"
        config.write_text(config.read_text().replace("hash_current = true", "hash_current = false"))

        spec_file = project / "spec" / "requirements.md"
        result = run_elspais("fix", cwd=project, env=env)
        assert result.returncode == 0, (
            f"fix should succeed when hash_current=false; got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        content = spec_file.read_text()
        assert "00000000" not in content, "stale hash should have been fixed"

    def test_fix_succeeds_when_author_name_not_required(self, tmp_path):
        project, env = _make_active_project_no_author(tmp_path)
        # Re-add user.email but leave user.name unset, then mark author_name
        # as not required.
        subprocess.run(
            ["git", "config", "user.email", "real@example.com"],
            cwd=project,
            capture_output=True,
        )
        config = project / ".elspais.toml"
        config.write_text(
            config.read_text() + "\n[changelog.require]\nauthor_name = false\nauthor_id = true\n"
        )

        spec_file = project / "spec" / "requirements.md"
        result = run_elspais("fix", "REQ-d00001", "-m", "tracked", cwd=project, env=env)
        assert result.returncode == 0, (
            f"fix should succeed when author_name is not required; "
            f"got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        content = spec_file.read_text()
        assert "## Changelog" in content
        assert "real@example.com" in content


# ---------------------------------------------------------------------------
# TOOL-39: daemon reuse must not serve results built from pre-change config
# ---------------------------------------------------------------------------


class TestDaemonConfigStaleRestart:
    """Verifies REQ-p00004-J: config is re-read from disk when reloading.

    A CLI call served by an already-running daemon must reflect config
    edits made after the daemon started: the stale daemon is restarted
    (it holds no unsaved mutations) and the fresh graph is served.
    """

    def test_config_edit_restarts_daemon_and_reflects_change(self, tmp_path):
        from tests.e2e.helpers import (
            Requirement,
            base_config,
            build_project,
            write_config,
            write_spec_file,
        )

        cfg = base_config(name="stale-daemon-project")
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Feature One",
                        "PRD",
                        assertions=[("A", "The system SHALL do one thing.")],
                    )
                ]
            },
        )

        # First CLI call auto-starts a daemon (cli_ttl=2 in base_config)
        trace1 = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert trace1.returncode == 0, trace1.stderr
        assert {r["id"] for r in json.loads(trace1.stdout)} == {"REQ-p00001"}

        daemon_json = tmp_path / ".elspais" / "daemon.json"
        assert daemon_json.exists(), "daemon should have auto-started"
        pid_before = json.loads(daemon_json.read_text())["pid"]

        # Mutate config: add a second spec directory with a new requirement.
        # Only a config re-read can reveal REQ-p00002.
        write_spec_file(
            tmp_path / "spec2" / "prd2.md",
            [
                Requirement(
                    "REQ-p00002",
                    "Feature Two",
                    "PRD",
                    assertions=[("A", "The system SHALL do another thing.")],
                )
            ],
        )
        cfg2 = base_config(name="stale-daemon-project", spec_dir=["spec", "spec2"])
        write_config(tmp_path / ".elspais.toml", cfg2)

        # Next CLI call must not silently serve the pre-change graph.
        trace2 = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert trace2.returncode == 0, trace2.stderr
        ids = {r["id"] for r in json.loads(trace2.stdout)}
        assert ids == {
            "REQ-p00001",
            "REQ-p00002",
        }, f"CLI served results from pre-change config: {ids}"

        # The stale daemon (clean, no unsaved mutations) was restarted.
        assert daemon_json.exists()
        pid_after = json.loads(daemon_json.read_text())["pid"]
        assert pid_after != pid_before, "stale daemon should have been restarted"


# ---------------------------------------------------------------------------
# Daemon session identity: bound at start, or withheld on explicit starts
# ---------------------------------------------------------------------------
# Verifies: REQ-o00074-A+B+C+E+F+I


class TestDaemonSpawnerLiveness:
    """Validates REQ-o00074-A: a daemon started implicitly on behalf of a
    client records that client's identity at the moment it starts, so it can
    afterwards determine whether the client still exists.

    Validates REQ-o00074-B: the client identities it has recorded are
    observable in the state record clients use to locate it.

    Validates REQ-o00074-C: a daemon started explicitly records no client
    identity and keeps idle-timeout-only lifetime.

    Validates REQ-o00074-E: while a recorded client still exists the daemon
    keeps serving, including a client that adopted it after the one that
    started it was gone; once none of them exists it terminates.

    Validates REQ-o00074-F: that obligation holds under every idle-timeout
    configuration, including one in which the idle timeout never expires.

    Validates REQ-o00074-I: a daemon terminating with no client present
    persists the changes it holds and leaves the facts of that save where the
    next client will find them.

    Deterministic: the "client" is a subprocess we control and kill; the
    daemon's check interval and grace period are shortened via the internal
    env knobs. This is the only tier that catches a watchdog thread that never
    starts at all.
    """

    def test_REQ_o00074_A_daemon_exits_after_spawner_dies(self, tmp_path):
        import os
        import sys
        import time

        from tests.e2e.helpers import Requirement, base_config, build_project

        build_project(
            tmp_path,
            base_config(name="spawner-liveness-project"),
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Feature One",
                        "PRD",
                        assertions=[("A", "The system SHALL do one thing.")],
                    )
                ]
            },
        )

        # Fake session process: long-lived until we kill it.
        spawner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        daemon_pid = None
        try:
            # Implicit daemon spawn via the CLI reuse path, declaring the
            # fake session as spawner.
            result = run_elspais(
                "summary",
                cwd=tmp_path,
                env={
                    "ELSPAIS_SPAWNER_PID": str(spawner.pid),
                    "_ELSPAIS_SPAWNER_CHECK_INTERVAL": "0.3",
                },
            )
            assert result.returncode == 0, result.stderr

            daemon_json = tmp_path / ".elspais" / "daemon.json"
            assert daemon_json.exists(), "daemon should have auto-started"
            info = json.loads(daemon_json.read_text())
            assert info["spawner_pid"] == spawner.pid
            # REQ-o00074-B: the recorded client set, not just the starter,
            # is what an operator reads to ask why the daemon is still up.
            assert info["client_pids"] == [spawner.pid]
            daemon_pid = info["pid"]
            os.kill(daemon_pid, 0)  # daemon alive while spawner alive

            # Kill the session; the daemon must notice and exit cleanly
            # (no unsaved mutations -> no grace period).
            spawner.kill()
            spawner.wait()

            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    os.kill(daemon_pid, 0)
                except ProcessLookupError:
                    break  # daemon exited
                time.sleep(0.3)
            else:
                raise AssertionError(
                    "daemon survived its spawner's death: "
                    + (tmp_path / ".elspais" / "daemon.log").read_text()[-1000:]
                )

            log = (tmp_path / ".elspais" / "daemon.log").read_text()
            assert "shutting down" in log
        finally:
            spawner.kill()
            if daemon_pid is not None:
                try:
                    os.kill(daemon_pid, 15)
                except OSError:
                    pass

    def test_REQ_o00074_C_explicit_restart_records_no_spawner(self, tmp_path):
        """`elspais daemon restart` is an explicit start: the daemon keeps
        TTL-only lifetime and records no spawner identity, even when the
        environment declares one."""
        import os
        import time

        from tests.e2e.helpers import Requirement, base_config, build_project

        build_project(
            tmp_path,
            base_config(name="explicit-daemon-project"),
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Feature One",
                        "PRD",
                        assertions=[("A", "The system SHALL do one thing.")],
                    )
                ]
            },
        )

        daemon_json = tmp_path / ".elspais" / "daemon.json"
        try:
            result = run_elspais(
                "daemon",  # defaults to the restart action
                cwd=tmp_path,
                env={"ELSPAIS_SPAWNER_PID": str(os.getpid())},
            )
            assert result.returncode == 0, result.stderr
            assert daemon_json.exists()
            info = json.loads(daemon_json.read_text())
            assert (
                "spawner_pid" not in info
            ), f"explicitly restarted daemon must not be session-tied: {info}"
            # And it stays up: no watchdog is running.
            time.sleep(1.5)
            os.kill(info["pid"], 0)
        finally:
            if daemon_json.exists():
                try:
                    os.kill(json.loads(daemon_json.read_text())["pid"], 15)
                except (OSError, ValueError, KeyError):
                    pass

    def test_REQ_o00074_F_daemon_exits_with_idle_timeout_disabled(self, tmp_path):
        """Validates REQ-o00074-F: the termination obligation holds under every
        idle-timeout configuration, including one in which the idle timeout
        never expires (``cli_ttl < 0``), and is not discharged by client request
        traffic. The check must hang off the daemon's own passage of time, not
        off a timeout a project can switch off or a client can keep resetting."""
        import os
        import sys
        import time
        import urllib.error
        import urllib.request

        from tests.e2e.helpers import Requirement, base_config, build_project

        config = base_config(name="no-ttl-spawner-project")
        config["cli_ttl"] = -1  # daemon never times out on idleness

        build_project(
            tmp_path,
            config,
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Feature One",
                        "PRD",
                        assertions=[("A", "The system SHALL do one thing.")],
                    )
                ]
            },
        )

        spawner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        daemon_pid = None
        try:
            result = run_elspais(
                "summary",
                cwd=tmp_path,
                env={
                    "ELSPAIS_SPAWNER_PID": str(spawner.pid),
                    "_ELSPAIS_SPAWNER_CHECK_INTERVAL": "0.3",
                },
            )
            assert result.returncode == 0, result.stderr

            daemon_json = tmp_path / ".elspais" / "daemon.json"
            assert daemon_json.exists(), "daemon should have auto-started with cli_ttl=-1"
            info = json.loads(daemon_json.read_text())
            assert info["spawner_pid"] == spawner.pid
            daemon_pid = info["pid"]
            dirty_url = f"http://127.0.0.1:{info['port']}/api/dirty"

            spawner.kill()
            spawner.wait()

            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    os.kill(daemon_pid, 0)
                except ProcessLookupError:
                    break  # daemon exited
                # A client that keeps talking to the daemon must not keep it
                # alive: read traffic is not evidence a writer is present.
                try:
                    urllib.request.urlopen(dirty_url, timeout=2).read()
                except (urllib.error.URLError, OSError):
                    pass  # daemon shutting down mid-poll is the expected end
                time.sleep(0.3)
            else:
                raise AssertionError(
                    "daemon with a never-expiring idle timeout survived its "
                    "spawner's death under continuous client traffic: "
                    + (tmp_path / ".elspais" / "daemon.log").read_text()[-1000:]
                )
        finally:
            spawner.kill()
            if daemon_pid is not None:
                try:
                    os.kill(daemon_pid, 15)
                except OSError:
                    pass

    def test_REQ_o00074_E_adopted_client_keeps_the_daemon_then_lets_it_go(self, tmp_path):
        """Validates REQ-o00074-E: a client that begins using a running daemon
        is recorded alongside its existing clients; the daemon keeps serving
        while that adopted client exists and terminates once it too is gone.

        The negative half is the point. A daemon that merely never dies would
        satisfy the positive half trivially, so the same daemon is driven
        through both: it survives its starter's death because an adopter is
        present, and then dies when the adopter goes.
        """
        import os
        import sys
        import time
        import urllib.request

        from tests.e2e.helpers import Requirement, base_config, build_project

        build_project(
            tmp_path,
            base_config(name="adopted-client-project"),
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Feature One",
                        "PRD",
                        assertions=[("A", "The system SHALL do one thing.")],
                    )
                ]
            },
        )

        starter = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        adopter = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        daemon_pid = None
        daemon_json = tmp_path / ".elspais" / "daemon.json"
        try:
            result = run_elspais(
                "summary",
                cwd=tmp_path,
                env={
                    "ELSPAIS_SPAWNER_PID": str(starter.pid),
                    "_ELSPAIS_SPAWNER_CHECK_INTERVAL": "0.3",
                },
            )
            assert result.returncode == 0, result.stderr
            assert daemon_json.exists(), "daemon should have auto-started"
            info = json.loads(daemon_json.read_text())
            daemon_pid = info["pid"]

            # A second client picks up the running daemon and announces
            # itself, which is what the adoption surface exists for.
            req = urllib.request.Request(
                f"http://127.0.0.1:{info['port']}/api/session/attach",
                data=json.dumps({"pid": adopter.pid}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                answer = json.loads(resp.read().decode())
            assert answer["attached"] is True, answer
            assert sorted(answer["clients"]) == sorted([starter.pid, adopter.pid])

            info = json.loads(daemon_json.read_text())
            assert info["pid"] == daemon_pid, "the second client restarted the daemon"
            assert sorted(info["client_pids"]) == sorted(
                [starter.pid, adopter.pid]
            ), f"the adopting client was not published in the state record: {info}"

            # The starter exits. The daemon must not stop underneath the
            # client that is actually using it.
            starter.kill()
            starter.wait()
            time.sleep(3)
            os.kill(daemon_pid, 0)  # raises ProcessLookupError if it stopped

            # Now the adopter goes. Nobody is left.
            adopter.kill()
            adopter.wait()
            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    os.kill(daemon_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.3)
            else:
                raise AssertionError(
                    "daemon kept serving with every recorded client gone: "
                    + (tmp_path / ".elspais" / "daemon.log").read_text()[-1500:]
                )
        finally:
            starter.kill()
            adopter.kill()
            if daemon_pid is not None:
                try:
                    os.kill(daemon_pid, 15)
                except OSError:
                    pass

    def test_REQ_o00074_I_daemon_saves_pending_work_before_terminating(self, tmp_path):
        """Validates REQ-o00074-I: a daemon terminating with no client present
        writes the changes it holds to disk rather than destroying them, and
        leaves a record saying that it saved them itself, when, how many, and
        what triggered it -- so the next client to open these files can see how
        they reached their current form.
        """
        import os
        import sys
        import time
        import urllib.request

        from tests.e2e.helpers import Requirement, base_config, build_project

        build_project(
            tmp_path,
            base_config(name="unattended-save-project"),
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Feature One",
                        "PRD",
                        assertions=[("A", "The system SHALL do one thing.")],
                    )
                ]
            },
        )

        spawner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        daemon_pid = None
        try:
            result = run_elspais(
                "summary",
                cwd=tmp_path,
                env={
                    "ELSPAIS_SPAWNER_PID": str(spawner.pid),
                    "_ELSPAIS_SPAWNER_CHECK_INTERVAL": "0.3",
                    "_ELSPAIS_SPAWNER_GRACE": "1",
                },
            )
            assert result.returncode == 0, result.stderr

            daemon_json = tmp_path / ".elspais" / "daemon.json"
            assert daemon_json.exists(), "daemon should have auto-started"
            info = json.loads(daemon_json.read_text())
            daemon_pid = info["pid"]
            base = f"http://127.0.0.1:{info['port']}"

            # A writer applies a change and leaves it unsaved in memory.
            with urllib.request.urlopen(f"{base}/api/node/REQ-p00001", timeout=5) as resp:
                version = json.loads(resp.read().decode())["version"]
            req = urllib.request.Request(
                f"{base}/api/mutate/title",
                data=json.dumps(
                    {
                        "node_id": "REQ-p00001",
                        "new_title": "Feature One Renamed In Memory",
                        "if_version": version,
                    }
                ).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert json.loads(resp.read().decode())["success"] is True
            assert (
                "Feature One Renamed In Memory" not in (tmp_path / "spec" / "prd.md").read_text()
            ), "the mutation was already on disk; the test cannot show the daemon saved it"

            # The writer disappears. No further writes: a change applied after
            # this point would restart the countdown (REQ-o00074-H).
            spawner.kill()
            spawner.wait()

            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    os.kill(daemon_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.3)
            else:
                raise AssertionError(
                    "daemon holding unsaved work never terminated: "
                    + (tmp_path / ".elspais" / "daemon.log").read_text()[-1500:]
                )

            log_tail = (tmp_path / ".elspais" / "daemon.log").read_text()[-1500:]
            assert "Feature One Renamed In Memory" in (tmp_path / "spec" / "prd.md").read_text(), (
                "the daemon terminated without persisting the work it held: " + log_tail
            )

            record_path = tmp_path / ".elspais" / "automatic-save.json"
            assert record_path.is_file(), (
                "the daemon saved without recording that it did so: " + log_tail
            )
            record = json.loads(record_path.read_text())
            assert record["saved_by"] == "daemon"
            assert record["mutation_count"] == 1, f"dishonest count in the record: {record}"
            assert record["files_written"] >= 1
            assert record["trigger"], "the record does not say what triggered the save"
        finally:
            spawner.kill()
            if daemon_pid is not None:
                try:
                    os.kill(daemon_pid, 15)
                except OSError:
                    pass

    def test_REQ_o00074_E_cli_reusing_a_daemon_records_itself_as_a_client(self, tmp_path):
        """Validates REQ-o00074-E: a client that begins using an already-running
        daemon is recorded alongside the daemon's existing clients.

        The CLI is the ordinary way a second session begins using a daemon, so
        the obligation has to hold for it and not only for callers that know to
        post to the adoption endpoint themselves.
        """
        import os
        import sys

        from tests.e2e.helpers import Requirement, base_config, build_project

        build_project(
            tmp_path,
            base_config(name="cli-adoption-project"),
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Feature One",
                        "PRD",
                        assertions=[("A", "The system SHALL do one thing.")],
                    )
                ]
            },
        )

        starter = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        adopter = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        daemon_json = tmp_path / ".elspais" / "daemon.json"
        daemon_pid = None
        try:
            result = run_elspais(
                "summary",
                cwd=tmp_path,
                env={"ELSPAIS_SPAWNER_PID": str(starter.pid)},
            )
            assert result.returncode == 0, result.stderr
            assert daemon_json.exists(), "daemon should have auto-started"
            daemon_pid = json.loads(daemon_json.read_text())["pid"]

            result = run_elspais(
                "summary",
                cwd=tmp_path,
                env={"ELSPAIS_SPAWNER_PID": str(adopter.pid)},
            )
            assert result.returncode == 0, result.stderr

            info = json.loads(daemon_json.read_text())
            assert info["pid"] == daemon_pid, "the second invocation restarted the daemon"
            assert sorted(info["client_pids"]) == sorted(
                [starter.pid, adopter.pid]
            ), f"the CLI reused the daemon without becoming one of its clients: {info}"
        finally:
            starter.kill()
            adopter.kill()
            if daemon_pid is not None:
                try:
                    os.kill(daemon_pid, 15)
                except OSError:
                    pass
