# Verifies: REQ-d00253-C
"""term-index generation uses primary terms only unless index_associates=True."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from elspais.commands.fix_cmd import _fix_terms, _select_terms_dictionary


def test_select_terms_federated_returns_merged(canonical_federated_graph):
    g = canonical_federated_graph
    federated = _select_terms_dictionary(g, include_associates=True)
    assert federated is g.terms


def test_select_terms_primary_only_returns_root_terms_with_federated_references(
    canonical_federated_graph,
):
    """False branch must offer the root repo's own terms, carrying scanned references.

    Which terms appear is the root repo's question: its own ``TraceGraph``
    dictionary records what that repo defines, and a term only an associate
    defines has no place in a primary-only index. What is KNOWN about each of
    those terms is the federation's question: the scan runs across every repo
    and establishes its findings on the federated dictionary's own entries, so
    that is where a term's references live. A primary-only index therefore
    reads the term list from one and each entry from the other.

    Assertions:
      1. primary is NOT the merged federated dict     -- fails if False branch returns g.terms
      2. primary's terms are exactly the root's terms -- fails if an associate-only term
         leaks in, or a root-defined term is dropped
      3. each entry carries the references the federated scan established -- fails if the
         index is built from a dictionary no scan ever wrote to
    """
    g = canonical_federated_graph
    primary = _select_terms_dictionary(g, include_associates=False)
    federated = _select_terms_dictionary(g, include_associates=True)

    # Locate the root repo's TraceGraph.
    root_entry = next(e for e in g.iter_repos() if e.name == g.root_repo_name)
    root_terms = root_entry.graph.terms  # stable object: TraceGraph._terms

    # 1. Must NOT be the merged dict (would fail if False branch returns g.terms).
    assert primary is not g.terms, (
        "_select_terms_dictionary(False) must offer the root repo's own terms, "
        "not the federated merged TermDictionary"
    )

    # 2. Exactly the terms the root repo defines -- no associate-only term.
    primary_names = {e.term for e in primary.iter_all()}
    root_names = {e.term for e in root_terms.iter_all()}
    assert primary_names == root_names

    associate_only = {
        e.term
        for entry in g.iter_repos()
        if entry.name != g.root_repo_name and entry.graph is not None
        for e in entry.graph.terms.iter_all()
    } - root_names
    assert primary_names.isdisjoint(associate_only), (
        f"primary-only index carries terms only an associate defines: "
        f"{sorted(primary_names & associate_only)}"
    )

    # 3. Each entry carries what the federated scan found for it. The root's
    #    own dictionary records definitions and is never scanned into, so an
    #    index built from it alone would list every term with no reference.
    for name in primary_names:
        assert len(primary.lookup(name).references) == len(federated.lookup(name).references)
    assert any(primary.lookup(name).references for name in primary_names), (
        "no term in the primary-only index carries a reference; the scan's "
        "findings did not reach the entries the index renders"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Transitive federation members and the primary-only term index
#
# Federation membership is transitive, so a repository reached through an
# associate's own [associates] table is a member the root's table never names.
# Its term references must be dropped from a primary-only term index just as a
# directly declared associate's are, or the artifact claims to be primary-only
# while carrying a foreign namespace section.
# ─────────────────────────────────────────────────────────────────────────────

_MIN_TOML = """version = 5

[project]
name = "{name}"
namespace = "{namespace}"

[levels.prd]
rank = 1
implements = []

[levels.dev]
rank = 2
implements = ["prd", "dev"]
"""

_SPEC = """# Spec for {name}

{definition}## {req_id}: A requirement in {name}

**Status**: active

The system shall provide a *widget*.

*End*
"""

_DEFINITION = """Widget
: A small self-contained part.

"""


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["HOME"] = env.get("HOME", "/tmp")
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, env=_git_env(), capture_output=True, check=True)


def _make_repo(
    base: Path,
    name: str,
    namespace: str,
    req_id: str,
    *,
    defines_term: bool = False,
    associates: dict[str, tuple[str, str]] | None = None,
) -> Path:
    """Create a minimal git-backed elspais repo defining or referencing a term."""
    repo = base / name
    (repo / "spec").mkdir(parents=True)
    text = _MIN_TOML.format(name=name, namespace=namespace)
    for assoc_name, (assoc_path, assoc_ns) in (associates or {}).items():
        text += f'\n[associates.{assoc_name}]\npath = "{assoc_path}"\nnamespace = "{assoc_ns}"\n'
    (repo / ".elspais.toml").write_text(text, encoding="utf-8")
    (repo / "spec" / "reqs.md").write_text(
        _SPEC.format(
            name=name,
            req_id=req_id,
            definition=_DEFINITION if defines_term else "",
        ),
        encoding="utf-8",
    )
    _git(base, "init", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


# Verifies: REQ-d00253-C, REQ-d00202-D
def test_primary_term_index_drops_transitive_member_namespace(tmp_path, monkeypatch):
    """A transitively federated repo's references stay out of the primary index.

    root -> mid -> leaf, each repo referencing a term the root defines. With
    ``federation.index_associates`` left false, the generated term index must
    list the root's own namespace and neither member's.
    """
    _make_repo(tmp_path, "leaf", "LEAF", "LEAF-d00001")
    _make_repo(tmp_path, "mid", "MID", "MID-d00001", associates={"leaf": ("../leaf", "LEAF")})
    root = _make_repo(
        tmp_path,
        "root",
        "REQ",
        "REQ-d00001",
        defines_term=True,
        associates={"mid": ("../mid", "MID")},
    )

    monkeypatch.chdir(root)
    _fix_terms(argparse.Namespace(config=None, spec_dir=None, git_root=root), dry_run=False)

    index = (root / "spec" / "_generated" / "term-index.md").read_text(encoding="utf-8")

    assert "**REQ:**" in index, "the root repo's own references belong in its term index"
    assert "**MID:**" not in index, "a directly declared associate's namespace must be dropped"
    assert "**LEAF:**" not in index, "a transitively federated repo's namespace must be dropped"
    assert "LEAF-d00001" not in index
