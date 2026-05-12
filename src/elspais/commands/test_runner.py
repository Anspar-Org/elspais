# Implements: REQ-d00249-A+B+C
"""Configured test-runner dispatcher for the checks run-tests feature.

Each entry in ``[[scanning.test.runners]]`` is executed in declaration order
via ``subprocess.run(command, shell=True)`` -- the same pattern used by the
existing ``prescan_command`` plumbing in ``graph/factory.py``. stdout and
stderr are passed through to the parent process so users see test output
live; this module captures only timing and exit codes.
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


def run_configured_runners(
    config: ElspaisConfig,
    repo_root: Path,
    *,
    fail_fast: bool = False,
) -> list[RunnerResult]:
    """Execute each configured runner in declaration order.

    Args:
        config: Loaded `ElspaisConfig`.
        repo_root: Repository root; `cwd` overrides resolve relative to it.
        fail_fast: If True, stop after the first runner that exits non-zero
            (or fails to spawn). The failing result is included in the
            returned list.

    Returns:
        One `RunnerResult` per runner that was actually invoked.
    """
    results: list[RunnerResult] = []
    resolved_root = repo_root.resolve()
    for runner in config.scanning.test.runners:
        # Resolve cwd and confine it to the repo root. `Path` join honors an
        # absolute right-hand side, and `..` segments can escape upward, so
        # we explicitly verify the resolved path lives under the repo.
        cwd_candidate = (repo_root / runner.cwd).resolve() if runner.cwd else resolved_root
        try:
            cwd_candidate.relative_to(resolved_root)
        except ValueError:
            elapsed = 0.0
            err = (
                f"cwd '{runner.cwd}' resolves to {cwd_candidate} which is "
                f"outside the repo root {resolved_root}"
            )
            print(
                f"\n<<< {runner.name}: FAILED (config error: {err}) ({elapsed:.1f}s)",
                file=sys.stderr,
            )
            results.append(
                RunnerResult(
                    name=runner.name,
                    command=runner.command,
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
            f"\n>>> Running '{runner.name}' runner: {runner.command}",
            file=sys.stderr,
        )
        start = time.monotonic()
        try:
            completed = subprocess.run(
                runner.command,
                shell=True,
                cwd=cwd,
            )
            elapsed = time.monotonic() - start
            result = RunnerResult(
                name=runner.name,
                command=runner.command,
                cwd=cwd,
                returncode=completed.returncode,
                duration_seconds=elapsed,
            )
            tag = "passed" if completed.returncode == 0 else f"FAILED (exit {completed.returncode})"
            print(
                f"<<< {runner.name}: {tag} ({elapsed:.1f}s)",
                file=sys.stderr,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            elapsed = time.monotonic() - start
            result = RunnerResult(
                name=runner.name,
                command=runner.command,
                cwd=cwd,
                returncode=-1,
                duration_seconds=elapsed,
                error=str(exc),
            )
            print(
                f"<<< {runner.name}: FAILED (spawn error: {exc}) ({elapsed:.1f}s)",
                file=sys.stderr,
            )
        results.append(result)
        if fail_fast and result.returncode != 0:
            break
    return results
