"""A reference list naming one target twice is refused wherever the target lives.

A list is judged for a repeated target as it is read, so the judgement can
only reach a target the reader can read. These tests build a real two-member
federation (``core`` owns ``REQ-p00001``; ``alpha`` declares namespace
``REQ-ALP`` and cites core's identifiers) and repeat a target in each place a
reference list is written: spec metadata, a journey's ``Validates:`` line and a
code annotation, in the member that owns the target and in one that does not.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from elspais.graph.factory import build_graph
from elspais.graph.reference_faults import FaultClass, FaultCode
from elspais.graph.relations import EdgeKind

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "e2e-associated"

_TARGET = "REQ-p00001"

_JOURNEY = """## JNY-o-01: A Journey

**Actor**: User
**Goal**: Do a thing
Validates: {validates}

### Steps

1. Do the thing

*End* *JNY-o-01*
"""

_CODE = "# Implements: {implements}\ndef f():\n    pass\n"


def _federation(tmp_path: Path) -> Path:
    """Copy the associated fixture into ``tmp_path`` and return core's root."""
    root = tmp_path / "fed"
    shutil.copytree(_FIXTURE, root)
    for member in ("core", "alpha", "beta"):
        subprocess.run(["git", "init", "-q", str(root / member)], check=True)
    return root


def _cite_in_spec(path: Path, citing_req: str, refs: str) -> None:
    """Replace the **Implements**: list of ``citing_req`` in ``path``."""
    lines = path.read_text().splitlines(keepends=True)
    header = next(i for i, line in enumerate(lines) if line.startswith(f"# {citing_req}:"))
    meta = next(i for i in range(header, len(lines)) if "**Implements**:" in lines[i])
    head, _sep, _old = lines[meta].partition("**Implements**: ")
    lines[meta] = f"{head}**Implements**: {refs}\n"
    path.write_text("".join(lines))


def _alpha_spec(root: Path, refs: str) -> str:
    _cite_in_spec(root / "alpha" / "spec" / "dev-alpha.md", "REQ-ALP-d00001", refs)
    return "REQ-ALP-d00001"


def _core_spec(root: Path, refs: str) -> str:
    _cite_in_spec(root / "core" / "spec" / "dev-core.md", "REQ-d00001", refs)
    return "REQ-d00001"


def _alpha_journey(root: Path, refs: str) -> str:
    (root / "alpha" / "spec" / "journeys.md").write_text(_JOURNEY.format(validates=refs))
    return "JNY-o-01"


def _alpha_code(root: Path, refs: str) -> str:
    alpha = root / "alpha"
    config = alpha / ".elspais.toml"
    config.write_text(config.read_text() + '\n[scanning.code]\ndirectories = ["src"]\n')
    (alpha / "src").mkdir()
    (alpha / "src" / "impl.py").write_text(_CODE.format(implements=refs))
    return "code:"


_PLACES = {
    "spec-implements-in-another-member": (_alpha_spec, EdgeKind.IMPLEMENTS),
    "journey-validates-in-another-member": (_alpha_journey, EdgeKind.VALIDATES),
    "spec-implements-in-the-owning-member": (_core_spec, EdgeKind.IMPLEMENTS),
    "code-implements-in-another-member": (_alpha_code, EdgeKind.IMPLEMENTS),
}


def _is_citing(node_id: str, citing: str) -> bool:
    """The code node id carries an absolute path, so it is matched by prefix."""
    return node_id.startswith(citing) if citing == "code:" else node_id == citing


# Verifies: REQ-d00272-K, REQ-d00287-F
@pytest.mark.parametrize("place", list(_PLACES), ids=list(_PLACES))
def test_every_instance_of_a_repeated_target_is_reported_and_none_binds(tmp_path, place):
    """Two instances of one target produce two reports and no relationship,
    whichever member owns the target and whichever list names it twice."""
    write, edge_kind = _PLACES[place]
    root = _federation(tmp_path)
    citing = write(root, f"{_TARGET}, {_TARGET}")

    graph = build_graph(repo_root=root / "core")

    faults = [
        f
        for f in graph.unresolved_references()
        if _is_citing(f.source_id, citing) and f.target_id == _TARGET
    ]
    assert len(faults) == 2, f"one report per repeated instance; got {faults}"
    assert all(f.fault_class is FaultClass.FORBIDDEN for f in faults)
    assert all(FaultCode.DUPLICATE_ITEM in f.codes for f in faults)
    assert all(f.edge_kind == edge_kind.value for f in faults)

    target = graph.find_by_id(_TARGET)
    assert target is not None
    bound = [
        e
        for e in target.iter_outgoing_edges()
        if e.kind is edge_kind and _is_citing(e.target.id, citing)
    ]
    assert bound == [], f"a repeated target must produce no relationship; got {bound}"


_SINGLE_PLACES = {
    "spec-implements-in-another-member": (_alpha_spec, EdgeKind.IMPLEMENTS),
    "journey-validates-in-another-member": (_alpha_journey, EdgeKind.VALIDATES),
}


# Verifies: REQ-d00272-K, REQ-d00287-F
@pytest.mark.parametrize("place", list(_SINGLE_PLACES), ids=list(_SINGLE_PLACES))
def test_a_cross_repository_target_named_once_binds_once(tmp_path, place):
    """Reading another member's identifiers must not turn a clean reference
    into a fault: a target named once still produces exactly one relationship."""
    write, edge_kind = _SINGLE_PLACES[place]
    root = _federation(tmp_path)
    citing = write(root, _TARGET)

    graph = build_graph(repo_root=root / "core")

    assert [f for f in graph.unresolved_references() if f.source_id == citing] == []
    target = graph.find_by_id(_TARGET)
    assert target is not None
    bound = [
        e for e in target.iter_outgoing_edges() if e.kind is edge_kind and e.target.id == citing
    ]
    assert len(bound) == 1, f"expected one relationship; got {bound}"
