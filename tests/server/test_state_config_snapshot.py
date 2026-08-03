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


def test_ensure_fresh_rebuilds_with_new_level_set(tmp_path: Path):
    """A running server's auto-refresh re-reads config, not just spec files.

    Regression test for the reported defect: after editing [levels.*] in
    .elspais.toml, the reloaded graph must reflect the new level set — a
    requirement at a freshly declared level appears without a server restart.
    """
    from elspais.server.state import AppState

    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        "[project]\n"
        'name = "cfg-reload"\n'
        'namespace = "REQ"\n'
        "\n"
        "[levels.prd]\n"
        "rank = 1\n"
        'letter = "p"\n'
        'display_name = "Product"\n'
        "implements = []\n"
    )
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "prd.md").write_text(
        "# REQ-p00001: Product requirement\n"
        "\n"
        "**Level**: PRD | **Status**: Active | **Implements**: -\n"
        "\n"
        "Body.\n"
        "\n"
        "## Assertions\n"
        "\n"
        "A. The system SHALL do the thing.\n"
        "\n"
        "*End* *Product requirement* | **Hash**: 00000000\n"
    )
    (spec_dir / "dev.md").write_text(
        "# REQ-d00001: Dev requirement\n"
        "\n"
        "**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001-A\n"
        "\n"
        "Body.\n"
        "\n"
        "## Assertions\n"
        "\n"
        "A. The implementation SHALL do the detailed thing.\n"
        "\n"
        "*End* *Dev requirement* | **Hash**: 00000000\n"
    )

    state = AppState.from_config(repo_root=tmp_path)
    assert state.graph.find_by_id("REQ-p00001") is not None
    assert state.graph.find_by_id("REQ-d00001") is None  # level undeclared

    # Declare the dev level on disk, as a user editing .elspais.toml would.
    with config_path.open("a") as f:
        f.write(
            "\n[levels.dev]\n"
            "rank = 2\n"
            'letter = "d"\n'
            'display_name = "Development"\n'
            'implements = ["prd"]\n'
        )
    _bump_mtime(config_path)
    state._last_stale_check = 0  # bypass the 1s throttle

    assert state.ensure_fresh() is True
    assert state.graph.find_by_id("REQ-d00001") is not None
    assert "dev" in state.config.get("levels", {})
