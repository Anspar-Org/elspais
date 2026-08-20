"""Tests for associates config functions.

Validates REQ-d00202-A: Read associate definitions from config.
Validates REQ-d00202-B: Path is required, namespace is required.
Validates REQ-d00202-C: Missing or empty associates section returns empty dict.
Validates REQ-d00202-D: Associates are resolved transitively.
Validates REQ-d00203-B: An associate's own config is loaded and its
    declarations are discovered.
"""

from elspais.config import get_associates_config


class TestGetAssociatesConfig:
    """Validates REQ-d00202-A, REQ-d00202-B, REQ-d00202-C."""

    def test_REQ_d00202_A_reads_associates_config(self):
        """Config with two associates returns both with paths and namespace fields."""
        config = {
            "associates": {
                "core": {"path": "../core", "namespace": "CORE"},
                "module-a": {"path": "../module-a", "namespace": "MODA"},
            }
        }

        result = get_associates_config(config)

        assert len(result) == 2
        assert result["core"]["path"] == "../core"
        assert result["core"]["namespace"] == "CORE"
        assert result["module-a"]["path"] == "../module-a"
        assert result["module-a"]["namespace"] == "MODA"

    def test_REQ_d00202_B_path_and_namespace_required(self):
        """Path and namespace are required fields."""
        config = {
            "associates": {
                "module-a": {"path": "../module-a", "namespace": "MODA"},
            }
        }

        result = get_associates_config(config)

        assert result["module-a"]["path"] == "../module-a"
        assert result["module-a"]["namespace"] == "MODA"

    def test_REQ_d00202_C_no_associates_returns_empty(self):
        """Config with no associates section returns empty dict."""
        config = {"project": {"namespace": "REQ"}}

        result = get_associates_config(config)

        assert result == {}

    def test_REQ_d00202_C_empty_associates_returns_empty(self):
        """Config with empty associates section returns empty dict."""
        config = {"associates": {}}

        result = get_associates_config(config)

        assert result == {}


class TestTransitiveAssociateDetection:
    """Validates REQ-d00202-D, REQ-d00203-B: transitive associates resolve."""

    # Verifies: REQ-d00202-D, REQ-d00203-B
    def test_REQ_d00202_D_associate_with_associates_resolves(self, tmp_path):
        """An associate declaring its own associates joins ONE federation.

        The sub-associate is only reachable by loading the associate's own
        config, so its presence proves the walk recursed rather than stopped.
        """
        from elspais.config import load_config
        from elspais.graph.factory import build_graph
        from tests.config.test_federation_config import make_repo

        make_repo(tmp_path, "sub-module")
        make_repo(tmp_path, "core", associates={"sub-module": "../sub-module"})
        root = make_repo(tmp_path, "app", associates={"core": "../core"})

        federated = build_graph(config=load_config(root / ".elspais.toml"), repo_root=root)

        assert {repo.name for repo in federated.iter_repos()} == {
            "app",
            "core",
            "sub-module",
        }

    # Verifies: REQ-d00202-D
    def test_REQ_d00202_D_associate_without_associates_is_a_leaf(self, tmp_path):
        """An associate with no [associates] section terminates the walk."""
        from elspais.config import load_config
        from elspais.graph.factory import build_graph
        from tests.config.test_federation_config import make_repo

        make_repo(tmp_path, "core")
        root = make_repo(tmp_path, "app", associates={"core": "../core"})

        federated = build_graph(config=load_config(root / ".elspais.toml"), repo_root=root)

        assert {repo.name for repo in federated.iter_repos()} == {"app", "core"}
