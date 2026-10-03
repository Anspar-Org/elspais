"""An MCP tool called with an argument it does not declare does nothing.

REQ-p00060-F: the server refuses the call and reports the undeclared
argument together with the arguments the tool accepts. The tests go through
the server's ``call_tool``, which is where every client request arrives;
the tool functions themselves never see the extra argument.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from elspais.graph.factory import build_graph
from elspais.graph.parsers.directives import assertion_is_retired
from elspais.graph.render import node_version

pytest.importorskip("mcp")

_CONFIG = """version = 5

[project]
name = "arguments"
namespace = "REQ"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[scanning.spec]
directories = ["spec"]
"""

_PRD = """# REQ-p00001: Parent

**Level**: prd | **Status**: Active | **Implements**: -

## Assertions

A. The tool SHALL do alpha.

B. The tool SHALL do beta.

*End* *Parent* | **Hash**: 00000000
---
"""


@pytest.fixture
def served(tmp_path: Path):
    """A graph over a one-requirement repository and the server serving it."""
    from elspais.mcp.server import create_server

    root = tmp_path / "repo"
    (root / "spec").mkdir(parents=True)
    (root / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    (root / "spec" / "prd.md").write_text(_PRD, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    graph = build_graph(repo_root=root)
    return graph, create_server(graph, working_dir=root)


def _call(server, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call *name* through the server's dispatch and return its JSON answer."""
    result = asyncio.run(server.call_tool(name, arguments))
    if isinstance(result, dict):
        return result
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


def _declared(server, name: str) -> list[str]:
    return sorted(server._tool_manager.get_tool(name).parameters.get("properties", {}))


def _delete_arguments(graph, **extra: Any) -> dict[str, Any]:
    return {
        "assertion_id": "REQ-p00001-B",
        "if_version": node_version(graph.find_by_id("REQ-p00001")),
        "confirm": True,
        **extra,
    }


class TestUndeclaredArgumentsAreRefused:
    """Validates REQ-p00060-F."""

    @pytest.mark.parametrize(
        "tool,arguments,undeclared",
        [
            pytest.param("get_graph_status", {"bogus": 1}, ["bogus"], id="read-no-arguments"),
            pytest.param(
                "get_requirement",
                {"req_id": "REQ-p00001", "verbose": True, "depth": 2},
                ["depth", "verbose"],
                id="read-with-arguments",
            ),
        ],
    )
    # Verifies: REQ-p00060-F
    def test_REQ_p00060_F_read_tool_refuses_and_names_what_it_accepts(
        self, served, tool: str, arguments: dict, undeclared: list[str]
    ):
        _graph, server = served

        answer = _call(server, tool, arguments)

        assert answer["success"] is False
        assert answer["code"] == "undeclared_argument"
        assert answer["undeclared"] == undeclared
        assert answer["accepted"] == _declared(server, tool)
        assert "Nothing was done" in answer["error"]
        for name in undeclared:
            assert repr(name) in answer["error"]

    # Verifies: REQ-p00060-F
    def test_REQ_p00060_F_mutation_with_an_undeclared_argument_changes_nothing(self, served):
        """``compact`` is not an argument of the deletion tool, so the call is
        refused before the deletion runs."""
        graph, server = served
        version = node_version(graph.find_by_id("REQ-p00001"))

        answer = _call(server, "mutate_delete_assertion", _delete_arguments(graph, compact=True))

        assert answer["code"] == "undeclared_argument"
        assert answer["undeclared"] == ["compact"]
        assert answer["accepted"] == ["assertion_id", "confirm", "if_version"]
        assert len(graph.mutation_log) == 0
        assert not assertion_is_retired(graph.find_by_id("REQ-p00001-B"))
        assert node_version(graph.find_by_id("REQ-p00001")) == version

    # Verifies: REQ-p00060-F
    def test_REQ_p00060_F_declared_arguments_alone_are_served(self, served):
        """Control: the same calls with only declared arguments do their work."""
        graph, server = served

        status = _call(server, "get_graph_status", {})
        deleted = _call(server, "mutate_delete_assertion", _delete_arguments(graph))

        assert "undeclared_argument" not in json.dumps(status)
        assert deleted["success"] is True, deleted
        assert len(graph.mutation_log) == 1
        assert assertion_is_retired(graph.find_by_id("REQ-p00001-B"))
