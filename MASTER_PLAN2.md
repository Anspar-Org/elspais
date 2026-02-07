# MASTER PLAN — Unified Test/Result Scanning Architecture

**Branch**: `feature/CUR-240-unified-test-results`
**Ticket**: CUR-240

## Goal

Fix the test result visibility problem: 22 of 30 TEST_RESULT nodes are invisible because result parsers auto-create duplicate TEST nodes that never merge with scanner-created ones. Unify all parsing through a single pipeline where each node type has exactly one source.

## Principle: One source per node type, references for linkage

| Node Type | Source | Created By |
|-----------|--------|-----------|
| REQUIREMENT | spec files (`.md`) | RequirementParser |
| CODE | source files | CodeParser |
| TEST | test files (`.py`) | TestParser |
| TEST_RESULT | result files (`.xml`, `.json`) | JUnit/PytestParser |

TEST_RESULT nodes **reference** TEST nodes via a foreign key (`test_id`). If the referenced TEST doesn't exist, it's a broken reference (same handling as `Implements: REQ-nonexistent`).

## Implementation Steps

### Step 1: `test_identity.py` utility + tests

**NEW** `src/elspais/utilities/test_identity.py`

- `classname_to_module_path(classname)` converts dotted classnames to file paths:
  - `tests.core.test_foo.TestBar` -> `("tests/core/test_foo.py", "TestBar")`
  - Strip trailing uppercase-starting segments (class names), dots->slashes, append `.py`
- `build_test_id(module_path, test_name, class_name=None)` builds canonical ID:
  - `test:tests/core/test_foo.py::TestBar::test_func`
- `strip_parametrize_suffix(test_name)` strips `[...]` from parametrized tests

### Step 2: `claim_and_parse()` on result parsers + tests

Make `JUnitXMLParser` and `PytestJSONParser` implement the `LineClaimingParser` protocol:

- [ ] Add `priority = 90` class attribute
- [ ] Add `claim_and_parse(lines, context)` method that:
  - Joins line text, calls existing `parse()` method
  - Yields `ParsedContent(content_type="test_result", ...)` for each result
  - Uses `test_identity.py` utilities to compute proper `test_id`

### Step 3: Simplify `factory.py` to standard pipeline

- [ ] Replace 50 lines of manual result wiring (lines 230-282) with standard pipeline:
  - Create result registry, register JUnit/Pytest parsers
  - Use `DomainFile` + `domain_file.deserialize(result_registry)`
  - Same pattern as code/test scanning

### Step 4: TestParser function/class tracking + tests

- [ ] Track `current_function` when matching `def test_*` lines
- [ ] Track `current_class` when matching `class Test*:` lines
- [ ] Include `function_name` and `class_name` in `parsed_data`
- [ ] One TEST node per function (not per REQ-referencing line)
- [ ] File-level scope: `# Tests REQ-xxx` at module scope becomes default for all tests

### Step 5: Builder `_add_test_ref()` canonical IDs + tests

- [ ] Use `test:{relative_path}::{class_name::}?{function_name}` as ID when function_name available
- [ ] Convert absolute source path to relative using `self.repo_root`
- [ ] Fall back to line-based ID for comment refs outside functions

### Step 6: Builder `_add_test_result()` remove auto-creation + tests

- [ ] Remove lines 1765-1785 (auto-creation of TEST nodes)
- [ ] Keep TEST_RESULT node creation
- [ ] Keep CONTAINS edge queue to `test_id`
- [ ] If `test_id` doesn't exist at link resolution time, it becomes a broken reference

### Step 7: Generator orphan handler fix

- [ ] Track `visited_node_ids: set[str]` during traversal
- [ ] After root traversal, iterate unvisited TEST nodes and render them with children
- [ ] Change orphan TEST_RESULT condition from `parent_count() > 0` to `node.id in visited_node_ids`

### Step 8: Update tests with old TEST ID format

- [ ] Find all tests referencing old line-based IDs (`test:path:line`)
- [ ] Update to new canonical format (`test:path::class::func`)

## Files to Modify

| File | Change |
|------|--------|
| **NEW** `src/elspais/utilities/test_identity.py` | `classname_to_module_path()`, `build_test_id()` |
| `src/elspais/graph/parsers/results/junit_xml.py` | Add `claim_and_parse()`, `priority`, compute `test_id` via utility |
| `src/elspais/graph/parsers/results/pytest_json.py` | Same as JUnit |
| `src/elspais/graph/parsers/test.py` | Function/class tracking, emit `function_name`/`class_name` |
| `src/elspais/graph/factory.py` | Replace manual result wiring with standard pipeline |
| `src/elspais/graph/builder.py` | Canonical IDs in `_add_test_ref()`, remove auto-creation from `_add_test_result()` |
| `src/elspais/html/generator.py` | Fix orphan handler to use visited tracking |

## What Stays the Same

- TraceGraph, GraphNode, GraphBuilder structure
- NodeKind, EdgeKind enums
- ParserRegistry, DomainFile, ParsedContent, LineClaimingParser protocol
- annotate_coverage()
- Existing `parse()` methods on result parsers (called internally by new `claim_and_parse()`)
- Broken reference handling infrastructure

## Conventions for Requirement Coverage

### Convention 1: REQ in test function names (existing)

```python
def test_REQ_p00001_A_validates_input(self):
    ...
```

### Convention 2: Comment-based references (existing)

```python
# Tests REQ-d00050-E
def test_annotates_uncommitted(self):
    ...
```

### Convention 3: File-level scope (new)

```python
# Tests REQ-d00050
class TestAnnotateGitState:
    def test_annotates_uncommitted(self): ...
    def test_annotates_moved(self): ...
```

### Parametrized test handling

Strip `[...]` suffix: `test_REQ_p00001_A_foo[1-2]` -> `test_id = test:path::test_REQ_p00001_A_foo`

## Verification

1. `python -m pytest tests/ -x -q` -- all pass
2. `python -m elspais trace --view --embed-content -o /tmp/trace.html`
3. `grep -c 'data-is-test-result="true"' /tmp/trace.html` -> 30
4. MCP `get_graph_status()` -- result count 30
5. TEST_RESULT nodes visible under parent TEST in tree

## Archive

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
