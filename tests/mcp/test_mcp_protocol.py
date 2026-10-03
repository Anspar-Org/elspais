# Verifies: REQ-p00060-A, REQ-p00060-C
"""End-to-end MCP protocol tests.

Starts the MCP server as a subprocess using stdio transport
and communicates via newline-delimited JSON-RPC 2.0.
"""

import json
import subprocess

import pytest

from tests.e2e.conftest import private_tree
from tests.e2e.helpers import resolve_elspais

pytest.importorskip("mcp")

_ELSPAIS = resolve_elspais()
pytestmark = [
    pytest.mark.skipif(
        _ELSPAIS is None,
        reason="elspais CLI not found on PATH",
    ),
    pytest.mark.e2e,
]


# Allowance for the server's first response, which follows a cold full graph
# build of this repository's estate. It covers that build on the slowest
# machine that runs this tier, beside another worker building its own copy.
# The tests ask whether the server answers; this is not a performance budget.
STARTUP_TIMEOUT = 120.0


def _send(proc, obj: dict) -> None:
    """Send a JSON-RPC 2.0 message to the server."""
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def _recv(proc, timeout: float = 10.0) -> dict:
    """Read a JSON-RPC 2.0 response from the server."""
    import select

    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        raise TimeoutError("No response from MCP server")
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise EOFError(f"MCP server closed stdout. stderr: {stderr}")
    return json.loads(line)


def _initialize(proc) -> dict:
    """Perform the MCP initialize handshake."""
    _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "0.1.0"},
            },
        },
    )
    response = _recv(proc, timeout=STARTUP_TIMEOUT)
    # Send initialized notification
    _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return response


@pytest.fixture(scope="module")
def protocol_tree(tmp_path_factory):
    """A private copy of this repository for the module's servers to serve."""
    return private_tree(tmp_path_factory.mktemp("repo-tree"))


@pytest.fixture
def mcp_server(protocol_tree):
    """Start MCP server as subprocess with stdio transport, over the private copy."""
    proc = subprocess.Popen(
        [_ELSPAIS, "mcp", "serve"],
        cwd=protocol_tree,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


class TestMCPProtocol:
    """Test MCP server via stdio transport."""

    # Verifies: REQ-p00060-A
    def test_REQ_p00060_A_initialize_handshake(self, mcp_server):
        """Server responds to initialize with capabilities."""
        response = _initialize(mcp_server)
        assert "result" in response, f"Got error: {response}"
        assert "capabilities" in response["result"]
        assert "serverInfo" in response["result"]

    # Verifies: REQ-p00060-C
    def test_REQ_p00060_C_tools_list(self, mcp_server):
        """Server exposes tools list after initialization."""
        _initialize(mcp_server)
        _send(
            mcp_server,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        response = _recv(mcp_server)
        assert "result" in response, f"Got error: {response}"
        tools = response["result"].get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "search" in tool_names
        assert "get_graph_status" in tool_names
        assert "get_requirement" in tool_names

    # Verifies: REQ-p00060-C
    def test_REQ_p00060_C_call_graph_status(self, mcp_server):
        """Server returns graph status via tool call."""
        _initialize(mcp_server)
        _send(
            mcp_server,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_graph_status", "arguments": {}},
            },
        )
        response = _recv(mcp_server)
        assert "result" in response, f"Got error: {response}"
