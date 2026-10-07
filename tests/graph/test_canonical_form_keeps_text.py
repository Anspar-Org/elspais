"""Bringing a requirement into canonical form keeps every heading and visible line.

A definition list inside a requirement is held as its own part. A section
whose text is only a definition list, and text written after one, must
still render where they were written: the heading kept, and the text kept
below the list rather than moved above it.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
from pathlib import Path

import pytest

PROJECT_TOML = """version = 5

[project]
name = "canon"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
skip_files = ["INDEX.md"]

[changelog]
hash_current = false
"""


def _requirement(req_id: str, title: str, body: str) -> str:
    """A requirement in canonical form whose recorded hash matches its assertion."""
    from elspais.utilities.hasher import compute_normalized_hash

    assertion = f"The tool SHALL {title.lower()}."
    digest = compute_normalized_hash([("A", assertion)])
    return (
        f"## {req_id}: {title}\n\n**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"{body}### Assertions\n\nA. {assertion}\n\n"
        f"*End* *{title}* | **Hash**: {digest}\n"
    )


def _with_tail(req_id: str, title: str, tail: str) -> str:
    """A requirement whose sections follow its assertions."""
    text = _requirement(req_id, title, f"{title} body.\n\n")
    end = text.index("*End*")
    return text[:end] + tail + text[end:]


def _canonical() -> str:
    """A spec file in canonical form holding each construct around a definition list."""
    definitions_only = _with_tail(
        "REQ-d00001",
        "Defines",
        "### Rationale\n\nWhy it is so.\n\n"
        "### Definitions\n\nWidget\n: A thing that does stuff.\n\n",
    )
    text_after_definitions = _with_tail(
        "REQ-d00002",
        "Continues",
        "### Rationale\n\nBefore the list.\n\nGadget\n: Another thing.\n\nAfter the list.\n\n",
    )
    preamble_definitions = _requirement(
        "REQ-d00003",
        "Opens",
        "Opening text.\n\nSprocket\n: A toothed wheel.\n\nClosing text.\n\n",
    )
    empty_section = _with_tail("REQ-d00004", "Headed", "### Notes\n\n### Rationale\n\nReasons.\n\n")
    return "# Dev\n\n" + "\n".join(
        [definitions_only, text_after_definitions, preamble_definitions, empty_section]
    )


def _project(root: Path, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".elspais.toml").write_text(PROJECT_TOML, encoding="utf-8")
    (root / "spec").mkdir()
    (root / "spec" / "dev.md").write_text(text, encoding="utf-8")
    return root


def _run_fix(root: Path) -> int:
    from elspais.commands.fix_cmd import run

    args = argparse.Namespace(
        req_id=None,
        dry_run=False,
        spec_dir=root / "spec",
        config=root / ".elspais.toml",
        verbose=False,
        quiet=False,
        message=None,
    )
    old_cwd = os.getcwd()
    os.chdir(root)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return run(args)
    finally:
        os.chdir(old_cwd)


def _visible_lines(text: str) -> list[str]:
    """The non-blank lines, without the heading markers whose depth canonical form sets."""
    return [line.lstrip("#").strip() for line in text.splitlines() if line.strip()]


# Verifies: REQ-d00132-O, REQ-d00132-P
def test_canonical_text_renders_byte_identical(tmp_path: Path):
    from elspais.graph import NodeKind
    from elspais.graph.factory import build_graph
    from elspais.graph.render import render_file

    root = _project(tmp_path / "project", _canonical())

    graph = build_graph(repo_root=root)
    (file_node,) = [
        n
        for n in graph.nodes_by_kind(NodeKind.FILE)
        if n.get_field("relative_path") == "spec/dev.md"
    ]
    assert render_file(file_node) == _canonical()
    dirty = [n.id for n in graph.nodes_by_kind(NodeKind.REQUIREMENT) if n.get_field("parse_dirty")]
    assert dirty == []


# Verifies: REQ-d00132-O, REQ-d00132-P
@pytest.mark.parametrize(
    "spacing",
    [
        pytest.param(lambda t: t.replace("### ", "## "), id="shallow-headings"),
        pytest.param(lambda t: t.replace(".\n\n", ".\n\n\n"), id="extra-blank-lines"),
        pytest.param(
            lambda t: t.replace(
                "**Level**: dev | **Status**: Active | **Implements**: -",
                "**Status**: Active | **Level**: dev",
            ),
            id="metadata-respelled",
        ),
    ],
)
def test_fix_keeps_headings_and_text_order(tmp_path: Path, spacing):
    root = _project(tmp_path / "project", spacing(_canonical()))

    assert _run_fix(root) == 0
    fixed = (root / "spec" / "dev.md").read_text(encoding="utf-8")

    # Every heading, definition and line of text survives, in written order;
    # only spacing, heading depth and the metadata block's spelling differ
    # from the canonical text.
    assert _visible_lines(fixed) == _visible_lines(_canonical())
    assert fixed == _canonical()

    # A second fix finds nothing to change.
    assert _run_fix(root) == 0
    assert (root / "spec" / "dev.md").read_text(encoding="utf-8") == fixed
