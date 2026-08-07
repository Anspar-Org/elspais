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
  server could not be asked -> badge shows ?, amber, with a tooltip
                               naming the last confirmed count
```

The third state exists because both ways of collapsing it lie. Leaving
the last count on screen asserts pending work that may exist in no
process; showing zero hides work that is still pending behind a
momentary network failure. `?` claims neither a count nor safety. The
next answer from the server -- from a mutation, or from the 30-second
poll -- replaces it with the reported count.

That poll is the page's only heartbeat: the count is otherwise refreshed
only at load and after a mutation, so a server that dies while the
operator sits idle would leave a frozen number on screen forever. A
failed poll therefore marks the count unknown, and a poll that answers
again resyncs it. A failed read does **not** advance the tip the page
has "seen", so the other-writer banner still fires for anything that
happened while the server was unreachable, and Save/Undo keep whatever
state they had rather than asserting that there is nothing to save.

The warning shown before navigating away follows the same rule: it arms
only while the server has **reported** pending work. Because that work
lives in the server, closing the tab destroys nothing -- the warning is a
courtesy, not a guard on data in the page -- so while the count is
unknown the viewer does not obstruct navigation.

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
