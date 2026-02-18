# E2E Integration Tests & CI Container - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add end-to-end integration tests for PDF generation, CLI subprocess invocation, tab completion, and MCP protocol — backed by a GHCR CI container with pandoc + texlive.

**Architecture:** A Docker image published to GHCR provides a consistent test environment with all system dependencies. The CI test job runs inside the container. New test files exercise each feature end-to-end, using `skipif` to gracefully degrade when tools are missing locally.

**Tech Stack:** Docker, GitHub Actions, GHCR, pytest, subprocess, MCP stdio transport

**Design doc:** `docs/plans/2026-02-17-e2e-integration-tests-design.md`

---

### Task 1: Tab Completion Tests

Tests for `src/elspais/commands/completion.py` (implements REQ-p00001-A).
Pure Python — no system dependencies needed.

**Files:**

- Create: `tests/commands/test_completion.py`

**Step 1: Write the tests**

```python
# Implements: REQ-p00001-A
"""Tests for shell tab-completion setup."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from elspais.commands.completion import (
    _COMPLETION_MARKER,
    _detect_shell,
    _get_rc_file,
    _install,
    _snippet_for,
    _uninstall,
)


class TestDetectShell:
    """Tests for _detect_shell()."""

    def test_REQ_p00001_A_detects_bash(self):
        with patch.dict(os.environ, {"SHELL": "/bin/bash"}):
            assert _detect_shell() == "bash"

    def test_REQ_p00001_A_detects_zsh(self):
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}):
            assert _detect_shell() == "zsh"

    def test_REQ_p00001_A_detects_fish(self):
        with patch.dict(os.environ, {"SHELL": "/usr/bin/fish"}):
            assert _detect_shell() == "fish"

    def test_REQ_p00001_A_detects_tcsh(self):
        with patch.dict(os.environ, {"SHELL": "/bin/tcsh"}):
            assert _detect_shell() == "tcsh"

    def test_REQ_p00001_A_defaults_to_bash_for_unknown(self):
        with patch.dict(os.environ, {"SHELL": "/bin/unknown"}):
            assert _detect_shell() == "bash"

    def test_REQ_p00001_A_defaults_to_bash_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _detect_shell() == "bash"


class TestGetRcFile:
    """Tests for _get_rc_file()."""

    def test_REQ_p00001_A_bash_rc_file(self):
        assert _get_rc_file("bash") == Path.home() / ".bashrc"

    def test_REQ_p00001_A_zsh_rc_file(self):
        assert _get_rc_file("zsh") == Path.home() / ".zshrc"

    def test_REQ_p00001_A_fish_rc_file(self):
        assert _get_rc_file("fish") == Path.home() / ".config" / "fish" / "config.fish"

    def test_REQ_p00001_A_tcsh_rc_file(self):
        assert _get_rc_file("tcsh") == Path.home() / ".tcshrc"

    def test_REQ_p00001_A_unknown_defaults_to_bashrc(self):
        assert _get_rc_file("nushell") == Path.home() / ".bashrc"


class TestSnippetFor:
    """Tests for _snippet_for()."""

    def test_REQ_p00001_A_bash_snippet_contains_marker(self):
        assert _COMPLETION_MARKER in _snippet_for("bash")

    def test_REQ_p00001_A_fish_snippet_uses_source(self):
        assert "source" in _snippet_for("fish")

    def test_REQ_p00001_A_tcsh_snippet_uses_eval(self):
        assert "eval" in _snippet_for("tcsh")


class TestInstall:
    """Tests for _install() writing to rc files."""

    def test_REQ_p00001_A_install_appends_snippet(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bashrc", delete=False) as f:
            f.write("# existing content\n")
            f.flush()
            rc_path = Path(f.name)

        with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
            result = _install("bash")

        assert result == 0
        content = rc_path.read_text()
        assert _COMPLETION_MARKER in content
        assert "existing content" in content
        rc_path.unlink()

    def test_REQ_p00001_A_install_idempotent(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bashrc", delete=False) as f:
            f.write(f"# existing\n{_snippet_for('bash')}")
            f.flush()
            rc_path = Path(f.name)

        with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
            result = _install("bash")

        assert result == 0
        # Should not duplicate
        assert content.count(_COMPLETION_MARKER) == 1
        rc_path.unlink()

    def test_REQ_p00001_A_install_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rc_path = Path(tmpdir) / ".bashrc"
            with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
                result = _install("bash")

            assert result == 0
            assert rc_path.exists()
            assert _COMPLETION_MARKER in rc_path.read_text()


class TestUninstall:
    """Tests for _uninstall() removing from rc files."""

    def test_REQ_p00001_A_uninstall_removes_snippet(self):
        snippet = _snippet_for("bash")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bashrc", delete=False) as f:
            f.write(f"# before\n\n{snippet}# after\n")
            f.flush()
            rc_path = Path(f.name)

        with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
            result = _uninstall("bash")

        assert result == 0
        content = rc_path.read_text()
        assert _COMPLETION_MARKER not in content
        assert "# before" in content
        assert "# after" in content
        rc_path.unlink()

    def test_REQ_p00001_A_uninstall_noop_when_not_installed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bashrc", delete=False) as f:
            f.write("# no completion here\n")
            f.flush()
            rc_path = Path(f.name)

        with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
            result = _uninstall("bash")

        assert result == 0
        rc_path.unlink()

    def test_REQ_p00001_A_uninstall_noop_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rc_path = Path(tmpdir) / ".bashrc"
            with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
                result = _uninstall("bash")

            assert result == 0
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/commands/test_completion.py -v`
Expected: All pass (fix the idempotent test's `content` variable reference).

**Step 3: Commit**

```
git add tests/commands/test_completion.py
git commit -m "[CUR-520] test: Add tab completion unit tests (REQ-p00001-A)"
```

---

### Task 2: CLI Subprocess Integration Tests

End-to-end tests invoking `elspais` as a real subprocess.
References REQ-p00001-A (CLI validation), REQ-p00080-A (PDF command), REQ-o00066-C (self-validation).

**Files:**

- Create: `tests/test_cli_integration.py`

**Step 1: Write the tests**

```python
# Implements: REQ-p00001-A, REQ-p00080-A, REQ-o00066-C
"""End-to-end CLI integration tests.

Invokes elspais as a subprocess to verify real command execution.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

requires_pandoc = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc not found (install: https://pandoc.org/installing.html)",
)

requires_xelatex = pytest.mark.skipif(
    shutil.which("xelatex") is None,
    reason="xelatex not found (install TeX Live, MiKTeX, or MacTeX)",
)


def _run_elspais(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    """Run elspais as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "elspais", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
    )


class TestCLIHelp:
    """Test --help works for main and subcommands."""

    def test_REQ_p00001_A_main_help(self):
        result = _run_elspais("--help")
        assert result.returncode == 0
        assert "elspais" in result.stdout

    def test_REQ_p00001_A_validate_help(self):
        result = _run_elspais("validate", "--help")
        assert result.returncode == 0

    def test_REQ_p00080_A_pdf_help(self):
        result = _run_elspais("pdf", "--help")
        assert result.returncode == 0
        assert "pandoc" in result.stdout.lower() or "pandoc" in result.stderr.lower()


class TestValidateCommand:
    """Test validate command runs end-to-end."""

    def test_REQ_p00001_A_validate_core(self):
        result = _run_elspais("validate", "--mode", "core")
        assert result.returncode == 0

    def test_REQ_o00066_C_index_validate(self):
        result = _run_elspais("index", "--mode", "core", "validate")
        assert result.returncode == 0


class TestDocsCommand:
    """Test docs command outputs content."""

    def test_REQ_p00001_A_docs_quickstart(self):
        result = _run_elspais("docs", "quickstart", "--plain")
        assert result.returncode == 0
        assert len(result.stdout) > 100


class TestTraceCommand:
    """Test trace command generates output."""

    def test_REQ_p00001_B_trace_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "trace"
            result = _run_elspais("trace", "--format", "markdown", "--output", str(out))
            assert result.returncode == 0
            assert (out.with_suffix(".md")).exists() or Path(f"{out}.md").exists()


class TestPdfCommand:
    """Test PDF generation end-to-end."""

    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_A_generates_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test-output.pdf"
            result = _run_elspais("pdf", "--output", str(out))
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert out.exists(), "PDF file was not created"
            assert out.stat().st_size > 0, "PDF file is empty"
            # Check PDF magic bytes
            with open(out, "rb") as f:
                assert f.read(4) == b"%PDF"

    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_F_generates_overview_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "overview.pdf"
            result = _run_elspais("pdf", "--overview", "--output", str(out))
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert out.exists()
            assert out.stat().st_size > 0
            with open(out, "rb") as f:
                assert f.read(4) == b"%PDF"
```

**Step 2: Run tests**

Run: `pytest tests/test_cli_integration.py -v`
Expected: CLI tests pass. PDF tests skip if pandoc/xelatex not available, pass if available.

**Step 3: Commit**

```
git add tests/test_cli_integration.py
git commit -m "[CUR-520] test: Add CLI subprocess integration tests (REQ-p00001-A, REQ-p00080-A)"
```

---

### Task 3: MCP Protocol Integration Tests

End-to-end test of the MCP server via stdio transport.
References REQ-p00060-A (expose graph through MCP tools), REQ-p00060-C (read-only query tools).

**Files:**

- Create: `tests/mcp/test_mcp_protocol.py`

**Step 1: Write the tests**

```python
# Implements: REQ-p00060-A, REQ-p00060-C
"""End-to-end MCP protocol tests.

Starts the MCP server as a subprocess using stdio transport
and communicates via JSON-RPC 2.0.
"""

import json
import subprocess
import sys

import pytest

mcp = pytest.importorskip("mcp")


def _send_jsonrpc(process, method: str, params: dict | None = None, req_id: int = 1) -> dict:
    """Send a JSON-RPC 2.0 request and read the response."""
    request = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params is not None:
        request["params"] = params

    message = json.dumps(request)
    content = f"Content-Length: {len(message)}\r\n\r\n{message}"
    process.stdin.write(content)
    process.stdin.flush()

    # Read response header
    header = ""
    while True:
        line = process.stdout.readline()
        if line == "\r\n" or line == "\n":
            break
        header += line

    # Parse content length
    content_length = 0
    for h in header.strip().split("\r\n"):
        if h.lower().startswith("content-length:"):
            content_length = int(h.split(":")[1].strip())

    # Read response body
    body = process.stdout.read(content_length)
    return json.loads(body)


class TestMCPProtocol:
    """Test MCP server via stdio transport."""

    @pytest.fixture
    def mcp_server(self):
        """Start MCP server as subprocess."""
        proc = subprocess.Popen(
            [sys.executable, "-m", "elspais.mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        yield proc
        proc.terminate()
        proc.wait(timeout=5)

    def test_REQ_p00060_A_initialize_handshake(self, mcp_server):
        """Server responds to initialize with capabilities."""
        response = _send_jsonrpc(
            mcp_server,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1"},
            },
        )
        assert "result" in response
        assert "capabilities" in response["result"]

    def test_REQ_p00060_C_tools_list(self, mcp_server):
        """Server exposes tools list."""
        # Initialize first
        _send_jsonrpc(
            mcp_server,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1"},
            },
        )
        # Send initialized notification (no id)
        notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        content = f"Content-Length: {len(notif)}\r\n\r\n{notif}"
        mcp_server.stdin.write(content)
        mcp_server.stdin.flush()

        # List tools
        response = _send_jsonrpc(mcp_server, "tools/list", req_id=2)
        assert "result" in response
        tools = response["result"].get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "search" in tool_names
        assert "get_graph_status" in tool_names
```

Note: The actual JSON-RPC framing may differ depending on the MCP SDK version. The test
implementation should be adapted to match `FastMCP`'s actual stdio protocol. If the SDK
uses SSE or a different framing, adjust accordingly. The key assertion is that the server
starts, accepts connections, and responds with its tool list.

**Step 2: Run tests**

Run: `pytest tests/mcp/test_mcp_protocol.py -v`
Expected: Pass if mcp is installed, skip otherwise.

**Step 3: Commit**

```
git add tests/mcp/test_mcp_protocol.py
git commit -m "[CUR-520] test: Add MCP protocol integration tests (REQ-p00060-A, REQ-p00060-C)"
```

---

### Task 4: Dockerfile and Build Workflow

Create the CI container image with all dependencies.

**Files:**

- Create: `.github/docker/Dockerfile`
- Create: `.github/workflows/build-ci-image.yml`

**Step 1: Write the Dockerfile**

```dockerfile
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    texlive-xetex \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/
COPY docs/ docs/

# Install with all extras
RUN pip install --no-cache-dir -e ".[dev,all]"
```

**Step 2: Write the build workflow**

```yaml
name: Build CI Image

on:
  push:
    branches: [main]
    paths:
      - ".github/docker/Dockerfile"
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/elspais-ci

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: .github/docker/Dockerfile
          push: true
          build-args: PYTHON_VERSION=${{ matrix.python-version }}
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:py${{ matrix.python-version }}
```

**Step 3: Commit**

```
git add .github/docker/Dockerfile .github/workflows/build-ci-image.yml
git commit -m "[CUR-520] feat: Add CI Docker image with pandoc and texlive (REQ-o00066-A)"
```

---

### Task 5: Update CI Workflow to Use Container

Switch the test job from bare ubuntu to the GHCR container.

**Files:**

- Modify: `.github/workflows/ci.yml`

**Step 1: Update the test job**

Replace the current test job (lines 9-31) with:

```yaml
  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    container: ghcr.io/anspar-org/elspais-ci:py${{ matrix.python-version }}
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Install package
        run: pip install -e ".[dev,all]"

      - name: Run tests
        run: pytest --tb=short -q
```

Keep the lint, self-validate, and security jobs unchanged.

**Step 2: Commit**

```
git add .github/workflows/ci.yml
git commit -m "[CUR-520] ci: Use GHCR container for test job (REQ-o00066-A)"
```

---

### Task 6: Run Full Test Suite and Push

Verify everything works locally, then push.

**Step 1: Run the full test suite**

```
pytest tests/ --tb=short -q
```

Expected: All new tests pass (PDF tests may skip locally without pandoc).

**Step 2: Push**

```
git push
```
