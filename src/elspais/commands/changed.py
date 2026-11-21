# Implements: REQ-p00004-B, REQ-p00004-M, REQ-d00336-A, REQ-d00336-B
"""
elspais.commands.changed - The code and test files to review after a requirement change.

A change is detected at the granularity a citation names: an *Assertion* whose
text differs from its text at the comparison base, and a requirement whose
*Assertions* differ as a set. For each change the command lists every code and
test file citing what changed, with the line of each citation, and marks each
file reviewed or awaiting review from the review record the repository
commits (``.elspais/changes.md``).

``compute_changes`` is the one computation: the command line and the MCP tool
both report what it returns.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.utilities.git import ComparisonBase, comparison_base, get_repo_root
from elspais.utilities.review_record import (
    RECORD_PATH,
    Awaiting,
    Review,
    ReviewRecord,
    ReviewRecordError,
    read_record,
    write_record,
)


@dataclass(frozen=True)
class _Consequence:
    """One file that cites one change."""

    change_id: str
    path: str
    lines: tuple[int, ...]
    content: str
    file_content: str


def _assertion_digest(node: GraphNode) -> str:
    """The digest of one *Assertion*'s normalized text."""
    from elspais.utilities.hasher import compute_normalized_hash

    return compute_normalized_hash([(node.get_field("label", ""), node.get_label() or "")])


def _assertions_of(req: GraphNode) -> dict[str, GraphNode]:
    """A requirement's own *Assertions*, by label."""
    from elspais.graph.render import iter_hashed_parts

    return {
        part.get_field("label", ""): part
        for part in iter_hashed_parts(req)
        if part.kind == NodeKind.ASSERTION and part.get_field("label")
    }


def _requirement_digest(req: GraphNode) -> str:
    from elspais.graph.render import compute_hash_for_node

    return compute_hash_for_node(req) or ""


def _file_digest(path: Path) -> str:
    from elspais.utilities.hasher import content_digest

    try:
        return content_digest(path.read_text(encoding="utf-8"))[:8]
    except OSError:
        return ""


def _expected_reviewer(req: GraphNode) -> str | None:
    """The author of the requirement's newest changelog entry."""
    entries = req.get_field("changelog") or []
    if not entries:
        return None
    entry = entries[0]
    name = entry.get("author_name") or ""
    ident = entry.get("author_id") or ""
    if not name:
        return None
    return f"{name} <{ident}>" if ident else name


def _reader(graph: Any) -> Any:
    """The federation's identifier reader, as the build read citations with."""
    from elspais.utilities.patterns import FederatedIdReader, build_resolver

    resolvers = [build_resolver(entry.config) for entry in graph.iter_repos() if entry.config]
    if not resolvers:
        return None
    return FederatedIdReader(resolvers[0], resolvers[1:])


def _citers(req: GraphNode, label: str | None) -> list[GraphNode]:
    """The CODE and TEST nodes whose citation names *label* of *req*, or the whole of it."""
    found: dict[int, GraphNode] = {}
    for edge in req.iter_outgoing_edges():
        if edge.target.kind not in (NodeKind.CODE, NodeKind.TEST):
            continue
        targets = edge.assertion_targets or []
        if (label is None and not targets) or (label is not None and label in targets):
            found[id(edge.target)] = edge.target
    if label is not None:
        assertion = _assertions_of(req).get(label)
        if assertion is not None:
            for edge in assertion.iter_outgoing_edges():
                if edge.target.kind in (NodeKind.CODE, NodeKind.TEST):
                    found[id(edge.target)] = edge.target
    return list(found.values())


def _display_path(file_node: GraphNode, repo_root: Path) -> str:
    """How the report and the record name a file.

    A file of the repository the command runs in is named by its path from
    that repository's root. A file another federation member holds is named
    by that member's namespace and its path within the member, so two
    members' files at one relative path stay apart and the name is the same
    on every machine.
    """
    from elspais.graph.GraphNode import parse_structural_id

    absolute = file_node.get_field("absolute_path")
    if absolute:
        try:
            return Path(absolute).resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            pass
    _prefix, namespace, relative, _line = parse_structural_id(file_node.id)
    return f"{namespace}:{relative}"


def _file_index(graph: Any, repo_root: Path) -> dict[str, Path]:
    """Every file the graph holds, by the name the report gives it."""
    index: dict[str, Path] = {}
    for file_node in graph.nodes_by_kind(NodeKind.FILE):
        absolute = file_node.get_field("absolute_path")
        if absolute:
            index[_display_path(file_node, repo_root)] = Path(absolute)
    return index


def _files_citing(
    req: GraphNode,
    label: str | None,
    change_id: str,
    content: str,
    reader: Any,
    repo_root: Path,
) -> list[_Consequence]:
    """Each file citing the change, with the lines of its citations."""
    from elspais.graph.citation_respelling import citation_lines_naming
    from elspais.graph.render import citation_texts

    by_path: dict[str, tuple[set[int], Path | None]] = {}
    for node in _citers(req, label):
        file_node = node.file_node()
        if file_node is None:
            continue
        rel = _display_path(file_node, repo_root)
        absolute = file_node.get_field("absolute_path")
        lines: list[int] = []
        if reader is not None:
            lines = citation_lines_naming(node, change_id, reader)
        if not lines:
            lines = sorted(citation_texts(node)) or [int(node.get_field("parse_line") or 0)]
        held = by_path.setdefault(rel, (set(), Path(absolute) if absolute else None))
        held[0].update(lines)
    return [
        _Consequence(
            change_id, rel, tuple(sorted(lines)), content, _file_digest(path) if path else ""
        )
        for rel, (lines, path) in sorted(by_path.items())
    ]


def _base_requirements(
    repo_root: Path, base: ComparisonBase, config_path: Path | None = None
) -> tuple[dict[str, Any], str | None]:
    """Each requirement at the base, by id, as its *Assertion* digests and hash.

    Returns the requirements and None, or nothing and why the base could not
    be read.
    """
    from elspais.graph.factory import build_graph
    from elspais.utilities.git import temporary_worktree

    if base.commit is None:
        return {}, base.error
    try:
        with temporary_worktree(repo_root, base.commit) as worktree:
            local = repo_root / ".elspais.local.toml"
            if local.is_file():
                # The machine-local overlay names where associates live, and
                # version control never holds it.
                shutil.copy2(local, worktree / ".elspais.local.toml")
            base_config = None
            if config_path is not None:
                named = Path(config_path)
                if named.is_absolute():
                    try:
                        named = named.resolve().relative_to(repo_root.resolve())
                    except ValueError:
                        return {}, (
                            f"the configuration {config_path} lies outside the repository, "
                            f"so the base holds no copy of it"
                        )
                base_config = worktree / named
            graph = build_graph(
                config_path=base_config, repo_root=worktree, scan_code=False, scan_tests=False
            )
            namespace = graph.root_repo_namespace
            held: dict[str, Any] = {}
            for req in graph.nodes_by_kind(NodeKind.REQUIREMENT, namespace=namespace):
                held[req.id] = (
                    {label: _assertion_digest(a) for label, a in _assertions_of(req).items()},
                    _requirement_digest(req),
                )
            return held, None
    except subprocess.CalledProcessError as exc:
        return {}, f"the base {base.commit} could not be checked out: {exc}"
    except Exception as exc:  # a base whose spec does not build is unverifiable
        return {}, f"the spec at the base {base.commit} could not be read: {exc}"


def _change_index(graph: Any) -> dict[str, tuple[GraphNode, str | None]]:
    """Every requirement and *Assertion* id, with its requirement and label."""
    index: dict[str, tuple[GraphNode, str | None]] = {}
    for req in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        index[req.id] = (req, None)
        for label, assertion in _assertions_of(req).items():
            index[assertion.id] = (req, label)
    return index


def _current_content(graph: Any, change_id: str) -> str | None:
    found = _change_index(graph).get(change_id)
    if found is None:
        return None
    req, label = found
    if label is None:
        return _requirement_digest(req)
    return _assertion_digest(_assertions_of(req)[label])


def _consequences(
    graph: Any, base_reqs: dict[str, Any], repo_root: Path
) -> list[tuple[dict, list[_Consequence]]]:
    """Each change in the working tree, with the files citing it."""
    reader = _reader(graph)
    namespace = graph.root_repo_namespace
    found: list[tuple[dict, list[_Consequence]]] = []
    for req in graph.nodes_by_kind(NodeKind.REQUIREMENT, namespace=namespace):
        base_assertions, base_hash = base_reqs.get(req.id, ({}, None))
        reviewer = _expected_reviewer(req)
        for label, assertion in sorted(_assertions_of(req).items()):
            digest = _assertion_digest(assertion)
            if base_assertions.get(label) == digest:
                continue
            change = {
                "id": assertion.id,
                "kind": "assertion",
                "requirement": req.id,
                "added": label not in base_assertions,
                "expected_reviewer": reviewer,
            }
            listed = _files_citing(req, label, assertion.id, digest, reader, repo_root)
            found.append((change, listed))
        digest = _requirement_digest(req)
        if digest != base_hash:
            change = {
                "id": req.id,
                "kind": "requirement",
                "requirement": req.id,
                "added": req.id not in base_reqs,
                "expected_reviewer": reviewer,
            }
            found.append((change, _files_citing(req, None, req.id, digest, reader, repo_root)))
    found.sort(key=lambda item: item[0]["id"])
    return found


def _matching_review(record: ReviewRecord, consequence: _Consequence) -> tuple[Review | None, bool]:
    """The review that still holds for *consequence*, and whether one went stale."""
    stale = False
    current: Review | None = None
    for review in record.reviews:
        if review.change_id != consequence.change_id or review.path != consequence.path:
            continue
        if (
            review.content == consequence.content
            and review.file_content == consequence.file_content
        ):
            if current is None or review.date >= current.date:
                current = review
        else:
            stale = True
    return current, stale and current is None


def _carried(
    graph: Any, repo_root: Path, record: ReviewRecord, current: set[tuple[str, str]]
) -> list[Awaiting]:
    """Files the record holds as awaiting review beyond the current change set."""
    index = _change_index(graph)
    files = _file_index(graph, repo_root)
    carried: list[Awaiting] = []
    for entry in record.awaiting:
        if (entry.change_id, entry.path) in current:
            continue
        if entry.change_id not in index or entry.path not in files:
            continue
        carried.append(entry)
    return sorted(set(carried), key=lambda a: (a.change_id, a.path))


@dataclass
class _Computed:
    result: dict[str, Any]
    consequences: list[_Consequence]
    carried: list[Awaiting]
    record: ReviewRecord


def _compute(
    graph: Any, repo_root: Path, base_branch: str, config_path: Path | None = None
) -> _Computed:
    base = comparison_base(repo_root, base_branch)
    record = read_record(repo_root)
    result: dict[str, Any] = {
        "base": {"branch": base.branch, "ref": base.ref, "commit": base.commit},
        "verifiable": True,
        "unverifiable_reason": None,
        "changes": [],
        "carried": [],
        "summary": {"changes": 0, "files": 0, "awaiting": 0, "reviewed": 0},
        "record": RECORD_PATH.as_posix(),
    }
    base_reqs, error = _base_requirements(repo_root, base, config_path)
    consequences: list[_Consequence] = []
    if error is not None:
        result["verifiable"] = False
        result["unverifiable_reason"] = error
    else:
        for change, files in _consequences(graph, base_reqs, repo_root):
            listed = []
            for consequence in files:
                review, stale = _matching_review(record, consequence)
                listed.append(
                    {
                        "path": consequence.path,
                        "lines": list(consequence.lines),
                        "status": "reviewed" if review else "awaiting",
                        "stale": stale,
                        "review": (
                            {"reviewer": review.reviewer, "date": review.date} if review else None
                        ),
                    }
                )
                consequences.append(consequence)
            change["files"] = listed
            result["changes"].append(change)
    current = {(c.change_id, c.path) for c in consequences}
    carried = _carried(graph, repo_root, record, current)
    result["carried"] = [
        {"id": a.change_id, "path": a.path, "lines": list(a.lines)} for a in carried
    ]
    awaiting_now = {
        (change["id"], f["path"])
        for change in result["changes"]
        for f in change["files"]
        if f["status"] == "awaiting"
    }
    recorded = {(a.change_id, a.path) for a in record.awaiting}
    result["record_behind"] = [
        {"id": cid, "path": path} for cid, path in sorted(awaiting_now - recorded)
    ]
    files = [f for change in result["changes"] for f in change["files"]]
    reviewed = sum(1 for f in files if f["status"] == "reviewed")
    result["summary"] = {
        "changes": len(result["changes"]),
        "files": len(files),
        "awaiting": len(files) - reviewed + len(carried),
        "reviewed": reviewed,
    }
    return _Computed(result, consequences, carried, record)


# Implements: REQ-d00336-C, REQ-d00336-D, REQ-d00336-E, REQ-d00336-F, REQ-d00336-G
# Implements: REQ-d00336-H, REQ-d00336-M, REQ-d00336-N, REQ-d00336-P
def compute_changes(
    graph: Any, repo_root: Path, base_branch: str = "main", config_path: Path | None = None
) -> dict[str, Any]:
    """The changes since the comparison base and the files to review for each.

    ``record_behind`` names each file awaiting review that the review record
    does not yet name, so a record that would lose one when committed says so.

    Args:
        graph: The federated graph of the working tree, code and tests scanned.
        repo_root: The root of the repository the graph was built from.
        base_branch: The branch the current branch is compared against.
        config_path: The configuration file the graph was built with, where
            it is not the repository's own; the base is read with its copy
            at the base commit.
    """
    return _compute(graph, repo_root, base_branch, config_path).result


def _awaiting_entries(computed: _Computed, reviewed: set[tuple[str, str]]) -> list[Awaiting]:
    """What the record names as awaiting review once *reviewed* is recorded."""
    entries: list[Awaiting] = []
    for consequence in computed.consequences:
        key = (consequence.change_id, consequence.path)
        if key in reviewed:
            continue
        review, _stale = _matching_review(computed.record, consequence)
        if review is None:
            entries.append(Awaiting(consequence.change_id, consequence.path, consequence.lines))
    entries += [a for a in computed.carried if (a.change_id, a.path) not in reviewed]
    return entries


# Implements: REQ-d00336-O
def write_awaiting(
    graph: Any, repo_root: Path, base_branch: str = "main", config_path: Path | None = None
) -> Path:
    """Write the files awaiting review into the record; record no review.

    Raises:
        ReviewRefused: The base cannot be read, so what awaits review is unknown.
    """
    computed = _compute(graph, repo_root, base_branch, config_path)
    _refuse_unverifiable(computed)
    record = ReviewRecord(_awaiting_entries(computed, set()), list(computed.record.reviews))
    return write_record(repo_root, record)


def _review_name(path: str, files: dict[str, Path]) -> str:
    """The report's name for a path a reviewer gave.

    A path relative to the repository root, or a federation member's
    ``NAMESPACE:path``, is the name itself; an absolute path is the name of
    the file the graph holds there, in whichever member holds it.
    """
    named = Path(path)
    if named.is_absolute():
        resolved = named.resolve()
        for name, absolute in files.items():
            if absolute.resolve() == resolved:
                return name
    return named.as_posix() if ":" not in path else path


class ReviewRefused(ValueError):
    """A review names a file that awaits no review, or the base cannot be read."""


def _refuse_unverifiable(computed: _Computed) -> None:
    if not computed.result["verifiable"]:
        raise ReviewRefused(
            f"the changes are unverifiable ({computed.result['unverifiable_reason']}), "
            f"so the record is left as it is."
        )


def _reviewer_identity() -> str:
    """The person recording a review: the git identity the repository commits as.

    The review record is committed, so a review names the identity its commit
    will carry.
    """
    from elspais.utilities.git import get_author_info

    author = get_author_info("git")
    return f"{author['name']} <{author['id']}>"


# Implements: REQ-d00336-J, REQ-d00336-K, REQ-d00336-L
def record_reviews(
    graph: Any,
    repo_root: Path,
    paths: list[str],
    *,
    base_branch: str = "main",
    config_path: Path | None = None,
    changes: list[str] | None = None,
    reviewer: str,
    today: str | None = None,
) -> list[Review]:
    """Record a review of each awaiting consequence of each path, and write the record.

    Raises:
        ReviewRefused: A path names no file awaiting review (for the changes
            named, where some are).
    """
    computed = _compute(graph, repo_root, base_branch, config_path)
    _refuse_unverifiable(computed)
    files = _file_index(graph, repo_root)
    wanted = set(changes or [])
    when = today or date.today().isoformat()
    targets: list[tuple[str, str, str, str]] = []
    for path in paths:
        rel = _review_name(path, files)
        hits = 0
        for consequence in computed.consequences:
            if consequence.path != rel or (wanted and consequence.change_id not in wanted):
                continue
            review, _stale = _matching_review(computed.record, consequence)
            if review is not None:
                continue
            targets.append(
                (consequence.change_id, consequence.content, rel, consequence.file_content)
            )
            hits += 1
        for entry in computed.carried:
            if entry.path != rel or (wanted and entry.change_id not in wanted):
                continue
            content = _current_content(graph, entry.change_id) or ""
            targets.append((entry.change_id, content, rel, _file_digest(files[rel])))
            hits += 1
        if hits == 0:
            named = f" for {', '.join(sorted(wanted))}" if wanted else ""
            raise ReviewRefused(
                f"{rel} awaits no review{named}; `elspais changed` lists the files that do."
            )
    reviews = [Review(cid, content, rel, fc, reviewer, when) for cid, content, rel, fc in targets]
    reviewed = {(r.change_id, r.path) for r in reviews}
    record = ReviewRecord(
        _awaiting_entries(computed, reviewed), list(computed.record.reviews) + reviews
    )
    write_record(repo_root, record)
    return reviews


# Implements: REQ-d00085-F
def render_text(result: dict[str, Any], quiet: bool = False) -> str:
    """The report a person reads."""
    base = result["base"]
    summary = result["summary"]
    if quiet:
        if not result["verifiable"]:
            return f"Changes unverifiable: {result['unverifiable_reason']}"
        return (
            f"Changes since {base['ref']}: {summary['changes']}, files to review: "
            f"{summary['awaiting']} awaiting, {summary['reviewed']} reviewed"
        )
    lines: list[str] = []
    if not result["verifiable"]:
        lines.append(f"Changes unverifiable: {result['unverifiable_reason']}")
    else:
        lines.append(f"Compared with {base['ref']} at {base['commit']}")
        if not result["changes"]:
            lines.append("No requirement or Assertion changed.")
        for change in result["changes"]:
            kind = "Assertion" if change["kind"] == "assertion" else "Requirement"
            added = " (new)" if change["added"] else ""
            lines.append("")
            lines.append(f"{kind} {change['id']}{added}")
            if change["expected_reviewer"]:
                lines.append(f"  expected reviewer: {change['expected_reviewer']}")
            if not change["files"]:
                lines.append("  no code or test file cites it")
            for listed in change["files"]:
                where = ", ".join(str(n) for n in listed["lines"])
                if listed["status"] == "reviewed":
                    status = (
                        f"reviewed by {listed['review']['reviewer']} on {listed['review']['date']}"
                    )
                else:
                    status = "awaiting review"
                    if listed["stale"]:
                        status += " (changed since its review)"
                lines.append(f"  {listed['path']}:{where}  {status}")
    if result["carried"]:
        lines.append("")
        lines.append(f"Awaiting review from earlier changes ({result['record']}):")
        for entry in result["carried"]:
            where = ", ".join(str(n) for n in entry["lines"])
            lines.append(f"  {entry['id']}  {entry['path']}:{where}  awaiting review")
    if result.get("record_behind"):
        lines.append("")
        lines.append(
            f"{result['record']} does not name {len(result['record_behind'])} file(s) "
            f"awaiting review; run `elspais changed --write-record` before committing."
        )
    lines.append("")
    lines.append(f"Files to review: {summary['awaiting']} awaiting, {summary['reviewed']} reviewed")
    return "\n".join(lines)


def _emit(text: str, output: Path | None) -> None:
    if output:
        Path(output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def run(args: argparse.Namespace) -> int:
    """Run the changed command."""
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    repo_root = get_repo_root()
    if repo_root is None:
        print("Error: Not in a git repository", file=sys.stderr)
        return 1
    config_path = getattr(args, "config", None)
    config = get_config(config_path=config_path)
    if config is None:
        return 1
    base_branch = getattr(args, "base_branch", None) or "main"
    output = getattr(args, "output", None)
    graph = build_graph(config=config, repo_root=repo_root)
    try:
        review_paths = list(getattr(args, "review", None) or [])
        if review_paths:
            reviewer = _reviewer_identity()
            reviews = record_reviews(
                graph,
                repo_root,
                review_paths,
                base_branch=base_branch,
                config_path=config_path,
                changes=list(getattr(args, "change", None) or []),
                reviewer=reviewer,
            )
            for review in reviews:
                print(f"Reviewed {review.path} for {review.change_id} ({reviewer})")
            print(f"Recorded in {RECORD_PATH.as_posix()}")
            return 0
        if getattr(args, "change", None):
            print(
                "Error: --change narrows --review; name the files with --review.",
                file=sys.stderr,
            )
            return 1
        if getattr(args, "write_record", False):
            path = write_awaiting(graph, repo_root, base_branch, config_path)
            print(f"Wrote the files awaiting review to {path.relative_to(repo_root).as_posix()}")
        result = compute_changes(graph, repo_root, base_branch, config_path)
    except (ReviewRefused, ReviewRecordError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if getattr(args, "format", "text") == "json":
        _emit(json.dumps(result, indent=2), output)
    else:
        _emit(render_text(result, quiet=getattr(args, "quiet", False)), output)
    return 0 if result["verifiable"] else 1
