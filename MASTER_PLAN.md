# MASTER PLAN — MCP Query Bug Fixes

**CURRENT_ASSERTIONS**: REQ-d00061-B (search body field), TBD (level normalization, keywords)

## Context

MCP tool testing against the hht_diary project revealed three bugs:
1. Level casing inconsistency — parser stores raw spec text without normalizing to config-defined canonical type keys
2. Keywords never populated — `annotate_keywords()` implemented but never wired into `build_graph()`
3. Search body field missing — REQ-d00061-B requires `field="body"` but implementation omits it

## Phase 1: Level Normalization to Config Type Keys

### Design

Config defines canonical type keys (`prd`, `ops`, `dev`) and names (`"PRD"`, `"Product Requirement"`, etc.). Key and name refer to the same type — key is shorthand, name is readable. The parser resolves spec file text to the canonical type key. Consumers needing display names look up the name from config.

### 1.1 Add `resolve_level()` to `PatternConfig`

**File**: `src/elspais/utilities/patterns.py`

Add method after `get_type_by_id` (~line 91):
- Case-insensitive match against config type keys
- Returns canonical key or None

### 1.2 Parser normalizes at parse time

**File**: `src/elspais/graph/parsers/requirement.py:194`

After capturing raw level text, resolve through `self.pattern_config.resolve_level()`. Fall back to raw text if unrecognized.

### 1.3 `count_by_level()` derives keys from config

**File**: `src/elspais/graph/annotators.py:192-215`

Accept optional config param. Derive initial dict keys from `config["patterns"]["types"].keys()` instead of hardcoding `{"PRD", "OPS", "DEV"}`.

### 1.4 `group_by_level()` same treatment

**File**: `src/elspais/graph/annotators.py:218-236`

Remove `.upper()` workaround. Derive group keys from config.

### 1.5 Update callers

- `src/elspais/mcp/server.py:419` — pass config
- `src/elspais/commands/analyze.py:128` — pass config

### 1.6 Tests + Verify

- [ ] Test `resolve_level()` maps "Dev"->"dev", "PRD"->"prd", unknown->fallback
- [ ] Test parser stores canonical keys
- [ ] Test `count_by_level` with config-derived keys
- [ ] `pytest tests/ -x`

## Phase 2: Wire `annotate_keywords()` into `build_graph()`

**File**: `src/elspais/graph/factory.py:284`

Call `annotate_keywords(graph)` after `builder.build()`, before return. All callers get keywords automatically.

### Tests + Verify

- [ ] Test that `build_graph()` produces nodes with populated keywords
- [ ] `pytest tests/ -x`

## Phase 3: Add Body Field to Search

**File**: `src/elspais/mcp/server.py:280`

REQ-d00061-B requires `field="body"`. Add body search between title and keywords blocks using `node.get_field("body_text", "")`. Return type stays as-is (list, per spec REQ-d00061-D).

### Tests + Verify

- [ ] Test `_search(graph, "SHALL", field="body")` returns results
- [ ] `pytest tests/ -x`

## Phase 4: Integration Verification

- [ ] Re-run hht_diary MCP test script
  - `get_project_summary` returns canonical type keys
  - `get_all_keywords` returns >0 keywords
  - `search(query="SHALL", field="body")` returns results
- [ ] Full test suite passes
- [ ] Commit with assertion references
