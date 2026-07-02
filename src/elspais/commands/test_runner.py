# Implements: REQ-d00249-A+B+C
"""Configured test-target dispatcher for the checks run-tests feature.

Each entry in ``[[scanning.test.targets]]`` that has a ``command`` is executed
in declaration order via ``subprocess.run(command, shell=True)``. stdout/stderr
pass-through vs. capture depends on the reporter channel; this module
captures timing, exit codes, and stdout for stdout-channel reporters.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from elspais.config.schema import ElspaisConfig


@dataclass
class RunnerResult:
    name: str
    command: str
    cwd: Path
    returncode: int  # -1 if the runner could not be spawned at all
    duration_seconds: float
    error: str = ""  # populated only on spawn failure

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


# Implements: REQ-d00254-F+H
def run_configured_targets(
    config: ElspaisConfig,
    repo_root: Path,
    *,
    fail_fast: bool = False,
    only: set[str] | None = None,
) -> tuple[list[RunnerResult], dict[str, str]]:
    """Execute each configured target's command in declaration order.

    For targets whose reporter channel is ``"stdout"``, stdout is captured and
    returned in the ``captured`` map keyed by ``target.name``; for file-channel
    reporters stdout passes through to the parent process.

    Args:
        config: Loaded `ElspaisConfig`.
        repo_root: Repository root; `cwd` overrides resolve relative to it.
        fail_fast: If True, stop after the first target that exits non-zero
            (or fails to spawn).
        only: If given, restricts execution to targets whose ``name`` is in
            this set; all other configured targets are skipped entirely.
            ``None`` (the default) runs every target with a command.

    Returns:
        A tuple ``(results, captured)`` where ``results`` is one
        ``RunnerResult`` per target that was actually invoked (command non-empty)
        and ``captured`` maps target name → stdout text for stdout-channel
        reporters.
    """
    from elspais.graph.parsers.results.registry import get_reporter

    results: list[RunnerResult] = []
    captured: dict[str, str] = {}
    resolved_root = repo_root.resolve()

    for target in config.scanning.test.targets:
        if not target.command:
            continue
        if only is not None and target.name not in only:
            continue

        # Determine whether this reporter captures stdout.
        try:
            spec = get_reporter(target.reporter)
            is_stdout_channel = spec.channel == "stdout"
        except KeyError:
            is_stdout_channel = False

        # Resolve cwd and confine it to the repo root.
        cwd_candidate = (repo_root / target.cwd).resolve() if target.cwd else resolved_root
        try:
            cwd_candidate.relative_to(resolved_root)
        except ValueError:
            elapsed = 0.0
            err = (
                f"cwd '{target.cwd}' resolves to {cwd_candidate} which is "
                f"outside the repo root {resolved_root}"
            )
            print(
                f"\n<<< {target.name}: FAILED (config error: {err}) ({elapsed:.1f}s)",
                file=sys.stderr,
            )
            results.append(
                RunnerResult(
                    name=target.name,
                    command=target.command,
                    cwd=cwd_candidate,
                    returncode=-1,
                    duration_seconds=elapsed,
                    error=err,
                )
            )
            if fail_fast:
                break
            continue

        cwd = cwd_candidate
        print(
            f"\n>>> Running '{target.name}' target: {target.command}",
            file=sys.stderr,
        )
        start = time.monotonic()
        try:
            if is_stdout_channel:
                completed = subprocess.run(
                    target.command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                )
                captured[target.name] = completed.stdout
            else:
                completed = subprocess.run(
                    target.command,
                    shell=True,
                    cwd=cwd,
                )
            elapsed = time.monotonic() - start
            result = RunnerResult(
                name=target.name,
                command=target.command,
                cwd=cwd,
                returncode=completed.returncode,
                duration_seconds=elapsed,
            )
            tag = "passed" if completed.returncode == 0 else f"FAILED (exit {completed.returncode})"
            print(
                f"<<< {target.name}: {tag} ({elapsed:.1f}s)",
                file=sys.stderr,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            elapsed = time.monotonic() - start
            result = RunnerResult(
                name=target.name,
                command=target.command,
                cwd=cwd,
                returncode=-1,
                duration_seconds=elapsed,
                error=str(exc),
            )
            print(
                f"<<< {target.name}: FAILED (spawn error: {exc}) ({elapsed:.1f}s)",
                file=sys.stderr,
            )
        results.append(result)
        if fail_fast and result.returncode != 0:
            break
    return results, captured
