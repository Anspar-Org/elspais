# Verifies: REQ-p00014-K
"""Instance assertion coverage inherits from the template original.

These tests pin the CUR-1353 Phase 5 contract:

- ``direct_coverage_for(node)`` counts coverage evidence on a node,
  dispatched by ``NodeKind``: ASSERTIONs walk the parent REQ's outgoing
  IMPLEMENTS/VERIFIES/VALIDATES edges (filtered by ``assertion_targets``);
  REQUIREMENTs count outgoing coverage edges; CODE/TEST/FILE/JOURNEY count
  incoming coverage edges. All filtered by
  :meth:`EdgeKind.contributes_to_coverage`.
- ``inherited_coverage_for(instance_assertion)`` follows the outbound
  INSTANCE edge to the template original and returns its direct count.
- ``satisfier_rollup(satisfier_req)`` combines the satisfier's own
  concrete-assertion coverage with the inherited template coverage.

The fixture builds a two-repo federation: a library that defines a
``**Template**`` REQ with one assertion and has a CODE file targeting
that assertion, plus an app whose REQ ``Satisfies`` the library template
and adds its own concrete assertion with NO covering CODE. The expected
rollup is therefore partial: template covered, own assertion uncovered.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


def _write(repo: Path, rel: str, body: str) -> None:
    """Write ``body`` (dedented, stripped, newline-terminated) to ``repo/rel``."""
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(body).strip() + "\n")


def _git_init(repo: Path) -> None:
    """Initialise a git repo at ``repo``."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=x@y",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "init",
        ],
        cwd=repo,
        check=True,
    )


def _build(tmp_path: Path):
    """Library + app federation; library CODE implements template assertion."""
    from elspais.graph.factory import build_graph

    library = tmp_path / "library"
    app = tmp_path / "app"
    library.mkdir()
    app.mkdir()

    _write(
        library,
        ".elspais.toml",
        """
        version = 3
        [project]
        name = "library"
        namespace = "LIB"
        [levels.prd]
        rank = 1
        letter = "p"
        implements = ["prd"]
        [scanning.spec]
        directories = ["spec"]
        [scanning.code]
        directories = ["src"]
        [scanning.test]
        enabled = false
        directories = []
        """,
    )
    _write(
        library,
        "spec/prd-library.md",
        """
        # LIB-p00001: Action Dispatch

        **Level**: PRD | **Status**: Approved | **Template**

        ### Assertions

        A. SHALL parse.

        *End* *Action Dispatch*
        """,
    )
    _write(
        library,
        "src/lib.py",
        """
        # Implements: LIB-p00001-A
        def parse(p):
            return p
        """,
    )
    _git_init(library)

    _write(
        app,
        ".elspais.toml",
        """
        version = 3
        [project]
        name = "app"
        namespace = "APP"
        [levels.prd]
        rank = 1
        letter = "p"
        implements = ["prd"]
        [scanning.spec]
        directories = ["spec"]
        [scanning.code]
        directories = []
        [scanning.test]
        enabled = false
        directories = []
        [associates.library]
        path = "../library"
        namespace = "LIB"
        """,
    )
    _write(
        app,
        "spec/prd-app.md",
        """
        # APP-p00001: Concrete Action

        **Level**: PRD | **Status**: Approved
        **Satisfies**: LIB-p00001

        ### Assertions

        A. SHALL be admin-only.

        *End* *Concrete Action*
        """,
    )
    _git_init(app)

    return build_graph(repo_root=app, scan_code=True, scan_tests=False)


def test_instance_assertion_inherits_template_coverage(tmp_path: Path) -> None:
    """An INSTANCE assertion's inherited coverage equals the template's direct coverage."""
    from elspais.graph.metrics import direct_coverage_for, inherited_coverage_for

    fed = _build(tmp_path)
    instance = fed.find_by_id("APP-p00001::LIB-p00001-A")
    template = fed.find_by_id("LIB-p00001-A")
    assert instance is not None, "expected cloned instance assertion to exist"
    assert template is not None, "expected library template assertion to exist"

    # The library CODE file has exactly one `# Implements: LIB-p00001-A`,
    # so the template original has exactly one direct-coverage edge.
    assert direct_coverage_for(template) == 1, "template assertion should have direct coverage"

    # The instance has NO direct inbound IMPLEMENTS/VERIFIES (CODE doesn't
    # use composite IDs); inherited coverage walks the INSTANCE edge.
    assert direct_coverage_for(instance) == 0
    assert inherited_coverage_for(instance) == direct_coverage_for(template)


def test_satisfier_rollup_combines_own_and_inherited(tmp_path: Path) -> None:
    """One covered template-assertion + one uncovered own assertion is partial."""
    from elspais.graph.metrics import satisfier_rollup

    fed = _build(tmp_path)
    satisfier = fed.find_by_id("APP-p00001")
    assert satisfier is not None

    # APP-p00001's own concrete assertion A is uncovered (no CODE in app/).
    # The template LIB-p00001 IS covered by library/src/lib.py.
    # Rollup should report partial: covered=1, total=2.
    rollup = satisfier_rollup(satisfier)
    assert rollup.total == 2, f"expected own+template = 2 assertions, got total={rollup.total}"
    assert (
        rollup.covered == 1
    ), f"expected exactly the template covered, got covered={rollup.covered}"
    assert (
        0 < rollup.covered_fraction < 1.0
    ), f"expected partial fraction, got {rollup.covered_fraction!r}"
