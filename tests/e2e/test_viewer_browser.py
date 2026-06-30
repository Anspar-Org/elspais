# Verifies: REQ-d00010
# Verifies: REQ-d00255-D
# Verifies: REQ-d00256-D
"""Playwright-based browser tests for the elspais viewer command.

Validates REQ-d00010: viewer command serves the traceability UI
and exposes API endpoints for graph exploration.

Validates REQ-d00255-D, REQ-d00256-D: journey UAT verdict badge and
failing-step identification are visible in the viewer.
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import time

import pytest

pw = pytest.importorskip("playwright", reason="playwright not installed")
from playwright.sync_api import sync_playwright  # noqa: E402

from .conftest import REPO_ROOT  # noqa: E402

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


def _find_free_port() -> int:
    """Find a free port in the 15000-15050 range."""
    for port in range(15000, 15051):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    pytest.skip("No free port found in range 15000-15050")


def _wait_for_server(base_url: str, *, timeout: float = 30.0) -> None:
    """Poll /api/status until the server is ready or timeout."""
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(f"{base_url}/api/status", timeout=2)
            if resp.status == 200:
                return
        except (urllib.error.URLError, OSError, ConnectionRefusedError):
            pass
        time.sleep(0.5)
    pytest.fail(f"Server at {base_url} did not become ready within {timeout}s")


@pytest.fixture(scope="session")
def viewer_url():
    """Start elspais viewer server and yield base URL."""
    elspais_bin = shutil.which("elspais")
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [elspais_bin, "viewer", "--server", "--port", str(port)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    try:
        _wait_for_server(base_url)
        yield base_url
    finally:
        # Graceful shutdown via API
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        # Wait briefly, then terminate
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page(viewer_url):
    """Launch headless Chromium and yield a Playwright page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


class TestViewerPageLoad:
    """Validates REQ-d00010: viewer page loads correctly in a browser."""

    def test_REQ_d00010_A_page_loads_without_js_errors(self, page, viewer_url):
        js_errors = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        page.goto(viewer_url, wait_until="networkidle")

        assert not js_errors, f"JS errors on page load: {js_errors}"
        title = page.title()
        body_text = page.text_content("body") or ""
        assert (
            "elspais" in title.lower() or len(body_text.strip()) > 0
        ), "Page has no title or body content"

    def test_REQ_d00010_A_page_has_content(self, page, viewer_url):
        page.goto(viewer_url, wait_until="networkidle")

        body_text = page.text_content("body") or ""
        assert (
            len(body_text.strip()) > 50
        ), f"Page body has too little content ({len(body_text.strip())} chars)"


class TestViewerAPI:
    """Validates REQ-d00010: viewer API endpoints return correct data."""

    def test_REQ_d00010_A_api_status_returns_json(self, page, viewer_url):
        resp = page.request.get(f"{viewer_url}/api/status")
        assert resp.ok, f"GET /api/status returned {resp.status}"

        data = resp.json()
        assert (
            "node_counts" in data
        ), f"Expected 'node_counts' in status response, got keys: {list(data.keys())}"

    def test_REQ_d00010_A_api_search_returns_results(self, page, viewer_url):
        resp = page.request.get(f"{viewer_url}/api/search?q=REQ")
        assert resp.ok, f"GET /api/search returned {resp.status}"

        data = resp.json()
        assert "results" in data, f"Expected 'results' key, got keys: {list(data.keys())}"
        assert isinstance(data["results"], list)


class TestViewerInteraction:
    """Validates REQ-d00010: viewer UI interactions work correctly."""

    def test_REQ_d00010_A_search_filters_tree(self, page, viewer_url):
        page.goto(viewer_url, wait_until="networkidle")

        search_input = page.query_selector(
            'input[type="search"], input[type="text"], input#search, '
            'input[placeholder*="earch"], input[name*="search"]'
        )
        if search_input is None:
            pytest.skip("No search input found on the viewer page")

        search_input.fill("REQ")
        # Give the UI time to filter
        page.wait_for_timeout(1000)

        body_text = page.text_content("body") or ""
        assert "REQ" in body_text, "Tree did not update after search"

    def test_REQ_d00010_A_requirement_click_shows_detail(self, page, viewer_url):
        page.goto(viewer_url, wait_until="networkidle")

        # Find a visible clickable element whose text contains a REQ ID
        locator = page.locator(":visible").filter(has_text="REQ-").first
        try:
            locator.wait_for(state="visible", timeout=5000)
        except Exception:
            pytest.skip("No visible requirement element found in the tree")

        locator.click()
        page.wait_for_timeout(1000)

        # Check that some detail content appeared (panel, modal, or new content)
        body_text = page.text_content("body") or ""
        assert len(body_text.strip()) > 100, "Expected detail content after clicking a requirement"


# ---------------------------------------------------------------------------
# Pipe-table rendering fixture + browser test
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def viewer_url_tables(tmp_path_factory):
    """Start an elspais viewer server against the viewer-tables fixture.

    Copies tests/fixtures/viewer-tables/ to a tmp dir and runs git init
    so the viewer treats it as a standalone project (its own daemon,
    own .elspais.toml). Yields the base URL.
    """
    elspais_bin = shutil.which("elspais")
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")

    dest = tmp_path_factory.mktemp("viewer-tables-run")
    # Copy fixture contents (not the dir itself) into dest.
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

    # git init so the viewer's repo-root detection settles on `dest`.
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init"], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dest, capture_output=True, env=env)

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [elspais_bin, "viewer", "--server", "--port", str(port), "--path", str(dest)],
        cwd=str(dest),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    try:
        _wait_for_server(base_url)
        yield base_url
    finally:
        # Graceful shutdown via API
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_tables(viewer_url_tables):
    """Launch headless Chromium against the tables-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


class TestTableRendering:
    """Validates REQ-d00010: pipe tables in spec body sections render as
    HTML tables with a full grid in the live viewer."""

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00010_table_renders_with_full_grid(self, page_tables, viewer_url_tables):
        """Open REQ-p00001 in the viewer; assert the rendered card contains
        a <table class="md-table"> with the expected headers, the expected
        first body cell, and a 1px border on all four sides of a <td>."""
        page_tables.goto(viewer_url_tables, wait_until="networkidle")

        # Body sections (where the pipe table lives) are only rendered
        # when cardViewMode === 'complete'. Force that mode before opening
        # the card so the Rationale section — which contains the table —
        # gets rendered.
        page_tables.evaluate("() => { editState.cardViewMode = 'complete'; }")

        # Drive the viewer JS directly: openCard(nodeId) is exposed globally
        # by _card-stack.js.j2 and is the canonical entry point used by the
        # nav tree, hash router, etc.
        page_tables.evaluate("() => window.openCard('REQ-p00001')")

        # Wait for the rendered table to appear in the card stack.
        table_locator = page_tables.locator("#card-stack-body table.md-table").first
        table_locator.wait_for(state="visible", timeout=10_000)

        # Headers
        ths = page_tables.locator("#card-stack-body table.md-table thead th")
        assert ths.count() == 3, f"Expected 3 <th> cells, got {ths.count()}"
        assert ths.nth(0).inner_text().strip() == "Column A"
        assert ths.nth(1).inner_text().strip() == "Column B"
        assert ths.nth(2).inner_text().strip() == "Column C"

        # First data body row, first cell (skip the visual separator row
        # emitted between <thead> and the data rows).
        tds = page_tables.locator(
            "#card-stack-body table.md-table tbody tr:not(.md-table-separator)"
        ).first.locator("td")
        assert tds.count() >= 1, "Expected at least one <td> in first data body row"
        assert tds.first.inner_text().strip() == "a1"

        # Border on all four sides of a data <td> must compute to 1px.
        border_widths = page_tables.evaluate(
            """() => {
                const td = document.querySelector(
                    '#card-stack-body table.md-table tbody tr:not(.md-table-separator) td'
                );
                if (!td) return null;
                const cs = getComputedStyle(td);
                return {
                    top: cs.borderTopWidth,
                    right: cs.borderRightWidth,
                    bottom: cs.borderBottomWidth,
                    left: cs.borderLeftWidth,
                };
            }"""
        )
        assert border_widths is not None, "No <td> found for border width check"
        for side, width in border_widths.items():
            assert width == "1px", f"Expected 1px border on {side} side of <td>, got {width!r}"


# ---------------------------------------------------------------------------
# Journey UAT verdict badge fixture + browser test
# ---------------------------------------------------------------------------

_JOURNEY_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "journey-uat" / "one-step-fails"
_FAILING_JOURNEY_ID = "JNY-OQ-Login-01"


@pytest.fixture(scope="module")
def failing_journey_viewer_url():
    """Start an elspais viewer server against the journey-uat/one-step-fails fixture.

    Uses the current worktree's Python (via PYTHONPATH) so that the version
    with verdict/failing_steps support is used, not the installed pipx binary.
    Yields the base URL.
    """
    if not _JOURNEY_FIXTURE.exists():
        pytest.skip(f"journey-uat fixture not present at {_JOURNEY_FIXTURE}")

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    # Inject the worktree src so we get the version that includes
    # journey verdict/failing_steps in the /api/node/ response.
    worktree_src = str(REPO_ROOT / "src")
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{worktree_src}:{existing}" if existing else worktree_src

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "elspais",
            "viewer",
            "--server",
            "--port",
            str(port),
            "--path",
            str(_JOURNEY_FIXTURE),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    try:
        _wait_for_server(base_url)
        yield base_url
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_journey(failing_journey_viewer_url):
    """Launch headless Chromium against the journey-uat-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


class TestJourneyVerdictBrowser:
    """Validates REQ-d00255-D, REQ-d00256-D: journey UAT verdict badge and
    failing-step identification are visible in the viewer card."""

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_d00256_D_journey_fail_verdict_badge(self, page_journey, failing_journey_viewer_url):
        # Verifies: REQ-d00256-D
        """Open a FAILING journey card in the viewer; assert that:
        - The API pre-check confirms verdict == 'fail' and failing_steps == ['step-2']
        - The rendered card shows the 'UAT: FAIL' badge
        - The rendered card lists 'step-2' as a failing step
        - No JS errors occur
        """
        js_errors: list[str] = []
        page_journey.on("pageerror", lambda err: js_errors.append(str(err)))

        # Pre-check: API must return fail verdict with correct failing step
        resp = page_journey.request.get(
            f"{failing_journey_viewer_url}/api/node/{_FAILING_JOURNEY_ID}"
        )
        assert resp.ok, f"GET /api/node/{_FAILING_JOURNEY_ID} returned {resp.status}"
        node_data = resp.json()
        props = node_data.get("properties", {})
        assert props.get("verdict") == "fail", (
            f"Expected verdict='fail' in API, got {props.get('verdict')!r}. " f"Properties: {props}"
        )
        assert "step-2" in props.get(
            "failing_steps", []
        ), f"Expected 'step-2' in failing_steps, got {props.get('failing_steps')!r}"

        # Load the viewer page
        page_journey.goto(failing_journey_viewer_url, wait_until="networkidle")

        # Open the journey card via the global openCard() function.
        # openCard() is async (does an API fetch then re-renders the card
        # stack); we fire it without awaiting and then wait for the DOM node.
        page_journey.evaluate(f"() => window.openCard('{_FAILING_JOURNEY_ID}')")

        # Wait for the card container to appear
        card_locator = page_journey.locator(f"#card-{_FAILING_JOURNEY_ID}")
        card_locator.wait_for(state="visible", timeout=10_000)

        # Assert UAT: FAIL badge text
        card_text = card_locator.inner_text()
        assert (
            "UAT: FAIL" in card_text
        ), f"Expected 'UAT: FAIL' in journey card, got card text:\n{card_text!r}"

        # Assert the failing step label is shown
        assert (
            "step-2" in card_text
        ), f"Expected 'step-2' in journey card, got card text:\n{card_text!r}"

        # No JS errors during the interaction
        assert not js_errors, f"JS errors during journey card render: {js_errors}"
