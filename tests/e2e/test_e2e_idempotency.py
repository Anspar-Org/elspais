# Verifies: REQ-d00248-A
"""End-to-end idempotency regression guard for `elspais fix`.

Cross-cutting regression test for markdown render hygiene: fenced code
block preservation, emphasis stripping at
user-text capture sites (term names, journey actor/goal/context), and
REMAINDER emphasis handling.

Validates REQ-d00248-A: running `elspais fix` twice in succession on the
same project must produce byte-identical files. The fixture deliberately
includes the bug-trigger content classes:
  - fenced code blocks with markdown emphasis (Bug 1)
  - glossary term with emphasis-wrapped name (Bug 2)
  - user journey with emphasized actor field (Bug 4)
  - REMAINDER section between requirements containing emphasized text
  - a requirement section holding only a definition list, and text written
    after a definition list (REQ-d00248-B, REQ-d00132-O)
  - a metadata block written in another spelling than its canonical one
    (REQ-d00248-B, REQ-d00132-P)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from .conftest import run_elspais
from .helpers import (
    Requirement,
    base_config,
    build_project,
    resolve_elspais,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        resolve_elspais() is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Fixture content (the bug-trigger surface)
# ---------------------------------------------------------------------------

# REMAINDER text between requirements that contains emphasized markup.
# This exercises render of REMAINDER nodes carrying ** and * markers.
_REMAINDER_PROSE = (
    "## Background\n"
    "\n"
    "This section sits between requirements as a top-level REMAINDER.\n"
    "It mentions *Authentication* and **Multi-Factor Authentication**\n"
    "to exercise emphasis preservation in REMAINDER render.\n"
)

# REQ body containing a fenced code block with emphasized markdown content.
# The fenced lines must round-trip verbatim (Bug 1).
_REQ_BODY_WITH_FENCED = (
    "The login flow integrates with *Authentication*.\n"
    "\n"
    "Example payload:\n"
    "\n"
    "```json\n"
    '{"user": "**bold-name**", "note": "*italic-note*", "code": "`literal`"}\n'
    "```\n"
    "\n"
    "Note the `inline-code` outside the fence as well.\n"
)

# Requirement prose around definition lists: a section whose only text is a
# definition list, and text that follows one. Each keeps its heading and its
# place when the fix brings the requirement into canonical form.
_RATIONALE_WITH_DEFINITIONS = (
    "Text before the list.\n"
    "\n"
    "Sprocket\n"
    ": A toothed wheel that engages a chain.\n"
    "\n"
    "Text after the list.\n"
    "\n"
    "## Definitions\n"
    "\n"
    "Pinion\n"
    ": The smaller of two meshing gears."
)

# Glossary file with an emphasis-wrapped term name (Bug 2).
# Definition list syntax: term-line followed by ": definition".
_GLOSSARY_CONTENT = (
    "# Glossary\n"
    "\n"
    "**Email Address**\n"
    ": A unique technical identifier used to deliver electronic messages.\n"
    "\n"
    "Authentication\n"
    ": The process of verifying a user identity.\n"
    "\n"
    "*Multi-Factor Authentication*\n"
    ": An *Authentication* method requiring two or more verification factors.\n"
)

# User journey file with emphasized actor field (Bug 4).
_JOURNEY_CONTENT = (
    "# User Journeys\n"
    "\n"
    "---\n"
    "\n"
    "### JNY-001: Site Login\n"
    "\n"
    "**Actor**: **Sarah (Site 101)**\n"
    "**Goal**: Successfully *authenticate* and access the platform\n"
    "\n"
    "## Context\n"
    "\n"
    "Sarah logs in at the start of each shift.\n"
    "\n"
    "## Steps\n"
    "\n"
    "1. Sarah enters her **Email Address** and password\n"
    "2. System verifies credentials\n"
    "3. System creates session\n"
    "\n"
    "## Validates\n"
    "\n"
    "Validates: REQ-p00001-A\n"
    "\n"
    "*End* *JNY-001 Site Login*\n"
    "---\n"
)


# A requirement whose metadata block is spelled out of canonical form: its
# fields out of order and no Implements field. Canonical form respells the
# block and keeps what it declares (REQ-d00132-P).
_RESPELLED_METADATA_REQ = (
    "## REQ-p00004: Respelled\n"
    "\n"
    "**Status**: Draft | **Level**: PRD\n"
    "\n"
    "### Assertions\n"
    "\n"
    "A. The system SHALL keep its declarations.\n"
    "\n"
    "*End* *Respelled* | **Hash**: 00000000\n"
)

# ---------------------------------------------------------------------------
# Module-scoped fixture: build the project once with the bug-trigger surface.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Build a minimal project that exercises the render-hygiene bug-trigger content."""
    root = tmp_path_factory.mktemp("e2e_idempotency")

    cfg = base_config(
        name="e2e-idempotency",
        # Allow REMAINDER + journeys without hierarchy noise.
        allow_structural_orphans=True,
        # Mirror the production self-config and the `init` template: exclude
        # the generated outputs (INDEX.md, the _generated directory) from spec
        # scanning, so a fix never reads back and tidies a file it generates.
        skip_files=["INDEX.md"],
        skip_dirs=["spec/_generated"],
    )
    # Enable terms output so `elspais fix` exercises the glossary
    # generation pipeline as part of settling.
    cfg["terms"] = {
        "output_dir": "spec/_generated",
        "markup_styles": ["*", "**"],
    }

    prd = Requirement(
        req_id="REQ-p00001",
        title="User Authentication",
        level="PRD",
        body=_REQ_BODY_WITH_FENCED,
        assertions=[
            ("A", "The system SHALL authenticate users via *Authentication*."),
            ("B", "The system SHALL deliver notifications to each **Email Address**."),
        ],
    )
    prd2 = Requirement(
        req_id="REQ-p00002",
        title="Notifications",
        level="PRD",
        assertions=[("A", "The system SHALL send email notifications.")],
    )

    prd3 = Requirement(
        req_id="REQ-p00003",
        title="Gearing",
        level="PRD",
        assertions=[("A", "The system SHALL transmit motion.")],
        rationale=_RATIONALE_WITH_DEFINITIONS,
    )

    # Spec file: REQ + REMAINDER between requirements + REQ.
    # write_spec_file concatenates Requirements; we need a REMAINDER block
    # between them, so build the file manually.
    spec_path = root / "spec" / "prd-core.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_text = (
        prd.render()
        + _REMAINDER_PROSE
        + "\n"
        + prd2.render()
        + prd3.render()
        + "\n"
        + _RESPELLED_METADATA_REQ
    )
    spec_path.write_text(spec_text)

    build_project(
        root,
        cfg,
        spec_files=None,  # we wrote prd-core.md manually above
        extra_files={
            "spec/glossary.md": _GLOSSARY_CONTENT,
            "spec/journeys.md": _JOURNEY_CONTENT,
        },
        init_git=True,
    )

    return root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    """Capture byte contents of every non-VCS, non-state file under root.

    Excludes `.git/` (mutates with every git operation) and `.elspais/`
    (daemon socket / cache state, not a render artifact).
    """
    snapshot: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if parts and parts[0] in {".git", ".elspais"}:
            continue
        snapshot[str(rel)] = path.read_bytes()
    return snapshot


def _commit_settled_state(root: Path) -> None:
    """Stage and commit any files produced by the first fix run."""
    env = {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": __import__("os").environ.get("PATH", ""),
    }
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True, env=env, check=False)
    subprocess.run(
        ["git", "commit", "-m", "settle", "--allow-empty"],
        cwd=root,
        capture_output=True,
        env=env,
        check=False,
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestFixIdempotency:
    """Validates REQ-d00248-A: `elspais fix` is idempotent across runs."""

    def test_REQ_d00248_A_fix_twice_produces_no_changes(self, project):
        # Verifies: REQ-d00248-A
        # First run: settle the project. May produce hash updates, generated
        # glossary/term-index artifacts, etc.
        first = run_elspais("fix", cwd=project)
        assert first.returncode == 0, (
            f"first `elspais fix` failed: stderr={first.stderr!r} stdout={first.stdout!r}"
        )

        # Verifies: REQ-d00132-O
        # The first run kept every heading and every line of text, in order.
        settled = (project / "spec" / "prd-core.md").read_text()
        for heading in ("Rationale", "Definitions"):
            assert any(
                line.lstrip("#").strip() == heading and line.startswith("#")
                for line in settled.splitlines()
            ), f"`elspais fix` dropped the {heading} heading:\n{settled}"
        order = [
            "Text before the list.",
            "Sprocket",
            "Text after the list.",
            "Definitions",
            "Pinion",
        ]
        positions = [settled.index(text) for text in order]
        assert positions == sorted(positions), settled

        # Verifies: REQ-d00132-P
        # The metadata block is respelled in its one form, declaring the same.
        assert "**Level**: prd | **Status**: Draft | **Implements**: -" in settled, settled
        assert "**Status**: Draft | **Level**: PRD" not in settled

        # Commit so that any subsequent disk diffs are attributable to the
        # second `fix` run rather than to remnants of the first.
        _commit_settled_state(project)

        before = _snapshot_tree(project)
        assert before, "expected at least one tracked file in the project tree"

        # Second run: must be a complete no-op on disk.
        second = run_elspais("fix", cwd=project)
        assert second.returncode == 0, (
            f"second `elspais fix` failed: stderr={second.stderr!r} stdout={second.stdout!r}"
        )

        after = _snapshot_tree(project)

        # Compare key sets first to surface added/removed files clearly.
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        assert not added, f"second `elspais fix` created new files: {added}"
        assert not removed, f"second `elspais fix` removed files: {removed}"

        # Then byte-equality per file -- surfaces the offending file in the
        # assertion message rather than dumping every diff.
        changed = [path for path in before if before[path] != after[path]]
        assert not changed, (
            f"second `elspais fix` modified files (expected no-op): {changed}\n"
            f"This is the regression signature for markdown render hygiene "
            f"(fenced code preservation, emphasis stripping, REMAINDER round-trip)."
        )
