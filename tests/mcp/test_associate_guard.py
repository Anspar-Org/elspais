"""MCP mutations targeting associate nodes are rejected when writes disabled.

Implements: REQ-d00253-D
"""

from elspais.mcp.server import _guard_associate_write


class _Repo:
    def __init__(self, name):
        self.name = name


class _Graph:
    root_repo_name = "primary"

    def __init__(self, ownership):
        self._ownership = ownership

    def repo_for(self, node_id):
        if node_id not in self._ownership:
            raise KeyError(node_id)
        return _Repo(self._ownership[node_id])


def test_guard_blocks_associate_node_when_disabled():
    g = _Graph({"LIB-d00001": "lib"})
    cfg = {"federation": {"write_associates": False}}
    result = _guard_associate_write(g, cfg, "LIB-d00001")
    assert result is not None
    assert result["success"] is False
    assert "read-only" in result["error"].lower()
    assert "lib" in result["error"].lower()


def test_guard_allows_primary_node():
    g = _Graph({"REQ-d00001": "primary"})
    cfg = {"federation": {"write_associates": False}}
    assert _guard_associate_write(g, cfg, "REQ-d00001") is None


def test_guard_allows_when_enabled():
    g = _Graph({"LIB-d00001": "lib"})
    cfg = {"federation": {"write_associates": True}}
    assert _guard_associate_write(g, cfg, "LIB-d00001") is None


def test_guard_ignores_unknown_node():
    g = _Graph({})
    cfg = {"federation": {"write_associates": False}}
    assert _guard_associate_write(g, cfg, "REQ-dNEW") is None


def test_guard_checks_all_ids():
    g = _Graph({"REQ-d00001": "primary", "LIB-d00001": "lib"})
    cfg = {"federation": {"write_associates": False}}
    assert _guard_associate_write(g, cfg, "REQ-d00001", "LIB-d00001") is not None
