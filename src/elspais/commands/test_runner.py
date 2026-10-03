# Implements: REQ-d00249-B+C+L+M, REQ-d00312-D, REQ-d00311-B+C, REQ-d00314-C+D
"""Configured test-target dispatcher for the checks run-tests feature.

With a ``concurrency`` of one, each entry in ``[[scanning.test.targets]]`` that
has a ``command`` is executed in declaration order. A runner's output always
reaches the invoking terminal live: a file-channel target inherits the parent's
file descriptors, and a stdout-channel target -- whose stdout must be captured
for the reporter to parse (REQ-d00254-F) -- has that stdout piped, echoed line
by line to stderr as it arrives, and accumulated for the parser. stderr is
never piped, so it streams straight through in both cases. This module also
records timing and exit codes.

With a larger ``concurrency``, targets run at the same time, except that two
targets naming a common shared resource never overlap. Both streams of every
target are then piped, and each line is echoed with the target's name in front
of it, because lines from targets running together arrive interleaved.

Before a target runs, this module empties the output area and writes the
fingerprint. After the command exits, this module records each input that
changed during the run. ``ELSPAIS_TARGET_OUTPUT`` gives the command the path of
its output area.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from elspais.config.schema import ElspaisConfig


class SelectionRefused(Exception):
    """A selection of targets that no run executes. The message names what to change."""


# Implements: REQ-d00249-F+I, REQ-d00283-D+H+K+M+N+O, REQ-d00322-A
def executable_selection(
    config: ElspaisConfig,
    selected: list[str],
    *,
    require_command: bool = True,
    flag: str = "--targets",
) -> set[str] | None:
    """Resolve the ``--targets`` names of a run that executes targets.

    Both runs that execute targets call this function, the one that evaluates
    checks and the one that does not. Consequently, a name selects the same
    targets in both, and both refuse the same selections. Writing an
    *Evidence Snapshot* selects through it too, with *require_command*
    false: it reads results another job may have produced, so a selected
    target needs no command of its own.

    *flag* is the option the names came from, so a refusal names it.

    Returns the selected target names, or ``None`` for every configured target.

    Raises:
        SelectionRefused: A name is neither a target nor a group, the
            selection reaches no target, or (with *require_command*) no
            selected target has a command.
    """
    from elspais.config import (
        empty_selection_refusal,
        last_run_refusal,
        selected_targets,
        unknown_target_refusal,
    )

    # Implements: REQ-d00316-I
    if refusal := last_run_refusal(selected):
        raise SelectionRefused(refusal)
    # Targets and groups share one namespace. The config reader keeps their
    # names apart (REQ-d00283-G). If a name is neither a target nor a group,
    # then the run refuses it and does not resolve it to nothing.
    if refusal := unknown_target_refusal(config, selected, flag=flag):
        raise SelectionRefused(refusal)
    if refusal := empty_selection_refusal(config, selected, executes=True):
        raise SelectionRefused(refusal)
    # One authority resolves both selectors; None means every configured
    # target, which is what keeps a project declaring no groups rendering
    # exactly as it did before (REQ-d00254-J).
    try:
        only = selected_targets(config, selected or None)
    except ValueError as exc:
        raise SelectionRefused(str(exc)) from exc
    if require_command and not any(
        t.command and (only is None or t.name in only) for t in config.scanning.test.targets
    ):
        raise SelectionRefused(
            "a run that executes targets requires at least one "
            "[[scanning.test.targets]] entry with a command field "
            "(within the selected --targets when given; a run "
            "naming neither executes the `default` group). "
            "See docs/cli/test-targets.md for configuration examples."
        )
    return only


@dataclass(frozen=True)
class TargetRun:
    """The targets of one federation member that a run executes, and where."""

    namespace: str
    config: ElspaisConfig
    raw_config: dict[str, Any] | None
    repo_root: Path
    only: set[str] | None
    # Whether the targets belong to the invoking repository, whose targets a
    # reader names without a namespace.
    is_root: bool = True

    def spell(self, name: str) -> str:
        """Name *name* as the reader would select it."""
        from elspais.commands._targets import qualified_target

        return name if self.is_root else qualified_target(self.namespace, name)


# Implements: REQ-d00249-N, REQ-d00283-D+H+K
def plan_target_runs(
    config: ElspaisConfig,
    repo_root: Path,
    selected: list[str],
    *,
    raw_config: dict[str, Any] | None = None,
    require_command: bool = True,
) -> list[TargetRun]:
    """Resolve a run's ``--targets`` names into one run per federation member.

    A bare name, and a run naming nothing, select the invoking repository's
    targets through :func:`executable_selection`. A name written after a
    member's namespace and ``:`` selects that member's target or group,
    resolved by that member's own declarations. Only such a name reaches a
    member, because running a member's target executes a command that the
    member's configuration declares. Each run carries its member's
    configuration and repository root, so its targets execute there and write
    into that member's output area.

    *config* is the invoking repository's validated configuration and
    *raw_config* the document it was validated from, where the caller holds
    it: a run that builds a graph of the repository it selects needs it.

    Raises:
        SelectionRefused: A name is unknown to the member it names, names a
            namespace no member declares, or a member's selection is refused
            by :func:`executable_selection`.
    """
    from elspais.commands._targets import (
        federation_members,
        split_by_member,
        unknown_namespace_refusal,
    )

    root_cfg = config
    root_ns = root_cfg.project.namespace
    wanted = [n for n in (x.strip() for x in selected) if n]
    try:
        by_member = split_by_member(wanted, root_ns, flag="--targets")
        members = (
            federation_members(raw_config or root_cfg, root_cfg, repo_root, flag="--targets")
            if set(by_member) - {root_ns}
            else {}
        )
    except ValueError as exc:
        raise SelectionRefused(str(exc)) from exc

    runs: list[TargetRun] = []
    if not wanted or root_ns in by_member:
        only = executable_selection(
            root_cfg, by_member.get(root_ns, []), require_command=require_command
        )
        runs.append(TargetRun(root_ns, root_cfg, raw_config, repo_root, only))
    for namespace, names in by_member.items():
        if namespace == root_ns:
            continue
        member = members.get(namespace)
        if member is None:
            raise SelectionRefused(
                unknown_namespace_refusal(namespace, names, members, flag="--targets")
            )
        only = executable_selection(
            member.config,
            names,
            require_command=require_command,
            flag=f"--targets (member {namespace})",
        )
        runs.append(
            TargetRun(
                namespace,
                member.config,
                member.raw_config,
                member.repo_root,
                only,
                is_root=False,
            )
        )
    return runs


# Implements: REQ-d00249-K
def unrecorded_targets(config: ElspaisConfig, only: set[str] | None) -> list[str]:
    """The selected targets whose results a run that evaluates no check would lose.

    A target whose reporter reads results and which declares no ``results``
    pattern leaves nothing on disk. A run that evaluates checks reads such a
    target's output while it runs. A run that evaluates no check reads nothing.
    """
    from elspais.graph.parsers.results.registry import get_reporter

    lost = []
    for target in config.scanning.test.targets:
        if not target.command or (only is not None and target.name not in only):
            continue
        try:
            kind = get_reporter(target.reporter).kind
        except KeyError:
            continue  # tests.ingestion_fault names a reporter nothing reads
        if kind == "results" and not target.results:
            lost.append(target.name)
    return lost


# Implements: REQ-d00315-B+C+D+E+F
def not_fresh_targets(
    config: ElspaisConfig, repo_root: Path, only: set[str] | None
) -> tuple[set[str], set[str]]:
    """Divide the selected targets with a command by the freshness of their results.

    Returns ``(execute, carry)``. ``carry`` holds each selected target whose
    results :func:`elspais.utilities.fingerprint.judge` finds fresh. ``execute``
    holds every other one: stale, absent, or a run in progress. Only a fresh
    target has results worth carrying.
    """
    from elspais.utilities.fingerprint import judge

    cache: dict[Path, str] = {}
    execute: set[str] = set()
    carry: set[str] = set()
    for target in config.scanning.test.targets:
        if not target.command or (only is not None and target.name not in only):
            continue
        verdict = judge(repo_root, config, target.name, digest_cache=cache)
        (carry if verdict.state == "fresh" else execute).add(target.name)
    return execute, carry


# Implements: REQ-d00315-H
def describe_stale_only(execute: set[str], carry: set[str]) -> str:
    """State which selected targets a stale-only run executes and which it carries."""
    ran = ", ".join(sorted(execute)) or "none"
    kept = ", ".join(sorted(carry)) or "none"
    return f"stale-only: executing {ran}; carrying fresh results of {kept}"


@dataclass
class RunnerResult:
    name: str
    command: str
    cwd: Path
    returncode: int  # -1 if the runner could not be spawned at all
    duration_seconds: float
    error: str = ""  # populated only on spawn failure
    # False where the target was refused before its run began (a cwd outside
    # the repository), so its output area and results are untouched.
    started: bool = True

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


# Implements: REQ-d00249-B, REQ-d00254-F
def _run_teeing_stdout(
    command: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
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
        env=env,
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


# Implements: REQ-d00316-A+D, REQ-d00314-O
def run_configured_targets(
    config: ElspaisConfig,
    repo_root: Path,
    *,
    fail_fast: bool = False,
    only: set[str] | None = None,
    concurrency: int | None = None,
) -> tuple[list[RunnerResult], dict[str, str]]:
    """Execute the selected targets, then record which of them the run executed.

    *concurrency* replaces ``[scanning.test] concurrency`` for this run.
    Everything else is :func:`_run_targets`.
    """
    from elspais.utilities.fingerprint import write_last_run

    if concurrency is not None and concurrency < 1:
        raise ValueError(concurrency_refusal(concurrency))
    if concurrency is not None and concurrency != config.scanning.test.concurrency:
        test_cfg = config.scanning.test.model_copy(update={"concurrency": concurrency})
        config = config.model_copy(
            update={"scanning": config.scanning.model_copy(update={"test": test_cfg})}
        )
    results, captured = _run_targets(config, repo_root, fail_fast=fail_fast, only=only)
    write_last_run(repo_root, config, [r.name for r in results if r.started])
    return results, captured


# Implements: REQ-d00314-P
def concurrency_refusal(value: int) -> str:
    """The reason to refuse a run's maximum of simultaneous targets below one."""
    return (
        f"--concurrency {value} must be a whole number of targets, 1 or more; "
        f"1 runs the targets one at a time"
    )


# Implements: REQ-d00254-F+H
def _run_targets(
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
    from elspais.utilities.fingerprint import OUTPUT_ENV, finish_run, start_run

    if config.scanning.test.concurrency > 1:
        return _run_concurrently(config, repo_root, fail_fast=fail_fast, only=only)

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
                    started=False,
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
        folder = start_run(repo_root, config, target.name)
        env = {**os.environ, OUTPUT_ENV: str(folder)}
        try:
            if is_stdout_channel:
                completed = _run_teeing_stdout(target.command, cwd, env)
                captured[target.name] = completed.stdout
            else:
                completed = subprocess.run(
                    target.command,
                    shell=True,
                    cwd=cwd,
                    env=env,
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
        finish_run(repo_root, config, target.name)
        results.append(result)
        if fail_fast and result.returncode != 0:
            break
    return results, captured


# How long the pumps may drain a target's pipes after its command exits.
_DRAIN_SECONDS = 2.0

# One lock serialises every line this process writes while targets run
# together, so a line is never split by another target's line.
_OUTPUT_LOCK = threading.Lock()


def _emit(stream: TextIO, text: str) -> None:
    with _OUTPUT_LOCK:
        stream.write(text)
        stream.flush()


# Implements: REQ-d00314-J+L
def _pump(source: Any, prefix: str, echo: TextIO, keep: list[str] | None) -> None:
    """Echo each line of *source* with *prefix* in front of it; keep it unprefixed in *keep*."""
    for line in source:
        if keep is not None:
            keep.append(line)
        _emit(echo, prefix + (line if line.endswith("\n") else line + "\n"))


# Implements: REQ-d00314-J+K+L, REQ-d00249-B+L+M, REQ-d00312-D
def _run_one_attributed(
    config: ElspaisConfig, repo_root: Path, target: Any
) -> tuple[RunnerResult, str | None]:
    """Run one target with each line of its output marked with its name.

    Returns the result and, for a stdout-channel target, the stdout it wrote.
    """
    from elspais.graph.parsers.results.registry import get_reporter
    from elspais.utilities.fingerprint import OUTPUT_ENV, finish_run, start_run

    try:
        is_stdout_channel = get_reporter(target.reporter).channel == "stdout"
    except KeyError:
        is_stdout_channel = False

    resolved_root = repo_root.resolve()
    cwd = (repo_root / target.cwd).resolve() if target.cwd else resolved_root
    try:
        cwd.relative_to(resolved_root)
    except ValueError:
        err = f"cwd '{target.cwd}' resolves to {cwd} which is outside the repo root {resolved_root}"
        _emit(sys.stderr, f"\n<<< {target.name}: FAILED (config error: {err}) (0.0s)\n")
        return (
            RunnerResult(target.name, target.command, cwd, -1, 0.0, error=err, started=False),
            None,
        )

    prefix = f"[{target.name}] "
    _emit(sys.stderr, f"\n>>> Running '{target.name}' target: {target.command}\n")
    start = time.monotonic()
    # The fingerprint is taken here, as the command starts, and never earlier:
    # a target running alongside can change files while this one waits.
    folder = start_run(repo_root, config, target.name)
    env = {**os.environ, OUTPUT_ENV: str(folder)}
    kept: list[str] | None = [] if is_stdout_channel else None
    try:
        proc = subprocess.Popen(
            target.command,
            shell=True,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            bufsize=1,
        )
        # A stdout-channel target's stdout is its results, so it is echoed
        # to stderr, as a run of one target at a time echoes it.
        pumps = [
            threading.Thread(
                target=_pump,
                args=(
                    proc.stdout,
                    prefix,
                    sys.stderr if is_stdout_channel else sys.stdout,
                    kept,
                ),
                daemon=True,
            ),
            threading.Thread(
                target=_pump, args=(proc.stderr, prefix, sys.stderr, None), daemon=True
            ),
        ]
        for pump in pumps:
            pump.start()
        # The target ends when its command exits. A process the command left
        # in the background can hold the pipes open for as long as it lives,
        # so the pumps get a bounded time to drain what is already written.
        returncode = proc.wait()
        for pump in pumps:
            pump.join(_DRAIN_SECONDS)
        elapsed = time.monotonic() - start
        result = RunnerResult(target.name, target.command, cwd, returncode, elapsed)
        tag = "passed" if returncode == 0 else f"FAILED (exit {returncode})"
        _emit(sys.stderr, f"<<< {target.name}: {tag} ({elapsed:.1f}s)\n")
    except OSError as exc:
        elapsed = time.monotonic() - start
        result = RunnerResult(target.name, target.command, cwd, -1, elapsed, error=str(exc))
        _emit(
            sys.stderr,
            f"<<< {target.name}: FAILED (spawn error: {exc}) ({elapsed:.1f}s)\n",
        )
    finish_run(repo_root, config, target.name)
    return result, ("".join(list(kept)) if kept is not None else None)


def _resource_keys(target: Any) -> frozenset[str]:
    return frozenset(r.strip().lower() for r in target.resources if r.strip())


# Implements: REQ-d00314-H+I+M+N
def _run_concurrently(
    config: ElspaisConfig,
    repo_root: Path,
    *,
    fail_fast: bool,
    only: set[str] | None,
) -> tuple[list[RunnerResult], dict[str, str]]:
    """Run the selected targets, up to ``concurrency`` at a time.

    A waiting target starts as soon as a place is free and no running target
    names a shared resource it names. Waiting targets are considered in
    declaration order, and one held back by a resource does not hold back the
    targets after it. After a failure under *fail_fast* no further target
    starts, and the targets already running finish.
    """
    limit = config.scanning.test.concurrency
    order = [
        t for t in config.scanning.test.targets if t.command and (only is None or t.name in only)
    ]
    position = {t.name: i for i, t in enumerate(order)}
    pending = list(order)
    running: dict[Future[tuple[RunnerResult, str | None]], Any] = {}
    in_use: set[str] = set()
    results: list[RunnerResult] = []
    captured: dict[str, str] = {}
    stopping = False

    with ThreadPoolExecutor(max_workers=limit) as pool:
        while True:
            if not stopping:
                for target in list(pending):
                    if len(running) >= limit:
                        break
                    keys = _resource_keys(target)
                    if keys & in_use:
                        continue
                    pending.remove(target)
                    in_use |= keys
                    running[pool.submit(_run_one_attributed, config, repo_root, target)] = target
            if not running:
                break
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                target = running.pop(future)
                in_use -= _resource_keys(target)
                result, stdout_text = future.result()
                results.append(result)
                if stdout_text is not None:
                    captured[target.name] = stdout_text
                if fail_fast and result.returncode != 0:
                    stopping = True

    results.sort(key=lambda r: position[r.name])
    return results, captured
