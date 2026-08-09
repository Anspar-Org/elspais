# Verifies: REQ-d00253-A
"""Tests for the [federation] config table."""

import re
import threading
from pathlib import Path

import pytest

from elspais.config.schema import ElspaisConfig, FederationConfig
from tests.federation_repos import make_repo


def test_federation_defaults_are_false():
    cfg = ElspaisConfig()
    assert cfg.federation.write_associates is False
    assert cfg.federation.index_associates is False


def test_federation_parses_from_dict():
    cfg = ElspaisConfig.model_validate(
        {"federation": {"write_associates": True, "index_associates": True}}
    )
    assert cfg.federation.write_associates is True
    assert cfg.federation.index_associates is True


def test_federation_dump_structure():
    dumped = ElspaisConfig().model_dump(by_alias=True)
    assert dumped["federation"] == {
        "write_associates": False,
        "index_associates": False,
    }


def test_federation_rejects_unknown_field():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FederationConfig(bogus=True)


# ─────────────────────────────────────────────────────────────────────────────
# Transitive federation planning
#
# These exercise `elspais.graph.federation_plan.plan_federation()`, which walks
# the `[associates.*]` declarations of every reachable repository rather than
# only the root's.  The planner module is imported *inside* each test so that
# its absence cannot break collection of the [federation] table tests above.
# ─────────────────────────────────────────────────────────────────────────────


def _load(repo: Path) -> dict:
    from elspais.config import load_config

    return load_config(repo / ".elspais.toml")


def _plan(repo: Path, **kwargs):
    """Call plan_federation for `repo`, importing the planner lazily."""
    from elspais.graph.federation_plan import plan_federation

    return plan_federation(_load(repo), repo, **kwargs)


def _plan_with_deadline(repo: Path, timeout: float = 20.0, **kwargs):
    """Run plan_federation on a daemon thread so a cycle-induced hang fails.

    Returns the planner's result, or re-raises whatever it raised.  If the call
    has not returned within `timeout`, the test fails rather than wedging the
    whole session.
    """
    box: dict[str, object] = {}

    def run():
        try:
            box["value"] = _plan(repo, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        pytest.fail(f"plan_federation did not terminate within {timeout}s")
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["value"]


def _chain(base: Path, names: list[str]) -> Path:
    """Build a linear A -> B -> C ... federation; return the root repo path."""
    for index, name in enumerate(names):
        successor = names[index + 1] if index + 1 < len(names) else None
        make_repo(
            base,
            name,
            associates={successor: f"../{successor}"} if successor else None,
            req_id=f"REQ-d0000{index + 1}",
        )
    return base / names[0]


class TestTransitiveResolution:
    """Validates REQ-d00202-D, REQ-d00203-B."""

    @pytest.mark.parametrize("names", [["a1", "b1", "c1"], ["a2", "b2", "c2", "d2"]])
    # Verifies: REQ-d00202-D
    def test_REQ_d00202_D_chain_resolves_to_every_depth(self, tmp_path, names):
        """A->B->C (and one link deeper) yields one entry per repo, root first."""
        root = _chain(tmp_path, names)

        planned = _plan(root)

        assert [entry.name for entry in planned] == names
        assert planned[0].repo_root == root.resolve()
        assert all(entry.config is not None for entry in planned)
        assert all(entry.error is None for entry in planned)

    # Verifies: REQ-d00203-B
    def test_REQ_d00203_B_associate_config_is_loaded(self, tmp_path):
        """Each associate's own config is loaded, so its declarations are found."""
        root = _chain(tmp_path, ["ra", "rb", "rc"])

        planned = _plan(root)
        by_name = {entry.name: entry for entry in planned}

        # 'rc' is only reachable by reading 'rb's config -- proof it was loaded.
        assert set(by_name) == {"ra", "rb", "rc"}
        assert by_name["rb"].config["project"]["name"] == "rb"
        assert by_name["rc"].repo_root == (tmp_path / "rc").resolve()

    # Verifies: REQ-d00202-D
    def test_REQ_d00202_D_declaration_path_is_inclusive_from_root(self, tmp_path):
        """declaration_path runs root-first and includes the repo itself."""
        root = _chain(tmp_path, ["pa", "pb", "pc"])

        by_name = {entry.name: entry for entry in _plan(root)}

        assert by_name["pa"].declaration_path == ("pa",)
        assert by_name["pb"].declaration_path == ("pa", "pb")
        assert by_name["pc"].declaration_path == ("pa", "pb", "pc")

    # Verifies: REQ-d00202-D
    def test_REQ_d00202_D_depth_first_declaration_order(self, tmp_path):
        """A branch is fully expanded before the next sibling declaration."""
        make_repo(tmp_path, "leaf", req_id="REQ-d00004")
        make_repo(tmp_path, "mid", associates={"leaf": "../leaf"}, req_id="REQ-d00003")
        make_repo(tmp_path, "sib", req_id="REQ-d00002")
        root = make_repo(
            tmp_path,
            "top",
            associates={"mid": "../mid", "sib": "../sib"},
            req_id="REQ-d00001",
        )

        assert [entry.name for entry in _plan(root)] == ["top", "mid", "leaf", "sib"]


class TestCycleDetection:
    """Validates REQ-d00202-E."""

    # Verifies: REQ-d00202-E
    def test_REQ_d00202_E_self_cycle_raises(self, tmp_path):
        """A repo declaring itself is a cycle, reported and terminating."""
        from elspais.graph.federation_plan import FederationCycleError

        root = make_repo(tmp_path, "solo", associates={"solo": "."})

        with pytest.raises(FederationCycleError) as excinfo:
            _plan_with_deadline(root)

        assert "solo" in str(excinfo.value)

    @pytest.mark.parametrize(
        "names",
        [["ca", "cb"], ["da", "db", "dc"]],
        ids=["two-repo-cycle", "three-repo-cycle"],
    )
    # Verifies: REQ-d00202-E
    def test_REQ_d00202_E_cycle_names_the_declaration_path(self, tmp_path, names):
        """The last repo declares the root back; the message names the path in order."""
        from elspais.graph.federation_plan import FederationCycleError

        for index, name in enumerate(names):
            successor = names[(index + 1) % len(names)]
            make_repo(
                tmp_path,
                name,
                associates={successor: f"../{successor}"},
                req_id=f"REQ-d0000{index + 1}",
            )
        root = tmp_path / names[0]

        with pytest.raises(FederationCycleError) as excinfo:
            _plan_with_deadline(root)

        message = str(excinfo.value)
        positions = [message.find(name) for name in names]
        assert all(pos >= 0 for pos in positions), f"missing repo name in: {message}"
        assert positions == sorted(positions), f"path out of order in: {message}"


class TestDiamondConvergence:
    """Validates REQ-d00202-F."""

    # Verifies: REQ-d00202-F
    def test_REQ_d00202_F_shared_associate_appears_once(self, tmp_path):
        """A declares B and C; both declare D. D resolves to exactly one entry."""
        shared = make_repo(tmp_path, "shared", req_id="REQ-d00004")
        make_repo(tmp_path, "left", associates={"shared": "../shared"}, req_id="REQ-d00002")
        make_repo(tmp_path, "right", associates={"shared": "../shared"}, req_id="REQ-d00003")
        root = make_repo(
            tmp_path,
            "apex",
            associates={"left": "../left", "right": "../right"},
            req_id="REQ-d00001",
        )

        planned = _plan(root)

        matches = [e for e in planned if e.repo_root == shared.resolve()]
        assert len(matches) == 1, [e.name for e in planned]
        assert len(planned) == 4
        assert all(entry.error is None for entry in planned)


class TestRepositoryIdentity:
    """Validates REQ-d00202-G."""

    # Verifies: REQ-d00202-G
    def test_REQ_d00202_G_shared_git_origin_is_one_repo(self, tmp_path):
        """Two distinct directories carrying the same origin URL are one entry."""
        origin = "https://example.com/shared-lib.git"
        copy_a = make_repo(tmp_path, "libA", origin=origin, req_id="REQ-d00002")
        copy_b = make_repo(tmp_path, "libB", origin=origin, req_id="REQ-d00003")
        root = make_repo(
            tmp_path,
            "consumer",
            associates={"libA": "../libA", "libB": "../libB"},
            req_id="REQ-d00001",
        )

        planned = _plan(root)

        assert copy_a.resolve() != copy_b.resolve()
        assert [e.name for e in planned] == ["consumer", "libA"]
        # The identity is derived from the origin (the planner may normalize the
        # URL form); what matters is that the origin was detected at all.
        assert planned[1].git_origin is not None
        assert "example.com/shared-lib" in planned[1].git_origin

    # Verifies: REQ-d00202-G
    def test_REQ_d00202_G_originless_repos_stay_distinct(self, tmp_path):
        """Without an origin, identity falls back to the resolved real path."""
        make_repo(tmp_path, "plainA", req_id="REQ-d00002")
        make_repo(tmp_path, "plainB", req_id="REQ-d00003")
        root = make_repo(
            tmp_path,
            "host",
            associates={"plainA": "../plainA", "plainB": "../plainB"},
            req_id="REQ-d00001",
        )

        planned = _plan(root)

        assert [e.name for e in planned] == ["host", "plainA", "plainB"]
        assert all(entry.git_origin is None for entry in planned)


_BROKEN_TOML = "this is not = = toml [[[\n"
_INVALID_TOML = "version = 3\n\n[levels.prd]\nrank = 1\nimplements = []\n"


def _federation_with_bad_associate(tmp_path: Path, kind: str) -> tuple[Path, Path]:
    """Root declares a good associate and a bad one; returns (root, bad_path)."""
    make_repo(tmp_path, "good", req_id="REQ-d00002")
    if kind == "missing":
        bad_path = tmp_path / "absent"
    elif kind == "unparseable":
        bad_path = make_repo(tmp_path, "broken", config_text=_BROKEN_TOML, req_id="REQ-d00003")
    else:
        bad_path = make_repo(tmp_path, "invalid", config_text=_INVALID_TOML, req_id="REQ-d00003")
    root = make_repo(
        tmp_path,
        "consumer",
        associates={"good": "../good", "bad": f"../{bad_path.name}"},
        req_id="REQ-d00001",
    )
    return root, bad_path


class TestLoadFailureReporting:
    """Validates REQ-d00202-I, REQ-d00203-C, REQ-d00203-D."""

    @pytest.mark.parametrize("kind", ["missing", "unparseable", "invalid"])
    # Verifies: REQ-d00202-I, REQ-d00203-C
    def test_REQ_d00202_I_bad_associate_is_reported_not_dropped(self, tmp_path, kind):
        """The bad repo survives in the plan with config=None and a reason."""
        root, bad_path = _federation_with_bad_associate(tmp_path, kind)

        planned = _plan(root)
        by_name = {entry.name: entry for entry in planned}

        assert set(by_name) == {"consumer", "good", "bad"}
        bad = by_name["bad"]
        assert bad.config is None
        assert bad.error, "load failure must carry a human-readable reason"
        assert str(bad_path) in bad.error or bad_path.name in bad.error
        # The rest of the federation still resolves.
        assert by_name["good"].config is not None
        assert by_name["good"].error is None

    @pytest.mark.parametrize("kind", ["missing", "unparseable", "invalid"])
    # Verifies: REQ-d00203-D
    def test_REQ_d00203_D_strict_raises_on_load_failure(self, tmp_path, kind):
        """strict=True turns the same soft report into a hard failure."""
        from elspais.graph.federated import FederationError

        root, bad_path = _federation_with_bad_associate(tmp_path, kind)

        with pytest.raises(FederationError) as excinfo:
            _plan(root, strict=True)

        message = str(excinfo.value)
        assert str(bad_path) in message or bad_path.name in message


class TestCrossRepoIdentifierCollision:
    """Validates REQ-d00202-H."""

    # Verifies: REQ-d00202-H
    def test_REQ_d00202_H_duplicate_id_across_repos_raises(self, tmp_path):
        """Two federated repos defining the same canonical ID is a hard error."""
        from elspais.graph.factory import build_graph
        from elspais.graph.federated import FederationError

        make_repo(tmp_path, "libcore", namespace="REQ", req_id="REQ-d00001")
        root = make_repo(
            tmp_path,
            "appmain",
            namespace="REQ",
            associates={"libcore": "../libcore"},
            req_id="REQ-d00001",
        )

        with pytest.raises(FederationError) as excinfo:
            build_graph(config=_load(root), repo_root=root)

        message = str(excinfo.value)
        assert "REQ-d00001" in message
        assert "appmain" in message
        assert "libcore" in message


class TestDuplicateNameCollision:
    """Validates REQ-d00202-J.

    ``FederatedGraph`` keys its repos by name, so two DIFFERENT repositories
    arriving under one declared name would silently shadow each other: the
    loser's graph is never yielded, while ``find_by_id`` still routes its IDs
    to the winner and returns None.  TOML's duplicate-key rule prevented this
    under root-only resolution; transitive resolution removes that guarantee.
    """

    # Verifies: REQ-d00202-J
    def test_REQ_d00202_J_two_repos_under_one_name_raise(self, tmp_path):
        """Distinct repos declared as 'core' at different depths is an error."""
        from elspais.graph.federated import FederationError

        near = make_repo(
            tmp_path,
            "coreX",
            origin="https://example.com/core-x.git",
            req_id="REQ-d00003",
        )
        far = make_repo(
            tmp_path,
            "coreY",
            origin="https://example.com/core-y.git",
            req_id="REQ-d00004",
        )
        make_repo(tmp_path, "mid", associates={"core": "../coreY"}, req_id="REQ-d00002")
        root = make_repo(
            tmp_path,
            "top",
            associates={"core": "../coreX", "mid": "../mid"},
            req_id="REQ-d00001",
        )

        with pytest.raises(FederationError) as excinfo:
            _plan(root)

        message = str(excinfo.value)
        # Both repositories must be identified by path -- naming only the
        # surviving one would leave the shadowed repo invisible.
        assert str(near.resolve()) in message, message
        assert str(far.resolve()) in message, message
        # ...and the declaration chain that reached each, which is the only
        # thing distinguishing the two 'core' declarations from one another.
        # Ordering is pinned; the separator glyph is not.
        assert re.search(r"top\W+core", message), message
        assert re.search(r"top\W+mid\W+core", message), message

    # Verifies: REQ-d00202-J
    def test_REQ_d00202_J_same_repo_under_one_name_is_not_a_collision(self, tmp_path):
        """An ordinary diamond re-declaring one repo under one name is fine.

        Identity dedupe must skip the second arrival rather than trip the
        duplicate-name guard; without this the guard would reject every
        legitimate shared associate.
        """
        shared = make_repo(
            tmp_path,
            "shared",
            origin="https://example.com/shared.git",
            req_id="REQ-d00003",
        )
        make_repo(tmp_path, "mid", associates={"core": "../shared"}, req_id="REQ-d00002")
        root = make_repo(
            tmp_path,
            "top",
            associates={"core": "../shared", "mid": "../mid"},
            req_id="REQ-d00001",
        )

        planned = _plan(root)

        assert [entry.name for entry in planned] == ["top", "core", "mid"]
        assert len([e for e in planned if e.repo_root == shared.resolve()]) == 1
