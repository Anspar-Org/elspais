# Implements: REQ-d00054-A
# Implements: REQ-d00128-A, REQ-d00128-B, REQ-d00128-C, REQ-d00128-G, REQ-d00128-H
"""Graph Factory - Shared utility for building TraceGraph from spec files.

This module provides a single entry point for all commands to build a TraceGraph
from configuration and spec directories. Commands should use this instead of
implementing their own file reading logic.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from glob import glob
from pathlib import Path, PurePosixPath
from typing import Any

from elspais.config import (
    config_document_paths,
    find_config_file,
    get_code_directories,
    get_config,
    get_spec_directories,
    parse_toml_document,
    scan_exclusions,
)
from elspais.config.schema import (
    DEFAULT_CODE_PATTERNS,
    DEFAULT_TEST_PATTERNS,
    ElspaisConfig,
)
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.declarations import build_declaration_nodes
from elspais.graph.deserializer import DomainFile
from elspais.graph.federated import FederatedGraph
from elspais.graph.federation_plan import (
    PlannedRepo,
    declared_associates,
    plan_federation,
    refuse_unreadable,
)
from elspais.graph.GraphNode import (
    FileType,
    GraphNode,
    NodeKind,
    make_file_id,
    make_result_id,
)
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.journey import JourneyParser
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.parsers.patterns import (
    KEYWORD_PATTERN,
    METADATA_COMMENT_MARKERS,
    comment_markers_for_path,
)
from elspais.graph.parsers.remainder import RemainderParser
from elspais.utilities.patterns import FederatedIdReader, IdResolver, build_resolver

_log = logging.getLogger(__name__)


# Implements: REQ-d00254-Y
def _resolve_coverage_file_node(graph, source_file, working_dir, repo_root):
    """The FILE node a coverage artifact's source path names, or None.

    A relative path is read against *working_dir*, the directory the target
    ran in, because the measuring tool wrote it from there. An absolute path
    is read as it stands. A path that names no scanned file of this
    repository resolves to nothing.

    The path is placed in the repository as written first, and through
    symbolic links second: a tool may record either spelling.
    """
    root = Path(repo_root).absolute()
    named = Path(os.path.normpath(Path(working_dir).absolute() / source_file))
    try:
        rel = named.relative_to(Path(os.path.normpath(root)))
    except ValueError:
        try:
            rel = named.resolve().relative_to(root.resolve())
        except ValueError:
            return None
    # Coverage is ingested into the repository whose graph this is, so the
    # id is written in that repository's namespace.
    return graph.find_by_id(make_file_id(graph.namespace, rel.as_posix()))


# Implements: REQ-d00254-F, REQ-d00254-I
# Implements: REQ-d00284-B
def _tests_named(name: str, scanned: frozenset[str]) -> list[str]:
    """The scanned test files *name* picks out, as repo-relative paths.

    A name matches a file whose path ends at a component boundary, so a bare
    basename reaches a test nested any depth below the target and a name
    carrying directories still has to match them. The candidates are the files
    scanned for the target that produced the result: a name matching a file
    some other target scans says nothing about where this result came from.
    """
    needle = name.replace("\\", "/").strip("/")
    if not needle:
        return []
    return sorted(p for p in scanned if p == needle or p.endswith("/" + needle))


# Implements: REQ-d00285-A
def _repo_relative(path: str | Path, repo_root: Path) -> str:
    """*path* as the repository sees it, or unchanged where it is elsewhere.

    A finding names a file the way the reader will look for it. Everything
    else the graph records about a file is repo-relative, and a finding that
    alone spelled it absolutely would not line up with any of it.
    """
    try:
        return str(Path(path).resolve().relative_to(Path(repo_root).resolve()))
    except ValueError:
        return str(path)


# Implements: REQ-d00285-F, REQ-d00285-G
def _unknown_reporter_cause(reporter: str) -> str:
    """The one wording for a target naming a reporter nothing reads.

    Two places detect it -- the ingestion loop, and the ingestion function
    called from anywhere else -- and one condition reported under two
    descriptions reads as two conditions.
    """
    from elspais.graph.parsers.results.registry import REPORTER_REGISTRY

    return (
        f"no reporter named {reporter!r}; nothing reads this target's results. "
        f"Known reporters: {', '.join(sorted(REPORTER_REGISTRY))}"
    )


# Implements: REQ-d00285-G
def _record_parser_diagnostics(
    recorder: Any,
    parser: Any,
    stage: str,
    target_name: str | None,
    fallback_path: str,
    repo_root: Path,
) -> None:
    """Lift what a results parser declined to read onto the graph.

    ``recorder`` is whatever holds the ingestion faults -- the builder while the graph
    is being built, the graph itself once it is. A parser that records
    nothing contributes nothing.
    """
    iter_diagnostics = getattr(parser, "iter_diagnostics", None)
    if iter_diagnostics is None:
        return
    for diagnostic in iter_diagnostics():
        recorder.record_ingestion_fault(
            path=_repo_relative(diagnostic.path or fallback_path, repo_root),
            stage=stage,
            cause=diagnostic.cause,
            line=diagnostic.line,
            target=target_name,
            partial=getattr(diagnostic, "partial", False),
        )


_WILDCARD_CHARS = "*?["


# Implements: REQ-d00294-C+D
def _environment_from_path(pattern: str, base: Path, path: str) -> tuple[str | None, str, bool]:
    """The environment a results file sits under, read from its own path.

    One grid writes one artifact for each device, under a directory named
    for it, and the glob that finds them holds one wildcard. That wildcard
    segment is the environment, so the answer is the part of the real path
    the wildcard stood for.

    Returns the environment, the reason there is none, and whether that
    reason is about the pattern alone. A pattern the tool cannot read is
    one condition however many files it matched, so the caller reports it
    against the pattern rather than against each of them.
    """
    pattern_parts = [p for p in PurePosixPath(pattern.replace(os.sep, "/")).parts if p != "."]
    if any("**" in part for part in pattern_parts):
        return None, "the pattern holds `**`, which stands for any number of directories", True
    wildcards = [
        i for i, part in enumerate(pattern_parts) if any(c in part for c in _WILDCARD_CHARS)
    ]
    if len(wildcards) != 1:
        return (
            None,
            f"the pattern holds {len(wildcards)} wildcard segments, "
            f"so no one segment names the environment",
            True,
        )
    try:
        path_parts = Path(path).relative_to(base).parts
    except ValueError:
        return None, "the results file lies outside the directory the pattern is read from", False
    if len(path_parts) != len(pattern_parts):
        return (
            None,
            "the results file has a different number of path segments from the pattern",
            False,
        )
    environment, reason = _wildcard_stood_for(pattern_parts[wildcards[0]], path_parts[wildcards[0]])
    return environment, reason, False


def _wildcard_stood_for(pattern_segment: str, path_segment: str) -> tuple[str | None, str]:
    """The part of *path_segment* that the wildcard in *pattern_segment* matched.

    A segment is not always all wildcard: `junit-*.xml` names the environment
    in the middle of it, and returning the whole segment would give
    `junit-pixel6.xml` where the project means `pixel6`. Reading the literal
    text around the wildcard is what tells the two apart.

    Several wildcards in one segment name no single part, so this reports
    rather than picks one (REQ-d00294-D).
    """
    expression = ""
    wildcards = 0
    index = 0
    while index < len(pattern_segment):
        char = pattern_segment[index]
        if char == "*":
            expression += "(.*)"
            wildcards += 1
        elif char == "?":
            expression += "(.)"
            wildcards += 1
        elif char == "[":
            close = pattern_segment.find("]", index + 1)
            if close == -1:
                expression += re.escape(char)
            else:
                expression += "(" + pattern_segment[index : close + 1] + ")"
                wildcards += 1
                index = close
        else:
            expression += re.escape(char)
        index += 1

    if wildcards != 1:
        return None, (
            f"the pattern's wildcard segment holds {wildcards} wildcards, "
            "so no one part of it names the environment"
        )
    match = re.fullmatch(expression, path_segment)
    if match is None:
        return None, "the results file name does not read as the pattern's wildcard segment"
    return match.group(1), ""


# Implements: REQ-d00285-G
def _ingest_target_results(
    builder,
    target,
    results_text: str,
    repo_root: Path,
    source_path: str = "",
    *,
    namespace: str,
    carried: bool = False,
    scanned_tests: frozenset[str] = frozenset(),
    results_pattern: str = "",
    results_base: Path | None = None,
    reporter: str | None = None,
    recorded_root: Path | None = None,
) -> int:
    """Parse a target's reporter output and add RESULT ParsedContent.

    Each ParsedContent carries real source_file (repo-relative) + match.
    Returns the count of RESULT nodes added.

    Only "results"-kind reporters are handled; coverage-kind reporters are
    skipped (returns 0 immediately).

    ``reporter`` names the format *results_text* is in, where it is not the
    one the target declares: an *Evidence Snapshot*'s lines for the target.

    ``recorded_root`` is the root the target's *Result Fingerprint* records.
    An absolute path under it is read relative to it, so results keep
    matching their tests after the tree moves.
    """
    from elspais.graph.parsers import ParsedContent
    from elspais.graph.parsers.results.registry import get_reporter

    reporter_name = reporter or target.reporter
    try:
        spec = get_reporter(reporter_name)
    except KeyError:
        # A misspelled reporter name produces no results anywhere, and a
        # target that ingested nothing looks exactly like a suite that
        # reported nothing. Record the name that matched no reporter.
        _log.debug("_ingest_target_results: unknown reporter %r, skipping", reporter_name)
        builder.record_ingestion_fault(
            path=_repo_relative(source_path, repo_root) if source_path else "",
            stage="target",
            cause=_unknown_reporter_cause(reporter_name),
            target=target.name,
        )
        return 0

    # Implements: REQ-d00322-C+J
    # The settings a target declares describe its own reporter's output. Text
    # in another reporter's format -- an Evidence Snapshot's lines, already in
    # the tool's own line numbering, naming their files and carrying no
    # environment -- is read by that reporter's declarations alone.
    line_base = spec.line_base if reporter else target.line_base
    if line_base is None:
        line_base = spec.line_base
    form = spec.classname if reporter else (target.classname or spec.classname)
    env_source = spec.environment if reporter else (target.environment or spec.environment)

    if spec.kind != "results":
        # Suppressed deliberately: this is routing, not a condition. A
        # coverage-kind reporter has its own ingestion pass, which reads this
        # same target and annotates FILE nodes from it; recording a fault
        # here would report a target that was read as one that was not.
        _log.debug(
            "_ingest_target_results: reporter %r is kind=%r, not 'results', skipping",
            reporter_name,
            spec.kind,
        )
        return 0

    parser = spec.parser_factory()
    result_records = parser.parse(results_text, source_path)
    # Implements: REQ-d00285-G
    _record_parser_diagnostics(builder, parser, "results", target.name, source_path, repo_root)

    # Implements: REQ-d00254-O
    # Normalise the producer's line origin to the tool's own numbering, once,
    # here. Everything downstream -- binding a result to the test at a line,
    # and pointing a reader at that line -- can then treat a line as a line.
    # `result_line` is this module's own count of lines in the results
    # artifact and is already 1-based, so it is left alone.
    line_shift = 1 - line_base
    if line_shift:
        for rec in result_records:
            for key in ("line", "root_line"):
                if isinstance(rec.get(key), int):
                    rec[key] = rec[key] + line_shift
    # Implements: REQ-d00284-A+B+C
    # Where a result names no source file, its recorded name is read in the
    # form declared for this target, falling back to the one its reporter
    # declares. A name read as a source file binds only where it picks out
    # exactly one test scanned for this target; otherwise it binds to nothing
    # and carries why, so the result can be reported rather than dropped.
    for rec in result_records:
        if not rec.get("test_id"):
            continue  # already bound by a source file the producer named
        if form == "python-module":
            continue  # the synthesized identifier already reads it that way
        matches = _tests_named(rec.get("classname", ""), scanned_tests) if form else []
        rec["test_id"] = None
        if len(matches) == 1:
            rec["source_path"] = matches[0]
        else:
            rec["name_match"] = "ambiguous" if matches else "unmatched"
            rec["name_candidates"] = matches

    # Implements: REQ-d00294-C+D
    # The environment is read only from the source the target declares, or
    # the one its reporter declares where the target says nothing. Where a
    # declared source yields nothing, the results keep no environment and
    # the build says it derived none, because a guess reads exactly like a
    # reading in every figure afterwards.
    path_environment: str | None = None
    if env_source == "results-path":
        about_pattern = False
        if source_path and results_pattern and results_base is not None:
            path_environment, reason, about_pattern = _environment_from_path(
                results_pattern, results_base, source_path
            )
        else:
            path_environment, reason = (
                None,
                (
                    "this target's results were read from a runner's output, "
                    "so there is no results path to read an environment from"
                ),
            )
        if path_environment is None:
            # A pattern the tool cannot read is one condition however many
            # files it matched, so it is reported against the pattern. Every
            # other reason is about the one file, and names it.
            if about_pattern and results_base is not None:
                where = _repo_relative(results_base / results_pattern, repo_root)
            else:
                where = _repo_relative(source_path, repo_root) if source_path else ""
            builder.record_ingestion_fault(
                path=where,
                stage="results",
                cause=(f"no environment was derived from the results path: {reason}"),
                target=target.name,
            )

    repo_root_resolved = Path(repo_root).resolve()

    # Implements: REQ-d00311-P
    def _repo_relative_or_kept(raw: str | None) -> str | None:
        # An absolute path inside the repository, or inside the root the run
        # executed in, becomes repo-relative. A relative path, or one under
        # neither root, is kept as it is. A path that no longer exists
        # resolves to itself, so the recorded root still matches it.
        if not raw or not os.path.isabs(raw):
            return raw
        resolved = Path(raw).resolve(strict=False)
        for root in (repo_root_resolved, recorded_root):
            if root is None:
                continue
            try:
                return str(resolved.relative_to(root))
            except ValueError:
                continue
        return raw

    count = 0
    for rec in result_records:
        raw_src = rec.get("source_path", "")
        source_file = _repo_relative_or_kept(raw_src) or ""

        # root_path is set only by flutter-machine for testWidgets() calls
        # whose test.line is a framework wrapper rather than the user call site.
        root_file = _repo_relative_or_kept(rec.get("root_path") or None)

        # Implements: REQ-d00294-G
        # The file that executed the test, where the reporter names one. It
        # differs from source_file for a scenario declared in a shared file.
        runner_file = _repo_relative_or_kept(rec.get("runner_path") or None)

        # Results-file provenance (REQ-d00254): repo-relative path + line of
        # the artifact that recorded this result, distinct from source_file
        # (the TEST's source, which stays the RESULT->TEST match key).
        result_file = _repo_relative_or_kept(rec.get("result_file") or None)
        result_line = rec.get("result_line")

        # Implements: REQ-d00294-A+B
        # The id is spelled here, where the repository root and the
        # namespace are known, so the place of a result record is
        # repo-relative and the same run reads the same way in any checkout.
        # A result record an artifact holds is placed by that artifact; one
        # read from a runner's output has no artifact and is placed by its
        # target.
        # An artifact outside the repository keeps the path it has, because
        # it has no repo-relative form to take. Such an id holds a path from
        # the machine that read it, and two checkouts reading one artifact
        # from different places do not agree about it.
        ordinal = rec.get("ordinal")
        if ordinal is None:
            raise ValueError(
                f"reporter {reporter_name!r} produced a result carrying no "
                f"ordinal, so the result record cannot be told from the other "
                f"result records of the same test. Every results reporter numbers "
                f"its result records."
            )
        result_id = make_result_id(namespace, result_file or target.name, ordinal)

        # Implements: REQ-d00294-C+D
        if env_source == "results-path":
            environment = path_environment
        elif env_source == "suite-hostname":
            environment = rec.get("suite_hostname") or None
            if environment is None:
                # A format that records no suite hostname at all and a suite
                # that left the attribute out are two conditions, and an
                # author fixes them differently: one by declaring another
                # source, the other by mending the producer.
                if "suite_hostname" in rec:
                    reason = "the suite that holds this result record names no hostname"
                else:
                    reason = (
                        f"reporter {reporter_name!r} reads a format whose "
                        f"result records carry no suite hostname"
                    )
                builder.record_ingestion_fault(
                    path=_repo_relative(source_path, repo_root) if source_path else "",
                    stage="results",
                    cause=f"no environment was derived from the suite hostname: {reason}",
                    target=target.name,
                )
        else:
            environment = None

        parsed_data = {
            "id": result_id,
            "status": rec.get("status"),
            "name": rec.get("name", ""),
            "classname": rec.get("classname", ""),
            "duration": rec.get("duration", 0.0),
            "message": rec.get("message"),
            # Implements: REQ-d00322-M
            "output": rec.get("output"),
            "test_id": rec.get("test_id"),
            "source_path": raw_src,
            "source_file": source_file,
            "match": target.match,
            "carried": carried,
            "target": target.name,
            "line": rec.get("line"),
            "root_line": rec.get("root_line"),
            "root_file": root_file,
            "runner_file": runner_file,
            "result_file": result_file,
            "result_line": result_line,
            # Implements: REQ-d00294-C
            "environment": environment,
            # Implements: REQ-d00284-C
            "name_match": rec.get("name_match"),
            "name_candidates": rec.get("name_candidates"),
        }
        content = ParsedContent(
            content_type="test_result",
            start_line=result_line or 1,
            end_line=result_line or 1,
            raw_text="",
            parsed_data=parsed_data,
        )
        builder.add_parsed_content(content)
        count += 1
    return count


# Implements: REQ-d00322-J+L
def _evidence_lines(
    builder, repo_root: Path, evidence: str, *, evidence_only: bool
) -> tuple[Path, dict[str, str]]:
    """The *Evidence Snapshot* at *evidence*, as each target's lines to ingest.

    Returns the snapshot's `results.jsonl` path and, for each target the
    snapshot holds, that target's result lines, one JSON object per line,
    each carrying ``_line``: its 1-based line number in `results.jsonl`. A
    target the snapshot selected and holds no result for maps to no lines,
    because its run produced none.

    A directory that does not exist holds no snapshot yet, and supplies
    nothing. A snapshot that cannot be read is an ingestion fault naming
    the file and line, and supplies nothing: it is never read as empty.
    The build that renders the report reads the snapshot before the report
    exists, so only it reads a snapshot without one.
    """
    from elspais.utilities.evidence import SnapshotUnreadable, load_snapshot

    directory = repo_root / evidence
    results_path = directory / "results.jsonl"
    if not evidence_only and not directory.is_dir():
        return results_path, {}
    try:
        snapshot = load_snapshot(directory, require_report=not evidence_only)
    except SnapshotUnreadable as exc:
        builder.record_ingestion_fault(
            path=_repo_relative(exc.path, repo_root),
            stage="results",
            cause=f"the Evidence Snapshot was not read: {exc.reason}",
            line=exc.line,
        )
        return results_path, {}
    lines: dict[str, list[str]] = {name: [] for name, _digest in snapshot.targets}
    for number, result in enumerate(snapshot.results, start=1):
        lines.setdefault(result.target, []).append(
            json.dumps({**result.to_json(), "_line": number}, sort_keys=True)
        )
    return results_path, {name: "\n".join(rows) for name, rows in lines.items()}


def _validate_config(config: dict[str, Any]) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig (see config.validate_config)."""
    from elspais.config import validate_config

    return validate_config(config)


# Implements: REQ-d00128-C
def _capture_git_info(repo_root: Path) -> tuple[str | None, str | None]:
    """Capture git branch and commit once per repo.

    Args:
        repo_root: Path to repository root.

    Returns:
        Tuple of (git_branch, git_commit), both may be None.
    """
    try:
        from elspais.utilities.git import get_current_branch, get_current_commit

        return get_current_branch(repo_root), get_current_commit(repo_root)
    except Exception:
        return None, None


# Implements: REQ-d00128-A, REQ-d00128-B
def create_file_node(
    file_path: Path,
    repo_root: Path,
    file_type: FileType,
    namespace: str,
    repo: str | None = None,
    git_branch: str | None = None,
    git_commit: str | None = None,
) -> GraphNode:
    """Create a FILE node for a scanned file.

    Args:
        file_path: Absolute path to the file.
        repo_root: Repository root for computing relative path.
        file_type: The FileType classification.
        namespace: The namespace this repository declares. Positional and
            required: a FILE id names the repository holding the file, and
            a caller that cannot say which repository that is cannot make
            the id.
        repo: Repository identifier (None for main project).
        git_branch: Current git branch (captured once per repo).
        git_commit: Current git commit (captured once per repo).

    Returns:
        A GraphNode with kind == NodeKind.FILE.

    Raises:
        ValueError: The namespace is empty.
    """
    if not namespace:
        raise ValueError(
            f"Cannot make a FILE id for {file_path} without a namespace: the id "
            f"names the repository holding the file."
        )
    try:
        rel_path = str(file_path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        rel_path = str(file_path)

    file_id = make_file_id(namespace, rel_path)
    node = GraphNode(
        id=file_id,
        kind=NodeKind.FILE,
        label=file_path.name,
    )
    node._content = {
        "file_type": file_type,
        "absolute_path": str(file_path.resolve()),
        "relative_path": rel_path,
        "repo": repo,
        "git_branch": git_branch,
        "git_commit": git_commit,
    }
    return node


# Implements: REQ-d00254-L+M
def _run_prescan_command(
    command: str,
    test_dirs: list[str],
    test_patterns: list[str],
    skip_dirs: list[str],
    repo_root: Path,
    skip_files: list[str] | None = None,
) -> dict[str, list[dict]] | None:
    """Run an external prescan command to discover test structure.

    The command receives test file paths on stdin (one per line, repo-relative)
    and outputs a JSON array on stdout with the standardized schema:
    [{"file": "...", "function": "...", "class": "...|null", "line": N}, ...]

    Each attribution record's ``file`` may be repo-relative (the form handed in on stdin)
    or absolute; both resolve against the scanned file, because every
    relative key returned here is aliased to its absolute form by the caller.
    Files the command reports on are attributed from its attribution records; every other
    scanned test file keeps built-in attribution, so a command may cover one
    file type and leave the rest alone.

    Args:
        command: Shell command to run.
        test_dirs: Test directory patterns from config.
        test_patterns: File patterns to match.
        skip_dirs: Directories to skip.
        repo_root: Repository root for resolving paths.
        skip_files: Globs over a file's name that the configuration excludes.
            Together with *skip_dirs* this is the whole exclusion; the walk
            needs nothing else. Without them this function read a file the
            reader had excluded and put its path on the stdin of an external
            program (REQ-p00015-H).

    Returns:
        Dict mapping file path -> list of function entries, or None on failure.
    """
    import json
    import subprocess
    import sys

    # Collect all test file paths
    test_files: list[str] = []
    for dir_pattern in test_dirs:
        matched_dirs = glob(str(repo_root / dir_pattern), recursive=True)
        for dir_path in matched_dirs:
            p = Path(dir_path)
            if p.is_dir():
                # Implements: REQ-p00015-H
                # The same exclusions the test scan itself walks under. Two of
                # the three ignore lists reached this walk through neither
                # argument before, so a file the reader excluded was read here.
                domain_file = DomainFile(
                    p,
                    patterns=test_patterns,
                    recursive=True,
                    skip_dirs=skip_dirs,
                    skip_files=list(skip_files or ()),
                    repo_root=repo_root,
                )
                # ``iter_selected`` gives the path and reads no content. The
                # command receives a path, so nothing here needs to open the
                # file. Reading one and discarding it is what REQ-p00015-H
                # forbids, and it also put an excluded path on the stdin of an
                # external program.
                for file_path in domain_file.iter_selected():
                    try:
                        rel = str(file_path.resolve().relative_to(repo_root.resolve()))
                    except ValueError:
                        rel = str(file_path)
                    test_files.append(rel)

    if not test_files:
        return None

    stdin_data = "\n".join(test_files)
    try:
        result = subprocess.run(
            command,
            shell=True,
            input=stdin_data,
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=60,
        )
        if result.returncode != 0:
            print(
                f"Warning: prescan_command failed (exit {result.returncode}): "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
            return None

        entries = json.loads(result.stdout)
        if not isinstance(entries, list):
            print("Warning: prescan_command output is not a JSON array", file=sys.stderr)
            return None

        # Group by file path, exactly as the command reported it
        by_file: dict[str, list[dict]] = {}
        for entry in entries:
            file_path = entry.get("file", "")
            if file_path:
                by_file.setdefault(file_path, []).append(entry)
        return by_file

    except subprocess.TimeoutExpired:
        print("Warning: prescan_command timed out after 60s", file=sys.stderr)
        return None
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: prescan_command error: {e}", file=sys.stderr)
        return None


# The default pattern lists live with the schema that declares them
# (``config/schema.py``), so the value a setting defaults to and the value
# scanning uses when a project declares none are the same object.


# Implements: REQ-d00212-Q+W
def _patterns_for_kind(declared: list[str], fallback: list[str]) -> list[str]:
    """The patterns a scanning kind selects by.

    A kind selects the files its declared patterns match, within the
    directories it declares -- that is the whole of file selection, and it
    means the same thing for every kind. Declaring none means the kind's
    defaults, so a configuration written before the setting had a default
    still scans what it always scanned rather than nothing at all.
    """
    return list(declared) if declared else list(fallback)


# Implements: REQ-d00241-F
# A *Traceability* keyword, read from the one authority that says what those
# keywords are, followed by the colon that makes it a citation rather than
# the ordinary English word. Nothing here decides whether the citation would
# have bound -- the file was never read, so that question has no answer; what
# is being recorded is that the tool declined to look.
_KEYWORD_CITATION = re.compile(r"\b(" + KEYWORD_PATTERN.pattern + r")\s*:", re.IGNORECASE)

# A declined file is read only far enough to answer one question. The cap
# bounds what a stray archive or generated blob in a scanned directory can
# cost, and a NUL byte in the opening chunk says the file is not text at all.
_DECLINED_PROBE_BYTES = 1 << 20


# Markdown fences hold examples. A keyword inside one is being shown, not
# written, and a document that explains the syntax is full of them -- so a
# fenced line is skipped rather than read as a citation the tool missed.
_MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})

# In markdown a citation opens its line, optionally wrapped in emphasis --
# that is the shape a metadata field and a journey's `Validates:` are written
# in. Prose ABOUT a keyword does not: it sits mid-sentence or inside an
# inline code span, and a document explaining the syntax is made of that. The
# looser reading is kept for every other file type, where a keyword followed
# by a colon is a citation wherever it appears in a comment.
_MARKDOWN_CITATION = re.compile(
    r"^\s*(?:[*_]{1,2})?(" + KEYWORD_PATTERN.pattern + r")(?:[*_]{1,2})?\s*:",
    re.IGNORECASE,
)


def _citation_in_comment(line: str, markers: tuple[str, ...]):
    """A *Traceability* citation written behind one of *markers* on *line*.

    A citation lives in a comment (REQ-d00269-K), so the keyword is looked
    for after a marker that opens one -- otherwise ``implements: list[str]``,
    an ordinary parameter annotation, reads as a citation the tool missed.
    """
    for marker in markers:
        at = line.find(marker)
        if at == -1:
            continue
        found = _KEYWORD_CITATION.search(line, at + len(marker))
        if found:
            return found
    return None


def _keyword_citation_in(path: Path) -> tuple[int, str] | None:
    """The first *Traceability* keyword written in *path*, if any.

    Returns the 1-based line and the keyword as the author spelled it, or
    None where the file carries none, cannot be read, or is not text.
    """
    try:
        with path.open("rb") as handle:
            raw = handle.read(_DECLINED_PROBE_BYTES)
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    text = raw.decode("utf-8", errors="ignore")
    markdown = path.suffix.lower() in _MARKDOWN_SUFFIXES
    # The markers a comment opens with in this file's language. Where the
    # language is not one the tool has a pattern for, the three metadata
    # markers stand in: the whole point here is to notice a citation the
    # tool cannot currently read, so the permissive reading is the useful
    # one -- unlike in the grammar, where guessing a marker would BIND an
    # edge off the strength of a shape.
    markers = comment_markers_for_path(str(path)) or METADATA_COMMENT_MARKERS
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if markdown:
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            found = _MARKDOWN_CITATION.match(line)
        else:
            found = _citation_in_comment(line, markers)
        if found:
            return number, found.group(1)
    return None


# Implements: REQ-d00241-F, REQ-d00241-G
def _record_declined_files(
    builder: GraphBuilder,
    domain_file: DomainFile,
    kind: str,
    repo_root: Path,
) -> None:
    """Record every file this walk reached, declined, and that cites anyway.

    A file the ignore configuration excludes never reaches this function --
    the walk drops it before anything is read -- so an ignored file is passed
    over in silence, which is what REQ-d00241-G requires.
    """
    for path in domain_file.iter_declined():
        found = _keyword_citation_in(path)
        if found is None:
            continue
        line, keyword = found
        try:
            relative = str(path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            relative = str(path)
        builder.record_unscanned_keyword_file(relative, kind, keyword, line)


@dataclass
class SpecDirConfig:
    """Per-spec-directory scan configuration.

    Bundles the parser registry and FileDispatcher with scan settings that
    may differ between the main project and associated projects.
    """

    registry: ParserRegistry
    dispatcher: FileDispatcher | None = None
    file_patterns: list[str] = field(default_factory=lambda: ["*.md"])
    skip_dirs: list[str] = field(default_factory=list)
    skip_files: list[str] = field(default_factory=list)


# Implements: REQ-d00254-A+B+F
def _derive_credit_config(targets):
    """Collapse one repository's per-target credit settings into a CoverageCreditConfig.

    The result governs that repository's evidence only; a federation derives
    one per member and credits each member's evidence under its own
    (REQ-d00261-E).

    Phase 1: homogeneous targets. assertion_credit = strongest credit_coverage;
    unmatched_credit = "verified" iff any aggregate target; dirs = target cwds;
    min_coverage_fraction = max.

    Returns:
        CoverageCreditConfig instance.
    """
    from elspais.graph.annotators import CoverageCreditConfig

    _tgt_dirs = tuple(t.cwd for t in targets if t.cwd and t.cwd != ".")
    _order = {"off": 0, "tested": 1, "verified": 2}
    _assertion_credit = "off"
    for _t in targets:
        if _order.get(_t.credit_coverage, 0) > _order.get(_assertion_credit, 0):
            _assertion_credit = _t.credit_coverage
    _unmatched = "verified" if any(_t.match == "aggregate" for _t in targets) else "off"
    _min_frac = max((_t.min_coverage_fraction for _t in targets), default=0.0)
    return CoverageCreditConfig(
        app_dirs=_tgt_dirs,
        unmatched_credit=_unmatched,
        coverage_dirs=_tgt_dirs,
        assertion_credit=_assertion_credit,
        min_coverage_fraction=_min_frac,
    )


def _find_repo_root(spec_dir: Path) -> Path | None:
    """Find the repository root containing .elspais.toml for a spec directory.

    Walks up the directory tree looking for .elspais.toml.

    Args:
        spec_dir: The spec directory path

    Returns:
        Path to repo root, or None if not found
    """
    current = spec_dir.resolve()
    while current != current.parent:
        if (current / ".elspais.toml").exists():
            return current
        current = current.parent
    return None


# Implements: REQ-d00128-G, REQ-d00272-K, REQ-d00287-F
def _resolve_spec_dir_config(
    spec_dir: Path,
    federation_resolvers: Sequence[IdResolver] = (),
) -> SpecDirConfig:
    """Resolve the full scan configuration for a spec directory.

    Loads the .elspais.toml from the repo containing spec_dir and returns
    a SpecDirConfig with the registry, file patterns, skip settings, and
    ignore config from that project's configuration.

    Metadata and journey reference lists are read in every member's grammar,
    as code and test annotations are. A list is judged for a repeated target
    as it is read, so a target the declaring member's own grammar cannot
    read would otherwise reach no repetition check at all. Requirement
    headers stay in the declaring member's grammar alone: a repository
    declares only the identifiers it owns.

    Args:
        spec_dir: The spec directory path

    Returns:
        SpecDirConfig with registry and scan settings for this spec directory

    Raises:
        FileNotFoundError: If no .elspais.toml is found above spec_dir.
            Associated projects must have their own configuration.
    """
    repo_root = _find_repo_root(spec_dir)
    if not repo_root:
        raise FileNotFoundError(
            f"No .elspais.toml found for spec directory: {spec_dir}. "
            "Associated projects must have their own .elspais.toml configuration."
        )

    config_path = repo_root / ".elspais.toml"
    repo_config = get_config(config_path, repo_root)

    # Typed config conversion at function boundary
    if isinstance(repo_config, dict):
        typed_repo_config = _validate_config(repo_config)
    else:
        typed_repo_config = repo_config

    resolver = build_resolver(repo_config)
    own_namespace = resolver.config.namespace
    member_resolvers = [r for r in federation_resolvers if r.config.namespace != own_namespace]

    # Build Lark-based FileDispatcher for spec files
    dispatcher = FileDispatcher(resolver, member_resolvers)

    # Spec files reach the Lark dispatcher; the registry carries the parsers
    # that read the rest of a spec directory.
    registry = ParserRegistry()
    # RequirementParser removed — Lark dispatcher handles spec files
    registry.register(JourneyParser(FederatedIdReader(resolver, member_resolvers)))
    registry.register(RemainderParser())

    file_patterns, skip_dirs, skip_files = _spec_selection(repo_config, typed_repo_config)
    return SpecDirConfig(
        registry=registry,
        dispatcher=dispatcher,
        file_patterns=file_patterns,
        skip_dirs=skip_dirs,
        skip_files=skip_files,
    )


def _spec_selection(config: Any, typed_config: Any) -> tuple[list[str], list[str], list[str]]:
    """The patterns, skipped directories and skipped files the spec kind selects by."""
    patterns = typed_config.scanning.spec.file_patterns
    # Fall back to ["*.md"] if patterns is empty or not a list.
    file_patterns = patterns if isinstance(patterns, list) and patterns else ["*.md"]
    skip_dirs, skip_files = scan_exclusions(config, "spec")
    return list(file_patterns), skip_dirs, skip_files


@dataclass(frozen=True)
class KindScan:
    """What one scanning kind of one repository reads.

    Attributes:
        kind: ``spec``, ``code`` or ``test``.
        directories: The existing directories the kind walks, absolute.
        patterns: The file patterns that select among what they hold.
        skip_dirs: The directories the walk does not enter.
        skip_files: The file-name globs the walk does not read.
    """

    kind: str
    directories: tuple[Path, ...]
    patterns: tuple[str, ...]
    skip_dirs: tuple[str, ...]
    skip_files: tuple[str, ...]


# Implements: REQ-p00015-H, REQ-d00313-A
def scan_plan(
    config: dict[str, Any],
    repo_root: Path,
    *,
    spec_dirs: list[Path] | None = None,
    scan_code: bool = True,
    scan_tests: bool = True,
) -> list[KindScan]:
    """The directories, patterns and exclusions each scanning kind of a repository reads by.

    ONE derivation: a build walks what this returns, and a serving process
    watches the same selection, so the files it judges a graph against are
    the files that graph was built from.
    """
    typed = _validate_config(config) if isinstance(config, dict) else config
    raw = config if isinstance(config, dict) else {}
    plan: list[KindScan] = []

    spec_patterns, spec_skip_dirs, spec_skip_files = _spec_selection(raw, typed)
    plan.append(
        KindScan(
            kind="spec",
            directories=tuple(
                spec_dirs if spec_dirs is not None else get_spec_directories(None, raw, repo_root)
            ),
            patterns=tuple(spec_patterns),
            skip_dirs=tuple(spec_skip_dirs),
            skip_files=tuple(spec_skip_files),
        )
    )
    if scan_code:
        code_skip_dirs, code_skip_files = scan_exclusions(raw, "code")
        plan.append(
            KindScan(
                kind="code",
                directories=tuple(get_code_directories(raw, repo_root)),
                patterns=tuple(
                    _patterns_for_kind(typed.scanning.code.file_patterns, DEFAULT_CODE_PATTERNS)
                ),
                skip_dirs=tuple(code_skip_dirs),
                skip_files=tuple(code_skip_files),
            )
        )
    if scan_tests and typed.scanning.test.enabled:
        test_skip_dirs, test_skip_files = scan_exclusions(raw, "test")
        test_dirs: list[Path] = []
        for dir_pattern in typed.scanning.test.directories:
            # A test directory is a glob over the repository.
            for matched in glob(str(repo_root / dir_pattern), recursive=True):
                if Path(matched).is_dir():
                    test_dirs.append(Path(matched))
        plan.append(
            KindScan(
                kind="test",
                directories=tuple(test_dirs),
                patterns=tuple(
                    _patterns_for_kind(typed.scanning.test.file_patterns, DEFAULT_TEST_PATTERNS)
                ),
                skip_dirs=tuple(test_skip_dirs),
                skip_files=tuple(test_skip_files),
            )
        )
    return plan


# Implements: REQ-p00005-B, REQ-d00203-A+B+E, REQ-d00200-J
def build_graph(
    config: dict[str, Any] | None = None,
    spec_dirs: list[Path] | None = None,
    config_path: Path | None = None,
    repo_root: Path | None = None,
    scan_code: bool = True,
    scan_tests: bool = True,
    captured_results: dict[str, str] | None = None,
    fresh_targets: set[str] | None = None,
    evidence_only: bool = False,
) -> FederatedGraph:
    """Build a FederatedGraph from spec directories.

    This is the standard way for commands to obtain a graph.
    It handles:
    - Configuration loading (auto-discovery or explicit)
    - Spec directory resolution
    - Parser registration
    - Graph construction
    - Code and test directory scanning (configurable)
    - Multi-repo federation via [associates] config

    Every member is built bare and handed to the one federation that holds
    it, so the cross-repository passes run once over each member.

    Args:
        config: Pre-loaded config dict (optional).
        spec_dirs: Explicit spec directories (optional).
        config_path: Path to config file (optional).
        repo_root: Repository root for relative paths (defaults to cwd).
        scan_code: Whether to scan code directories from traceability.scan_patterns.
        scan_tests: Whether to scan test directories from testing.test_dirs.
        captured_results: Optional mapping of target name -> captured stdout/results
            text, bypassing the on-disk results glob for that target.
        fresh_targets: Optional set of [[scanning.test.targets]] names considered
            "freshly run" (e.g. via ``--targets``). When set, every RESULT node
            ingested for a target NOT in this set is tagged ``carried=True``.
            When None (the default), no target is considered carried. Stashed
            on the returned FederatedGraph as ``render_fresh_targets``.
        evidence_only: Read every target's results from the *Evidence
            Snapshot* its repository names, and none from the target's own
            output area or coverage file.

    Returns:
        FederatedGraph wrapping one or more TraceGraph instances.

    Priority:
        spec_dirs > config > config_path > defaults
    """
    # Default repo_root
    if repo_root is None:
        repo_root = Path.cwd()

    # 1. Resolve configuration
    if config is None:
        config = get_config(config_path, repo_root)

    default_resolver = build_resolver(config)

    # Implements: REQ-d00269-C
    # Membership is settled before any file is scanned: an identifier owned
    # by any member has to be recognised in this repository's code and test
    # annotations, and a scanner cannot recognise a grammar it has not been
    # given.  The plan is resolved from configuration alone and reused for
    # the associate builds below rather than walked a second time.
    plan: list[PlannedRepo] | None = None
    federation_resolvers = [default_resolver]
    if declared_associates(config, repo_root):
        # Implements: REQ-d00202-G, REQ-d00202-M
        # A declaration whose repository cannot be read names no
        # namespace, and a member without one cannot be placed.
        # Building around it would answer questions about a corpus
        # nobody chose, so the build stops and says which
        # declarations are at fault. Surfaces that exist to REPORT
        # the faults use plan_federation_or_error instead.
        plan = plan_federation(config, repo_root)
        refuse_unreadable(plan)
        federation_resolvers.extend(build_resolver(member.config) for member in plan[1:])

    graph, annotate_coverage_here = _build_repository(
        config,
        repo_root,
        spec_dirs=spec_dirs,
        config_path=config_path,
        scan_code=scan_code,
        scan_tests=scan_tests,
        captured_results=captured_results,
        fresh_targets=fresh_targets,
        federation_resolvers=federation_resolvers,
        evidence_only=evidence_only,
    )

    # Implements: REQ-d00203-A+B+E
    # Build every repository the declarations reach, not only those the
    # root names directly (REQ-d00202-D).
    if plan is not None and len(plan) > 1:
        from elspais.graph.federated import RepoEntry

        entries: list[RepoEntry] = [
            RepoEntry(
                name=plan[0].name,
                graph=graph,
                config=config,
                repo_root=repo_root,
                # The plan detected this repository's origin along with
                # every other member's. Leaving it off here made the
                # repository being worked in the one member that never
                # reported an origin, and so the one that never received
                # branch or divergence staleness.
                git_origin=plan[0].git_origin,
            )
        ]
        for member in plan[1:]:
            # The plan already resolved this member's own declarations,
            # so each graph is built for itself alone. A federation
            # recomputes coverage over every member once the
            # cross-repository edges exist, so a member is not annotated
            # here.
            member_graph, _ = _build_repository(
                member.config,
                member.repo_root,
                scan_code=scan_code,
                scan_tests=scan_tests,
                federation_resolvers=federation_resolvers,
                evidence_only=evidence_only,
            )
            entries.append(
                RepoEntry(
                    name=member.name,
                    graph=member_graph,
                    config=member.config,
                    repo_root=member.repo_root,
                    git_origin=member.git_origin,
                )
            )
        # The host is entries[0]; FederatedGraph identifies it the way it
        # identifies every member, so naming it here would be a second
        # answer to that question.
        federated = FederatedGraph(entries)
    else:
        # A federation of one recomputes nothing, so this is the only
        # coverage pass this graph receives.
        annotate_coverage_here()
        federated = FederatedGraph.from_single(graph, config, repo_root)
    # Implements: REQ-d00254-I
    federated.render_fresh_targets = fresh_targets
    return federated


# Implements: REQ-d00203-A, REQ-d00200-J
def _build_repository(
    config: dict[str, Any],
    repo_root: Path,
    *,
    spec_dirs: list[Path] | None = None,
    config_path: Path | None = None,
    scan_code: bool = True,
    scan_tests: bool = True,
    captured_results: dict[str, str] | None = None,
    fresh_targets: set[str] | None = None,
    federation_resolvers: list[IdResolver] | None = None,
    evidence_only: bool = False,
) -> tuple[TraceGraph, Callable[[], None]]:
    """Build one repository's graph, held by no federation.

    Returns the graph and the coverage pass for it. The caller runs that
    pass only where no federation will recompute coverage over the graph,
    because a federation discards every figure computed before its
    cross-repository edges exist.

    ``federation_resolvers`` is every member's ``IdResolver``. Each
    repository's own grammar still comes from its own configuration;
    sharing the set is what lets its code and tests name the identifiers
    its siblings own.
    """
    typed_config = _validate_config(config)

    # 2. Resolve spec directories
    if spec_dirs is None:
        spec_dirs = get_spec_directories(None, config, repo_root)
    _plan = scan_plan(
        config, repo_root, spec_dirs=spec_dirs, scan_code=scan_code, scan_tests=scan_tests
    )

    # 3. Create default resolver
    default_resolver = build_resolver(config)
    if federation_resolvers is None:
        federation_resolvers = [default_resolver]
    own_namespace = default_resolver.config.namespace
    member_resolvers = [r for r in federation_resolvers if r.config.namespace != own_namespace]

    # Implements: REQ-d00128-G
    # Lark FileDispatcher for code and test files
    default_dispatcher = FileDispatcher(default_resolver, member_resolvers)

    # 4. Build graph from all spec directories
    satellite_kinds = ["assertion", "result"]
    # YIELDS (RESULT->TEST) links are always enabled: flutter-machine emits
    # test_id=None (never queues YIELDS), while junit/pytest emit real test_ids
    # (YIELDS desired).  So the per-test link is unconditionally safe.
    builder = GraphBuilder(
        repo_root=repo_root,
        satellite_kinds=satellite_kinds,
        resolver=default_resolver,
        namespace=typed_config.project.namespace,
        project_name=typed_config.project.name,
        link_results_to_tests=True,
    )

    # Implements: REQ-d00128-C
    # Capture git info once per repo
    git_branch, git_commit = _capture_git_info(repo_root)

    # Track FILE nodes created to avoid duplicates
    file_nodes: dict[str, GraphNode] = {}  # resolved_path -> FILE node

    def _get_or_create_file_node(
        source_path: Path,
        file_type: FileType,
        file_repo: str | None = None,
    ) -> GraphNode:
        """Get or create a FILE node for the given source path."""
        resolved = str(source_path.resolve())
        if resolved not in file_nodes:
            fn = create_file_node(
                source_path,
                repo_root,
                file_type,
                typed_config.project.namespace,
                repo=file_repo,
                git_branch=git_branch,
                git_commit=git_commit,
            )
            file_nodes[resolved] = fn
            builder.register_file_node(fn)
        else:
            # Multi-role: track additional file types on existing node (stored as
            # string values for JSON serializability)
            fn = file_nodes[resolved]
            existing_types = fn.get_field("file_types")
            if existing_types is None:
                first = fn.get_field("file_type")
                existing_types = [first.value if isinstance(first, FileType) else first]
            type_val = file_type.value if isinstance(file_type, FileType) else file_type
            if type_val not in existing_types:
                existing_types.append(type_val)
            fn.set_field("file_types", existing_types)
        return file_nodes[resolved]

    # Implements: REQ-d00299-A
    # The configuration is read before anything else and decides how the
    # rest is read, so the document it was read from is held before any
    # spec file is. The node carries the parsed document rather than the
    # values taken from it: the values are already in `config`, and it is
    # the document — its comments, its spacing, the order its author chose
    # — that a writer must be able to give back unchanged.
    _read_config_path = config_path if config_path else find_config_file(repo_root)
    if _read_config_path is not None and _read_config_path.is_file():
        for document_path in config_document_paths(_read_config_path):
            try:
                document_text = document_path.read_text(encoding="utf-8")
            except OSError:
                # The configuration was read moments ago; a document that
                # cannot be read now is a race, not a configuration fault,
                # and refusing the build over it would be a worse answer
                # than building without holding that document.
                continue
            config_node = _get_or_create_file_node(document_path, FileType.CONFIG)
            config_node.set_field("config_document", parse_toml_document(document_text))
            # Implements: REQ-d00299-D
            # A declaration the document makes under a name becomes a node
            # of its own, so it can be addressed and versioned. These are
            # CONTAINS children that are NOT the file's text -- the CONFIG
            # renderer dumps the document and never walks them.
            for declaration_node in build_declaration_nodes(config_node):
                builder.register_declaration_node(declaration_node)

    for spec_dir in spec_dirs:
        # Resolve full scan config for this spec dir from its own .elspais.toml
        dir_config = _resolve_spec_dir_config(spec_dir, federation_resolvers)

        # Implements: REQ-d00212-Q+W
        # One mechanism, one meaning: the ignore configuration excludes, the
        # declared patterns select, and both are settled inside the walk.
        domain_file = DomainFile(
            spec_dir,
            patterns=dir_config.file_patterns,
            recursive=True,
            skip_dirs=dir_config.skip_dirs,
            skip_files=dir_config.skip_files,
            repo_root=repo_root,
        )

        # Use Lark FileDispatcher for spec file parsing
        for parsed_content in domain_file.dispatch(dir_config.dispatcher.dispatch_spec):
            source_path = parsed_content.source_context.metadata.get("path")
            # Implements: REQ-d00128-A
            # Create FILE node for this spec file
            file_node = None
            if source_path:
                file_node = _get_or_create_file_node(Path(source_path), FileType.SPEC)
            builder.add_parsed_content(parsed_content, file_node=file_node)

        _record_declined_files(builder, domain_file, "spec", repo_root)

    # 5. Scan code files from the code kind's declared directories.
    # Implements: REQ-d00212-Q+W
    if scan_code:
        scanned_code_files: set[str] = set()

        (code_scan,) = (k for k in _plan if k.kind == "code")

        for code_dir in code_scan.directories:
            domain_file = DomainFile(
                code_dir,
                patterns=list(code_scan.patterns),
                recursive=True,
                skip_dirs=list(code_scan.skip_dirs),
                skip_files=list(code_scan.skip_files),
                repo_root=repo_root,
            )
            # One file is scanned once, however many declared directories
            # happen to contain it.
            here = {str(f.resolve()) for f in domain_file.iter_selected()}
            fresh = here - scanned_code_files
            scanned_code_files |= here

            for parsed_content in domain_file.dispatch(default_dispatcher.dispatch_code):
                source_path = parsed_content.source_context.metadata.get("path")
                if source_path and str(Path(source_path).resolve()) not in fresh:
                    continue
                # Implements: REQ-d00128-A
                fn = None
                if source_path:
                    fn = _get_or_create_file_node(Path(source_path), FileType.CODE)
                builder.add_parsed_content(parsed_content, file_node=fn)

            _record_declined_files(builder, domain_file, "code", repo_root)

    # 6. Scan test directories from testing config
    if scan_tests:
        testing_cfg = typed_config.scanning.test
        if testing_cfg.enabled:
            test_dirs = list(testing_cfg.directories)
            # Implements: REQ-d00212-Q+W
            (test_scan,) = (k for k in _plan if k.kind == "test")
            test_patterns = list(test_scan.patterns)
            test_skip_dirs = list(test_scan.skip_dirs)
            test_skip_files = list(test_scan.skip_files)

            # Run external prescan command if configured
            prescan_command = testing_cfg.prescan_command
            prescan_data: dict[str, list[dict]] | None = None
            if prescan_command:
                prescan_data = _run_prescan_command(
                    prescan_command,
                    test_dirs,
                    test_patterns,
                    test_skip_dirs,
                    repo_root,
                    skip_files=test_skip_files,
                )
                # Paths go out on stdin repo-relative, so a conforming command
                # answers with those, while scanning dispatches absolute paths.
                # Alias each relative key to its absolute form so attribution records govern
                # either way (REQ-d00254-N).
                if prescan_data:
                    for reported in list(prescan_data):
                        if not Path(reported).is_absolute():
                            prescan_data.setdefault(
                                str(repo_root / reported), prescan_data[reported]
                            )

            # Build dispatch function with prescan data
            def _dispatch_test(content: str, file_path: str) -> list:
                return default_dispatcher.dispatch_test(
                    content, file_path, prescan_data=prescan_data
                )

            scanned_test_files: set[str] = set()
            resolved_root = repo_root.resolve()
            for path in test_scan.directories:
                # Implements: REQ-d00212-Q+W, REQ-d00241-G
                # The ignore configuration governs the test kind too:
                # it was never asked here, so `[scanning.test]`'s own
                # exclusions decided nothing.
                domain_file = DomainFile(
                    path,
                    patterns=test_patterns,
                    recursive=True,
                    skip_dirs=test_skip_dirs,
                    skip_files=test_skip_files,
                    repo_root=repo_root,
                )
                for parsed_content in domain_file.dispatch(_dispatch_test):
                    # Implements: REQ-d00128-A
                    source_path = parsed_content.source_context.metadata.get("path")
                    fn = None
                    if source_path:
                        fn = _get_or_create_file_node(Path(source_path), FileType.TEST)
                        # Implements: REQ-d00284-B
                        # The candidates a result's recorded name is
                        # resolved among, gathered as they are scanned.
                        try:
                            scanned_test_files.add(
                                str(Path(source_path).resolve().relative_to(resolved_root))
                            )
                        except ValueError:
                            pass
                    builder.add_parsed_content(parsed_content, file_node=fn)

                _record_declined_files(builder, domain_file, "test", repo_root)

            # 6b-target. Ingest results from [[scanning.test.targets]] via reporter registry.
            # Implements: REQ-d00128-A+H
            # RemainderParser is NOT registered for RESULT file types.
            # When targets is empty (the default) this loop is a no-op.
            from elspais.graph.builder import UnreadArtifact
            from elspais.utilities.fingerprint import (
                FINGERPRINT_NAME,
                read_fingerprint,
                run_in_progress,
                target_folder,
            )

            _captured = captured_results or {}
            from elspais.graph.parsers.results.registry import get_reporter as _get_reporter

            # Implements: REQ-d00322-J+L
            # The Evidence Snapshot this repository names, read once. Each
            # federation member reads its own, against its own root.
            evidence_path: Path | None = None
            evidence_lines: dict[str, str] = {}
            if typed_config.scanning.test.evidence and typed_config.scanning.test.targets:
                evidence_path, evidence_lines = _evidence_lines(
                    builder,
                    repo_root,
                    typed_config.scanning.test.evidence,
                    evidence_only=evidence_only,
                )

            def _read_evidence(target, scanned: frozenset[str]) -> bool:
                """Ingest *target*'s results from the Evidence Snapshot.

                They are tagged carried, except in a build reading only the
                snapshot for a target it names as fresh. Returns whether the
                snapshot holds the target and was read.
                """
                if evidence_path is None or target.name not in evidence_lines:
                    return False
                # Implements: REQ-d00322-J, REQ-d00254-I, REQ-d00283-R
                # A target this run executed, or one whose output area holds
                # a Result Fingerprint, ran here: its results are its own even
                # where it left none, so the snapshot never stands in for
                # them. A build reading only the snapshot asks nothing of the
                # output area.
                if not evidence_only:
                    if fresh_targets is not None and target.name in fresh_targets:
                        return False
                    area = target_folder(repo_root, typed_config, target.name)
                    if (area / FINGERPRINT_NAME).is_file():
                        return False
                _get_or_create_file_node(evidence_path, FileType.RESULT)
                # Implements: REQ-d00322-F+J
                # A build reading only the snapshot renders that snapshot's
                # own run: the targets it names as fresh are that run, and
                # their results are not carried from anything.
                carried_here = not (
                    evidence_only and fresh_targets is not None and target.name in fresh_targets
                )
                _ingest_target_results(
                    builder,
                    target,
                    evidence_lines[target.name],
                    repo_root,
                    str(evidence_path),
                    namespace=typed_config.project.namespace,
                    carried=carried_here,
                    scanned_tests=scanned,
                    reporter="evidence-snapshot",
                )
                return True

            for target in typed_config.scanning.test.targets:
                if not target.reporter:
                    continue
                # Implements: REQ-d00285-G
                # Resolve the reporter before anything is read, so a name
                # nothing reads is reported as that, and so the conditions
                # below can tell a target that owes results from one whose
                # results are a coverage report read further down.
                try:
                    target_spec = _get_reporter(target.reporter)
                except KeyError:
                    builder.record_ingestion_fault(
                        path="",
                        stage="target",
                        cause=_unknown_reporter_cause(target.reporter),
                        target=target.name,
                    )
                    continue
                # Implements: REQ-d00254-I
                carried = fresh_targets is not None and target.name not in fresh_targets
                # cwd-escape guard: skip targets whose cwd resolves outside the repo root
                cwd_path = (repo_root / target.cwd) if target.cwd else repo_root
                try:
                    cwd_path.resolve().relative_to(resolved_root)
                except ValueError:
                    # Implements: REQ-d00285-G
                    _log.warning(
                        "target %r: cwd %r escapes repo root -- skipping",
                        target.name,
                        target.cwd,
                    )
                    builder.record_ingestion_fault(
                        path=str(target.cwd or ""),
                        stage="target",
                        cause=(
                            f"working directory {target.cwd!r} resolves outside the "
                            f"repository, so no results were read for this target"
                        ),
                        target=target.name,
                    )
                    continue
                # Implements: REQ-d00284-B
                # The candidates are the tests scanned under this target's own
                # cwd: a name matching a file some other target scans says
                # nothing about where this result came from.
                try:
                    cwd_rel = str(cwd_path.resolve().relative_to(resolved_root))
                except ValueError:
                    cwd_rel = ""
                prefix = "" if cwd_rel in ("", ".") else cwd_rel.rstrip("/") + "/"
                target_tests = frozenset(
                    f for f in scanned_test_files if not prefix or f.startswith(prefix)
                )
                # Implements: REQ-d00322-J
                # A build reading only the snapshot reads nothing from the
                # target's output area, whatever is there or running.
                if evidence_only:
                    if not _read_evidence(target, target_tests) and target_spec.kind == "results":
                        builder.record_unread_artifact(
                            UnreadArtifact(
                                target=target.name,
                                artifact="results",
                                path=(
                                    _repo_relative(evidence_path, repo_root)
                                    if evidence_path is not None
                                    else ""
                                ),
                                reason="absent",
                            )
                        )
                    continue
                # Implements: REQ-d00311-N
                # A run in progress has emptied the area and writes into it
                # while it runs, so nothing there is read until it ends.
                # Output this invocation captured is read: it is a run that
                # has ended.
                _running = run_in_progress(target_folder(repo_root, typed_config, target.name))
                if target.name not in _captured and _running is not None:
                    builder.record_unread_artifact(
                        UnreadArtifact(
                            target=target.name,
                            artifact="results",
                            path=(
                                _repo_relative(
                                    target_folder(repo_root, typed_config, target.name)
                                    / target.results,
                                    repo_root,
                                )
                                if target.results
                                else ""
                            ),
                            reason="running",
                            started_at=str(_running.get("started_at", "")),
                        )
                    )
                    continue
                # Implements: REQ-d00311-P
                # The root the run executed in, read once for the target, so
                # a path its reporter recorded under that root still names
                # the same file after the tree moves.
                _fingerprint = read_fingerprint(target_folder(repo_root, typed_config, target.name))
                _recorded = (_fingerprint or {}).get("root")
                recorded_root = (
                    Path(_recorded) if isinstance(_recorded, str) and _recorded else None
                )
                if target.name in _captured:
                    _ingest_target_results(
                        builder,
                        target,
                        _captured[target.name],
                        repo_root,
                        "",
                        namespace=typed_config.project.namespace,
                        carried=carried,
                        scanned_tests=target_tests,
                        recorded_root=recorded_root,
                    )
                elif target.results:
                    # Implements: REQ-d00312-A+C
                    # target.results names files inside the output area of the
                    # target. The working directory of the target does not
                    # change this location.
                    area = target_folder(repo_root, typed_config, target.name)
                    matched = glob(str(area / target.results), recursive=True)
                    if matched:
                        for f in matched:
                            if Path(f).is_file():
                                # Implements: REQ-d00128-A
                                _get_or_create_file_node(Path(f), FileType.RESULT)
                                _ingest_target_results(
                                    builder,
                                    target,
                                    Path(f).read_text(encoding="utf-8", errors="replace"),
                                    repo_root,
                                    str(Path(f)),
                                    namespace=typed_config.project.namespace,
                                    carried=carried,
                                    scanned_tests=target_tests,
                                    # Implements: REQ-d00294-C
                                    # The pattern and the directory it was
                                    # read from, so a target declaring
                                    # `results-path` can read back the part
                                    # of the path its wildcard stood for.
                                    results_pattern=target.results,
                                    results_base=area,
                                    recorded_root=recorded_root,
                                )
                    elif target_spec.kind == "results":
                        # Implements: REQ-d00322-J
                        # A target with no results of its own reads the
                        # project's Evidence Snapshot, tagged carried.
                        if _read_evidence(target, target_tests):
                            continue
                        # Implements: REQ-d00283-R+S+T
                        # The build records that no results are there. Whether
                        # that is a fault depends on what the run executed and
                        # expected, which a health check judges.
                        _log.debug("target %r: no files matched %r", target.name, target.results)
                        builder.record_unread_artifact(
                            UnreadArtifact(
                                target=target.name,
                                artifact="results",
                                path=_repo_relative(area / target.results, repo_root),
                                reason="absent",
                            )
                        )
                elif target_spec.kind == "results":
                    # Implements: REQ-d00322-J
                    if _read_evidence(target, target_tests):
                        continue
                    # Implements: REQ-d00283-R+S+T
                    # The same fact as a results pattern that matched nothing,
                    # for a target whose reporter reads its runner's output.
                    _log.debug(
                        "target %r: stdout reporter with no captured output and no results glob",
                        target.name,
                    )
                    builder.record_unread_artifact(
                        UnreadArtifact(
                            target=target.name, artifact="results", path="", reason="absent"
                        )
                    )

    graph = builder.build()

    # 6c-target. Per-target coverage ingestion: scan coverage files and annotate FILE nodes.
    # When targets is empty (the default), this loop is a no-op.
    # Implements: REQ-d00322-F
    # A build reading only the Evidence Snapshot reads no coverage file: the
    # snapshot holds none, and the report rendered from it depends on the
    # snapshot and the specification alone.
    if typed_config.scanning.test.targets and not evidence_only:
        from elspais.graph.builder import UnreadArtifact
        from elspais.graph.parsers.results.coverage_json import CoverageJsonParser
        from elspais.graph.parsers.results.coverage_sqlite import CoverageSqliteParser
        from elspais.graph.parsers.results.lcov import LcovParser
        from elspais.utilities.fingerprint import run_in_progress, target_folder

        lcov_parser = LcovParser()
        cov_json_parser = CoverageJsonParser()
        cov_sqlite_parser = CoverageSqliteParser()
        _resolved_root = repo_root.resolve()
        for target in typed_config.scanning.test.targets:
            if not target.coverage:
                continue
            # cwd-escape guard: skip targets whose cwd resolves outside the repo root
            cwd_path = (repo_root / target.cwd) if target.cwd else repo_root
            try:
                cwd_path.resolve().relative_to(_resolved_root)
            except ValueError:
                # Implements: REQ-d00285-G
                _log.warning(
                    "target %r: cwd %r escapes repo root -- skipping",
                    target.name,
                    target.cwd,
                )
                graph.record_ingestion_fault(
                    path=str(target.cwd or ""),
                    stage="target",
                    cause=(
                        f"working directory {target.cwd!r} resolves outside the "
                        f"repository, so no coverage was read for this target"
                    ),
                    target=target.name,
                )
                continue
            # Implements: REQ-d00312-A+C
            cov_area = target_folder(repo_root, typed_config, target.name)
            cov_path = (cov_area / target.coverage).resolve()
            # Implements: REQ-d00311-N
            _running = run_in_progress(cov_area)
            if _running is not None and target.name not in (captured_results or {}):
                graph.record_unread_artifact(
                    UnreadArtifact(
                        target=target.name,
                        artifact="coverage",
                        path=_repo_relative(cov_path, repo_root),
                        reason="running",
                        started_at=str(_running.get("started_at", "")),
                    )
                )
                continue
            if not cov_path.is_file():
                # Implements: REQ-d00283-V
                # No coverage file and coverage measuring nothing are the same
                # zero once the numbers are aggregated, so the absence is
                # recorded for a health check to judge.
                _log.debug("target %r: coverage file not found: %s", target.name, cov_path)
                graph.record_unread_artifact(
                    UnreadArtifact(
                        target=target.name,
                        artifact="coverage",
                        path=_repo_relative(cov_path, repo_root),
                        reason="absent",
                    )
                )
                continue
            if lcov_parser.can_parse(cov_path):
                cov_parser = lcov_parser
            elif cov_json_parser.can_parse(cov_path):
                cov_parser = cov_json_parser
            elif cov_sqlite_parser.can_parse(cov_path):
                cov_parser = cov_sqlite_parser
            else:
                # Implements: REQ-d00285-G
                _log.debug("target %r: unrecognised coverage format: %s", target.name, cov_path)
                graph.record_ingestion_fault(
                    path=_repo_relative(cov_path, repo_root),
                    stage="coverage",
                    cause=(
                        "no coverage reader recognises this file's format, so the "
                        "measurement it holds was not read"
                    ),
                    target=target.name,
                )
                continue
            # Binary formats (e.g. the .coverage SQLite DB) can't be
            # text-decoded -- their parser ignores `content` and reopens
            # `source_path` directly (see CoverageSqliteParser.binary).
            if getattr(cov_parser, "binary", False):
                cov_content = ""
            else:
                cov_content = cov_path.read_text(encoding="utf-8")
            if cov_parser is cov_sqlite_parser:
                # Contexts are the suite-scaled part of the data (every test
                # context string per executed line). Only materialize them
                # for measured files that actually resolve to a FILE node --
                # unresolvable ones (test files, out-of-tree sources) are
                # discarded by the annotation loop below anyway.
                def _wanted(source_file: str, _cwd: Path = cwd_path) -> bool:
                    return (
                        _resolve_coverage_file_node(graph, source_file, _cwd, repo_root) is not None
                    )

                parsed_cov = cov_parser.parse(cov_content, str(cov_path), wanted_files=_wanted)
            else:
                parsed_cov = cov_parser.parse(cov_content, str(cov_path))
            # Implements: REQ-d00285-G
            _record_parser_diagnostics(
                graph, cov_parser, "coverage", target.name, str(cov_path), repo_root
            )
            for source_file, data in parsed_cov.items():
                cov_node = _resolve_coverage_file_node(graph, source_file, cwd_path, repo_root)
                if cov_node is None:
                    continue
                cov_node.set_field("line_coverage", data["line_coverage"])
                cov_node.set_field("executable_lines", data["executable_lines"])
                # Implements: REQ-d00254-Q
                # A file whose source could not be re-analysed has executed
                # lines but no known total. Carry that, so a figure computed
                # over this file can leave it out rather than treat its
                # executed count as its size.
                if not data.get("source_analysed", True):
                    cov_node.set_field("source_analysed", False)
                if data.get("contexts"):
                    cov_node.set_field("line_contexts", data["contexts"])

    # Link TEST nodes to CODE nodes via import analysis.
    # This creates TEST→CODE edges that enable transitive coverage:
    # REQUIREMENT ← CODE ← TEST ← RESULT
    if scan_code and scan_tests:
        from elspais.graph.test_code_linker import link_tests_to_code

        # Get source roots from config (default: ["src", ""])
        source_roots = typed_config.scanning.code.source_roots
        link_tests_to_code(graph, repo_root, source_roots)

    # Annotate keywords on all nodes so keyword search tools work
    # Annotate coverage metrics so all consumers (MCP, HTML, viewer) get coverage data
    from elspais.graph.annotators import (
        DEFAULT_STOPWORDS,
        KeywordsConfig,
        annotate_coverage,
        annotate_journey_verification,
        annotate_keywords,
    )

    # The shortest word worth indexing is the project's to set. The
    # extractor has always honoured it; nothing had ever passed it in.
    annotate_keywords(
        graph,
        KeywordsConfig(
            stopwords=DEFAULT_STOPWORDS,
            min_length=typed_config.keywords.min_length,
        ),
    )
    # Derive this repository's coverage-credit config from
    # [[scanning.test.targets]]. Per-target settings are collapsed into one
    # config for the repository (acceptable for Phase 1 homogeneous targets).
    # Logic lives in _derive_credit_config (pure, unit-tested independently).
    credit = _derive_credit_config(typed_config.scanning.test.targets)

    def _annotate_coverage_here() -> None:
        # Roll each journey's verifying tests into a journey_verification
        # metric BEFORE coverage, so the per-REQ UAT consumer can read each
        # validating journey's verdict when populating the uat_verified
        # dimension.
        annotate_journey_verification(graph)
        annotate_coverage(graph, credit)

    return graph, _annotate_coverage_here


__all__ = ["build_graph"]
