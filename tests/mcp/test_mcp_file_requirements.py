"""The MCP ``get_file_requirements`` tool answers as ``compute_files`` does.

The tool is reached through the registered closure, so the wrapper's own
handling of the graph and of its build time is what is exercised.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from elspais.commands._requests import FilesRequest
from elspais.commands.files_cmd import compute_files

HHT_LIKE = Path(__file__).parent.parent / "fixtures" / "hht-like"

PATHS = [
    "database/schema.sql",
    "tests/test_auth.py",
    "spec/journeys.md",
    "spec/glossary.md",
    "spec/INDEX.md",
    "no/such/file.py",
]


@pytest.fixture
def file_requirements(canonical_federated_graph):
    pytest.importorskip("mcp")
    from elspais.mcp.server import create_server

    server = create_server(canonical_federated_graph, working_dir=HHT_LIKE)
    return server._tool_manager._tools["get_file_requirements"].fn


# Verifies: REQ-d00335-C
def test_the_tool_answers_with_the_files_compute_files_gives(
    file_requirements, canonical_federated_graph, canonical_config
):
    result = file_requirements(paths=list(PATHS))
    expected = compute_files(
        canonical_federated_graph,
        canonical_config,
        FilesRequest(paths=tuple(PATHS)),
        built_at=time.time(),
    )
    assert result["files"] == expected["files"]
    schema = result["files"][0]
    assert schema["path"] == "database/schema.sql"
    assert {"kind": "implements", "id": "REQ-d00001", "requirement": "REQ-d00001"} in schema[
        "links"
    ]
