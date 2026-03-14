"""
pytest configuration and shared fixtures for elspais tests.
"""

import sys
from collections.abc import Generator
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Test run metadata sidecar for elspais health visibility.
# Any test runner can produce this format; this is the pytest implementation.
_REPO_ROOT = Path(__file__).parent.parent
_RUN_META_PATH = _REPO_ROOT / "test-run-meta.json"


def pytest_deselected(items):
    """Write deselected test metadata to sidecar JSON for elspais."""
    import json

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
        "project": {
            "name": "test-project",
            "type": "core",
            "namespace": "REQ",
        },
        "directories": {
            "spec": "spec",
            "docs": "docs",
        },
        "id-patterns": {
            "canonical": "{namespace}-{type.letter}{component}",
            "aliases": {"short": "{type.letter}{component}"},
            "types": {
                "prd": {"level": 1, "aliases": {"letter": "p"}},
                "ops": {"level": 2, "aliases": {"letter": "o"}},
                "dev": {"level": 3, "aliases": {"letter": "d"}},
            },
            "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
        },
        "rules": {
            "hierarchy": {
                "allowed_implements": [
                    "dev -> ops, prd",
                    "ops -> prd",
                    "prd -> prd",
                ],
                "allow_circular": False,
                "allow_orphans": False,
            },
            "format": {
                "require_hash": True,
                "require_assertions": True,
                "acceptance_criteria": "warn",
            },
        },
    }
