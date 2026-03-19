# Implements: REQ-p00001-A
"""
Shell completion script generation and installation.

Uses Tyro's built-in completion backend to generate bash/zsh/tcsh
completion scripts, installs them to standard shell locations, and
idempotently updates shell RC files.
"""
from __future__ import annotations

import glob
import os
import re
import sys
from pathlib import Path

# Shell → (script install path, RC file path, fpath line needed)
_SHELL_CONFIG: dict[str, dict[str, Path | str | None]] = {
    "bash": {
        "script_path": (
            Path.home() / ".local" / "share" / "bash-completion" / "completions" / "elspais"
        ),
        "rc_file": Path.home() / ".bashrc",
        # bash-completion auto-loads from this dir; no RC entry needed
        "rc_block": None,
    },
    "zsh": {
        "script_path": Path.home() / ".zfunc" / "_elspais",
        "rc_file": Path.home() / ".zshrc",
        "rc_block": (
            "# elspais shell completion\n"
            "fpath=(~/.zfunc $fpath)\n"
            "autoload -Uz compinit && compinit"
        ),
    },
    "tcsh": {
        "script_path": Path.home() / ".config" / "elspais" / "completion.tcsh",
        "rc_file": Path.home() / ".tcshrc",
        "rc_block": "# elspais shell completion\nsource {script_path}",
    },
}

# Patterns to detect and remove stale argcomplete entries
_ARGCOMPLETE_PATTERNS = [
    re.compile(r'^eval "\$\(register-python-argcomplete elspais\)"$'),
    # Comment lines that precede argcomplete evals (but NOT our own marker)
    re.compile(
        r"^#.*(?:Autocompletion for elspais|elspais shell tab-completion).*$",
        re.IGNORECASE,
    ),
]


def _detect_shell() -> str | None:
    """Auto-detect shell from $SHELL environment variable."""
    shell_env = os.environ.get("SHELL", "")
    basename = Path(shell_env).name if shell_env else ""
    if basename in ("bash", "zsh", "tcsh"):
        return basename
    return None


def _generate_completion(shell: str) -> str:
    """Generate completion script content for the given shell."""
    import tempfile

    from elspais.cli import main

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        tmp_path = f.name

    old_argv0 = sys.argv[0]
    sys.argv[0] = "elspais"
    try:
        main(["--tyro-write-completion", shell, tmp_path])
    except SystemExit:
        pass
    finally:
        sys.argv[0] = old_argv0

    content = Path(tmp_path).read_text()
    Path(tmp_path).unlink(missing_ok=True)

    # Tyro's zsh generator names the function _tyro_<prog> but the
    # #compdef directive makes zsh autoload it as _<prog>.  Rename so
    # the function name matches the file name for zsh autoload.
    if shell == "zsh":
        content = content.replace("_tyro_elspais", "_elspais")

    return content


def _clear_zsh_compdump() -> int:
    """Remove stale zsh completion cache files.

    Returns the number of files removed.
    """
    removed = 0
    for path in glob.glob(os.path.join(Path.home(), ".zcompdump*")):
        try:
            Path(path).unlink()
            removed += 1
        except OSError:
            pass
    return removed


def _remove_argcomplete_lines(rc_path: Path) -> int:
    """Remove stale argcomplete entries from an RC file.

    Returns the number of lines removed.
    """
    if not rc_path.is_file():
        return 0

    lines = rc_path.read_text().splitlines(keepends=True)
    cleaned: list[str] = []
    removed = 0
    skip_blank_after_removal = False

    for line in lines:
        stripped = line.rstrip("\n")
        is_stale = any(p.match(stripped) for p in _ARGCOMPLETE_PATTERNS)
        if is_stale:
            removed += 1
            skip_blank_after_removal = True
            continue
        # Collapse extra blank lines left by removal
        if skip_blank_after_removal and stripped == "":
            skip_blank_after_removal = False
            continue
        skip_blank_after_removal = False
        cleaned.append(line)

    if removed:
        rc_path.write_text("".join(cleaned))

    return removed


def _rc_has_block(rc_path: Path, marker: str) -> bool:
    """Check if the RC file already contains the elspais completion block."""
    if not rc_path.is_file():
        return False
    content = rc_path.read_text()
    # Check for the marker comment or the fpath line (handles orphaned blocks)
    return marker in content or "fpath=(~/.zfunc $fpath)" in content


def _append_rc_block(rc_path: Path, block: str) -> None:
    """Append the completion block to the RC file."""
    content = rc_path.read_text() if rc_path.is_file() else ""
    # Ensure trailing newline before our block
    if content and not content.endswith("\n"):
        content += "\n"
    if not content.endswith("\n\n") and content:
        content += "\n"
    content += block + "\n"
    rc_path.write_text(content)


def _remove_rc_block(rc_path: Path) -> bool:
    """Remove the elspais completion block from the RC file.

    Returns True if a block was removed.
    """
    if not rc_path.is_file():
        return False

    content = rc_path.read_text()
    # Remove the block including the comment marker and associated lines
    # Match: comment line + fpath/source line(s) + compinit line (if present)
    patterns = [
        # zsh: comment + fpath + compinit (3 lines)
        re.compile(
            r"\n?# elspais shell completion\n"
            r"fpath=\(~/.zfunc \$fpath\)\n"
            r"autoload -Uz compinit && compinit\n?",
        ),
        # tcsh: comment + source line
        re.compile(
            r"\n?# elspais shell completion\n" r"source [^\n]+completion\.tcsh\n?",
        ),
    ]

    for pattern in patterns:
        new_content = pattern.sub("\n", content)
        if new_content != content:
            # Clean up double blank lines
            new_content = re.sub(r"\n{3,}", "\n\n", new_content)
            rc_path.write_text(new_content)
            return True

    return False


def cmd_install(shell: str | None) -> int:
    """Generate and install completion script, updating shell RC files."""
    if shell is None:
        shell = _detect_shell()
        if shell is None:
            print(
                "Could not detect shell from $SHELL. " "Specify one with --shell {bash,zsh,tcsh}.",
                file=sys.stderr,
            )
            return 1

    if shell not in _SHELL_CONFIG:
        print(f"Unsupported shell: {shell}", file=sys.stderr)
        return 1

    config = _SHELL_CONFIG[shell]
    script_path: Path = config["script_path"]  # type: ignore[assignment]
    rc_file: Path = config["rc_file"]  # type: ignore[assignment]
    rc_block: str | None = config["rc_block"]  # type: ignore[assignment]

    # Generate the completion script
    script = _generate_completion(shell)
    if not script:
        print("Error: completion script generation failed.", file=sys.stderr)
        return 1

    # Install the script
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script)
    print(f"Installed {shell} completions to {script_path}")

    # Remove stale argcomplete entries from RC file
    stale_removed = _remove_argcomplete_lines(rc_file)
    if stale_removed:
        print(f"Removed {stale_removed} stale argcomplete line(s) from {rc_file}")

    # Clear zsh cache if applicable
    if shell == "zsh":
        cache_cleared = _clear_zsh_compdump()
        if cache_cleared:
            print(f"Cleared {cache_cleared} stale zsh cache file(s)")

    # Idempotently add RC block
    if rc_block is not None:
        formatted_block = rc_block.format(script_path=script_path)
        marker = "# elspais shell completion"
        if _rc_has_block(rc_file, marker):
            print(f"Shell config already set up in {rc_file}")
        else:
            _append_rc_block(rc_file, formatted_block)
            print(f"Added completion config to {rc_file}")

    print()
    print("To activate:  exec " + shell)
    return 0


def cmd_uninstall(shell: str | None) -> int:
    """Remove installed completion script and RC entries."""
    if shell is None:
        shell = _detect_shell()
        if shell is None:
            print(
                "Could not detect shell from $SHELL. " "Specify one with --shell {bash,zsh,tcsh}.",
                file=sys.stderr,
            )
            return 1

    if shell not in _SHELL_CONFIG:
        print(f"Unsupported shell: {shell}", file=sys.stderr)
        return 1

    config = _SHELL_CONFIG[shell]
    script_path: Path = config["script_path"]  # type: ignore[assignment]
    rc_file: Path = config["rc_file"]  # type: ignore[assignment]

    # Remove script file
    if script_path.exists():
        script_path.unlink()
        print(f"Removed {shell} completions from {script_path}")
    else:
        print(f"No {shell} completions found at {script_path}")

    # Remove stale argcomplete entries
    stale_removed = _remove_argcomplete_lines(rc_file)
    if stale_removed:
        print(f"Removed {stale_removed} stale argcomplete line(s) from {rc_file}")

    # Remove RC block
    if _remove_rc_block(rc_file):
        print(f"Removed completion config from {rc_file}")

    # Clear zsh cache
    if shell == "zsh":
        cache_cleared = _clear_zsh_compdump()
        if cache_cleared:
            print(f"Cleared {cache_cleared} zsh cache file(s)")

    return 0


def run(args) -> int:
    """Entry point for the completion command."""
    action = getattr(args, "completion_action", None)
    shell = getattr(args, "shell", None)

    if action == "install":
        return cmd_install(shell)
    elif action == "uninstall":
        return cmd_uninstall(shell)
    else:
        print("Usage: elspais completion install [--shell {bash,zsh,tcsh}]")
        print("       elspais completion uninstall [--shell {bash,zsh,tcsh}]")
        return 0
