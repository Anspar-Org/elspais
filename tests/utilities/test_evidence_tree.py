# Verifies: REQ-d00322-D
"""Tests for the tree digest that binds an *Evidence Snapshot* to a tree."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from elspais.utilities.evidence import tree_digest

_GIT = [
    "git",
    "-c",
    "user.name=x",
    "-c",
    "user.email=x@x",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "init.defaultBranch=main",
]


def _run(repo: Path, *args: str) -> None:
    subprocess.run([*_GIT, *args], cwd=repo, check=True, capture_output=True)


def _git_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-q")
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "init")
    return repo


# Verifies: REQ-d00322-D
def test_same_tree_gives_the_same_digest(tmp_path):
    repo = _git_repo(tmp_path, {"a.txt": "x", "src/b.py": "y"})
    assert tree_digest(repo, exclude="test-evidence") == tree_digest(repo, exclude="test-evidence")


# Verifies: REQ-d00322-D
def test_editing_a_tracked_file_changes_the_digest(tmp_path):
    repo = _git_repo(tmp_path, {"a.txt": "x"})
    before = tree_digest(repo, exclude="test-evidence").digest
    (repo / "a.txt").write_text("changed")
    assert tree_digest(repo, exclude="test-evidence").digest != before


# Verifies: REQ-d00322-D
def test_digest_ignores_the_snapshot_directory(tmp_path):
    repo = _git_repo(tmp_path, {"a.txt": "x", "test-evidence/results.jsonl": "1"})
    before = tree_digest(repo, exclude="test-evidence").digest
    (repo / "test-evidence/results.jsonl").write_text("2")
    assert tree_digest(repo, exclude="test-evidence").digest == before


# Verifies: REQ-d00322-D
def test_a_staged_new_file_changes_the_digest(tmp_path):
    repo = _git_repo(tmp_path, {"a.txt": "x"})
    before = tree_digest(repo, exclude="test-evidence").digest
    (repo / "new.txt").write_text("n")
    _run(repo, "add", "new.txt")
    assert tree_digest(repo, exclude="test-evidence").digest != before


# Verifies: REQ-d00322-D
def test_an_untracked_file_is_listed_but_not_digested(tmp_path):
    repo = _git_repo(tmp_path, {"a.txt": "x"})
    before = tree_digest(repo, exclude="test-evidence").digest
    (repo / "loose.txt").write_text("n")
    after = tree_digest(repo, exclude="test-evidence")
    assert after.digest == before
    assert after.uncommitted == ("loose.txt",)


# Verifies: REQ-d00322-D
def test_uncommitted_names_edits_and_untracked_files_only(tmp_path):
    """Review Focus 3: the warning names the tree CI will not see."""
    repo = _git_repo(
        tmp_path,
        {".gitignore": "ignored.log\n", "a.txt": "x", "test-evidence/results.jsonl": "1"},
    )
    (repo / "a.txt").write_text("edited")
    (repo / "loose.txt").write_text("n")
    (repo / "ignored.log").write_text("i")
    (repo / "test-evidence/results.jsonl").write_text("2")
    (repo / "test-evidence/timings.jsonl").write_text("t")
    assert tree_digest(repo, exclude="test-evidence").uncommitted == ("a.txt", "loose.txt")


# Verifies: REQ-d00322-D
def test_a_gitignored_file_changes_nothing(tmp_path):
    repo = _git_repo(tmp_path, {".gitignore": "ignored.log\n", "a.txt": "x"})
    before = tree_digest(repo, exclude="test-evidence")
    (repo / "ignored.log").write_text("i")
    assert tree_digest(repo, exclude="test-evidence") == before
    assert before.uncommitted == ()


# Verifies: REQ-d00322-D
def test_digest_does_not_depend_on_the_location(tmp_path):
    repo = _git_repo(tmp_path, {"a.txt": "x", "src/b.py": "y"})
    elsewhere = tmp_path / "elsewhere" / "copy"
    shutil.copytree(repo, elsewhere, symlinks=True)
    assert tree_digest(elsewhere, exclude="test-evidence") == tree_digest(
        repo, exclude="test-evidence"
    )


# Verifies: REQ-d00322-D
def test_a_symlink_contributes_its_target_text(tmp_path):
    """Git records a link as its target text, so a link to a directory counts."""
    repo = _git_repo(tmp_path, {"one/a.txt": "x", "two/a.txt": "x"})
    (repo / "link").symlink_to("one")
    _run(repo, "add", "link")
    _run(repo, "commit", "-q", "-m", "link")
    before = tree_digest(repo, exclude="test-evidence").digest
    (repo / "link").unlink()
    (repo / "link").symlink_to("two")
    assert tree_digest(repo, exclude="test-evidence").digest != before


# Verifies: REQ-d00322-D
def test_a_path_git_would_quote_is_listed_unquoted_and_excluded_under_the_snapshot(tmp_path):
    repo = _git_repo(tmp_path, {"a.txt": "x", "test-evidence/r\u00e9sults.jsonl": "1"})
    (repo / "test-evidence/r\u00e9sults.jsonl").write_text("2")
    (repo / 'na\u00efve "q".txt').write_text("n")
    assert tree_digest(repo, exclude="test-evidence").uncommitted == ('na\u00efve "q".txt',)


# Verifies: REQ-d00322-D
def test_a_rename_is_listed_by_its_new_path(tmp_path):
    repo = _git_repo(tmp_path, {"old.txt": "content that git can follow\n"})
    _run(repo, "mv", "old.txt", "new.txt")
    assert tree_digest(repo, exclude="test-evidence").uncommitted == ("new.txt",)


# Verifies: REQ-d00322-D
def test_git_giving_no_answer_is_an_error_not_a_clean_tree(tmp_path):
    import subprocess as sp

    import pytest

    from elspais.utilities.git import list_uncommitted_files

    with pytest.raises(sp.CalledProcessError):
        list_uncommitted_files(tmp_path)
