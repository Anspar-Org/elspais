"""Tests for --mode associate in elspais validate.

Tests REQ-p00005-A: cross-repo references with configurable namespace prefixes.
Tests REQ-p00002-B: detect and report hierarchy violations including orphaned requirements.

In associate mode, validate suppresses hierarchy.orphan warnings for requirements
whose Implements target is in an external (core) repo that was not loaded. This
is detected via graph.broken_references() — a broken reference means the target
lives outside the loaded graph.
"""

import argparse
import os
import subprocess

import pytest


def _clean_git_env() -> dict[str, str]:
    """Return environment with GIT_DIR/GIT_WORK_TREE removed for test isolation."""
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def associate_repo(tmp_path):
    """Create a temporary git repository configured as an associated project.

    The repo contains:
    - REQ-p00010: A PRD requirement (should never be flagged as orphan).
    - REQ-d00020: A DEV requirement that Implements REQ-p00001 (cross-repo).
      Since the core repo is not loaded, this creates a broken reference.
      In associate mode this orphan warning should be suppressed.
    - REQ-d00030: A DEV requirement with NO Implements (truly orphaned).
      This should always be flagged as orphan in any mode.
    """
    env = _clean_git_env()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, env=env, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )

    # Create elspais config for an associated project
    config_file = tmp_path / ".elspais.toml"
    config_file.write_text(
        """\
[project]
name = "test-associated"
type = "associated"

[core]
path = "../nonexistent-core"

[directories]
spec = "spec"

[patterns]
prefix = "REQ"

[rules.hierarchy]
cross_repo_implements = true
allowed_implements = [
    "dev -> ops, prd",
    "ops -> prd",
]
"""
    )

    # Create spec directory
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    # Create spec file with three requirements
    spec_file = spec_dir / "requirements.md"
    spec_file.write_text(
        """\
# Associated Project Requirements

## REQ-p00010: Top-Level PRD Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

This is a PRD requirement. It should never be flagged as orphan.

## Assertions

A. The system SHALL exist.

*End* *Top-Level PRD Requirement* | **Hash**: 00000001

---

## REQ-d00020: Cross-Repo DEV Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

This implements a core-repo requirement. Since core is not loaded,
the reference will be broken. Associate mode should suppress the
orphan warning for this.

## Assertions

A. The system SHALL implement cross-repo feature.

*End* *Cross-Repo DEV Requirement* | **Hash**: 00000002

---

## REQ-d00030: Truly Orphaned DEV Requirement

**Level**: DEV | **Status**: Active | **Implements**: -

This has no parent at all. It should always be flagged as orphan.

## Assertions

A. The system SHALL be orphaned.

*End* *Truly Orphaned DEV Requirement* | **Hash**: 00000003

---
""",
        encoding="utf-8",
    )

    # Commit initial state
    subprocess.run(["git", "add", "."], cwd=tmp_path, env=env, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )

    return tmp_path


def _make_validate_args(repo_path, mode="associate"):
    """Build an argparse.Namespace for validate.run() with the given mode."""
    return argparse.Namespace(
        spec_dir=repo_path / "spec",
        config=repo_path / ".elspais.toml",
        fix=False,
        dry_run=False,
        skip_rule=None,
        json=False,
        quiet=False,
        export=False,
        mode=mode,
        canonical_root=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAssociateModeOrphanSuppression:
    """Tests for --mode associate orphan suppression behaviour.

    Validates REQ-p00005-A: cross-repo references with configurable namespace prefixes.
    Validates REQ-p00002-B: detect and report hierarchy violations including orphaned
    requirements.
    """

    def test_REQ_p00005_A_associate_mode_suppresses_orphan_for_cross_repo_ref(
        self, associate_repo, capsys
    ):
        """Associate mode suppresses orphan warning for requirement with broken cross-repo ref.

        REQ-d00020 implements REQ-p00001 (core repo). Since core is not loaded,
        the reference is broken. In associate mode, the orphan warning for
        REQ-d00020 should be suppressed because graph.broken_references()
        identifies it as having an external parent.
        """
        from elspais.commands.validate import run

        args = _make_validate_args(associate_repo, mode="associate")
        run(args)

        captured = capsys.readouterr()
        stderr = captured.err

        # No hierarchy.orphan line should mention REQ-d00020
        orphan_lines = [line for line in stderr.splitlines() if "hierarchy.orphan" in line]
        orphan_ids = [line for line in orphan_lines if "REQ-d00020" in line]
        assert orphan_ids == [], (
            f"REQ-d00020 should not be flagged as orphan in associate mode, "
            f"but got: {orphan_ids}"
        )

    def test_REQ_p00002_B_associate_mode_still_flags_truly_orphaned(self, associate_repo, capsys):
        """Associate mode still flags requirements with no parent at all.

        REQ-d00030 has Implements: - (no parent). Even in associate mode, it
        should be flagged as orphan because it has no broken reference — it
        genuinely has no parent anywhere.
        """
        from elspais.commands.validate import run

        args = _make_validate_args(associate_repo, mode="associate")
        run(args)

        captured = capsys.readouterr()
        stderr = captured.err

        # REQ-d00030 should still be flagged as orphan
        orphan_lines = [line for line in stderr.splitlines() if "hierarchy.orphan" in line]
        orphan_ids_d00030 = [line for line in orphan_lines if "REQ-d00030" in line]
        assert len(orphan_ids_d00030) == 1, (
            f"REQ-d00030 should be flagged as orphan in associate mode, "
            f"got orphan lines: {orphan_lines}"
        )

    def test_REQ_p00005_A_core_mode_flags_orphan_for_cross_repo_ref(self, associate_repo, capsys):
        """Core mode does NOT suppress orphan warnings for broken cross-repo refs.

        In core mode, has_external_parent is empty, so REQ-d00020 (with its
        broken Implements: REQ-p00001) should be flagged as orphan just like
        any other parentless non-PRD requirement.
        """
        from elspais.commands.validate import run

        args = _make_validate_args(associate_repo, mode="core")
        run(args)

        captured = capsys.readouterr()
        stderr = captured.err

        # REQ-d00020 SHOULD be flagged as orphan in core mode
        orphan_lines = [line for line in stderr.splitlines() if "hierarchy.orphan" in line]
        orphan_ids_d00020 = [line for line in orphan_lines if "REQ-d00020" in line]
        assert len(orphan_ids_d00020) == 1, (
            f"REQ-d00020 should be flagged as orphan in core mode, "
            f"got orphan lines: {orphan_lines}"
        )

    def test_REQ_p00002_B_prd_requirement_never_flagged_as_orphan(self, associate_repo, capsys):
        """PRD requirements are never flagged as orphan regardless of mode.

        REQ-p00010 is PRD level with no parent. The validate logic explicitly
        skips PRD-level requirements from orphan checking.
        """
        from elspais.commands.validate import run

        args = _make_validate_args(associate_repo, mode="associate")
        run(args)

        captured = capsys.readouterr()
        stderr = captured.err

        orphan_lines = [line for line in stderr.splitlines() if "hierarchy.orphan" in line]
        orphan_ids_p00010 = [line for line in orphan_lines if "REQ-p00010" in line]
        assert orphan_ids_p00010 == [], (
            f"PRD requirement REQ-p00010 should never be flagged as orphan, "
            f"but got: {orphan_ids_p00010}"
        )
