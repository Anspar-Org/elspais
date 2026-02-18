# Implements: REQ-p00060-A, REQ-p00060-C
"""End-to-end MCP protocol tests.

Starts the MCP server as a subprocess using stdio transport
and communicates via newline-delimited JSON-RPC 2.0.
"""

import json
import shutil
import subprocess

import pytest

pytest.importorskip("mcp")

_ELSPAIS = shutil.which("elspais")
pytestmark = pytest.mark.skipif(
    _ELSPAIS is None,
    reason="elspais CLI not found on PATH",
)


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
    response = _recv(proc)
    # Send initialized notification
    _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return response


@pytest.fixture
def mcp_server():
    """Start MCP server as subprocess with stdio transport."""
    proc = subprocess.Popen(
        [_ELSPAIS, "mcp", "serve"],
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

    def test_REQ_p00060_A_initialize_handshake(self, mcp_server):
        """Server responds to initialize with capabilities."""
        response = _initialize(mcp_server)
        assert "result" in response, f"Got error: {response}"
        assert "capabilities" in response["result"]
        assert "serverInfo" in response["result"]

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
