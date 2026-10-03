"""The reason ``elspais edit`` records for a change to an Active requirement.

Each test writes a small project into ``tmp_path`` -- one Active requirement,
one Draft requirement, and the requirement both implement -- and enters the
command at ``run()``, as the CLI does. The author is pinned through the git
environment variables so it resolves without ``gh``.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytest

ACTIVE = "REQ-d00001"
DRAFT = "REQ-d00002"
PARENT = "REQ-p00001"
OTHER_PARENT = "REQ-p00002"
REASON = "the safety review asked for it"

_CONFIG = """version = 5

[project]
name = "edit-reason"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""

_TRACKING_OFF = """
[changelog]
hash_current = false
"""

_PRD = f"""# Product

# {PARENT}: Parent

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL be a parent.

*End* *Parent* | **Hash**: 00000000
---

# {OTHER_PARENT}: Other Parent

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL be another parent.

*End* *Other Parent* | **Hash**: 00000000
---
"""

_DEV = f"""# Development

# {ACTIVE}: Active Child

**Level**: DEV | **Status**: Active | **Implements**: {PARENT}

## Assertions

A. The system SHALL do X.

## Changelog

- 2026-01-01 | abcd1234 | - | Old Author (<old@test.org>) | Initial version

*End* *Active Child* | **Hash**: abcd1234
---

# {DRAFT}: Draft Child

**Level**: DEV | **Status**: Draft | **Implements**: {PARENT}

## Assertions

A. The system SHALL do Y.

*End* *Draft Child* | **Hash**: 1234abcd
---
"""


@pytest.fixture(autouse=True)
def _author(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Reason Tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "reason@test.org")


def _project(tmp_path: Path, tracking: bool = True) -> Path:
    (tmp_path / ".elspais.toml").write_text(_CONFIG + ("" if tracking else _TRACKING_OFF))
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "prd.md").write_text(_PRD)
    (spec / "dev.md").write_text(_DEV)
    (spec / "elsewhere.md").write_text("# Elsewhere\n")
    return tmp_path


def _snapshot(project: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted((project / "spec").iterdir())}


def _edit(project: Path, monkeypatch, req_id: str, **change) -> int:
    from elspais.commands.edit import run

    monkeypatch.chdir(project)
    args = argparse.Namespace(
        req_id=req_id,
        implements=change.get("implements"),
        status=change.get("status"),
        move_to=change.get("move_to"),
        message=change.get("message"),
        spec_dir=None,
        config=project / ".elspais.toml",
        dry_run=False,
        validate_refs=False,
        from_json=None,
    )
    return run(args)


def _batch(project: Path, monkeypatch, changes: list[dict], message: str | None = None) -> int:
    from elspais.commands.edit import run

    monkeypatch.chdir(project)
    source = project / "changes.json"
    source.write_text(json.dumps(changes))
    args = argparse.Namespace(
        req_id=None,
        from_json=str(source),
        message=message,
        spec_dir=None,
        config=project / ".elspais.toml",
        dry_run=False,
        validate_refs=False,
    )
    return run(args)


def _block(text: str, req_id: str) -> str:
    """The text of one requirement, from its header to its End marker."""
    start = text.index(f"# {req_id}:")
    end = text.index("*End*", start)
    return text[start : text.index("\n", end) + 1]


def _rows(block: str) -> list[str]:
    return [line for line in block.splitlines() if re.match(r"- \d{4}-\d{2}-\d{2} \|", line)]


def _end_hash(block: str) -> str:
    return re.search(r"\*\*Hash\*\*: (\S+)", block).group(1)


# The edits of the Active requirement the command can make, and the file the
# requirement is in afterwards.
ACTIVE_EDITS = [
    pytest.param({"implements": OTHER_PARENT}, "dev.md", id="implements"),
    pytest.param({"status": "Draft"}, "dev.md", id="status-active-to-draft"),
    pytest.param({"move_to": "elsewhere.md"}, "elsewhere.md", id="move-to"),
]


@pytest.mark.parametrize("message", [None, "", "   "], ids=["absent", "empty", "blank"])
@pytest.mark.parametrize("change, _dest", ACTIVE_EDITS)
# Verifies: REQ-d00325-H
def test_REQ_d00325_H_an_active_edit_without_a_reason_changes_no_file(
    tmp_path: Path, monkeypatch, capsys, change, _dest, message
):
    project = _project(tmp_path)
    before = _snapshot(project)

    exit_code = _edit(project, monkeypatch, ACTIVE, message=message, **change)

    assert exit_code == 1
    assert _snapshot(project) == before
    err = capsys.readouterr().err
    assert ACTIVE in err, err
    assert "--message" in err, err


@pytest.mark.parametrize("change, dest", ACTIVE_EDITS)
# Verifies: REQ-d00325-G
def test_REQ_d00325_G_an_active_edit_records_one_row_with_the_reason_and_the_hash(
    tmp_path: Path, monkeypatch, change, dest
):
    project = _project(tmp_path)
    old_rows = _rows(_block((project / "spec" / "dev.md").read_text(), ACTIVE))

    exit_code = _edit(project, monkeypatch, ACTIVE, message=REASON, **change)

    assert exit_code == 0
    block = _block((project / "spec" / dest).read_text(), ACTIVE)
    added = [row for row in _rows(block) if row not in old_rows]
    assert len(added) == 1, block
    cells = [cell.strip() for cell in added[0].split("|")]
    assert cells[-1] == REASON, added[0]
    assert cells[1] == _end_hash(block), block
    assert "Reason Tester" in added[0]


# Verifies: REQ-d00325-G+H
def test_REQ_d00325_H_making_a_draft_active_needs_the_reason_it_records(
    tmp_path: Path, monkeypatch, capsys
):
    project = _project(tmp_path)
    before = _snapshot(project)

    assert _edit(project, monkeypatch, DRAFT, status="Active") == 1
    assert _snapshot(project) == before
    assert DRAFT in capsys.readouterr().err

    assert _edit(project, monkeypatch, DRAFT, status="Active", message=REASON) == 0
    block = _block((project / "spec" / "dev.md").read_text(), DRAFT)
    assert "**Status**: Active" in block
    rows = _rows(block)
    assert len(rows) == 1, block
    assert rows[0].endswith(f"| {REASON}"), rows
    assert f"| {_end_hash(block)} |" in rows[0]


@pytest.mark.parametrize(
    "req_id, change",
    [
        pytest.param(DRAFT, {"implements": OTHER_PARENT}, id="draft-implements"),
        pytest.param(DRAFT, {"move_to": "elsewhere.md"}, id="draft-move"),
        pytest.param(ACTIVE, {"status": "Active"}, id="active-status-unchanged"),
    ],
)
# Verifies: REQ-d00325-G+H
def test_REQ_d00325_H_an_edit_touching_no_active_requirement_needs_no_reason(
    tmp_path: Path, monkeypatch, req_id, change
):
    project = _project(tmp_path)
    old_rows = _rows(_block((project / "spec" / "dev.md").read_text(), ACTIVE))

    assert _edit(project, monkeypatch, req_id, **change) == 0

    text = "".join(p.read_text() for p in (project / "spec").iterdir())
    assert _rows(_block(text, ACTIVE)) == old_rows
    assert "Reason Tester" not in text


@pytest.mark.parametrize("change, dest", ACTIVE_EDITS)
# Verifies: REQ-d00325-G+H
def test_REQ_d00325_H_without_changelog_tracking_no_reason_is_needed(
    tmp_path: Path, monkeypatch, change, dest
):
    project = _project(tmp_path, tracking=False)
    old_rows = _rows(_block((project / "spec" / "dev.md").read_text(), ACTIVE))

    assert _edit(project, monkeypatch, ACTIVE, **change) == 0

    block = _block((project / "spec" / dest).read_text(), ACTIVE)
    assert _rows(block) == old_rows


# Verifies: REQ-d00325-H
def test_REQ_d00325_H_a_batch_is_refused_whole_when_one_active_change_lacks_a_reason(
    tmp_path: Path, monkeypatch, capsys
):
    project = _project(tmp_path)
    before = _snapshot(project)
    changes = [
        {"req_id": DRAFT, "implements": [OTHER_PARENT]},
        {"req_id": ACTIVE, "implements": [OTHER_PARENT]},
    ]

    assert _batch(project, monkeypatch, changes) == 1

    assert _snapshot(project) == before
    err = capsys.readouterr().err
    assert ACTIVE in err, err
    assert "message" in err, err


@pytest.mark.parametrize(
    "per_change, command_message, expected",
    [
        pytest.param("the change's own reason", None, "the change's own reason", id="per-change"),
        pytest.param(None, REASON, REASON, id="command-fallback"),
        pytest.param("the change's own reason", REASON, "the change's own reason", id="both"),
    ],
)
# Verifies: REQ-d00325-G
def test_REQ_d00325_G_a_batch_records_each_changes_reason(
    tmp_path: Path, monkeypatch, per_change, command_message, expected
):
    project = _project(tmp_path)
    old_rows = _rows(_block((project / "spec" / "dev.md").read_text(), ACTIVE))
    change = {"req_id": ACTIVE, "implements": [OTHER_PARENT]}
    if per_change is not None:
        change["message"] = per_change

    assert _batch(project, monkeypatch, [change], message=command_message) == 0

    block = _block((project / "spec" / "dev.md").read_text(), ACTIVE)
    added = [row for row in _rows(block) if row not in old_rows]
    assert len(added) == 1, block
    assert added[0].endswith(f"| {expected}"), added
    assert f"| {_end_hash(block)} |" in added[0]
