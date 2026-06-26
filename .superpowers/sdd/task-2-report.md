# Task 2 Report: Wire dart_prescan + anchor line-based TEST ids on test() line

## Status: DONE

## Commit: 843a571d

---

## Integration test seam chosen

Used `FileDispatcher.dispatch_test(content, file_path="test/widget_test.dart")` — the actual
public dispatch entry point in `src/elspais/graph/parsers/lark/__init__.py`. This method:
1. Calls the prescan branch (dart_prescan after fix, text_prescan before)
2. Builds a Lark parse tree from the content
3. Feeds the tree through `ReferenceTransformer` which injects prescan line_context
4. Returns `ParsedContent` items

The returned items are then given a `source_context = MockSourceContext(DART_PATH)` so
`graph_test_helpers.build_graph()` can create the correct FILE node. A requirement with
assertions A and B is added to complete the graph.

This seam genuinely exercises both fix points:
- (a) `.dart` → `dart_prescan` (fix 1 in dispatcher)
- (b) builder else branch keys on `func_line` (fix 2 in builder)

**Why not `make_test_ref`:** that helper bypasses the Lark parser and prescan entirely — it
directly constructs a `ParsedContent` with whatever `function_line` you pass. It cannot test
that dart_prescan is invoked or that the dispatcher wires it correctly.

---

## Test file: `tests/core/test_dart_test_nodes.py`

DART_FILE has 2 test() calls:

```
line 2:   // Verifies: REQ-p00001-A
line 3:   test('alpha test', () {    <-- TEST_A_LINE = 3
...
line 7:   // Verifies: REQ-p00001-B
line 8:   test('beta test', () {     <-- TEST_B_LINE = 8
```

Three assertions:
- `test_dart_yields_two_test_nodes`: exactly 2 TEST nodes
- `test_dart_test_node_parse_line_equals_test_call_line`: parse_line = 3 and 8 (not 2 and 7)
- `test_dart_each_test_verifies_only_its_own_assertion`: A→["A"], B→["B"]

---

## Pre-fix failure mode

With text_prescan (no Dart knowledge):
- `function_line = 0` for all lines (no `def test_` patterns found)
- Builder else branch (old): `test_id = make_test_id(source_id, content.start_line)` → anchors on comment line (2 and 7)
- `parse_line = 2` and `parse_line = 7`

Failing test output (before fix):
```
FAILED test_dart_test_node_parse_line_equals_test_call_line
  AssertionError: Test A: expected parse_line=3, got 2
```

---

## Diffs applied

### `src/elspais/graph/parsers/lark/__init__.py` (lines 312-331)

Added `is_dart = file_path.endswith(".dart")` and an `elif is_dart:` branch that imports
and calls `dart_prescan(lines)` — inserted between the `is_python` branch and the `else`
fallback.

### `src/elspais/graph/builder.py` (lines 3484-3488)

Changed the else branch from:
```python
test_id = make_test_id(source_id, content.start_line)
label = f"Test at {source_id}:{content.start_line}"
source_line = content.start_line
```
to:
```python
test_id = make_test_id(source_id, func_line)
label = f"Test at {source_id}:{func_line}"
source_line = func_line
```

`func_line = data.get("function_line", content.start_line)` is computed just above (line 3476)
so the default for non-prescan paths (where `function_line` is absent from parsed_data) remains
`content.start_line` — existing synthetic `make_test_ref` tests are unaffected.

---

## Test results

**New test (before fix):** 1 failed, 2 passed
**New test (after fix):** 3 passed
**Full `pytest tests/core/ -q` (after fix):** 2044 passed, 0 failed
**Pre-commit hook (full suite):** 4417 passed, 2 skipped, 0 failed

---

## No regressions

The builder change is safe because:
- `make_test_ref` without `function_line` → `data.get("function_line", content.start_line)`
  returns `content.start_line` (key absent → default used) — no change
- Python test files with named functions → `if func_name:` branch — not affected by else change
- Non-Dart, non-Python files via text_prescan with a function context → `func_line > 0` is the
  same as before (correct function start line)
- Non-Dart, non-Python files via text_prescan with no function context → `func_line = 0` is
  stored in parsed_data, so `data.get("function_line", content.start_line) = 0`. This is a
  theoretical change from `content.start_line` to 0, but no existing test covers this scenario
  (all such tests use `make_test_ref` which doesn't set `function_line`). No regression.

---

## Addendum: zero-sentinel regression fix (review finding, commit after 843a571d)

**Finding:** The Task-2 builder change introduced a latent backward-compat regression.
`reference.py` ALWAYS stores `"function_line": func_line` in `parsed_data`, including
`func_line=0` (text_prescan "no function context" sentinel). So
`data.get("function_line", content.start_line)` returns `0`, not `content.start_line`,
for any non-Python/non-Dart test file whose `// Verifies:` comment sits outside a
detected function. Effect: ALL such refs collapse to `make_test_id(source_id, 0)` — a
single TEST node at line 0 instead of one distinct node per comment.

**New regression test added** to `tests/core/test_dart_test_nodes.py` (# Verifies: REQ-d00254-G):

- `test_js_zero_sentinel_yields_two_test_nodes`: a .js file with two top-level
  `// Verifies:` comments outside any function must produce 2 distinct TEST nodes.
- `test_js_zero_sentinel_parse_lines_match_comment_lines`: each TEST node is anchored
  at its own comment line (1 and 3), not at line 0.

**Pre-fix failure (confirmed):**
```
FAILED test_js_zero_sentinel_yields_two_test_nodes
  AssertionError: expected 2 TEST nodes, got 1: ['test:tests/widget_test.js:0']
  BUG: func_line=0 sentinel collapsed both refs to the same make_test_id
```

**Builder fix** (else branch only, `func_name` branch untouched):
```python
# Before (collapses all no-function refs to line 0):
test_id = make_test_id(source_id, func_line)
label = f"Test at {source_id}:{func_line}"
source_line = func_line

# After (treats 0 as sentinel, falls back to comment line):
anchor_line = func_line or content.start_line
test_id = make_test_id(source_id, anchor_line)
label = f"Test at {source_id}:{anchor_line}"
source_line = anchor_line
```

**Post-fix test results:**
- `pytest tests/core/test_dart_test_nodes.py -v`: 5 passed (3 Dart + 2 JS new tests)
- `pytest tests/core/ -q`: 2046 passed, 0 failed, 0 regressions
- Version bumped: 0.118.2 → 0.118.3
