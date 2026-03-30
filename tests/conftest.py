# Verifies: REQ-p00013-A+B+C+D+E+F
"""
pytest configuration and shared fixtures for elspais tests.
"""

import os
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def pytest_configure(config):
    """Strip git env vars before any test collection or coverage forking.

    Git sets GIT_DIR when running hooks (pre-commit, pre-push).  This
    overrides cwd in subprocess calls, causing test git operations to
    target the hook's repo instead of temp directories.

    GIT_CEILING_DIRECTORIES=/ prevents git from discovering a parent
    .git above a test's working directory — defense-in-depth against
    accidental upward repo discovery.

    Using pytest_configure (not module-level code) ensures this runs
    before pytest-cov forks coverage subprocesses.
    """
    os.environ.pop("GIT_DIR", None)
    os.environ.pop("GIT_WORK_TREE", None)
    os.environ["GIT_CEILING_DIRECTORIES"] = "/"
    config.addinivalue_line(
        "markers",
        "incremental: mark test class for sequential execution with xfail on prior failure",
    )


# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Test run metadata sidecar for elspais health visibility.
# Any test runner can produce this format; this is the pytest implementation.
_REPO_ROOT = Path(__file__).parent.parent
_RUN_META_PATH = _REPO_ROOT / ".results" / "test-run-meta.json"


def pytest_deselected(items):
    """Write deselected test metadata to sidecar JSON for elspais."""
    import json

    _RUN_META_PATH.parent.mkdir(exist_ok=True)
    _RUN_META_PATH.write_text(
        json.dumps(
            {
                "runner": "pytest",
                "deselected_count": len(items),
                "deselected": [item.nodeid for item in items],
            },
            indent=2,
        )
    )


def pytest_runtest_makereport(item, call):
    """Track failures in incremental test classes."""
    if "incremental" in item.keywords and call.excinfo is not None:
        item.parent._previous_failed = item.name


def pytest_runtest_setup(item):
    """Skip subsequent tests in incremental class if a prior step failed."""
    previous = getattr(item.parent, "_previous_failed", None)
    if previous and "incremental" in item.keywords:
        pytest.xfail(f"previous step failed: {previous}")


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def hht_like_fixture() -> Path:
    """Return path to HHT-like fixture."""
    return FIXTURES_DIR / "hht-like"


@pytest.fixture
def fda_style_fixture() -> Path:
    """Return path to FDA-style fixture."""
    return FIXTURES_DIR / "fda-style"


@pytest.fixture
def jira_style_fixture() -> Path:
    """Return path to Jira-style fixture."""
    return FIXTURES_DIR / "jira-style"


@pytest.fixture
def named_reqs_fixture() -> Path:
    """Return path to named requirements fixture."""
    return FIXTURES_DIR / "named-reqs"


@pytest.fixture
def associated_repo_fixture() -> Path:
    """Return path to associated repository fixture."""
    return FIXTURES_DIR / "associated-repo"


@pytest.fixture
def circular_deps_fixture() -> Path:
    """Return path to circular dependencies fixture (invalid)."""
    return FIXTURES_DIR / "invalid" / "circular-deps"


@pytest.fixture
def broken_links_fixture() -> Path:
    """Return path to broken links fixture (invalid)."""
    return FIXTURES_DIR / "invalid" / "broken-links"


@pytest.fixture
def missing_hash_fixture() -> Path:
    """Return path to missing hash fixture (invalid)."""
    return FIXTURES_DIR / "invalid" / "missing-hash"


@pytest.fixture
def assertions_fixture() -> Path:
    """Return path to assertions-based fixture."""
    return FIXTURES_DIR / "assertions"


@pytest.fixture
def hht_resolver():
    """Return an IdResolver configured for the standard HHT-like pattern."""
    from elspais.utilities.patterns import IdPatternConfig, IdResolver

    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
    )
    return IdResolver(config)


@pytest.fixture
def temp_project(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary project directory for testing."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    spec_dir = project_dir / "spec"
    spec_dir.mkdir()
    yield project_dir


@pytest.fixture
def sample_requirement_text() -> str:
    """Return sample requirement markdown text."""
    return """### REQ-p00001: Sample Requirement

**Level**: PRD | **Status**: Active

The system SHALL do something.

**Acceptance Criteria**:
- Criterion 1
- Criterion 2

*End* *Sample Requirement* | **Hash**: test1234
---"""


@pytest.fixture
def sample_config_dict() -> dict:
    """Return sample configuration dictionary."""
    return {
        "version": 3,
        "project": {
            "name": "test-project",
            "namespace": "REQ",
        },
        "levels": {
            "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
            "ops": {"rank": 2, "letter": "o", "implements": ["ops", "prd"]},
            "dev": {"rank": 3, "letter": "d", "implements": ["dev", "ops", "prd"]},
        },
        "scanning": {
            "spec": {"directories": ["spec"]},
            "docs": {"directories": ["docs"]},
        },
        "id-patterns": {
            "canonical": "{namespace}-{level.letter}{component}",
            "aliases": {"short": "{level.letter}{component}"},
            "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
        },
        "rules": {
            "hierarchy": {
                "allow_circular": False,
                "allow_structural_orphans": False,
            },
            "format": {
                "require_hash": True,
                "require_assertions": True,
            },
        },
    }


@pytest.fixture(scope="session")
def canonical_federated_graph():
    """Build the hht-like fixture FederatedGraph once per session.

    Use this when you need the full FederatedGraph (e.g., for trace commands).
    Use canonical_graph for the primary TraceGraph.
    """
    from elspais.graph.factory import build_graph

    root = FIXTURES_DIR / "hht-like"
    return build_graph(repo_root=root)


@pytest.fixture(scope="session")
def canonical_graph(canonical_federated_graph):
    """The primary TraceGraph from the hht-like fixture.

    Built once per session. For read-only assertions against graph state.
    """
    fg = canonical_federated_graph
    return fg._repos[fg._root_repo].graph


@pytest.fixture(scope="class")
def mutable_graph(canonical_graph):
    """Yield the canonical graph for a mutation chain, undo all on teardown.

    Use with @pytest.mark.incremental test classes. Tests run in order,
    each mutating the graph. After the class completes, all mutations
    are undone, restoring the graph to its pristine state.
    """
    yield canonical_graph
    while canonical_graph.mutation_log.last() is not None:
        canonical_graph.undo_last()
