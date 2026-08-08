# Verifies: REQ-d00010
# Verifies: REQ-d00255-D
# Verifies: REQ-d00256-D
# Verifies: REQ-o00062-O
# Verifies: REQ-d00267-A
# Verifies: REQ-d00267-B
# Verifies: REQ-d00267-C
# Verifies: REQ-d00267-D
# Verifies: REQ-d00267-E
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
from datetime import datetime

import pytest

pw = pytest.importorskip("playwright", reason="playwright not installed")
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402
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
        - The API pre-check confirms verdict == 'fail' and failing_steps == ['2']
        - The rendered card shows the 'UAT: FAIL' badge
        - The rendered card lists step 2 as a failing step
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
        assert "2" in props.get(
            "failing_steps", []
        ), f"Expected '2' in failing_steps, got {props.get('failing_steps')!r}"

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

        # Assert the failing step label is shown (bare step number, "Failing
        # steps: 2" — a substring check on "2" alone would be trivially true)
        assert (
            "Failing steps: 2" in card_text
        ), f"Expected 'Failing steps: 2' in journey card, got card text:\n{card_text!r}"

        # No JS errors during the interaction
        assert not js_errors, f"JS errors during journey card render: {js_errors}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_p00006_A_incoming_links_validated_by(
        self, page_journey, failing_journey_viewer_url
    ):
        # Verifies: REQ-p00006-A
        """Open the requirement card validated by a FAILING journey; assert that:
        - The API payload carries an incoming_links 'Validated by' section whose
          real-path state maps to fail -> red with a 2/3 step-fraction tooltip
        - The card shows an 'Incoming Links' section with a 'Validated by' toggle
        - Clicking the toggle reveals the validating journey link, its red 'fail'
          state badge, and the 2/3 step fraction in the row tooltip
        - No JS errors occur
        """
        req_id = "REQ-d00001"
        js_errors: list[str] = []
        page_journey.on("pageerror", lambda err: js_errors.append(str(err)))

        # Pre-check: API returns a Validated by section with the real-path state
        # mapping (fail -> red) and an accurate step-fraction tooltip.
        resp = page_journey.request.get(f"{failing_journey_viewer_url}/api/node/{req_id}")
        assert resp.ok, f"GET /api/node/{req_id} returned {resp.status}"
        sections = resp.json().get("incoming_links", [])
        by_kind = {s["kind"]: s for s in sections}
        assert "Validated by" in by_kind, f"Expected 'Validated by' section, got {sections!r}"
        vlink = by_kind["Validated by"]["links"][0]
        assert vlink["id"] == "JNY-OQ-Login-01"
        assert vlink["state"]["label"] == "fail", f"Expected fail state, got {vlink['state']!r}"
        assert vlink["state"]["color"] == "red", f"Expected red color, got {vlink['state']!r}"
        assert (
            "2/3 steps verified" in vlink["tooltip"]
        ), f"Expected 2/3 fraction, got {vlink['tooltip']!r}"

        page_journey.goto(failing_journey_viewer_url, wait_until="networkidle")
        page_journey.evaluate(f"() => window.openCard('{req_id}')")
        card_locator = page_journey.locator(f"#card-{req_id}")
        card_locator.wait_for(state="visible", timeout=10_000)

        assert "incoming links" in card_locator.inner_text().lower()

        # Click the "Validated by" toggle and confirm the journey link appears.
        toggle = card_locator.locator("button.incoming-link-toggle", has_text="Validated by")
        toggle.wait_for(state="visible", timeout=10_000)
        toggle.click()
        panel = card_locator.locator(".incoming-link-panel", has_text="JNY-OQ-Login-01")
        panel.wait_for(state="visible", timeout=10_000)
        assert "JNY-OQ-Login-01" in panel.inner_text()

        # The state badge renders red ('fail') in the DOM, not merely present.
        badge = panel.locator(".incoming-state-badge")
        badge.wait_for(state="visible", timeout=10_000)
        assert (
            "fail" in badge.inner_text().lower()
        ), f"Expected 'fail' badge text, got {badge.inner_text()!r}"
        badge_class = badge.get_attribute("class") or ""
        assert "val-red" in badge_class, f"Expected val-red on badge, got class={badge_class!r}"

        # The 2/3 step fraction is surfaced via the row's hover tooltip (title).
        row = panel.locator(".incoming-link-row", has_text="JNY-OQ-Login-01")
        row_title = row.get_attribute("title") or ""
        assert (
            "2/3 steps verified" in row_title
        ), f"Expected 2/3 fraction in tooltip, got {row_title!r}"

        assert not js_errors, f"JS errors during incoming-links render: {js_errors}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_d00256_journey_step_status_on_card(self, page_journey, failing_journey_viewer_url):
        # Verifies: REQ-d00256
        """Open the failing journey card; assert that the Steps section is
        rendered like REQ assertions: plain step text with right-aligned
        Verified/result badges, plus verifying-test rows.

        Checks:
        - A "Steps" section header appears in the card (rendered as "STEPS" by CSS)
        - step-2's result badge carries the 'validation-fail' CSS class
        - step-1 and step-3 result badges do NOT carry 'validation-fail'
        - No JS errors occur
        """
        js_errors: list[str] = []
        page_journey.on("pageerror", lambda err: js_errors.append(str(err)))

        page_journey.goto(failing_journey_viewer_url, wait_until="networkidle")
        page_journey.evaluate(f"() => window.openCard('{_FAILING_JOURNEY_ID}')")

        card_locator = page_journey.locator(f"#card-{_FAILING_JOURNEY_ID}")
        card_locator.wait_for(state="visible", timeout=10_000)

        # "Steps (N)" section must exist as a DOM element (text-transform may
        # render it as "STEPS" in inner_text; use the class selector instead)
        steps_section = card_locator.locator(".journey-steps")
        assert (
            steps_section.count() == 1
        ), "Expected exactly one .journey-steps section in the journey card"

        # Three step rows must appear (one per numbered step in the fixture)
        all_step_rows = card_locator.locator(".journey-step-row").all()
        assert len(all_step_rows) == 3, f"Expected 3 step rows, got {len(all_step_rows)}"

        def row_status_class(row):
            # Steps now render like assertions: a "Verified" badge then a
            # result ("Passed"/"Failed") badge. The result badge is the last
            # .journey-step-badge in the row and carries the validation-* class.
            badge = row.locator(".journey-step-badge").last
            return badge.get_attribute("class") or ""

        step1_cls = row_status_class(all_step_rows[0])
        step2_cls = row_status_class(all_step_rows[1])
        step3_cls = row_status_class(all_step_rows[2])

        assert (
            "validation-fail" in step2_cls
        ), f"step-2 badge should be validation-fail, got {step2_cls!r}"
        assert (
            "validation-fail" not in step1_cls
        ), f"step-1 badge should NOT be validation-fail, got {step1_cls!r}"
        assert (
            "validation-fail" not in step3_cls
        ), f"step-3 badge should NOT be validation-fail, got {step3_cls!r}"

        # Each step must expose at least one verifying-test row
        all_test_rows = card_locator.locator(".journey-step-test-row").all()
        assert (
            len(all_test_rows) >= 3
        ), f"Expected >= 3 verifying-test rows, got {len(all_test_rows)}"

        assert not js_errors, f"JS errors during step-status render: {js_errors}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_d00256_journey_step_badge_toggles_test_panel(
        self, page_journey, failing_journey_viewer_url
    ):
        # Verifies: REQ-d00256
        """Journey step badges must behave like REQ assertion badges: the
        per-step verifying-tests panel is collapsed by default and toggles
        open/closed when a step badge (VER/PASS/FAIL) is clicked, mirroring
        toggleAssertionTests interaction parity for REQ cards.

        Checks:
        - The step-1 test panel is hidden on initial render
        - Clicking a step-1 badge reveals the panel (and the test row text)
        - Clicking the badge again hides the panel
        - No JS errors occur
        """
        js_errors: list[str] = []
        page_journey.on("pageerror", lambda err: js_errors.append(str(err)))

        page_journey.goto(failing_journey_viewer_url, wait_until="networkidle")
        page_journey.evaluate(f"() => window.openCard('{_FAILING_JOURNEY_ID}')")

        card_locator = page_journey.locator(f"#card-{_FAILING_JOURNEY_ID}")
        card_locator.wait_for(state="visible", timeout=10_000)

        first_row = card_locator.locator(".journey-step-row").first
        panel = card_locator.locator(f"#journey-step-tests-{_FAILING_JOURNEY_ID}-1")

        # Panel must exist but be hidden by default (collapsed, REQ-card parity)
        assert panel.count() == 1, "Expected a step-1 test panel in the DOM"
        assert not panel.is_visible(), "Step-1 test panel should be hidden by default"

        # Click the first badge (VER) in the row — should reveal the panel
        badge = first_row.locator(".journey-step-badge").first
        badge.click()
        panel.wait_for(state="visible", timeout=5_000)
        assert (
            "test_step1" in panel.inner_text()
        ), f"Expected verifying test id in revealed panel, got: {panel.inner_text()!r}"
        assert "active" in (
            badge.get_attribute("class") or ""
        ), "Badge should carry 'active' class while its panel is open"

        # Click again — should hide the panel
        badge.click()
        panel.wait_for(state="hidden", timeout=5_000)
        assert "active" not in (
            badge.get_attribute("class") or ""
        ), "Badge should lose 'active' class once its panel is closed"

        assert not js_errors, f"JS errors during step-badge toggle: {js_errors}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_d00256_journey_step_test_row_single_link(
        self, page_journey, failing_journey_viewer_url
    ):
        # Verifies: REQ-d00256
        """Each verifying-test row shows a status chip plus exactly ONE
        clickable source link (calling showSource) -- not the same path text
        rendered twice with no link (the CUR-1568 bug).

        Checks:
        - The revealed step-1 panel contains exactly one <a> link
        - That link's onclick calls showSource(...)
        - The row does not repeat its display text (no duplicated path)
        """
        js_errors: list[str] = []
        page_journey.on("pageerror", lambda err: js_errors.append(str(err)))

        page_journey.goto(failing_journey_viewer_url, wait_until="networkidle")
        page_journey.evaluate(f"() => window.openCard('{_FAILING_JOURNEY_ID}')")

        card_locator = page_journey.locator(f"#card-{_FAILING_JOURNEY_ID}")
        card_locator.wait_for(state="visible", timeout=10_000)

        first_row = card_locator.locator(".journey-step-row").first
        panel = card_locator.locator(f"#journey-step-tests-{_FAILING_JOURNEY_ID}-1")
        badge = first_row.locator(".journey-step-badge").first

        # Badge sizing parity: the step badge must render at the shared
        # assertion-badge size (0.65rem), not the ballooned inherited size
        # from a `font: inherit` override (CUR-1568).
        badge_rem = page_journey.evaluate(
            "(el) => parseFloat(getComputedStyle(el).fontSize) "
            "/ parseFloat(getComputedStyle(document.documentElement).fontSize)",
            badge.element_handle(),
        )
        assert abs(badge_rem - 0.65) < 0.06, (
            f"step badge font-size should be ~0.65rem (matching assertion "
            f"badges), got {badge_rem:.3f}rem"
        )

        badge.click()
        panel.wait_for(state="visible", timeout=5_000)

        test_row = panel.locator(".journey-step-test-row").first
        # Exactly one clickable link per test row (the bug rendered zero links
        # and two duplicated <span> texts instead).
        links = test_row.locator("a")
        assert links.count() == 1, (
            f"Expected exactly one link in the step-test row, got {links.count()}: "
            f"{test_row.inner_html()!r}"
        )
        onclick = links.first.get_attribute("onclick") or ""
        assert (
            "showSource(" in onclick
        ), f"Step-test link must call showSource, got onclick={onclick!r}"

        # The display text must appear only once (no id + duplicate title spans).
        link_text = links.first.inner_text().strip()
        assert link_text, "link should have display text"
        assert test_row.inner_text().count(link_text) == 1, (
            f"Display text {link_text!r} should not be duplicated in row: "
            f"{test_row.inner_text()!r}"
        )

        assert not js_errors, f"JS errors during step-test link render: {js_errors}"


# ─────────────────────────────────────────────────────────────────────────────
# Step-scope RESULT binding + results-file provenance in the viewer
# (junit-step-binding fixture: testcases with file= but NO line=)
# ─────────────────────────────────────────────────────────────────────────────

_STEP_BINDING_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "journey-uat" / "junit-step-binding"
_STEP_BINDING_JOURNEY_ID = "JNY-OQ-Login-01"


@pytest.fixture(scope="module")
def step_binding_viewer_url():
    """Start a viewer server against the journey-uat/junit-step-binding fixture.

    Mirrors ``failing_journey_viewer_url`` (worktree src via PYTHONPATH) but
    serves the fixture whose junit results bind at STEP scope: one test
    source file with per-step Verifies tests, and results.xml testcases that
    carry ``file=`` but no ``line=`` and embed ``<journey>/N`` step ids.
    """
    if not _STEP_BINDING_FIXTURE.exists():
        pytest.skip(f"junit-step-binding fixture not present at {_STEP_BINDING_FIXTURE}")

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

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
            str(_STEP_BINDING_FIXTURE),
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
def page_step_binding(step_binding_viewer_url):
    """Launch headless Chromium against the junit-step-binding viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


class TestJunitStepBindingBrowser:
    """Step-scoped result binding and results-artifact links in the viewer."""

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_step_result_panel_not_conflated_and_links_artifact(
        self, page_step_binding, step_binding_viewer_url
    ):
        # Verifies: REQ-d00256-E
        # Verifies: REQ-d00254-F
        """Open the journey card, toggle step-1's Result panel and assert:

        1. No conflation (end-to-end): step-1's panel holds exactly one
           STEP-scoped result row -- its own (``results.xml:3``) -- and NOT
           the sibling step's uniquely-lined result (``results.xml:4``).
           The two no-step-id/ambiguous testcases legitimately fan out to
           both tests at file scope, so the panel's expected total is 3
           rows (1 step-scoped + 2 file-scoped).
        2. Provenance: every result row's link text points at the results
           ARTIFACT (``results.xml:<line>``), never the test source file.
        """
        js_errors: list[str] = []
        page_step_binding.on("pageerror", lambda err: js_errors.append(str(err)))

        page_step_binding.goto(step_binding_viewer_url, wait_until="networkidle")
        page_step_binding.evaluate(f"() => window.openCard('{_STEP_BINDING_JOURNEY_ID}')")

        card_locator = page_step_binding.locator(f"#card-{_STEP_BINDING_JOURNEY_ID}")
        card_locator.wait_for(state="visible", timeout=10_000)

        step_rows = card_locator.locator(".journey-step-row").all()
        assert len(step_rows) == 2, f"Expected 2 step rows, got {len(step_rows)}"

        # The Result badge is the LAST .journey-step-badge in the row (VER
        # first, then Result); it toggles the RESULTS panel.
        panel = card_locator.locator(f"#journey-step-results-{_STEP_BINDING_JOURNEY_ID}-1")
        assert panel.count() == 1, "Expected a step-1 results panel in the DOM"
        assert not panel.is_visible(), "Step-1 results panel should be hidden by default"

        result_badge = step_rows[0].locator(".journey-step-badge").last
        result_badge.click()
        panel.wait_for(state="visible", timeout=5_000)

        rows = panel.locator(".journey-step-result-row")
        # 1 step-scoped result + 2 file-scope fanout results (no-step-id and
        # ambiguous testcases) = 3. Before the step-scope fix, step 2's
        # per-step result also fanned out here, making it 4.
        assert rows.count() == 3, (
            f"Expected 3 result rows (1 step-scoped + 2 file-scope), got "
            f"{rows.count()}: {panel.inner_text()!r}"
        )

        panel_text = panel.inner_text()
        assert "results.xml:3" in panel_text, (
            f"Step-1 panel must show its own step-scoped result "
            f"(results.xml:3), got: {panel_text!r}"
        )
        assert "results.xml:4" not in panel_text, (
            f"Step-1 panel must NOT show step-2's result (results.xml:4, "
            f"the conflation regression), got: {panel_text!r}"
        )

        # Every row links to the results ARTIFACT, not the test source.
        assert "test_steps.py" not in panel_text, (
            f"Result rows must link the results artifact, not the test "
            f"source file, got: {panel_text!r}"
        )
        for i in range(rows.count()):
            link = rows.nth(i).locator("a")
            assert link.count() == 1, (
                f"Result row {i} should have exactly one link: " f"{rows.nth(i).inner_html()!r}"
            )
            link_text = link.inner_text().strip()
            assert link_text.startswith("results.xml:"), (
                f"Result row {i} link must be 'results.xml:<line>', got " f"{link_text!r}"
            )

        assert not js_errors, f"JS errors during step-results render: {js_errors}"


# ─────────────────────────────────────────────────────────────────────────────
# Optimistic concurrency: edit → 409 → re-read loop (REQ-o00062-O)
# ─────────────────────────────────────────────────────────────────────────────

_CONCURRENCY_REQ_ID = "REQ-p00001"


@pytest.fixture(scope="module")
def concurrency_viewer_url(tmp_path_factory):
    """Start a viewer against a private copy of the viewer-tables fixture.

    A private copy (module scope, own server) because the test mutates the
    server's in-memory graph behind the browser's back — sharing the
    session-scoped tables server would poison its state for other tests.
    The repo is put on a working branch so the edit toggle activates
    without the create-a-branch modal that guards main.
    """
    elspais_bin = shutil.which("elspais")
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")

    dest = tmp_path_factory.mktemp("viewer-concurrency-run")
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

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
    # A non-main working branch: toggleEditMode() activates directly instead
    # of raising the "create a working branch" modal.
    subprocess.run(
        ["git", "checkout", "-b", "concurrent-edit"], cwd=dest, capture_output=True, env=env
    )

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
def page_concurrency(concurrency_viewer_url):
    """Launch headless Chromium against the concurrency-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


class TestBrowserOptimisticConcurrency:
    """Validates REQ-o00062-O: the browser client meets the same version
    preconditions as MCP, receives the identical 409 rejection shape, and
    recovers by re-reading — never by blind retry."""

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_o00062_O_edit_conflict_rereads_instead_of_retrying(
        self, page_concurrency, concurrency_viewer_url
    ):
        # Verifies: REQ-o00062-O
        """Full edit -> 409 -> re-read loop through the real edit UI:

        1. Enter edit mode and change the title once (succeeds; the client
           now holds the returned token for the card).
        2. BEHIND the browser: read a fresh token over HTTP and POST a title
           mutation directly — the browser's held token is now stale.
        3. Blur a second title edit composed against the stale state:
           - the POST is rejected with HTTP 409 / code=version_conflict,
           - the client does NOT blind-retry (exactly one POST, none succeed),
           - the client re-reads the node (GET after the 409) and refreshes
             the card to show the behind-the-back state,
           - the server keeps the behind-the-back title.
        """
        page = page_concurrency
        base = concurrency_viewer_url
        req_id = _CONCURRENCY_REQ_ID

        js_errors: list[str] = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        page.goto(base, wait_until="networkidle")
        page.evaluate(f"() => window.openCard('{req_id}')")
        card = page.locator(f"#card-{req_id}")
        card.wait_for(state="visible", timeout=10_000)

        # Enter edit mode through the real toggle (branch check passes: the
        # fixture repo is on a non-main working branch).
        page.click("#edit-toggle")
        page.wait_for_selector("body.edit-mode", timeout=10_000)
        title_input = card.locator("input.req-card-title-edit")
        title_input.wait_for(state="visible", timeout=10_000)

        # -- Step 1: a first successful edit caches the returned token -----
        title_input.fill("Browser Edit One")
        title_input.blur()
        # Success re-renders the card from server data; the fresh input
        # carries the new title as its value.
        page.wait_for_function(
            f"""() => {{
                const el = document.querySelector(
                    '#card-{req_id} input.req-card-title-edit');
                return el && el.value === 'Browser Edit One';
            }}""",
            timeout=10_000,
        )

        # -- Step 2: invalidate the browser's state behind its back --------
        node = page.request.get(f"{base}/api/node/{req_id}").json()
        fresh_token = node.get("version")
        assert fresh_token, f"/api/node must report a version token, got: {node}"
        agent_resp = page.request.post(
            f"{base}/api/mutate/title",
            data={
                "node_id": req_id,
                "new_title": "Agent Rewrote This",
                "if_version": fresh_token,
            },
        )
        assert agent_resp.status == 200, (
            f"behind-the-back mutation with a fresh token must succeed, "
            f"got {agent_resp.status}: {agent_resp.text()}"
        )
        agent_body = agent_resp.json()
        assert agent_body.get("success") and agent_body.get("version"), agent_body

        # -- Step 3: submit the stale browser edit and watch the recovery --
        events: list[dict] = []

        def _record(response):
            events.append(
                {
                    "method": response.request.method,
                    "url": response.url,
                    "status": response.status,
                }
            )

        page.on("response", _record)

        stale_input = card.locator("input.req-card-title-edit")
        stale_input.fill("Browser Edit Two")
        stale_input.blur()

        # The client announces the conflict rather than pretending success.
        page.locator(".toast.error", has_text="Someone else changed this").wait_for(
            state="visible", timeout=10_000
        )

        # The card refreshes to the CURRENT state (the agent's title), which
        # can only come from a re-read — the browser never typed this value.
        page.wait_for_function(
            f"""() => {{
                const el = document.querySelector(
                    '#card-{req_id} input.req-card-title-edit');
                return el && el.value === 'Agent Rewrote This';
            }}""",
            timeout=10_000,
        )

        # Network-level proof of the protocol:
        mutate_posts = [
            (i, e)
            for i, e in enumerate(events)
            if e["method"] == "POST" and e["url"].endswith("/api/mutate/title")
        ]
        assert (
            len(mutate_posts) == 1
        ), f"expected exactly ONE title POST (no blind retry), got: {mutate_posts}"
        conflict_index, conflict_event = mutate_posts[0]
        assert (
            conflict_event["status"] == 409
        ), f"stale edit must be rejected with HTTP 409, got {conflict_event}"
        rereads = [
            i
            for i, e in enumerate(events)
            if e["method"] == "GET" and f"/api/node/{req_id}" in e["url"]
        ]
        assert any(i > conflict_index for i in rereads), (
            f"expected a re-read GET of /api/node/{req_id} AFTER the 409; " f"events: {events}"
        )

        # Server state: the behind-the-back write survived; the stale browser
        # edit never landed.
        final = page.request.get(f"{base}/api/node/{req_id}").json()
        assert (
            final.get("title") == "Agent Rewrote This"
        ), f"server must keep the concurrent writer's state, got: {final.get('title')!r}"

        assert not js_errors, f"JS errors during conflict recovery: {js_errors}"


# ─────────────────────────────────────────────────────────────────────────────
# Pending-work indicator truth: reported / unknown (REQ-d00267-A/B/C)
# ─────────────────────────────────────────────────────────────────────────────

_BADGE_REQ_ID = "REQ-p00001"


@pytest.fixture(scope="module")
def badge_viewer_url(tmp_path_factory):
    """Start a viewer against a private copy of the viewer-tables fixture.

    A private copy (module scope, own server, own port) because these tests
    push real pending mutations into the server's in-memory graph — sharing
    the session-scoped tables server would leave unsaved work behind for
    every other test. The repo is put on a non-main working branch so the
    edit surfaces are usable without the create-a-branch modal.
    """
    elspais_bin = shutil.which("elspais")
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")

    dest = tmp_path_factory.mktemp("viewer-badge-run")
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

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
    subprocess.run(["git", "checkout", "-b", "badge-truth"], cwd=dest, capture_output=True, env=env)

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
def page_badge(badge_viewer_url):
    """Launch headless Chromium against the badge-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


def _badge_state(page) -> dict:
    """Snapshot everything the pending-work indicator presents."""
    return page.evaluate(
        """() => {
            const b = document.getElementById('unsaved-badge');
            return {
                text: b ? b.textContent.trim() : null,
                classes: b ? Array.from(b.classList) : null,
                title: b ? (b.getAttribute('title') || '') : null,
                count: editState.mutationCount,
                count_type: typeof editState.mutationCount,
                tip: editState.lastSeenTip,
            };
        }"""
    )


def _refresh_dirty(page) -> None:
    """Drive the count refresh explicitly instead of waiting on the 30s poll."""
    page.evaluate("() => refreshDirtyCount()")


def _create_pending_mutation(page, base: str, new_title: str) -> int:
    """Make real server-side pending work; return the server's pending count."""
    node = page.request.get(f"{base}/api/node/{_BADGE_REQ_ID}").json()
    token = node.get("version")
    assert token, f"/api/node must report a version token, got: {node}"
    resp = page.request.post(
        f"{base}/api/mutate/title",
        data={"node_id": _BADGE_REQ_ID, "new_title": new_title, "if_version": token},
    )
    assert resp.status == 200, f"pending-work setup mutation failed: {resp.status} {resp.text()}"
    dirty = page.request.get(f"{base}/api/dirty").json()
    count = dirty.get("mutation_count")
    assert isinstance(count, int) and count > 0, f"server must report pending work, got: {dirty}"
    return count


def _go_unknown(page) -> None:
    """Make /api/dirty unreachable and refresh, leaving the count unknown."""
    page.route("**/api/dirty", lambda route: route.abort())
    _refresh_dirty(page)


def _close_observing_beforeunload(page, timeout: float = 5.0) -> list[str]:
    """Close the page for real and report any beforeunload dialog it raised.

    Chromium suppresses beforeunload dialogs on pages the user has never
    interacted with, so a genuine click comes first. The wait is on the
    BROWSER CONTEXT, not the page: Chromium delivers the dialog after the
    page target is already gone, so a page-scoped waiter would be torn down
    before it ever saw it. A dialog left unanswered would hang the close, so
    it is accepted as soon as it is observed.
    """
    context = page.context
    dialogs: list[str] = []

    page.click(".header-title")  # real user gesture
    try:
        with context.expect_event("dialog", timeout=timeout * 1000) as info:
            page.close(run_before_unload=True)
        dialog = info.value
        dialogs.append(dialog.type)
        try:
            dialog.accept()
        except Exception:
            # The target can already be gone by the time we answer; the
            # observation is what the test cares about.
            pass
    except PlaywrightTimeoutError:
        pass

    if not page.is_closed():
        page.close()
    return dialogs


class TestBrowserPendingWorkIndicatorTruth:
    """Validates REQ-d00267-A, REQ-d00267-B, REQ-d00267-C: the viewer's
    pending-change indicator is server-truth with three states — nothing
    pending, work pending, and count unknown. A failed count fetch must
    present as unknown rather than collapsing to the last count or to zero,
    a later successful fetch must restore the reported count, and the
    navigation warning must arm only on a server-reported pending count."""

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_A_badge_hidden_when_server_reports_zero(self, page_badge, badge_viewer_url):
        # Verifies: REQ-d00267-A
        """Control: a live server reporting nothing pending hides the badge."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        dirty = page.request.get(f"{badge_viewer_url}/api/dirty").json()
        assert dirty.get("mutation_count") == 0, (
            f"this test must run before any mutation test in the module; "
            f"server already reports pending work: {dirty}"
        )

        _refresh_dirty(page)
        state = _badge_state(page)
        assert (
            "hidden" in state["classes"]
        ), f"server reported 0 pending: badge must be hidden, got classes {state['classes']}"
        assert state["count"] == 0, f"editState.mutationCount must be 0, got {state['count']!r}"
        assert (
            state["count_type"] == "number"
        ), f"a reported count is a number, got type {state['count_type']!r}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_A_badge_reads_unknown_when_server_unreachable(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-A
        """An unreachable count endpoint presents as unknown, not as the last
        count and not as zero — the two collapses REQ-d00267-A forbids."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        pending = _create_pending_mutation(page, badge_viewer_url, "Badge Pending One")
        _refresh_dirty(page)
        reported = _badge_state(page)
        assert reported["text"] == str(
            pending
        ), f"precondition: badge must show the server's count {pending}, got {reported['text']!r}"
        assert "hidden" not in reported["classes"], reported["classes"]

        _go_unknown(page)
        state = _badge_state(page)

        assert state["text"] == "?", (
            f"unknown count must be presented as '?', got {state['text']!r} "
            f"(classes {state['classes']})"
        )
        assert state["text"] != str(pending), (
            f"unknown count must NOT keep presenting the last count "
            f"{pending} as though it were current"
        )
        assert state["text"] != "0", "unknown count must NOT be presented as zero"
        assert "unknown" in state["classes"], (
            f"badge must carry the 'unknown' class while the count is "
            f"unknown, got {state['classes']}"
        )
        assert "hidden" not in state["classes"], (
            f"an unknown count is not 'nothing pending' — the badge must stay "
            f"visible, got {state['classes']}"
        )
        assert state["title"], "unknown badge must carry an explanatory title attribute"
        assert (
            "unreachable" in state["title"].lower()
        ), f"unknown badge title must name the unreachable server, got {state['title']!r}"
        assert state["count"] is None, (
            f"editState.mutationCount must be null (unknown), got "
            f"{state['count']!r} (type {state['count_type']!r})"
        )

        page.unroute("**/api/dirty")

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_A_failed_fetch_does_not_advance_last_seen_tip(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-A
        """Regression guard: a failed count fetch has seen no history, so it
        must not mark the mutation-log tip as seen (which would suppress the
        other-writer banner on a tip the page never actually observed)."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Pending Tip")
        _refresh_dirty(page)
        before = _badge_state(page)["tip"]
        assert before, f"precondition: a successful refresh must record a tip, got {before!r}"

        _go_unknown(page)
        after = _badge_state(page)["tip"]
        assert (
            after == before
        ), f"a failed /api/dirty fetch must leave lastSeenTip untouched: {before!r} -> {after!r}"

        page.unroute("**/api/dirty")

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_B_badge_returns_to_server_truth_after_transient_failure(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-B
        """A transient blip must not silently drop the pending work: once the
        server answers again, the unknown presentation is replaced by the
        reported count."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        pending = _create_pending_mutation(page, badge_viewer_url, "Badge Pending Two")
        _refresh_dirty(page)
        assert _badge_state(page)["text"] == str(pending)

        _go_unknown(page)
        unknown = _badge_state(page)
        assert unknown["text"] == "?" and "unknown" in unknown["classes"], (
            f"precondition: the badge must first be in the unknown state, got "
            f"text {unknown['text']!r} classes {unknown['classes']}"
        )

        page.unroute("**/api/dirty")
        _refresh_dirty(page)
        state = _badge_state(page)

        assert state["text"] == str(pending), (
            f"after the server answers again the badge must show the reported "
            f"count {pending}, got {state['text']!r}"
        )
        assert (
            "unknown" not in state["classes"]
        ), f"the unknown presentation must be replaced, got {state['classes']}"
        assert "hidden" not in state["classes"], state["classes"]
        assert (
            state["count"] == pending
        ), f"editState.mutationCount must be the reported count {pending}, got {state['count']!r}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_C_navigation_warned_while_server_reports_pending(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-C
        """Non-vacuity control for the unknown case: with a server-REPORTED
        pending count the navigation warning is armed and a real close raises
        the beforeunload dialog."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        pending = _create_pending_mutation(page, badge_viewer_url, "Badge Pending Warn")
        _refresh_dirty(page)
        state = _badge_state(page)
        assert state["count"] == pending and state["count_type"] == "number", state

        dialogs = _close_observing_beforeunload(page)
        assert dialogs, (
            "with the server reporting pending changes, closing the page must "
            "raise a beforeunload dialog; none was observed"
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_C_navigation_not_obstructed_while_count_unknown(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-C
        """While the count is unknown the viewer must not obstruct navigation:
        it cannot verify the claim, and blocking on it can strand an operator."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Pending Unknown Nav")
        _refresh_dirty(page)

        _go_unknown(page)
        state = _badge_state(page)
        assert state["count"] is None, (
            f"precondition: the count must be unknown before testing "
            f"navigation, got {state['count']!r}"
        )

        dialogs = _close_observing_beforeunload(page)
        assert not dialogs, (
            f"navigation must not be obstructed while the pending count is "
            f"unknown, but a beforeunload dialog was raised: {dialogs}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Unload decision observability (REQ-d00267-D)
# ─────────────────────────────────────────────────────────────────────────────

_UNLOAD_STATE_KEYS = {
    "willWarnOnClose",
    "pendingCount",
    "countKnown",
    "countEstablishedAt",
    "countSource",
    "lastSeenTip",
}


def _has_unload_state(page) -> bool:
    """Is the on-demand inspection hook present at all?"""
    return page.evaluate("() => typeof window.unloadWarningState === 'function'")


def _unload_state(page) -> dict:
    """Read the inspection hook, failing with a diagnosis if it is absent.

    Going through a helper keeps every downstream test's failure a plain
    assertion about missing behaviour rather than a raw ReferenceError out of
    page.evaluate, which reads like a broken harness.
    """
    assert _has_unload_state(page), (
        "window.unloadWarningState() is not defined: the state behind the "
        "navigation warning is not inspectable from the console"
    )
    return page.evaluate("() => window.unloadWarningState()")


def _server_dirty(page, base: str) -> dict:
    """Ask the server directly what it considers pending."""
    return page.request.get(f"{base}/api/dirty").json()


def _revert_to_zero(page, base: str) -> None:
    """Discard every pending mutation so the server truthfully reports zero.

    The badge fixture's server is module-scoped and earlier tests leave real
    pending work in it, so "nothing pending" cannot be assumed — it has to be
    established. /api/revert rebuilds the graph from disk, which empties the
    mutation log outright; it is guarded on the mutation-log tip, so the
    current tip is read from /api/dirty and echoed back ("" when the log is
    already empty).
    """
    tip = _server_dirty(page, base).get("tip") or ""
    resp = page.request.post(f"{base}/api/revert", data={"if_tip_mutation_id": tip})
    assert resp.status == 200, f"revert setup failed: {resp.status} {resp.text()}"
    after = _server_dirty(page, base)
    assert after.get("mutation_count") == 0, f"revert must leave nothing pending, got: {after}"


def _console_sink(page) -> list[str]:
    """Collect console message text emitted by the page from now on."""
    messages: list[str] = []
    page.on("console", lambda msg: messages.append(msg.text))
    return messages


# The armed branch's own phrasing. The not-armed branch's known-zero wording
# ("no pending changes") deliberately does not contain the parenthesised form,
# so this one literal discriminates against BOTH not-armed variants.
_ARMED_PHRASE = "pending change(s)"


def _beforeunload_messages(messages: list[str]) -> list[str]:
    """The subset of console output reporting the navigation decision."""
    return [m for m in messages if "[elspais]" in m and "beforeunload" in m.lower()]


class TestBrowserUnloadDecisionObservable:
    """Validates REQ-d00267-D: the state deciding whether the viewer warns
    before navigation is inspectable on demand — the count, whether the count
    is known, and when it was last established — and the decision actually
    reached is reported at the moment navigation is attempted.

    This is instrumentation for a field report of a tab that would not close,
    whose cause was never observed. A busy main thread and a beforeunload
    dialog that never rendered look identical from outside; the arming state
    and the emitted decision are what tell them apart, so both are asserted
    against the REAL observed dialog behaviour rather than on their own.
    """

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_D_unload_state_is_inspectable(self, page_badge, badge_viewer_url):
        # Verifies: REQ-d00267-D
        """The inspection hook exists as a global function and reports the
        whole decision input: count, known-ness, when established, provenance,
        the seen tip, and the arming decision itself."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        assert _has_unload_state(page), (
            "an operator with nothing but the browser console must be able to "
            "call window.unloadWarningState(); it is not a function"
        )

        state = page.evaluate("() => window.unloadWarningState()")
        assert isinstance(state, dict), f"unloadWarningState() must return an object, got {state!r}"
        missing = _UNLOAD_STATE_KEYS - set(state)
        assert not missing, (
            f"unloadWarningState() must report the full decision input; "
            f"missing keys {sorted(missing)} (got {sorted(state)})"
        )
        assert isinstance(
            state["willWarnOnClose"], bool
        ), f"willWarnOnClose must be a boolean decision, got {state['willWarnOnClose']!r}"
        assert isinstance(
            state["countKnown"], bool
        ), f"countKnown must be a boolean, got {state['countKnown']!r}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_D_state_and_dialog_agree_when_work_pending(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-D
        """With a server-reported pending count, the reported decision says it
        will warn AND a real close raises the dialog. Asserting both in one
        test is the point: a reported value that re-derives the condition
        instead of reflecting the handler could otherwise say 'warn' while the
        page silently lets you leave."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        pending = _create_pending_mutation(page, badge_viewer_url, "Badge Decision Pending")
        _refresh_dirty(page)

        state = _unload_state(page)
        assert state["willWarnOnClose"] is True, (
            f"the server reports {pending} pending: the reported decision must "
            f"be to warn, got {state!r}"
        )
        assert (
            state["pendingCount"] == pending
        ), f"pendingCount must be the server's count {pending}, got {state['pendingCount']!r}"
        assert (
            state["countKnown"] is True
        ), f"a server-reported count is known, got countKnown={state['countKnown']!r}"
        assert (
            state["countSource"] == "server"
        ), f"the count came from the server, got countSource={state['countSource']!r}"
        assert state["countEstablishedAt"], (
            "the moment the count was established must be reported, got "
            f"{state['countEstablishedAt']!r}"
        )
        # Parsed, not merely non-empty: an operator reading this after the
        # fact needs to know how stale the count is.
        established = datetime.fromisoformat(
            str(state["countEstablishedAt"]).replace("Z", "+00:00")
        )
        assert established.year >= 2020, f"implausible countEstablishedAt: {established!r}"

        dialogs = _close_observing_beforeunload(page)
        assert dialogs, (
            f"unloadWarningState() reported willWarnOnClose=True with "
            f"{pending} pending, but closing the page raised no beforeunload "
            f"dialog — the reported decision does not match the handler"
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_D_state_and_dialog_agree_when_count_unknown(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-D
        """With the count endpoint unreachable the reported decision says it
        will NOT warn, names the count as unknown and unreachable-sourced, and
        a real close is in fact unobstructed."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Decision Unknown")
        _refresh_dirty(page)
        assert _unload_state(page)["countKnown"] is True, "precondition: count must start known"

        _go_unknown(page)
        state = _unload_state(page)

        assert state["willWarnOnClose"] is False, (
            f"an unverifiable claim must not arm the warning; reported " f"decision was {state!r}"
        )
        assert (
            state["pendingCount"] is None
        ), f"an unknown count must be reported as null, got {state['pendingCount']!r}"
        assert (
            state["countKnown"] is False
        ), f"countKnown must be false while unreachable, got {state['countKnown']!r}"
        assert state["countSource"] == "unreachable", (
            f"the state must name WHY the count is what it is, expected "
            f"'unreachable', got {state['countSource']!r}"
        )

        dialogs = _close_observing_beforeunload(page)
        assert not dialogs, (
            f"unloadWarningState() reported willWarnOnClose=False, but closing "
            f"the page raised a beforeunload dialog: {dialogs}"
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_D_handler_disarmed_when_server_dead_and_nothing_pending(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-D
        """The discriminating case for the field report: the server reported
        ZERO pending and then went away. This is the state an operator was in
        when they could not close the tab, so the reported decision must show
        the handler disarmed in BOTH sub-states — while the page still holds
        the reported zero, and after the failed poll turns it unknown — and a
        real close must go through.

        Nothing-pending is established by reverting, not assumed: the badge
        fixture's server is module-scoped and earlier tests in this module
        leave real pending work in it.
        """
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _revert_to_zero(page, badge_viewer_url)
        _refresh_dirty(page)

        reported_zero = _unload_state(page)
        assert reported_zero["pendingCount"] == 0, (
            f"precondition: the server reported nothing pending, so the page "
            f"must hold 0, got {reported_zero['pendingCount']!r}"
        )
        assert reported_zero["countKnown"] is True, reported_zero
        assert reported_zero["countSource"] == "server", reported_zero
        assert reported_zero["willWarnOnClose"] is False, (
            f"a server-reported zero must leave the warning disarmed, got " f"{reported_zero!r}"
        )

        # The server now goes away. Nothing pending was ever reported, so the
        # failed poll must not resurrect a warning out of thin air.
        _go_unknown(page)
        dead = _unload_state(page)
        assert dead["countKnown"] is False, dead
        assert dead["willWarnOnClose"] is False, (
            f"server dead with nothing pending must stay disarmed — this is "
            f"the state in which a tab reportedly would not close; got {dead!r}"
        )

        dialogs = _close_observing_beforeunload(page)
        assert not dialogs, (
            f"with nothing pending and the server unreachable the page must "
            f"close unobstructed, but a beforeunload dialog was raised: {dialogs}"
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_D_decision_is_reported_at_navigation_when_armed(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-D
        """Attempting navigation with work pending emits a console record of
        the decision reached, naming the pending count. Without this an
        operator cannot tell 'the handler ran and armed' from 'the handler
        never ran' after the fact."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        pending = _create_pending_mutation(page, badge_viewer_url, "Badge Decision Console Armed")
        _refresh_dirty(page)
        assert _unload_state(page)["willWarnOnClose"] is True, "precondition: must be armed"

        messages = _console_sink(page)
        dialogs = _close_observing_beforeunload(page)
        assert dialogs, "precondition: the armed case must actually raise the dialog"

        reported = _beforeunload_messages(messages)
        assert reported, (
            f"attempting navigation must emit an '[elspais]' beforeunload "
            f"decision record; console carried only {messages!r}"
        )
        assert any(str(pending) in m for m in reported), (
            f"the armed decision record must name the pending count "
            f"{pending} it armed on, got {reported!r}"
        )
        assert any(_ARMED_PHRASE in m for m in reported), (
            f"the armed record must carry its own phrasing {_ARMED_PHRASE!r} "
            f"so it is distinguishable from the not-armed one: {reported!r}"
        )
        assert not any(
            "not warning" in m for m in reported
        ), f"the armed record must not read as a not-warning decision: {reported!r}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_D_decision_is_reported_at_navigation_when_not_armed(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-D
        """Attempting navigation with the count unknown emits its own console
        record of the decision, distinguishable from the armed one: the
        handler ran and chose NOT to obstruct. A silent not-armed path would
        be indistinguishable from a handler that never fired at all."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Decision Console Quiet")
        _refresh_dirty(page)
        _go_unknown(page)
        assert _unload_state(page)["willWarnOnClose"] is False, "precondition: must be disarmed"

        messages = _console_sink(page)
        dialogs = _close_observing_beforeunload(page)
        assert not dialogs, "precondition: the unknown case must not raise a dialog"

        reported = _beforeunload_messages(messages)
        assert reported, (
            f"a not-armed navigation attempt must still report the decision "
            f"it reached; console carried only {messages!r}"
        )
        # Discriminate on the two branches' own phrasing. An earlier version of
        # this test asserted the armed count's digits were absent, which the
        # not-armed line can never contain — it constrained nothing.
        assert all("not warning" in m for m in reported), (
            f"the not-armed record must say so in words, so an operator "
            f"reading the console can tell which branch ran: {reported!r}"
        )
        assert not any(_ARMED_PHRASE in m for m in reported), (
            f"the not-armed record must not carry the armed record's "
            f"pending-count phrasing {_ARMED_PHRASE!r}: {reported!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pending-work count under PARTIAL failure (REQ-d00267-A/B)
# ─────────────────────────────────────────────────────────────────────────────


def _has_poll(page) -> bool:
    """Is the 30s poll reachable as a named function a test can drive?"""
    return page.evaluate("() => typeof window.pollForExternalChanges === 'function'")


def _poll_once(page) -> None:
    """Run one poll cycle and wait for its count probe to actually land.

    The poll is not required to hand back a promise, so completion is observed
    rather than awaited: `dirtyCountAt` is cleared first and the wait is for
    something to set it again. Both count outcomes stamp it — a server answer
    and a failed read alike — so this is a true "a probe happened" signal, not
    a "the probe succeeded" one. That is what makes an absence assertion
    (`the badge never went to ?`) strict instead of racy.
    """
    assert _has_poll(page), (
        "window.pollForExternalChanges() is not defined: the 30s poll is not a "
        "named function, so the page's only count heartbeat cannot be driven "
        "or observed"
    )
    page.evaluate("() => { editState.dirtyCountAt = null; }")
    page.evaluate("() => pollForExternalChanges()")
    _wait_for_js(
        page,
        "() => editState.dirtyCountAt !== null",
        "a poll cycle must probe the pending count, but nothing re-established it",
    )


def _wait_for_js(page, expression: str, message: str, timeout: float = 5.0) -> None:
    """Wait for a page-side condition, failing as an assertion rather than a
    raw Playwright timeout so the report reads as missing behaviour."""
    try:
        page.wait_for_function(expression, timeout=timeout * 1000)
    except PlaywrightTimeoutError:
        raise AssertionError(f"{message} (waiting on: {expression})") from None


def _dom_present(page, selector: str) -> bool:
    return page.evaluate(f"() => document.querySelector({selector!r}) !== null")


def _error_modal_text(page) -> str:
    return page.evaluate(
        """() => {
            const el = document.getElementById('error-modal-overlay');
            return el ? el.textContent : '';
        }"""
    )


class TestBrowserPendingWorkUnderPartialFailure:
    """Validates REQ-d00267-A, REQ-d00267-B: the pending-change count is
    established by, and only by, the count endpoint — on a heartbeat, and
    honestly when the answer is unusable.

    Partial failure is the interesting case. One endpoint going down while
    another stays healthy must not let the healthy one's silence, or the
    broken one's noise, speak for the count: a failure elsewhere that pins the
    badge to unknown disarms the navigation warning forever, and a malformed
    answer read as zero hides real work.
    """

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_A_poll_cycle_drives_the_count(self, page_badge, badge_viewer_url):
        # Verifies: REQ-d00267-A
        """The poll is the page's only count heartbeat: an idle page whose
        server dies must notice without any mutation or reload. Driving the
        poll alone — never refreshDirtyCount() directly — must turn the count
        unknown, and must recover it once the server answers again."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Poll Heartbeat")
        _refresh_dirty(page)
        assert _badge_state(page)["count_type"] == "number", "precondition: count must start known"

        # Only the count endpoint dies; check-freshness stays healthy, so an
        # unknown count here can only have come from the count probe itself.
        page.route("**/api/dirty", lambda route: route.abort())
        _poll_once(page)
        _wait_for_js(
            page,
            "() => editState.mutationCount === null",
            "a poll cycle with the count endpoint down must mark the count "
            "unknown; the page went on presenting a count it could not confirm",
        )
        assert _badge_state(page)["text"] == "?", _badge_state(page)

        page.unroute("**/api/dirty")
        _poll_once(page)
        _wait_for_js(
            page,
            "() => typeof editState.mutationCount === 'number'",
            "a poll cycle after the server recovered must re-establish the count",
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_A_freshness_failure_does_not_speak_for_the_count(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-A
        """Regression guard for the stuck-at-'?' bug. Only /api/dirty outcomes
        may establish the count. A failing /api/check-freshness alongside a
        perfectly healthy /api/dirty used to mark the count unknown, which
        pinned the badge at '?' and left the navigation warning disarmed for
        the rest of the session even though the server was answering."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        pending = _create_pending_mutation(page, badge_viewer_url, "Badge Freshness Down")
        _refresh_dirty(page)
        assert _badge_state(page)["text"] == str(pending), "precondition: badge shows the count"

        page.route("**/api/check-freshness", lambda route: route.abort())

        for cycle in range(3):
            _poll_once(page)
            state = _badge_state(page)
            assert state["text"] != "?", (
                f"cycle {cycle + 1}: /api/dirty is healthy, so the count is "
                f"knowable; a check-freshness failure must not present it as "
                f"unknown (badge {state['text']!r}, classes {state['classes']})"
            )
            assert "unknown" not in state["classes"], f"cycle {cycle + 1}: {state['classes']}"
            assert state["count"] == pending, (
                f"cycle {cycle + 1}: the badge must keep showing the server's "
                f"real count {pending}, got {state['count']!r}"
            )
            assert _unload_state(page)["willWarnOnClose"] is True, (
                f"cycle {cycle + 1}: work is pending and the count endpoint is "
                f"healthy, so the navigation warning must stay armed"
            )

        page.unroute("**/api/check-freshness")

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_A_poll_does_not_adopt_another_writers_tip(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-A
        """The poll's count probe must not record the change history as seen.
        Adopting the tip every 30s would mark another writer's mutations as
        already-looked-at and the 'Another writer changed the graph' banner
        could never raise again — the poll would silently destroy the very
        warning it exists to give."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Tip Baseline")
        _refresh_dirty(page)
        seen_before = _badge_state(page)["tip"]
        assert seen_before, f"precondition: a baseline tip must be recorded, got {seen_before!r}"

        # Another writer moves the graph behind this page's back.
        _create_pending_mutation(page, badge_viewer_url, "Badge Tip Other Writer")
        other_tip = _server_dirty(page, badge_viewer_url).get("tip")
        assert other_tip and other_tip != seen_before, (
            f"precondition: the other writer must have advanced the tip "
            f"{seen_before!r} -> {other_tip!r}"
        )

        _poll_once(page)

        assert _badge_state(page)["tip"] == seen_before, (
            f"the poll must not record history it never showed the operator as "
            f"seen: lastSeenTip moved {seen_before!r} -> "
            f"{_badge_state(page)['tip']!r}"
        )
        _wait_for_js(
            page,
            "() => { const b = document.getElementById('stale-banner');"
            " return b && !b.classList.contains('hidden'); }",
            "another writer moved the tip, so the poll must raise the "
            "'Another writer changed the graph' banner",
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_A_failed_mutation_reprobes_and_marks_unknown_if_dead(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-A
        """A mutation POST that comes back with nothing leaves the page's idea
        of the count unfounded — the request may or may not have landed. The
        count must be re-established, and with the count endpoint also down
        that re-establishment is 'unknown', not the stale number."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Failed Mutation Dead")
        _refresh_dirty(page)
        assert _badge_state(page)["count_type"] == "number", "precondition: count must start known"

        # /api/node stays reachable so the guard token still resolves and the
        # POST itself is what fails.
        page.route("**/api/mutate/title", lambda route: route.abort())
        page.route("**/api/dirty", lambda route: route.abort())
        _attempt_title_mutation(page, "Badge Failed Mutation Dead 2")

        _wait_for_js(
            page,
            "() => editState.mutationCount === null",
            "a mutation POST that failed against an unreachable server must "
            "leave the count unknown, not standing at its stale value",
        )

        page.unroute("**/api/mutate/title")
        page.unroute("**/api/dirty")

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_B_failed_mutation_reprobes_and_recovers_if_alive(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-B
        """The other half of the same path: a rejected request is not a dead
        server. With the count endpoint healthy the re-probe must reach it and
        restore a real number, rather than assuming death.

        The count is deliberately forced to unknown first. Asserting only that
        the count is right afterwards would pass even if nothing re-probed at
        all — recovery from unknown is what proves the probe ran.
        """
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _refresh_dirty(page)
        page.evaluate("() => markDirtyCountUnknown()")
        assert _badge_state(page)["count"] is None, "precondition: count must be unknown"

        page.route("**/api/mutate/title", lambda route: route.abort())
        _attempt_title_mutation(page, "Badge Failed Mutation Alive")

        _wait_for_js(
            page,
            "() => typeof editState.mutationCount === 'number'",
            "a failed mutation POST must re-probe the count; the count "
            "endpoint was healthy, so the count must be known again rather "
            "than assumed unknowable",
        )
        server = _server_dirty(page, badge_viewer_url).get("mutation_count")
        assert _badge_state(page)["count"] == server, (
            f"the re-probe must adopt the server's real count {server}, got "
            f"{_badge_state(page)['count']!r}"
        )

        page.unroute("**/api/mutate/title")

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_A_malformed_count_response_is_unknown_not_zero(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-A
        """A 200 carrying no usable count is an answer the page cannot read.
        Coercing it to zero would hide pending work behind a hidden badge and
        a disarmed warning, which is exactly the collapse REQ-d00267-A
        forbids — the response reached us, but the count did not."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Malformed Dirty")
        _refresh_dirty(page)
        assert _badge_state(page)["count_type"] == "number", "precondition: count must start known"

        page.route(
            "**/api/dirty",
            lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
        )
        _refresh_dirty(page)
        state = _badge_state(page)

        assert state["count"] is None, (
            f"a response without a numeric count is unreadable, not zero; "
            f"editState.mutationCount was {state['count']!r}"
        )
        assert state["text"] == "?", f"badge must read unknown, got {state['text']!r}"
        assert "hidden" not in state["classes"], (
            f"an unreadable count is not 'nothing pending' — the badge must "
            f"stay visible, got {state['classes']}"
        )
        assert _unload_state(page)["countKnown"] is False, _unload_state(page)

        page.unroute("**/api/dirty")


# ─────────────────────────────────────────────────────────────────────────────
# Destructive operations under an unknown count (REQ-d00267-E)
# ─────────────────────────────────────────────────────────────────────────────


def _attempt_title_mutation(page, new_title: str) -> None:
    """Drive the page's own mutate() path for the badge fixture's requirement.

    mutate() is the unit under test here, and it is a global, so it is invoked
    directly rather than through a card's edit UI: opening a card and typing
    would exercise a great deal of unrelated machinery for no extra coverage
    of the failed-POST branch, and would be far less deterministic.
    """
    page.evaluate(
        """async (payload) => {
            await mutate('/api/mutate/title', payload);
        }""",
        {"node_id": _BADGE_REQ_ID, "new_title": new_title},
    )


class TestBrowserDestructiveOperationsUnderUnknownCount:
    """Validates REQ-d00267-E: an operation that would discard, strand, or
    commit around pending changes treats an unknown count as changes that may
    exist, never as zero.

    Note the polarity is the opposite of the navigation warning, deliberately.
    Closing a tab destroys nothing held in the page, so uncertainty there
    stays permissive. These operations act ON the server-side changes, so the
    same uncertainty has to be restrictive. Both guards read
    `editState.mutationCount > 0`, and `null > 0` is false, so a single
    network blip is enough to walk straight past them.

    They refuse rather than prompt: 'save first' is not actionable advice when
    saving needs the same server whose silence caused the uncertainty.
    """

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_E_branch_picker_refuses_while_count_unknown(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-E
        """Switching branches under an unknown count could strand pending work
        on the branch being left. Driven through the real UI (a click on the
        branch badge). Only /api/dirty is broken — the branch endpoints are
        healthy — so a refusal here is attributable to the guard and not to a
        failed fetch, and without the guard the picker really does open."""
        page = page_badge
        page.on("dialog", lambda d: d.dismiss())
        page.goto(badge_viewer_url, wait_until="networkidle")

        _go_unknown(page)
        assert _badge_state(page)["count"] is None, "precondition: count must be unknown"

        page.click("#branch-badge")

        _wait_for_js(
            page,
            "() => document.getElementById('error-modal-overlay') !== null",
            "an unknown count may be hiding pending work, so the branch "
            "picker must refuse and say so; no error modal appeared",
        )
        assert not _dom_present(page, "#branch-modal-overlay"), (
            "the branch picker must not open while the pending count is "
            "unknown — switching branches could strand work the page cannot "
            "confirm is absent"
        )
        text = _error_modal_text(page).lower()
        assert "unknown" in text, (
            f"the refusal must name the reason — the count is unknown — so the "
            f"operator knows to restore the server rather than retry; got {text!r}"
        )

        page.unroute("**/api/dirty")

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_E_branch_picker_opens_when_server_reports_zero(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-E
        """Negative control: the guard must key on 'unknown', not on 'not
        greater than zero'. A server-REPORTED zero is a real answer and must
        still let the picker open, or the refusal is just a broken feature."""
        page = page_badge
        page.on("dialog", lambda d: d.dismiss())
        page.goto(badge_viewer_url, wait_until="networkidle")

        _revert_to_zero(page, badge_viewer_url)
        _refresh_dirty(page)
        assert _badge_state(page)["count"] == 0, "precondition: server reports nothing pending"

        page.click("#branch-badge")

        _wait_for_js(
            page,
            "() => document.getElementById('branch-modal-overlay') !== null",
            "with the server reporting nothing pending the branch picker must " "open normally",
        )
        assert not _dom_present(page, "#error-modal-overlay"), (
            f"a reported zero is a real answer and must not be refused; "
            f"error modal said {_error_modal_text(page)!r}"
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_E_checkpoint_refuses_while_count_unknown(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-E
        """Checkpointing under an unknown count commits around changes that
        may be pending, producing a commit that silently omits them.

        Driven by calling showCheckpointModal() directly rather than clicking
        #btn-checkpoint: that button is enabled only when the repo has
        uncommitted files, and the badge fixture's repo is committed clean, so
        there is no clickable path to the guard. The dialog handler is
        defensive — the guard must refuse outright, never prompt, because
        saving would need the same server that just went quiet.
        """
        page = page_badge
        dialogs: list[str] = []
        page.on("dialog", lambda d: (dialogs.append(d.type), d.dismiss()))
        page.goto(badge_viewer_url, wait_until="networkidle")

        _go_unknown(page)
        assert _badge_state(page)["count"] is None, "precondition: count must be unknown"

        page.evaluate("() => showCheckpointModal()")

        _wait_for_js(
            page,
            "() => document.getElementById('error-modal-overlay') !== null",
            "an unknown count may be hiding pending work, so checkpointing "
            "must refuse and say so; no error modal appeared",
        )
        assert not dialogs, (
            f"the guard must refuse outright, not prompt: saving needs the "
            f"same server whose silence caused the uncertainty, so a prompt "
            f"offers no action the operator can take; got dialogs {dialogs}"
        )
        text = _error_modal_text(page).lower()
        assert (
            "unknown" in text
        ), f"the refusal must name the reason — the count is unknown; got {text!r}"

        page.unroute("**/api/dirty")

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_E_checkpoint_not_refused_when_server_reports_zero(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-d00267-E
        """Negative control for the checkpoint guard: a server-reported zero
        is a real answer and must pass through to the normal checkpoint path
        rather than being refused."""
        page = page_badge
        page.on("dialog", lambda d: d.dismiss())
        page.goto(badge_viewer_url, wait_until="networkidle")

        _revert_to_zero(page, badge_viewer_url)
        _refresh_dirty(page)
        assert _badge_state(page)["count"] == 0, "precondition: server reports nothing pending"

        # Waiting on the request the un-refused path makes, not on a clock:
        # a reported zero falls straight through to the checkpoint modal,
        # whose first act is to read git status. If the guard wrongly refused,
        # that request never happens and this fails as a timeout naming the
        # missing call rather than passing on a sleep that was long enough.
        with page.expect_response("**/api/git/status", timeout=10_000):
            page.evaluate("() => showCheckpointModal()")

        assert not _dom_present(page, "#error-modal-overlay"), (
            f"a reported zero is a real answer and must not be refused; "
            f"error modal said {_error_modal_text(page)!r}"
        )
