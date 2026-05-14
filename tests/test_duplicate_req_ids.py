# Verifies: REQ-d00085-I
"""Regression tests for cross-file REQ ID collisions.

Bug: when two spec files defined the same REQ ID (e.g., both ``# REQ-d00001:``),
the graph builder picked one file's content (last-wins) but MERGED parent edges
from both files onto the single canonical node, and ``elspais fix`` then wrote
those merged edges back into the canonical file's frontmatter as synthesized
``Implements:`` / ``Refines:`` lines that no human authored. The
``spec.no_duplicates`` health check silently passed because it walked the
post-collapse index.

Fix: the builder now disambiguates subsequent occurrences by appending a
``#<file-stem>`` suffix to the synthetic node's ID and records every collision
in ``_duplicate_req_ids``. The health check reads from that record, ``fix``
aborts when duplicates are present, and ``render_save`` skips any file that
participates in a duplicate as defense-in-depth.

Validates REQ-d00085-I findings enrichment for duplicate detection.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from elspais.commands.fix_cmd import run as fix_run
from elspais.commands.health import HealthFinding, check_spec_no_duplicates
from elspais.graph import EdgeKind
from elspais.graph.factory import build_graph
from elspais.graph.render import render_save

# ─────────────────────────────────────────────────────────────────────────────
# Fixture builder
# ─────────────────────────────────────────────────────────────────────────────


CONFIG_TOML = """\
version = 3

[project]
name = "duplicate-req-id-repro"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = []

[scanning.test]
enabled = false
directories = []
"""

PRD_TARGETS_MD = """\
# Target PRDs

## REQ-p00001: First parent

**Level**: PRD | **Status**: Active | **Implements**: -

### Assertions

A. The system SHALL do thing one.

*End* *First parent*

## REQ-p00002: Second parent

**Level**: PRD | **Status**: Active | **Implements**: -

### Assertions

A. The system SHALL do thing two.

*End* *Second parent*
"""

DEV_FILE_A_MD = """\
# File A — canonical definition

## REQ-d00001: Server-Owned Activation (file A definition)

**Level**: DEV | **Status**: Active | **Implements**: -
**Refines**: REQ-p00001

### Assertions

A. POST /activate SHALL accept {code, password} with no bearer auth.

B. The handler SHALL validate code expiry before any external call.

*End* *Server-Owned Activation (file A definition)*
"""

DEV_FILE_B_MD = """\
# File B — colliding definition with different semantics

## REQ-d00001: Notifications Table Schema (file B definition)

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. The notifications table SHALL persist every push notification.

B. Each row SHALL carry a UUID primary key.

*End* *Notifications Table Schema (file B definition)*
"""


def _make_dup_project(tmp_path: Path) -> Path:
    """Create the canonical three-file duplicate-id fixture on disk.

    Returns ``tmp_path`` for convenience. Files are scanned in alphabetical
    order, so ``dev-file-a.md`` provides the canonical REQ-d00001 and
    ``dev-file-b.md`` becomes the synthetic ``REQ-d00001#dev-file-b``.
    """
    (tmp_path / ".elspais.toml").write_text(CONFIG_TOML)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "prd-targets.md").write_text(PRD_TARGETS_MD)
    (spec_dir / "dev-file-a.md").write_text(DEV_FILE_A_MD)
    (spec_dir / "dev-file-b.md").write_text(DEV_FILE_B_MD)
    return tmp_path


def _build(tmp_path: Path):
    """Build a FederatedGraph for the duplicate-id fixture."""
    return build_graph(
        spec_dirs=[tmp_path / "spec"],
        config_path=tmp_path / ".elspais.toml",
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )


def _rel(*parts: str) -> str:
    """Build a forward-slash relative path for cross-platform compare."""
    return Path(*parts).as_posix()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Builder-level: synthetic IDs, isolated edges, content fields
# ─────────────────────────────────────────────────────────────────────────────


# Implements: REQ-d00085-I
def test_builder_creates_synthetic_id_for_second_occurrence(tmp_path: Path) -> None:
    """The second cross-file occurrence of a REQ ID becomes a synthetic node.

    Asserts that the two REQ nodes exist with distinct IDs, that their
    incoming parent edges did NOT cross (no merged frontmatter), and that the
    synthetic node carries ``is_duplicate=True`` and ``original_id`` markers.
    """
    project = _make_dup_project(tmp_path)
    graph = _build(project)

    canonical = graph.find_by_id("REQ-d00001")
    synthetic = graph.find_by_id("REQ-d00001#dev-file-b")

    assert canonical is not None, "Canonical REQ-d00001 (file A) should be present"
    assert synthetic is not None, (
        "Synthetic REQ-d00001#dev-file-b (file B) should be present; "
        "the builder must disambiguate the second occurrence rather than merging"
    )

    # Edges must NOT cross files. file A only declared Refines: REQ-p00001;
    # file B only declared Implements: REQ-p00002. The canonical node must
    # carry only file A's parent edge.
    canonical_incoming = list(canonical.iter_incoming_edges())
    # Filter to traceability edges (drop CONTAINS from the FILE node).
    canonical_trace = [
        e for e in canonical_incoming if e.kind in {EdgeKind.IMPLEMENTS, EdgeKind.REFINES}
    ]
    assert len(canonical_trace) == 1, (
        f"Canonical node should have exactly one traceability incoming edge, "
        f"got {[(e.source.id, e.kind.value) for e in canonical_trace]}"
    )
    assert canonical_trace[0].kind == EdgeKind.REFINES
    assert canonical_trace[0].source.id == "REQ-p00001"

    synthetic_incoming = list(synthetic.iter_incoming_edges())
    synthetic_trace = [
        e for e in synthetic_incoming if e.kind in {EdgeKind.IMPLEMENTS, EdgeKind.REFINES}
    ]
    assert len(synthetic_trace) == 1, (
        f"Synthetic node should have exactly one traceability incoming edge, "
        f"got {[(e.source.id, e.kind.value) for e in synthetic_trace]}"
    )
    assert synthetic_trace[0].kind == EdgeKind.IMPLEMENTS
    assert synthetic_trace[0].source.id == "REQ-p00002"

    # The synthetic node carries the duplicate-marker fields.
    assert synthetic.get_field("is_duplicate") is True
    assert synthetic.get_field("original_id") == "REQ-d00001"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Accessor: graph.duplicate_req_ids() / has_duplicate_req_ids()
# ─────────────────────────────────────────────────────────────────────────────


# Implements: REQ-d00085-I
def test_duplicate_req_ids_accessor_lists_all_sources(tmp_path: Path) -> None:
    """``graph.duplicate_req_ids()`` returns the canonical→sources map.

    First-occurrence file (file A) appears first in the path list, then the
    later occurrence (file B). ``has_duplicate_req_ids()`` is True.
    """
    project = _make_dup_project(tmp_path)
    graph = _build(project)

    dups = graph.duplicate_req_ids()

    assert graph.has_duplicate_req_ids() is True
    assert list(dups.keys()) == ["REQ-d00001"]

    file_a = _rel("spec", "dev-file-a.md")
    file_b = _rel("spec", "dev-file-b.md")
    sources = [Path(p).as_posix() for p in dups["REQ-d00001"]]

    assert sources == [file_a, file_b], (
        f"Expected sources to be ordered [file A, file B] for the canonical "
        f"REQ-d00001, got {sources}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Health check: spec.no_duplicates fires on cross-file collision
# ─────────────────────────────────────────────────────────────────────────────


# Implements: REQ-d00085-I
def test_check_spec_no_duplicates_fires_on_cross_file_collision(tmp_path: Path) -> None:
    """``check_spec_no_duplicates`` must fail when two files define the same REQ ID.

    Before the fix, the check walked the post-collapse index and saw exactly
    one node, so it silently passed. Now it reads from the build-time
    collision record.
    """
    project = _make_dup_project(tmp_path)
    graph = _build(project)

    check = check_spec_no_duplicates(graph)

    assert check.passed is False
    duplicates = check.details["duplicates"]
    assert len(duplicates) == 1
    assert "REQ-d00001" in duplicates

    listed_paths = [Path(p).as_posix() for p in duplicates["REQ-d00001"]]
    assert _rel("spec", "dev-file-a.md") in listed_paths
    assert _rel("spec", "dev-file-b.md") in listed_paths

    assert len(check.findings) == 1
    finding = check.findings[0]
    assert isinstance(finding, HealthFinding)
    assert finding.node_id == "REQ-d00001"


# ─────────────────────────────────────────────────────────────────────────────
# 4. CLI: elspais fix aborts when duplicates exist; files unchanged on disk
# ─────────────────────────────────────────────────────────────────────────────


# Implements: REQ-d00085-I
def test_fix_command_aborts_when_duplicates_exist(tmp_path: Path, capsys) -> None:
    """``fix_cmd.run`` must abort with exit code 1 and leave files untouched.

    Critical regression: without the guard, render_save would write the
    disambiguated synthetic IDs back to disk as headings/references, corrupting
    the user's source. We snapshot file B before the run and assert it is
    byte-for-byte unchanged afterwards.
    """
    project = _make_dup_project(tmp_path)
    file_b = project / "spec" / "dev-file-b.md"
    before = file_b.read_bytes()

    args = argparse.Namespace(
        req_id=None,
        dry_run=False,
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        git_root=project,
        verbose=False,
        quiet=False,
        message=None,
    )

    rc = fix_run(args)

    assert rc == 1, "fix must abort with exit code 1 when duplicate REQ IDs exist"

    after = file_b.read_bytes()
    assert after == before, (
        "dev-file-b.md must be byte-for-byte unchanged after a duplicate-id "
        "abort; render_save would otherwise write the synthetic ID back to disk"
    )

    captured = capsys.readouterr()
    stderr = captured.err
    assert "REQ-d00001" in stderr, f"stderr should name the colliding canonical ID; got: {stderr!r}"
    assert (
        "dev-file-a.md" in stderr
    ), f"stderr should list file A as a colliding source; got: {stderr!r}"
    assert (
        "dev-file-b.md" in stderr
    ), f"stderr should list file B as a colliding source; got: {stderr!r}"


# Implements: REQ-d00085-I
def test_non_duplicate_fix_failure_still_runs_index_and_term_passes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A non-duplicate failure in ``_fix_parse_dirty`` must not suppress
    ``_fix_index`` and ``_fix_terms``.

    Regression for a bug where the run-loop early-returned on any non-zero
    parse-dirty exit code, conflating duplicate aborts (which should suppress
    INDEX/term generation because synthetic IDs would leak into outputs) with
    unrelated unfixable conditions (e.g. section header depth at H6), where
    INDEX/term generation must still run.
    """
    from elspais.commands import fix_cmd

    project = _make_dup_project(tmp_path)
    # Drop the colliding file B so there are no duplicates — the precheck
    # passes and we can exercise the post-precheck path.
    (project / "spec" / "dev-file-b.md").unlink()

    args = argparse.Namespace(
        req_id=None,
        dry_run=False,
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        git_root=project,
        verbose=False,
        quiet=False,
        message=None,
    )

    # Simulate a non-duplicate failure: _fix_parse_dirty returns 1 as if
    # there were unfixable section depth issues. _fix_index and _fix_terms
    # should still be invoked.
    call_log: list[str] = []
    monkeypatch.setattr(
        fix_cmd, "_fix_parse_dirty", lambda *a, **kw: (call_log.append("parse"), 1)[1]
    )
    monkeypatch.setattr(fix_cmd, "_fix_index", lambda *a, **kw: call_log.append("index"))
    monkeypatch.setattr(fix_cmd, "_fix_terms", lambda *a, **kw: call_log.append("terms"))

    rc = fix_run(args)

    assert rc == 1, f"non-duplicate failure should propagate the failing exit code; got {rc}"
    assert call_log == ["parse", "index", "terms"], (
        f"all three sub-passes must run when the failure is not a duplicate abort; "
        f"got call order: {call_log!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Defense-in-depth: render_save skips colliding files
# ─────────────────────────────────────────────────────────────────────────────


# Implements: REQ-d00085-I
def test_render_save_skips_files_in_duplicates(tmp_path: Path) -> None:
    """``render_save`` must refuse to write any file that participated in a duplicate.

    Backstop for callers that bypass the fix CLI guard (mutation API, GUI).
    Even when the FILE nodes are marked dirty, the colliding files must be
    listed in ``skipped`` and remain unchanged on disk.
    """
    project = _make_dup_project(tmp_path)
    graph = _build(project)

    file_a_path = project / "spec" / "dev-file-a.md"
    file_b_path = project / "spec" / "dev-file-b.md"
    before_a = file_a_path.read_bytes()
    before_b = file_b_path.read_bytes()

    # Mark both REQ-d00001 nodes parse_dirty so _find_dirty_files() picks up
    # their FILE ancestors. Without this, render_save would have no work to do
    # and the duplicate filter would never be exercised.
    canonical = graph.find_by_id("REQ-d00001")
    synthetic = graph.find_by_id("REQ-d00001#dev-file-b")
    assert canonical is not None
    assert synthetic is not None
    canonical.mark_parse_dirty("duplicate_refs")
    synthetic.mark_parse_dirty("duplicate_refs")

    # Snapshot mutation-log length before render_save so we can assert it is
    # preserved (not cleared) when duplicate-induced skips block the save.
    before_log_len = sum(1 for _ in graph.mutation_log.iter_entries())

    result = render_save(graph, repo_root=project)

    assert result["saved_count"] == 0, (
        f"render_save must not save any files when duplicates exist, "
        f"got saved_count={result['saved_count']}"
    )

    skipped_text = "\n".join(result.get("skipped", []))
    assert (
        "dev-file-a.md" in skipped_text
    ), f"file A must appear in skipped list; got: {result.get('skipped')!r}"
    assert (
        "dev-file-b.md" in skipped_text
    ), f"file B must appear in skipped list; got: {result.get('skipped')!r}"

    # Duplicate-skipped files are also reported as errors so callers can
    # detect the failure programmatically. ``success`` must be False and
    # the mutation log must be preserved — losing queued mutations because
    # of a duplicate elsewhere in the project would silently destroy work.
    assert result["success"] is False, (
        "render_save must report success=False when duplicate collisions " "prevented any save"
    )
    errors_text = "\n".join(result.get("errors", []))
    assert (
        "duplicate" in errors_text.lower()
    ), f"errors must mention the duplicate condition; got: {result.get('errors')!r}"
    after_log_len = sum(1 for _ in graph.mutation_log.iter_entries())
    assert after_log_len == before_log_len, (
        f"mutation log must be preserved when duplicates blocked all saves "
        f"(was {before_log_len}, now {after_log_len})"
    )

    assert file_a_path.read_bytes() == before_a, "file A must be unchanged on disk"
    assert file_b_path.read_bytes() == before_b, "file B must be unchanged on disk"
