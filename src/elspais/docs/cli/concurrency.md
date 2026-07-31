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

Sub-nodes resolve to the requirement that renders them: an assertion or
remainder ID yields (and is guarded by) its owning requirement's
version, on both the read and the mutation side.

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
| `mutate_add_requirement` | `parent_id` if supplied; unguarded without one |
| `mutate_add_journey` | the parent FILE |
| `mutate_move_node_to_file` | three tokens: node, source file, target file |
| `mutate_rename_file` | the FILE node |
| `apply_link` | the FILE it edits |

Edge mutations guard the source because only the source's rendered
`Implements:`/`Refines:` line changes -- a target token would reject
writes that cannot clobber anything. Creation guards the parent whose
rendered content gains the new child; a parentless creation has nothing
to clobber. A move changes all three participants, so all three are
guarded (a destination file created by the move itself needs no token).

## History-Level Guards: the Mutation-Log Tip

Undo, discard, and persist act on **every** writer's pending work, not
just yours, so they require the mutation-log tip -- the ID of the newest
pending mutation as you last saw it:

- `undo_last_mutation(if_mutation_id=<tip>)`
- `undo_to_mutation(mutation_id=..., if_tip_mutation_id=<tip>)`
- `save_mutations(if_tip_mutation_id=<tip>)`
- `refresh_graph(force=True, if_tip_mutation_id=<tip>)` -- the tip is
  required only with `force=True`, which discards pending work

Get the tip from `get_mutation_log()` -- entries are chronological, so
the tip is the `id` of the last entry (raise `limit` if the log is
longer). Over HTTP, `/api/dirty` returns it as `tip`.

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
