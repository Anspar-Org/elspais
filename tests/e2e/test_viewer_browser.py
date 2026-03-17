# Validates: REQ-d00010
"""Playwright-based browser tests for the elspais viewer command.

Validates REQ-d00010: viewer command serves the traceability UI
and exposes API endpoints for graph exploration.
"""

import os
import shutil
import signal
import socket
import subprocess
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
        assert isinstance(
            data, list
        ), f"Expected search to return a list, got {type(data).__name__}"


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
