# Implements: REQ-p00001-A
"""
elspais.commands.completion - Shell tab-completion setup.

Generates and installs shell completion scripts using argcomplete.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _detect_shell() -> str:
    """Detect the current shell from environment."""
    shell = os.environ.get("SHELL", "")
    basename = Path(shell).name if shell else ""
    if basename in ("bash", "zsh", "fish", "tcsh"):
        return basename
    return "bash"  # default


def _get_rc_file(shell: str) -> Path:
    """Return the rc file path for a given shell."""
    home = Path.home()
    rc_files = {
        "bash": home / ".bashrc",
        "zsh": home / ".zshrc",
        "fish": home / ".config" / "fish" / "config.fish",
        "tcsh": home / ".tcshrc",
    }
    return rc_files.get(shell, home / ".bashrc")


_COMPLETION_MARKER = "# elspais shell completion"

_BASH_ZSH_SNIPPET = "# elspais shell completion\n" 'eval "$(register-python-argcomplete elspais)"\n'

_FISH_SNIPPET = (
    "# elspais shell completion\n" "register-python-argcomplete --shell fish elspais | source\n"
)

_TCSH_SNIPPET = (
    "# elspais shell completion\n" "eval `register-python-argcomplete --shell tcsh elspais`\n"
)


def _snippet_for(shell: str) -> str:
    """Return the completion snippet for a given shell."""
    if shell == "fish":
        return _FISH_SNIPPET
    if shell == "tcsh":
        return _TCSH_SNIPPET
    return _BASH_ZSH_SNIPPET


def _check_argcomplete() -> bool:
    """Check if argcomplete is installed."""
    try:
        import argcomplete  # noqa: F401

        return True
    except ImportError:
        return False


def maybe_show_completion_hint() -> None:
    """Show a one-line hint about shell completion when no command is given."""
    if not _check_argcomplete():
        print(
            "\nTip: Enable tab-completion with: pip install elspais[completion]",
            file=sys.stderr,
        )


def run(args) -> int:
    """Handle ``elspais completion`` command."""
    if not _check_argcomplete():
        print("Error: argcomplete is not installed.", file=sys.stderr)
        print("Install with: pip install elspais[completion]", file=sys.stderr)
        return 1

    shell = getattr(args, "shell", None) or _detect_shell()

    if getattr(args, "uninstall", False):
        return _uninstall(shell)

    if getattr(args, "install", False):
        return _install(shell)

    # Default: print manual instructions
    _print_instructions(shell)
    return 0


def _install(shell: str) -> int:
    """Install completion snippet into the shell rc file."""
    rc_file = _get_rc_file(shell)

    # Check if already installed
    if rc_file.exists():
        content = rc_file.read_text()
        if _COMPLETION_MARKER in content:
            print(f"Completion already installed in {rc_file}")
            return 0

    snippet = _snippet_for(shell)

    try:
        with open(rc_file, "a") as f:
            f.write("\n" + snippet)
        print(f"Installed completion in {rc_file}")
        print(f"Restart your shell or run: source {rc_file}")
        return 0
    except OSError as e:
        print(f"Error writing to {rc_file}: {e}", file=sys.stderr)
        return 1


def _uninstall(shell: str) -> int:
    """Remove completion snippet from the shell rc file."""
    rc_file = _get_rc_file(shell)

    if not rc_file.exists():
        print(f"No rc file found at {rc_file}")
        return 0

    content = rc_file.read_text()
    if _COMPLETION_MARKER not in content:
        print(f"No elspais completion found in {rc_file}")
        return 0

    # Remove lines belonging to the snippet
    lines = content.splitlines(keepends=True)
    filtered = []
    skip_next = False
    for line in lines:
        if _COMPLETION_MARKER in line:
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        filtered.append(line)

    try:
        rc_file.write_text("".join(filtered))
        print(f"Removed completion from {rc_file}")
        return 0
    except OSError as e:
        print(f"Error writing to {rc_file}: {e}", file=sys.stderr)
        return 1


def _print_instructions(shell: str) -> None:
    """Print manual setup instructions."""
    snippet = _snippet_for(shell)
    rc_file = _get_rc_file(shell)
    print(f"Shell completion for {shell}:")
    print()
    print(f"Add the following to {rc_file}:")
    print()
    print(f"  {snippet.strip().split(chr(10))[-1]}")
    print()
    print("Or auto-install with:")
    print()
    print(f"  elspais completion --install --shell {shell}")
