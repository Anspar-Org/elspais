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
        make_repo(tmp_path, "leaf")
        make_repo(tmp_path, "mid", associates={"leaf": "../leaf"})
        make_repo(tmp_path, "sib")
        root = make_repo(
            tmp_path,
            "top",
            associates={"mid": "../mid", "sib": "../sib"},
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
        shared = make_repo(tmp_path, "shared")
        make_repo(tmp_path, "left", associates={"shared": "../shared"})
        make_repo(tmp_path, "right", associates={"shared": "../shared"})
        root = make_repo(
            tmp_path,
            "apex",
            associates={"left": "../left", "right": "../right"},
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
        copy_a = make_repo(tmp_path, "libA", origin=origin)
        copy_b = make_repo(tmp_path, "libB", origin=origin)
        root = make_repo(
            tmp_path,
            "consumer",
            associates={"libA": "../libA", "libB": "../libB"},
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
        make_repo(tmp_path, "plainA")
        make_repo(tmp_path, "plainB")
        root = make_repo(
            tmp_path,
            "host",
            associates={"plainA": "../plainA", "plainB": "../plainB"},
        )

        planned = _plan(root)

        assert [e.name for e in planned] == ["host", "plainA", "plainB"]
        assert all(entry.git_origin is None for entry in planned)


_BROKEN_TOML = "this is not = = toml [[[\n"
_INVALID_TOML = "version = 3\n\n[levels.prd]\nrank = 1\nimplements = []\n"


def _federation_with_bad_associate(tmp_path: Path, kind: str) -> tuple[Path, Path]:
    """Root declares a good associate and a bad one; returns (root, bad_path)."""
    make_repo(tmp_path, "good")
    if kind == "missing":
        bad_path = tmp_path / "absent"
    elif kind == "unparseable":
        bad_path = make_repo(tmp_path, "broken", config_text=_BROKEN_TOML)
    else:
        bad_path = make_repo(tmp_path, "invalid", config_text=_INVALID_TOML)
    root = make_repo(
        tmp_path,
        "consumer",
        associates={"good": "../good", "bad": f"../{bad_path.name}"},
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
        """Two federated repos defining the same canonical ID is a hard error.

        Distinct namespaces are what make two repos federable at all, and
        an identifier that spells its namespace cannot then collide.  A
        canonical pattern that spells a fixed literal instead is where the
        collision survives, so that is the shape this exercises.
        """
        from elspais.graph.factory import build_graph
        from elspais.graph.federated import FederationError

        def _fixed_prefix_config(name: str, namespace: str, associates: str = "") -> str:
            return (
                f'version = 3\n\n[project]\nname = "{name}"\n'
                f'namespace = "{namespace}"\n\n'
                '[levels.prd]\nrank = 1\nimplements = []\n\n'
                '[levels.dev]\nrank = 2\nimplements = ["prd", "dev"]\n\n'
                '[id-patterns]\ncanonical = "REQ-{level.letter}{component}"\n' + associates
            )

        make_repo(
            tmp_path,
            "libcore",
            config_text=_fixed_prefix_config("libcore", "LIBCORE"),
            req_id="REQ-d00001",
        )
        root = make_repo(
            tmp_path,
            "appmain",
            config_text=_fixed_prefix_config(
                "appmain",
                "APPMAIN",
                '\n[associates.libcore]\npath = "../libcore"\nnamespace = "LIBCORE"\n',
            ),
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
        )
        far = make_repo(
            tmp_path,
            "coreY",
            origin="https://example.com/core-y.git",
        )
        make_repo(
            tmp_path,
            "mid",
            associates={"core": "../coreY"},
            associate_namespaces={"core": "COREY"},
        )
        root = make_repo(
            tmp_path,
            "top",
            associates={"core": "../coreX", "mid": "../mid"},
            associate_namespaces={"core": "COREX"},
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
        )
        make_repo(
            tmp_path,
            "mid",
            associates={"core": "../shared"},
            associate_namespaces={"core": "SHARED"},
        )
        root = make_repo(
            tmp_path,
            "top",
            associates={"core": "../shared", "mid": "../mid"},
            associate_namespaces={"core": "SHARED"},
        )

        planned = _plan(root)

        assert [entry.name for entry in planned] == ["top", "core", "mid"]
        assert len([e for e in planned if e.repo_root == shared.resolve()]) == 1


class TestDeclarationRequiredFields:
    """Validates REQ-d00202-B.

    A declaration says which repository it means by stating where it is and
    whose identifiers live there.  Missing either, it names nothing in
    particular, so it is refused rather than resolved against whatever
    happens to sit at that path.  The git remote answers a different
    question -- how to obtain the repository -- and is therefore optional.
    """

    @pytest.mark.parametrize(
        "entry",
        [
            {"namespace": "LIB"},
            {"path": "../lib"},
            {"path": "", "namespace": "LIB"},
            {"path": "../lib", "namespace": ""},
            "../lib",
        ],
        ids=[
            "no-path",
            "no-namespace",
            "empty-path",
            "empty-namespace",
            "not-a-table",
        ],
    )
    # Verifies: REQ-d00202-B
    def test_REQ_d00202_B_incomplete_declaration_is_refused(self, entry):
        """A declaration missing its path or its namespace is a ValueError."""
        from elspais.config import get_associates_config

        with pytest.raises(ValueError) as excinfo:
            get_associates_config({"associates": {"lib": entry}})

        # The operator has to be told WHICH declaration is unusable.
        assert "lib" in str(excinfo.value), str(excinfo.value)

    @pytest.mark.parametrize(
        "git",
        [None, "https://example.com/lib.git"],
        ids=["git-omitted", "git-supplied"],
    )
    # Verifies: REQ-d00202-B
    def test_REQ_d00202_B_git_remote_is_optional(self, git):
        """path + namespace alone is a complete declaration; git rides along."""
        from elspais.config import get_associates_config

        declaration = {"path": "../lib", "namespace": "LIB"}
        if git is not None:
            declaration["git"] = git

        resolved = get_associates_config({"associates": {"lib": declaration}})

        assert resolved["lib"]["path"] == "../lib"
        assert resolved["lib"]["namespace"] == "LIB"
        # Absent, it reads as "no clone hint" rather than being missing from
        # the resolved declaration; present, it is carried untouched.  Either
        # way it takes no part in locating the repository.
        assert resolved["lib"]["git"] == git

    # Verifies: REQ-d00202-B, REQ-d00212-K
    def test_REQ_d00202_B_git_remote_survives_a_config_on_disk(self, tmp_path):
        """An authored `.elspais.toml` may carry the remote, and it arrives intact.

        The declaration reader tolerating a remote is not the same as an
        operator being able to write one: config loading validates the
        declaration table on its own terms, so a remote that never reaches
        the reader is a remote nobody can supply.  This is the level the
        obligation is actually met at.
        """
        from elspais.config import get_associates_config

        remote = "https://example.com/lib.git"
        make_repo(tmp_path, "lib")
        root = make_repo(
            tmp_path,
            "app",
            config_text=(
                'version = 3\n\n[project]\nname = "app"\nnamespace = "APP"\n\n'
                "[levels.prd]\nrank = 1\nimplements = []\n\n"
                '[levels.dev]\nrank = 2\nimplements = ["prd", "dev"]\n\n'
                f'[associates.lib]\npath = "../lib"\nnamespace = "LIB"\ngit = "{remote}"\n'
            ),
            req_id="APP-d00001",
        )

        config = _load(root)
        resolved = get_associates_config(config, repo_root=root)

        assert resolved["lib"]["git"] == remote
        assert resolved["lib"]["path"] == "../lib"
        assert resolved["lib"]["namespace"] == "LIB"
        # The remote is clone assistance, not a locator: the federation
        # resolves through the declared path exactly as it would without it.
        assert [entry.name for entry in _plan(root)] == ["app", "lib"]

    # Verifies: REQ-d00202-B
    def test_REQ_d00202_B_incomplete_declaration_fails_the_federation(self, tmp_path):
        """Reached through planning, the refusal is a FederationError.

        A planning surface handles one error family.  A raw ValueError
        escaping the walk would reach callers that catch FederationError and
        take the rest of the report down with it, and it would not say which
        repository's configuration holds the bad declaration.
        """
        from elspais.graph.federated import FederationError
        from elspais.graph.federation_plan import plan_federation

        root = make_repo(tmp_path, "hub")
        config = _load(root)
        config["associates"] = {"lib": {"path": "../lib"}}

        with pytest.raises(FederationError) as excinfo:
            plan_federation(config, root)

        message = str(excinfo.value)
        assert str(root.resolve()) in message, message
        assert "lib" in message, message


class TestNamespaceCollision:
    """Validates REQ-d00202-K.

    A namespace answers whose identifiers these are.  Two repositories
    claiming one namespace leave that question unanswerable: identifiers
    spelled with it route to whichever repository the walk recorded last,
    and the other repository's requirements resolve against the wrong
    configuration.  One declaration table cannot collide with itself, so
    this only becomes reachable once declarations from several repositories
    are combined.
    """

    # Verifies: REQ-d00202-K
    def test_REQ_d00202_K_two_repos_under_one_namespace_raise(self, tmp_path):
        """Distinct repos both declaring 'SHARED', reached at different depths."""
        from elspais.graph.federated import FederationError

        near = make_repo(tmp_path, "alpha", namespace="SHARED")
        far = make_repo(tmp_path, "beta", namespace="SHARED")
        make_repo(
            tmp_path,
            "mid",
            associates={"beta": "../beta"},
            associate_namespaces={"beta": "SHARED"},
        )
        root = make_repo(
            tmp_path,
            "top",
            associates={"alpha": "../alpha", "mid": "../mid"},
            associate_namespaces={"alpha": "SHARED"},
        )

        # Planning raises on its own: the collision is settled before a
        # single repository's graph is built.
        with pytest.raises(FederationError) as excinfo:
            _plan(root)

        message = str(excinfo.value)
        assert "SHARED" in message, message
        # Both repositories must be identified by path -- naming only the
        # surviving claimant would leave the shadowed repo invisible.
        assert str(near.resolve()) in message, message
        assert str(far.resolve()) in message, message
        # ...and the declaration chain that reached each, which is the only
        # thing telling the two claims apart.  Ordering is pinned; the
        # separator glyph is not.
        assert re.search(r"top\W+alpha", message), message
        assert re.search(r"top\W+mid\W+beta", message), message

    # Verifies: REQ-d00202-K
    def test_REQ_d00202_K_one_repo_reached_twice_is_not_a_collision(self, tmp_path):
        """A diamond re-declaring one repository is convergence, not a clash.

        The second arrival carries the same namespace by construction, so a
        guard that ran before identity dedupe would reject every legitimate
        shared associate.
        """
        shared = make_repo(tmp_path, "common")
        make_repo(
            tmp_path,
            "mid",
            associates={"lib": "../common"},
            associate_namespaces={"lib": "COMMON"},
        )
        root = make_repo(
            tmp_path,
            "top",
            associates={"core": "../common", "mid": "../mid"},
            associate_namespaces={"core": "COMMON"},
        )

        planned = _plan(root)

        assert [entry.name for entry in planned] == ["top", "core", "mid"]
        assert len([e for e in planned if e.repo_root == shared.resolve()]) == 1

    # Verifies: REQ-d00202-K
    def test_REQ_d00202_K_unloadable_repos_are_not_namespace_claimants(self, tmp_path):
        """A repo that failed to load declares nothing, so two cannot collide.

        Their configs are None, so both would present the same empty
        namespace; treating that as a claim would turn every pair of broken
        associate paths into a spurious collision and hide the real reason
        each one failed.
        """
        root = make_repo(
            tmp_path,
            "hub",
            associates={"gone1": "../absent1", "gone2": "../absent2"},
        )

        planned = _plan(root)
        by_name = {entry.name: entry for entry in planned}

        assert set(by_name) == {"hub", "gone1", "gone2"}
        assert by_name["gone1"].config is None
        assert by_name["gone2"].config is None
        assert by_name["gone1"].error and by_name["gone2"].error


class TestDeclaredNamespaceMismatch:
    """Validates REQ-d00202-L.

    A declaration does not assign a namespace to the repository it names --
    it states the namespace its author expected to find there.  A mismatch
    means the declaration points somewhere its author did not intend, which
    is a mistake to report rather than a preference to reconcile.
    """

    @pytest.mark.parametrize(
        "declared",
        ["WRONG", "Lib"],
        ids=["different-namespace", "different-case"],
    )
    # Verifies: REQ-d00202-L
    def test_REQ_d00202_L_mismatched_namespace_raises(self, tmp_path, declared):
        """The message names the path, the namespace named, and the one found."""
        from elspais.graph.federated import FederationError

        lib = make_repo(tmp_path, "lib")  # declares namespace 'LIB'
        root = make_repo(
            tmp_path,
            "app",
            associates={"lib": "../lib"},
            associate_namespaces={"lib": declared},
        )

        with pytest.raises(FederationError) as excinfo:
            _plan(root)

        message = str(excinfo.value)
        assert str(lib.resolve()) in message, message
        # Quoted so 'Lib' and 'LIB' cannot satisfy one another by substring:
        # case is never repaired, so the near-miss spelling is still a miss.
        assert f"'{declared}'" in message, message
        assert "'LIB'" in message, message

    # Verifies: REQ-d00202-L
    def test_REQ_d00202_L_mismatch_is_caught_at_any_depth(self, tmp_path):
        """A transitively-reached declaration is checked like a direct one."""
        from elspais.graph.federated import FederationError

        deep = make_repo(tmp_path, "deep")  # declares namespace 'DEEP'
        make_repo(
            tmp_path,
            "mid",
            associates={"deep": "../deep"},
            associate_namespaces={"deep": "ELSEWHERE"},
        )
        root = make_repo(tmp_path, "front", associates={"mid": "../mid"})

        with pytest.raises(FederationError) as excinfo:
            _plan(root)

        message = str(excinfo.value)
        assert str(deep.resolve()) in message, message
        assert "'ELSEWHERE'" in message, message
        assert "'DEEP'" in message, message

    # Verifies: REQ-d00202-L
    def test_REQ_d00202_L_agreeing_namespace_resolves(self, tmp_path):
        """The check fires on disagreement only, not on every declaration."""
        make_repo(tmp_path, "lib")
        root = make_repo(
            tmp_path,
            "app",
            associates={"lib": "../lib"},
            associate_namespaces={"lib": "LIB"},
        )

        planned = _plan(root)

        assert [entry.name for entry in planned] == ["app", "lib"]
        assert all(entry.error is None for entry in planned)
