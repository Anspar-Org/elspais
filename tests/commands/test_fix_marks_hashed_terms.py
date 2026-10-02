"""The fix command marks a *Defined Term* in the text a requirement's hash covers.

Validates REQ-d00132-L: a save leaves that text as written for a requirement
no mutation changed, so fixing is the deliberate act that marks it. The bulk
fix marks every requirement; fixing one requirement marks that one alone.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
from pathlib import Path

import pytest

from tests.core.graph_test_helpers import (
    NEIGHBOUR_ASSERTION,
    end_marker_hash,
    requirement_block,
    write_unmarked_term_repo,
)

MARKED_EDITED = "The tool SHALL make a *Widget*."
MARKED_NEIGHBOUR = "The tool SHALL count every *Widget*."


def _hash_of(assertion: str) -> str:
    from elspais.utilities.hasher import compute_normalized_hash

    return compute_normalized_hash([("A", assertion)])


def _run_fix(root: Path, req_id: str | None, *, dry_run: bool = False) -> tuple[int, str, str]:
    """Run the fix command with cwd pinned to the project root; return (code, stdout, stderr)."""
    from elspais.commands.fix_cmd import run

    args = argparse.Namespace(
        req_id=req_id,
        dry_run=dry_run,
        spec_dir=root / "spec",
        config=root / ".elspais.toml",
        verbose=False,
        quiet=False,
        message=None,
    )
    old_cwd = os.getcwd()
    os.chdir(root)
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = run(args)
    finally:
        os.chdir(old_cwd)
    return code, stdout.getvalue(), stderr.getvalue()


def _needs_rewrite(root: Path):
    from elspais.commands.health import check_spec_needs_rewrite
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    graph = build_graph(repo_root=root)
    return check_spec_needs_rewrite(graph, get_config(None, root))


# Verifies: REQ-d00132-L
@pytest.mark.parametrize(
    "extra_toml",
    [
        pytest.param("", id="changelog-enforced"),
        pytest.param("\n[changelog]\nhash_current = false\n", id="changelog-not-enforced"),
    ],
)
def test_REQ_d00132_L_fix_marks_the_term_and_moves_the_hash_of_every_requirement(
    tmp_path: Path, extra_toml: str
):
    spec = write_unmarked_term_repo(tmp_path, extra_toml=extra_toml)

    before = _needs_rewrite(tmp_path)
    assert before.passed is False
    flagged = {f.node_id: f.message for f in before.findings}
    assert "non_canonical_term" in flagged.get("REQ-d00002", ""), flagged
    assert "non_canonical_term" in flagged.get("REQ-d00001", ""), flagged

    code, _out, err = _run_fix(tmp_path, None)

    assert code == 0, err
    text = (spec / "dev.md").read_text(encoding="utf-8")
    assert f"A. {MARKED_NEIGHBOUR}" in requirement_block(text, "REQ-d00002")
    assert end_marker_hash(text, "REQ-d00002") == _hash_of(MARKED_NEIGHBOUR)
    assert f"A. {MARKED_EDITED}" in requirement_block(text, "REQ-d00001")
    assert end_marker_hash(text, "REQ-d00001") == _hash_of(MARKED_EDITED)

    after = _needs_rewrite(tmp_path)
    assert after.passed is True, [(f.node_id, f.message) for f in after.findings]


# Verifies: REQ-d00132-L
def test_REQ_d00132_L_fixing_one_requirement_leaves_its_neighbour_as_written(
    tmp_path: Path,
):
    spec = write_unmarked_term_repo(tmp_path)
    neighbour_before = requirement_block(
        (spec / "dev.md").read_text(encoding="utf-8"), "REQ-d00002"
    )

    code, _out, err = _run_fix(tmp_path, "REQ-d00001")

    assert code == 0, err
    text = (spec / "dev.md").read_text(encoding="utf-8")
    assert f"A. {MARKED_EDITED}" in requirement_block(text, "REQ-d00001")
    assert end_marker_hash(text, "REQ-d00001") == _hash_of(MARKED_EDITED)
    assert requirement_block(text, "REQ-d00002") == neighbour_before
    assert f"A. {NEIGHBOUR_ASSERTION}" in neighbour_before
    assert end_marker_hash(text, "REQ-d00002") == _hash_of(NEIGHBOUR_ASSERTION)


# Verifies: REQ-d00132-L
def test_REQ_d00132_L_a_fix_dry_run_names_the_hash_marking_will_write(tmp_path: Path):
    """The hash a fix writes is the hash of the marked text, and a dry run says so."""
    spec = write_unmarked_term_repo(tmp_path)
    before = (spec / "dev.md").read_bytes()

    code, out, err = _run_fix(tmp_path, None, dry_run=True)

    assert code == 0, err
    unmarked_hash = _hash_of(NEIGHBOUR_ASSERTION)
    assert f"Would fix REQ-d00002: hash {unmarked_hash} -> {_hash_of(MARKED_NEIGHBOUR)}" in out, out
    assert (spec / "dev.md").read_bytes() == before
