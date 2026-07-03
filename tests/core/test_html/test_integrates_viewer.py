# Verifies: REQ-d00252
"""HTML viewer support for the ``Integrates:`` feature (REQ-d00252).

A consumer requirement that declares ``Integrates: <library-req>`` inherits
the library requirement's implemented/verified coverage via the dedicated
``INTEGRATES`` edge. The viewer must surface, for the consumer card:

1. The inherited coverage rollup (``integrates_rollup``), serialized into the
   embedded ``node-index`` JSON island and rendered as an "Integrated
   coverage:" row.
2. The INTEGRATES relationship link to the library requirement.
3. An edge badge in the legend catalog describing the relationship.

The card UI is rendered client-side by JavaScript using the embedded
``node-index`` JSON, so most assertions inspect that JSON. The display-literal
tests assert against the inlined card JS template / CSS hooks.
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


def _extract_node_index(html: str) -> dict:
    """Parse the embedded ``node-index`` JSON island from the rendered HTML."""
    m = re.search(
        r'<script[^>]*id="node-index"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert m is not None, "expected an embedded node-index <script> in rendered HTML"
    return json.loads(m.group(1))


@pytest.fixture
def federation(tmp_path: Path):
    """Two-repo federation: library (covered code) + app (consumer via Integrates)."""
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
        # LIB-p00001: Append-only event log

        **Level**: PRD | **Status**: Approved

        ### Assertions

        A. Events SHALL be appended.

        *End* *Append-only event log*
        """,
    )
    _write(
        library,
        "src/lib.py",
        """
        # Implements: LIB-p00001-A
        def append(e):
            return e
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
        # APP-p00001: Concrete consumer

        **Level**: PRD | **Status**: Approved
        **Integrates**: LIB-p00001

        ### Assertions

        A. SHALL be admin-only.

        *End* *Concrete consumer*
        """,
    )
    _git_init(app)

    return build_graph(repo_root=app, scan_code=True, scan_tests=False)


class TestIntegratesRollupSerialized:
    """Validates REQ-d00252-D: the consumer's integrates_rollup is serialized
    into the embedded node-index JSON, and non-consumers carry no rollup."""

    def test_REQ_d00252_D_consumer_node_index_has_integrates_rollup(self, federation):
        """Consumer APP-p00001 exposes integrates_rollup with inherited numerics."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)

        cid = "APP-p00001"
        assert cid in nodes, f"expected consumer {cid} in node-index; got {sorted(nodes)[:10]}"
        props = nodes[cid].get("properties") or {}
        assert (
            "integrates_rollup" in props
        ), f"expected integrates_rollup on consumer {cid}; properties keys: {sorted(props)}"
        assert props["integrates_rollup"] == {
            "implemented_covered": 1,
            "implemented_total": 1,
            "verified_covered": 0,
            "verified_total": 1,
            "has_failures": False,
        }, (
            "integrates_rollup numerics mismatch (library REQ has 1 assertion, "
            f"implemented by code, not verified); got {props['integrates_rollup']!r}"
        )

    # Verifies: REQ-d00252-D, REQ-d00258-B
    def test_REQ_d00258_B_library_failure_flag_serialized(self, federation):
        """A failing library Verifies-result with full lcov credit reads as
        covered in the passing union, but the serialized rollup must carry
        has_failures=True so the viewer can flag the red library suite."""
        from elspais.graph.metrics import CoverageDimension, RollupMetrics

        lib_req = federation._repos["library"].graph._index["LIB-p00001"]
        lib_req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=CoverageDimension(total=1, direct=1.0, indirect=1.0),
                verified=CoverageDimension(total=1, has_failures=True),
                lcov_tested=CoverageDimension(
                    total=1,
                    direct=1.0,
                    indirect=1.0,
                    direct_labels={"A"},
                    indirect_labels={"A"},
                    direct_pct_by_label={"A": 1.0},
                    indirect_pct_by_label={"A": 1.0},
                ),
            ),
        )

        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)
        rollup = (nodes["APP-p00001"].get("properties") or {})["integrates_rollup"]
        assert rollup["verified_covered"] == 1  # union covered despite the failure
        assert rollup["has_failures"] is True

    def test_REQ_d00252_D_non_integrating_req_has_no_integrates_rollup(self, federation):
        """Library LIB-p00001 (no outbound INTEGRATES) carries no rollup field."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)

        assert "LIB-p00001" in nodes, "expected LIB-p00001 in node-index"
        props = nodes["LIB-p00001"].get("properties") or {}
        assert "integrates_rollup" not in props, (
            f"library REQ has no outbound INTEGRATES, should not carry integrates_rollup; "
            f"got {props.get('integrates_rollup')!r}"
        )


class TestIntegratesRollupRendered:
    """Validates REQ-d00252-D: the rendered HTML wires the integrated-coverage
    card row (label + CSS hook) for consumer requirements."""

    def test_REQ_d00252_D_integrated_coverage_label_in_html(self, federation):
        """The 'Integrated coverage:' label and 'integrates-rollup' CSS class are wired in."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        assert "Integrated coverage:" in html, (
            "expected 'Integrated coverage:' label in rendered HTML "
            "(integrates rollup card row not wired in)"
        )
        assert (
            "integrates-rollup" in html
        ), "expected 'integrates-rollup' CSS class in rendered HTML"


class TestIntegratesRelationshipRendered:
    """Validates REQ-d00252-D: the INTEGRATES relationship is wired into the
    card (CSS hook) and carried as a link on both consumer and library nodes."""

    def test_REQ_d00252_D_integrates_relationship_section_in_html(self, federation):
        """The 'integrates-refs' CSS class (relationship section) is wired in."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        assert "integrates-refs" in html, (
            "expected 'integrates-refs' CSS class in rendered HTML "
            "(integrates relationship card section not wired in)"
        )

    def test_REQ_d00252_D_consumer_links_carry_integrates_edge(self, federation):
        """Consumer APP-p00001's links include an INTEGRATES edge to LIB-p00001."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)

        links = nodes["APP-p00001"].get("links") or []
        match = [
            link
            for link in links
            if link.get("edge_kind") == "integrates" and link.get("id") == "LIB-p00001"
        ]
        assert match, (
            f"expected consumer APP-p00001 to carry an INTEGRATES link to LIB-p00001; "
            f"got links: {links!r}"
        )

    def test_REQ_d00252_D_library_links_carry_integrates_edge(self, federation):
        """Library LIB-p00001's links include an INTEGRATES edge to APP-p00001."""
        html = HTMLGenerator(federation).generate(embed_content=True)
        nodes = _extract_node_index(html)

        links = nodes["LIB-p00001"].get("links") or []
        match = [
            link
            for link in links
            if link.get("edge_kind") == "integrates" and link.get("id") == "APP-p00001"
        ]
        assert match, (
            f"expected library LIB-p00001 to carry an INTEGRATES link to APP-p00001; "
            f"got links: {links!r}"
        )


class TestIntegratesEdgeBadge:
    """Validates REQ-d00252-D: the legend catalog defines an INTEGRATES edge
    badge with label and descriptions so the viewer can render its legend."""

    def test_REQ_d00252_D_legend_catalog_has_integrates_edge(self):
        """The badges.edge category includes a fully described integrates badge."""
        from elspais.html.theme import get_catalog

        catalog = get_catalog()
        edge_entries = catalog.by_category("badges.edge")
        integrates = [e for e in edge_entries if e.key == "badges.edge.integrates"]
        assert integrates, (
            "expected a 'badges.edge.integrates' entry in the legend catalog; "
            f"got edge keys: {[e.key for e in edge_entries]}"
        )
        entry = integrates[0]
        assert entry.label == "Integrates", f"expected label 'Integrates', got {entry.label!r}"
        assert entry.description, "expected non-empty description on integrates edge badge"
        assert (
            entry.long_description
        ), "expected non-empty long_description on integrates edge badge"
        assert entry.css_class, "expected non-empty css_class on integrates edge badge"
