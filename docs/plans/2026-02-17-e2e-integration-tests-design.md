# E2E Integration Tests & CI Container

**Date:** 2026-02-17
**Ticket:** CUR-520

## Problem

Several features lack end-to-end tests. The PDF command has never been tested with real pandoc invocation — all subprocess calls are mocked. CI runs on bare ubuntu-latest without pandoc or texlive, so mocked tests pass silently. Similar gaps exist for CLI subprocess invocation, tab completion, and MCP protocol testing.

## Decision Summary

- Build a GHCR container with Python + pandoc + texlive + all project extras
- Use the container for the CI test job (all Python versions via build-arg)
- Add e2e tests for: PDF generation, CLI subprocess, tab completion, MCP protocol
- Use `pytest.mark.skipif` with clear reason messages for tool-dependent tests

## Container

**Dockerfile** at `.github/docker/Dockerfile`:

- Base: `python:${PYTHON_VERSION}-slim` (build-arg, default 3.13)
- System packages: `pandoc`, `texlive-xetex`, `texlive-fonts-recommended`, `texlive-fonts-extra`
- Python install: `pip install -e ".[dev,all]"` (covers pytest, flask, mcp, jinja2, pygments, argcomplete, etc.)
- Published to: `ghcr.io/anspar-org/elspais-ci:py3.10`, `py3.11`, `py3.12`, `py3.13`

**Build workflow** at `.github/workflows/build-ci-image.yml`:

- Triggers on: changes to Dockerfile, manual dispatch
- Builds and pushes multi-version tags via matrix
- Uses GITHUB_TOKEN for GHCR auth

## CI Changes

**`.github/workflows/ci.yml` test job:**

Replace `runs-on: ubuntu-latest` + `setup-python` + `pip install` with:

```yaml
container: ghcr.io/anspar-org/elspais-ci:py${{ matrix.python-version }}
```

Lint, self-validate, and security jobs stay on ubuntu-latest (no container needed).

## New Tests

### 1. PDF Integration (`tests/test_pdf_integration.py`)

- `skipif`: `shutil.which("pandoc") is None` — reason: "pandoc not found"
- Runs `elspais pdf` against the repo's own `spec/` directory
- Asserts: output file exists, non-empty, starts with `%PDF` magic bytes
- Tests both default mode and `--overview` mode
- Uses tmpdir for output cleanup

### 2. CLI Subprocess (`tests/test_cli_subprocess.py`)

- Invokes `subprocess.run([sys.executable, "-m", "elspais", ...])` for key commands
- Tests: `validate --mode core`, `index validate`, `pdf --output <tmp>`, `docs <topic>`, `--help`
- Asserts: return codes, expected stdout patterns
- PDF test uses `skipif` for pandoc availability

### 3. Tab Completion (`tests/test_completion.py`)

- Tests `_detect_shell()` with mocked `$SHELL` env var
- Tests `_get_rc_file()` returns correct paths per shell
- Tests `_install()` writes completion block to temp rc file
- Tests `_uninstall()` removes the block cleanly
- No external tool dependency — pure Python logic with temp files

### 4. MCP Protocol (`tests/mcp/test_mcp_protocol.py`)

- Uses `pytest.importorskip("mcp")`
- Starts MCP server via stdio transport in a subprocess
- Sends JSON-RPC 2.0 `tools/list` and `tools/call` messages
- Validates response structure matches MCP spec
- Tests at least one tool invocation end-to-end (e.g., `get_graph_status`)

## Homebrew

The formula in `Anspar-Org/homebrew-anspar` needs pandoc and texlive as dependencies for the `pdf` command. This is out of scope for this change — noted for a separate PR to that repo.

## Skip Pattern

All tool-dependent tests use:

```python
requires_pandoc = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc not found (install: https://pandoc.org/installing.html)",
)
```

Tests show as `SKIPPED` with the reason in verbose output. In the container, all tools are available so nothing skips.
