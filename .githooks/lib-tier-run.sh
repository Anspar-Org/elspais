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
# So the tier is run in its own process group. The hook waits on it and
# relays its output, but nothing that reaches the hook reaches the run. A
# hook that is killed and invoked again ATTACHES to the run still going
# rather than starting a second one, so the minutes already spent are never
# thrown away — and if the run finished while no hook was watching, it has
# already recorded its own verdict, so the next invocation is a cache hit.
#
# Sourced by unit-verdict, e2e-verdict and run-target (which the Makefile's
# test targets call). Do not run a tier any other way.

# tier_require <command> -- stop naming the command when it is not on PATH.
#
# Every dependency this runner cannot do without is checked here, once, at
# the point it is needed, rather than discovered as an unexplained failure
# partway through a run.
tier_require() {
    if ! command -v "$1" > /dev/null 2>&1; then
        echo "ERROR: this machine has no '$1', which the test runner requires." >&2
        return 1
    fi
    return 0
}

# tier_pid_args <pid> -- print the command line of a live process.
#
# Read from /proc where there is one, which no terminal width can cut short;
# otherwise from `ps -ww`, which asks for the whole line. Returns 1 when
# neither can say -- a slim container ships no `ps` -- and the caller then
# decides on liveness alone rather than reading an empty line as "something
# else".
tier_pid_args() {
    if [ -r "/proc/$1/cmdline" ]; then
        tr '\0' ' ' < "/proc/$1/cmdline"
        return 0
    fi
    if command -v ps > /dev/null 2>&1; then
        _pargs=$(ps -ww -o args= -p "$1" 2>/dev/null) || _pargs=""
        if [ -n "$_pargs" ]; then
            printf '%s\n' "$_pargs"
            return 0
        fi
    fi
    return 1
}

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
        # A shard is written by a Python process. A live pid running anything
        # else is a number reused after the writer died, and its shard is
        # abandoned like any other.
        if kill -0 "$_spid" 2>/dev/null; then
            if ! _sargs=$(tier_pid_args "$_spid"); then continue; fi
            case "$_sargs" in
                *python*|*pytest*) continue ;;
            esac
        fi
        rm -f "$_shard"
        # To stderr: callers capture this function's caller's stdout for the
        # exit code, and a stray line there becomes part of the "code".
        echo "  swept an abandoned coverage shard: ${_shard##*/}" >&2
    done
}

# Is the run recorded in this state directory still going?
#
# A live pid is not enough: the run that recorded it may have ended long ago
# and the number been given to an unrelated process since. The recorded pid
# is the shell running this directory's run.sh, so the process must still be
# running that script. A pid that names anything else is a run that ended.
tier_run_alive() {
    _dir="$1"
    [ -f "$_dir/pid" ] || return 1
    _rpid=$(cat "$_dir/pid" 2>/dev/null) || return 1
    [ -n "$_rpid" ] || return 1
    kill -0 "$_rpid" 2>/dev/null || return 1
    if ! _rargs=$(tier_pid_args "$_rpid"); then return 0; fi
    case "$_rargs" in
        *"$_dir/run.sh"*) return 0 ;;
    esac
    return 1
}

tier_run_key() {
    _dir="$1"
    if [ -f "$_dir/key" ]; then cat "$_dir/key" 2>/dev/null; fi
}

# tier_proc_is_zombie <pid> -- true if the kernel is still holding this pid's exit status.
#
# `kill -0` reports a zombie as signallable, so it alone cannot tell a run
# that is still going from one that exited but was never reaped -- exactly
# the orphan a detached run becomes when its container's pid 1 does not
# reap it (the same condition CLAUDE.md's `pid_alive()` exists to answer in
# Python; this is its shell-side counterpart for a caller with no /proc).
# Read from /proc's stat where there is one; otherwise `ps -o state=`, which
# both BSD and GNU ps print `Z` from. Neither readable is answered False:
# a pid this cannot inspect is judged on `kill -0` alone, same as elsewhere
# in this file.
tier_proc_is_zombie() {
    if [ -r "/proc/$1/stat" ]; then
        # Field 2, the comm name, is parenthesized and may itself hold a
        # space or a paren; state is field 3, so what follows the LAST ")"
        # is read, same as _session_leader_has_tty's Python counterpart.
        _tpz_rest=$(sed -n 's/^[0-9]*.*) //p' "/proc/$1/stat" 2>/dev/null)
        set -- $_tpz_rest
        [ "$1" = "Z" ]
        return
    fi
    _tpz_state=$(ps -o state= -p "$1" 2>/dev/null) || _tpz_state=""
    case "$_tpz_state" in
        *Z*) return 0 ;;
    esac
    return 1
}

# tier_tail_until <pid> <file> -- relay a growing file until <pid> exits.
#
# The portable replacement for GNU `tail -f --pid=`, which BSD tail (macOS)
# does not accept at all. Follows in the background, polls the pid, then
# stops the follower once the writer is gone. A pid still signallable but
# reaped into a zombie counts as gone, not alive, or this loop never ends
# in a container whose pid 1 does not reap orphans.
#
# `tail -f` polls for new data on its own schedule, documented at 1 second
# by default on both GNU and BSD `tail`, and no flag for a shorter one is
# common to both -- so the file being fully written the moment the pid
# exits does not mean `tail` has caught up to it yet. The grace sleep below
# is longer than that worst case, or the run's last lines are lost to a
# `tail` this loop stops before its next poll.
tier_tail_until() {
    _tu_pid="$1"
    _tu_file="$2"
    tail -f -n +1 "$_tu_file" 2>/dev/null &
    _tu_tpid=$!
    while kill -0 "$_tu_pid" 2>/dev/null && ! tier_proc_is_zombie "$_tu_pid"; do
        sleep 0.2
    done
    sleep 1.5
    kill "$_tu_tpid" 2>/dev/null
    wait "$_tu_tpid" 2>/dev/null
}

# tier_prepare <state-dir> <key> <repo-root> <finisher-or-empty> <cmd> [args...]
#
# Writes <state-dir>/{key,log,cmd.sh,run.sh} and clears {pid,rc}. run.sh is
# the run: it records its own pid, runs the command into the log, runs the
# finisher, and records the exit code. The finisher, when given, is a script
# run after the command with the command's exit code as $1, so whatever it
# records -- a verdict, a cache key, a formatted artifact -- is recorded by
# the run itself.
tier_prepare() {
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
}

# tier_start <state-dir> <key> <repo-root> <finisher-or-empty> <cmd> [args...]
#
# Prepares the run and starts it detached, in a session of its own.
tier_start() {
    _dir="$1"
    tier_prepare "$@"

    # Bash job control (enabled here for this one launch, regardless of the
    # caller's own setting) puts a background job in a process group of its
    # own: the hook's process group can be signalled without reaching it.
    # This is what `setsid` was used for -- util-linux, and absent on macOS
    # -- but a session of its own is more isolation than the run needs; its
    # own process group is the same immunity to a process-group signal, and
    # bash job control gives it on every platform this runner supports.
    # </dev/null so it never blocks on a terminal that is going away, and its
    # output goes to the log rather than to a stdout that may close under it.
    (set -m; bash "$_dir/run.sh" < /dev/null > /dev/null 2>&1 &)

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
        tier_tail_until "$_rpid" "$_dir/log" >&2 2>/dev/null
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

    if ! tier_require tail; then
        echo 1
        return 0
    fi

    if tier_run_alive "$_dir"; then
        if [ "$(tier_run_key "$_dir")" = "$_key" ]; then
            echo "  attaching to the $_label run already in progress (pid $(cat "$_dir/pid"))" >&2
            tier_wait "$_dir"
            return 0
        fi
        echo "ERROR: another $_label run is in progress (pid $(cat "$_dir/pid")): one for a different" >&2
        echo "       tree, or one started from a terminal." >&2
        echo "       Two runs of one tier in one worktree overwrite each other's results" >&2
        echo "       and coverage data. Wait for it to finish; its output is in $_dir/log." >&2
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

# tier_execute_foreground <state-dir> <repo-root> <label> <cmd> [args...]
#
# Runs a tier in the foreground, for a person at a terminal (`make test`),
# under the same guards a hook's run has: it refuses while any run of this
# tier is in progress in the worktree, sweeps abandoned coverage shards, and
# records itself in the state directory so a hook started meanwhile refuses
# in turn. Interrupting it stops the run. Exits with the command's code.
tier_execute_foreground() {
    _dir="$1"
    _root="$2"
    _label="$3"
    shift 3

    if ! tier_require tail; then
        return 1
    fi

    if tier_run_alive "$_dir"; then
        echo "ERROR: a $_label run is already in progress in this worktree (pid $(cat "$_dir/pid"))." >&2
        echo "       Two runs of one tier in one worktree overwrite each other's results" >&2
        echo "       and coverage data. Wait for it to finish; its output is in $_dir/log." >&2
        return 1
    fi

    tier_sweep_dead_coverage_shards "$_root"
    tier_prepare "$_dir" "foreground $$" "$_root" "" "$@"
    # The log is shown as it is written, and kept for whoever asks later.
    # The run is the foreground job, so an interrupt reaches it; the relay is
    # stopped explicitly below, whichever way the run ends.
    tail -f -n +1 "$_dir/log" 2>/dev/null &
    _tpid=$!
    bash "$_dir/run.sh"
    # Let the relay print what the run wrote last before it is stopped.
    sleep 1
    kill "$_tpid" 2>/dev/null
    wait "$_tpid" 2>/dev/null
    if [ -f "$_dir/rc" ]; then
        return "$(cat "$_dir/rc")"
    fi
    return 137
}
