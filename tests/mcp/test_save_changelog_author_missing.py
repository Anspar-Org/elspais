# Verifies: REQ-d00132-A, REQ-o00074-K, REQ-d00296-A, REQ-d00296-B
"""Tests for the author a save signs its changelog rows with.

A save touching an Active requirement owes each such requirement a
changelog row, and the row needs an author. These tests run
``persist_pending`` against a process whose own author cannot be
resolved and prove two things: a save that would have to sign a row it
cannot sign is refused before anything reaches disk, with the pending
work still in hand; and a save handed the identity a trusted proxy
supplied with the request signs with that identity and never consults
the process's own.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from elspais.mcp.daemon import read_automatic_save
from elspais.mcp.shared_state import persist_pending
from elspais.server.state import AppState

SPEC_FILE = Path("spec") / "prd-core.md"
ACTIVE_REQ = "REQ-p00001"
SUPPLIED_AUTHOR = {"name": "Bob Jones", "id": "bob@co.org"}


@pytest.fixture
def hht_project(tmp_path: Path) -> Path:
    """A throwaway copy of the hht-like fixture the save paths may write to."""
    src = Path(__file__).parent.parent / "fixtures" / "hht-like"
    dest = tmp_path / "project"
    shutil.copytree(src, dest)
    return dest


@pytest.fixture
def unresolvable_process_author(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave the process with no author of its own to sign a changelog row.

    The session's conftest pins the git author variables to a test
    identity, and the machine running the suite may hold a real one in
    ``gh`` or git config, so both routes are closed: the variables are
    removed and the raw lookup answers with nothing. The real resolver
    then raises its real error.
    """
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.setattr(
        "elspais.utilities.changelog_author._lookup_raw",
        lambda _id_source: ("", ""),
    )


@pytest.mark.usefixtures("unresolvable_process_author")
class TestSaveRefusedWhenProcessAuthorUnresolvable:
    """A save owing a changelog row nobody can sign is refused whole.

    The refusal comes before the safety branch and before any file is
    written, so the spec file, the mutation log and the automatic-save
    record are exactly as they were: the work is retained, and there is
    no record of a save that did not happen.
    """

    # Verifies: REQ-d00132-A, REQ-o00074-K
    @pytest.mark.parametrize(
        "save_kwargs",
        [
            pytest.param({"message": "retitled by the session"}, id="client"),
            pytest.param(
                {"automatic": True, "trigger": "no recorded client was running"},
                id="automatic",
            ),
        ],
    )
    def test_refusal_leaves_files_and_pending_work_untouched(
        self, hht_project: Path, save_kwargs: dict
    ):
        state = AppState.from_config(repo_root=hht_project)
        spec_path = hht_project / SPEC_FILE
        before = spec_path.read_bytes()

        state.graph.update_title(ACTIVE_REQ, "User Authentication (retitled)")
        assert len(state.graph.mutation_log) == 1

        result = persist_pending(state.shared, **save_kwargs)

        assert result["success"] is False, result
        assert result["code"] == "save_failed", result
        assert "author_name" in result["error"], result["error"]

        assert spec_path.read_bytes() == before, "a refused save changed the spec file"
        assert len(state.graph.mutation_log) == 1, "a refused save dropped the pending work"
        after = spec_path.read_text()
        assert "## Changelog" not in after
        assert "(retitled)" not in after
        assert read_automatic_save(hht_project) is None, (
            "a save that did not happen left a record of itself"
        )


@pytest.mark.usefixtures("unresolvable_process_author")
class TestSuppliedIdentitySignsTheRow:
    """An identity handed in with the request is the one the row names.

    The process author is left unresolvable for this test too, so the
    save can only succeed if the supplied identity was used and the
    process's own was never consulted.
    """

    # Verifies: REQ-d00296-A, REQ-d00296-B
    def test_row_names_the_supplied_author(self, hht_project: Path):
        state = AppState.from_config(repo_root=hht_project)
        spec_path = hht_project / SPEC_FILE

        state.graph.update_title(ACTIVE_REQ, "User Authentication (retitled)")

        result = persist_pending(
            state.shared,
            message="retitled by the session",
            author=SUPPLIED_AUTHOR,
        )

        assert result.get("success"), result
        assert len(state.graph.mutation_log) == 0, "a successful save left the work pending"
        after = spec_path.read_text()
        assert "User Authentication (retitled)" in after, "the save did not reach disk"
        assert "Bob Jones (<bob@co.org>) | retitled by the session" in after, after
