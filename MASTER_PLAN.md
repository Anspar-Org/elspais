# MASTER PLAN Phase 2 — Indirect Traceability Through Code

**Branch**: `feature/CUR-514-viewtrace-port`
**Ticket**: CUR-240

## Goal

Add TEST → CODE → REQUIREMENT chain so tests automatically provide coverage for requirements without explicitly referencing them. A test that exercises a function provides coverage for requirements that function implements.

**Chain**: `REQUIREMENT ← (IMPLEMENTS) ← CODE ← (VALIDATES) ← TEST ← (CONTAINS) ← TEST_RESULT`

## Principle: Coverage rolls up through the chain

A test doesn't need to know about requirements — it just tests a function. That function declares `# Implements: REQ-xxx`. Coverage rolls up through the chain. Existing direct TEST→REQ edges continue to work and take priority.

## Implementation Steps

### Step 1: CodeParser function context tracking + tests

**File**: `src/elspais/graph/parsers/code.py`

Reuse the pre-scan pattern from TestParser (`test.py:231-286`):

- [ ] Add pre-scan pass before main `claim_and_parse()` loop
- [ ] Build `line_context: dict[int, tuple[str|None, str|None, int]]` mapping line → `(function_name, class_name, function_line)`
- [ ] Detect functions with language-aware regexes (no AST libraries):
  - Python: `def name(` — reuse from TestParser
  - JS/TS: `function name(`, `async function name(`
  - Go: `func name(`
  - Rust: `pub? fn name(`
  - Generic fallback for C/Java
- [ ] Detect classes: `class Name`, `struct Name`, `impl Name`
- [ ] Scope tracking: indentation for Python, brace counting (`{`/`}`) for C-family
- [ ] **Forward-looking**: fix up comment lines with no function context by looking ahead up to 5 lines for next function definition. Handles `# Implements: REQ-xxx` placed immediately BEFORE a function.
- [ ] Add `function_name`, `class_name`, `function_line` to `parsed_data`

### Step 2: Builder stores function context on CODE nodes + tests

**File**: `src/elspais/graph/builder.py` (`_add_code_ref()`, ~line 1711)

- [ ] Extract `function_name`, `class_name`, `function_line` from `parsed_data`
- [ ] Store on CODE node via `node.set_field("function_name", ...)` and `node.set_field("class_name", ...)`
- [ ] Update label to include function name when available
- [ ] Keep existing line-based ID format `code:{path}:{line}` unchanged

### Step 3: Import analysis utility + tests

**NEW file**: `src/elspais/utilities/import_analyzer.py`

- [ ] `extract_python_imports(content: str) -> list[str]` — parse `from X import Y` and `import X`, return module paths
- [ ] `module_to_source_path(module: str, repo_root: Path, source_roots: list[str]) -> Path | None` — map `elspais.graph.annotators` → `src/elspais/graph/annotators.py`

### Step 4: Test-to-code linker + tests

**NEW file**: `src/elspais/graph/test_code_linker.py`

- [ ] `link_tests_to_code(graph: TraceGraph, repo_root: Path) -> None`
- [ ] Build CODE index: `dict[(source_path, function_name), list[GraphNode]]`
- [ ] Cache test file imports per file (read once per unique test file)
- [ ] For each TEST node:
  - Get test file imports, map to source paths
  - Match test function → source function via heuristics:
    - Strip `test_` prefix from function name → candidate
    - Strip `Test` prefix from class name, snake_case → candidate
    - Prefix matching: `test_build_graph_with_config` → `build_graph()`
  - Create edge: `code_node.link(test_node, EdgeKind.VALIDATES)`

### Step 5: Coverage rollup enhancement + tests

**File**: `src/elspais/graph/annotators.py` (`annotate_coverage()`, ~line 516)

- [ ] After processing CODE children of a REQUIREMENT:
  - Check each CODE child's outgoing VALIDATES edges for TEST grandchildren
  - For each TEST grandchild, look for TEST_RESULT children
  - Credit REQUIREMENT with INDIRECT coverage for code-covered assertions
  - Mark as `validated_with_indirect` if TEST_RESULT passed

### Step 6: Factory integration + end-to-end tests

**File**: `src/elspais/graph/factory.py` (`build_graph()`, ~line 270)

- [ ] Call `link_tests_to_code(graph, repo_root)` after `builder.build()` returns
- [ ] Ensures TEST→CODE edges exist before any coverage annotation runs

## Function Name Matching Heuristics

| Test Pattern | Matches Source Function | How |
|-------------|----------------------|-----|
| `TestAnnotateCoverage::test_basic` | `annotate_coverage()` | Strip `Test`, snake_case class name |
| `test_annotate_coverage_basic` | `annotate_coverage()` | Strip `test_`, prefix match |
| `TestGraphNode::test_init` | `GraphNode.__init__` | Strip `Test`, match class directly |
| `test_build_graph_with_config` | `build_graph()` | Strip `test_`, prefix match |

## Files to Modify

| File | Change |
|------|--------|
| `src/elspais/graph/parsers/code.py` | Add function/class context tracking pre-scan |
| `src/elspais/graph/builder.py` | Store function_name/class_name on CODE nodes |
| **NEW** `src/elspais/utilities/import_analyzer.py` | Python import extraction + module→path mapping |
| **NEW** `src/elspais/graph/test_code_linker.py` | Main linking logic: imports + function matching |
| `src/elspais/graph/annotators.py` | Follow CODE→TEST chain in coverage rollup |
| `src/elspais/graph/factory.py` | Call `link_tests_to_code()` after build |

## What Stays the Same

- TraceGraph, GraphNode, GraphBuilder structure
- NodeKind, EdgeKind enums (reuse VALIDATES for TEST→CODE)
- TestParser (unchanged — already captures function context)
- Existing TEST→REQ direct edges (still work, higher priority)
- ParsedContent, LineClaimingParser protocol
- RollupMetrics, CoverageContribution (reuse INDIRECT source)

## Commit Strategy

3 commits (one per logical unit):
1. **CodeParser function context + builder changes** (Steps 1-2 + tests)
2. **Import analyzer + test-to-code linker** (Steps 3-4 + tests)
3. **Coverage rollup + factory integration** (Steps 5-6 + end-to-end tests)

## Verification

1. `python -m pytest tests/ -x -q` — all pass
2. CODE nodes have function metadata: `code_node.get_field("function_name") == "annotate_coverage"`
3. TEST→CODE edges exist after graph build
4. Coverage rollup: requirement implemented by tested code shows INDIRECT coverage
5. `python -m elspais trace --view --output /tmp/trace.html` — visual check
6. MCP `get_graph_status()` — no unexpected broken references from new edges

## Archive

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase

---

# MASTER PLAN Phase 3 — Explicit Requirement Linking for Tests and Code

**Branch**: TBD
**Ticket**: TBD

## Goal

Make requirement linking a first-class workflow for developers and AI agents. Provide tooling to discover unlinked tests and code, surface coverage gaps in reports, and offer agent-assisted linking suggestions. Phase 2 introduced *indirect* coverage through code chains; Phase 3 ensures teams can *see* what is unlinked and *act on it* efficiently.

## Principle: Every test and code file should be traceable

Indirect coverage (Phase 2) is valuable but insufficient on its own. Teams need visibility into which files have no requirement references at all, and AI agents need programmatic access to coverage gaps so they can suggest or apply links during development.

## Implementation Steps

### Step 1: MCP tools for coverage gap discovery

**Files**: `src/elspais/mcp/tools/` (new tools or extend existing)

Expose requirement-linking status through MCP so AI agents can query gaps programmatically:

- [ ] `get_unlinked_tests()` — return TEST nodes that have no direct requirement references (no `Implements:`, `Refines:`, or `REQ-xxx` in name)
- [ ] `get_unlinked_code()` — return CODE-eligible source files that contain no `# Implements:` or `# Refines:` comments
- [ ] `get_requirements_without_tests()` — return requirements that have zero TEST coverage (neither direct nor indirect)
- [ ] `suggest_links(test_id)` — given a TEST node, analyze its imports, function names, and file path to suggest candidate requirements it likely validates
- [ ] All tools return structured data (requirement IDs, file paths, confidence scores) suitable for agent consumption

### Step 2: Unlinked file reports in trace output

**Files**: `src/elspais/graph/annotators.py`, `src/elspais/commands/trace.py`, HTML templates

Extend trace reports (CLI and HTML) with a section showing files that have no requirement references:

- [ ] During graph annotation, build sets of: all scanned source files, all scanned test files, files with at least one requirement reference
- [ ] Compute unlinked sets: `scanned - linked` for both code and test files
- [ ] CLI `elspais trace` output: add summary line — `Unlinked: 12 test files, 5 source files have no requirement references`
- [ ] HTML trace view: add collapsible "Unlinked Files" section listing each file with its path and a brief reason (no `Implements:` comment found, no `REQ-xxx` in test names, etc.)
- [ ] Support `--include-unlinked` / `--exclude-unlinked` flag to control whether unlinked files appear in output

### Step 3: Coverage gaps view — direct vs. indirect

**Files**: `src/elspais/graph/annotators.py`, HTML templates, `src/elspais/commands/trace.py`

Show which requirements rely solely on indirect coverage so teams can decide if explicit links are needed:

- [ ] Annotate each requirement with coverage source breakdown: `direct_only`, `indirect_only`, `both`
- [ ] HTML trace view: add visual indicator (icon or badge) for requirements covered only indirectly
- [ ] CLI output: list requirements with only indirect coverage in a dedicated section
- [ ] Filter support: `elspais trace --coverage-type direct|indirect|both` to focus on specific coverage sources

### Step 4: Linking convention documentation

**Files**: `docs/cli/linking.md` (new documentation topic for `elspais docs linking`)

Define a clear, authoritative convention for requirement linking that developers and AI agents follow:

- [ ] **Code files**: Use `# Implements: REQ-xxx` (or language-appropriate comment) above or inside the function that implements the requirement
- [ ] **Test files — direct**: Use `# Tests REQ-xxx` comment or include `REQ_xxx` in test function names (`test_REQ_p00001_A_validates_input`)
- [ ] **Test files — indirect**: Import and exercise a function that has `# Implements: REQ-xxx`; coverage rolls up automatically (Phase 2)
- [ ] **Multi-assertion syntax**: `# Implements: REQ-p00001-A-B-C` expands to individual assertion references
- [ ] **When to use each approach**: Decision tree — direct linking for acceptance/integration tests, indirect linking acceptable for unit tests of implementation functions
- [ ] **AI agent instructions**: Snippet suitable for inclusion in agent prompts (CLAUDE.md, etc.) describing the linking convention

### Step 5: Agent-assisted linking command

**Files**: `src/elspais/commands/link_suggest.py` (new), `src/elspais/cli.py`

Add an `elspais link suggest` command that analyzes unlinked tests and suggests requirement associations:

- [ ] `elspais link suggest` — scan all unlinked test files and print suggested links with confidence scores
- [ ] `elspais link suggest --file <path>` — analyze a single file
- [ ] `elspais link suggest --apply` — interactively apply suggestions (add `# Implements:` comments to files)
- [ ] Suggestion heuristics:
  - Import analysis: test imports module → module has `# Implements: REQ-xxx` → suggest REQ-xxx
  - Function name matching: `test_build_graph` → `build_graph()` implements REQ-xxx → suggest REQ-xxx
  - File path proximity: `tests/test_validator.py` → `src/elspais/validation/` has requirement refs → suggest those
  - Keyword overlap: requirement title words appearing in test docstrings or function names
- [ ] Output format: `SUGGEST: tests/test_foo.py::test_bar → REQ-p00001-A (confidence: high, reason: imports foo which implements REQ-p00001-A)`
- [ ] JSON output mode for programmatic consumption: `--format json`

### Step 6: MCP integration for link suggestions

**Files**: `src/elspais/mcp/tools/` (extend from Step 1)

Wire the link suggestion engine into MCP so AI agents can request and apply suggestions during coding sessions:

- [ ] `suggest_links_for_file(file_path)` — return structured suggestions for a specific file
- [ ] `apply_link(file_path, line, requirement_id)` — insert a `# Implements: REQ-xxx` comment at the specified location
- [ ] `get_linking_convention()` — return the convention documentation as structured text for agent prompt injection
- [ ] Integrate with existing `get_uncovered_assertions()` MCP tool to provide a complete workflow: discover gaps → get suggestions → apply links

## Files to Modify

| File | Change |
|------|--------|
| `src/elspais/mcp/tools/` | New MCP tools for gap discovery + link suggestions |
| `src/elspais/graph/annotators.py` | Track unlinked files, annotate direct vs. indirect coverage source |
| `src/elspais/commands/trace.py` | Add unlinked files summary to CLI output |
| HTML templates | Add "Unlinked Files" section and indirect-only coverage indicators |
| **NEW** `docs/cli/linking.md` | Linking convention documentation |
| **NEW** `src/elspais/commands/link_suggest.py` | Agent-assisted link suggestion command |
| `src/elspais/cli.py` | Register `link suggest` subcommand |

## What Stays the Same

- TraceGraph, GraphNode, GraphBuilder structure
- NodeKind, EdgeKind enums
- Existing parsers (CodeParser, TestParser) — these already produce the nodes we analyze
- Phase 2 indirect coverage chain (TEST -> CODE -> REQUIREMENT) — this phase builds on top of it
- RollupMetrics, CoverageContribution — reuse existing tracking fields
- ParsedContent, LineClaimingParser protocol

## Commit Strategy

4 commits (one per logical unit):
1. **MCP gap discovery tools** (Step 1 + tests)
2. **Unlinked file reports + coverage gaps view** (Steps 2-3 + tests)
3. **Linking convention docs + link suggest command** (Steps 4-5 + tests)
4. **MCP link suggestion integration** (Step 6 + end-to-end tests)

## Verification

1. `python -m pytest tests/ -x -q` — all pass
2. MCP tools return correct unlinked test/code lists for fixture repos
3. `elspais trace` CLI output includes unlinked file summary
4. HTML trace view shows "Unlinked Files" section and indirect-only badges
5. `elspais link suggest` produces reasonable suggestions for fixture test files
6. `elspais docs linking` displays the convention documentation
7. End-to-end: run `link suggest --apply` on a test file, rebuild graph, verify new coverage appears

## Archive

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
