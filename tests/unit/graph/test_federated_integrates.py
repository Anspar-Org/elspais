# Verifies: REQ-d00252
"""Tests for cross-graph Integrates: edge wiring during federation.

Validates REQ-d00252-C, REQ-d00252-D, REQ-d00252-E: a consumer requirement
declares ``Integrates: <associate REQ id>`` to say its implementation is
provided by a requirement in a configured associate (external library) repo.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from elspais.commands.health import check_spec_hierarchy_levels
from elspais.config import get_config
from elspais.graph.factory import build_graph
from elspais.graph.metrics import direct_coverage_for
from elspais.graph.relations import EdgeKind
from elspais.graph.render import render_node

FIX = Path(__file__).parents[2] / "fixtures" / "e2e-integrates"

# A levels block shared by the inline federation repos below. The consumer
# (dev) and library (prd) deliberately sit at DIFFERENT levels so an
# INTEGRATES edge, if treated as a hierarchy parent, would look like a
# cross-level deviation.
_LEVELS_TOML = """\
[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]
[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "prd"]
[scanning.spec]
directories = ["spec"]
[scanning.code]
directories = []
[scanning.test]
enabled = false
directories = []
"""


def _write(path: Path, text: str) -> None:
    """Write ``text`` to ``path``, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _federate(app_root: Path):
    """Build a FederatedGraph rooted at ``app_root``."""
    return build_graph(
        config=get_config(None, app_root),
        repo_root=app_root,
        scan_code=False,
        scan_tests=False,
    )


def _copy_full(tmp_path: Path) -> Path:
    """Copy the whole fixture (app + library) to tmp; return the app root."""
    dest = tmp_path / "proj"
    shutil.copytree(FIX, dest)
    return dest / "app"


def _copy_app_only(tmp_path: Path) -> Path:
    """Copy only the app/ tree to tmp so ``../library`` does not exist."""
    dest = tmp_path / "proj"
    (dest).mkdir(parents=True)
    shutil.copytree(FIX / "app", dest / "app")
    return dest / "app"


def _outgoing_integrates(node):
    return [e for e in node.iter_outgoing_edges() if e.kind == EdgeKind.INTEGRATES]


class TestIntegratesWiresEdge:
    """Validates REQ-d00252-D: wire an INTEGRATES edge from consumer to library."""

    def test_REQ_d00252_D_integrates_wires_cross_graph_edge(self, tmp_path):
        app_root = _copy_full(tmp_path)
        fed = _federate(app_root)
        app_req = fed._repos["app"].graph._index["APP-d00001"]
        edges = _outgoing_integrates(app_req)
        assert len(edges) == 1
        assert edges[0].target.id == "LIB-d00007"

    def test_REQ_d00252_D_consumer_requirement_is_implemented(self, tmp_path):
        app_root = _copy_full(tmp_path)
        fed = _federate(app_root)
        app_req = fed._repos["app"].graph._index["APP-d00001"]
        assert direct_coverage_for(app_req) >= 1

    def test_REQ_d00252_D_library_node_unmodified(self, tmp_path):
        app_root = _copy_full(tmp_path)
        fed = _federate(app_root)
        lib_req = fed._repos["library"].graph._index["LIB-d00007"]
        assert "APP-d00001" not in render_node(lib_req)

    def test_REQ_d00252_D_assertion_suffix_target_wires_whole_req(self, tmp_path):
        """Validates REQ-d00252-D: an Integrates target with a library assertion
        suffix (LIB-d00007-A) resolves to the base REQ and wires one whole-REQ edge."""
        app_root = _copy_full(tmp_path)
        app_spec = app_root / "spec" / "dev-app.md"
        app_spec.write_text(app_spec.read_text().replace("LIB-d00007", "LIB-d00007-A"))
        fed = _federate(app_root)
        app_req = fed._repos["app"].graph._index["APP-d00001"]
        integ = _outgoing_integrates(app_req)
        assert len(integ) == 1
        assert integ[0].target.id == "LIB-d00007"
        # no broken ref for the suffixed target
        assert not fed._repos["app"].graph._broken_references


class TestIntegratesUnresolved:
    """Validates REQ-d00252-E: unresolved targets are soft or hard per claim."""

    def test_REQ_d00252_E_absent_associate_is_soft(self, tmp_path):
        # Copy only app/ so ../library does not exist: associate soft-fails.
        app_root = _copy_app_only(tmp_path)
        fed = _federate(app_root)  # must not raise
        brs = fed._repos["app"].graph._broken_references
        matches = [b for b in brs if b.target_id == "LIB-d00007"]
        assert len(matches) == 1
        assert matches[0].presumed_foreign is True

    def test_REQ_d00252_E_configured_but_missing_is_hard(self, tmp_path):
        app_root = _copy_full(tmp_path)
        spec = app_root / "spec" / "dev-app.md"
        spec.write_text(
            spec.read_text().replace("**Integrates**: LIB-d00007", "**Integrates**: LIB-d99999")
        )
        fed = _federate(app_root)
        brs = fed._repos["app"].graph._broken_references
        matches = [b for b in brs if b.target_id == "LIB-d99999"]
        assert len(matches) == 1
        assert matches[0].presumed_foreign is False


class TestIntegratesSameRepo:
    """Validates REQ-d00252-C: a same-repo target is an external-only violation."""

    def test_REQ_d00252_C_same_repo_target_is_error(self, tmp_path):
        # Add a second app REQ and point Integrates at it (same repo).
        app_root = _copy_full(tmp_path)
        spec = app_root / "spec" / "dev-app.md"
        text = spec.read_text().replace("**Integrates**: LIB-d00007", "**Integrates**: APP-d00002")
        text += (
            "\n\n# APP-d00002: Local helper\n\n"
            "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
            "A locally-provided helper.\n\n"
            "## Assertions\n\n"
            "A. The helper SHALL exist.\n\n"
            "*End* *Local helper* | **Hash**: 00000000\n"
        )
        spec.write_text(text)
        fed = _federate(app_root)
        app_req = fed._repos["app"].graph._index["APP-d00001"]
        # No INTEGRATES edge created for a same-repo target.
        assert _outgoing_integrates(app_req) == []
        brs = fed._repos["app"].graph._broken_references
        matches = [b for b in brs if b.target_id == "APP-d00002"]
        assert len(matches) == 1


class TestIntegratesHierarchyLevels:
    """Validates REQ-d00252-D: the cross-repo INTEGRATES edge is an
    integration link, not a level-hierarchy relationship, so it must be
    excluded from the spec hierarchy-level check. A low-level consumer that
    ``Integrates:`` a higher-level library requirement must NOT produce a
    false-positive hierarchy-level deviation on the library node."""

    def _build_cross_level_federation(self, tmp_path: Path):
        """Inline federation where a DEV consumer integrates a PRD library
        requirement (cross-level). Returns the FederatedGraph."""
        library = tmp_path / "library"
        app = tmp_path / "app"

        _write(
            library / ".elspais.toml",
            'version = 3\n[project]\nname = "library"\nnamespace = "LIB"\n' + _LEVELS_TOML,
        )
        _write(
            library / "spec" / "prd.md",
            "# LIB-p00001: Event Log\n\n"
            "**Level**: prd | **Status**: Active | **Implements**: -\n\n"
            "A. SHALL append.\n\n"
            "*End* *Event Log*\n",
        )

        _write(
            app / ".elspais.toml",
            'version = 3\n[project]\nname = "app"\nnamespace = "APP"\n'
            + _LEVELS_TOML
            + '[associates.library]\npath = "../library"\nnamespace = "LIB"\n',
        )
        _write(
            app / "spec" / "dev.md",
            "# APP-d00001: Consumer log\n\n"
            "**Level**: dev | **Status**: Active | **Implements**: -\n"
            "**Integrates**: LIB-p00001\n\n"
            "A. SHALL use the library log.\n\n"
            "*End* *Consumer log*\n",
        )

        return build_graph(
            config=get_config(None, app),
            repo_root=app,
            scan_code=False,
            scan_tests=False,
        )

    def test_REQ_d00252_D_integrates_edge_excluded_from_hierarchy_levels(self, tmp_path):
        """The INTEGRATES edge (consumer DEV -> library PRD) must NOT be
        counted as a hierarchy parent. Fails on the unfixed code because the
        check iterates all parents and flags LIB-p00001 <- APP-d00001."""
        fed = self._build_cross_level_federation(tmp_path)
        lib_entry = fed._repos["library"]

        # Sanity: the cross-repo INTEGRATES edge exists, so the library node
        # really does have the consumer as an INTEGRATES parent. Without this
        # the test could pass for the wrong reason (no edge at all).
        lib_req = lib_entry.graph._index["LIB-p00001"]
        integ_parents = [e for e in lib_req.iter_incoming_edges() if e.kind == EdgeKind.INTEGRATES]
        assert len(integ_parents) == 1
        assert integ_parents[0].source.id == "APP-d00001"

        res = check_spec_hierarchy_levels(lib_entry.graph, lib_entry.config)
        violations = res.details.get("violations", [])
        offending = [
            v for v in violations if v["child"] == "LIB-p00001" and v["parent"] == "APP-d00001"
        ]
        assert offending == [], (
            "INTEGRATES edge wrongly flagged as a hierarchy-level deviation: " f"{offending}"
        )
        assert violations == []
        assert res.message == "All requirements follow hierarchy rules"

    def _build_associate_consumer_federation(self, tmp_path: Path):
        """Inline federation where the CONSUMER lives in an ASSOCIATE repo.

        CUR-1521: the root repo declares TWO associates (A and B). A
        requirement in associate A declares ``Integrates:`` a requirement in
        associate B. Because A's per-repo build does not know B's ids, the
        Integrates target is recorded as a cross-repo INTEGRATES *broken
        reference* in A's graph -- this is the exact condition that triggers
        the double-wiring bug. A simple root-consumer -> associate-library
        Integrates does NOT reproduce it. Returns the FederatedGraph.
        """
        root = tmp_path / "root"
        assoc_a = tmp_path / "assoc_a"
        assoc_b = tmp_path / "assoc_b"

        # Associate A holds the CONSUMER requirement that Integrates: B's REQ.
        _write(
            assoc_a / ".elspais.toml",
            'version = 3\n[project]\nname = "assoc_a"\nnamespace = "AAA"\n' + _LEVELS_TOML,
        )
        _write(
            assoc_a / "spec" / "dev.md",
            "# AAA-d00001: Consumer log\n\n"
            "**Level**: dev | **Status**: Active | **Implements**: -\n"
            "**Integrates**: BBB-p00001\n\n"
            "A. SHALL use the library log.\n\n"
            "*End* *Consumer log*\n",
        )

        # Associate B holds the LIBRARY requirement that A integrates.
        _write(
            assoc_b / ".elspais.toml",
            'version = 3\n[project]\nname = "assoc_b"\nnamespace = "BBB"\n' + _LEVELS_TOML,
        )
        _write(
            assoc_b / "spec" / "prd.md",
            "# BBB-p00001: Event Log\n\n"
            "**Level**: prd | **Status**: Active | **Implements**: -\n\n"
            "A. SHALL append.\n\n"
            "*End* *Event Log*\n",
        )

        # Only the ROOT may declare associates (FederationError otherwise).
        _write(
            root / ".elspais.toml",
            'version = 3\n[project]\nname = "root"\nnamespace = "ROOT"\n'
            + _LEVELS_TOML
            + '[associates.assoc_a]\npath = "../assoc_a"\nnamespace = "AAA"\n'
            + '[associates.assoc_b]\npath = "../assoc_b"\nnamespace = "BBB"\n',
        )
        # The root needs at least one spec file to build cleanly.
        _write(
            root / "spec" / "prd.md",
            "# ROOT-p00001: Root anchor\n\n"
            "**Level**: prd | **Status**: Active | **Implements**: -\n\n"
            "A. SHALL anchor.\n\n"
            "*End* *Root anchor*\n",
        )

        return build_graph(
            config=get_config(None, root),
            repo_root=root,
            scan_code=False,
            scan_tests=False,
        )

    def test_REQ_d00252_C_integrates_wires_single_edge_no_cycle(self, tmp_path):
        """CUR-1521 regression: a consumer in an ASSOCIATE repo that
        ``Integrates:`` a requirement in another associate must produce exactly
        ONE INTEGRATES edge (consumer -> library). The pre-fix code wired a
        SECOND, reverse edge (library -> consumer) via the generic
        broken-reference resolver in ``_wire_cross_graph_edges``, creating a
        cycle. Asserts: (1) consumer has one outgoing INTEGRATES edge to the
        library; (2) the library has NO outgoing INTEGRATES edge back to the
        consumer; (3) no broken reference remains for the resolved target."""
        fed = self._build_associate_consumer_federation(tmp_path)
        consumer = fed._repos["assoc_a"].graph._index["AAA-d00001"]
        library = fed._repos["assoc_b"].graph._index["BBB-p00001"]

        # (1) Exactly one outgoing INTEGRATES edge from consumer -> library.
        out = [e for e in consumer.iter_outgoing_edges() if e.kind == EdgeKind.INTEGRATES]
        assert len(out) == 1, f"expected one consumer->library INTEGRATES edge, got {out}"
        assert out[0].target.id == "BBB-p00001"

        # (2) NO reverse edge library -> consumer (the cycle the bug created).
        reverse = [e for e in library.iter_outgoing_edges() if e.kind == EdgeKind.INTEGRATES]
        assert reverse == [], (
            "library wrongly has an outgoing INTEGRATES edge back to the consumer "
            f"(double-wired cycle): {[(e.source.id, e.target.id) for e in reverse]}"
        )

        # (3) No surviving broken reference for the resolved Integrates target.
        leftover = [
            br
            for br in fed._repos["assoc_a"].graph._broken_references
            if br.target_id == "BBB-p00001"
        ]
        assert leftover == [], f"resolved Integrates target left a broken ref: {leftover}"

    def test_REQ_d00252_D_genuine_level_violation_still_detected(self, tmp_path):
        """CONTROL: a real same-repo level violation (a PRD requirement that
        ``Implements:`` a DEV requirement) must STILL be reported. Proves the
        INTEGRATES exclusion does not gut the check."""
        repo = tmp_path / "repo"
        _write(
            repo / ".elspais.toml",
            'version = 3\n[project]\nname = "repo"\nnamespace = "REPO"\n' + _LEVELS_TOML,
        )
        _write(
            repo / "spec" / "reqs.md",
            "# REPO-d00001: Foo\n\n"
            "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
            "A. SHALL foo.\n\n"
            "*End* *Foo*\n\n"
            "# REPO-p00001: Bar\n\n"
            "**Level**: prd | **Status**: Active | **Implements**: REPO-d00001\n\n"
            "A. SHALL bar.\n\n"
            "*End* *Bar*\n",
        )

        fed = build_graph(
            config=get_config(None, repo),
            repo_root=repo,
            scan_code=False,
            scan_tests=False,
        )
        entry = fed._repos["repo"]

        res = check_spec_hierarchy_levels(entry.graph, entry.config)
        violations = res.details.get("violations", [])
        offending = [
            v for v in violations if v["child"] == "REPO-p00001" and v["parent"] == "REPO-d00001"
        ]
        assert (
            len(offending) == 1
        ), f"genuine same-repo level violation not detected; violations={violations}"
