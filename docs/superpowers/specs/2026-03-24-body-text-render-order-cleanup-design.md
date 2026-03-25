# Design: Remove body_text and Add render_order to STRUCTURES Edges

**Date:** 2026-03-24
**Status:** Draft
**Branch:** graph-cleanup

## Problem

Two related structural issues in the graph:

1. **STRUCTURES edges lack explicit ordering.** CONTAINS edges (FILE->content) carry `render_order` metadata for robust sorting, but STRUCTURES edges (REQ->ASSERTION, REQ->REMAINDER) rely on insertion order. This is fragile if sections are moved or reordered via mutations.

2. **`body_text` is a redundant field.** It stores the raw unparsed body of a requirement as a flat string, duplicating content already parsed into structured ASSERTION and REMAINDER children. Four mutation helpers perform regex text-surgery to keep it in sync. The render protocol already reconstructs output from structured children, proving `body_text` is unnecessary.

These are coupled: robust ordering (Phase 1) makes body_text removal (Phase 2) safe.

## Phase 1: render_order on STRUCTURES Edges

### Build-time Assignment

In `builder.py` (~line 2760-2764), after sorting children by line number, assign `render_order` as edge metadata on each STRUCTURES edge. Pattern matches `_wire_contains_edge()`:

```python
edge_meta = {"render_order": float(line_number)}
node.link(child_node, EdgeKind.STRUCTURES, metadata=edge_meta)
```

### Mutation Maintenance

- `mutate_add_assertion()`: Assign render_order to the new STRUCTURES edge. Use max existing render_order + 1.0 (or compute an insertion point if label-sorted ordering matters).
- `mutate_delete_*()`: No change needed — edge removed with the node.
- Undo paths: Ensure restored links carry original metadata.

### Render Path

`_render_requirement()` in `render.py` (~line 121): Read `render_order` from STRUCTURES edge metadata and sort children by it, same as `render_file()` does for CONTAINS children. Fall back to insertion order if metadata absent (backward compat with in-memory graphs built before this change).

### API Exposure

Expose render_order in MCP server and routes_api where children are serialized, so the viewer can sort by it.

## Phase 2: Remove body_text Field

### Parsers — Stop Setting It

- **Lark transformer** (`parsers/lark/transformers/requirement.py` ~line 225, 252): Remove `_extract_body_text()` call and method. Remove `body_text` from `parsed_data`.
- **Regex parser** (`parsers/requirement.py`): Removed entirely (see Phase 2b).

### Hash Computation — Compute From Structured Children

The hash must be computed **before** rendering (since the renderer embeds the hash in the `*End*` footer). This avoids a circular dependency.

For `full-text` mode, compute the hash directly from structured children:

1. Walk STRUCTURES children in render_order.
2. For each ASSERTION child: format as `{label}. {text}`.
3. For each REMAINDER child: use its stored text.
4. Concatenate all pieces (preserving document order via render_order).
5. Pass the result through `clean_requirement_body()` (which strips the Changelog section).
6. Hash with `calculate_hash()`.

This replaces reading `node.get_field("body_text")` with an on-demand reconstruction from the same structured children the renderer uses, ensuring consistency.

Affected sites:
- `builder.py` `_compute_hash()` (~line 1177-1197): Full-text mode reconstructs body from STRUCTURES children.
- `render.py` (~line 175): Same approach — compute hash from children before emitting footer.
- `validate.py` `compute_hash_for_node()` (~line 66): Same approach.

Normalized-text mode is unchanged (already uses structured assertions).

**Hash migration note:** Projects using `full-text` mode may see hash changes after this refactor due to whitespace normalization differences between the original parsed `body_text` and the reconstructed text. Run `elspais validate --fix` after upgrade to regenerate hashes.

### Search — Iterate Structured Children

Replace `node.get_field("body_text")` with iteration over STRUCTURES children:

- `search_cmd.py` (~line 124): Iterate children, match against each REMAINDER `.get_field("text")` and ASSERTION text.
- `mcp/search.py` `_get_field_text()` (~line 134): Same iteration pattern.
- `mcp/server.py` (~line 672): Same for regex field search.

### API Serialization — Drop the Field

Three callsites in `mcp/server.py`:
- Line 373: `_node_to_dict()` properties block — remove `body_text` key.
- Line 672: Regex field search — handled above under "Search — Iterate Structured Children."
- Line 1325: `_get_requirement()` detail endpoint — remove `body` key.

No replacement field needed: structured children (assertions, remainder sections) are already returned in the response and carry the same data.

### Delete Mutation Helpers

Remove from `builder.py` (lines 1082-1175):
- `_update_assertion_in_body_text()`
- `_add_assertion_to_body_text()`
- `_delete_assertion_from_body_text()`
- `_rename_assertion_in_body_text()`

Remove their call sites in `mutate_update_assertion()`, `mutate_add_assertion()`, `mutate_delete_assertion()`, `mutate_rename_assertion()`.

### Template Cloning

Template-instance cloning (~line 3176) copies all content fields via `get_all_content()`. After Phase 2, `body_text` will no longer exist in content, so no explicit exclusion is needed — it becomes a no-op.

## Phase 2b: Remove RequirementParser

### Stop Registration

`factory.py` line 320: Remove `RequirementParser` registration. Lark parser handles all requirement parsing.

### Relocate Shared Regex Constants

Move these 4 constants from `parsers/requirement.py` to a new `parsers/patterns.py`:
- `ASSERTION_LINE_PATTERN`
- `IMPLEMENTS_PATTERN`
- `REFINES_PATTERN`
- `ALT_STATUS_PATTERN`

Update imports and access patterns:
- `builder.py`: Remove `from elspais.graph.parsers.requirement import RequirementParser` import. Replace class attribute `_ASSERTION_LINE_RE = RequirementParser.ASSERTION_LINE_PATTERN` with direct import from `parsers.patterns`. Both changes must happen in the same commit to avoid import failures.
- `spec_writer.py`: Replace `RequirementParser.IMPLEMENTS_PATTERN` (and REFINES, ALT_STATUS) class-attribute access with direct module imports from `parsers.patterns`.

Delete `parsers/requirement.py`.

## Testing

### Phase 1 Tests

- Build a requirement with assertions + remainder sections; verify STRUCTURES edges carry render_order metadata in document order.
- `mutate_add_assertion()` assigns render_order to new edge.
- Render output is identical before/after (ordering preserved).

### Phase 2 Tests

- `get_field("body_text")` returns None after build.
- Full-text hash computed from structured children matches normalized-text hash for equivalent content.
- Search matches body content via structured children iteration.
- Assertion mutations work correctly without body_text helpers.
- E2E: `elspais checks`, `elspais search`, `elspais validate` all pass.
- E2E: MCP search and get_requirement endpoints return correct data without body_text field.

### Phase 2b Tests

- Lark parser handles all fixture files previously handled by RequirementParser.
- spec_writer works with relocated patterns.

## Commit Plan

- **Commit 1:** Phase 1 — render_order on STRUCTURES edges
- **Commit 2:** Phase 2 + 2b — Remove body_text, remove RequirementParser, relocate patterns
