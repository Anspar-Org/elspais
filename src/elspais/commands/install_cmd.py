# Implements: REQ-p00001-A
"""
elspais.commands.install_cmd - Manage elspais installation (local dev / PyPI).

Provides install/uninstall of local editable development versions,
replacing the current global pipx/uv installation.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def detect_tool(preferred: str | None = None) -> str | None:
    """Detect available package tool (pipx or uv).

    Args:
        preferred: If set, only check this tool.

    Returns:
        Tool name ("pipx" or "uv") or None if not found.
    """
    if preferred:
        return preferred if shutil.which(preferred) else None

    for tool in ("pipx", "uv"):
        if shutil.which(tool):
            return tool
    return None


def find_source_root(override_path: Path | None = None) -> Path | None:
    """Find the elspais source root directory.

    Walks up from this file's location to find pyproject.toml
    with name="elspais".

    Args:
        override_path: Explicit path to use instead of auto-detection.

    Returns:
        Path to source root, or None if not found.
    """
    if override_path:
        return _validate_source_root(override_path)

    current = Path(__file__).resolve().parent
    while current != current.parent:
        candidate = current / "pyproject.toml"
        if candidate.exists() and _is_elspais_project(candidate):
            return current
        current = current.parent
    return None


def _validate_source_root(path: Path) -> Path | None:
    """Validate that a path is an elspais source root."""
    path = path.resolve()
    pyproject = path / "pyproject.toml"
    if pyproject.exists() and _is_elspais_project(pyproject):
        return path
    return None


def _is_elspais_project(pyproject_path: Path) -> bool:
    """Check if a pyproject.toml belongs to the elspais project."""
    import tomlkit

    try:
        content = pyproject_path.read_text(encoding="utf-8")
        data = tomlkit.parse(content)
        return data.get("project", {}).get("name") == "elspais"
    except Exception:
        return False


def detect_installed_extras() -> list[str]:
    """Detect which elspais extras are currently installed.

    Returns:
        List of extra names that have their dependencies satisfied.
    """
    import importlib.util

    extras_deps: dict[str, list[str]] = {
        "mcp": ["mcp"],
        "trace-view": ["jinja2", "pygments"],
        "trace-review": ["jinja2", "pygments", "flask", "flask_cors"],
        "completion": ["argcomplete"],
    }

    installed = []
    for extra, deps in extras_deps.items():
        if all(importlib.util.find_spec(dep) is not None for dep in deps):
            installed.append(extra)

    # trace-review is a superset of trace-view; don't duplicate
    if "trace-review" in installed and "trace-view" in installed:
        installed.remove("trace-view")

    return installed


def _build_install_spec(base: str, extras: list[str] | None) -> str:
    """Build a pip/pipx install spec string with optional extras."""
    if extras:
        return f"{base}[{','.join(extras)}]"
    return base


def install_local(
    source_root: Path,
    tool: str,
    extras: list[str] | None = None,
    verbose: bool = False,
) -> int:
    """Install elspais from local source as editable.

    Args:
        source_root: Path to the elspais source directory.
        tool: Package tool to use ("pipx" or "uv").
        extras: Optional extras to install (e.g., ["mcp", "all"]).
        verbose: Show subprocess output.

    Returns:
        Exit code (0 = success).
    """
    install_spec = _build_install_spec(str(source_root), extras)

    if tool == "pipx":
        return _pipx_install_editable(source_root, install_spec, extras, verbose)
    elif tool == "uv":
        cmd = ["uv", "tool", "install", "--editable", install_spec, "--force"]
    else:
        print(f"Error: Unsupported tool '{tool}'", file=sys.stderr)
        return 1

    print(f"Installing local elspais from {source_root}")
    if extras:
        print(f"  Extras: {', '.join(extras)}")
    print(f"  Using: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=not verbose,
        text=True,
    )

    if result.returncode != 0:
        print(
            f"Error: Installation failed (exit code {result.returncode})",
            file=sys.stderr,
        )
        if not verbose and result.stderr:
            print(result.stderr, file=sys.stderr)
        return 1

    _patch_argcomplete_marker()
    _show_active_version()
    _print_shell_hint()
    return 0


def _pipx_install_editable(
    source_root: Path,
    install_spec: str,
    extras: list[str] | None,
    verbose: bool,
) -> int:
    """Install editable into pipx using a two-step workaround.

    pipx 1.x silently ignores --editable for local paths, doing a regular
    install instead. We work around this by:
    1. ``pipx install <path> --force`` to create the venv + entry point
    2. ``pipx runpip elspais install -e <path>[extras]`` to replace the
       package inside the venv with a true editable install
    """
    capture = not verbose

    # Step 1: create the venv with entry point
    step1_cmd = ["pipx", "install", str(source_root), "--force"]
    print(f"Installing local elspais from {source_root}")
    if extras:
        print(f"  Extras: {', '.join(extras)}")
    print(f"  Step 1: {' '.join(step1_cmd)}")

    result = subprocess.run(step1_cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print("Error: pipx install failed", file=sys.stderr)
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        return 1

    # Step 2: replace with editable install inside the venv
    step2_cmd = ["pipx", "runpip", "elspais", "install", "-e", install_spec]
    print(f"  Step 2: {' '.join(step2_cmd)}")

    result = subprocess.run(step2_cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print("Error: editable install into pipx venv failed", file=sys.stderr)
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        return 1

    _patch_argcomplete_marker()
    _show_active_version()
    _print_shell_hint()
    return 0


def uninstall_local(
    tool: str,
    extras: list[str] | None = None,
    version: str | None = None,
    verbose: bool = False,
) -> int:
    """Revert to PyPI release version.

    Uses a two-step process: uninstall first, then install fresh.
    This is necessary because ``pipx install --force`` caches the local
    source path from editable installs and silently reuses it instead
    of fetching from PyPI.

    Args:
        tool: Package tool to use ("pipx" or "uv").
        extras: Extras to install with the PyPI version.
        version: Specific PyPI version to install (default: latest).
        verbose: Show subprocess output.

    Returns:
        Exit code (0 = success).
    """
    base = f"elspais=={version}" if version else "elspais"
    install_spec = _build_install_spec(base, extras)
    capture = not verbose

    if tool == "pipx":
        uninstall_cmd = ["pipx", "uninstall", "elspais"]
        install_cmd = ["pipx", "install", install_spec]
    elif tool == "uv":
        uninstall_cmd = ["uv", "tool", "uninstall", "elspais"]
        install_cmd = ["uv", "tool", "install", install_spec]
    else:
        print(f"Error: Unsupported tool '{tool}'", file=sys.stderr)
        return 1

    print("Reverting to PyPI version of elspais")
    if extras:
        print(f"  Extras: {', '.join(extras)}")
    if version:
        print(f"  Version: {version}")

    # Step 1: fully remove the current install (clears cached paths)
    print(f"  Step 1: {' '.join(uninstall_cmd)}")
    result = subprocess.run(uninstall_cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print("Error: Uninstall failed", file=sys.stderr)
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        return 1

    # Step 2: fresh install from PyPI
    print(f"  Step 2: {' '.join(install_cmd)}")
    result = subprocess.run(install_cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(
            f"Error: Installation failed (exit code {result.returncode})",
            file=sys.stderr,
        )
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        return 1

    _patch_argcomplete_marker()
    _show_active_version()
    _print_shell_hint()
    return 0


def _patch_argcomplete_marker() -> None:
    """Inject PYTHON_ARGCOMPLETE_OK marker into the elspais entry point.

    pip/pipx-generated console scripts don't include the magic comment
    that argcomplete's shell function checks (first 1024 bytes) to
    decide whether to activate completion. Without it, tab-completion
    silently stops working after a reinstall.
    """
    entry_point = shutil.which("elspais")
    if not entry_point:
        return

    marker = "# PYTHON_ARGCOMPLETE_OK"
    try:
        script = Path(entry_point).read_text(encoding="utf-8")
        if marker in script:
            return  # already patched

        # Insert marker after the shebang line
        lines = script.split("\n", 1)
        if len(lines) == 2 and lines[0].startswith("#!"):
            patched = f"{lines[0]}\n{marker}\n{lines[1]}"
            Path(entry_point).write_text(patched, encoding="utf-8")
            print(f"  Patched {entry_point} with {marker}")
    except (OSError, PermissionError) as e:
        print(f"  Warning: Could not patch argcomplete marker: {e}", file=sys.stderr)


def _show_active_version() -> None:
    """Print the currently active elspais version."""
    try:
        result = subprocess.run(
            ["elspais", "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  Active: {result.stdout.strip()}")
    except FileNotFoundError:
        print("  Warning: elspais command not found in PATH", file=sys.stderr)


def _print_shell_hint() -> None:
    """Print shell commands the user should run to refresh their session.

    After pipx/uv reinstalls the binary, the shell's command hash table
    and completion functions are stale. We print the exact commands to
    run — but never source rc files automatically.
    """
    import os

    shell_path = os.environ.get("SHELL", "")
    shell = Path(shell_path).name if shell_path else ""

    print("\n  To activate in this shell, run:")

    if shell == "zsh":
        print("    rehash")
        print('    eval "$(register-python-argcomplete elspais)"')
    elif shell == "bash":
        print("    hash -r")
        print('    eval "$(register-python-argcomplete elspais)"')
    elif shell == "fish":
        print("    register-python-argcomplete --shell fish elspais | source")
    elif shell == "tcsh":
        print("    rehash")
        print("    eval `register-python-argcomplete --shell tcsh elspais`")
    else:
        print("    hash -r  # or rehash, depending on your shell")


# --- CLI dispatchers ---


def run(args: argparse.Namespace) -> int:
    """Dispatch install subcommand."""
    action = getattr(args, "install_action", None)
    if action == "local":
        return _run_install_local(args)
    print("Usage: elspais install local [options]", file=sys.stderr)
    return 1


def run_uninstall(args: argparse.Namespace) -> int:
    """Dispatch uninstall subcommand."""
    action = getattr(args, "uninstall_action", None)
    if action == "local":
        return _run_uninstall_local(args)
    print("Usage: elspais uninstall local [options]", file=sys.stderr)
    return 1


def _run_install_local(args: argparse.Namespace) -> int:
    """Handle 'elspais install local'."""
    verbose = getattr(args, "verbose", False)
    tool_name = getattr(args, "tool", None)
    tool = detect_tool(tool_name)
    if tool is None:
        if tool_name:
            print(f"Error: '{tool_name}' not found in PATH.", file=sys.stderr)
        else:
            print("Error: Neither pipx nor uv found in PATH.", file=sys.stderr)
            print("Install pipx: python -m pip install pipx", file=sys.stderr)
            print(
                "Install uv:   curl -LsSf https://astral.sh/uv/install.sh | sh",
                file=sys.stderr,
            )
        return 1

    override = Path(args.path) if getattr(args, "path", None) else None
    source_root = find_source_root(override)
    if source_root is None:
        if override:
            print(
                f"Error: '{override}' is not an elspais source directory.",
                file=sys.stderr,
            )
        else:
            print("Error: Cannot find elspais source directory.", file=sys.stderr)
            print(
                "Use --path to specify the source directory explicitly.",
                file=sys.stderr,
            )
        return 1

    extras = _parse_extras(args)
    return install_local(source_root, tool, extras, verbose)


def _run_uninstall_local(args: argparse.Namespace) -> int:
    """Handle 'elspais uninstall local'."""
    verbose = getattr(args, "verbose", False)
    tool_name = getattr(args, "tool", None)
    tool = detect_tool(tool_name)
    if tool is None:
        if tool_name:
            print(f"Error: '{tool_name}' not found in PATH.", file=sys.stderr)
        else:
            print("Error: Neither pipx nor uv found in PATH.", file=sys.stderr)
        return 1

    extras = _parse_extras(args)
    version_arg = getattr(args, "version", None)
    return uninstall_local(tool, extras, version_arg, verbose)


def _parse_extras(args: argparse.Namespace) -> list[str] | None:
    """Parse --extras argument or auto-detect installed extras."""
    extras_arg = getattr(args, "extras", None)
    if extras_arg:
        return [e.strip() for e in extras_arg.split(",")]
    detected = detect_installed_extras()
    return detected or None
