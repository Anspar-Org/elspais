# Verifies: REQ-d00010
# Verifies: REQ-d00255-D
# Verifies: REQ-d00256-D
# Verifies: REQ-o00062-O
# Verifies: REQ-d00267-A
# Verifies: REQ-d00267-B
# Verifies: REQ-d00267-C
# Verifies: REQ-d00267-D
# Verifies: REQ-d00267-E
"""Playwright-based browser tests for the elspais viewer: its pages, cards,
reports, journeys, results and concurrency guards.

Validates REQ-d00010: viewer command serves the traceability UI
and exposes API endpoints for graph exploration.

Validates REQ-d00255-D, REQ-d00256-D: journey UAT verdict badge and
failing-step identification are visible in the viewer.
"""

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="playwright not installed")
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from tests.embedded_page import embedded_data  # noqa: E402

from ..helpers import resolve_elspais  # noqa: E402
from .support import (  # noqa: E402
    _CONCURRENCY_REQ_ID,
    _EDIT_CONTROLS_CITING,
    _EMBEDDED_NOTES_ASSERTION,
    _EMBEDDED_NOTES_REQ,
    _FAILING_JOURNEY_ID,
    _FETCH_TEXT,
    _FILE_MUT_NAMESPACE,
    _FILE_MUT_REQ_ID,
    _FILTERS_READY,
    _PAGE_LOAD_TIMEOUT,
    _SESSION_CHECK_SECONDS,
    _SESSION_GRACE_SECONDS,
    _SHOW_EVERY_STATUS,
    _STEP_BINDING_JOURNEY_ID,
    _VOCABULARY,
    _authority_scope_membership,
    _await_process_exit,
    _await_viewer,
    _client_scope_membership,
    _end_viewer,
    _enter_edit_mode,
    _file_lines,
    _open_results_panel,
    _restored_source_panel,
    _server_output,
    _session_lifetime_viewer,
    _spec_files,
    _wait_for_js,
    _wait_for_spec_file,
)

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        resolve_elspais() is None,
        reason="elspais CLI not found on PATH",
    ),
]


class TestViewerPageLoad:
    """Validates REQ-d00010: viewer page loads correctly in a browser."""

    # These are the first loads of the page over this repository's own estate,
    # and a cold CI container has overrun the fixture's default deadline on
    # that first render alone, so both get the allowance their neighbours get.
    # The wait stays on networkidle: the page's scripts must have run for a
    # script error to be observable.

    # Verifies: REQ-d00010-A
    def test_REQ_d00010_A_page_loads_without_js_errors(self, page, viewer_url):
        js_errors = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        page.goto(viewer_url, wait_until="networkidle", timeout=_PAGE_LOAD_TIMEOUT)

        assert not js_errors, f"JS errors on page load: {js_errors}"
        title = page.title()
        body_text = page.text_content("body") or ""
        assert "elspais" in title.lower() or len(body_text.strip()) > 0, (
            "Page has no title or body content"
        )

    # Verifies: REQ-d00010-A
    def test_REQ_d00010_A_page_has_content(self, page, viewer_url):
        page.goto(viewer_url, wait_until="networkidle", timeout=_PAGE_LOAD_TIMEOUT)

        body_text = page.text_content("body") or ""
        assert len(body_text.strip()) > 50, (
            f"Page body has too little content ({len(body_text.strip())} chars)"
        )


class TestViewerAPI:
    """Validates REQ-d00010: viewer API endpoints return correct data."""

    # Verifies: REQ-d00010-A
    def test_REQ_d00010_A_api_status_returns_json(self, page, viewer_url):
        resp = page.request.get(f"{viewer_url}/api/status")
        assert resp.ok, f"GET /api/status returned {resp.status}"

        data = resp.json()
        assert "node_counts" in data, (
            f"Expected 'node_counts' in status response, got keys: {list(data.keys())}"
        )

    # Verifies: REQ-d00010-A
    def test_REQ_d00010_A_api_search_returns_results(self, page, viewer_url):
        resp = page.request.get(f"{viewer_url}/api/search?q=REQ")
        assert resp.ok, f"GET /api/search returned {resp.status}"

        data = resp.json()
        assert "results" in data, f"Expected 'results' key, got keys: {list(data.keys())}"
        assert isinstance(data["results"], list)


class TestViewerInteraction:
    """Validates REQ-d00010: viewer UI interactions work correctly."""

    # Verifies: REQ-d00010-A
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

    # Verifies: REQ-d00010-A
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


class TestViewerExport:
    """Validates REQ-d00298: a report downloads from the served page."""

    # Verifies: REQ-d00298-A, REQ-d00298-F
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00298_A_export_control_downloads_the_chosen_report(self, page, viewer_url):
        """Choosing a report and a format in the toolbar and pressing Download
        fetches an attachment named for that report and format."""
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_selector("#btn-export", timeout=_PAGE_LOAD_TIMEOUT)
        page.select_option("#export-report", "trace")
        page.select_option("#export-format", "markdown")
        with page.expect_download() as download_info:
            page.click("#btn-export")
        download = download_info.value
        assert re.match(r"^trace-\d{8}-\d{6}\.md$", download.suggested_filename), (
            download.suggested_filename
        )
        # The page is still the viewer: a download is not a navigation away.
        assert page.query_selector("#export-control") is not None

    # Verifies: REQ-d00298-E
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00298_E_formats_listed_are_the_ones_the_report_offers(self, page, viewer_url):
        """Switching to a report that offers no CSV drops CSV from the list,
        so a reader cannot ask for a format the route will refuse."""
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_selector("#btn-export", timeout=_PAGE_LOAD_TIMEOUT)
        page.select_option("#export-report", "trace")
        trace_formats = page.eval_on_selector_all(
            "#export-format option", "opts => opts.map(o => o.value)"
        )
        assert trace_formats == ["markdown", "csv", "pdf"]
        page.select_option("#export-report", "gaps")
        gaps_formats = page.eval_on_selector_all(
            "#export-format option", "opts => opts.map(o => o.value)"
        )
        assert gaps_formats == ["markdown", "pdf"]

    # Verifies: REQ-d00298-G
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00298_G_level_narrowing_reaches_only_a_report_that_reads_a_scope(
        self, page, viewer_url
    ):
        """A level soloed in the header is sent as the scope the run route
        reads, and only to a report that reads one: the checks listing reads
        no scope, so sending it one would narrow nothing while looking as if
        it had."""
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_function(_FILTERS_READY, timeout=_PAGE_LOAD_TIMEOUT)
        page.evaluate(_SHOW_EVERY_STATUS)
        page.click("#stat-level-prd", modifiers=["Shift"])
        page.wait_for_timeout(300)
        page.select_option("#export-report", "trace")
        page.select_option("#export-format", "csv")
        assert page.evaluate("exportUrl()") == "/api/export/trace?format=csv&scope_level=prd"
        page.select_option("#export-report", "checks")
        assert page.evaluate("exportUrl()") == "/api/export/checks?format=markdown"

        # No level on is a page showing nothing. The toggle keeps the last
        # level on, so the state arrives only through restored filter state;
        # a scope cannot say "nothing", so the export has no URL and is
        # refused rather than widened to the whole estate. A report reading
        # no scope is unaffected.
        page.evaluate(
            "() => { filterGroups.level.restore({on: []}); filterGroups.level.render(); }"
        )
        assert page.evaluate("exportUrl()") == "/api/export/checks?format=markdown"
        page.select_option("#export-report", "trace")
        assert page.evaluate("exportUrl()") is None
        page.click("#btn-export")
        toast = page.wait_for_selector(".toast.error", timeout=5_000)
        assert "nothing to export" in toast.text_content().lower()
        assert page.query_selector("#export-control") is not None

    # Verifies: REQ-d00298-G
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00298_G_a_status_hidden_on_screen_is_hidden_from_the_download(
        self, page, viewer_url
    ):
        """A reader who hides a status has narrowed the report they are
        reading; the download carries the same narrowing, so it does not
        arrive holding the rows the page was told to put away. Whole-estate
        first, because a narrowing that changed nothing would prove nothing."""
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_function(_FILTERS_READY, timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_function(
            "() => !!filterGroups.status && filterGroups.status.buttons.length > 1",
            timeout=_PAGE_LOAD_TIMEOUT,
        )
        page.evaluate(_SHOW_EVERY_STATUS)
        page.select_option("#export-report", "trace")
        page.select_option("#export-format", "csv")
        assert "scope_status" not in page.evaluate("exportUrl()")
        whole = page.evaluate(_FETCH_TEXT, page.evaluate("exportUrl()"))

        # The status carrying the most of the estate, soloed: rows exist to
        # be kept, and every other status's rows are the ones put away.
        kept = page.evaluate(
            """() => {
                const g = filterGroups.status;
                const counted = g.buttons
                    .map(b => [b.key, g._available.get(b.key) || 0])
                    .sort((a, b) => b[1] - a[1]);
                return counted[0][1] > 0 && counted[1][1] > 0 ? counted[0][0] : null;
            }"""
        )
        assert kept, "precondition: the estate must hold rows under two statuses"
        page.evaluate(
            "(k) => { filterGroups.status.restore({on: [k]}); filterGroups.status.render(); }",
            kept,
        )
        narrowed_url = page.evaluate("exportUrl()")
        assert f"scope_status={kept}" in narrowed_url, narrowed_url
        narrowed = page.evaluate(_FETCH_TEXT, narrowed_url)
        assert narrowed != whole
        assert len(narrowed) < len(whole)

        # A report that reads no scope is told nothing, status included.
        page.select_option("#export-report", "checks")
        assert page.evaluate("exportUrl()") == "/api/export/checks?format=markdown"

    # Verifies: REQ-d00298-A
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00298_A_download_raises_no_leave_page_warning_over_pending_work(
        self, page, viewer_url
    ):
        """The page holds pending work, so leaving it warns. A download is
        not a departure: it is fetched in place, and no dialog is raised.
        Registered before the click, because the dialog the old navigation
        raised came with the click itself."""
        dialogs: list[str] = []
        page.on("dialog", lambda d: (dialogs.append(d.type), d.dismiss()))

        # The page takes its pending count from /api/dirty on load and on every
        # server event, so a count set from the page is overwritten by the next
        # probe. The route makes every probe report pending work instead.
        def _report_pending(route):
            response = route.fetch()
            body = response.json()
            body["mutation_count"] = 1
            route.fulfill(response=response, json=body)

        page.route("**/api/dirty", _report_pending)
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_selector("#btn-export", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_function(
            "() => unloadWarningState().willWarnOnClose === true",
            timeout=_PAGE_LOAD_TIMEOUT,
        )
        page.select_option("#export-report", "summary")
        page.select_option("#export-format", "csv")
        with page.expect_download() as download_info:
            page.click("#btn-export")
        download = download_info.value
        assert re.match(r"^summary-\d{8}-\d{6}\.csv$", download.suggested_filename), (
            download.suggested_filename
        )
        assert dialogs == [], f"a download raised a dialog: {dialogs}"
        assert page.url.rstrip("/") == viewer_url.rstrip("/")
        assert page.query_selector("#export-control") is not None

    # Verifies: REQ-d00298-E
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00298_E_a_refusal_is_shown_on_the_page_not_in_its_place(self, page, viewer_url):
        """A format the report does not offer is refused by the route; the
        refusal reaches the reader as a message on the page they were on,
        naming the formats offered, rather than as the route's JSON where the
        page used to be. The control lists only offered formats, so the
        unoffered one is put into the list by hand."""
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_selector("#btn-export", timeout=_PAGE_LOAD_TIMEOUT)
        # Let the page's own load-time requests over this estate finish first,
        # so the refusal is measured on its own: clicked while they are still
        # in flight, the fetch queues behind them on the server, and on a cold
        # CI container that queue alone outran a short wait. The wait then
        # gets the allowance the page gets, since the answer is bounded by the
        # same load; the toast appears the moment the refusal arrives.
        page.wait_for_load_state("networkidle", timeout=_PAGE_LOAD_TIMEOUT)
        page.select_option("#export-report", "gaps")
        page.evaluate(
            """() => {
                const sel = document.getElementById('export-format');
                const opt = document.createElement('option');
                opt.value = 'csv'; opt.textContent = 'csv';
                sel.appendChild(opt);
            }"""
        )
        page.select_option("#export-format", "csv")
        assert page.evaluate("exportUrl()") == "/api/export/gaps?format=csv"
        page.click("#btn-export")
        toast = page.wait_for_selector(".toast.error", timeout=_PAGE_LOAD_TIMEOUT)
        text = toast.text_content()
        assert "markdown" in text and "pdf" in text, text
        assert page.url.rstrip("/") == viewer_url.rstrip("/")
        assert page.query_selector("#export-control") is not None


class TestTableRendering:
    """Validates REQ-d00010: pipe tables in spec body sections render as
    HTML tables with a full grid in the live viewer."""

    # Verifies: REQ-d00010
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
            f"Expected verdict='fail' in API, got {props.get('verdict')!r}. Properties: {props}"
        )
        assert "2" in props.get("failing_steps", []), (
            f"Expected '2' in failing_steps, got {props.get('failing_steps')!r}"
        )

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
        assert "UAT: FAIL" in card_text, (
            f"Expected 'UAT: FAIL' in journey card, got card text:\n{card_text!r}"
        )

        # Assert the failing step label is shown (bare step number, "Failing
        # steps: 2" — a substring check on "2" alone would be trivially true)
        assert "Failing steps: 2" in card_text, (
            f"Expected 'Failing steps: 2' in journey card, got card text:\n{card_text!r}"
        )

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
        assert "2/3 steps verified" in vlink["tooltip"], (
            f"Expected 2/3 fraction, got {vlink['tooltip']!r}"
        )

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
        assert "fail" in badge.inner_text().lower(), (
            f"Expected 'fail' badge text, got {badge.inner_text()!r}"
        )
        badge_class = badge.get_attribute("class") or ""
        assert "val-red" in badge_class, f"Expected val-red on badge, got class={badge_class!r}"

        # The 2/3 step fraction is surfaced via the row's hover tooltip (title).
        row = panel.locator(".incoming-link-row", has_text="JNY-OQ-Login-01")
        row_title = row.get_attribute("title") or ""
        assert "2/3 steps verified" in row_title, (
            f"Expected 2/3 fraction in tooltip, got {row_title!r}"
        )

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
        assert steps_section.count() == 1, (
            "Expected exactly one .journey-steps section in the journey card"
        )

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

        assert "validation-fail" in step2_cls, (
            f"step-2 badge should be validation-fail, got {step2_cls!r}"
        )
        assert "validation-fail" not in step1_cls, (
            f"step-1 badge should NOT be validation-fail, got {step1_cls!r}"
        )
        assert "validation-fail" not in step3_cls, (
            f"step-3 badge should NOT be validation-fail, got {step3_cls!r}"
        )

        # Each step must expose at least one verifying-test row
        all_test_rows = card_locator.locator(".journey-step-test-row").all()
        assert len(all_test_rows) >= 3, (
            f"Expected >= 3 verifying-test rows, got {len(all_test_rows)}"
        )

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
        assert "test_step1" in panel.inner_text(), (
            f"Expected verifying test id in revealed panel, got: {panel.inner_text()!r}"
        )
        assert "active" in (badge.get_attribute("class") or ""), (
            "Badge should carry 'active' class while its panel is open"
        )

        # Click again — should hide the panel
        badge.click()
        panel.wait_for(state="hidden", timeout=5_000)
        assert "active" not in (badge.get_attribute("class") or ""), (
            "Badge should lose 'active' class once its panel is closed"
        )

        assert not js_errors, f"JS errors during step-badge toggle: {js_errors}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_d00256_journey_step_test_row_single_link(
        self, page_journey, failing_journey_viewer_url
    ):
        # Verifies: REQ-d00256
        """Each verifying-test row shows a status chip plus exactly ONE
        clickable source link (calling showSource) -- not the same path text
        rendered twice with no link.

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
        # from a `font: inherit` override.
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
        assert "showSource(" in onclick, (
            f"Step-test link must call showSource, got onclick={onclick!r}"
        )

        # The display text must appear only once (no id + duplicate title spans).
        link_text = links.first.inner_text().strip()
        assert link_text, "link should have display text"
        assert test_row.inner_text().count(link_text) == 1, (
            f"Display text {link_text!r} should not be duplicated in row: {test_row.inner_text()!r}"
        )

        assert not js_errors, f"JS errors during step-test link render: {js_errors}"


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
                f"Result row {i} should have exactly one link: {rows.nth(i).inner_html()!r}"
            )
            link_text = link.inner_text().strip()
            assert link_text.startswith("results/junit/results.xml:"), (
                f"Result row {i} link must be 'results/junit/results.xml:<line>', got {link_text!r}"
            )

        assert not js_errors, f"JS errors during step-results render: {js_errors}"


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
        assert len(mutate_posts) == 1, (
            f"expected exactly ONE title POST (no blind retry), got: {mutate_posts}"
        )
        conflict_index, conflict_event = mutate_posts[0]
        assert conflict_event["status"] == 409, (
            f"stale edit must be rejected with HTTP 409, got {conflict_event}"
        )
        rereads = [
            i
            for i, e in enumerate(events)
            if e["method"] == "GET" and f"/api/node/{req_id}" in e["url"]
        ]
        assert any(i > conflict_index for i in rereads), (
            f"expected a re-read GET of /api/node/{req_id} AFTER the 409; events: {events}"
        )

        # Server state: the behind-the-back write survived; the stale browser
        # edit never landed.
        final = page.request.get(f"{base}/api/node/{req_id}").json()
        assert final.get("title") == "Agent Rewrote This", (
            f"server must keep the concurrent writer's state, got: {final.get('title')!r}"
        )

        assert not js_errors, f"JS errors during conflict recovery: {js_errors}"


class TestBrowserFileMutations:
    """Validates REQ-p00050-E: a FILE node id denotes exactly one node, so it
    carries the owning repository's namespace and is minted or resolved by the
    server. The browser names a file by path; it never builds the id."""

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_p00050_E_rename_file_through_ui_renames_the_file(
        self, page_file_mutation, file_mutation_viewer_url
    ):
        # Verifies: REQ-p00050-E
        """Rename a spec file through the file viewer's real Rename button
        (a `prompt()` dialog, answered by a Playwright dialog handler) and
        assert the SERVER-side effect: /api/spec-files stops listing the old
        path and lists the new one under an id in the serving repository's
        namespace.

        The whole flow is driven through the UI: the card's source link opens
        the file viewer, and #fv-rename is clicked. Nothing here calls fetch()
        against the API, so the client-side path->id handling is exercised.
        """
        page = page_file_mutation
        base = file_mutation_viewer_url
        js_errors: list[str] = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        before = _spec_files(page, base)
        old_path = "spec/prd-tables.md"
        new_path = "spec/prd-tables-renamed.md"
        assert old_path in before, f"precondition: fixture must hold {old_path}, got {before}"
        assert new_path not in before, f"precondition: {new_path} must not exist yet, got {before}"

        page.goto(base, wait_until="networkidle")
        _enter_edit_mode(page)
        page.evaluate(f"() => window.openCard('{_FILE_MUT_REQ_ID}')")
        card = page.locator(f"#card-{_FILE_MUT_REQ_ID}")
        card.wait_for(state="visible", timeout=10_000)

        # Open the file in the viewer through the card's own source link —
        # that is what makes #fv-path (the path the rename reads) and the
        # Rename button available.
        card.locator("a", has_text="prd-tables.md:").first.click()
        rename_btn = page.locator("#fv-rename")
        rename_btn.wait_for(state="visible", timeout=10_000)
        assert page.locator("#fv-path").get_attribute("title") == old_path, (
            "file viewer must be showing the file about to be renamed"
        )

        # The Rename control asks for the new path with prompt().
        page.on("dialog", lambda d: d.accept(new_path))
        rename_btn.click()

        after = _wait_for_spec_file(page, base, new_path)
        assert new_path in after, (
            f"renaming through the UI must land on the server: expected "
            f"{new_path} in /api/spec-files, got {after}"
        )
        assert old_path not in after, (
            f"the old path must be gone after a rename, still listed in {after}"
        )
        assert after[new_path] == f"file:{_FILE_MUT_NAMESPACE}:{new_path}", (
            f"the renamed FILE id must carry the owning repository's "
            f"namespace, got {after[new_path]!r}"
        )

        assert not js_errors, f"JS errors during the rename flow: {js_errors}"

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_p00050_E_move_requirement_to_a_new_file_creates_it(
        self, page_file_mutation, file_mutation_viewer_url
    ):
        # Verifies: REQ-p00050-E
        """Move a requirement to a file that does not exist yet, through the
        card's real Move button and its modal ("+ New file…" + a typed path),
        and assert the SERVER-side effect: the file is created, carries an id
        in the serving repository's namespace, and the requirement now reports
        it as its source.

        Driven entirely through the UI controls — the modal's radio, its path
        input and its Move button — so the client-side handling of a path for
        a not-yet-existing file is what is under test.
        """
        page = page_file_mutation
        base = file_mutation_viewer_url
        js_errors: list[str] = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        new_path = "spec/moved-requirement.md"
        before = _spec_files(page, base)
        assert new_path not in before, f"precondition: {new_path} must not exist yet, got {before}"

        page.goto(base, wait_until="networkidle")
        _enter_edit_mode(page)
        page.evaluate(f"() => window.openCard('{_FILE_MUT_REQ_ID}')")
        card = page.locator(f"#card-{_FILE_MUT_REQ_ID}")
        card.wait_for(state="visible", timeout=10_000)

        source_before = page.request.get(f"{base}/api/requirement/{_FILE_MUT_REQ_ID}").json()
        old_source_path = (source_before.get("source") or {}).get("path")
        assert old_source_path and old_source_path != new_path, source_before

        card.locator("button.card-move-file-btn").first.click()
        overlay = page.locator("#move-file-modal-overlay")
        overlay.wait_for(state="visible", timeout=10_000)

        # "+ New file…" reveals the path input; the path names a file that
        # does not exist, so only the server can say what its id will be.
        overlay.locator('input[value="__new__"]').check()
        path_input = overlay.locator("input.modal-input")
        path_input.wait_for(state="visible", timeout=5_000)
        path_input.fill(new_path)
        overlay.locator("button.btn-primary").click()

        # A successful move closes the modal; a refused one keeps it open and
        # writes the server's reason into it. Capture that reason rather than
        # failing on an opaque wait, so a rejected id shape names itself.
        modal_error = ""
        try:
            overlay.wait_for(state="detached", timeout=10_000)
        except PlaywrightTimeoutError:
            modal_error = overlay.locator(".modal-error").inner_text()

        after = _wait_for_spec_file(page, base, new_path)
        assert new_path in after, (
            f"moving to a new file must create it on the server: expected "
            f"{new_path} in /api/spec-files, got {after}"
            + (f"; the move modal reported: {modal_error!r}" if modal_error else "")
        )
        assert after[new_path] == f"file:{_FILE_MUT_NAMESPACE}:{new_path}", (
            f"the created FILE id must carry the owning repository's "
            f"namespace, got {after[new_path]!r}"
        )

        moved = page.request.get(f"{base}/api/requirement/{_FILE_MUT_REQ_ID}").json()
        assert (moved.get("source") or {}).get("path") == new_path, (
            f"{_FILE_MUT_REQ_ID} must now live in {new_path}, server reports "
            f"{moved.get('source')!r}"
        )

        assert not js_errors, f"JS errors during the move flow: {js_errors}"


class TestAssertionPillMeasures:
    """A rendered pill makes the measures behind its standing readable.

    The server payload carrying those measures is tested elsewhere; this is
    the only place the wiring from that payload into the rendered pill is
    exercised. Without it a pill could silently stop showing the measures --
    or start showing a caveat again -- and nothing would go red.
    """

    # Verifies: REQ-d00292-E, REQ-d00258-J
    def test_pill_title_names_the_measures_and_carries_no_caveat(self, page, viewer_url):
        """Open a covered requirement; read its per-*Assertion* pills.

        REQ-d00258 is opened because it is covered on several dimensions in
        this repository's own estate, so its assertions render pills at all.
        The assertions here are about the pill, not about that coverage:
        a pill states its standing, names the four measures behind it, and
        carries no `~` and no caveat element (REQ-d00258-J).
        """
        # Not `networkidle`: this page holds a change stream open to its
        # server for its whole life. Waiting for the entry point the test
        # actually calls is both stricter and stable.
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_function(
            "() => typeof window.openCard === 'function'", timeout=_PAGE_LOAD_TIMEOUT
        )
        page.evaluate("() => window.openCard('REQ-d00258')")

        page.locator("#card-stack-body .card-assertion-wrapper").first.wait_for(
            state="visible", timeout=10_000
        )
        pills = page.locator("#card-stack-body .assertion-badges-area button")
        assert pills.count() > 0, "no per-assertion pills rendered for REQ-d00258"

        titles = [pills.nth(i).get_attribute("title") or "" for i in range(pills.count())]
        labels = [pills.nth(i).inner_text() for i in range(pills.count())]

        # The measures reach the reader: at least one pill names them, and a
        # pill that states a standing states them all.
        with_standing = [t for t in titles if "standing: " in t]
        assert with_standing, f"no pill title stated a coverage standing: {titles}"
        for tip in with_standing:
            for word in (
                "cited by name here",
                "whole-requirement",
                "conducted direct",
                "conducted indirect",
            ):
                assert word in tip, f"pill title omits {word!r}: {tip!r}"

        # And nothing stands in for a measure it does not show (REQ-d00258-J).
        for tip in titles:
            assert "~" not in tip, f"pill title carries a caveat marker: {tip!r}"
        for label in labels:
            assert "~" not in label, f"pill label carries a caveat marker: {label!r}"
        assert page.locator("#card-stack-body .dim-caveat").count() == 0, (
            "a caveat element is still rendered in the card"
        )


class TestScopeMembershipAgreesWithAuthority:
    """Validates REQ-d00279-B: the viewer decides scope membership for itself,
    over rows it already holds, so that it can answer as fast as a reader
    narrows. What it owes for that permission is the membership the authority
    yields for the same scope — not a rule that is merely consistent with
    itself. These tests drive the client's real ``filterGroups`` and compare
    against ``/api/scope``."""

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_unconstrained_scope_membership_matches_authority(self, page, viewer_url):
        # Verifies: REQ-d00279-B
        """The neutral state is a scope too, and the one the comparison rests on.

        Were the client never shown some requirement, it could hide it under
        every scope and still look equivalent.
        """
        # The index over this repository's own estate may carry a full rebuild
        # (the mutation tests before this one wrote spec files), so the page
        # load gets the same allowance its neighbours get, not the fixture's
        # default.
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_function(_FILTERS_READY, timeout=_PAGE_LOAD_TIMEOUT)

        client = _client_scope_membership(page)
        authority = _authority_scope_membership(page, viewer_url)

        assert client == authority, (
            f"the viewer shows {len(client)} requirements unconstrained where the "
            f"authority yields {len(authority)}; "
            f"only the viewer: {sorted(set(client) - set(authority))[:10]}, "
            f"only the authority: {sorted(set(authority) - set(client))[:10]}"
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_narrowed_scope_membership_matches_authority(self, page, viewer_url):
        # Verifies: REQ-d00279-B
        """A scope a reader could write, answered both ways.

        The scopes are derived from what this estate actually carries rather
        than spelled out here, so the comparison keeps deciding something as the
        estate's levels and statuses change.
        """
        # The index over this repository's own estate may carry a full rebuild
        # (the mutation tests before this one wrote spec files), so the page
        # load gets the same allowance its neighbours get, not the fixture's
        # default.
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT)
        page.wait_for_function(_FILTERS_READY, timeout=_PAGE_LOAD_TIMEOUT)

        vocab = page.evaluate(_VOCABULARY)
        carried_levels = sorted(
            k for k in vocab["levels"] if k.upper() in {v.upper() for v in vocab["carriedLevels"]}
        )
        carried_statuses = sorted(set(vocab["statuses"]) & set(vocab["carriedStatuses"]))
        assert carried_levels, f"no level button matches a carried level: {vocab}"
        assert carried_statuses, f"no status button matches a carried status: {vocab}"

        level, status = carried_levels[0], carried_statuses[0]
        cases: dict[str, tuple[dict[str, list[str] | None], str]] = {
            "one level": ({"level": [level]}, f"scope_level={level}"),
            "one status": ({"status": [status]}, f"scope_status={status}"),
            "status excluded": (
                {"status": [s for s in vocab["statuses"] if s != status]},
                f"scope_not_status={status}",
            ),
            "level and status": (
                {"level": [level], "status": [status]},
                f"scope_level={level}&scope_status={status}",
            ),
        }

        divergences: list[str] = []
        for name, (narrowing, params) in cases.items():
            client = _client_scope_membership(page, **narrowing)
            authority = _authority_scope_membership(page, viewer_url, params)
            if client != authority:
                divergences.append(
                    f"{name} ({params}): viewer {len(client)} vs authority "
                    f"{len(authority)}; only the viewer "
                    f"{sorted(set(client) - set(authority))[:5]}, only the authority "
                    f"{sorted(set(authority) - set(client))[:5]}"
                )
        assert not divergences, "; ".join(divergences)

        # A scope that decides nothing would let any rule pass the comparison.
        whole = _authority_scope_membership(page, viewer_url)
        narrowed = _authority_scope_membership(page, viewer_url, f"scope_level={level}")
        assert 0 < len(narrowed) < len(whole), (
            f"scope_level={level} selects {len(narrowed)} of {len(whole)}: "
            "these cases must divide the estate to decide anything"
        )


class TestEnvironmentTagRendering:
    """The environment a result was recorded in is drawn beside that result."""

    # Verifies: REQ-d00294-F
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00294_F_each_result_shows_its_environment(
        self, page_environments, viewer_url_environments
    ):
        """One test reported in two projects draws one row for each, and the
        project that wrote each row stands beside it.

        The rows are alike in every other way -- same test, same class, same
        recorded line -- so without the environment a reader cannot tell which
        project a row came from.
        """
        page_environments.goto(viewer_url_environments, wait_until="networkidle")
        panel = _open_results_panel(page_environments, "REQ-d00001", "A")

        tags = panel.locator(".result-environment")
        tags.first.wait_for(state="visible", timeout=10_000)

        found = sorted(tags.nth(i).inner_text().strip() for i in range(tags.count()))
        assert found == ["chromium", "firefox"], f"expected both projects, got {found}"

        rows = panel.locator(".assertion-test-item")
        assert rows.count() == tags.count(), (
            f"every result row should carry an environment: "
            f"{rows.count()} rows, {tags.count()} tags"
        )

    # Verifies: REQ-d00294-F
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00294_F_a_result_without_an_environment_draws_no_tag(
        self, page_tables, viewer_url_tables
    ):
        """A project declaring no environment source draws no tag at all.

        The element is absent rather than empty, which is what keeps a card
        in a single-environment project reading as it read before.
        """
        page_tables.goto(viewer_url_tables, wait_until="networkidle")
        page_tables.evaluate("() => window.openCard('REQ-p00001')")
        page_tables.locator("#card-stack-body").wait_for(state="visible", timeout=10_000)

        assert page_tables.locator("#card-stack-body .result-environment").count() == 0


class TestBrowserSessionBoundLifetime:
    """Validates REQ-o00079-A and REQ-o00079-B through a real tab: the page
    holds a handle for as long as it is open, the viewer keeps serving while
    it does, and once the tab has been gone for the grace the viewer ends on
    its own.
    """

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_o00079_A_open_tab_keeps_the_viewer_and_closing_it_ends_it(self, tmp_path_factory):
        # Verifies: REQ-o00079-A, REQ-o00079-B
        # The browser and its tab are up before the viewer is, so the grace
        # -- counted from the viewer's start -- is spent on the viewer
        # becoming ready and the page loading, and on nothing else.
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            proc, log_path, dest = _session_lifetime_viewer(tmp_path_factory)
            daemon_json = dest / ".elspais" / "daemon.json"
            try:
                base_url = _await_viewer(proc, log_path, dest, poll=0.1)
                page.goto(base_url, wait_until="domcontentloaded")
                _wait_for_js(
                    page,
                    "() => editState.lastAnnouncedTip !== null",
                    "the page must hold the change stream and hear the server on it",
                    timeout=_SESSION_GRACE_SECONDS - 2.0,
                )
                # The tab holds its stream for longer than the grace: the
                # handle is what the rule sees, and the rule is not the
                # cause of an ending while one is held -- the grace bounds
                # an absence, not a lifetime.
                assert not _await_process_exit(proc, _SESSION_GRACE_SECONDS + 1.0), (
                    f"the viewer ended while a tab held its stream:\n{_server_output(log_path)}"
                )
                # The tab is visible in the record an operator reads.
                info = json.loads(daemon_json.read_text())
                assert {"kind": "session", "count": 1} in info.get("clients", []), info
                browser.close()

                # Losing the tab starts the grace rather than ending the
                # viewer at the next check: a reload drops the stream the
                # same way, and comes back.
                assert not _await_process_exit(proc, _SESSION_CHECK_SECONDS * 3), (
                    f"the viewer ended at a check inside the grace:\n{_server_output(log_path)}"
                )
                assert _await_process_exit(proc, _SESSION_GRACE_SECONDS + 10), (
                    f"the last tab closed, but the viewer went on serving:\n"
                    f"{_server_output(log_path)}"
                )
                assert proc.returncode == 0, _server_output(log_path)
                assert not daemon_json.exists(), (
                    "a viewer that ended must not leave a record naming it as serving"
                )
            finally:
                _end_viewer(proc)


class TestBrowserStaticEmbeddedContent:
    """Validates REQ-d00321-A, REQ-d00321-B, REQ-d00321-E, REQ-p00006-C."""

    # Verifies: REQ-d00321-A, REQ-d00321-B, REQ-d00321-E, REQ-p00006-C
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00321_AB_a_card_opens_its_source_with_every_line_numbered(
        self, page, embedded_static_page
    ):
        """The card opens from the restored index, and its file's highlighted
        lines are numbered from 1 and carry the file's text line for line."""
        url, project = embedded_static_page
        js_errors: list[str] = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))
        page.goto(url, wait_until="load")

        texts = _restored_source_panel(page, _EDIT_CONTROLS_CITING, "dev.md")

        expected = _file_lines(project / "spec" / "dev.md")
        numbers = page.locator("#fv-body .line-num").all_text_contents()
        assert numbers == [str(n) for n in range(1, len(expected) + 1)]
        assert texts == expected
        highlighted = page.locator("#fv-body code.line-content span[class]")
        assert highlighted.count() > 0, "the source panel shows no highlighting markup"
        assert page.locator("#embedded-data-error").count() == 0
        assert not js_errors, f"JS errors on the static page: {js_errors}"

    # Verifies: REQ-d00321-E
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00321_E_the_page_restores_its_content_exactly(self, page, embedded_static_page):
        """The content the page restores in the browser is the content the
        generator compressed, and a card and its source show text holding
        non-ASCII characters, a script closer and a comment opener whole."""
        url, project = embedded_static_page
        js_errors: list[str] = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))
        page.goto(url, wait_until="load")

        restored = page.evaluate("() => _embeddedReady")
        from urllib.parse import unquote, urlparse

        page_text = Path(unquote(urlparse(url).path)).read_text(encoding="utf-8")
        assert restored == embedded_data(page_text)
        assert _EMBEDDED_NOTES_REQ in restored["nodes"]

        texts = _restored_source_panel(page, _EMBEDDED_NOTES_REQ, "notes.md")
        card = page.locator(f"#card-{_EMBEDDED_NOTES_REQ}")
        assert _EMBEDDED_NOTES_ASSERTION in card.inner_text()
        assert texts == _file_lines(project / "spec" / "notes.md")
        assert any("</script><!-- not a comment -->" in line for line in texts)
        assert page.locator("#embedded-data-error").count() == 0
        assert not js_errors, f"JS errors on the static page: {js_errors}"
