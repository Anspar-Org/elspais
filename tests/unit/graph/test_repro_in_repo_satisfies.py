"""Regression guard for the in-repo Satisfies wiring.

Originally written to investigate a report from a downstream consumer
(cure-hht) claiming elspais 0.115.29 'broke within-repo Satisfies wiring
(the field parses but the edge isn't constructed and no INSTANCE clones
are created)'. Investigation conclusion: NOT a regression — the downstream
specs lacked **Template** markers, and Phase 2 (intentionally) rejects
Satisfies: against unmarked targets. These tests lock in the contract:

  A. Target marked **Template** + canonical **Satisfies**: -> clones land.
  B. Target NOT marked **Template** -> typed broken-ref diagnostic.
  C. Bare Satisfies: form (parser tolerance) -> same as A.
"""

import subprocess
import tempfile
import textwrap
from pathlib import Path


def _build_repro(spec_body: str) -> Path:
    repo = Path(tempfile.mkdtemp(prefix="in_repo_satisfies_"))
    (repo / ".elspais.toml").write_text(
        textwrap.dedent(
            """
        version = 3
        [project]
        name = "repro"
        namespace = "URS"
        [levels.prd]
        rank = 1
        letter = "p"
        implements = ["prd"]
        [scanning.spec]
        directories = ["spec"]
    """
        ).strip()
    )
    (repo / "spec").mkdir()
    (repo / "spec/spec.md").write_text(textwrap.dedent(spec_body).strip())
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=x@y", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=repo,
        check=True,
    )
    return repo


# Verifies: REQ-p00014-B
def test_in_repo_satisfies_marked_template_produces_clones():
    """Scenario A: target marked **Template** + bold **Satisfies** form."""
    repo = _build_repro(
        """
        # URS-p00001: Per-Env Template

        **Level**: PRD | **Status**: Approved | **Template**

        ## Assertions

        A. The env SHALL define a backend URL.

        # URS-p00002: Dev Env

        **Level**: PRD | **Status**: Approved
        **Satisfies**: URS-p00001

        ## Assertions

        A. Dev env SHALL allow localhost.
    """
    )
    try:
        from elspais.graph.factory import build_graph

        graph = build_graph(repo_root=repo)
        assert (
            graph.find_by_id("URS-p00002::URS-p00001") is not None
        ), "in-repo INSTANCE clone (root) missing"
        assert (
            graph.find_by_id("URS-p00002::URS-p00001-A") is not None
        ), "in-repo INSTANCE clone (assertion) missing"
    finally:
        import shutil

        shutil.rmtree(repo)


# Verifies: REQ-p00014-G
def test_in_repo_satisfies_unmarked_target_emits_broken_ref():
    """Scenario B: target NOT marked **Template** — Phase 2 emits typed diagnostic."""
    repo = _build_repro(
        """
        # URS-p00001: Per-Env (NOT marked Template)

        **Level**: PRD | **Status**: Approved

        ## Assertions

        A. The env SHALL define a backend URL.

        # URS-p00002: Dev Env

        **Level**: PRD | **Status**: Approved
        **Satisfies**: URS-p00001

        ## Assertions

        A. Dev env SHALL allow localhost.
    """
    )
    try:
        from elspais.graph.factory import build_graph

        graph = build_graph(repo_root=repo)
        assert (
            graph.find_by_id("URS-p00002::URS-p00001") is None
        ), "Unexpected: clone created against unmarked target"
        brs = list(graph.broken_references())
        marker_diag = [br for br in brs if "not marked **Template**" in (br.diagnostic or "")]
        assert marker_diag, (
            f"Expected diagnostic naming **Template**; " f"got: {[br.diagnostic for br in brs]}"
        )
    finally:
        import shutil

        shutil.rmtree(repo)


# Verifies: REQ-p00014-A
# (A, not E: p00014-E's "markdown decoration optional" covers the **Template**
# flag; the bare-vs-bold Satisfies: form is the field-support contract in A.)
def test_in_repo_satisfies_bare_form_also_works():
    """Scenario C: parser tolerates bare Satisfies: form (without bold)."""
    repo = _build_repro(
        """
        # URS-p00001: Per-Env Template

        **Level**: PRD | **Status**: Approved | **Template**

        ## Assertions

        A. The env SHALL define a backend URL.

        # URS-p00002: Dev Env

        **Level**: PRD | **Status**: Approved
        Satisfies: URS-p00001

        ## Assertions

        A. Dev env SHALL allow localhost.
    """
    )
    try:
        from elspais.graph.factory import build_graph

        graph = build_graph(repo_root=repo)
        assert (
            graph.find_by_id("URS-p00002::URS-p00001") is not None
        ), "bare Satisfies: form should produce INSTANCE clone"
        assert (
            graph.find_by_id("URS-p00002::URS-p00001-A") is not None
        ), "bare Satisfies: form should produce INSTANCE assertion"
    finally:
        import shutil

        shutil.rmtree(repo)
