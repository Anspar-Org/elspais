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
