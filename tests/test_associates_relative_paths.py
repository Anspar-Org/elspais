"""Tests for how an associate declaration's path is resolved.

Validates REQ-d00202-O: a relative associate path is resolved against the
root of the working tree of the repository that declares it (``base_path``),
and an absolute path is used as written; the user docs say so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.associates import get_associate_spec_directories


class TestAssociatePathResolution:
    """Validates REQ-d00202-O: get_associate_spec_directories path resolution."""

    @staticmethod
    def _create_associate_repo(repo_dir: Path, namespace: str = "TST") -> None:
        """Create a minimal associate repo with .elspais.toml and spec/.

        The repo declares the namespace its declaration names: a declaration
        naming a namespace the repository does not declare is a federation
        error, and these tests are about path resolution, not that error.
        """
        repo_dir.mkdir(parents=True, exist_ok=True)
        toml_content = (
            "version = 5\n"
            "[project]\n"
            'name = "test-associate"\n'
            f'namespace = "{namespace}"\n'
            "\n"
            "[scanning.spec]\n"
            'directories = ["spec"]\n'
        )
        (repo_dir / ".elspais.toml").write_text(toml_content, encoding="utf-8")
        (repo_dir / "spec").mkdir(exist_ok=True)

    # Verifies: REQ-d00202-O
    def test_REQ_d00202_O_relative_path_resolves_from_declaring_root(self, tmp_path: Path):
        """A relative associate path resolves against the declaring root."""
        declaring_root = tmp_path / "core"
        declaring_root.mkdir()
        self._create_associate_repo(declaring_root / "associates" / "test-repo")

        config: dict = {
            "associates": {
                "test-repo": {"path": "associates/test-repo", "namespace": "TST"},
            },
        }

        spec_dirs, errors = get_associate_spec_directories(config, base_path=declaring_root)

        assert errors == []
        assert spec_dirs == [declaring_root / "associates" / "test-repo" / "spec"]

    # Verifies: REQ-d00202-O
    def test_REQ_d00202_O_absolute_path_is_used_as_written(self, tmp_path: Path):
        """An absolute associate path is used directly, whatever the declaring root."""
        associate_repo = tmp_path / "absolute" / "associate"
        self._create_associate_repo(associate_repo, namespace="ABS")

        declaring_root = tmp_path / "worktrees" / "feature-x"
        declaring_root.mkdir(parents=True)

        config: dict = {
            "associates": {
                "associate": {"path": str(associate_repo), "namespace": "ABS"},
            },
        }

        spec_dirs, errors = get_associate_spec_directories(config, base_path=declaring_root)

        assert errors == []
        assert spec_dirs == [associate_repo / "spec"]

    # Verifies: REQ-d00202-O, REQ-d00202-M
    def test_REQ_d00202_O_relative_path_is_not_read_against_another_root(self, tmp_path: Path):
        """A relative path valid only from some other directory is not found.

        The associate sits beside ``elsewhere``, not beside the declaring
        root, so resolving against the declaring root reaches nothing and
        the declaration is reported rather than silently resolved elsewhere.
        """
        self._create_associate_repo(tmp_path / "elsewhere" / "associates" / "test-repo")
        declaring_root = tmp_path / "core"
        declaring_root.mkdir()

        config: dict = {
            "associates": {
                "test-repo": {"path": "associates/test-repo", "namespace": "TST"},
            },
        }

        spec_dirs, errors = get_associate_spec_directories(config, base_path=declaring_root)

        assert spec_dirs == []
        assert len(errors) == 1
        assert str(declaring_root / "associates" / "test-repo") in errors[0]


class TestDocsStateTheResolutionFrame:
    """Validates REQ-d00202-O+P: user docs describe the rule the tool applies."""

    @pytest.mark.parametrize("topic", ["config", "git", "associate", "mcp"])
    # Verifies: REQ-d00202-O
    def test_REQ_d00202_O_docs_promise_no_canonical_root_resolution(self, topic):
        """No paragraph ties associate paths or worktrees to a canonical root."""
        from elspais.utilities.docs_loader import load_topic

        text = load_topic(topic)
        assert text, f"topic {topic!r} did not load"
        for paragraph in text.split("\n\n"):
            flat = " ".join(paragraph.split()).lower()
            if "canonical" not in flat:
                continue
            assert "worktree" not in flat and "associate" not in flat, paragraph

    # Verifies: REQ-d00202-O+P
    def test_REQ_d00202_P_config_docs_state_the_declaring_root_rule(self):
        from elspais.utilities.docs_loader import load_topic

        flat = " ".join(load_topic("config").split())
        assert "resolves against the root of the working tree that declares it" in flat
        assert "' resolved against " in flat
