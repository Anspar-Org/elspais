"""A fix run reports, and writes, exactly the changes it makes.

The dry run lists every file the run will rewrite, a run with nothing to
change writes nothing, a ``Satisfies:`` copy is fixed through its original,
and an associate inside the write scope keeps its own INDEX.md current.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pytest

_CONFIG = """\
version = 5

[project]
name = "{name}"
namespace = "{namespace}"

[scanning.spec]
directories = ["spec"]
skip_files = ["INDEX.md"]
skip_dirs = ["**/_generated"]

[changelog]
hash_current = false
{extra}"""

_LINK = """
[associates.callisto]
path = "../callisto"
namespace = "CAL"

[federation]
write_associates = true
"""


def _requirement(req_id: str, title: str, assertion: str, hash_value: str, meta: str = "") -> str:
    return (
        f"## {req_id}: {title}\n\n"
        f"**Level**: prd | **Status**: Active | **Implements**: -{meta}\n\n"
        f"### Assertions\n\nA. {assertion}\n\n"
        f"*End* *{title}* | **Hash**: {hash_value}\n"
    )


def _args(root: Path, *, dry_run: bool = False, req_id: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        req_id=req_id,
        dry_run=dry_run,
        spec_dir=None,
        config=root / ".elspais.toml",
        quiet=False,
        verbose=False,
        message=None,
        git_root=root,
    )


def _repo(root: Path, name: str, namespace: str, spec: str, extra: str = "") -> Path:
    (root / "spec").mkdir(parents=True)
    (root / ".elspais.toml").write_text(
        _CONFIG.format(name=name, namespace=namespace, extra=extra), encoding="utf-8"
    )
    (root / "spec" / "prd.md").write_text(spec, encoding="utf-8")
    return root


def _fix(root: Path, monkeypatch, capsys, **kwargs) -> tuple[int, str, str]:
    from elspais.commands.fix_cmd import run

    monkeypatch.chdir(root)
    rc = run(_args(root, **kwargs))
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _index_current(root: Path) -> bool:
    from elspais.commands.health import check_spec_index_current
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    config = get_config(root / ".elspais.toml", root)
    graph = build_graph(config_path=root / ".elspais.toml", repo_root=root)
    return check_spec_index_current(graph, [root / "spec"], config=config).passed


_TERMED = "# PRD\n\n" + _requirement(
    "REQ-p00001", "Widgets", "The system SHALL keep widgets.", "deadbeef"
).replace(
    "### Assertions", "### Definitions\n\nWidget\n: A thing that does stuff.\n\n### Assertions"
)


class TestDryRunListsEveryWrite:
    # Verifies: REQ-d00330-A
    def test_dry_run_names_the_index_the_run_rewrites(self, tmp_path, monkeypatch, capsys):
        root = _repo(tmp_path / "solo", "solo", "REQ", _TERMED)
        assert _fix(root, monkeypatch, capsys)[0] == 0
        spec = root / "spec" / "prd.md"
        spec.write_text(
            spec.read_text(encoding="utf-8").replace("keep widgets", "store widgets"),
            encoding="utf-8",
        )
        index_before = (root / "spec" / "INDEX.md").read_bytes()

        rc, out, _err = _fix(root, monkeypatch, capsys, dry_run=True)

        assert rc == 0
        assert "Would regenerate INDEX.md" in out
        assert (root / "spec" / "INDEX.md").read_bytes() == index_before
        rc, out, _err = _fix(root, monkeypatch, capsys)
        assert rc == 0
        assert (root / "spec" / "INDEX.md").read_bytes() != index_before


class TestSettledFixWritesNothing:
    # Verifies: REQ-d00248-A
    def test_second_fix_leaves_generated_files_alone(self, tmp_path, monkeypatch, capsys):
        root = _repo(tmp_path / "solo", "solo", "REQ", _TERMED)
        rc, out, _err = _fix(root, monkeypatch, capsys)
        assert rc == 0
        generated = sorted((root / "spec" / "_generated").rglob("*.md"))
        assert generated, out
        stamps = {p: p.stat().st_mtime_ns for p in generated}
        for path in generated:
            os.utime(path, ns=(1, 1))

        rc, out, _err = _fix(root, monkeypatch, capsys)
        assert rc == 0
        assert "Generated" not in out
        assert all(p.stat().st_mtime_ns == 1 for p in stamps)

        rc, out, _err = _fix(root, monkeypatch, capsys, dry_run=True)
        assert rc == 0
        assert "Would" not in out


class TestSatisfiesCopyFixedThroughOriginal:
    # Verifies: REQ-d00330-A, REQ-d00330-D
    def test_copy_is_not_reported_and_the_run_succeeds(self, tmp_path, monkeypatch, capsys):
        spec = (
            "# PRD\n\n"
            + _requirement(
                "REQ-p00002",
                "Template",
                "The system SHALL be templated.",
                "11111111",
                " | **Template**",
            )
            + "\n"
            + _requirement("REQ-p00003", "User", "The system SHALL use it.", "22222222").replace(
                "**Implements**: -", "**Implements**: -\n**Satisfies**: REQ-p00002"
            )
        )
        root = _repo(tmp_path / "solo", "solo", "REQ", spec)

        rc, planned, _err = _fix(root, monkeypatch, capsys, dry_run=True)
        assert rc == 0
        assert "::" not in planned
        assert "Would fix REQ-p00002" in planned

        rc, out, err = _fix(root, monkeypatch, capsys)
        assert rc == 0, err
        assert "Not fixed" not in out
        assert "::" not in out


@pytest.fixture()
def linked_writable(tmp_path: Path) -> dict[str, Path]:
    """A primary whose write scope reaches its associate, which keeps an INDEX.md."""
    primary = _repo(
        tmp_path / "primary",
        "primary",
        "REQ",
        "# PRD\n\n" + _requirement("REQ-p00001", "Core", "The system SHALL run.", "deadbeef"),
        extra=_LINK,
    )
    associate = _repo(
        tmp_path / "callisto",
        "callisto",
        "CAL",
        "# Lib\n\n" + _requirement("CAL-p00001", "Lib", "The system SHALL serve.", "00000000"),
    )
    return {"primary": primary, "associate": associate}


class TestAssociateIndexInWriteScope:
    # Verifies: REQ-d00330-B
    @pytest.mark.parametrize("named", [False, True], ids=["full-fix", "named-fix"])
    def test_associate_index_is_current_after_fix(
        self, linked_writable, monkeypatch, capsys, named
    ):
        primary = linked_writable["primary"]
        associate = linked_writable["associate"]
        # The associate settles itself, writing its own INDEX.md, then its
        # requirement changes so its recorded hash goes stale.
        assert _fix(associate, monkeypatch, capsys)[0] == 0
        lib = associate / "spec" / "prd.md"
        lib.write_text(
            lib.read_text(encoding="utf-8").replace("SHALL serve", "SHALL serve data"),
            encoding="utf-8",
        )
        stale = lib.read_text(encoding="utf-8")

        rc, out, err = _fix(primary, monkeypatch, capsys, req_id="CAL-p00001" if named else None)

        assert rc == 0, err
        # The fix rewrote the associate's hash, which its INDEX.md lists.
        assert lib.read_text(encoding="utf-8") != stale
        assert _index_current(associate), out + err
