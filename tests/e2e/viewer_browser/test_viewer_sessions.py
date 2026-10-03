"""Playwright-based browser tests for the viewer under a URL prefix, what it
remembers between visits, and its edit and save controls."""

import json
import time

import pytest

pytest.importorskip("playwright", reason="playwright not installed")
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402

from ..helpers import resolve_elspais  # noqa: E402
from .support import (  # noqa: E402
    _BASE_PATH,
    _EDIT_CONTROLS_CITED,
    _EDIT_CONTROLS_CITING,
    _HUB_ORIGIN,
    _LEFT_PROJECT_STATE,
    _LEFT_READER_PREFERENCES,
    _NO_PROJECT_STATE,
    _REMEMBERED_CARD,
    _REMEMBERED_FILTER,
    _SECOND_BASE_PATH,
    _enter_edit_mode,
    _leave_project_state,
    _leave_reader_preferences,
    _open_viewer,
    _project_state,
    _reader_preferences,
    _requests_to,
    _route_hub,
)

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        resolve_elspais() is None,
        reason="elspais CLI not found on PATH",
    ),
]


class TestViewerUnderBasePath:
    """Validates REQ-d00295: a viewer started under a prefix serves the page
    there, the page requests everything under it, and the agent surface sits
    beside it."""

    # Verifies: REQ-d00295-A, REQ-d00295-B
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00295_B_a_card_loads_with_every_request_under_the_prefix(
        self, page_prefixed, prefixed_viewer
    ):
        root_url, base_url, _log, _dir = prefixed_viewer
        requested: list[str] = []
        page_prefixed.on(
            "request",
            lambda request: (
                requested.append(request.url) if request.url.startswith(root_url) else None
            ),
        )

        page_prefixed.goto(base_url, wait_until="networkidle")
        page_prefixed.evaluate("() => window.openCard('REQ-p00001')")
        card = page_prefixed.locator("#card-stack-body").filter(has_text="REQ-p00001")
        card.wait_for(state="visible", timeout=10_000)

        paths = [url[len(root_url) :] for url in requested]
        api_paths = [p for p in paths if "/api/" in p]
        assert any(p.startswith(f"{_BASE_PATH}/api/node/") for p in api_paths), api_paths
        outside = [p for p in paths if not p.startswith(_BASE_PATH)]
        assert outside == [], f"requests escaped the prefix: {outside}"

    # Verifies: REQ-d00295-A
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00295_A_the_root_answers_nothing_and_the_address_names_the_prefix(
        self, prefixed_viewer
    ):
        import urllib.error
        import urllib.request

        root_url, base_url, log_path, _dir = prefixed_viewer
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(f"{root_url}/api/status", timeout=5)
        assert refused.value.code == 404
        with urllib.request.urlopen(f"{base_url}/", timeout=5) as resp:
            assert resp.status == 200
            assert f'URL_PREFIX = "{_BASE_PATH}"' in resp.read().decode()
        # The address the command announces is the one a browser can use.
        # The whole log, not its tail: the line is the first thing the
        # server wrote, and every request since has added a line below it.
        assert f"Starting trace-edit server at {base_url}" in log_path.read_text(errors="replace")

    # Verifies: REQ-d00295-D
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00295_D_an_agent_reaches_mcp_under_the_prefix(self, prefixed_viewer):
        pytest.importorskip("mcp")
        import asyncio

        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        _root, base_url, _log, _dir = prefixed_viewer

        async def scenario() -> list[str]:
            async with streamablehttp_client(f"{base_url}/mcp") as (read, write, _sid):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return [tool.name for tool in tools.tools]

        names = asyncio.run(asyncio.wait_for(scenario(), 60))
        assert "get_requirement" in names, names

    # Verifies: REQ-o00076-E
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_o00076_E_a_command_locating_the_viewer_reaches_it_under_the_prefix(
        self, prefixed_viewer
    ):
        """The record a prefixed viewer leaves names the prefix, and the
        unsaved-work probe every command runs through it gets an answer
        rather than the 404 of the root."""
        from elspais.mcp.daemon import get_daemon_info, get_daemon_mutation_count

        _root, _base, _log, project_dir = prefixed_viewer
        info = get_daemon_info(project_dir)
        assert info is not None, "the viewer left no record"
        assert info["type"] == "viewer"
        assert info["base_path"] == _BASE_PATH
        assert get_daemon_mutation_count(info) == 0


class TestViewerRememberedState:
    """Validates REQ-d00300: a viewer restores the Project State it saved,
    and only that, while a Reader Preference follows the reader to every
    viewer on the host.

    Every test observes what a page shows on reopening -- the filter text,
    the open cards, the theme, the font size -- and never how or where the
    page stored it. Each test that looks for state in a second viewer first
    reopens the first and sees it restored, so a save that never happened
    cannot pass as a viewer that kept to itself.
    """

    # Verifies: REQ-d00300-A
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00300_A_a_reopened_viewer_restores_its_project_state(
        self, static_viewer_site, remembering_context
    ):
        first, _second = static_viewer_site
        page = _open_viewer(remembering_context, f"{first}/a/")
        assert _project_state(page) == _NO_PROJECT_STATE, "a fresh browser restored state"
        _leave_project_state(page)
        page.close()

        reopened = _open_viewer(remembering_context, f"{first}/a/")
        assert _project_state(reopened) == _LEFT_PROJECT_STATE

    # Verifies: REQ-d00300-B
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00300_B_a_viewer_on_another_port_restores_none_of_it(
        self, static_viewer_site, remembering_context
    ):
        first, second = static_viewer_site
        page = _open_viewer(remembering_context, f"{first}/")
        _leave_project_state(page)
        page.close()
        assert _project_state(_open_viewer(remembering_context, f"{first}/")) == (
            _LEFT_PROJECT_STATE
        ), "the saving viewer did not restore its own state"

        other = _open_viewer(remembering_context, f"{second}/")
        assert _project_state(other) == _NO_PROJECT_STATE, (
            f"a viewer at {second}/ restored Project State saved at {first}/"
        )

    # Verifies: REQ-d00300-C
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00300_C_a_static_page_at_another_path_restores_none_of_it(
        self, static_viewer_site, remembering_context
    ):
        first, _second = static_viewer_site
        page = _open_viewer(remembering_context, f"{first}/a/")
        _leave_project_state(page)
        page.close()
        assert _project_state(_open_viewer(remembering_context, f"{first}/a/")) == (
            _LEFT_PROJECT_STATE
        ), "the saving viewer did not restore its own state"

        other = _open_viewer(remembering_context, f"{first}/b/")
        assert _project_state(other) == _NO_PROJECT_STATE, (
            "a page at /b/ restored Project State saved at /a/"
        )

    # Verifies: REQ-d00300-C
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00300_C_a_page_under_a_path_restores_none_of_the_roots(
        self, static_viewer_site, remembering_context
    ):
        first, _second = static_viewer_site
        page = _open_viewer(remembering_context, f"{first}/")
        _leave_project_state(page)
        page.close()
        assert _project_state(_open_viewer(remembering_context, f"{first}/")) == (
            _LEFT_PROJECT_STATE
        ), "the saving viewer did not restore its own state"

        under = _open_viewer(remembering_context, f"{first}/a/")
        assert _project_state(under) == _NO_PROJECT_STATE, (
            "a page at /a/ restored Project State saved by the viewer at /"
        )

    # Verifies: REQ-d00300-C
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00300_C_viewers_under_two_prefixes_of_one_origin_keep_apart(
        self, prefixed_viewer, second_prefixed_viewer, remembering_context
    ):
        """Two workspaces of one project served under two prefixes, seen by
        the browser at one origin.

        The edit-mode monorepo toggle is set through the page's own
        ``setMonorepoMode`` and read through ``getMonorepoMode``: the
        checkbox is drawn only when the repository status reports several
        repositories, which a single-repository fixture never does. Its
        default is on, so a second workspace reading it off is reading the
        first workspace's choice.
        """
        first_root, _first_base, _log, _dir = prefixed_viewer
        second_root, _second_base = second_prefixed_viewer
        _route_hub(
            remembering_context,
            {_BASE_PATH: first_root, _SECOND_BASE_PATH: second_root},
        )
        first_url = f"{_HUB_ORIGIN}{_BASE_PATH}/"
        second_url = f"{_HUB_ORIGIN}{_SECOND_BASE_PATH}/"

        page = _open_viewer(remembering_context, first_url)
        assert page.evaluate("() => getMonorepoMode()") is True, (
            "the monorepo toggle does not start on"
        )
        page.evaluate("() => setMonorepoMode(false)")
        _leave_project_state(page)
        page.close()

        reopened = _open_viewer(remembering_context, first_url)
        assert _project_state(reopened) == _LEFT_PROJECT_STATE, (
            "the saving viewer did not restore its own state"
        )
        assert reopened.evaluate("() => getMonorepoMode()") is False, (
            "the saving viewer did not keep its own monorepo toggle"
        )
        reopened.close()

        other = _open_viewer(remembering_context, second_url)
        observed = {
            **_project_state(other),
            "monorepo_mode": other.evaluate("() => getMonorepoMode()"),
        }
        assert observed == {**_NO_PROJECT_STATE, "monorepo_mode": True}, (
            f"the workspace at {_SECOND_BASE_PATH}/ restored Project State saved "
            f"at {_BASE_PATH}/ (a leaked filter, card or monorepo_mode=False): {observed}"
        )

    # Verifies: REQ-d00300-D
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00300_D_reader_preferences_follow_to_other_ports_and_paths(
        self, static_viewer_site, remembering_context
    ):
        first, second = static_viewer_site
        page = _open_viewer(remembering_context, f"{first}/a/")
        assert _reader_preferences(page) != _LEFT_READER_PREFERENCES, (
            "a fresh browser already applies the preferences under test"
        )
        _leave_reader_preferences(page)
        page.close()

        observed = {
            url: _reader_preferences(_open_viewer(remembering_context, url))
            for url in (f"{second}/a/", f"{first}/b/", f"{first}/")
        }
        assert observed == dict.fromkeys(observed, _LEFT_READER_PREFERENCES), observed

    # Verifies: REQ-d00300-D
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00300_D_reader_preferences_follow_across_prefixes(
        self, prefixed_viewer, second_prefixed_viewer, remembering_context
    ):
        first_root, _first_base, _log, _dir = prefixed_viewer
        second_root, _second_base = second_prefixed_viewer
        _route_hub(
            remembering_context,
            {_BASE_PATH: first_root, _SECOND_BASE_PATH: second_root},
        )
        page = _open_viewer(remembering_context, f"{_HUB_ORIGIN}{_BASE_PATH}/")
        _leave_reader_preferences(page)
        page.close()

        other = _open_viewer(remembering_context, f"{_HUB_ORIGIN}{_SECOND_BASE_PATH}/")
        assert _reader_preferences(other) == _LEFT_READER_PREFERENCES, (
            f"the workspace at {_SECOND_BASE_PATH}/ did not apply the preferences "
            f"set at {_BASE_PATH}/"
        )

    # Verifies: REQ-d00300-B, REQ-d00300-C
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00300_BC_state_not_naming_where_it_was_saved_is_not_restored(
        self, static_viewer_site, remembering_context
    ):
        """State in the form the viewer kept before it recorded where state
        was saved -- one record for the whole host -- cannot show that the
        viewer reading it saved it, so it is not restored even at the root.
        """
        import urllib.parse

        first, _second = static_viewer_site
        legacy = {
            "_v": 16,
            "editEnabled": False,
            "openCardIds": [_REMEMBERED_CARD],
            "activeNavTab": "req",
            "collapsedTreeNodes": [],
            "collapsedCards": [],
            "filterState": {
                "git": {"on": ["unsaved", "uncommitted", "changed", "unchanged"]},
                "hierarchy": {"on": ["root", "internal", "leaf"]},
                "status": {"on": ["active"]},
                "coverage": {"on": ["failing", "missing", "partial", "full"]},
                "level": {"on": ["prd", "ops", "dev"]},
                "repo": {"on": ["req"]},
                "showHiddenParents": True,
            },
            "fontSize": 14,
            "theme": "system",
            "toolbarHidden": False,
            "cardViewMode": "compact",
            "assertionBadgeMode": "abbrev",
            "viewMode": "tree",
            "treeDisplayMode": "compact",
            "levelAtEnd": False,
            "navPanelWidth": None,
            "fileViewerWidth": None,
            "refsCollapsedCards": [],
            "filterText": _REMEMBERED_FILTER,
        }
        remembering_context.add_cookies(
            [
                {
                    "name": "elspais_trace_state",
                    "value": urllib.parse.quote(json.dumps(legacy), safe=""),
                    "domain": "127.0.0.1",
                    "path": "/",
                    "expires": time.time() + 86_400,
                    "sameSite": "Lax",
                }
            ]
        )

        page = _open_viewer(remembering_context, f"{first}/")
        assert _project_state(page) == _NO_PROJECT_STATE, (
            "a viewer restored Project State from a record naming no origin or path"
        )


class TestBrowserEditControlsStateWhatTheyDo:
    """Validates REQ-d00320-A/B/C and REQ-d00211-E.

    The relationship-type test changes the project, so it runs last.
    """

    # Verifies: REQ-d00320-A
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00320_A_repository_controls_name_their_operation(
        self, page_edit_controls, edit_controls_viewer_url
    ):
        page = page_edit_controls
        page.goto(edit_controls_viewer_url, wait_until="networkidle")
        _enter_edit_mode(page)

        assert page.get_attribute("#btn-save", "title") == "Save edits to disk"
        assert page.get_attribute("#btn-checkpoint", "title") == "git commit saved edits"
        assert page.get_attribute("#btn-share", "title") == "git push the commits"

    # Verifies: REQ-d00320-B, REQ-d00320-C
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00320_BC_a_click_on_share_says_how_and_pushes_nothing(
        self, page_edit_controls, edit_controls_viewer_url
    ):
        """Share acts on a drag or a held Enter. A click shows how, and sends no push."""
        page = page_edit_controls
        pushes = _requests_to(page, "/api/git/push")
        page.goto(edit_controls_viewer_url, wait_until="networkidle")
        _enter_edit_mode(page)
        # The project has no remote, so nothing is ahead of it and Share
        # starts disabled; enable it to reach the click handler.
        page.evaluate("() => { document.getElementById('btn-share').disabled = false; }")

        page.click("#btn-share")

        hint = page.wait_for_selector("#share-hint", state="visible")
        text = hint.text_content() or ""
        assert "drag" in text and "hold Enter" in text, text
        assert "git push" in text, text
        assert hint.get_attribute("role") == "status"
        page.wait_for_timeout(1500)
        assert pushes == [], f"a click on Share sent a push: {[r.url for r in pushes]}"

    # Verifies: REQ-d00320-C
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00320_C_holding_enter_on_share_does_push(
        self, page_edit_controls, edit_controls_viewer_url
    ):
        """Companion: the gesture that operates Share does reach the push."""
        page = page_edit_controls
        pushes = _requests_to(page, "/api/git/push")
        page.goto(edit_controls_viewer_url, wait_until="networkidle")
        _enter_edit_mode(page)
        page.evaluate("() => { document.getElementById('btn-share').disabled = false; }")

        page.focus("#btn-share")
        page.keyboard.down("Enter")
        page.wait_for_timeout(1500)
        page.keyboard.up("Enter")

        deadline = time.monotonic() + 5
        while not pushes and time.monotonic() < deadline:
            page.wait_for_timeout(100)
        assert len(pushes) == 1, f"holding Enter sent {len(pushes)} pushes"
        assert pushes[0].method == "POST"

    # Verifies: REQ-d00211-E
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00211_E_one_control_offers_every_relationship_type(
        self, page_edit_controls, edit_controls_viewer_url
    ):
        page = page_edit_controls
        base = edit_controls_viewer_url
        edge_posts = _requests_to(page, "/api/mutate/edge")
        page.goto(base, wait_until="networkidle")
        _enter_edit_mode(page)
        page.evaluate(f"() => window.openCard('{_EDIT_CONTROLS_CITING}')")
        card = page.locator(f"#card-{_EDIT_CONTROLS_CITING}")
        card.wait_for(state="visible", timeout=10_000)
        card.locator(".outgoing-link-toggle").first.click()

        control = card.locator(".card-parent-kind-select")
        assert control.count() == 1, "the relationship has no single type control"
        assert card.locator(".card-parent-kind-toggle").count() == 0
        options = control.locator("option").evaluate_all(
            "(opts) => opts.filter(o => !o.disabled).map(o => o.value)"
        )
        assert options == ["implements", "refines", "satisfies"], options
        assert control.input_value() == "implements"

        control.select_option("refines")

        deadline = time.monotonic() + 5
        while not edge_posts and time.monotonic() < deadline:
            page.wait_for_timeout(100)
        assert len(edge_posts) == 1, f"{len(edge_posts)} edge requests sent"
        sent = json.loads(edge_posts[0].post_data or "{}")
        assert sent["action"] == "change_kind"
        assert sent["new_kind"] == "refines"
        assert sent["source_id"] == _EDIT_CONTROLS_CITING
        assert sent["target_id"] == _EDIT_CONTROLS_CITED

        node = page.request.get(f"{base}/api/node/{_EDIT_CONTROLS_CITING}").json()
        kinds = [p["edge_kind"] for p in node["parents"] if p["id"] == _EDIT_CONTROLS_CITED]
        assert kinds == ["refines"], node["parents"]


class TestBrowserSaveDisclosesTextNoEditChanged:
    """Validates REQ-d00320-D."""

    # Verifies: REQ-d00320-D
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00320_D_save_lists_the_parts_it_changed_beyond_the_edit(
        self, page_save_disclosure, save_disclosure_viewer_url
    ):
        page = page_save_disclosure
        js_errors: list[str] = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))
        page.goto(save_disclosure_viewer_url, wait_until="networkidle")
        _enter_edit_mode(page)

        edited = page.evaluate(
            """async () => await mutate('/api/mutate/title',
                {node_id: 'REQ-d00001', new_title: 'Beta Renamed'})"""
        )
        assert edited and edited.get("success"), edited
        page.wait_for_selector("#btn-save:not([disabled])", timeout=10_000)
        saves: list = []
        page.on("response", lambda r: saves.append(r) if r.url.endswith("/api/save") else None)
        page.click("#btn-save")

        try:
            overlay = page.wait_for_selector("#save-disclosure-overlay", timeout=10_000)
        except PlaywrightTimeoutError:
            bodies = [r.text() for r in saves]
            pytest.fail(f"no disclosure after save; /api/save answered {bodies}, JS {js_errors}")
        named = page.locator("#save-disclosure-overlay li.save-disclosure-item").evaluate_all(
            "(items) => items.map(i => i.dataset.nodeId)"
        )
        assert "REQ-d00002" in named, named
        assert "REQ-d00001" not in named, named
        assert any(n.startswith("rem:") for n in named), named
        assert len(named) == 2, named
        assert overlay.is_visible()
        assert not js_errors, f"JS errors on save: {js_errors}"

        page.click("#save-disclosure-dismiss")
        page.wait_for_selector("#save-disclosure-overlay", state="detached")


class TestBrowserSaveReportsRefusal:
    """Validates REQ-p00015-B."""

    # Verifies: REQ-p00015-B
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_p00015_B_refused_save_names_its_cause_and_keeps_the_edit(
        self, page_refused_save, refused_save_viewer
    ):
        page = page_refused_save
        base_url, project = refused_save_viewer
        spec_file = project / "spec" / "dev.md"
        before = spec_file.read_text(encoding="utf-8")
        js_errors: list[str] = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))
        page.goto(base_url, wait_until="networkidle")
        _enter_edit_mode(page)

        edited = page.evaluate(
            f"""async () => await mutate('/api/mutate/title',
                {{node_id: '{_EDIT_CONTROLS_CITING}', new_title: 'Citing Renamed'}})"""
        )
        assert edited and edited.get("success"), edited
        # The save the reader answers with a reason is refused by the write
        # itself: the reason prompt is something the viewer can answer, a
        # write that failed is not. The first, reasonless save reaches the
        # server, which asks for the reason.
        cause = "save failed: PermissionError(13, 'Permission denied')"

        def _refuse_the_write(route):
            body = route.request.post_data_json or {}
            if body.get("message"):
                route.fulfill(
                    status=500,
                    content_type="application/json",
                    body=json.dumps({"success": False, "code": "save_failed", "error": cause}),
                )
            else:
                route.continue_()

        page.route("**/api/save", _refuse_the_write)
        page.wait_for_selector("#btn-save:not([disabled])", timeout=10_000)
        saves: list = []
        page.on("response", lambda r: saves.append(r) if r.url.endswith("/api/save") else None)
        page.click("#btn-save")
        page.wait_for_selector("#changelog-reason-overlay", timeout=10_000)
        page.fill("#changelog-reason-input", "a reason the write will not reach")
        page.click("#changelog-reason-submit")

        try:
            overlay = page.wait_for_selector("#error-modal-overlay", timeout=10_000)
        except PlaywrightTimeoutError:
            bodies = [(r.status, r.text()) for r in saves]
            pytest.fail(f"no error shown for a refused save; /api/save answered {bodies}")
        assert overlay.is_visible()
        assert [r.status for r in saves] == [400, 500]
        shown = page.locator("#error-modal-overlay").inner_text()
        assert "Save failed" in shown, shown
        assert cause in shown, shown

        dirty = page.request.get(f"{base_url}/api/dirty").json()
        assert dirty.get("mutation_count", 0) > 0, dirty
        assert spec_file.read_text(encoding="utf-8") == before
        assert not js_errors, f"JS errors on save: {js_errors}"
