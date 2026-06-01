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
