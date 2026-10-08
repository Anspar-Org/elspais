"""A fix named for one requirement changes that requirement and its INDEX rows alone.

Every other file, every other part of the target's own file, and every
other INDEX row keep their bytes, even where a whole-file write would bring
them into canonical form.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

_CONFIG = """\
version = 5

[project]
name = "solo"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
"""

_TARGET = """\
## REQ-p00001: Target Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

Target intro.

## Assertions

A. The system SHALL validate input.

*End* *Target Requirement* | **Hash**: deadbeef
"""

# The neighbour is out of canonical form (assertion spacing, heading depth)
# and carries a stale hash, so a whole-file write would change it.
_NEIGHBOUR = """\
## REQ-p00002: Neighbour Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

Neighbour intro.

## Assertions
A. The system SHALL log output.
B. The system SHALL keep records.

*End* *Neighbour Requirement* | **Hash**: 00000000
"""

_CORE = "# Core\n\n" + _TARGET + "\n---\n\n" + _NEIGHBOUR

_OTHER = """\
# Other

## REQ-p00003: Other Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL archive data.

*End* *Other Requirement* | **Hash**: 11111111
"""


def _write_index(repo: Path) -> None:
    """Write INDEX.md as a full regeneration would, listing the hashes on disk."""
    from elspais.commands.index import _build_index_content
    from elspais.graph.factory import build_graph

    graph = build_graph(config_path=repo / ".elspais.toml", repo_root=repo)
    path, content, _reqs, _jnys = _build_index_content(graph, [repo / "spec"])
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def solo_repo(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / "spec").mkdir()
    (tmp_path / ".elspais.toml").write_text(_CONFIG)
    (tmp_path / "spec" / "core.md").write_text(_CORE)
    (tmp_path / "spec" / "other.md").write_text(_OTHER)
    _write_index(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _args(repo: Path, req_id: str, dry_run: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        req_id=req_id,
        dry_run=dry_run,
        spec_dir=None,
        config=repo / ".elspais.toml",
        message=None,
        quiet=False,
        verbose=False,
        git_root=repo,
    )


def _snapshot(repo: Path) -> dict[str, bytes]:
    return {str(p.relative_to(repo)): p.read_bytes() for p in sorted((repo / "spec").rglob("*.md"))}


def _changed_lines(before: bytes, after: bytes) -> list[int]:
    old = before.decode().split("\n")
    new = after.decode().split("\n")
    assert len(old) == len(new), "a named fix here changes no line count"
    return [i for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]


def _needing_rewrite(repo: Path) -> set[str]:
    """The parts spec.needs_rewrite reports as out of canonical form."""
    from elspais.commands.health import run_spec_checks
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    config = get_config(repo / ".elspais.toml", repo)
    graph = build_graph(config_path=repo / ".elspais.toml", repo_root=repo)
    return {
        finding.node_id
        for check in run_spec_checks(graph, config)
        if check.name == "spec.needs_rewrite" and not check.passed
        for finding in check.findings
    }


class TestNamedFixScope:
    """The named requirement is fixed; nothing else is."""

    # Verifies: REQ-d00330-C
    def test_only_target_lines_and_its_index_row_change(self, solo_repo, capsys):
        from elspais.commands.fix_cmd import run

        # A whole-file write would change the neighbour and the other file.
        assert {"REQ-p00002", "REQ-p00003"} <= _needing_rewrite(solo_repo)
        before = _snapshot(solo_repo)
        rc = run(_args(solo_repo, "REQ-p00001"))
        assert rc == 0, capsys.readouterr()
        after = _snapshot(solo_repo)

        assert after["spec/other.md"] == before["spec/other.md"]

        core = after["spec/core.md"].decode()
        # The neighbour keeps every byte, though it is out of canonical form.
        assert core.endswith(_NEIGHBOUR)
        assert core.startswith("# Core\n\n## REQ-p00001: Target Requirement\n")
        target_block = core[: core.index("\n---\n")]
        assert "deadbeef" not in target_block
        assert "### Assertions" in target_block  # the target's own canonical form

        index_rows = _changed_lines(before["spec/INDEX.md"], after["spec/INDEX.md"])
        index_lines = after["spec/INDEX.md"].decode().split("\n")
        assert [index_lines[i].split("|")[1].strip() for i in index_rows] == ["REQ-p00001"]
        assert "deadbeef" not in index_lines[index_rows[0]]
        # The other rows still list the hashes on disk.
        index_text = after["spec/INDEX.md"].decode()
        assert "00000000" in index_text and "11111111" in index_text

        out = capsys.readouterr().out
        assert "Fixed REQ-p00001" in out
        assert "INDEX.md row for REQ-p00001" in out
        # The parts left alone are still reported, so a full fix still has them.
        assert {"REQ-p00002", "REQ-p00003"} <= _needing_rewrite(solo_repo)
        assert "REQ-p00001" not in _needing_rewrite(solo_repo)

    # Verifies: REQ-d00330-C
    def test_second_named_fix_finds_nothing(self, solo_repo, capsys):
        from elspais.commands.fix_cmd import run

        assert run(_args(solo_repo, "REQ-p00001")) == 0
        settled = _snapshot(solo_repo)
        capsys.readouterr()
        assert run(_args(solo_repo, "REQ-p00001")) == 0
        assert _snapshot(solo_repo) == settled
        out = capsys.readouterr().out
        assert "already up to date" in out
        assert "INDEX.md row" not in out

    # Verifies: REQ-d00330-C, REQ-p00015-B
    def test_misshapen_index_row_is_reported_not_updated(self, solo_repo, capsys):
        from elspais.commands.fix_cmd import run

        index = solo_repo / "spec" / "INDEX.md"
        lines = index.read_text(encoding="utf-8").split("\n")
        (number,) = [i for i, line in enumerate(lines) if line.startswith("| REQ-p00001 ")]
        cells = lines[number][2:-2].split(" | ")
        (hash_cell,) = [i for i, cell in enumerate(cells) if cell.strip() == "deadbeef"]
        del cells[hash_cell]
        lines[number] = "| " + " | ".join(cells) + " |"
        index.chmod(0o644)
        index.write_text("\n".join(lines), encoding="utf-8")
        core = solo_repo / "spec" / "core.md"
        core.write_text(
            core.read_text().replace("SHALL validate input.", "SHALL validate every input.")
        )
        index_before = index.read_bytes()

        rc = run(_args(solo_repo, "REQ-p00001"))

        captured = capsys.readouterr()
        assert rc == 0, captured
        target_block = core.read_text()[: core.read_text().index("\n---\n")]
        assert "SHALL validate every input." in target_block
        assert "deadbeef" not in target_block
        assert "**Hash**: " in target_block
        assert index.read_bytes() == index_before
        assert "REQ-p00001" in captured.err
        assert "columns differ" in captured.err
        assert "a full `elspais fix` regenerates it" in captured.err

    # Verifies: REQ-d00330-C
    def test_dry_run_writes_nothing_and_names_the_index_row(self, solo_repo, capsys):
        from elspais.commands.fix_cmd import run

        before = _snapshot(solo_repo)
        assert run(_args(solo_repo, "REQ-p00001", dry_run=True)) == 0
        assert _snapshot(solo_repo) == before
        out = capsys.readouterr().out
        assert "Would fix REQ-p00001" in out
        assert "Would update the INDEX.md row for REQ-p00001" in out
        assert "REQ-p00002" not in out


class TestConfinedSave:
    """A save confined to named parts refuses work queued for any other part."""

    # Verifies: REQ-d00330-C
    def test_mutation_outside_the_named_parts_writes_nothing(self, solo_repo):
        from elspais.graph.factory import build_graph
        from elspais.graph.render import render_save

        before = _snapshot(solo_repo)
        graph = build_graph(config_path=solo_repo / ".elspais.toml", repo_root=solo_repo)
        target = graph.find_by_id("REQ-p00001")
        graph.update_title("REQ-p00002", "Renamed Neighbour")

        result = render_save(graph, repo_root=solo_repo, parts=[target])

        assert result["success"] is False
        assert any("REQ-p00002" in err for err in result["errors"])
        assert result["files_modified"] == []
        assert _snapshot(solo_repo) == before


_PRIMARY_CONFIG = """\
version = 5

[project]
name = "primary"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false

[associates.callisto]
path = "../callisto"
namespace = "CAL"
"""

_ASSOCIATE_CONFIG = """\
version = 5

[project]
name = "callisto"
namespace = "CAL"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
"""

_ASSOCIATE_SPEC = """\
# Callisto

## CAL-p00001: Library Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

### Assertions

A. The system SHALL process data.

*End* *Library Requirement* | **Hash**: 00000000
"""


class TestNamedAssociateFix:
    """A named requirement outside the write scope is refused, changing nothing."""

    # Verifies: REQ-d00330-C, REQ-d00253-B, REQ-d00253-F
    def test_associate_owned_target_is_refused(self, tmp_path, monkeypatch, capsys):
        from elspais.commands.fix_cmd import run

        primary = tmp_path / "primary"
        associate = tmp_path / "callisto"
        (primary / "spec").mkdir(parents=True)
        (associate / "spec").mkdir(parents=True)
        (primary / ".elspais.toml").write_text(_PRIMARY_CONFIG)
        (primary / "spec" / "core.md").write_text("# Core\n\n" + _TARGET)
        (associate / ".elspais.toml").write_text(_ASSOCIATE_CONFIG)
        (associate / "spec" / "lib.md").write_text(_ASSOCIATE_SPEC)
        monkeypatch.chdir(primary)

        rc = run(_args(primary, "CAL-p00001"))

        assert rc == 1
        err = capsys.readouterr().err
        assert "CAL-p00001" in err and "write_associates" in err
        assert (associate / "spec" / "lib.md").read_text() == _ASSOCIATE_SPEC
        assert (primary / "spec" / "core.md").read_text() == "# Core\n\n" + _TARGET
