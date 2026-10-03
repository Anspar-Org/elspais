"""Playwright-based browser test for the reason the viewer asks for when a save
changes an Active requirement."""

import pytest

pytest.importorskip("playwright", reason="playwright not installed")
from playwright.sync_api import sync_playwright  # noqa: E402

from ..helpers import resolve_elspais  # noqa: E402
from .support import (  # noqa: E402
    _EDIT_CONTROLS_CITING,
    _enter_edit_mode,
    _served_viewer,
    _wait_for_js,
    _write_edit_controls_project,
)

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        resolve_elspais() is None,
        reason="elspais CLI not found on PATH",
    ),
]

_REASON = "the reader explained this change"


@pytest.fixture(scope="module")
def reason_viewer(tmp_path_factory):
    """A viewer over a private project whose Active requirement the test edits
    and saves. Yields the viewer's URL and the project directory."""
    dest = tmp_path_factory.mktemp("viewer-changelog-reason")
    _write_edit_controls_project(dest)
    with _served_viewer(dest) as base_url:
        yield base_url, dest


@pytest.fixture()
def page_reason(reason_viewer):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_context().new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


def _pending(page, base_url: str) -> int:
    return page.request.get(f"{base_url}/api/dirty").json().get("mutation_count", 0)


def _ask_for_reason(page) -> None:
    """Click the page's Save control and wait for the reason prompt."""
    page.wait_for_selector("#btn-save:not([disabled])", timeout=10_000)
    page.click("#btn-save")
    page.wait_for_selector("#changelog-reason-overlay", timeout=10_000)


class TestBrowserSaveAsksForTheReason:
    """Validates REQ-d00325-D."""

    # Verifies: REQ-d00325-D
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00325_D_save_completes_only_with_the_reason_the_reader_enters(
        self, page_reason, reason_viewer
    ):
        page = page_reason
        base_url, project = reason_viewer
        spec_file = project / "spec" / "dev.md"
        before = spec_file.read_text(encoding="utf-8")
        js_errors: list[str] = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))
        saves: list = []
        page.on("response", lambda r: saves.append(r) if r.url.endswith("/api/save") else None)
        page.goto(base_url, wait_until="networkidle")
        _enter_edit_mode(page)

        edited = page.evaluate(
            f"""async () => await mutate('/api/mutate/title',
                {{node_id: '{_EDIT_CONTROLS_CITING}', new_title: 'Citing Retitled'}})"""
        )
        assert edited and edited.get("success"), edited

        # The prompt names the requirement that needs the reason.
        _ask_for_reason(page)
        assert [r.status for r in saves] == [400]
        listed = page.locator("#changelog-reason-ids").inner_text()
        assert _EDIT_CONTROLS_CITING in listed, listed

        # Cancelling saves nothing and keeps the change.
        page.click("#changelog-reason-cancel")
        page.wait_for_selector("#changelog-reason-overlay", state="detached")
        toasts = page.locator("#toast-container").inner_text()
        assert "Not saved" in toasts, toasts
        assert _pending(page, base_url) > 0
        assert spec_file.read_text(encoding="utf-8") == before

        # An empty reason is not accepted and nothing is sent.
        _ask_for_reason(page)
        sent = len(saves)
        page.fill("#changelog-reason-input", "   ")
        page.click("#changelog-reason-submit")
        error = page.locator("#changelog-reason-error")
        assert error.is_visible(), "an empty reason must be reported in the prompt"
        assert "hidden" not in (error.get_attribute("class") or "")
        assert page.locator("#changelog-reason-overlay").is_visible()
        assert len(saves) == sent, "an empty reason was sent to the server"
        assert _pending(page, base_url) > 0
        assert spec_file.read_text(encoding="utf-8") == before

        # The reason the reader enters completes the save.
        page.fill("#changelog-reason-input", _REASON)
        page.click("#changelog-reason-submit")
        page.wait_for_selector("#changelog-reason-overlay", state="detached")
        _wait_for_js(
            page,
            "() => editState.mutationCount === 0",
            "the save with the reader's reason did not clear the pending count",
            timeout=10.0,
        )
        assert saves[-1].status == 200, saves[-1].text()
        assert _pending(page, base_url) == 0
        after = spec_file.read_text(encoding="utf-8")
        assert "Citing Retitled" in after
        assert _REASON in after
        assert not js_errors, f"JS errors on save: {js_errors}"
