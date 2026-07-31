# Verifies: REQ-p00004-J
"""Tests that AppState's mtime snapshot covers config files.

A long-running server must notice edits to .elspais.toml and
.elspais.local.toml and treat the graph as stale, so it rebuilds with
freshly re-read configuration.
"""

import os
from pathlib import Path


def _make_state(tmp_path: Path):
    from elspais.server.state import AppState

    config_path = tmp_path / ".elspais.toml"
    config_path.write_text('[project]\nname = "test"\n\n[scanning.spec]\ndirectories = ["spec"]\n')
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir(exist_ok=True)
    (spec_dir / "prd.md").write_text("# placeholder\n")

    config = {"scanning": {"spec": {"directories": ["spec"]}}}
    # Dummy graph object: snapshot/staleness logic never touches the graph.
    state = AppState(
        graph=object(),  # type: ignore[arg-type]
        repo_root=tmp_path,
        config=config,
        allowed_roots=[tmp_path],
    )
    return state, config_path


def _bump_mtime(path: Path) -> None:
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 10))


def test_not_stale_without_changes(tmp_path: Path):
    state, _ = _make_state(tmp_path)
    assert state.is_stale() is False


def test_config_edit_marks_state_stale(tmp_path: Path):
    state, config_path = _make_state(tmp_path)
    config_path.write_text(
        '[project]\nname = "renamed"\n\n[scanning.spec]\ndirectories = ["spec"]\n'
    )
    _bump_mtime(config_path)
    assert state.is_stale() is True


def test_new_local_config_marks_state_stale(tmp_path: Path):
    state, _ = _make_state(tmp_path)
    (tmp_path / ".elspais.local.toml").write_text('[project]\nname = "override"\n')
    assert state.is_stale() is True


def test_local_config_edit_marks_state_stale(tmp_path: Path):
    local = tmp_path / ".elspais.local.toml"
    local.write_text('[project]\nname = "override"\n')
    state, _ = _make_state(tmp_path)
    assert state.is_stale() is False
    local.write_text('[project]\nname = "override-2"\n')
    _bump_mtime(local)
    assert state.is_stale() is True


def test_config_delete_marks_state_stale(tmp_path: Path):
    local = tmp_path / ".elspais.local.toml"
    local.write_text('[project]\nname = "override"\n')
    state, _ = _make_state(tmp_path)
    local.unlink()
    assert state.is_stale() is True
