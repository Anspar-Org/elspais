# MASTER PLAN — MCP get_requirement Round-Trip Fidelity

**CURRENT_ASSERTIONS**: REQ-d00062-B, REQ-d00064-B

## Context

The MCP `get_requirement` tool must return enough data to reconstruct the original requirement from the graph (ignoring whitespace). This violates REQ-d00062-B ("SHALL return node fields: id, title, level, status, hash, body") and REQ-d00064-B ("SHALL return all fields including body, assertions, edges").

**Goal**: Every line of a requirement accounted for. Non-normative sections as separate REMAINDER child nodes. Flat children list with line numbers for document-order reconstruction. Parent edge kinds exposed.

## Completed Work

- [x] Parser: `_extract_sections()` splits body_text into named sections
- [x] Builder: creates REMAINDER child nodes from sections
- [x] MCP serializer: returns `body_text`, `remainder`, `source` fields

## Phase 6: Parser -- Line Numbers on Assertions and Sections

**File**: `src/elspais/graph/parsers/requirement.py`

- [ ] Add `start_line` param to `_parse_requirement()`
- [ ] `_extract_assertions()`: accept `start_line`, compute `line = start_line + text[:match.start()].count('\n')` per assertion
- [ ] `_extract_sections()`: accept `start_line` + raw `text`, compute absolute line per section heading
- [ ] `claim_and_parse()`: pass `start_line` to `_parse_requirement()`
- [ ] Each assertion dict returns `{"label", "text", "line"}`
- [ ] Each section dict returns `{"heading", "content", "line"}`
- [ ] Verify: `pytest tests/core/test_parsers/test_requirement_parser.py` passes

## Phase 7: Builder -- Source Locations + Document-Order Children

**File**: `src/elspais/graph/builder.py`, `_add_requirement()`

- [ ] Set `source=SourceLocation(path, line)` on assertion nodes from `assertion["line"]`
- [ ] Set accurate `source=SourceLocation(path, line)` on REMAINDER section nodes from `section["line"]`
- [ ] Collect all children (assertions + sections) into one list, sort by line, then `add_child()` in order
- [ ] Verify: `pytest tests/mcp/test_mcp_core.py` passes

## Phase 8: MCP Serializer -- Flat Children + Edge Kind on Parents

**File**: `src/elspais/mcp/server.py`, `_serialize_requirement_full()`

- [ ] Replace separate `assertions`/`remainder`/`children` with one flat `children` list
- [ ] Each child entry includes `kind` ("assertion" | "remainder" | other), `id`, `line`, and kind-specific fields
- [ ] Add `edge_kind` field to each parent entry (from `node.iter_outgoing_edges()` target→kind map)
- [ ] Return dict: `{id, title, level, status, hash, body_text, children, parents, source}`
- [ ] Verify: `pytest tests/mcp/test_mcp_core.py` passes

## Phase 9: Tests

- [ ] Parser: assertions and sections include `line` key
- [ ] Builder: children iterate in document order (preamble before assertions before rationale)
- [ ] MCP: flat `children` list, `edge_kind` on parents
- [ ] Verify: full test suite passes

## Phase 10: Commit

- [ ] Update version in `pyproject.toml`
- [ ] Update CHANGELOG.md
- [ ] Update CLAUDE.md if needed
- [ ] Commit with assertion references
