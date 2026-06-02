# Federation write/generation scope (CUR-1419)

**Date:** 2026-06-01
**Status:** Approved design, pre-implementation

## Problem

When an associate is configured, `elspais fix` operates on the **federated**
graph (primary + associates) for its *write* and *generate* surfaces, not just
its read/validation surfaces. As a result it:

1. **Rewrites spec files inside associate repos** — term canonicalization and
   requirement-hash stamping mutate files outside the primary project.
2. **Folds associate requirements into the primary's generated artifacts** —
   `spec/INDEX.md` and `spec/_generated/term-index.md` are regenerated as
   federated artifacts containing the associate's reqs.

This is HIGH severity because pre-commit hooks run `elspais fix && git add spec/`.
Any commit in a repo with an associate configured silently dirties the sibling
repo and inflates the committed INDEX, which then fails CI's `spec.index_current`
check on a clean checkout (no associate configured regenerates the smaller,
correct INDEX). Observed concretely: a primary repo's INDEX jumped 135 → 176
reqs (41 associate rows leaked) and 20 associate spec files were rewritten.

**Core invariant to restore:** `elspais fix` must produce byte-identical
primary-repo files whether or not an associate is configured. Associates remain
read-only inputs for cross-repo resolution (`checks`, `summary`, `Integrates:`),
never silently written, and never folded into the primary's generated artifacts —
**unless explicitly opted in via config.**

## Goals

- Default behavior: federation affects only read/validation surfaces. Write and
  generate surfaces are primary-repo-only.
- Make both federation write behaviors **opt-in** via config:
  - whether associate repos may be written (by `fix` and by MCP `save_mutations`);
  - whether generated artifacts (`INDEX.md`, `term-index.md`) include associates.
- MCP mutate functions targeting associate-owned nodes must fail cleanly
  (read-only) when associate writes are disabled.

## Non-goals (YAGNI)

- Per-invocation CLI flags (e.g. `--write-associates`). Config-only, repo-wide.
- Per-associate granularity (one associate writable, another not). Repo-wide.
- Changing how federation works for `checks` / `summary` / cross-repo
  resolution — those continue to federate (that is the point of associates).

## Configuration

A single top-level `[federation]` table holds both toggles. Both default
`false`. Added to the `ElspaisConfig` Pydantic model (`config/schema.py`) as a
new `FederationConfig` sub-model with a default-constructed instance, so the
section is optional and existing configs validate unchanged. No config-version
migration is required (new fields carry defaults).

```toml
[federation]
write_associates = false    # allow fix + MCP save_mutations to write associate repo files
index_associates = false    # include associate reqs in generated INDEX.md / term-index.md
```

Schema:

```text
ElspaisConfig
  ...
  federation: FederationConfig
    write_associates: bool = False
    index_associates: bool = False
```

Accessed from the loaded config dict via `config.get("federation", {})` (keys
`write_associates`, `index_associates`).

## Behavior by surface

### Term scanning / canonicalization (in-memory) — UNCHANGED

Term scanning and canonicalization continue to run across all repos in memory.
This is correct for cross-repo validation. Only the *write* of canonicalized
content is gated (below). When `write_associates=false`, associate files are
canonicalized in the in-memory graph but never persisted, so the on-disk
associate repo is untouched.

### `fix` / MCP — spec-file writes

`render_save()` (`graph/render.py`) is the single write surface for both `fix`
and MCP `save_mutations`. It writes each dirty FILE node. Add a primary-repo
filter:

- Determine ownership via the existing `FederatedGraph.repo_for(file_id)` /
  `root_repo_name`. A FILE node is primary iff its owning repo name equals
  `graph.root_repo_name` (equivalently, the FILE node's `repo` field is `None`).
- When `write_associates=false`, skip writing any dirty FILE node not owned by
  the root repo. Filter applied to the dirty-file set produced by
  `_find_dirty_files()` (or at the write loop), so the filter covers files
  marked dirty by build-time canonicalization as well as by mutations.
- When `write_associates=true`, write all dirty FILE nodes (current behavior),
  routing each to its owning repo root via `graph.repo_for(file_id).repo_root`
  (already implemented).

`render_save()` needs access to the flag. Pass it in (e.g. a
`write_associates: bool = False` parameter) from both callers — `fix_cmd.py`
reads it from the loaded config; the MCP `save_mutations` tool reads it from
`_state["config"]`. Keeping it a parameter avoids `render_save()` re-loading
config and keeps the function testable.

### `fix` / `index` — generated artifacts

`INDEX.md` (`commands/index.py` `_build_index_content()`) and the
term-index/glossary generation iterate `graph.nodes_by_kind(...)` across all
repos. Add a primary-repo filter on the iterated requirement/journey/term set:

- When `index_associates=false`, include only nodes owned by the root repo
  (`graph.repo_for(node_id).name == graph.root_repo_name`).
- When `index_associates=true`, include all (current behavior; associate rows
  bucketed by repo as today).

Both INDEX and term-index share the single `index_associates` flag.

### MCP mutate functions — read-only guard

Add a shared helper:

```text
_guard_associate_write(graph, config, *node_ids) -> dict | None
    returns {"success": False, "error": "Associate '<name>' is read-only
             (set federation.write_associates=true to enable)"} if any node_id
             resolves to an associate-owned node and write_associates is false;
    else None.
```

Each mutate function calls the guard early with the relevant target node id(s)
and returns the error dict verbatim if non-None (no in-memory mutation applied).

- Target-resolving mutations guard on the resolved existing target node:
  `mutate_rename_node`, `mutate_update_title`, `mutate_change_status`,
  `mutate_add_assertion`, `mutate_update_assertion`, `mutate_delete_assertion`,
  `mutate_rename_assertion`, `mutate_delete_requirement`,
  `mutate_move_node_to_file`, `mutate_rename_file`, `mutate_fix_broken_reference`.
- Edge mutations (`mutate_add_edge`, `mutate_change_edge_kind`,
  `mutate_change_edge_targets`, `mutate_delete_edge`) guard on **both** endpoint
  repos.
- `mutate_add_requirement`: new reqs land in the root repo (no associate write);
  if `parent_id` resolves to an associate, guard on the parent.
- `save_mutations` relies on `render_save()`'s write filter as defense in depth:
  the guard prevents associate mutations from entering the log, and the filter
  guarantees a build-time dirty associate FILE is never persisted.

`get_workspace_info` surfaces the `write_associates` / `index_associates` state
so an agent can see why a mutation was rejected.

## Data flow

```text
build_graph()  ->  FederatedGraph (primary + associates)   [unchanged]
        |
        +-- read surfaces (checks/summary/Integrates) -> federate    [unchanged]
        |
        +-- WRITE surface: render_save(graph, write_associates)
        |        if not write_associates: skip non-root-repo FILE nodes
        |
        +-- GENERATE surface: _build_index_content / term-index
                 if not index_associates: skip non-root-repo nodes
```

## Testing

Tests written by a sub-agent; every test references a requirement. Use the
`test_e2e_associated` fixture (multi-repo: standard core + FDA associate).

1. **Bug regression (both flags off, default):**
   - After `elspais fix` from the primary, the associate repo working tree has
     **zero** changes.
   - The primary `spec/INDEX.md` requirement count equals the count produced by
     the same `fix` run with no associate configured (associate reqs absent from
     the primary INDEX). Same assertion for `term-index.md`.
2. **`write_associates=true`:** `fix` writes associate spec files (dirty after
   run); MCP mutate targeting an associate node succeeds and persists.
3. **`index_associates=true`:** generated `INDEX.md` includes associate rows.
4. **MCP read-only guard (`write_associates=false`):** a mutate targeting an
   associate-owned node returns `success: false` with the read-only error and
   applies no in-memory change; an edge mutation with one associate endpoint is
   likewise rejected.

## User-facing surfaces (mandatory updates)

- `docs/configuration.md` — document the `[federation]` table.
- `docs/cli/*.md` — note primary-only default on `fix` (and `index`).
- `src/elspais/commands/init.py` — add `[federation]` to the generated template.
- CLI help/epilog text and shell completion — reflect the new config section.
- **Spec requirements** (self-validating repo): add/extend REQs covering the
  federation write/generation scoping so tests can reference them; run
  `elspais fix` to regenerate `spec/_generated/*`.

## Acceptance criteria

- With defaults, `elspais fix` output for primary-repo files is byte-identical
  whether or not an associate is configured.
- Associate repos are never written by `fix` or MCP unless
  `federation.write_associates=true`.
- `INDEX.md` / `term-index.md` contain only primary reqs unless
  `federation.index_associates=true`.
- MCP mutates targeting associate nodes fail read-only when writes are disabled.
- `checks` / `summary` / cross-repo resolution continue to federate.
