# Graph Architecture Reference

**Purpose:** Reference documentation for sub-agents working on the test parsing unification refactor.

---

## Node Types (`NodeKind` enum)

| Kind | Description |
|------|-------------|
| `REQUIREMENT` | Spec requirement with title, body, assertions |
| `ASSERTION` | Testable obligation (child of requirement) |
| `CODE` | Implementation file reference |
| `TEST` | Test file reference |
| `TEST_RESULT` | Test execution result |
| `USER_JOURNEY` | Non-normative context provider |

---

## TraceNode Core Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `str` | Unique identifier |
| `kind` | `NodeKind` | Node type |
| `label` | `str` | Human-readable display label |
| `source` | `SourceLocation` | **File + line reference** |
| `children` | `list[TraceNode]` | Child nodes |
| `parents` | `list[TraceNode]` | Parent nodes (DAG) |

---

## SourceLocation (File Reference)

| Attribute | Type | Description |
|-----------|------|-------------|
| `path` | `str` | Relative to repo root |
| `line` | `int` | 1-based line number |
| `end_line` | `int\|None` | End line for ranges |
| `repo` | `str\|None` | Multi-repo namespace (e.g., "CAL") |

---

## Typed Content Fields (one per node based on kind)

| Field | Populated When | Content |
|-------|----------------|---------|
| `requirement` | `kind=REQUIREMENT` | Full `Requirement` object |
| `assertion` | `kind=ASSERTION` | `Assertion` object |
| `code_ref` | `kind=CODE` | `CodeReference` (file, line, symbol) |
| `test_ref` | `kind=TEST` | `TestReference` (file, line, test_name, test_class) |
| `test_result` | `kind=TEST_RESULT` | `TestResult` (status, duration, message) |
| `journey` | `kind=USER_JOURNEY` | `UserJourney` (actor, goal, steps) |

---

## Requirement Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique ID (e.g., "REQ-p00001") |
| `title` | `str` | Requirement title |
| `level` | `str` | Type name (PRD, OPS, DEV) |
| `status` | `str` | Active, Draft, Deprecated |
| `body` | `str` | Main text |
| `implements` | `list[str]` | Parent requirement IDs |
| `acceptance_criteria` | `list[str]` | Legacy format |
| `assertions` | `list[Assertion]` | New format |
| `rationale` | `str\|None` | Non-normative explanation |
| `hash` | `str\|None` | Content hash (8 chars) |
| `file_path` | `Path\|None` | Source file |
| `line_number` | `int\|None` | Line in source |
| `tags` | `list[str]` | Optional tags |
| `subdir` | `str` | Subdirectory (e.g., "roadmap") |
| `is_conflict` | `bool` | Duplicate detection |
| `conflict_with` | `str` | Original ID if conflict |

---

## Computed Metrics (stored in `node.metrics`)

| Metric | Description |
|--------|-------------|
| `_validates_targets` | List of requirement IDs this test validates |
| `_expected_broken_targets` | IDs expected to be broken (marker suppression) |
| `_test_status` | "passed", "failed", "skipped", "unknown" |
| `_rollup` | `RollupMetrics` object (intermediate) |
| `total_assertions` | Rolled-up assertion count |
| `covered_assertions` | Assertions with tests |
| `total_tests` | Test count |
| `passed_tests` | Passed test count |
| `failed_tests` | Failed test count |
| `skipped_tests` | Skipped test count |
| `total_code_refs` | Code reference count |
| `coverage_pct` | Coverage percentage |
| `pass_rate_pct` | Pass rate percentage |
| `test_name` | From JUnit/pytest result |
| `test_class` | From JUnit/pytest result |

---

## Relationship Schema

| Attribute | Description |
|-----------|-------------|
| `name` | Relationship name (implements, validates, etc.) |
| `from_kind` | Valid source node types |
| `to_kind` | Valid target node types |
| `direction` | "up" (child→parent) or "down" (parent→child) |
| `source_field` | Field containing target IDs |
| `extract_from_content` | Parse from file content |
| `required_for_non_root` | Orphan check flag |
| `attach_during_parse` | Link during parse phase |

---

## Default Relationships

| Name | From | To | Direction |
|------|------|----|-----------|
| `implements` | requirement | requirement | up |
| `addresses` | requirement | user_journey | up |
| `validates` | test, code | requirement, assertion | up |
| `produces` | test | test_result | down |

---

## Validation Checks

| Check | Description |
|-------|-------------|
| `orphan_check` | Non-root nodes without parents |
| `cycle_check` | Circular dependencies |
| `broken_link_check` | References to non-existent IDs |
| `duplicate_id_check` | Duplicate IDs |
| `assertion_coverage_check` | Assertions without tests |
| `level_constraint_check` | Hierarchy level rules |

---

## TraceGraph Container

| Method/Attribute | Description |
|------------------|-------------|
| `roots` | Top-level nodes |
| `repo_root` | Repository path |
| `_index` | Fast lookup by ID |
| `find_by_id(id)` | Get node by ID |
| `all_nodes(order)` | Iterate all nodes |
| `nodes_by_kind(kind)` | Filter by type |
| `accumulate(...)` | Compute metrics leaf→root |
| `node_count()` | Total nodes |
| `count_by_kind()` | Counts by type |

---

## Node Traversal Methods

| Method | Description |
|--------|-------------|
| `walk(order)` | pre/post/level order traversal |
| `ancestors()` | BFS up through parents |
| `find(predicate)` | Filter descendants |
| `find_by_kind(kind)` | Filter by type |
| `depth` | Minimum depth from root |

---

## Parsing Approach Evaluation

### Option 1: Formal Grammar (Lex/Yacc, ANTLR)
- ❌ External dependency (violates zero-dependency principle)
- ❌ Poor error messages ("syntax error at line X")
- ❌ Hard to add "did you mean...?" suggestions
- ✅ Provably correct parsing

### Option 2: PEG Libraries (lark, pyparsing)
- ❌ Still a dependency
- ❌ Grammar complexity for multi-format (Markdown + TOML + code)
- ✅ More Pythonic than lex/yacc

### Option 3: Custom Implementation (Current)
- ✅ Zero dependencies
- ✅ Rich, context-aware error messages
- ✅ Easy to evolve patterns
- ❌ More code to maintain

### Option 4: Schema-Driven Custom (Recommended)
Patterns defined declaratively in schema, custom code for execution:

```toml
[patterns.references]
validates = "(?:Validates|VALIDATES)[:\\s]+{id_pattern}"
implements = "(?:IMPLEMENTS|Implements)[:\\s]+{id_pattern}"

[patterns.suggestions]  # Fuzzy match → correction
"Validate:" = "Did you mean 'Validates:'?"
"implements " = "Did you mean 'Implements:' (with colon)?"
```

**Benefits:**
- Patterns are declarative and configurable
- Custom code provides rich error suggestions
- Zero dependencies maintained
- Schema drives both parsing AND validation

---

## Key Files

| File | Purpose |
|------|---------|
| `src/elspais/core/graph.py` | TraceNode, TraceGraph, NodeKind, SourceLocation |
| `src/elspais/core/graph_schema.py` | GraphSchema, RelationshipSchema, NodeTypeSchema |
| `src/elspais/core/graph_builder.py` | TraceGraphBuilder, ValidationResult |
| `src/elspais/parsers/test.py` | TestParser (to be enhanced) |
| `src/elspais/testing/scanner.py` | TestScanner (to be deleted) |
| `src/elspais/commands/trace.py` | CLI command using graph builder |
