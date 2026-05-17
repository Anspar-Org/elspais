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


# ─── CUR-1353 Phase 11: uniform template_repo + satisfier rollup ─────────────


def _build_in_repo_satisfies(tmp_path: Path) -> tuple[Path, object]:
    """Build a single-repo fixture with an in-repo Satisfies declaration."""
    repo = tmp_path / "solo"
    repo.mkdir()
    _write(
        repo,
        ".elspais.toml",
        """
        version = 3
        [project]
        name = "solo-repo"
        namespace = "URS"
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
        """,
    )
    _write(
        repo,
        "spec/spec.md",
        """
        # URS-p00001: Cross-Cutting Template

        **Level**: PRD | **Status**: Approved | **Template**

        ### Assertions

        A. SHALL validate.

        *End* *Cross-Cutting Template*

        # URS-p00002: Concrete Satisfier

        **Level**: PRD | **Status**: Approved
        **Satisfies**: URS-p00001

        ### Assertions

        A. SHALL be admin-only.

        *End* *Concrete Satisfier*
        """,
    )
    _git_init(repo)
    return repo, build_graph(repo_root=repo, scan_code=False, scan_tests=False)


class TestPhase11InRepoTemplateRepo:
    """In-repo INSTANCE clones carry template_repo set to the local project name."""

    def test_in_repo_instance_clone_has_template_repo_field(self, tmp_path):
        """Phase 11: in-repo clones tag template_repo with [project].name."""
        _repo, graph = _build_in_repo_satisfies(tmp_path)

        # Locate the cloned root via the local TraceGraph (single repo).
        clone_id = "URS-p00002::URS-p00001"
        clone = graph.find_by_id(clone_id)
        assert clone is not None, f"expected in-repo INSTANCE clone {clone_id}"

        got = clone.get_field("template_repo")
        assert got == "solo-repo", (
            f"expected in-repo clone template_repo='solo-repo' "
            f"(matches [project].name), got {got!r}"
        )

        # Cloned assertion should also carry the field (the cloner copies
        # all content fields then sets stereotype, plus the new template_repo).
        clone_a = graph.find_by_id("URS-p00002::URS-p00001-A")
        assert clone_a is not None, "expected cloned assertion URS-p00002::URS-p00001-A"
        assert clone_a.get_field("template_repo") == "solo-repo", (
            f"expected cloned-assertion template_repo='solo-repo', "
            f"got {clone_a.get_field('template_repo')!r}"
        )


class TestPhase11SatisfierRollupSerialized:
    """satisfier_rollup data appears in the per-node JSON for satisfier REQs."""

    def test_satisfier_req_json_has_rollup(self, federation):
        """The app's satisfier REQ exposes a satisfier_rollup property."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)

        sat_id = "APP-p00001"
        assert sat_id in nodes, f"expected satisfier REQ {sat_id} in node-index"
        props = nodes[sat_id].get("properties") or {}

        assert "satisfier_rollup" in props, (
            f"expected satisfier_rollup on satisfier REQ {sat_id}, "
            f"got props keys: {sorted(props)}"
        )
        sr = props["satisfier_rollup"]
        # Fixture: APP-p00001 has 1 own assertion (A, uncovered) and
        # SATISFIES LIB-p00001 (1 template assertion, covered by lib.py).
        # So rollup = covered=1 / total=2.
        assert sr["total"] == 2, f"expected total=2 (1 own + 1 inherited), got {sr['total']}"
        assert (
            sr["covered"] == 1
        ), f"expected covered=1 (template assertion only), got {sr['covered']}"
        assert (
            0.0 < sr["covered_fraction"] < 1.0
        ), f"expected partial covered_fraction in (0,1), got {sr['covered_fraction']}"

    def test_non_satisfier_req_has_no_rollup(self, federation):
        """REQs without outbound SATISFIES edges must not carry the field."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)

        # LIB-p00001 is the template (no SATISFIES out), so no rollup.
        props = nodes["LIB-p00001"].get("properties") or {}
        assert "satisfier_rollup" not in props, (
            f"expected no satisfier_rollup on non-satisfier REQ LIB-p00001, "
            f"got {props.get('satisfier_rollup')!r}"
        )


class TestPhase11SatisfierRollupRendered:
    """Rendered HTML for a satisfier REQ surfaces the combined-coverage row."""

    def test_combined_coverage_string_appears_in_rendered_html(self, federation):
        """The literal 'Combined coverage' label is wired into the card template."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        # The JS partial contains the literal label; it must be present in
        # the inlined script bundle the generator emits.
        assert "Combined coverage:" in html, (
            "expected 'Combined coverage:' label in rendered HTML "
            "(satisfier rollup card row not wired in)"
        )
        # The rollup-class hook used by the card row must be present too.
        assert "satisfier-rollup" in html, "expected 'satisfier-rollup' CSS class in rendered HTML"

    def test_satisfier_rollup_lands_in_html_node_index(self, federation):
        """End-to-end: build the library+app federation, generate HTML, parse
        the embedded node-index JSON, find APP-p00001 (the satisfier REQ), and
        assert its satisfier_rollup field has the expected numerics.

        This is a stronger sibling to ``test_combined_coverage_string_appears_in_rendered_html``:
        that test only proves the JS template literal exists (it's compiled in
        regardless of fixture content). This test proves the data path
        end-to-end:

            builder -> metrics.satisfier_rollup
                    -> mcp.server._serialize_node_generic
                    -> html.generator._build_node_index
                    -> <script id="node-index"> in trace_unified.html.j2

        It combines positive (rollup present + correctly shaped + correct
        numerics) and negative (counter-check on the template) into a single
        end-to-end assertion so a regression anywhere on that path fails here.
        """
        html = HTMLGenerator(federation).generate(embed_content=True)
        node_index = _extract_node_index(html)

        # --- Positive: satisfier REQ carries a well-shaped rollup ---------
        sat_id = "APP-p00001"
        assert sat_id in node_index, (
            f"{sat_id} missing from node-index; available (first 10): " f"{sorted(node_index)[:10]}"
        )
        props = node_index[sat_id].get("properties") or {}
        rollup = props.get("satisfier_rollup")
        assert rollup is not None, (
            f"{sat_id} is a satisfier REQ but its node-index entry has no "
            f"satisfier_rollup in properties; properties keys: {sorted(props)}"
        )
        assert isinstance(rollup, dict), (
            f"expected satisfier_rollup to be a dict (covered/total/covered_fraction), "
            f"got {type(rollup).__name__}"
        )
        assert set(rollup.keys()) >= {"covered", "total", "covered_fraction"}, (
            f"satisfier_rollup missing required keys; "
            f"expected at minimum {{covered, total, covered_fraction}}, "
            f"got {sorted(rollup.keys())}"
        )

        # Fixture-specific numerics (locks in real data-path output):
        # APP-p00001 has 1 own concrete assertion A (uncovered: no code in
        # the app repo) and Satisfies LIB-p00001 which has 1 assertion A
        # covered by library/src/lib.py. So combined coverage is 1 / 2.
        assert rollup["total"] == 2, (
            f"expected total=2 (1 own concrete + 1 inherited template), "
            f"got {rollup['total']} (rollup={rollup})"
        )
        assert rollup["covered"] == 1, (
            f"expected covered=1 (only the template assertion is covered), "
            f"got {rollup['covered']} (rollup={rollup})"
        )
        assert 0.0 < rollup["covered_fraction"] < 1.0, (
            f"expected partial covered_fraction in (0, 1) for 1-of-2 coverage, "
            f"got {rollup['covered_fraction']!r}"
        )
        # 1/2 specifically, with float tolerance.
        assert (
            abs(rollup["covered_fraction"] - 0.5) < 1e-9
        ), f"expected covered_fraction ~= 0.5 (1 of 2), got {rollup['covered_fraction']!r}"

        # --- Counter-check: non-satisfier REQs do NOT carry the field ---
        # LIB-p00001 is a Template; it has no outbound SATISFIES edges, so
        # the serializer must skip the rollup. If this fires it means
        # _serialize_node_generic is leaking the field onto wrong nodes.
        assert "LIB-p00001" in node_index, "expected LIB-p00001 in node-index"
        lib_props = node_index["LIB-p00001"].get("properties") or {}
        assert "satisfier_rollup" not in lib_props, (
            f"LIB-p00001 is a template (no Satisfies edges), should not have "
            f"satisfier_rollup; got {lib_props.get('satisfier_rollup')!r}"
        )
