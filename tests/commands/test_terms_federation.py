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


def test_select_terms_primary_only_returns_root_not_merged(canonical_federated_graph):
    """False branch must return the root repo's own TraceGraph._terms, not the merged dict.

    Identity semantics (both properties return a stable cached object):
      - FederatedGraph.terms   -> self._terms  (merged TermDictionary, a distinct object)
      - TraceGraph.terms       -> self._terms  (the per-repo TermDictionary)
      - FederatedGraph._merge_terms() always constructs a NEW TermDictionary, so
        g.terms is never the same object as any single repo's entry.graph._terms.

    Assertions:
      1. primary is NOT the merged federated dict     -- fails if False branch returns g.terms
      2. primary IS the root repo's own TraceGraph._terms -- fails if False branch returns
         anything other than the root repo's terms
      3. len(primary) <= len(federated)               -- sanity: subset relationship
    """
    g = canonical_federated_graph
    primary = _select_terms_dictionary(g, include_associates=False)
    federated = _select_terms_dictionary(g, include_associates=True)

    # Locate the root repo's TraceGraph.
    root_entry = next(e for e in g.iter_repos() if e.name == g.root_repo_name)
    root_terms = root_entry.graph.terms  # stable object: TraceGraph._terms

    # 1. Must NOT be the merged dict (would fail if False branch returns g.terms).
    assert primary is not g.terms, (
        "_select_terms_dictionary(False) must return the root repo's own terms, "
        "not the federated merged TermDictionary"
    )

    # 2. Must be exactly the root repo's own stable _terms object.
    assert primary is root_terms, (
        "_select_terms_dictionary(False) must return root_entry.graph.terms "
        f"(id={id(root_terms):#x}), got id={id(primary):#x}"
    )

    # 3. Sanity: primary is a subset of the federated merged dict.
    assert len(primary) <= len(federated)


# ─────────────────────────────────────────────────────────────────────────────
# Transitive federation members and the primary-only term index
#
# Federation membership is transitive, so a repository reached through an
# associate's own [associates] table is a member the root's table never names.
# Its term references must be dropped from a primary-only term index just as a
# directly declared associate's are, or the artifact claims to be primary-only
# while carrying a foreign namespace section.
# ─────────────────────────────────────────────────────────────────────────────

_MIN_TOML = """version = 3

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
