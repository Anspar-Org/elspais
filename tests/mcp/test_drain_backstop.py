# Verifies: REQ-p00083-A+D
"""A drain that cannot finish must not strand the work or lie about it.

A client holding an MCP stream keeps an in-flight request open, so the
server's drain never completes. The process must still account for what it
holds -- REQ-p00083-A obliges it to persist work whenever it executes its
own ending -- and must not report that ending as clean when it gave up on
it. An exit status of success for an abandoned drain is the same defect as
a mutation acknowledged and dropped: an action represented as performed
whose effect is not what the report claims.
"""

from __future__ import annotations

import time

from elspais.mcp.shared_state import SharedServerState, arm_drain_backstop


class TestDrainBackstop:
    def test_REQ_p00083_A_backstop_accounts_for_work_before_exiting(self, tmp_path):
        """Validates REQ-p00083-A: the backstop runs the shutdown routine
        before it exits, so an abandoned drain still writes what the process
        holds rather than taking it down with the process."""
        order: list[str] = []
        state = SharedServerState()
        state["working_dir"] = tmp_path
        arm_drain_backstop(
            state,
            seconds=0.05,
            finalize_fn=lambda: order.append("finalized") or {"success": True},
            exit_fn=lambda code: order.append(f"exit:{code}"),
        )
        time.sleep(0.4)
        assert order and order[0] == "finalized", f"exited without accounting: {order}"
        assert any(o.startswith("exit:") for o in order)

    def test_REQ_p00083_D_abandoned_drain_exits_non_zero(self, tmp_path):
        """Validates REQ-p00083-D: giving up on a drain is reported, not
        dressed as a clean stop. A supervisor that cannot tell an abandoned
        shutdown from a completed one cannot act on the difference."""
        codes: list[int] = []
        state = SharedServerState()
        state["working_dir"] = tmp_path
        arm_drain_backstop(
            state,
            seconds=0.05,
            finalize_fn=lambda: {"success": True},
            exit_fn=codes.append,
        )
        time.sleep(0.4)
        assert codes and codes[0] != 0, f"abandoned drain reported success: {codes}"

    def test_REQ_p00083_A_completed_drain_is_not_forced(self, tmp_path):
        """Validates REQ-p00083-A: the backstop is a bound on a stall, not a
        deadline every shutdown races. A drain that completes must leave no
        forced exit behind it."""
        codes: list[int] = []
        state = SharedServerState()
        state["working_dir"] = tmp_path
        cancel = arm_drain_backstop(
            state,
            seconds=0.3,
            finalize_fn=lambda: {"success": True},
            exit_fn=codes.append,
        )
        cancel()
        time.sleep(0.5)
        assert codes == [], "a completed drain still forced an exit"

    def test_REQ_p00083_A_arming_twice_leaves_one_backstop(self, tmp_path):
        """Validates REQ-p00083-A: a stop reached through two paths (a
        client's stop request, whose signal then lands in the same handler)
        must leave one bound behind it, not two. A second timer nobody holds
        a handle to would force an exit after a drain that finished."""
        codes: list[int] = []
        state = SharedServerState()
        state["working_dir"] = tmp_path
        first = arm_drain_backstop(
            state,
            seconds=0.2,
            finalize_fn=lambda: {"success": True},
            exit_fn=codes.append,
        )
        second = arm_drain_backstop(
            state,
            seconds=0.2,
            finalize_fn=lambda: {"success": True},
            exit_fn=codes.append,
        )
        # Either handle cancels the one armed bound.
        second()
        time.sleep(0.5)
        assert codes == [], f"a second backstop survived the cancel: {codes}"
        # The handles address the same bound, so the first is a no-op now.
        first()

    def test_REQ_p00083_D_failed_save_still_exits_non_zero(self, tmp_path):
        """Validates REQ-p00083-D: a backstop whose save fails still ends the
        process, and does not report the ending as clean. The process has
        already committed to stopping and refuses writes, so staying up would
        be a hang no client could rescue; the failure is what the status and
        the log say."""
        codes: list[int] = []
        state = SharedServerState()
        state["working_dir"] = tmp_path
        arm_drain_backstop(
            state,
            seconds=0.05,
            finalize_fn=lambda: {"success": False, "pending": 3, "error": "disk full"},
            exit_fn=codes.append,
        )
        time.sleep(0.4)
        assert codes and codes[0] != 0, f"a failed save exited clean: {codes}"
