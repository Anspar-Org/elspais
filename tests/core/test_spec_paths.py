# Verifies: REQ-p00015-H, REQ-d00275-C
"""The one search for the spec file holding a requirement.

`find_spec_file_holding` answers "which file declares this id?" for every
surface that must know without a built graph. Two facts decide the answer and
both are properties of the repository being searched: where its spec files are
(REQ-d00275-C), and which of them the reader excluded (REQ-p00015-H). These
tests watch the reads themselves, because a search that opens an excluded file
and then declines to match on it has already read what it was told not to.
"""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from elspais.config import load_config
from elspais.utilities.spec_paths import find_spec_file_holding


def _write_spec_file(path: Path, req_id: str) -> None:
    """Write a spec file declaring exactly *req_id*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""\
### {req_id}: Some Requirement

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *Some Requirement* | **Hash**: ________
""",
        encoding="utf-8",
    )


def _config(tmp_path: Path, *, spec_dirs: list[str], global_skip: list[str]) -> dict:
    """A project declaring *spec_dirs* and excluding *global_skip*."""
    listed = "[" + ", ".join(f'"{value}"' for value in spec_dirs) + "]"
    skipped = "[" + ", ".join(f'"{value}"' for value in global_skip) + "]"
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        f"""\
[project]
name = "test-spec-paths"
namespace = "REQ"

[scanning]
skip = {skipped}

[scanning.spec]
directories = {listed}
""",
        encoding="utf-8",
    )
    return load_config(config_path)


class _OpenRecorder:
    """Records every path opened while it is installed."""

    def __init__(self) -> None:
        self.opened: set[str] = set()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_path_open = Path.open
        real_builtin_open = builtins.open
        opened = self.opened

        def record_path_open(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            opened.add(str(Path(self).resolve()))
            return real_path_open(self, *args, **kwargs)

        def record_builtin_open(file, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            if isinstance(file, (str, Path)):
                opened.add(str(Path(file).resolve()))
            return real_builtin_open(file, *args, **kwargs)

        monkeypatch.setattr(Path, "open", record_path_open)
        monkeypatch.setattr(builtins, "open", record_builtin_open)


class TestFindingTheFileHoldingARequirement:
    """Where a repository keeps its requirements, and which it has excluded."""

    # Verifies: REQ-p00015-H
    def test_a_requirement_declared_only_in_an_excluded_file_is_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The excluded file is never opened, so what it declares is unknown.

        The id searched for is declared nowhere else, so a search that opened
        the excluded file would both read it and answer with it. Reaching the
        kept file is what shows the search ran at all.
        """
        _write_spec_file(tmp_path / "spec" / "reqs.md", "REQ-p00001")
        _write_spec_file(tmp_path / "spec" / "secret.md", "REQ-p00009")
        config = _config(tmp_path, spec_dirs=["spec"], global_skip=["secret.md"])

        recorder = _OpenRecorder()
        recorder.install(monkeypatch)
        try:
            found = find_spec_file_holding("REQ-p00009", tmp_path, config)
        finally:
            monkeypatch.undo()

        assert found is None, (
            "A requirement declared only in an excluded file is not the tool's business"
        )
        assert str((tmp_path / "spec" / "reqs.md").resolve()) in recorder.opened, (
            "The kept spec file was read, so the search really walked the spec directory"
        )
        assert str((tmp_path / "spec" / "secret.md").resolve()) not in recorder.opened, (
            "An excluded spec file must never be opened"
        )

    # Verifies: REQ-d00275-C
    def test_the_search_reads_the_directories_the_project_declares(self, tmp_path: Path) -> None:
        """A project keeping requirements outside `spec/` is searched correctly.

        The decoy lives in a `spec/` this project never declared and holds the
        same id, so a search fixed on `spec/` answers with it -- the wrong file
        in a directory the project did not offer for scanning.
        """
        _write_spec_file(tmp_path / "requirements" / "reqs.md", "REQ-p00001")
        _write_spec_file(tmp_path / "spec" / "decoy.md", "REQ-p00001")
        config = _config(tmp_path, spec_dirs=["requirements"], global_skip=[])

        found = find_spec_file_holding("REQ-p00001", tmp_path, config)

        assert found == tmp_path / "requirements" / "reqs.md", (
            f"The declared directory holds the requirement; the search answered {found}"
        )

    # Verifies: REQ-d00275-C
    def test_an_id_no_declared_directory_declares_is_not_found(self, tmp_path: Path) -> None:
        """Nothing outside the declared directories answers the search."""
        _write_spec_file(tmp_path / "requirements" / "reqs.md", "REQ-p00001")
        _write_spec_file(tmp_path / "spec" / "decoy.md", "REQ-p00009")
        config = _config(tmp_path, spec_dirs=["requirements"], global_skip=[])

        assert find_spec_file_holding("REQ-p00001", tmp_path, config) is not None
        assert find_spec_file_holding("REQ-p00009", tmp_path, config) is None, (
            "An undeclared directory is not searched, however spec-shaped it looks"
        )
