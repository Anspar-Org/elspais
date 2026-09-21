#!/bin/bash
# =====================================================
# lib-tier-run: run a long test stage so that killing the hook
#               does not kill the run
# =====================================================
#
# A test tier here runs for minutes. The hook that starts it is a child of
# `git`, and git's caller is often something with a timeout — an agent
# session's command limit, a terminal that is closed, a remote that drops an
# idle connection. When that timeout fires the whole process group dies, and
# the tier, started in the foreground, dies with it: partway through, with
# nothing recorded.
#
# That is worse than losing the time. pytest-cov gives each process its own
# `.coverage.<host>.pid<N>.<suffix>` shard and combines them at the end; a
# process killed before it writes that file's schema leaves a shard with no
# `context` table, and the NEXT run fails every test's coverage teardown with
# `no such table: context` while reporting every test as passed. One killed
# run therefore blocks the following commit for a reason that is nowhere in
# the code.
#
# So the tier is run in its own session. The hook waits on it and relays its
# output, but nothing that reaches the hook reaches the run. A hook that is
# killed and invoked again ATTACHES to the run still going rather than
# starting a second one, so the minutes already spent are never thrown away —
# and if the run finished while no hook was watching, it has already recorded
# its own verdict, so the next invocation is a cache hit.
#
# Sourced by pre-commit, pre-push and e2e-verdict. Do not run a tier any other
# way from a hook.

# Remove coverage shards abandoned by runs that are no longer alive.
#
# The owning pid is in the filename, so this is decided per file rather than
# by clearing the directory: a shard whose process is still running belongs to
# a live tier and must survive, and the sweep is safe beside one.
tier_sweep_dead_coverage_shards() {
    _root="$1"
    for _shard in "$_root"/.coverage.*; do
        [ -e "$_shard" ] || continue
        _spid=$(printf '%s' "${_shard##*/}" | sed -n 's/.*\.pid\([0-9][0-9]*\)\..*/\1/p')
        [ -n "$_spid" ] || continue
        if kill -0 "$_spid" 2>/dev/null; then continue; fi
        rm -f "$_shard"
        # To stderr: callers capture this function's caller's stdout for the
        # exit code, and a stray line there becomes part of the "code".
        echo "  swept an abandoned coverage shard: ${_shard##*/}" >&2
    done
}

# Is the run recorded in this state directory still going?
tier_run_alive() {
    _dir="$1"
    [ -f "$_dir/pid" ] || return 1
    _rpid=$(cat "$_dir/pid" 2>/dev/null) || return 1
    [ -n "$_rpid" ] || return 1
    kill -0 "$_rpid" 2>/dev/null
}

tier_run_key() {
    _dir="$1"
    if [ -f "$_dir/key" ]; then cat "$_dir/key" 2>/dev/null; fi
}

# tier_start <state-dir> <key> <repo-root> <finisher-or-empty> <cmd> [args...]
#
# Writes <state-dir>/{pid,key,log,rc}. The finisher, when given, is a script
# run after the command with the command's exit code as $1; it runs inside the
# detached session too, so whatever it records — a verdict, a cache key, a
# formatted artifact — is recorded even when no hook is left watching.
tier_start() {
    _dir="$1"; shift
    _key="$1"; shift
    _root="$1"; shift
    _finisher="$1"; shift

    mkdir -p "$_dir"
    rm -f "$_dir/rc" "$_dir/pid"
    : > "$_dir/log"
    printf '%s\n' "$_key" > "$_dir/key"

    {
        printf '#!/bin/bash\n'
        printf 'cd %q || exit 99\n' "$_root"
        printf 'exec'
        for _a in "$@"; do printf ' %q' "$_a"; done
        printf '\n'
    } > "$_dir/cmd.sh"

    {
        printf '#!/bin/bash\n'
        printf 'echo $$ > %q\n' "$_dir/pid"
        printf 'bash %q >> %q 2>&1\n' "$_dir/cmd.sh" "$_dir/log"
        printf '_rc=$?\n'
        if [ -n "$_finisher" ]; then
            printf 'bash %q "$_rc" >> %q 2>&1\n' "$_finisher" "$_dir/log"
        fi
        printf 'echo "$_rc" > %q\n' "$_dir/rc"
    } > "$_dir/run.sh"

    # setsid puts it in a session of its own: the hook's process group can be
    # signalled without reaching it. </dev/null so it never blocks on a
    # terminal that is going away, and its output goes to the log rather than
    # to a stdout that may close under it.
    setsid bash "$_dir/run.sh" < /dev/null > /dev/null 2>&1 &

    _waited=0
    while [ ! -f "$_dir/pid" ] && [ "$_waited" -lt 50 ]; do
        sleep 0.1
        _waited=$((_waited + 1))
    done
    if [ ! -f "$_dir/pid" ]; then
        echo "ERROR: the detached run never reported a pid" >&2
        return 1
    fi
}

# tier_wait <state-dir> — relay the run's output, then echo its exit code.
#
# Always returns 0: the tier's verdict is the echoed code, and a caller under
# `set -e` must get the chance to read it. An exit code of 137 stands for "the
# run ended without recording one", which is what a run killed outside this
# machinery looks like.
tier_wait() {
    _dir="$1"
    _rpid=$(cat "$_dir/pid" 2>/dev/null) || _rpid=""

    if [ -n "$_rpid" ]; then
        # Exits by itself when the run does; killed with the hook otherwise,
        # which is the point — the run behind it keeps going.
        #
        # To stderr, not stdout: this function's stdout carries the exit code
        # and the caller captures it. Relaying the tier's output there instead
        # would swallow the whole log into the caller's variable and leave the
        # user watching nothing.
        # Order matters: `>&2` first, so stdout takes the caller's real
        # stderr, and only then is tail's own stderr discarded.
        tail -f -n +1 --pid="$_rpid" "$_dir/log" >&2 2>/dev/null
    fi

    _waited=0
    while [ ! -f "$_dir/rc" ] && [ "$_waited" -lt 30 ]; do
        sleep 1
        _waited=$((_waited + 1))
    done

    if [ -f "$_dir/rc" ]; then
        cat "$_dir/rc"
    else
        echo 137
    fi
    return 0
}

# tier_execute <state-dir> <key> <repo-root> <label> <finisher-or-empty> <cmd> [args...]
#
# Attach if this key's run is already going, refuse if a different one is,
# start one otherwise. Echoes the exit code; always returns 0.
tier_execute() {
    _dir="$1"
    _key="$2"
    _root="$3"
    _label="$4"
    shift 4
    # What remains is tier_start's tail: the finisher, then the command.

    if tier_run_alive "$_dir"; then
        if [ "$(tier_run_key "$_dir")" = "$_key" ]; then
            echo "  attaching to the $_label run already in progress (pid $(cat "$_dir/pid"))" >&2
            tier_wait "$_dir"
            return 0
        fi
        echo "ERROR: a $_label run for a different tree is in progress (pid $(cat "$_dir/pid"))." >&2
        echo "       Two test runs in one worktree corrupt each other's coverage data." >&2
        echo "       Wait for it, or stop it and remove $_dir/pid." >&2
        echo 1
        return 0
    fi

    tier_sweep_dead_coverage_shards "$_root"

    if ! tier_start "$_dir" "$_key" "$_root" "$@"; then
        echo 1
        return 0
    fi
    tier_wait "$_dir"
    return 0
}
