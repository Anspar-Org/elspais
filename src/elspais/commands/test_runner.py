# Implements: REQ-d00249-A+B+C
"""Configured test-target dispatcher for the checks run-tests feature.

Each entry in ``[[scanning.test.targets]]`` that has a ``command`` is executed
in declaration order. A runner's output always reaches the invoking terminal
live: a file-channel target inherits the parent's file descriptors, and a
stdout-channel target -- whose stdout must be captured for the reporter to
parse (REQ-d00254-F) -- has that stdout piped, echoed line by line to stderr as
it arrives, and accumulated for the parser. stderr is never piped, so it
streams straight through in both cases. This module also records timing and
exit codes.
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


# Implements: REQ-d00249-B, REQ-d00254-F
def _run_teeing_stdout(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run ``command``, echoing its stdout live while also accumulating it.

    A stdout-channel reporter's output IS the results artifact, so it has to be
    captured for the parser (REQ-d00254-F) -- but capturing it must not cost the
    developer sight of the run (REQ-d00249-B). stdout is therefore piped and
    written back out line by line as it arrives, to stderr rather than stdout so
    that machine-format output (e.g. ``flutter test --machine`` JSON lines)
    cannot contaminate this process's own stdout, which may itself be a
    machine-readable report. stderr is left unpiped, so the runner's own
    diagnostics stream straight to the terminal and are never captured.
    """
    chunks: list[str] = []
    with subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            chunks.append(line)
            sys.stderr.write(line)
            sys.stderr.flush()
        returncode = proc.wait()
    return subprocess.CompletedProcess(command, returncode, "".join(chunks), None)


# Implements: REQ-d00254-F+H
def run_configured_targets(
    config: ElspaisConfig,
    repo_root: Path,
    *,
    fail_fast: bool = False,
    only: set[str] | None = None,
) -> tuple[list[RunnerResult], dict[str, str]]:
    """Execute each configured target's command in declaration order.

    For targets whose reporter channel is ``"stdout"``, stdout is piped so it can
    be returned in the ``captured`` map keyed by ``target.name``, and every line
    read is echoed to this process's stderr as it arrives so the developer sees
    the run live. For file-channel reporters stdout passes through to the parent
    process untouched. stderr is inherited in both cases and never captured.

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
                completed = _run_teeing_stdout(target.command, cwd)
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
