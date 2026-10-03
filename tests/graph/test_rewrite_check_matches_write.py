"""The rewrite check reports every part a write of its file would change.

Validates REQ-d00132-N: a part whose text on disk differs from what a write
of its file gives it is reported by ``spec.needs_rewrite``, whether the build
changed the part or only the write does. The fix operation is the remedy the
check names, so after it the check passes.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
from pathlib import Path

import pytest

from tests.core.graph_test_helpers import end_marker_hash, requirement_block

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

PROJECT_TOML = """version = 5

[project]
name = "rewrite"
namespace = "REQ"

# Changelog upkeep is a separate remedy; leave it out of what fix writes here.
[changelog]
hash_current = false
"""

# A heading-less part (a definition block) between two sections, one blank
# line before it: the form a write gives it.
CANONICAL_TAIL = (
    "### Notes\n\nSome notes.\n\nGadget\n: A defined thing.\n\n### More\n\nMore notes.\n\n"
)
# The same part with two blank lines before it.
SPACED_TAIL = (
    "### Notes\n\nSome notes.\n\n\nGadget\n: A defined thing.\n\n### More\n\nMore notes.\n\n"
)

CANONICAL_ID = "REQ-d00001"
UPPER_LEVEL_ID = "REQ-d00002"
NO_IMPLEMENTS_ID = "REQ-d00003"
SPACED_PART_ID = "REQ-d00004"
BODY_ONLY_ID = "REQ-d00005"
BODY_ONLY_UNSPACED_ID = "REQ-d00006"
CANONICAL_IDS = {CANONICAL_ID, BODY_ONLY_ID}
NON_CANONICAL_IDS = {UPPER_LEVEL_ID, NO_IMPLEMENTS_ID, SPACED_PART_ID, BODY_ONLY_UNSPACED_ID}
ALL_IDS = NON_CANONICAL_IDS | CANONICAL_IDS


def _requirement(
    req_id: str,
    title: str,
    *,
    level: str = "dev",
    implements: str | None = "-",
    tail: str = "",
) -> str:
    """One requirement whose recorded hash matches its assertion as written."""
    from elspais.utilities.hasher import compute_normalized_hash

    assertion = f"The tool SHALL {title.lower()}."
    digest = compute_normalized_hash([("A", assertion)])
    meta = f"**Level**: {level} | **Status**: Active"
    if implements is not None:
        meta += f" | **Implements**: {implements}"
    return (
        f"## {req_id}: {title}\n\n{meta}\n\n{title} body.\n\n"
        f"### Assertions\n\nA. {assertion}\n\n{tail}"
        f"*End* *{title}* | **Hash**: {digest}\n"
    )


def _body_only(req_id: str, title: str, *, blank_before_end: bool = True) -> str:
    """A requirement whose text ends in its body: no assertions, no sections."""
    gap = "\n" if blank_before_end else ""
    return (
        f"## {req_id}: {title}\n\n**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"{title} body.\n{gap}*End* *{title}* | **Hash**: N/A\n"
    )


def _write_project(root: Path) -> Path:
    """A spec project with one canonical requirement and one per write-time difference."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".elspais.toml").write_text(PROJECT_TOML, encoding="utf-8")
    spec = root / "spec"
    spec.mkdir()
    (spec / "dev.md").write_text(
        "# Dev\n\n"
        + "\n".join(
            [
                _requirement(CANONICAL_ID, "Canon", tail=CANONICAL_TAIL),
                _requirement(UPPER_LEVEL_ID, "Upper", level="DEV"),
                _requirement(NO_IMPLEMENTS_ID, "Bare", implements=None),
                _requirement(SPACED_PART_ID, "Spaced", tail=SPACED_TAIL),
                _body_only(BODY_ONLY_ID, "Plain"),
                _body_only(BODY_ONLY_UNSPACED_ID, "Tight", blank_before_end=False),
            ]
        ),
        encoding="utf-8",
    )
    return root


def _needs_rewrite(graph):
    from elspais.commands.health import check_spec_needs_rewrite

    return check_spec_needs_rewrite(graph, None)


def _parts_a_write_changes(graph) -> set[str]:
    """Ids of every part ``_changed_beyond_edits`` names in a spec or journey file."""
    from elspais.graph import NodeKind
    from elspais.graph.GraphNode import FileType
    from elspais.graph.render import _changed_beyond_edits

    named: set[str] = set()
    for file_node in graph.nodes_by_kind(NodeKind.FILE):
        if file_node.get_field("file_type") not in (FileType.SPEC, FileType.JOURNEY):
            continue
        disk_text = Path(file_node.get_field("absolute_path")).read_text(encoding="utf-8")
        resolver = getattr(graph.repo_for_node(file_node).graph, "_resolver", None)
        for entry in _changed_beyond_edits(file_node, disk_text, {}, resolver):
            named.add(entry["node_id"])
    return named


def _run_fix(root: Path, *, dry_run: bool) -> tuple[int, str]:
    """Run the fix command with cwd pinned to the project root; return (code, stdout)."""
    from elspais.commands.fix_cmd import run

    args = argparse.Namespace(
        req_id=None,
        dry_run=dry_run,
        spec_dir=root / "spec",
        config=root / ".elspais.toml",
        verbose=False,
        quiet=False,
        message=None,
    )
    old_cwd = os.getcwd()
    os.chdir(root)
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = run(args)
    finally:
        os.chdir(old_cwd)
    return code, stdout.getvalue()


# Verifies: REQ-d00132-N
def test_check_reports_each_part_a_write_would_change_and_not_the_canonical_one(
    tmp_path: Path,
):
    from elspais.graph.factory import build_graph
    from elspais.graph.render import CANONICAL_FORM_REASON

    root = _write_project(tmp_path / "project")
    check = _needs_rewrite(build_graph(repo_root=root))

    assert not check.passed
    reported = {f.node_id: f.message for f in check.findings}
    assert set(reported) == NON_CANONICAL_IDS
    for req_id in NON_CANONICAL_IDS:
        assert CANONICAL_FORM_REASON in reported[req_id], req_id


# Verifies: REQ-d00132-N
@pytest.mark.parametrize(
    "fixture",
    [
        pytest.param(None, id="tmp-project"),
        pytest.param("e2e-standard", id="e2e-standard"),
        pytest.param("e2e-jira-edge", id="e2e-jira-edge"),
        pytest.param("e2e-named-custom", id="e2e-named-custom"),
        pytest.param("e2e-fda-numeric", id="e2e-fda-numeric"),
        pytest.param("hht-like", id="hht-like"),
    ],
)
def test_every_part_a_write_changes_is_reported(tmp_path: Path, fixture: str | None):
    from elspais.graph.factory import build_graph

    if fixture is None:
        root = _write_project(tmp_path / "project")
    else:
        root = tmp_path / fixture
        shutil.copytree(FIXTURES / fixture, root)

    graph = build_graph(repo_root=root)
    named = _parts_a_write_changes(graph)
    reported = {f.node_id for f in _needs_rewrite(graph).findings}

    assert named <= reported, sorted(named - reported)


# Verifies: REQ-d00132-N
def test_fix_writes_what_the_check_reports_and_moves_no_hash(tmp_path: Path):
    from elspais.graph.factory import build_graph

    root = _write_project(tmp_path / "project")
    dev = root / "spec" / "dev.md"
    before = dev.read_text(encoding="utf-8")
    hashes_before = {req_id: end_marker_hash(before, req_id) for req_id in ALL_IDS}

    code, listing = _run_fix(root, dry_run=True)
    assert code == 0, listing
    assert dev.read_text(encoding="utf-8") == before
    lines = listing.splitlines()
    for req_id in NON_CANONICAL_IDS:
        assert any(req_id in ln and "write in canonical form" in ln for ln in lines), listing
    for req_id in CANONICAL_IDS:
        assert req_id not in listing, listing

    code, out = _run_fix(root, dry_run=False)
    assert code == 0, out

    check = _needs_rewrite(build_graph(repo_root=root))
    assert check.passed, [(f.node_id, f.message) for f in check.findings]

    after = dev.read_text(encoding="utf-8")
    assert {req_id: end_marker_hash(after, req_id) for req_id in ALL_IDS} == hashes_before
    # A requirement already canonical is written exactly as it was.
    for req_id in CANONICAL_IDS:
        assert requirement_block(after, req_id) == requirement_block(before, req_id)


# Verifies: REQ-d00132-N
@pytest.mark.parametrize("req_id", [CANONICAL_ID, SPACED_PART_ID])
def test_heading_less_part_after_a_section_renders_with_one_blank_line(tmp_path: Path, req_id: str):
    from elspais.graph.factory import build_graph
    from elspais.graph.render import render_node

    root = _write_project(tmp_path / "project")
    rendered = render_node(build_graph(repo_root=root).find_by_id(req_id))

    assert "Some notes.\n\nGadget\n: A defined thing." in rendered
    assert "\n\n\n" not in rendered


# Verifies: REQ-d00132-N
def test_render_parse_render_is_a_fixed_point(tmp_path: Path):
    from elspais.graph.factory import build_graph
    from elspais.graph.render import render_file

    root = _write_project(tmp_path / "project")
    dev = root / "spec" / "dev.md"

    first = render_file(build_graph(repo_root=root).find_by_id(CANONICAL_ID).file_node())
    dev.write_text(first, encoding="utf-8")
    graph = build_graph(repo_root=root)
    second = render_file(graph.find_by_id(CANONICAL_ID).file_node())

    assert second == first
    assert _needs_rewrite(graph).passed


# Verifies: REQ-d00132-N
@pytest.mark.parametrize("req_id", [BODY_ONLY_ID, BODY_ONLY_UNSPACED_ID])
def test_requirement_ending_in_its_body_renders_one_blank_line_before_end(
    tmp_path: Path, req_id: str
):
    from elspais.graph.factory import build_graph
    from elspais.graph.render import render_node

    root = _write_project(tmp_path / "project")
    node = build_graph(repo_root=root).find_by_id(req_id)
    rendered = render_node(node)

    assert f"{node.get_label()} body.\n\n*End*" in rendered
    assert "\n\n\n" not in rendered


CHANGELOG_TOML = """version = 5

[project]
name = "rewrite"
namespace = "REQ"

[changelog]
hash_current = true
"""

FIX_AUTHOR = {"name": "Test User", "id": "test@test.org"}


def _write_changelogged_project(root: Path, *, level: str, assertion: str) -> Path:
    """One Active requirement whose changelog records the hash of ``The tool SHALL go.``."""
    from elspais.utilities.hasher import compute_normalized_hash

    recorded = compute_normalized_hash([("A", "The tool SHALL go.")])
    root.mkdir(parents=True, exist_ok=True)
    (root / ".elspais.toml").write_text(CHANGELOG_TOML, encoding="utf-8")
    (root / "spec").mkdir()
    (root / "spec" / "dev.md").write_text(
        "# Dev\n\n"
        f"## {CANONICAL_ID}: Go\n\n"
        f"**Level**: {level} | **Status**: Active | **Implements**: -\n\n"
        "Go body.\n\n"
        f"### Assertions\n\nA. {assertion}\n\n"
        "### Changelog\n\n"
        f"- 2026-01-01 | {recorded} | - | Alice (<a@b.org>) | Initial version\n\n"
        f"*End* *Go* | **Hash**: {recorded}\n",
        encoding="utf-8",
    )
    return root


def _changelog_rows(text: str) -> list[str]:
    block = requirement_block(text, CANONICAL_ID)
    return [ln for ln in block.splitlines() if ln.startswith("- 2")]


# Verifies: REQ-d00132-N
@pytest.mark.parametrize(
    ("level", "assertion", "rows_added"),
    [
        pytest.param("DEV", "The tool SHALL go.", 0, id="formatting-only"),
        pytest.param("dev", "The tool SHALL go far.", 1, id="hash-changed"),
    ],
)
def test_fixing_one_requirement_records_a_changelog_entry_only_for_a_hash_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, level: str, assertion: str, rows_added: int
):
    from elspais.commands.fix_cmd import run
    from elspais.graph.factory import build_graph

    monkeypatch.setattr(
        "elspais.utilities.changelog_author.resolve_changelog_author",
        lambda *_a, **_k: FIX_AUTHOR,
    )
    root = _write_changelogged_project(tmp_path / "project", level=level, assertion=assertion)
    dev = root / "spec" / "dev.md"
    rows_before = _changelog_rows(dev.read_text(encoding="utf-8"))

    args = argparse.Namespace(
        req_id=CANONICAL_ID,
        dry_run=False,
        spec_dir=root / "spec",
        config=root / ".elspais.toml",
        verbose=False,
        quiet=False,
        message=None,
    )
    monkeypatch.chdir(root)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert run(args) == 0

    after = dev.read_text(encoding="utf-8")
    assert "**Level**: dev | **Status**: Active" in requirement_block(after, CANONICAL_ID)
    assert len(_changelog_rows(after)) == len(rows_before) + rows_added
    assert _needs_rewrite(build_graph(repo_root=root)).passed
