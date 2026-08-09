# Verifies: REQ-d00131-B, REQ-d00131-J
"""Tests for blank lines *inside* an assertion's continuation text.

An assertion's text may run over several lines, and those lines may be
separated by blank lines — a paragraph followed by a GFM table is the
common case. Under GFM a table must be preceded by a blank line; without
it the table joins the preceding paragraph and stops rendering as a table
(markdownlint MD058).

The parse side must therefore carry interior blank lines through to the
assertion node's text, so that the REQUIREMENT render (REQ-d00131-B) puts
them back on disk when ``elspais fix`` rewrites the file. Trailing blank
lines, by contrast, are structure between assertions and are stripped —
that stays true.

REQ-d00131-J's normalized-text hashing is what makes preservation safe:
normalization collapses newlines to spaces and runs of spaces to one, so
an interior blank line cannot alter a requirement's hash. That property is
pinned directly here.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

# normalized-text hash mode is the default. Changelog enforcement is OFF so
# that a fix run touches nothing but the End marker's hash.
CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
"""

# Draft requirement, no hash on the End marker, whose assertion A is a
# paragraph, a blank line, and a 3-row GFM table.
REQ_ASSERTION_WITH_TABLE = """\
# REQ-d00001: Task Panel Ordering

**Level**: dev | **Status**: Draft | **Implements**: -

Some body text here.

## Assertions

A. The panel SHALL display the following task types in the priority order listed:

| Priority | Task Type |
| :---- | :---- |
| 1 | Urgent |

B. The panel SHALL refresh on demand.

*End* *Task Panel Ordering*
---
"""

# Assertion A carries two consecutive blank lines mid-text, so a
# reconstruction driven by real line-number gaps differs observably from
# one that hardcodes a single blank line.
REQ_ASSERTION_WITH_DOUBLE_GAP = """\
# REQ-d00002: Double Gap

**Level**: dev | **Status**: Draft | **Implements**: -

Some body text here.

## Assertions

A. The system SHALL state the first paragraph.


The system SHALL state the second paragraph after two blank lines.

B. The system SHALL do something else.

*End* *Double Gap*
---
"""

# Assertion A's continuation ends with blank lines before assertion B, so
# "trailing" is unambiguous: blank lines between assertions, not before
# the End marker.
REQ_ASSERTION_WITH_TRAILING_BLANKS = """\
# REQ-d00003: Trailing Blanks

**Level**: dev | **Status**: Draft | **Implements**: -

Some body text here.

## Assertions

A. The system SHALL state the first paragraph.

The continuation line that ends the assertion.


B. The system SHALL do something else.

*End* *Trailing Blanks*
---
"""

# Two requirements in one file. REQ-p00001's *End* marker is hash-less in
# the literal below; the helper stamps its genuine computed hash before the
# fix run, so REQ-p00001 needs nothing fixed. REQ-p00002 stays hash-less and
# is what triggers the whole-file rewrite.
TWO_REQS = """\
## REQ-p00001: Already Correct

**Level**: prd | **Status**: Draft | **Implements**: -

Body text for the first requirement.

### Assertions

A. The system SHALL keep this requirement exactly as written.

B. The system SHALL leave its spacing alone.

*End* *Already Correct*
---

## REQ-p00002: Needs A Hash

**Level**: prd | **Status**: Draft | **Implements**: -

Body text for the second requirement.

### Assertions

A. The system SHALL acquire a hash on its first fix run.

*End* *Needs A Hash*
---
"""

# The same two requirements, but wrapped in prose that is separated from
# every neighbour by TWO consecutive blank lines. None of that prose is the
# tool's to restyle.
TWO_REQS_WITH_PROSE = """\
# Spec Document

Intro prose that the tool did not write and must not restyle.


## REQ-p00001: Already Correct

**Level**: prd | **Status**: Draft | **Implements**: -

Body text for the first requirement.

### Assertions

A. The system SHALL keep this requirement exactly as written.

B. The system SHALL leave its spacing alone.

*End* *Already Correct*
---


Interstitial prose sitting between the two requirements.


## REQ-p00002: Needs A Hash

**Level**: prd | **Status**: Draft | **Implements**: -

Body text for the second requirement.

### Assertions

A. The system SHALL acquire a hash on its first fix run.

*End* *Needs A Hash*
---


Trailing prose after the last requirement.
"""

END_LINE_RE = re.compile(r"^\*End\*.*$", re.MULTILINE)
HASH_SEGMENT_RE = re.compile(r" \| \*\*Hash\*\*: [0-9a-f]{8}$")


def _make_project(tmp_path: Path, req_content: str) -> Path:
    """Create a minimal on-disk project with config and one spec file."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".elspais.toml").write_text(CONFIG_TOML)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "requirements.md").write_text(req_content)
    return tmp_path


def _build_graph(project: Path):
    """Build a graph for the test project."""
    from elspais.graph.factory import build_graph

    old_cwd = os.getcwd()
    os.chdir(project)
    try:
        return build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )
    finally:
        os.chdir(old_cwd)


def _assertion_text(graph, assertion_id: str) -> str:
    """Return the parsed text of an assertion node (its display label)."""
    from elspais.graph import NodeKind

    for node in graph.iter_by_kind(NodeKind.ASSERTION):
        if node.id == assertion_id:
            return node.get_label()
    raise AssertionError(f"Assertion {assertion_id} not found in graph")


def _run_fix(project: Path) -> int:
    """Run the bulk fix path with cwd pinned to the project root."""
    from elspais.commands.fix_cmd import run

    args = argparse.Namespace(
        req_id=None,
        dry_run=False,
        spec_dir=project / "spec",
        config=project / ".elspais.toml",
        verbose=False,
        quiet=False,
        message=None,
    )
    old_cwd = os.getcwd()
    os.chdir(project)
    try:
        return run(args)
    finally:
        os.chdir(old_cwd)


def _split_on_end_line(text: str) -> tuple[list[str], str]:
    """Return the file's lines with the *End* line removed, plus that line."""
    lines = text.splitlines()
    end_indices = [i for i, line in enumerate(lines) if line.startswith("*End*")]
    assert len(end_indices) == 1, f"Expected exactly one *End* line in:\n{text}"
    idx = end_indices[0]
    return lines[:idx] + lines[idx + 1 :], lines[idx]


def _stamp_real_hash(project: Path, req_id: str) -> str:
    """Write ``req_id``'s genuinely computed hash into its *End* marker.

    The value comes from the production hash function over the built graph,
    never from a hardcoded digest, so the requirement is left in the state a
    correct estate would already be in: nothing about it needs fixing.
    """
    from elspais.graph import NodeKind
    from elspais.graph.render import compute_hash_for_node

    graph = _build_graph(project)
    node = next(
        (n for n in graph.iter_by_kind(NodeKind.REQUIREMENT) if n.id == req_id),
        None,
    )
    assert node is not None, f"{req_id} not found in graph"
    computed = compute_hash_for_node(node, "normalized-text")
    assert computed, f"{req_id} must have hashable content, got {computed!r}"

    spec_file = project / "spec" / "requirements.md"
    lines = spec_file.read_text().splitlines(keepends=True)
    title = node.get_label()
    marker = f"*End* *{title}*"
    stamped = False
    for i, line in enumerate(lines):
        if line.startswith(marker):
            lines[i] = f"{marker} | **Hash**: {computed}\n"
            stamped = True
            break
    assert stamped, f"No {marker!r} line found to stamp in {spec_file}"
    spec_file.write_text("".join(lines))
    return computed


def _requirement_block(text: str, req_id: str) -> str:
    """Slice ``text`` from ``## <req_id>:`` through its *End* line inclusive."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith(f"## {req_id}:")]
    assert len(starts) == 1, f"Expected exactly one '## {req_id}:' header in:\n{text}"
    start = starts[0]
    ends = [i for i, line in enumerate(lines) if i > start and line.startswith("*End*")]
    assert ends, f"No *End* line after '## {req_id}:' in:\n{text}"
    return "".join(lines[start : ends[0] + 1])


class TestAssertionBlankLinePreservation:
    """Pins interior blank-line fidelity in assertion continuation text."""

    def test_blank_line_inside_assertion_survives_parsing(self, tmp_path):
        """The parsed assertion text must retain a blank line that separates
        the assertion's opening paragraph from a following GFM table, since
        REQUIREMENT render (REQ-d00131-B) can only re-emit what was parsed.
        """
        project = _make_project(tmp_path, REQ_ASSERTION_WITH_TABLE)
        graph = _build_graph(project)

        text = _assertion_text(graph, "REQ-d00001-A")

        assert "listed:\n\n| Priority" in text, (
            "The blank line before the table was lost at parse time; "
            f"assertion text was:\n{text!r}"
        )

    def test_blank_line_before_table_survives_fix(self, tmp_path):
        """A fix run that stamps a first hash must leave the file otherwise
        byte-identical — including the blank line before the table.
        """
        project = _make_project(tmp_path, REQ_ASSERTION_WITH_TABLE)
        spec_file = project / "spec" / "requirements.md"
        before = spec_file.read_text()

        rc = _run_fix(project)
        assert rc == 0, f"fix should succeed, got exit code {rc}"

        after = spec_file.read_text()

        assert "listed:\n\n| Priority | Task Type |" in after, (
            "fix removed the blank line between the assertion paragraph and "
            f"the table; file is now:\n{after}"
        )

        before_body, before_end = _split_on_end_line(before)
        after_body, after_end = _split_on_end_line(after)

        assert after_body == before_body, (
            "fix changed more than the *End* marker's hash:\n"
            f"  before: {before_body!r}\n"
            f"  after:  {after_body!r}"
        )
        assert after_end.startswith(before_end) and re.fullmatch(
            r"\*End\*.*\| \*\*Hash\*\*: [0-9a-f]{8}", after_end
        ), (
            "The only *End* line change must be the added Hash segment:\n"
            f"  before: {before_end!r}\n"
            f"  after:  {after_end!r}"
        )

    def test_multiple_interior_blank_lines_are_preserved_verbatim(self, tmp_path):
        """Two consecutive interior blank lines must both survive parsing —
        the reconstruction follows real line-number gaps rather than
        inserting one fixed blank line wherever a gap occurred.
        """
        project = _make_project(tmp_path, REQ_ASSERTION_WITH_DOUBLE_GAP)
        graph = _build_graph(project)

        text = _assertion_text(graph, "REQ-d00002-A")

        assert "\n\n\n" in text, (
            "Both interior blank lines must be preserved; assertion text was:\n" f"{text!r}"
        )

    def test_trailing_blank_lines_are_still_stripped(self, tmp_path):
        """Blank lines between the end of one assertion and the next are
        structure, not content: the parsed text must not end with them.
        """
        project = _make_project(tmp_path, REQ_ASSERTION_WITH_TRAILING_BLANKS)
        graph = _build_graph(project)

        text = _assertion_text(graph, "REQ-d00003-A")

        assert not text.endswith("\n"), (
            "Trailing blank lines before the next assertion must stay stripped; "
            f"assertion text was:\n{text!r}"
        )
        assert text.endswith("The continuation line that ends the assertion."), (
            "The assertion text must end at its last content line; got:\n" f"{text!r}"
        )


class TestRewriteTouchesNothingItWasNotAskedTo:
    """Pins blast radius: a whole-file rewrite alters only the fixed marker.

    `elspais fix` rewrites an entire spec file when any one requirement in it
    needs a hash. Everything the fix was not asked to change — neighbouring
    requirements, and prose the tool did not author — must come back byte for
    byte (REQ-d00131-B: render reproduces what was parsed).
    """

    def test_rewrite_leaves_other_requirements_byte_identical(self, tmp_path):
        """A requirement that needs no fixing must survive the rewrite
        triggered by a *different* requirement without a single byte moving.
        """
        project = _make_project(tmp_path, TWO_REQS)
        spec_file = project / "spec" / "requirements.md"
        _stamp_real_hash(project, "REQ-p00001")

        before = spec_file.read_text()
        before_block = _requirement_block(before, "REQ-p00001")

        rc = _run_fix(project)
        assert rc == 0, f"fix should succeed, got exit code {rc}"

        after = spec_file.read_text()
        after_block = _requirement_block(after, "REQ-p00001")

        assert after_block == before_block, (
            "REQ-p00001 needed no fixing but drifted across the rewrite "
            "triggered by REQ-p00002:\n"
            f"  before: {before_block!r}\n"
            f"  after:  {after_block!r}"
        )

        # And nothing else in the file moved either: the sole difference is
        # the Hash segment appended to REQ-p00002's End line.
        target_end = "*End* *Needs A Hash*"
        before_lines = [ln for ln in before.splitlines() if not ln.startswith(target_end)]
        after_lines = [ln for ln in after.splitlines() if not ln.startswith(target_end)]
        assert after_lines == before_lines, (
            "The rewrite changed lines outside REQ-p00002's *End* marker:\n"
            f"  before: {before_lines!r}\n"
            f"  after:  {after_lines!r}"
        )

        after_end = next(ln for ln in after.splitlines() if ln.startswith(target_end))
        assert HASH_SEGMENT_RE.search(after_end) and after_end.startswith(target_end), (
            "REQ-p00002's *End* line must differ only by the added Hash "
            f"segment; got {after_end!r}"
        )

    def test_rewrite_preserves_vertical_whitespace_outside_requirements(self, tmp_path):
        """Prose outside any requirement — and the double blank lines that
        separate it — is not the tool's to restyle across a rewrite.
        """
        project = _make_project(tmp_path, TWO_REQS_WITH_PROSE)
        spec_file = project / "spec" / "requirements.md"
        _stamp_real_hash(project, "REQ-p00001")

        before = spec_file.read_text()
        before_runs = before.count("\n\n\n")
        assert before_runs == 4, (
            "Fixture must carry four double-blank-line runs (before the first "
            f"requirement, between, and after the last); found {before_runs}"
        )

        rc = _run_fix(project)
        assert rc == 0, f"fix should succeed, got exit code {rc}"

        after = spec_file.read_text()

        # Control: the rewrite really happened, so the whitespace assertions
        # below are not passing vacuously.
        rewritten_end = next(
            ln for ln in after.splitlines() if ln.startswith("*End* *Needs A Hash*")
        )
        assert HASH_SEGMENT_RE.search(rewritten_end), (
            "REQ-p00002 must have acquired a hash, otherwise no rewrite "
            f"occurred; End line was {rewritten_end!r}"
        )

        for region, snippet in (
            ("intro prose", "must not restyle.\n\n\n## REQ-p00001:"),
            ("prose before the interstitial", "---\n\n\nInterstitial prose"),
            ("prose after the interstitial", "two requirements.\n\n\n## REQ-p00002:"),
            ("trailing prose", "---\n\n\nTrailing prose"),
        ):
            assert snippet in after, (
                f"The double blank line at the {region} was restyled by the "
                f"rewrite; expected {snippet!r} in:\n{after}"
            )

        after_runs = after.count("\n\n\n")
        assert after_runs == before_runs, (
            "The rewrite changed the number of double-blank-line runs "
            f"({before_runs} -> {after_runs}); file is now:\n{after}"
        )


class TestNormalizedHashIsBlankLineInvariant:
    """Pins REQ-d00131-J's normalization: interior blank lines cost no hash."""

    def test_preserving_blank_lines_does_not_change_the_computed_hash(self):
        """`compute_normalized_hash` collapses newlines to spaces and runs of
        spaces to one, so an interior blank line inside an assertion must
        yield the same hash — otherwise preserving blank lines would rewrite
        every stored hash in every estate.
        """
        from elspais.utilities.hasher import compute_normalized_hash

        without_gap = compute_normalized_hash([("A", "text one\nline two")])
        with_gap = compute_normalized_hash([("A", "text one\n\nline two")])

        assert with_gap == without_gap, (
            "An interior blank line changed the normalized hash "
            f"({without_gap!r} -> {with_gap!r}); preserving blank lines would "
            "silently invalidate every stored requirement hash"
        )
