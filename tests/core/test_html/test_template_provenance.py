# Verifies: REQ-p00014-K
"""HTML viewer affordance for cross-repo template provenance.

CUR-1353 Phase 9: when an INSTANCE clone of a foreign-repo template
shows up in the HTML viewer, the user must see:

1. Where the template is defined (``template_repo``).
2. The template original's ID, exposed as a navigable anchor/link.
3. For instance assertions: a note that coverage is inherited (instead
   of the bare "no direct coverage" hint that applies to concrete
   uncovered assertions).

The card UI is rendered client-side by JavaScript using the embedded
``node-index`` JSON. These tests therefore assert that the JSON
embedded in the generated HTML includes the new fields. The JS render
path (``buildCardHtml`` / ``buildAssertionHtml``) consumes them
unconditionally, so once the data is present the badge appears.
"""

from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

from elspais.graph.factory import build_graph
from elspais.html.generator import HTMLGenerator


def _write(repo: Path, rel: str, body: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(body).strip() + "\n")


def _git_init(repo: Path) -> None:
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


@pytest.fixture
def federation(tmp_path: Path):
    """Two-repo federation: library (template + covered code) + app (satisfier)."""
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


def _extract_node_index(html: str) -> dict:
    """Parse the embedded ``node-index`` JSON island from the rendered HTML."""
    m = re.search(
        r'<script[^>]*id="node-index"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert m is not None, "expected an embedded node-index <script> in rendered HTML"
    return json.loads(m.group(1))


class TestTemplateProvenanceInRenderedHTML:
    """The generated HTML's embedded JSON exposes template provenance fields."""

    def test_instance_req_node_has_template_repo_and_template_id(self, federation):
        """Cross-repo INSTANCE clone surfaces template_repo + template_id."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)

        clone_id = "APP-p00001::LIB-p00001"
        assert clone_id in nodes, f"expected clone {clone_id} in node-index; got {list(nodes)[:5]}"
        clone = nodes[clone_id]

        props = clone.get("properties") or {}
        assert (
            props.get("template_repo") == "library"
        ), f"expected template_repo='library' on INSTANCE clone, got {props.get('template_repo')!r}"
        assert (
            props.get("template_id") == "LIB-p00001"
        ), f"expected template_id='LIB-p00001' on INSTANCE clone, got {props.get('template_id')!r}"
        assert (
            props.get("stereotype") or ""
        ).lower() == "instance", f"expected stereotype='instance', got {props.get('stereotype')!r}"

    def test_template_repo_and_id_present_in_raw_html(self, federation):
        """User-visible content: 'library' repo name and 'LIB-p00001' anchor in the HTML."""
        html = HTMLGenerator(federation).generate(embed_content=True)

        # The template repo name must appear somewhere (embedded JSON).
        assert "library" in html, "expected template repo name 'library' in rendered HTML"
        # The template original's ID must appear too, navigable via JS click.
        assert "LIB-p00001" in html, "expected template ID 'LIB-p00001' in rendered HTML"

    def test_concrete_requirement_has_no_template_provenance_fields(self, federation):
        """Non-INSTANCE REQs MUST NOT carry template_repo/template_id (no regression)."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)

        # APP-p00001 is the concrete satisfier itself; LIB-p00001 is the template.
        # Neither is an INSTANCE, so neither should expose template provenance.
        for rid in ("APP-p00001", "LIB-p00001"):
            assert rid in nodes
            props = nodes[rid].get("properties") or {}
            got_repo = props.get("template_repo")
            got_id = props.get("template_id")
            assert (
                "template_repo" not in props
            ), f"concrete REQ {rid} should not carry template_repo, got {got_repo!r}"
            assert (
                "template_id" not in props
            ), f"concrete REQ {rid} should not carry template_id, got {got_id!r}"

    def test_instance_assertion_child_entry_has_inherited_coverage(self, federation):
        """Cloned-assertion children entries include inherited_coverage + template_id."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)

        clone_id = "APP-p00001::LIB-p00001"
        clone = nodes[clone_id]
        children = clone.get("children") or []
        assertion_entries = [c for c in children if c.get("kind") == "assertion"]
        assert assertion_entries, f"expected at least one cloned assertion child on {clone_id}"

        # Each INSTANCE-assertion child entry must surface inherited_coverage
        # plus template metadata so the JS can show "inherits from LIB-..."
        # instead of the generic "no direct coverage" hint.
        a = assertion_entries[0]
        assert "inherited_coverage" in a, f"expected inherited_coverage on cloned child, got {a!r}"
        assert (
            a.get("template_repo") == "library"
        ), f"expected child template_repo='library', got {a.get('template_repo')!r}"
        # Template assertion ID is reachable via the outbound INSTANCE edge.
        assert (a.get("template_id") or "").startswith(
            "LIB-p00001-"
        ), f"expected child template_id LIB-p00001-..., got {a.get('template_id')!r}"
        # The library CODE provides exactly one direct cover for LIB-p00001-A,
        # so the inherited count on the cloned A is 1.
        if a.get("label") == "A":
            assert a["inherited_coverage"] == 1, (
                f"expected inherited_coverage=1 (mirrors template's direct coverage), "
                f"got {a['inherited_coverage']!r}"
            )
