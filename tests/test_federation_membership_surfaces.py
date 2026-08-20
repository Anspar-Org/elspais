"""The viewer's membership surfaces answer for the whole federation.

A repository reached only through an associate's own declarations is as much a
member as one the invoking repo names directly.  The file-serving allowlist,
the associate spec-directory scan, and the namespace catalog the viewer styles
cross-repo badges from must all cover it.
"""

from __future__ import annotations

from pathlib import Path

from tests.federation_repos import make_repo


def _load(repo: Path) -> dict:
    from elspais.config import load_config

    return load_config(repo / ".elspais.toml")


def _chain(tmp_path: Path) -> tuple[Path, Path, Path]:
    """root -> mid -> leaf, where root never names leaf."""
    leaf = make_repo(tmp_path, "leaf", namespace="LEAF", req_id="LEAF-d00001")
    mid = make_repo(
        tmp_path,
        "mid",
        namespace="MID",
        associates={"leaf": "../leaf"},
        associate_namespaces={"leaf": "LEAF"},
        req_id="MID-d00001",
    )
    root = make_repo(
        tmp_path,
        "root",
        namespace="ROOT",
        associates={"mid": "../mid"},
        associate_namespaces={"mid": "MID"},
        req_id="ROOT-d00001",
    )
    return root, mid, leaf


# Verifies: REQ-d00202-D
def test_spec_directories_include_a_transitively_reached_repo(tmp_path: Path):
    """The scan reports the spec dir of a repo only an associate declares."""
    from elspais.associates import get_associate_spec_directories

    root, mid, leaf = _chain(tmp_path)

    spec_dirs, errors = get_associate_spec_directories(_load(root), root)

    assert errors == []
    assert set(spec_dirs) == {mid / "spec", leaf / "spec"}


# Verifies: REQ-d00203-B
def test_spec_directory_errors_name_a_transitively_reached_repo(tmp_path: Path):
    """A member reached through an associate is reported when it cannot load."""
    from elspais.associates import get_associate_spec_directories

    make_repo(
        tmp_path,
        "mid",
        namespace="MID",
        associates={"gone": "../gone"},
        associate_namespaces={"gone": "GONE"},
        req_id="MID-d00001",
    )
    root = make_repo(
        tmp_path,
        "root",
        namespace="ROOT",
        associates={"mid": "../mid"},
        associate_namespaces={"mid": "MID"},
        req_id="ROOT-d00001",
    )

    spec_dirs, errors = get_associate_spec_directories(_load(root), root)

    assert spec_dirs == [tmp_path / "mid" / "spec"]
    assert len(errors) == 1
    assert "gone" in errors[0]
    assert "does not exist" in errors[0]


# Verifies: REQ-d00202-D
def test_allowed_roots_cover_a_transitively_reached_repo(tmp_path: Path):
    """The file-serving allowlist admits every repo the federation owns."""
    from elspais.server.state import AppState

    root, mid, leaf = _chain(tmp_path)

    state = AppState.from_config(repo_root=root)

    assert leaf.resolve() in state.allowed_roots
    assert mid.resolve() in state.allowed_roots
    assert root.resolve() in state.allowed_roots


# Verifies: REQ-d00203-B
def test_namespace_catalog_includes_a_transitively_reached_repo(tmp_path: Path):
    """Every federation member's namespace gets a catalog entry."""
    from elspais.config.schema import ElspaisConfig
    from elspais.graph.factory import build_graph
    from elspais.view_model import build_namespaces

    root, _mid, _leaf = _chain(tmp_path)
    config = _load(root)
    federation = build_graph(config=config, repo_root=root)

    entries = build_namespaces(ElspaisConfig.model_validate(config), federation)

    by_code = {entry["code"]: entry for entry in entries}
    assert set(by_code) == {"ROOT", "MID", "LEAF"}
    assert by_code["ROOT"]["is_local"] is True
    assert by_code["LEAF"]["is_local"] is False
    # The catalog is what the badge styling indexes off, so a transitive
    # member needs the same resolved colors as a directly-named one.
    assert by_code["LEAF"]["bg"] and by_code["LEAF"]["text"]
    assert by_code["LEAF"]["project_name"] == "leaf"


# Verifies: REQ-d00202-D
def test_namespace_catalog_without_a_federation_uses_declarations(tmp_path: Path):
    """With no federation on hand the invoking config's own table is the source."""
    from elspais.config.schema import ElspaisConfig
    from elspais.view_model import build_namespaces

    root, _mid, _leaf = _chain(tmp_path)

    entries = build_namespaces(ElspaisConfig.model_validate(_load(root)))

    assert [entry["code"] for entry in entries] == ["ROOT", "MID"]
