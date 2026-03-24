"""Tests for canonical_root parameter in associate resolution functions.

Validates REQ-p00005-F: canonical_root enables worktree-aware path resolution
for associate repositories, ensuring cross-repo relative paths (using ..)
resolve from the canonical (non-worktree) repo root.
"""

from __future__ import annotations

from pathlib import Path

from elspais.associates import get_associate_spec_directories


class TestGetAssociateSpecDirectoriesCanonicalRoot:
    """Validates REQ-p00005-F: get_associate_spec_directories canonical_root handling.

    Named associate loading (config['associates']['<name>']) uses
    canonical_root for relative paths. Absolute paths are unaffected.
    """

    @staticmethod
    def _create_associate_repo(repo_dir: Path) -> None:
        """Create a minimal associate repo with .elspais.toml and spec/."""
        repo_dir.mkdir(parents=True, exist_ok=True)
        toml_content = (
            "version = 3\n"
            "[project]\n"
            'name = "test-associate"\n'
            "\n"
            "[scanning.spec]\n"
            'directories = ["spec"]\n'
        )
        (repo_dir / ".elspais.toml").write_text(toml_content, encoding="utf-8")
        (repo_dir / "spec").mkdir(exist_ok=True)

    def test_REQ_p00005_F_relative_path_resolves_from_canonical_root(self, tmp_path: Path):
        """Relative associate path resolves from canonical_root."""
        canonical_root = tmp_path / "canonical"
        canonical_root.mkdir()

        # Create associate repo relative to canonical_root
        associate_repo = canonical_root / "associates" / "test-repo"
        self._create_associate_repo(associate_repo)

        # base_path is a worktree (different from canonical_root)
        worktree = tmp_path / "worktrees" / "feature-x"
        worktree.mkdir(parents=True)

        config: dict = {
            "associates": {
                "test-repo": {"path": "associates/test-repo", "namespace": "TST"},
            },
        }

        spec_dirs, errors = get_associate_spec_directories(
            config, base_path=canonical_root
        )

        assert len(errors) == 0
        assert len(spec_dirs) == 1
        assert spec_dirs[0] == canonical_root / "associates" / "test-repo" / "spec"

    def test_REQ_p00005_F_absolute_path_ignores_canonical_root(self, tmp_path: Path):
        """Absolute associate path is used directly regardless of canonical_root."""
        canonical_root = tmp_path / "canonical"
        canonical_root.mkdir()

        # Create associate repo at an absolute location
        associate_repo = tmp_path / "absolute" / "associate"
        self._create_associate_repo(associate_repo)

        worktree = tmp_path / "worktrees" / "feature-x"
        worktree.mkdir(parents=True)

        config: dict = {
            "associates": {
                "associate": {"path": str(associate_repo), "namespace": "ABS"},
            },
        }

        spec_dirs, errors = get_associate_spec_directories(
            config, base_path=worktree
        )

        assert len(errors) == 0
        assert len(spec_dirs) == 1
        assert spec_dirs[0] == associate_repo / "spec"

    def test_REQ_p00005_F_none_canonical_root_uses_base_path_for_relative(self, tmp_path: Path):
        """When canonical_root is None, absolute paths still resolve correctly."""
        base = tmp_path / "base"
        base.mkdir()

        associate_repo = tmp_path / "associates" / "test-repo"
        self._create_associate_repo(associate_repo)

        config: dict = {
            "associates": {
                "test-repo": {"path": str(associate_repo), "namespace": "TST"},
            },
        }

        # Use absolute path in config to guarantee it resolves correctly
        # when canonical_root is None
        spec_dirs, errors = get_associate_spec_directories(
            config, base_path=base
        )

        assert len(errors) == 0
        assert len(spec_dirs) == 1
        assert spec_dirs[0] == associate_repo / "spec"
