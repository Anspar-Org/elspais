# Verifies: REQ-p00006-A
"""Guard: the static HTML generate path must not import starlette (CUR-1698).

`elspais viewer --static` ships under the ``[trace-view]`` extra, which does NOT
install starlette (that lives in ``[all]`` / ``[trace-review]``). The static
generator previously imported its level/namespace/status builders from
``elspais.server.routes_ui``, which imports starlette at module top level — so
``viewer --static`` blew up with ``No module named 'starlette'`` in a
trace-view-only environment. The builders now live in the starlette-free
``elspais.view_model``.

This runs in a fresh subprocess and asserts starlette is never imported while
building a static HTML document. A fresh interpreter is required because other
tests in this process legitimately import starlette (the server suite), which
would pollute ``sys.modules``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

# The subprocess builds a minimal graph and renders static HTML, then asserts no
# starlette module was pulled in transitively.
_PROBE = """
import sys
from tests.core.graph_test_helpers import build_graph, make_requirement
from elspais.html.generator import HTMLGenerator

graph = build_graph(
    make_requirement(
        "REQ-p00001",
        level="PRD",
        title="Product Requirement",
        assertions=[{"label": "A", "text": "First assertion"}],
        hash_value="abc12345",
        source_path="spec/prd.md",
    ),
)
html = HTMLGenerator(graph).generate()
assert "<html" in html.lower(), "static generate did not produce HTML"

pulled = sorted(m for m in sys.modules if m.split(".")[0] == "starlette")
assert not pulled, f"static generate transitively imported starlette: {pulled}"
print("STARLETTE_FREE_OK")
"""


@pytest.mark.e2e
def test_static_generate_does_not_import_starlette():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"probe failed:\n{result.stdout}\n{result.stderr}"
    assert "STARLETTE_FREE_OK" in result.stdout, result.stdout
