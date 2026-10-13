"""Run a project's own commands: fill a placeholder, and read a JSON answer.

A project names shell commands in its configuration: a prescan command, a
fetch command, a test target's command, a dependency source's command. Two
things recur across them, and each has one form here.

- A placeholder such as ``{dest}`` or ``{selection}`` is replaced by words,
  each quoted for the shell, so a path holding a space stays one word.
- A command handed paths on its standard input answers with JSON on its
  standard output. A non-zero exit, a timeout or unreadable output is a
  failure that names its cause, and each caller decides what a failure costs.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

#: The longest a command answering in JSON may run, in seconds.
JSON_COMMAND_TIMEOUT = 60


def fill_placeholder(command: str, placeholder: str, words: Iterable[str]) -> str:
    """Return *command* with every *placeholder* replaced by *words*, each shell-quoted."""
    return command.replace(placeholder, " ".join(shlex.quote(w) for w in words))


class CommandFailed(Exception):
    """A command gave no usable answer. The message names the cause."""


def run_json_command(
    command: str, stdin_lines: Iterable[str], cwd: Path, *, timeout: int = JSON_COMMAND_TIMEOUT
) -> Any:
    """Run *command* in *cwd* with one line per item on stdin; return its stdout read as JSON.

    Raises:
        CommandFailed: The command could not start, ran past *timeout*,
            exited non-zero, or printed something that is not JSON.
    """
    try:
        completed = subprocess.run(
            command,
            shell=True,
            input="\n".join(stdin_lines),
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandFailed(f"timed out after {timeout}s") from exc
    except OSError as exc:
        raise CommandFailed(f"could not start: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        raise CommandFailed(f"exited {completed.returncode}" + (f": {detail}" if detail else ""))
    try:
        return json.loads(completed.stdout)
    except ValueError as exc:
        raise CommandFailed(f"printed output that is not JSON: {exc}") from exc
