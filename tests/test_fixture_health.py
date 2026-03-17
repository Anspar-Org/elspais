# Validates REQ-p00002
"""Health check validation on test fixtures.

Ensures each fixture with an .elspais.toml can build a graph and pass
spec health checks via run_spec_checks (the proper orchestration path).
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Fixtures that have their own .elspais.toml and spec/ directory
FIXTURE_DIRS = sorted(
    d
    for d in FIXTURES_DIR.iterdir()
    if d.is_dir() and (d / ".elspais.toml").exists() and (d / "spec").exists()
)


@pytest.mark.parametrize(
    "fixture_dir",
    FIXTURE_DIRS,
    ids=[d.name for d in FIXTURE_DIRS],
)
class TestFixtureHealth:
    """Validates REQ-p00002: Requirements validation works on fixture projects."""

    def test_REQ_p00002_fixture_spec_checks_pass(self, fixture_dir: Path) -> None:
        """Fixture project passes all spec health checks via run_spec_checks."""
        from elspais.commands.health import run_spec_checks
        from elspais.config import ConfigLoader, get_config, get_spec_directories
        from elspais.graph.factory import build_graph

        raw_config = get_config(start_path=fixture_dir)
        config = ConfigLoader.from_dict(raw_config)
        graph = build_graph(
            config=raw_config,
            repo_root=fixture_dir,
            scan_code=False,
            scan_tests=False,
            _build_associates=False,
        )
        assert graph.node_count() > 0, f"Fixture {fixture_dir.name} produced empty graph"

        spec_dirs = get_spec_directories(None, raw_config)
        spec_dirs = [fixture_dir / d for d in spec_dirs]
        checks = run_spec_checks(graph, config, spec_dirs=spec_dirs)

        errors = [c for c in checks if not c.passed and c.severity == "error"]
        assert not errors, f"Fixture {fixture_dir.name} has {len(errors)} error(s): " + "; ".join(
            c.message for c in errors
        )
