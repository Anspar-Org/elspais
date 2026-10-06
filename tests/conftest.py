# Verifies: REQ-p00013-F
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


def _selects_marker(markexpr: str, name: str) -> bool:
    """Whether a marker expression SELECTS tests carrying *name*.

    Answered by evaluating the expression the way pytest's own selection does,
    against an item carrying *name* and nothing else. A substring test cannot
    answer it at all: `not browser` and `browser` both contain the word, and
    they mean opposite things.

    An expression pytest itself would reject compiles to nothing here and reads
    as selecting nothing; pytest reports the syntax error on its own terms.
    """
    if not markexpr:
        return False
    try:
        from _pytest.mark.expression import Expression
    except ImportError:  # pragma: no cover - private module, stable since 5.4
        # If it ever moves, keep the guard's narrow job rather than guessing:
        # the bare marker name is the one spelling that cannot be a negation.
        return markexpr.strip() == name
    try:
        return bool(Expression.compile(markexpr).evaluate(lambda n: n == name))
    except Exception:
        return False


def _selects_marker_set(markexpr: str, names: frozenset[str]) -> bool:
    """Whether a marker expression SELECTS a test carrying exactly *names*.

    The e2e tier's expression (`e2e and not serial`) selects the browser tests
    that also carry `e2e`, and says nothing of `browser`, so asking about each
    marker alone cannot tell that the tier runs them.
    """
    if not markexpr:
        return False
    try:
        from _pytest.mark.expression import Expression
    except ImportError:  # pragma: no cover - private module, stable since 5.4
        return False
    try:
        return bool(Expression.compile(markexpr).evaluate(lambda n: n in names))
    except Exception:
        return False


#: The environment variable naming the extras a session deliberately runs
#: without. Its tests that need one then skip, as they always did; without
#: it, a missing extra stops the session.
WITHOUT_ENV = "ELSPAIS_TEST_WITHOUT"

#: What each name ELSPAIS_TEST_WITHOUT accepts stands for.
OPTIONAL_EXTRAS = {
    "mcp": "the `mcp` package (the `mcp` extra, also in `all`)",
    "browser": "playwright and its chromium build (the `browser` extra)",
}

_SETUP_HINT = (
    "Run `make setup`, which installs this checkout's venv with every extra the "
    "suite uses and fetches chromium"
)


def _declared_without() -> set[str]:
    """The extras ELSPAIS_TEST_WITHOUT names, refusing a name it cannot mean."""
    raw = os.environ.get(WITHOUT_ENV, "")
    names = {part.strip() for part in raw.split(",") if part.strip()}
    unknown = sorted(names - set(OPTIONAL_EXTRAS))
    if unknown:
        raise pytest.UsageError(
            f"{WITHOUT_ENV} names {', '.join(unknown)}, which is not an extra the "
            f"suite can run without; it accepts: {', '.join(sorted(OPTIONAL_EXTRAS))}"
        )
    return names


def _importable(module: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _chromium_refusal() -> str | None:
    """Why the browser tests could not launch chromium, or None where they can."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "playwright is not installed"
    try:
        with sync_playwright() as p:
            executable = p.chromium.executable_path
    except Exception as exc:  # the driver itself failed to start
        return f"playwright could not start: {exc}"
    if not executable or not Path(executable).exists():
        return f"playwright's chromium is not installed (expected at {executable})"
    return None


def _missing_extras_refusal(markexpr: str) -> str | None:
    """Why this session would quietly skip tests it was asked to run, or None.

    A test needing an absent extra skips on `importorskip`, and a run that
    skipped a tier's worth of tests reads like a run that passed. Every tier
    holds tests importing `mcp`, so its absence stops every session. The
    browser extra and chromium stop a session that selects browser tests --
    the e2e tier does, since most browser tests also carry `e2e`. A session
    that means to run without one names it in ELSPAIS_TEST_WITHOUT.
    """
    without = _declared_without()
    problems: list[str] = []
    if "mcp" not in without and not _importable("mcp"):
        problems.append("the `mcp` package is not installed, so every test needing it would skip")
    selects_browser = _selects_marker_set(markexpr, frozenset({"browser"})) or (
        _selects_marker_set(markexpr, frozenset({"e2e", "browser"}))
    )
    if selects_browser and "browser" not in without:
        # An xdist worker asks nothing: the controller already asked, and a
        # worker's refusal is reported as an internal error without its text.
        if not os.environ.get("PYTEST_XDIST_WORKER"):
            refusal = _chromium_refusal()
            if refusal is not None:
                problems.append(
                    f"this session selects browser tests and {refusal}, so they would skip or fail"
                )
    if not problems:
        return None
    return (
        "; ".join(problems)
        + f". {_SETUP_HINT}, or name what this session deliberately runs without in "
        + f"{WITHOUT_ENV} (accepted: {', '.join(sorted(OPTIONAL_EXTRAS))})."
    )


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

    # Pin a deterministic changelog-author identity for the whole
    # session via the standard git env vars. Without this, fix/edit/
    # save_mutations consult `gh api user` and `git config user.*`,
    # which vary by developer machine / CI runner — making the
    # "no author configured" failure mode impossible to reproduce
    # locally and breaking CI on machines without git config set.
    # Tests that need to exercise the missing-author path strip these
    # vars explicitly (see tests/e2e/test_e2e_special.py::
    # _make_active_project_no_author).
    os.environ.setdefault("GIT_AUTHOR_NAME", "Test User")
    os.environ.setdefault("GIT_AUTHOR_EMAIL", "test@test.org")

    # Declare this process as the client of every daemon the run
    # starts. Without it the client handle resolves to whatever
    # long-lived session invoked pytest — an editor, an agent session,
    # a login shell — and a daemon bound to that outlives the run by
    # hours while its idle timeout keeps re-arming, because a daemon
    # with a live client does not reap itself. Set here rather than in
    # a fixture so it precedes collection, and exported rather than
    # passed so the elspais subprocesses the e2e helpers spawn declare
    # the same client this process does.
    os.environ["ELSPAIS_CLIENT_PID"] = str(os.getpid())

    config.addinivalue_line(
        "markers",
        "incremental: mark test class for sequential execution with xfail on prior failure",
    )

    # A tier asked for by NAME must run or say why it did not -- and asking for
    # it is what the marker expression SELECTS, never what it mentions. The
    # default `addopts` expression names the browser tier precisely in order to
    # deselect it (`not e2e and not browser and not stress`), so a substring
    # test reads every ordinary run as a request for the tier and refuses it.
    #
    # The browser
    # tier's module opens with `pytest.importorskip("playwright")`, so without
    # the `browser` extra installed the module never imports, pytest records a
    # single skip, and `pytest -m browser` exits 0 having run nothing — a run
    # that looks exactly like a passing one. CUR-1829 declared the extra to
    # answer that, but declaring it installs nothing, so the tier went on
    # reporting green. Asking for the marker explicitly is an unambiguous
    # statement of intent, and an intent the run cannot honour is an error
    # rather than a silence.
    if _selects_marker(config.getoption("markexpr", default="") or "", "browser"):
        try:
            import playwright  # noqa: F401
        except ImportError:
            raise pytest.UsageError(
                "pytest -m browser was requested but playwright is not installed, "
                "so the browser tier would report success having run nothing. "
                'Install it with: pip install -e ".[browser]" && playwright install chromium'
            ) from None

    # A tier must run what it selects or say why it did not. An extra the
    # suite needs and the environment lacks turns tests into skips, and a run
    # that skipped them is indistinguishable from one that passed them.
    refusal = _missing_extras_refusal(config.getoption("markexpr", default="") or "")
    if refusal is not None:
        raise pytest.UsageError(refusal)


# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def pytest_runtest_makereport(item, call):
    """Track failures in incremental test classes."""
    if "incremental" in item.keywords and call.excinfo is not None:
        item.parent._previous_failed = item.name


_IDENTITY_UNSET = object()
_identity_refusal: object = _IDENTITY_UNSET


def _build_identity_refusal() -> str | None:
    """Whether the program e2e and browser tests spawn is this checkout's build.

    Asked once per process, at the first such test, so a session that runs
    none of them never asks.
    """
    global _identity_refusal
    if _identity_refusal is _IDENTITY_UNSET:
        from tests.e2e.helpers import build_identity_refusal

        _identity_refusal = build_identity_refusal()
    return _identity_refusal  # type: ignore[return-value]


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Fail a `serial` test on an xdist worker, and an e2e or browser test
    when the program it would spawn is not this checkout's build; xfail
    after an incremental failure.

    A `serial` test shares state that no worker owns: the live worktree and
    its daemon, the user's home directory, fixed ports. Run beside other tests
    it can corrupt them or be corrupted by them, and the failure looks like a
    flaky test rather than a wrong invocation. `tryfirst` fails it before any
    of its fixtures start. Only a worker sets `PYTEST_XDIST_WORKER`, so a
    session without `-n` never fails here. A worker cannot refuse at
    collection instead: xdist reports that as an internal error and drops the
    message.

    The build check fails the test rather than the session for the same
    reason, and asks where the spawned program's interpreter imports elspais
    from, because two checkouts at one version print the same version.
    """
    if os.environ.get("PYTEST_XDIST_WORKER") and item.get_closest_marker("serial") is not None:
        pytest.fail(
            "this test is marked `serial` and was run by an xdist worker. "
            "Run it without -n, or exclude it with -m 'not serial'; "
            ".githooks/run-e2e-tier runs the e2e tier in both passes.",
            pytrace=False,
        )
    if item.get_closest_marker("e2e") is not None or item.get_closest_marker("browser") is not None:
        refusal = _build_identity_refusal()
        if refusal is not None:
            pytest.fail(f"refusing to run: {refusal}", pytrace=False)
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
    """Return an IdResolver configured for the standard HHT-like pattern.

    Written the way a repository writes it — levels in their own section —
    and validated the way a config file is, so this fixture cannot describe
    a repository the tool would refuse to load.
    """
    from elspais.config.schema import ElspaisConfig
    from elspais.utilities.patterns import build_resolver

    config = {
        "project": {"name": "hht-like", "namespace": "REQ"},
        "levels": {
            "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
            "ops": {"rank": 2, "letter": "o", "implements": ["ops", "prd"]},
            "dev": {"rank": 3, "letter": "d", "implements": ["dev", "ops", "prd"]},
        },
        "id-patterns": {
            "canonical": "{namespace}-{level.letter}{component}",
            "aliases": {"short": "{level.letter}{component}"},
            "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
            "assertions": {"label_style": "uppercase", "max_count": 26},
        },
    }
    ElspaisConfig.model_validate(config)
    return build_resolver(config)


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
        "version": 5,
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
def canonical_config(canonical_federated_graph) -> dict:
    """The config dict already loaded for the canonical hht-like fixture.

    Reuses the config the root repo loaded while building
    ``canonical_federated_graph`` -- does not reload or rebuild it.
    """
    fg = canonical_federated_graph
    return fg._repos[fg._root_repo].config


@pytest.fixture(scope="session")
def canonical_graph(canonical_federated_graph):
    """The primary TraceGraph from the hht-like fixture.

    Built once per session. For read-only assertions against graph state.
    """
    fg = canonical_federated_graph
    return fg._repos[fg._root_repo].graph


@pytest.fixture(scope="class")
def mutable_graph(canonical_federated_graph, canonical_graph):
    """Yield the canonical graph for a mutation chain, undo all on teardown.

    Use with @pytest.mark.incremental test classes. Tests run in order,
    each mutating the graph. After the class completes, all mutations
    are undone, restoring the graph to its pristine state.

    Teardown undoes through the FederatedGraph first: mutations applied via
    federation-level surfaces (e.g. MCP tools) record federated pointers and
    can change the cross-repo ownership map, which only
    ``FederatedGraph.undo_last()`` restores. Undoing such mutations on the
    bare TraceGraph would restore the node index but leave the ownership map
    stale, breaking ``find_by_id`` for every later test in the session.
    """
    fg = canonical_federated_graph
    yield canonical_graph
    # Undo federation-level mutations (restores the ownership map too).
    while len(fg.mutation_log) > 0:
        fg.undo_last()
    # Drain mutations made directly on the TraceGraph (no federated pointer).
    drained_direct = False
    while canonical_graph.mutation_log.last() is not None:
        canonical_graph.undo_last()
        drained_direct = True
    if drained_direct:
        # Direct undos bypass the federation; resync the ownership map.
        fg._rebuild_ownership()
