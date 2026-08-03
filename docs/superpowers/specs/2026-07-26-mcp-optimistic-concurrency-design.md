# Optimistic Concurrency for Graph Mutations

**Status**: Design approved, not yet implemented
**Date**: 2026-07-26

## Problem

A single elspais daemon serves multiple concurrent writers: MCP agents over
streamable-HTTP, and the viewer GUI, whose `/api/mutate/*` routes call the same
`_mutate_*` helpers in `mcp/server.py`. Nothing coordinates them. Two clients
that both read a requirement, then both write, produce a lost update — the
second write silently overwrites the first, and neither client is told.

The daemon is the only place that knows the current state, so it is the only
place the conflict can be detected.

## Solution

Optimistic concurrency control. Every mutation carries a precondition: the
version of the state the caller believes it is modifying. The daemon compares
that version against live state and rejects the mutation if they differ,
returning enough information for the caller to reconcile and retry.

The precondition is **required**, not optional. An unguarded mutation is a
blind write, which is the pattern that causes the problem.

## Version derivation

A single function `node_version(node) -> str` returning a 16-char hex digest,
added to `graph/render.py` beside `compute_hash_for_node` — the existing
canonical home for content-derived digests. Do not add a second derivation
elsewhere.

```text
version = sha256(
    node.kind
    || rendered text
    || canonical outgoing traceability edges, sorted:
       [(edge_kind, target_id, assertion_targets), ...]
)[:16]
```

`render_node()` on a REQUIREMENT already emits the ID, title, status,
`**Template**` marker, `Implements:` / `Refines:` / `Satisfies:` /
`Integrates:` lines derived from live edges, body, assertions, and remainder
sections. The version therefore changes if and only if something that would be
written to disk changes.

Per-kind resolution:

| Node kind | Version is |
|---|---|
| REQUIREMENT, USER_JOURNEY | its own, per the formula (`render_node()` for the rendered text) |
| ASSERTION, REMAINDER | the owning REQUIREMENT / USER_JOURNEY's version, found by walking the STRUCTURES parent |
| CODE, TEST | its own, using `raw_text` as the rendered text |
| FILE | `sha256(relative_path + ordered CONTAINS child IDs)` |

The FILE rule covers identity and composition only, deliberately excluding
child content: editing prose inside one requirement must not invalidate a
pending file-level operation on the file that contains it.

The ASSERTION / REMAINDER rule is what makes requirement-scoped granularity
usable. `mutate_update_assertion(assertion_id="REQ-d00001-A", ...)` takes the
parent requirement's version — the same token the caller already received from
`get_requirement("REQ-d00001")`. No extra lookup is needed to mutate a
sub-node.

### Why content-derived rather than a counter

A rebuild that produces identical content yields identical versions, so a
routine `refresh_graph` does not invalidate every outstanding token. A
counter or epoch scheme would force every client to re-read after every
refresh.

Content-addressing also makes the ABA case benign. If a node goes
`bar -> foo -> bar`, a token from the first `bar` matches again — but the state
is byte-identical to what the holder read, so the write is exactly as valid as
if nothing had intervened. A counter would reject this correct write.

### Granularity

The unit of concurrency is the authoring unit: a REQUIREMENT or USER_JOURNEY,
covering its assertions and remainder sections. Two clients editing different
assertions of the same requirement conflict. This is correct — they are editing
one rendered block that is written to disk as a unit.

## Guard mechanism

A single helper in `mcp/server.py`:

```text
_guard_version(graph, node_id, if_version) -> dict | None
```

Called immediately after the existing `_guard_associate_write` in every MCP
mutate tool, and from every `api_mutate_*` route in `server/routes_api.py`.
Two surfaces, one implementation.

- Version matches: returns `None`, the mutation proceeds.
- Version differs: returns the conflict dict (below).
- Node absent: returns `{"success": false, "code": "node_not_found", ...}`.
  This is distinct from a conflict because retrying will not help.

### Which node each mutation guards

**Content and metadata mutations** guard the named node, resolved through the
per-kind table above: `rename_node`, `update_title`, `change_status`,
`set_stereotype`, `delete_requirement`, `update_assertion`,
`delete_assertion`, `rename_assertion`, `update_remainder`,
`delete_remainder`, and the journey equivalents. Creation mutations are
covered separately below.

**Edge mutations** guard the **source only**: `add_edge`, `delete_edge`,
`change_edge_kind`, `change_edge_targets`, `fix_broken_reference`. The source's
rendered `Implements:` / `Refines:` line is what changes on disk. The target's
rendered text is unaffected, so requiring a target token would reject writes
that cannot clobber anything.

**Creation mutations** guard the parent, since the created node has no prior
state: `add_assertion` and `add_remainder` guard `req_id`;
`mutate_add_requirement` guards `parent_id` when supplied, and is unguarded
when it is not — there is nothing to clobber.

**File mutations** guard every node whose rendered output changes:

- `rename_file(file_id, new_relative_path, if_version)` — the FILE itself.
- `move_node_to_file(node_id, target_file_id, if_version,
  if_source_file_version, if_target_version)` — the moved node, the source
  FILE (the node leaves its CONTAINS list), and the destination FILE (its
  composition changes, and `render_order` placement depends on concurrent
  arrivals).

A file move is not analogous to an edge. Both files genuinely mutate. The rule
is "guard every node whose rendered output changes", which is uniform and
statable in one sentence.

`move_node_to_file` requires the target FILE to already exist in the index
(`builder.py:1998` raises `KeyError` otherwise), so `if_target_version` is
unconditionally required. If a create-on-move path is ever added, the
destination token would be omitted for that case only.

The source FILE id is reachable from the node the caller has already read, so
its version is surfaced in read payloads and costs no extra round-trip.

### Log-tip guards: undo, refresh, save

`undo_last_mutation` and `undo_to_mutation` unwind whatever is at the tip of
the mutation log, which may be another user's work. Both take a required
`if_mutation_id` (`if_tip_mutation_id` for `undo_to_mutation`, which already
names a target) that must equal the current log tip. Mismatch returns
`{"success": false, "code": "mutation_log_conflict", "current_tip": ...}`.

`refresh_graph(force=True)` discards all pending in-memory mutations,
including other users'. It is already opt-in — `server.py:5399` refuses when
mutations are pending — but the opt-in is not informed. `force=True` also
requires `if_tip_mutation_id` matching the log tip, so a caller can only
discard a mutation set it has actually observed.

`save_mutations` persists every client's pending work to disk, including
mutations the caller has never seen and work another writer may consider
half-finished. It takes the same required `if_tip_mutation_id`. On mismatch it
returns `mutation_log_conflict` carrying the current tip and a summary of the
entries appended since the caller's tip, so the caller can inspect what it is
about to persist and re-issue against the observed tip.

This makes the flush **informed**: it remains all-or-nothing across writers,
but no caller can persist a mutation set it has not looked at. All three
log-tip guards share one helper and one error code.

## Conflict response

Uniform across both surfaces. The viewer routes return it as HTTP **409** with
an identical JSON body.

```text
{ "success": false,
  "code": "version_conflict",
  "node_id": "REQ-d00001",
  "provided_version": "7f3c1e2a91b04d55",
  "current_version": "91cc40281ae7f3b2",
  "current_state": { ... },
  "hint": "State changed since you read it. Reconcile against
           current_state and retry with current_version." }
```

`current_state` is produced by the existing `_get_requirement` (or `_get_node`
for non-requirement kinds), reused verbatim. There must be no second
serializer to drift out of sync.

Including the state lets the caller reconcile and retry in one round-trip
instead of a reject-then-re-read cycle. The cost is paid only on the failure
path.

## Version exposure on reads

Every **successful** mutation returns the new `version` in its response. A
client performing a sequence of edits threads the returned token into the next
call and never re-reads. Without this, mandatory preconditions would double
every round-trip; with it, a sequence costs one read at the start.

`version` is added to the output of `get_requirement`, `get_node`, and
`get_subtree`. For requirements, the payload also carries the containing FILE's
version, so file operations need no extra fetch.

A new tool `get_versions(node_ids: list[str]) -> dict[str, str]` returns
versions without content, for refreshing tokens cheaply.

## Rollout

Hard cutover in one minor release. No deprecation window and no configuration
flag to disable the guard — a permissive path would only ever be used to
restore the unsafe behavior this design exists to remove.

Surfaces to update in the same change:

- MCP mutate tool signatures in `mcp/server.py`.
- All `/api/mutate/*` routes in `server/routes_api.py` (19 routes registered in
  `server/app.py:174-198`) and their JS callers in the viewer.
- Read tools that gain `version`.
- `docs/cli/*.md` and `docs/configuration.md`.
- The MCP `docs` and `faq` topics.
- `agent_instructions()` — agents must be told the read, mutate, thread-the-
  token protocol, and how to respond to `version_conflict`. Without this they
  will flail on their first conflict.
- CHANGELOG entry marking the breaking change.

The verbosity cost falls only on callers that skip the read entirely. Correct
read-before-write clients carry one additional field.

## Testing

Tests are written by a sub-agent, per project convention, and every test
references a requirement.

- **Derivation unit tests**: rebuild stability (identical content yields
  identical versions); one test per mutation kind proving it bumps the version,
  explicitly including the four the content hash does not cover — title,
  status, rename, and edge mutations. Per-kind resolution for ASSERTION,
  REMAINDER, CODE, TEST, and FILE nodes.
- **Conflict tests**: an `@pytest.mark.incremental` class on the `mutable_graph`
  fixture simulating two clients against one graph — read, read, write, write,
  asserting the second write is rejected with the correct code and that
  `current_state` reflects the first write.
- **Log-tip guard tests**: for each of `undo_last_mutation`,
  `undo_to_mutation`, `refresh_graph(force=True)`, and `save_mutations` — a
  stale tip is rejected, a matching tip is accepted, and the conflict response
  lists the unseen entries.
- **Viewer test**: a stale token produces HTTP 409 with the same body shape as
  the MCP conflict dict.
- **E2E**: one MCP test in `test_e2e_standard`, placed after the existing
  mutation tests since it mutates state.

## Known limitations

A client that calls `refresh_graph` mid-sequence after another user's work was
saved to disk will find its tokens stale. This is correct behavior — the state
really did change — but it means the client must re-read. Document it.
