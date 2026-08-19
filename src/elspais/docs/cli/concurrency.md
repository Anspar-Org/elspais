# OPTIMISTIC CONCURRENCY

A single daemon serves several writers at once: MCP agents and the
viewer GUI share the same in-memory graph. Every mutation therefore
requires a version token proving the caller has seen the state it is
about to change. A stale token is refused instead of silently
overwriting work that arrived in between.

This page documents the full protocol. The MCP tool docstrings state the
per-tool contract; `faq("concurrency")` has quick answers.

## The Protocol in Three Steps

1. **Read** the node. Every read surface reports the token a mutation
   will need: `get_requirement` and `get_node` return `version`
   (requirements also return `file_version`, the containing FILE's
   token); `get_subtree` (`flat`/`nested` formats) carries a `version`
   per node; `get_versions(node_ids)` refreshes tokens in bulk without
   content.
2. **Mutate** with `if_version` set to the token from your read. Every
   `mutate_*` tool requires it.
3. **Thread the returned token.** Every successful mutation returns the
   node's new `version`. Pass that into your next mutation of the same
   node -- do not re-read between your own successive writes. A sequence
   of edits costs one read at the start, not one per step.

Sub-nodes resolve to the **authoring unit** that renders them: an
assertion or remainder ID yields (and is guarded by) the version of the
requirement -- or user journey -- that owns it, on both the read and the
mutation side. A journey's sections resolve to the journey, not to any
requirement.

Deletions have no surviving node to report, so they return the version
of the surviving container that absorbed the change:
`mutate_delete_assertion` and `mutate_delete_remainder` return the
owning requirement's resulting version; `mutate_delete_requirement`
returns the containing FILE's resulting version.

`get_versions` **omits** unknown IDs rather than raising or returning
None -- an absent key means "re-resolve this one" (renamed or deleted),
and one dead ID cannot defeat a refresh of the rest. The `markdown`
subtree format carries no tokens; it is rendered prose.

## On `version_conflict`: Reconcile, Never Retry Blind

A stale token is rejected with:

```json
{
  "success": false,
  "code": "version_conflict",
  "node_id": "REQ-d00001",
  "provided_version": "...",
  "current_version": "...",
  "current_state": { ... },
  "hint": "State changed since you read it. ..."
}
```

Someone else changed the node between your read and your write. Your
pending edit was composed against text that no longer exists, so:

1. Re-read your intent against `current_state` (the same payload
   `get_requirement`/`get_node` would return). Your edit may no longer
   apply, may conflict with the other change, or may already be done.
2. Only if the edit still makes sense, retry with `current_version`.

**Never** take `current_version` from the error and resubmit unchanged
without checking `current_state` -- that reintroduces exactly the blind
overwrite the guard exists to prevent.

`node_not_found` is a distinct code: the node does not exist at all
(renamed or deleted). Retrying cannot fix it; re-resolve the ID with
`search()` or `get_versions()` first.

## Which Token Guards Which Node

| Mutation | Guarded by |
|----------|-----------|
| Content/metadata (rename, title, status, delete, stereotype) | the node itself |
| Assertion and remainder mutations | the parent REQUIREMENT |
| Edge mutations (add/delete/change kind/change targets/fix ref) | the SOURCE node only |
| `mutate_add_assertion`, `mutate_add_remainder` | the parent requirement (`req_id`) |
| `mutate_add_requirement` | `file_id` if supplied (placement changes that file's composition), else `parent_id`; unguarded without either |
| `mutate_add_journey` | the parent FILE |
| `mutate_move_node_to_file` | three tokens: node, source file, target file |
| `mutate_rename_file` | the FILE node |
| `apply_link` | the FILE it edits |

Edge mutations guard the source because only the source's rendered
`Implements:`/`Refines:` line changes -- a target token would reject
writes that cannot clobber anything. Creation guards the parent whose
rendered content gains the new child; a parentless creation has nothing
to clobber. A move changes all three participants, so all three are
guarded -- but a destination file the move itself creates has no prior
state to clobber, so pass `if_target_version=""` and the move creates
the file (path validated against the scanning config, all guards run
before anything touches disk), exactly like the viewer's HTTP route.

## History-Level Guards: the Mutation-Log Tip

Undo, discard, and persist act on **every** writer's pending work, not
just yours, so they require the mutation-log tip -- the ID of the newest
pending mutation as you last saw it:

- `undo_last_mutation(if_mutation_id=<tip>)`
- `undo_to_mutation(mutation_id=..., if_tip_mutation_id=<tip>)`
- `save_mutations(if_tip_mutation_id=<tip>)`
- `refresh_graph(force=True, if_tip_mutation_id=<tip>)` -- the tip is
  required only with `force=True`, which discards pending work
- `restore_from_safety_branch(branch_name, if_tip_mutation_id=<tip>)` --
  a restore overwrites files and discards every writer's pending work

The viewer's three HTTP history routes carry the same guard:
`/api/save`, `/api/revert`, and `/api/reload` require
`if_tip_mutation_id` in the JSON body and reject a stale or missing tip
with HTTP 409 (`mutation_log_conflict`, identical body to the MCP
rejection). The viewer's own JS threads the tip automatically.

Get the tip from `get_mutation_log()` -- it returns `current_tip`
directly, alongside the most recent entries (newest first) and the
`total` pending count. Over HTTP, `/api/dirty` returns it as `tip`.

`""` (the empty string) means "I believe nothing is pending". It is the
correct value when you have made no mutations and seen none.

A mismatch is rejected with `code: "mutation_log_conflict"` carrying
`current_tip` and `unseen` -- the entries appended since your position.
Review `unseen` before retrying with `current_tip`: those entries are
exactly the work you were about to unwind, discard, or persist sight
unseen.

## HTTP Parity (Viewer API)

The viewer's `/api/mutate/*` routes enforce the same guards through the
same helpers -- there is no softer path around the protocol:

- Requests carry `if_version` (or `if_mutation_id` for undo, or the
  three tokens for move-to-file) in the JSON body.
- A stale or missing token returns **HTTP 409** whose JSON body is
  identical to the MCP rejection (`version_conflict` or
  `mutation_log_conflict`).
- An unknown node returns **404** with `code: "node_not_found"`.
- 409 means a conflict and nothing else. A save that fails for another
  reason says so with its own status and `code`: **400** with
  `changelog_message_required` when an Active requirement changed and no
  changelog reason was given, **500** with `save_failed` when the write
  itself failed. Neither is fixed by re-reading and retrying, which is
  what 409 asks for.
- Successful mutations return the new `version`.
- `/api/dirty` returns the pending `mutation_count` and the `tip`.
- The history routes `/api/save`, `/api/revert`, and `/api/reload`
  require `if_tip_mutation_id` in the JSON body (`""` = nothing
  pending), mirroring the MCP history tools.

## Noticing Another Writer

Mutations live in memory until saved, so a writer working through the
MCP tools changes no file. Nothing on disk moves, and a client watching
file timestamps sees nothing -- yet the graph every surface reads has
already changed.

That also means pending work lives only in the daemon process, and the
daemon has a lifetime of its own. One that a CLI command auto-started
keeps serving while any of its clients is running, and shuts down once
none of them is. A client is a process id it was told about, or an agent
session holding its MCP connection's stream open — a completed request is
not enough. When neither can be established for a session, or a declared
`ELSPAIS_CLIENT_PID` names a process that is already dead, you are told so
once on stderr, naming `ELSPAIS_CLIENT_PID` as the variable to set; the
command still runs, and the same daemon does not warn you twice. See
`docs("commands")` for the resolution order and the recipe for a CI job or
harness. If it is holding pending mutations when that happens it
logs the count to `.elspais/daemon.log`, waits a bounded grace period
(30 minutes), and then **saves** them to disk and stops — nothing is
discarded. An applied mutation during that window restarts the grace
period; reads never do.

That deadline is not the only way the process ends, and none of the
others discards either. A daemon that stops because its idle timeout
expired, or because something outside it signalled it, persists what it
is holding first and leaves the same record. Whatever prompts the stop,
work you applied and never saved is on disk afterwards rather than gone
— unless somebody said they did not want it, which is what
`elspais daemon --discard-changes` says. A discard covers the
mutations that existed when it was asked for: one applied in between
moves the tip and the whole request is refused, so nothing is thrown away
that the person asking never saw.

A save the daemon performed is recorded, and the record reaches you in
the metadata you already read: `get_workspace_info` and
`get_graph_status` carry an `automatic_save` block while one is
outstanding, as do `/api/dirty` and `/api/check-freshness`. It states who
saved, when, how many mutations, and what triggered it — and nothing
else. It is not a verdict on the work: a client can vanish because it
finished, crashed, or lost its connection, and nothing in the daemon can
distinguish those. Read the diff and decide. Saving deliberately
(`save_mutations(if_tip_mutation_id=<tip>)`) retires the record, and is
still the right habit before your session ends. See `docs("commands")`
for the full lifetime rules.

A process can also die without reaching any of that — killed outright,
or with its machine. While a server holds unsaved changes it says so in a
sentinel file beside its state record, written before the change is
acknowledged; a server that starts and finds one left by a process that
is gone reports a `lost_changes` block on the same surfaces as the
automatic-save record. It tells you that changes were held and never
written, and that is all it can tell you: nothing keeps the changes
themselves, so this is a disclosure, not a recovery. Saving at your own
request retires it.

Once a daemon has decided to stop, further mutations are refused with
`server_shutting_down` (HTTP 409, same body, on the viewer's routes)
rather than accepted into a shutdown that would drop them. Treat it like
any other rejection: nothing was applied, so reconnect and re-apply.

## On `executable_changed`: the Server Is Running Older elspais

A server loads elspais once and answers from it until it ends, so when
elspais is reinstalled beneath a running server -- which, when the tree
you are working in is elspais's own source, is what editing a file
amounts to -- that server goes on answering from the program it started
with. This is not the same thing as your spec files going stale, and it
is reported separately: `executable_difference` appears on
`get_workspace_info`, `get_graph_status`, `/api/dirty` and
`/api/check-freshness`, naming what the server is running and what is
now installed.

A daemon in that state renews itself: it writes anything it is holding,
replaces its own process image with the current program, and goes on
serving at the same address. You will not normally see it happen. The
write is unasked, so it leaves the same `automatic_save` record any
unasked save leaves; what it cannot preserve is the ability to undo those
changes, because the mutation log goes with the process that held it.

A **stdio** MCP server cannot renew itself -- its client reaches it over
a connection that client owns, and exiting would remove its tools from
your session with nothing to restart it. So it refuses instead, with
`executable_changed`. Nothing was applied; reconnect the server (`/mcp`
in Claude Code) to pick up the current program.

None of this applies to an installation whose files are fixed until it is
replaced wholesale. It arises only where the install resolves to a working
tree, so that editing a source file installs a new program by the same
act.

`/api/check-freshness` therefore reports two independent signals:

- `stale` (with `stale_files`) -- spec files changed **on disk**, e.g. a
  git checkout or an outside editor. Reloading from disk is the fix.
- `mutation_tip` -- the mutation-log tip. Poll it and compare against the
  tip you last saw: if it moved, another writer mutated the shared
  in-memory graph. The live graph is already correct, so the fix is to
  re-read it (refetch the nodes you display), *not* to reload from disk,
  which would discard that writer's unsaved work.

The viewer does exactly this on a 30-second poll and raises a banner
naming which of the two happened. An agent holding state across calls
can use the same field to know when to re-read.

## The Viewer's Pending-Change Badge

The badge beside the viewer's Save button counts work held in the
**server** process, not in the browser page. The page cannot recompute
that number on its own, so it has three states to report, not two:

```text
  server said 0 pending  ->  badge hidden
  server said N pending  ->  badge shows N, red
  no usable answer       ->  badge shows ?, amber, with a tooltip
                             naming the last confirmed count
```

The third state is not only "the network dropped". It covers every way
the page can fail to get a number it can trust: an unreachable server, a
server that answered with an error, and an answer whose count is missing
or not a number. All three are the absence of a value, and coercing any
of them to zero would report pending work as confirmed absent. The
tooltip says so -- "the viewer server is unreachable or not answering".

The third state exists because both ways of collapsing it lie. Leaving
the last count on screen asserts pending work that may exist in no
process; showing zero hides work that is still pending behind a
momentary network failure. `?` claims neither a count nor safety. The
next usable answer from the server -- from a mutation, or from the
30-second poll -- replaces it with the reported count.

### The Count's Heartbeat

The count is server-truth, so the page re-establishes it on a 30-second
poll. Every cycle the poll probes `/api/dirty` and records the outcome,
success or failure. Without that the count would move only at load and
after this page's own mutations, and a server that died while the
operator sat idle would leave a frozen number on screen forever.

Two rules keep that probe honest:

- **Only the count endpoint speaks for the count.** The same poll also
  calls `/api/check-freshness` for the stale-file and other-writer
  banners, but a failure there leaves the count alone. Letting it mark
  the count unknown pinned the badge to `?` -- and the navigation
  warning off -- for as long as that one endpoint stayed broken, even
  with `/api/dirty` answering perfectly.
- **The probe never adopts the mutation-log tip**, on success or on
  failure. Adopting it would mark another writer's mutations as seen
  every cycle and the "Another writer changed the graph" banner would
  never raise again. The tip advances only where the page has actually
  re-read state: at load, after its own mutation, and on a reload from
  memory. So `lastSeenTip` can lag the count by many cycles, which is
  correct.

**This makes an idle tab reactive to other writers.** Because the probe
runs whether or not you touch the page, pending changes arriving through
the shared daemon from someone else -- an MCP agent, a second viewer --
show up in *this* tab's badge within 30 seconds, and arm its
before-navigation warning. That follows from the badge being server-truth
rather than a tally of what this page did, but it is a real change in
behaviour from a badge that moved only when this page acted: a tab you
have not touched can start warning you before it closes.

### Leaving, Versus Acting on the Changes

The warning shown before navigating away arms only while the server has
**reported** pending work. Because that work lives in the server, closing
the tab destroys nothing -- the warning is a courtesy, not a guard on
data in the page -- so while the count is unknown the viewer does not
obstruct navigation.

Operations that act on those server-side changes take the opposite
stance under the same uncertainty, and the two must not be conflated.
Switching branches or taking a checkpoint while the count is unknown
would risk stranding pending changes on the branch being left, or
committing around changes that are still pending. Both therefore
**refuse** -- an error modal, not a prompt. A prompt's only remedy is to
save first, and saving needs the same server whose silence caused the
uncertainty in the first place. Navigation is permissive because it
destroys nothing; an operation that can destroy is restrictive.

Save, Revert and Refresh need no such modal: each carries the
mutation-log tip read fresh from `/api/dirty`, and a failed read
degrades that to `""` -- "I believe nothing is pending" -- which the
server rejects with a 409 if anything actually is. The guard is enforced
server-side rather than presented in the page.

## Finding Out Why the Page Did (or Did Not) Warn

The viewer in edit mode can tell you the state behind that decision, so
you do not have to infer it from what the page is showing. Open the
browser's developer console and call:

```text
  > unloadWarningState()

  {
    willWarnOnClose:    true | false
    pendingCount:       N | null
    countKnown:         true | false
    countEstablishedAt: "2026-08-07T12:34:56.789Z" | null
    countSource:        "server" | "unreachable" | null
    lastSeenTip:        "<mutation id>" | ""
  }
```

Field by field:

- `willWarnOnClose` -- whether the page will warn if you try to leave
  right now. It is exactly `countKnown && pendingCount > 0`.
- `pendingCount` -- the pending-change count the server last reported;
  `null` when the count is unknown (the `?` badge).
- `countKnown` -- whether `pendingCount` is a number the server actually
  gave, as opposed to an absent value.
- `countEstablishedAt` -- when that outcome was recorded, ISO-8601.
  `null` before the page has asked at all. Both outcomes stamp it, and
  the 30-second poll produces one every cycle, so an old timestamp does
  not mean "the server went quiet" -- it means no outcome of either kind
  has been recorded since, i.e. the page has stopped asking. (Browsers
  throttle timers in backgrounded tabs, so a tab that has been in the
  background can show an old timestamp legitimately. Read it in a tab
  that has been in the foreground.)
- `countSource` -- `"server"` if the count came from a usable
  `/api/dirty` answer, `"unreachable"` if the last attempt produced no
  usable answer (no response, an error response, or a count that was not
  a number), `null` if the page has not yet made the request.
- `lastSeenTip` -- the mutation-log tip as of the last point at which
  this page actually re-read state, which is what the other-writer
  banner compares against. Neither a failed read nor the poll's routine
  count probe advances it, so it is routinely older than
  `countEstablishedAt` -- that is not a fault. `""` means nothing was
  pending when it was read.

This function reports; it does not decide anything. Calling it changes
no state and does not arm or disarm the warning.

The console also carries the decision itself. Each time you attempt to
navigate away, the handler logs one line beginning `[elspais]
beforeunload:` saying whether it warned and why -- naming the pending
count when it warned, and naming the count as unknown when it did not.
If you tried to close the page and no such line appeared, the page never
reached the decision; if the line is there, it did, and the values it
names are the ones the decision was made on.

Both of these exist only in edit mode. A read-only viewer never warns
before navigation and does not define `unloadWarningState`.

## Why Tokens Survive a Refresh

The version is a 16-character digest of the node's rendered text plus
its outgoing traceability references (`node_version()`), not a counter.
It changes when, and only when, the node's on-disk representation would
change. Rebuilding the graph from unchanged files yields unchanged
versions, so a routine `refresh_graph()` does not invalidate tokens
held by other clients.

FILE node versions cover path plus ordered child IDs -- identity and
composition only -- so editing prose inside one requirement does not
invalidate a pending file-level operation elsewhere in the file.

The viewer's automatic refresh (the mtime-triggered rebuild that keeps
the graph in sync with on-disk edits) never rebuilds over pending
in-memory mutations -- an auto-rebuild would be a silent discard of
every writer's unsaved work. Discarding pending work always requires an
explicit, tip-guarded revert, reload, or forced refresh.
