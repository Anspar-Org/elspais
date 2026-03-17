# Validates: REQ-p00060
"""Extended MCP protocol tests for elspais.

Starts the MCP server as a subprocess using stdio transport
and exercises tool calls via newline-delimited JSON-RPC 2.0.
"""

import json
import shutil
import subprocess

import pytest

pytest.importorskip("mcp")

_ELSPAIS = shutil.which("elspais")
pytestmark = [
    pytest.mark.skipif(
        _ELSPAIS is None,
        reason="elspais CLI not found on PATH",
    ),
    pytest.mark.e2e,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _call_tool(proc, name: str, arguments: dict, msg_id: int = 2):
    """Send a tools/call request and return the parsed content.

    The MCP response wraps tool output in::

        {"result": {"content": [{"type": "text", "text": "<json-string>"}]}}

    This helper extracts and parses the inner JSON string.
    Returns None if the content list is empty.
    """
    _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    response = _recv(proc)
    assert "result" in response, f"Expected result, got: {response}"
    content = response["result"]["content"]
    if not content:
        return None
    text = content[0]["text"]
    return json.loads(text)


def _call_tool_all(proc, name: str, arguments: dict, msg_id: int = 2) -> list:
    """Like _call_tool but returns ALL content items as parsed dicts."""
    _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    response = _recv(proc)
    assert "result" in response, f"Expected result, got: {response}"
    content = response["result"]["content"]
    return [json.loads(item["text"]) for item in content]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp():
    """Start an MCP server, perform the initialize handshake, and yield it."""
    proc = subprocess.Popen(
        [_ELSPAIS, "mcp", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    _initialize(proc)
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMCPSearch:
    """Validates REQ-p00060: MCP search tool calls."""

    def test_REQ_p00060_A_search_returns_results(self, mcp):
        """Search for 'REQ' returns at least one result."""
        results = _call_tool_all(mcp, "search", {"query": "REQ"}, msg_id=2)
        assert len(results) >= 1, "Expected at least 1 search result"
        # Each result should have an id field
        assert "id" in results[0], f"Expected 'id' in result: {results[0]}"

    def test_REQ_p00060_A_search_empty_query(self, mcp):
        """Search for a nonsense string returns no results."""
        results = _call_tool_all(mcp, "search", {"query": "xyznonexistent12345"}, msg_id=2)
        assert len(results) == 0, f"Expected 0 results, got {len(results)}"


class TestMCPGetRequirement:
    """Validates REQ-p00060: MCP get_requirement tool calls."""

    def test_REQ_p00060_A_get_requirement_found(self, mcp):
        """get_requirement returns data for a known requirement."""
        result = _call_tool(mcp, "get_requirement", {"req_id": "REQ-p00001"}, msg_id=2)
        assert "id" in result, f"Expected 'id' in result: {result}"
        assert result["id"] == "REQ-p00001"

    def test_REQ_p00060_A_get_requirement_not_found(self, mcp):
        """get_requirement for a nonexistent ID signals not-found."""
        _send(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_requirement",
                    "arguments": {"req_id": "REQ-zzz99999"},
                },
            },
        )
        response = _recv(mcp)
        # The server may return an error or a result indicating not found.
        if "error" in response:
            # Explicit JSON-RPC error — that counts as not-found.
            return
        # Otherwise the tool ran but should signal absence in the content.
        content = response["result"]["content"]
        text = content[0]["text"]
        # Accept either an error-like message or a null/empty result.
        parsed = json.loads(text)
        not_found = (
            parsed is None
            or parsed == {}
            or (isinstance(parsed, dict) and parsed.get("error"))
            or (isinstance(parsed, dict) and "not found" in str(parsed).lower())
        )
        assert not_found, f"Expected not-found indication, got: {parsed}"


class TestMCPHierarchy:
    """Validates REQ-p00060: MCP get_hierarchy tool call."""

    def test_REQ_p00060_A_get_hierarchy(self, mcp):
        """get_hierarchy returns ancestors and children for a known req."""
        result = _call_tool(mcp, "get_hierarchy", {"req_id": "REQ-p00001"}, msg_id=2)
        assert "ancestors" in result, f"Expected 'ancestors' key: {result}"
        assert "children" in result, f"Expected 'children' key: {result}"


class TestMCPProjectSummary:
    """Validates REQ-p00060: MCP get_project_summary tool call."""

    def test_REQ_p00060_A_project_summary(self, mcp):
        """get_project_summary returns counts."""
        result = _call_tool(mcp, "get_project_summary", {}, msg_id=2)
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        # Should have some count-like keys (e.g. total, active, etc.)
        assert len(result) > 0, "Expected non-empty project summary"


class TestMCPCursorPagination:
    """Validates REQ-p00060: MCP cursor pagination protocol."""

    def test_REQ_p00060_A_cursor_open_and_next(self, mcp):
        """open_cursor + cursor_next advances through results."""
        # Open a cursor over search results
        open_result = _call_tool(
            mcp,
            "open_cursor",
            {"query": "search", "params": {"query": "REQ"}, "batch_size": 1},
            msg_id=2,
        )
        assert isinstance(open_result, dict), f"Expected dict: {open_result}"
        # Cursor response has: current, total, position, remaining
        assert "current" in open_result, f"Expected 'current' in cursor response: {open_result}"
        assert "total" in open_result, f"Expected 'total' in cursor response: {open_result}"
        assert open_result["total"] > 0, "Expected at least 1 total item"

        # Advance the cursor
        next_result = _call_tool(mcp, "cursor_next", {"count": 1}, msg_id=3)
        assert isinstance(next_result, dict), f"Expected dict: {next_result}"


class TestMCPMutationRoundtrip:
    """Validates REQ-p00060: MCP mutation and undo round-trip."""

    def test_REQ_p00060_A_mutation_undo_roundtrip(self, mcp):
        """Mutate a title, undo, and verify reversion."""
        # 1. Get the original title
        original = _call_tool(mcp, "get_requirement", {"req_id": "REQ-p00001"}, msg_id=2)
        original_title = original.get("title", "")
        assert original_title, "Expected a non-empty original title"

        # 2. Mutate the title
        mutate_result = _call_tool(
            mcp,
            "mutate_update_title",
            {"node_id": "REQ-p00001", "new_title": "Test Mutation Title"},
            msg_id=3,
        )
        assert isinstance(mutate_result, dict), f"Mutation failed: {mutate_result}"

        # 3. Undo the mutation
        undo_result = _call_tool(mcp, "undo_last_mutation", {}, msg_id=4)
        assert isinstance(undo_result, dict), f"Undo failed: {undo_result}"

        # 4. Verify the title reverted
        after_undo = _call_tool(mcp, "get_requirement", {"req_id": "REQ-p00001"}, msg_id=5)
        assert after_undo.get("title") == original_title, (
            f"Title did not revert: expected {original_title!r}, "
            f"got {after_undo.get('title')!r}"
        )
