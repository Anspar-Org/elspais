"""Playwright-based browser tests for the viewer's pending-work indicator,
its unload warning and the operations it refuses under an unknown count."""

import time
from datetime import datetime

import pytest

pytest.importorskip("playwright", reason="playwright not installed")


from ..helpers import resolve_elspais  # noqa: E402
from .support import (  # noqa: E402
    _ADOPTION_DELAY_SECONDS,
    _ARMED_PHRASE,
    _BADGE_HEARTBEAT_SECONDS,
    _CYCLE_TIMEOUT,
    _JUDGEMENT_TIMEOUT,
    _UNLOAD_STATE_KEYS,
    _attempt_title_mutation,
    _await_cycle,
    _badge_state,
    _beforeunload_messages,
    _close_observing_beforeunload,
    _console_sink,
    _create_pending_mutation,
    _dom_present,
    _error_modal_text,
    _go_unknown,
    _has_unload_state,
    _offer,
    _pr_route_recorder,
    _refresh_dirty,
    _revert_to_zero,
    _server_dirty,
    _unload_state,
    _wait_for_js,
)

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        resolve_elspais() is None,
        reason="elspais CLI not found on PATH",
    ),
]


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
        assert "hidden" in state["classes"], (
            f"server reported 0 pending: badge must be hidden, got classes {state['classes']}"
        )
        assert state["count"] == 0, f"editState.mutationCount must be 0, got {state['count']!r}"
        assert state["count_type"] == "number", (
            f"a reported count is a number, got type {state['count_type']!r}"
        )

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
        assert reported["text"] == str(pending), (
            f"precondition: badge must show the server's count {pending}, got {reported['text']!r}"
        )
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
        assert "unreachable" in state["title"].lower(), (
            f"unknown badge title must name the unreachable server, got {state['title']!r}"
        )
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
        assert after == before, (
            f"a failed /api/dirty fetch must leave lastSeenTip untouched: {before!r} -> {after!r}"
        )

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
        assert "unknown" not in state["classes"], (
            f"the unknown presentation must be replaced, got {state['classes']}"
        )
        assert "hidden" not in state["classes"], state["classes"]
        assert state["count"] == pending, (
            f"editState.mutationCount must be the reported count {pending}, got {state['count']!r}"
        )

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
        assert isinstance(state["willWarnOnClose"], bool), (
            f"willWarnOnClose must be a boolean decision, got {state['willWarnOnClose']!r}"
        )
        assert isinstance(state["countKnown"], bool), (
            f"countKnown must be a boolean, got {state['countKnown']!r}"
        )

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
        assert state["pendingCount"] == pending, (
            f"pendingCount must be the server's count {pending}, got {state['pendingCount']!r}"
        )
        assert state["countKnown"] is True, (
            f"a server-reported count is known, got countKnown={state['countKnown']!r}"
        )
        assert state["countSource"] == "server", (
            f"the count came from the server, got countSource={state['countSource']!r}"
        )
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
            f"an unverifiable claim must not arm the warning; reported decision was {state!r}"
        )
        assert state["pendingCount"] is None, (
            f"an unknown count must be reported as null, got {state['pendingCount']!r}"
        )
        assert state["countKnown"] is False, (
            f"countKnown must be false while unreachable, got {state['countKnown']!r}"
        )
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
            f"a server-reported zero must leave the warning disarmed, got {reported_zero!r}"
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
        assert not any("not warning" in m for m in reported), (
            f"the armed record must not read as a not-warning decision: {reported!r}"
        )

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


class TestBrowserPendingWorkUnderPartialFailure:
    """Validates REQ-d00267-A, REQ-d00267-B, REQ-o00079-C, REQ-o00079-D,
    REQ-o00079-E: the pending-change count is established by, and only by,
    the count endpoint — on every announcement the server makes over the
    stream the page holds, and honestly when the answer is unusable.

    Partial failure is the interesting case. One endpoint going down while
    another stays healthy must not let the healthy one's silence, or the
    broken one's noise, speak for the count: a failure elsewhere that pins the
    badge to unknown disarms the navigation warning forever, and a malformed
    answer read as zero hides real work.
    """

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00267_A_stream_cycle_drives_the_count(self, page_badge, badge_viewer_url):
        # Verifies: REQ-d00267-A, REQ-o00079-D
        """The stream is the page's only count heartbeat: an idle page whose
        server dies must notice without any mutation or reload. Every
        announcement runs one cycle, and that cycle alone — never
        refreshDirtyCount() directly — must turn the count unknown, and must
        recover it once the server answers again."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Stream Heartbeat")
        _refresh_dirty(page)
        assert _badge_state(page)["count_type"] == "number", "precondition: count must start known"

        # Only the count endpoint dies; the stream keeps announcing, so an
        # unknown count here can only have come from the count probe itself.
        page.route("**/api/dirty", lambda route: route.abort())
        _await_cycle(page)
        _wait_for_js(
            page,
            "() => editState.mutationCount === null",
            "a stream cycle with the count endpoint down must mark the count "
            "unknown; the page went on presenting a count it could not confirm",
        )
        assert _badge_state(page)["text"] == "?", _badge_state(page)

        page.unroute("**/api/dirty")
        _await_cycle(page)
        _wait_for_js(
            page,
            "() => typeof editState.mutationCount === 'number'",
            "a stream cycle after the server recovered must re-establish the count",
            timeout=_CYCLE_TIMEOUT,
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_o00079_E_lost_stream_reprobes_and_does_not_speak_for_the_count(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-o00079-E, REQ-d00267-A
        """A lost handle re-establishes the count, and only /api/dirty may
        say what it is. The stream is lost while the count endpoint stays
        healthy, so the count must come back known: presenting it as unknown
        would pin the badge at '?' and disarm the navigation warning for as
        long as the stream stayed broken even though the server was
        answering. The count's record is cleared only after the page holds
        the stream, so what stamps it next can only be the loss itself."""
        page = page_badge
        pending = _create_pending_mutation(page, badge_viewer_url, "Badge Stream Down")
        page.goto(badge_viewer_url, wait_until="networkidle")
        _wait_for_js(
            page,
            "() => editState.lastAnnouncedTip !== null",
            "the page must hold the stream before it can lose it",
        )

        # From here the server declines every attempt to hold the stream.
        # The page drops the handle it has and seeks it again, which is what
        # its own retry does after a loss; the refusal it meets is the loss.
        page.route("**/api/events", lambda route: route.abort())
        page.evaluate(
            """() => {
                editState.dirtyCountAt = null;
                _eventSource.close();
                _eventSource = null;
                connectServerEvents();
            }"""
        )
        # Sooner than the silence watch could fire (twice the announced
        # interval), so the probe can only be the lost handle's.
        _wait_for_js(
            page,
            "() => _eventSource === null && editState.dirtyCountAt !== null",
            "a lost stream must release the handle and re-establish the count",
            timeout=_BADGE_HEARTBEAT_SECONDS * 2 - 1.0,
        )
        assert page.evaluate("() => editState.dirtyCountSource") == "server"
        state = _badge_state(page)
        assert state["text"] == str(pending), (
            f"/api/dirty is healthy, so the count is knowable; a lost stream "
            f"must not present it as unknown (badge {state['text']!r}, "
            f"classes {state['classes']})"
        )
        assert "unknown" not in state["classes"], state["classes"]
        assert _unload_state(page)["willWarnOnClose"] is True, (
            "work is pending and the count endpoint is healthy, so the "
            "navigation warning must be armed"
        )
        page.unroute("**/api/events")

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_o00079_E_silence_past_the_promised_interval_reprobes_the_count(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-o00079-E
        """Silence is a cycle too. With the stream closed on the page's side
        nothing can arrive, and the interval the page holds the server to is
        shortened so the silence is noticed within the test's patience; the
        only thing that can then re-establish the count is the page noticing
        that nothing announced itself -- and it must keep noticing."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")
        _wait_for_js(
            page,
            "() => editState.lastAnnouncedTip !== null",
            "the page must hear the server before it can miss it",
        )
        page.evaluate(
            """() => {
                _eventSource.close();
                _eventSource = null;
                editState.dirtyCountAt = null;
                _heartbeatMs = 200;
                armSilenceWatch();
            }"""
        )
        _wait_for_js(
            page,
            "() => editState.dirtyCountAt !== null",
            "nothing was announced for twice the promised interval, so the "
            "page must re-establish the count on its own",
            timeout=1.5,
        )
        assert page.evaluate("() => editState.dirtyCountSource") == "server"
        page.evaluate("() => { editState.dirtyCountAt = null; }")
        _wait_for_js(
            page,
            "() => editState.dirtyCountAt !== null",
            "the silence must keep being noticed, not noticed once",
            timeout=1.5,
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_o00079_E_a_server_that_stops_answering_is_presented_as_one(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-o00079-E, REQ-d00267-B
        """The reason the handle's loss re-establishes the count: a server
        that has gone must show as one. The tab loses its network -- the
        held stream drops without the page doing anything -- and the count
        must turn unknown through the failing probe; once the network is
        back the page's own retry must re-hold the stream and recover it."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")
        _wait_for_js(
            page,
            "() => editState.lastAnnouncedTip !== null",
            "the page must hold the stream before it can lose it",
        )
        page.evaluate("() => { editState.dirtyCountAt = null; }")
        page.context.set_offline(True)
        try:
            _wait_for_js(
                page,
                "() => editState.dirtyCountAt !== null",
                "the stream dropped, so the count must be re-established",
                timeout=_BADGE_HEARTBEAT_SECONDS * 2 - 1.0,
            )
            assert page.evaluate("() => editState.dirtyCountSource") == "unreachable"
            assert _badge_state(page)["text"] == "?", _badge_state(page)
        finally:
            page.context.set_offline(False)
        _wait_for_js(
            page,
            "() => _eventSource !== null && editState.dirtyCountSource === 'server'",
            "once the server answers again the page must re-hold the stream and recover the count",
            timeout=_CYCLE_TIMEOUT,
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_o00079_C_another_writers_change_is_announced_and_its_tip_not_adopted(
        self, page_badge, badge_viewer_url
    ):
        # Verifies: REQ-o00079-C, REQ-d00267-A
        """Another writer's mutation reaches the page as an announcement, not
        at a poll: the 'Another writer changed the graph' banner raises within
        the server's wake, and the cycle's count probe must not record the
        change history as seen. Adopting the announced tip would mark another
        writer's mutations as already-looked-at and the banner could never
        raise again — the stream would silently destroy the very warning it
        exists to carry."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")

        _create_pending_mutation(page, badge_viewer_url, "Badge Tip Baseline")
        _refresh_dirty(page)
        seen_before = _badge_state(page)["tip"]
        assert seen_before, f"precondition: a baseline tip must be recorded, got {seen_before!r}"
        # The baseline mutation is itself announced; let that announcement
        # land and clear whatever it raised, so what follows is attributable
        # to the other writer alone.
        _wait_for_js(
            page,
            f"() => editState.lastAnnouncedTip === {seen_before!r}",
            "the baseline mutation must be announced over the stream",
        )
        page.evaluate("() => dismissStaleBanner()")

        # Another writer moves the graph behind this page's back.
        _create_pending_mutation(page, badge_viewer_url, "Badge Tip Other Writer")
        other_tip = _server_dirty(page, badge_viewer_url).get("tip")
        assert other_tip and other_tip != seen_before, (
            f"precondition: the other writer must have advanced the tip "
            f"{seen_before!r} -> {other_tip!r}"
        )

        _wait_for_js(
            page,
            "() => { const b = document.getElementById('stale-banner');"
            " return b && !b.classList.contains('hidden'); }",
            "another writer moved the tip, so the announcement must raise the "
            "'Another writer changed the graph' banner",
        )
        assert page.evaluate("() => editState.lastAnnouncedTip") == other_tip, (
            "the announcement must carry the other writer's tip"
        )
        assert _badge_state(page)["tip"] == seen_before, (
            f"the cycle must not record history it never showed the operator as "
            f"seen: lastSeenTip moved {seen_before!r} -> "
            f"{_badge_state(page)['tip']!r}"
        )

    @pytest.mark.browser
    @pytest.mark.e2e
    @pytest.mark.parametrize("edits", [1, 2])
    def test_REQ_o00079_C_the_pages_own_edits_are_not_another_writers(
        self, page_badge, badge_viewer_url, edits
    ):
        # Verifies: REQ-o00079-C
        """The announcement of this page's own edit arrives within the
        server's wake, and must not be read as somebody else's change. Here
        it always arrives first: the count probe that adopts the first edit's
        tip is held past the wake, so the announcement outruns the page's
        bookkeeping and is held back. One edit is the plain case. Two edits
        is the case where the second lands and is adopted at once, inside
        the settle window of the first: what is judged when the held-back
        announcement is finally weighed must be the tip last announced, not
        the one the page had in hand when it began waiting."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")
        _refresh_dirty(page)
        page.evaluate("() => dismissStaleBanner()")

        # Only the first edit's adopting probe is held -- the first count
        # request after it. The stream's own cycles probe the same endpoint,
        # and holding those too would queue them ahead of the adoption and
        # push it past the settle window, which is not the case under test.
        hold_next = [True]

        def _slow_adoption(route):
            if hold_next[0]:
                hold_next[0] = False
                time.sleep(_ADOPTION_DELAY_SECONDS)
            route.continue_()

        page.route("**/api/dirty", _slow_adoption)
        try:
            for n in range(edits):
                _attempt_title_mutation(page, f"Badge Own Edit Announced {n + 1}")
        finally:
            page.unroute("**/api/dirty")
        tip = _server_dirty(page, badge_viewer_url).get("tip")
        _wait_for_js(
            page,
            f"() => editState.lastAnnouncedTip === {tip!r}",
            "the page's own edit must be announced over the stream",
        )
        # The verdict is observed, not timed: an announced tip is held back
        # while a write of the page's own is recent, and the page holds at
        # most one such judgement.
        _wait_for_js(
            page,
            "() => _tipJudgement === null",
            "an announced tip held back for the page's own write must be judged once it settles",
            timeout=_JUDGEMENT_TIMEOUT,
        )
        assert page.evaluate(
            "() => { const b = document.getElementById('stale-banner');"
            " return b && b.classList.contains('hidden'); }"
        ), "the page's own edit was announced back to it as another writer's"
        assert _badge_state(page)["tip"] == tip, "the page's own write must be adopted as seen"

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
            "with the server reporting nothing pending the branch picker must open normally",
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
        assert "unknown" in text, (
            f"the refusal must name the reason — the count is unknown; got {text!r}"
        )

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


class TestBrowserPullRequestModal:
    """Validates REQ-d00297-A, REQ-d00297-C: a pushed branch is proposed from
    the page, the proposal carries what the person typed and names where it
    goes, and a push that carried several repositories is not answered by a
    dialog proposing one of them without saying which."""

    # Verifies: REQ-d00297-A
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00297_A_a_pushed_branch_is_proposed_with_what_was_typed(
        self, page_badge, badge_viewer_url
    ):
        """The dialog appears after a push, sends the title and description
        the person typed, and puts the pull request it is told about in front
        of them as something they can follow."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")
        sent = _pr_route_recorder(
            page,
            {
                "success": True,
                "url": "https://github.com/o/r/pull/41",
                "number": 41,
                "existing": False,
            },
        )

        _offer(page, {"success": True, "branch": "badge-truth"})
        page.wait_for_selector("#pr-modal-overlay", state="visible")
        page.fill("#pr-title-input", "Propose the badge work")
        page.fill("#pr-body-input", "What it changes and why")
        page.click("#pr-modal-submit")

        page.wait_for_function("() => !document.getElementById('pr-modal-overlay')")
        assert sent == [{"title": "Propose the badge work", "body": "What it changes and why"}]

        link = page.wait_for_selector("#toast-container a")
        assert link.get_attribute("href") == "https://github.com/o/r/pull/41"
        assert link.get_attribute("target") == "_blank"
        assert "41" in link.text_content()

    # Verifies: REQ-d00297-C
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00297_C_a_refusal_is_shown_and_the_dialog_stays_open(
        self, page_badge, badge_viewer_url
    ):
        """A refusal is put in front of the person in the dialog they are in,
        so the condition it names is read where the work still is."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")
        _pr_route_recorder(
            page,
            {"success": False, "error": "Branch 'badge-truth' is not on the remote yet"},
            status=400,
        )

        _offer(page, {"success": True, "branch": "badge-truth"})
        page.wait_for_selector("#pr-modal-overlay", state="visible")
        page.click("#pr-modal-submit")

        page.wait_for_function(
            "() => { const e = document.getElementById('pr-modal-error');"
            " return e && !e.classList.contains('hidden'); }"
        )
        assert "not on the remote yet" in page.text_content("#pr-modal-error")
        assert page.is_visible("#pr-modal-overlay")

    # Verifies: REQ-d00297-A+C
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00297_A_a_push_across_repositories_is_not_answered_by_one_dialog(
        self, page_badge, badge_viewer_url
    ):
        """A pull request proposes one repository. A push that carried
        several is told about, rather than answered by a dialog proposing
        whichever one the server would resolve to."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")
        sent = _pr_route_recorder(page, {"success": True, "url": "x", "number": 1})

        _offer(
            page,
            {
                "success": True,
                "results": [
                    {"repo": "core", "success": True, "branch": "badge-truth"},
                    {"repo": "lib", "success": True, "branch": "badge-truth"},
                ],
            },
        )

        page.wait_for_selector("#toast-container .toast")
        assert not _dom_present(page, "#pr-modal-overlay")
        assert "one at a time" in page.text_content("#toast-container")
        assert sent == []

    # Verifies: REQ-d00297-A
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00297_A_a_push_that_carried_one_repository_names_it(
        self, page_badge, badge_viewer_url
    ):
        """Where the push carried exactly one repository there is no doubt
        which is proposed — so it is proposed, named in the dialog and named
        in what the dialog sends."""
        page = page_badge
        page.goto(badge_viewer_url, wait_until="networkidle")
        sent = _pr_route_recorder(
            page, {"success": True, "url": "https://github.com/o/r/pull/8", "number": 8}
        )

        _offer(
            page,
            {
                "success": True,
                "results": [{"repo": "core", "success": True, "branch": "badge-truth"}],
            },
        )

        page.wait_for_selector("#pr-modal-overlay", state="visible")
        assert "core" in page.text_content("#pr-modal-overlay .modal-title")
        page.fill("#pr-title-input", "Propose core")
        page.click("#pr-modal-submit")

        page.wait_for_function("() => !document.getElementById('pr-modal-overlay')")
        assert sent == [{"title": "Propose core", "body": "", "repo": "core"}]
