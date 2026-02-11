"""
elspais.utilities.version_check - Check for updates and detect install method.

Queries PyPI for the latest version and provides tailored upgrade instructions
based on how elspais was installed (pipx, pip, brew, editable dev install).
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PYPI_URL = "https://pypi.org/pypi/elspais/json"
TIMEOUT_SECONDS = 5


def fetch_latest_version() -> str | None:
    """Fetch the latest version of elspais from PyPI.

    Returns:
        Version string (e.g., "0.58.0") or None if the check fails.
    """
    try:
        req = urllib.request.Request(PYPI_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError):
        return None


def parse_version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse a PEP 440 version string into a comparable tuple.

    Handles versions like "0.58.0", "1.0.0a1" (strips pre-release suffix).
    """
    # Strip pre-release/dev suffixes for comparison
    clean = version_str.split("+")[0].split("a")[0].split("b")[0].split("rc")[0].split(".dev")[0]
    parts = []
    for part in clean.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            break
    return tuple(parts) if parts else (0,)


def is_newer(latest: str, current: str) -> bool:
    """Return True if latest is strictly newer than current."""
    return parse_version_tuple(latest) > parse_version_tuple(current)


def detect_install_method() -> str:
    """Detect how elspais was installed.

    Returns one of: "pipx", "brew", "venv", "user", "editable", "unknown"
    """
    try:
        import elspais

        install_path = Path(elspais.__file__).resolve()
    except (ImportError, AttributeError, TypeError):
        return "unknown"

    path_str = str(install_path)

    # Editable/dev install: source checkout (not in site-packages)
    if "site-packages" not in path_str:
        return "editable"

    # pipx: installed in ~/.local/pipx/venvs/
    if "pipx/venvs" in path_str:
        return "pipx"

    # Homebrew: /opt/homebrew/ (Apple Silicon) or /usr/local/Cellar/ (Intel Mac)
    if "/opt/homebrew/" in path_str or "/usr/local/Cellar/" in path_str:
        return "brew"

    # Virtual environment: check for VIRTUAL_ENV or venv-like path
    if sys.prefix != sys.base_prefix:
        return "venv"

    # pip --user: ~/.local/lib/ (Linux) or ~/Library/ (macOS)
    if "/.local/lib/" in path_str or "/Library/Python/" in path_str:
        return "user"

    return "unknown"


def get_upgrade_command(method: str) -> str:
    """Return the upgrade command for the detected install method."""
    commands = {
        "pipx": "pipx upgrade elspais",
        "brew": "brew upgrade elspais",
        "venv": "pip install --upgrade elspais",
        "user": "pip install --user --upgrade elspais",
        "editable": "git pull  # (editable install — update your source checkout)",
        "unknown": "pip install --upgrade elspais",
    }
    return commands.get(method, commands["unknown"])


def check_for_updates(current_version: str) -> int:
    """Check PyPI for a newer version and print upgrade instructions.

    Args:
        current_version: The currently installed version string.

    Returns:
        Exit code (0 = up to date or newer available, 1 = check failed).
    """
    print(f"Installed: elspais {current_version}")
    print("Checking PyPI for updates...", end=" ", flush=True)

    latest = fetch_latest_version()

    if latest is None:
        print("failed.")
        print("Could not reach PyPI. Check your network connection.", file=sys.stderr)
        return 1

    if is_newer(latest, current_version):
        print("update available!")
        print(f"  Latest:  {latest}")
        method = detect_install_method()
        cmd = get_upgrade_command(method)
        print(f"\nUpgrade with:\n  {cmd}")
    else:
        print(f"up to date. (latest: {latest})")

    return 0
