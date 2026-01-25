# Future Plan: MCP Graph Integration

**Status:** Planned for Phase 2
**Focus:** Interactive graph manipulation during Claude Code sessions

---

## Vision

Enable Claude Code to work with the traceability graph as a live, bidirectional data structure during sessions. Changes to spec files update the graph; graph operations can modify spec files. The graph serves both interactive development workflows and auditor review sessions.

---

## Primary Use Cases

### UC1: Reference Manipulation

Claude Code modifies `Implements:` and `Refines:` references while working with the user.

| Operation | Example | Graph Effect |
|-----------|---------|--------------|
| Add reference | `Implements: REQ-p00001` | Create edge REQ→REQ |
| Specialize reference | `Implements: REQ-p00001-A-B` | Create edges REQ→Assertion |
| Remove reference | Delete `Implements:` line | Remove edge(s) |
| Convert type | `Implements:` → `Refines:` | Change edge type (coverage rollup disabled) |

**Workflow:**
1. User asks: "Change REQ-d00005 to implement only assertion A of REQ-p00001"
2. Claude edits spec file: `Implements: REQ-p00001` → `Implements: REQ-p00001-A`
3. Graph detects file change, updates edges
4. Coverage metrics recalculate

### UC2: Implements → Refines Conversion

User wants to change a requirement from claiming satisfaction to adding detail.

**Before:** REQ-d00005 `Implements: REQ-p00001` (claims to satisfy parent)
**After:** REQ-d00005 `Refines: REQ-p00001` (adds detail, no coverage rollup)

**Graph impact:**
- Edge type changes from `implements` to `refines`
- Parent's coverage no longer includes this child's metrics
- Parent may show coverage gap (intentional)

### UC3: Moving Requirements Between Files

REQ and JNY nodes can be moved to different markdown files.

**Scenarios:**
1. Split large spec file into smaller focused files
2. Reorganize by feature area
3. Move roadmap items to main spec
4. Create new category files

**Graph behavior:**
- `source_file` and `line_number` update on affected nodes
- ID remains stable (no graph structure change)
- References to moved node remain valid
- Backlinks update automatically

**Example:**
```
# Before
spec/platform.md contains REQ-p00001, REQ-p00002, REQ-p00003

# User request
"Move REQ-p00002 and REQ-p00003 to a new file spec/authentication.md"

# After
spec/platform.md contains REQ-p00001
spec/authentication.md contains REQ-p00002, REQ-p00003
Graph: same structure, updated file locations
```

### UC4: Spec File Deletion Workflow

Delete a spec file after all requirements have been moved elsewhere.

**Pre-conditions:**
- All REQ and JNY entries moved to other files
- Only descriptive text (context, overview) remains

**Workflow:**
1. User asks: "I want to delete spec/legacy-auth.md but keep the useful context"
2. Claude identifies remaining non-requirement content
3. Claude extracts and consolidates with target file (e.g., append to spec/authentication.md)
4. Claude deletes now-empty source file
5. Graph already updated (no nodes pointed to this file)

### UC5: Bidirectional Synchronization

**Filesystem → Graph:**
- File modification detected via mtime
- Incremental re-parse of changed file only
- Graph edges updated, metrics recomputed

**Graph → Filesystem:**
- MCP tool modifies graph relationship
- Corresponding spec file updated
- Format preserved (whitespace, comments)

**Sync triggers:**
| Event | Action |
|-------|--------|
| File saved | Mark graph stale for that file |
| MCP query | Refresh stale portions only |
| Explicit refresh | Full rebuild |
| Time-based (optional) | Periodic check |

### UC6: Lazy Graph Recreation

Graph should only rebuild when:
1. A query or operation is requested AND
2. Something has actually changed

**Implementation strategy:**
```python
@dataclass
class GraphState:
    graph: TraceGraph
    validation: ValidationResult
    file_mtimes: Dict[Path, float]  # Tracked files and their mtimes at build time

    def is_stale(self) -> bool:
        """Check if any tracked file changed since last build."""
        for path, mtime in self.file_mtimes.items():
            if not path.exists():
                return True  # File deleted
            if path.stat().st_mtime > mtime:
                return True  # File modified
        # Also check for new files in spec directories
        return self._has_new_spec_files()

    def partial_refresh(self, changed_files: List[Path]) -> None:
        """Refresh only affected portions of graph."""
        # Re-parse changed files
        # Update graph nodes with new source locations
        # Recompute affected metrics
        pass
```

**Optimization levels:**
1. **Basic:** Full rebuild on any change
2. **Smart:** Track file mtimes, rebuild only when stale
3. **Incremental:** Re-parse only changed files, update affected subgraph

### UC7: Auditor Review Session

User is working with an auditor reviewing a compliant software platform.

**Capabilities needed:**

| Auditor Question | MCP Response |
|------------------|--------------|
| "Show me all PRD-level requirements" | List requirements where level=PRD |
| "What implements REQ-p00001?" | Traverse children: OPS→DEV→Code→Tests |
| "Is REQ-p00001 fully covered?" | Coverage metrics + breakdown by assertion |
| "Show me the test that validates assertion A" | Test node with file path, function name |
| "What code files implement this?" | Code references with line numbers |
| "Show me REQ-p00001-A in context" | Display assertion text + surrounding requirement |
| "What requirements are orphaned?" | Validation result: orphan list |
| "Show the full traceability path" | Graph traversal: REQ→Assertion→Code→Test→Result |

**Interactive navigation:**
1. Auditor asks about a requirement
2. Claude shows the requirement, its assertions, coverage status
3. Auditor asks to see implementing code
4. Claude shows code file with `# Implements: REQ-xxx-A` comment
5. Auditor asks about test coverage
6. Claude shows test file, test function, pass/fail status

---

## Data Model Enhancements

### Tracked Files Registry

```python
@dataclass
class TrackedFile:
    path: Path
    mtime: float
    node_ids: Set[str]  # Requirements/journeys in this file

@dataclass
class WorkspaceState:
    spec_files: Dict[Path, TrackedFile]
    test_files: Dict[Path, TrackedFile]
    code_files: Dict[Path, TrackedFile]
```

### Graph Modification Operations

```python
class GraphMutator:
    """Apply modifications to graph and sync to filesystem."""

    def change_reference_type(
        self,
        source_id: str,
        target_id: str,
        new_type: Literal["implements", "refines"]
    ) -> None:
        """Change Implements: ↔ Refines: in spec file."""

    def update_references(
        self,
        source_id: str,
        new_references: List[str]
    ) -> None:
        """Replace all Implements:/Refines: for a requirement."""

    def move_requirement(
        self,
        req_id: str,
        target_file: Path,
        after_id: Optional[str] = None
    ) -> None:
        """Move requirement to different file."""

    def extract_content(
        self,
        source_file: Path,
        exclude_ids: Set[str]
    ) -> str:
        """Extract non-requirement content for consolidation."""
```

---

## MCP Tools (Write Operations)

### Relationship Management

```python
@mcp.tool()
def change_reference_type(
    source_id: str,
    target_id: str,
    new_type: Literal["implements", "refines"]
) -> Dict[str, Any]:
    """
    Change a requirement's reference from Implements to Refines or vice versa.

    Args:
        source_id: The requirement being modified (e.g., REQ-d00005)
        target_id: The referenced requirement (e.g., REQ-p00001)
        new_type: "implements" or "refines"

    Returns:
        Updated requirement details and coverage impact
    """

@mcp.tool()
def specialize_reference(
    source_id: str,
    target_id: str,
    assertions: List[str]
) -> Dict[str, Any]:
    """
    Convert REQ→REQ reference to REQ→Assertion references.

    Args:
        source_id: The requirement being modified
        target_id: The parent requirement (e.g., REQ-p00001)
        assertions: Specific assertions (e.g., ["A", "B"])

    Example:
        specialize_reference("REQ-d00005", "REQ-p00001", ["A", "B"])
        # Changes: Implements: REQ-p00001 → Implements: REQ-p00001-A-B
    """
```

### File Operations

```python
@mcp.tool()
def move_requirement(
    req_id: str,
    target_file: str,
    position: Literal["start", "end", "after"] = "end",
    after_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Move a requirement to a different spec file.

    Args:
        req_id: Requirement to move
        target_file: Destination file (relative to spec dir)
        position: Where to place in target file
        after_id: If position="after", place after this requirement
    """

@mcp.tool()
def prepare_file_deletion(source_file: str) -> Dict[str, Any]:
    """
    Analyze a spec file for deletion readiness.

    Returns:
        - remaining_reqs: REQ/JNY ids still in file (must be moved first)
        - extractable_content: Non-requirement text that could be preserved
        - ready_to_delete: True if no requirements remain
    """

@mcp.tool()
def extract_and_delete(
    source_file: str,
    content_target: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract non-requirement content and delete empty spec file.

    Args:
        source_file: File to delete
        content_target: If provided, append extracted content here

    Precondition: No REQ/JNY entries remain in source_file
    """
```

### Graph State

```python
@mcp.tool()
def get_graph_status() -> Dict[str, Any]:
    """
    Get current graph state and staleness info.

    Returns:
        - is_stale: Whether graph needs refresh
        - stale_files: Files that changed since last build
        - node_counts: Count by node kind
        - last_built: Timestamp of last build
    """

@mcp.tool()
def refresh_graph(full: bool = False) -> Dict[str, Any]:
    """
    Refresh the traceability graph.

    Args:
        full: Force full rebuild even if only partial changes detected

    Returns:
        - refreshed_files: Files that were re-parsed
        - validation: Any new warnings/errors
    """
```

---

## MCP Tools (Read Operations for Auditor Review)

### Hierarchy Navigation

```python
@mcp.tool()
def get_traceability_path(req_id: str) -> Dict[str, Any]:
    """
    Get full traceability from requirement down to test results.

    Returns tree structure:
        REQ-p00001
        ├── Assertion A
        │   ├── REQ-d00005 (implements)
        │   │   └── src/auth.py:45 (code)
        │   │       └── test_auth.py::test_password (PASS)
        │   └── REQ-d00006 (implements)
        └── Assertion B
            └── (no coverage)
    """

@mcp.tool()
def get_coverage_breakdown(req_id: str) -> Dict[str, Any]:
    """
    Detailed coverage analysis for auditor review.

    Returns:
        - assertion_coverage: Per-assertion status (covered/not covered)
        - coverage_sources: direct/explicit/inferred for each
        - implementing_code: File paths with line numbers
        - validating_tests: Test names with pass/fail status
        - gaps: Assertions without coverage
    """

@mcp.tool()
def show_requirement_context(
    req_id: str,
    include_assertions: bool = True,
    include_implementers: bool = False
) -> Dict[str, Any]:
    """
    Display requirement with surrounding context.

    Returns:
        - requirement: Full requirement text
        - assertions: Labeled assertion texts
        - source: File path and line range
        - metrics: Coverage summary
    """

@mcp.tool()
def list_by_criteria(
    level: Optional[str] = None,
    status: Optional[str] = None,
    coverage_below: Optional[float] = None,
    has_gaps: Optional[bool] = None
) -> Dict[str, Any]:
    """
    List requirements matching criteria.

    Examples:
        list_by_criteria(level="PRD")  # All PRD requirements
        list_by_criteria(coverage_below=100)  # Not fully covered
        list_by_criteria(has_gaps=True)  # Has uncovered assertions
    """
```

---

## MCP Resources

| Resource URI | Description |
|-------------|-------------|
| `graph://status` | Graph staleness and statistics |
| `graph://validation` | Current validation warnings/errors |
| `traceability://{id}` | Full traceability path for requirement |
| `coverage://{id}` | Coverage breakdown for requirement |
| `hierarchy://{id}/ancestors` | Ancestor chain |
| `hierarchy://{id}/descendants` | All descendants |
| `spec://{file}` | Parsed content of spec file |

---

## Implementation Phases

### Phase 1: Read-Only Graph with Lazy Refresh
- Graph builds on first query
- File mtime tracking for staleness detection
- Full rebuild when stale
- Auditor review tools

### Phase 2: Incremental Refresh
- Track which nodes come from which files
- Re-parse only changed files
- Update affected subgraph only
- Preserve unchanged portions

### Phase 3: Write Operations
- Reference manipulation tools
- Filesystem sync from graph changes
- Format-preserving edits
- File move/delete operations

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/elspais/mcp/context.py` | Add `GraphState`, staleness tracking, lazy refresh |
| `src/elspais/mcp/server.py` | Add read/write tools, resources |
| `src/elspais/mcp/mutator.py` | New file: `GraphMutator` for write operations |
| `src/elspais/mcp/serializers.py` | Add traceability path serialization |

---

## Dependencies

- TraceGraph and GraphBuilder must be stable (complete)
- Test scanner integration via parser registry
- Requirement file editing utilities (format-preserving)

---

## References

- Graph implementation: `src/elspais/core/graph.py`
- Graph builder: `src/elspais/core/graph_builder.py`
- Graph schema: `src/elspais/core/graph_schema.py`
- MCP server: `src/elspais/mcp/server.py`
