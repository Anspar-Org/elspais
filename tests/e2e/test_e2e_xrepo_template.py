# Verifies: REQ-p00014
"""E2E tests for cross-repo template instantiation (CUR-1353).

Drives the real ``elspais`` CLI against the ``e2e-xrepo-template`` fixture
(library + app + tenant) to verify:

  - Phase 1: ``**Template**`` marker round-trips through render (exercised
             via the library fixture's spec file).
  - Phase 3: federated cross-repo Satisfies produces composite-ID clones
             that appear in trace/graph output without leaking onto disk.
  - Phase 4: missing-associate diagnostic surfaces in ``checks`` output
             (the cycle-detection branch is unit-test only because the
             federation factory rejects circular configs before this layer).
  - Phase 5: inherited template coverage flows from the library's CODE/TEST
             through to template rollups; instance assertion clones carry a
             ``template_repo`` field for viewer attribution.

Phase 2 (in-repo validation matrix — ``Refines: TEMPLATE`` errors etc.) is
covered exhaustively by ``tests/unit/graph/test_template_validation.py`` and
is not duplicated here: the rules need contrived spec-content combinations
that are awkward at the e2e level.

Fixture topology (see ``tests/fixtures/e2e-xrepo-template/``):

  library  -- LIB-p00001 template (assertions A and B);
              library/src/library.py implements LIB-p00001-A;
              library/tests/test_library.py verifies LIB-p00001-B.
  app      -- APP-p00001 Satisfies LIB-p00001 (+ own assertion A);
              APP-p00002 Refines APP-p00001;
              app/src/app.py implements both APP-p00001-A and APP-p00002-A.
  tenant   -- TEN-p00001 Satisfies LIB-p00001 (+ own assertion A).

All tests drive the real CLI; the daemon is restarted per fixture project so
cross-test pollution is avoided.
"""

from __future__ import annotations

import json
import shutil

import pytest

from .conftest import (
    ensure_fixture_daemon,
    load_xrepo_template_fixture,
    run_elspais,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Shared module fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Copy fixture to /tmp, git init each repo, start daemon on app project."""
    root = tmp_path_factory.mktemp("e2e_xrepo_template")
    app = load_xrepo_template_fixture(root)
    ensure_fixture_daemon(app)
    return app


# ---------------------------------------------------------------------------
# Phase 1/2/3: Federated graph builds clean, instance composites surface
# ---------------------------------------------------------------------------


class TestHealthOnCrossRepoTemplate:
    """Cross-repo Satisfies graph passes lenient checks; composites surface."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_trace_lists_instance_clones(self, project):
        """Phase A clones must appear with composite IDs in the trace matrix."""
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0, result.stderr
        rows = json.loads(result.stdout)
        ids = {row["id"] for row in rows}
        # Phase A composite root
        assert (
            "APP-p00001::LIB-p00001" in ids
        ), f"Missing composite instance root in trace; saw: {sorted(ids)}"
        # Underlying template still observable
        assert "LIB-p00001" in ids


# ---------------------------------------------------------------------------
# Phase 4: Missing-associate diagnostic
# ---------------------------------------------------------------------------


class TestMissingAssociateDiagnostic:
    """When the associate path is broken, ``checks`` must fail with a clear message."""

    def test_missing_path_fails_health(self, tmp_path_factory):
        root = tmp_path_factory.mktemp("e2e_xrepo_missing")
        app = load_xrepo_template_fixture(root)
        # Point the associate at a non-existent directory.
        cfg = (app / ".elspais.toml").read_text()
        cfg = cfg.replace('path = "../library"', 'path = "../nowhere"')
        (app / ".elspais.toml").write_text(cfg)

        result = run_elspais("checks", cwd=app)
        assert result.returncode != 0, f"Expected non-zero exit, got 0. stdout={result.stdout}"
        combined = result.stdout + result.stderr
        # Diagnostic must surface the associate name and/or path so the user
        # can find the broken config entry.
        assert (
            "library" in combined.lower() or "nowhere" in combined.lower()
        ), f"Expected diagnostic to mention the broken associate; got:\n{combined}"
        # The associate_paths check is what produces the failure.
        assert (
            "associate" in combined.lower()
        ), f"Expected 'associate' in diagnostic; got:\n{combined}"


# ---------------------------------------------------------------------------
# Phase 3: Trace surfaces the instance card alongside the satisfier
# ---------------------------------------------------------------------------


class TestTraceShowsInstanceCard:
    """The composite instance node is visible in trace output formats."""

    def test_trace_json_includes_composite_id(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0, result.stderr
        # Substring search is enough — JSON dump preserves the composite ID.
        assert "APP-p00001::LIB-p00001" in result.stdout

    def test_trace_markdown_includes_composite_id(self, project):
        # Default format is markdown — exercise it too so docs/text users
        # also see the instance card.
        result = run_elspais("trace", cwd=project)
        assert result.returncode == 0, result.stderr
        assert "APP-p00001::LIB-p00001" in result.stdout


# ---------------------------------------------------------------------------
# Phase 3: render_save must not leak template content into satisfier files
# ---------------------------------------------------------------------------


class TestRenderSaveDoesNotLeakInstance:
    """The satisfier's spec file must keep only ``Satisfies:`` (no template body)."""

    def test_app_disk_file_has_no_instance_subtree(self, project):
        spec = (project / "spec" / "prd-app.md").read_text()
        # The Satisfies metadata line must remain on disk.
        assert "Satisfies" in spec
        assert "LIB-p00001" in spec
        # The template title and body MUST NOT be persisted into APP's spec.
        assert "Action Dispatch" not in spec
        assert "parsing, validation, authorization" not in spec
        # And the Phase A composite ID must never be written to disk —
        # it exists only in memory after the federated build.
        assert "APP-p00001::LIB-p00001" not in spec


# ---------------------------------------------------------------------------
# Phase 5: Inherited template coverage
# ---------------------------------------------------------------------------


class TestInheritedCoverageEndToEnd:
    """Coverage on template assertions flows through to satisfiers in the same view."""

    def test_template_assertion_reports_inherited_coverage(self, project):
        """The library has its own CODE+TEST against LIB-p00001-A/B. Built
        through the app project, that coverage must still surface on the
        template rollup (not just as ``n/a``) — proving the federated graph
        keeps the template node reachable to evidence."""
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0, result.stderr
        rows = {row["id"]: row for row in json.loads(result.stdout)}
        template = rows.get("LIB-p00001")
        assert template is not None, f"LIB-p00001 not present in trace; saw {sorted(rows)}"
        # The library implements LIB-p00001-A in src/library.py — coverage
        # for the template assertion must be non-zero. Parse the numerator
        # so we catch nonsense like "0/2" without accepting it through a
        # loose ``startswith`` branch.
        implemented = template.get("implemented", "")
        covered_count = int(implemented.split("/", 1)[0]) if "/" in implemented else 0
        assert covered_count >= 1, (
            f"Expected template LIB-p00001 to have at least one implementation "
            f"(from library/src/library.py); got implemented={implemented!r}"
        )

    def test_lenient_checks_pass_with_inherited_evidence(self, project):
        """The app has no direct CODE targeting LIB-p00001-A/B; coverage
        comes via inheritance. ``checks --lenient`` must still report
        HEALTHY (the cross-repo evidence does its job)."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, (
            f"Expected HEALTHY despite zero direct coverage on inherited "
            f"assertions; got:\n{result.stdout}\n{result.stderr}"
        )

    def test_template_repo_attribution_in_graph(self, project):
        """Phase 5: instance assertion nodes carry a ``template_repo`` field
        so the viewer can attribute inherited evidence to the source repo."""
        result = run_elspais("graph", cwd=project)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        nodes = data["nodes"]
        instance = nodes.get("APP-p00001::LIB-p00001-A")
        assert instance is not None, (
            f"INSTANCE assertion node not found in graph output. "
            f"Available (first 10): {sorted(nodes.keys())[:10]}"
        )
        # Phase 5 stamp: template_repo identifies the source repo.
        assert instance["content"].get("template_repo") == "library"
        # Phase 3 stamp: stereotype distinguishes instances from concrete nodes.
        # ``serialize_node`` emits ``Enum.value``; Stereotype.INSTANCE.value == "instance".
        assert instance["content"].get("stereotype") == "instance"
