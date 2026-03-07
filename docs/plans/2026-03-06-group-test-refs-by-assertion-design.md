# Group Test Refs by Assertion in Trace Reports

## Problem

The trace report lists test refs as a flat list under each requirement. This is misleading: a requirement with assertions A, B, C, D might show 12 test refs, but most only cover assertion D. The flat list obscures which assertions are actually tested.

## Design

### Core Data Change

In `_get_node_data()`, add `test_refs_grouped: dict[str, list[str]]` alongside the existing flat `test_refs`. Keys are assertion labels; `"*"` is used for whole-requirement tests (edges with no `assertion_targets`). The grouping is derived from `edge.assertion_targets` on outgoing edges from the requirement to TEST children.

### Markdown

Group test refs under assertion labels with counts:

```markdown
<details><summary>Test Refs (12)</summary>

**Whole-requirement** (3):
- `test:tests/core/test_builder.py:1`
- `test:tests/core/test_html/test_generator.py:2`
- `test:tests/test_trace_command.py:2`

**D** (9):
- `test:tests/mcp/test_matches_query.py::TestSingleCodePath::test_REQ_p00050_D_returns_bool`
- ...

</details>
```

### HTML Table

Same grouping rendered with `<strong>` labels and `<br>` separators within the test refs cell.

### JSON

Replace flat `test_refs` list with grouped dict:

```json
{
  "test_refs": {
    "*": ["test:tests/core/test_builder.py:1"],
    "D": ["test:tests/mcp/test_matches_query.py::..."]
  }
}
```

### CSV

Add a `Kind` column (column 1) to indicate row type. When test refs are included, emit child rows after each requirement:

```
Kind,ID,Title,Level,Status,Implemented,Validated,Passing,Assertion,Test Ref
REQ,REQ-p00050,Unified Graph Architecture,prd,Active,4/4 (100%),4/4 (100%),0/4 (0%),,
TEST,REQ-p00050,,,,,,,*,test:tests/core/test_builder.py:1
TEST,REQ-p00050,,,,,,,D,test:tests/mcp/test_matches_query.py::...
```

`Kind` values: `REQ` for requirement rows, `TEST` for test ref rows. `Assertion` column shows which assertion the test covers (`*` = whole-req).

## Scope

Files modified:
- `src/elspais/commands/trace.py` — `_get_node_data()`, `format_markdown()`, `format_html()`, `format_json()`, `format_csv()`
- Tests for each formatter

## Out of Scope

- `format_view()` (interactive HTML via HTMLGenerator) — separate rendering pipeline
- ASRT row kind in CSV for assertions — future enhancement
