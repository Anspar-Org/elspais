# MASTER PLAN — MCP get_requirement Round-Trip Fidelity

**CURRENT_ASSERTIONS**: REQ-d00062-B, REQ-d00064-B

## Context

The MCP `get_requirement` tool must return enough data to reconstruct the original requirement from the graph (ignoring whitespace). Phases 1-5 (archived) added section extraction, REMAINDER child nodes, and body_text/remainder/source to the MCP serializer.

**Goal**: Line numbers for document-order reconstruction. Flat children list. Parent edge kinds exposed.

## Phase 6: Parser -- Line Numbers on Assertions and Sections

**File**: `src/elspais/graph/parsers/requirement.py`

- [x] Add `start_line` param to `_parse_requirement()`
- [x] `_extract_assertions()`: accept `start_line`, compute `line = start_line + text[:match.start()].count('\n')` per assertion
- [x] `_extract_sections()`: accept `start_line` + raw `text`, compute absolute line per section heading
- [x] `claim_and_parse()`: pass `start_line` to `_parse_requirement()`
- [x] Each assertion dict returns `{"label", "text", "line"}`
- [x] Each section dict returns `{"heading", "content", "line"}`
- [x] Verify: `pytest tests/core/test_parsers/test_requirement_parser.py` passes

## Phase 7: Builder -- Source Locations + Document-Order Children

**File**: `src/elspais/graph/builder.py`, `_add_requirement()`

- [x] Set `source=SourceLocation(path, line)` on assertion nodes from `assertion["line"]`
- [x] Set accurate `source=SourceLocation(path, line)` on REMAINDER section nodes from `section["line"]`
- [x] Collect all children (assertions + sections) into one list, sort by line, then `add_child()` in order
- [x] Verify: `pytest tests/mcp/test_mcp_core.py` passes

## Phase 8: MCP Serializer -- Flat Children + Edge Kind on Parents

**File**: `src/elspais/mcp/server.py`, `_serialize_requirement_full()`

- [x] Replace separate `assertions`/`remainder`/`children` with one flat `children` list
- [x] Each child entry includes `kind` ("assertion" | "remainder" | other), `id`, `line`, and kind-specific fields
- [x] Add `edge_kind` field to each parent entry (from `node.iter_outgoing_edges()` target→kind map)
- [x] Return dict: `{id, title, level, status, hash, body_text, children, parents, source}`
- [x] Verify: `pytest tests/mcp/test_mcp_core.py` passes

## Phase 9: Tests

- [x] Parser: assertions and sections include `line` key
- [x] Builder: children iterate in document order (preamble before assertions before rationale)
- [x] MCP: flat `children` list, `edge_kind` on parents
- [x] Verify: full test suite passes

## Phase 10: Commit

- [x] Update version in `pyproject.toml`
- [x] Update CHANGELOG.md
- [x] Update CLAUDE.md if needed
- [x] Commit with assertion references

## Archive

- [x] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
