# MASTER PLAN 8 — Agent-Assisted Linking Engine

**Branch**: feature/CUR-514-viewtrace-port
**Ticket**: CUR-240
**CURRENT_ASSERTIONS**: REQ-o00065 (A-F), REQ-d00072 (A-F), REQ-d00073 (A-E), REQ-d00074 (A-D)

## Goal

Build a suggestion engine that analyzes unlinked tests and code files, then proposes requirement associations using heuristics (import analysis, function name matching, file path proximity, keyword overlap). Expose this through both a CLI command and MCP tools for AI agent consumption.

## Principle: Discovery + Action

Teams need to not just *see* what's unlinked (existing tools already do this via `get_orphaned_nodes()`, `get_uncovered_assertions()`), but *act on it* efficiently with intelligent suggestions.

## Prerequisites

- MASTER_PLAN (linking convention documentation) should be completed first so conventions are documented before the tool enforces them.

## Implementation Steps

### Step 1: Agent-assisted linking command

**Files**: `src/elspais/commands/link_suggest.py` (new), `src/elspais/cli.py`

Add an `elspais link suggest` command that analyzes unlinked tests and suggests requirement associations:

- [ ] `elspais link suggest` — scan all unlinked test files and print suggested links with confidence scores
- [ ] `elspais link suggest --file <path>` — analyze a single file
- [ ] `elspais link suggest --apply` — interactively apply suggestions (add `# Implements:` comments to files)
- [ ] Suggestion heuristics:
  - Import analysis: test imports module -> module has `# Implements: REQ-xxx` -> suggest REQ-xxx
  - Function name matching: `test_build_graph` -> `build_graph()` implements REQ-xxx -> suggest REQ-xxx
  - File path proximity: `tests/test_validator.py` -> `src/elspais/validation/` has requirement refs -> suggest those
  - Keyword overlap: requirement title words appearing in test docstrings or function names
- [ ] Output format: `SUGGEST: tests/test_foo.py::test_bar -> REQ-p00001-A (confidence: high, reason: imports foo which implements REQ-p00001-A)`
- [ ] JSON output mode for programmatic consumption: `--format json`

### Step 2: MCP integration for link suggestions

**Files**: `src/elspais/mcp/tools/` (extend existing)

Wire the link suggestion engine into MCP so AI agents can request and apply suggestions during coding sessions:

- [ ] `suggest_links_for_file(file_path)` — return structured suggestions for a specific file
- [ ] `apply_link(file_path, line, requirement_id)` — insert a `# Implements: REQ-xxx` comment at the specified location
- [ ] `get_linking_convention()` — return the convention documentation as structured text for agent prompt injection
- [ ] Integrate with existing `get_uncovered_assertions()` MCP tool to provide a complete workflow: discover gaps -> get suggestions -> apply links

## Files to Modify

| File | Change |
|------|--------|
| **NEW** `src/elspais/commands/link_suggest.py` | Suggestion engine + CLI command |
| `src/elspais/cli.py` | Register `link suggest` subcommand |
| `src/elspais/mcp/server.py` | New MCP tools wrapping suggestion engine |

## What Stays the Same

- TraceGraph, GraphNode, GraphBuilder structure
- NodeKind, EdgeKind enums
- Existing parsers (CodeParser, TestParser)
- RollupMetrics, CoverageContribution
- All existing MCP tools

## Commit Strategy

2 commits:
1. **Linking suggestion engine + CLI command** (Step 1 + tests)
2. **MCP integration** (Step 2 + end-to-end tests)

## Verification

1. `python -m pytest tests/ -x -q` — all pass
2. `elspais link suggest` produces reasonable suggestions for fixture test files
3. `elspais link suggest --apply` on a test file, rebuild graph, verify new coverage appears
4. MCP `suggest_links_for_file()` returns structured suggestions
5. End-to-end: MCP discover gaps -> get suggestions -> apply links workflow

## Archive

- [ ] Mark phase complete in MASTER_PLAN8.md
- [ ] Archive completed plan: `mv MASTER_PLAN8.md ~/archive/YYYY-MM-DD/MASTER_PLAN8x.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
