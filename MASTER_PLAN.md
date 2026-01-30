# MASTER PLAN: Codebase Review for Design Principle Violations

## Overview

Systematic review of the elspais codebase to identify:
1. **Design principle violations** (per AGENT_DESIGN_PRINCIPLES.md)
2. **Anti-patterns** (code smells, poor practices)
3. **Code duplication** (repeated logic that should be centralized)

## Review Methodology

For each subsystem:
1. Use `feature-dev:code-reviewer` agent to analyze
2. Check against specific design principles
3. Document findings with file:line references
4. Categorize severity: CRITICAL / HIGH / MEDIUM / LOW

---

## Phase 1: MCP Server Review (2108 lines)

**File**: `src/elspais/mcp/server.py`

### Design Principles to Check

- [ ] MCP tools MUST delegate to graph methods, not implement mutation logic directly
- [ ] ALWAYS use existing graph API functions instead of reimplementing logic
- [ ] ALWAYS use aggregate functions from `graph/annotators.py` for statistics
- [ ] DO NOT manually iterate to compute statistics

### Review Tasks

- [ ] Check each MCP tool for direct mutation logic (should delegate to graph)
- [ ] Check for statistics computed by iteration instead of aggregate functions
- [ ] Check for duplicated logic between tools
- [ ] Check for proper error handling patterns

### Findings

```
[Document findings here after review]
```

---

## Phase 2: Graph Builder Review (1752 lines)

**File**: `src/elspais/graph/builder.py`

### Design Principles to Check

- [ ] DO NOT change the structure of Graph, GraphTrace, or GraphBuilder
- [ ] DO NOT violate existing encapsulation
- [ ] ALWAYS use iterator-only API methods for traversal

### Review Tasks

- [ ] Check for encapsulation violations (direct access to private members)
- [ ] Check for duplicated parsing/building logic
- [ ] Check for consistent error handling
- [ ] Check for proper use of iterator API

### Findings

```
[Document findings here after review]
```

---

## Phase 3: CLI Review (996 lines)

**File**: `src/elspais/cli.py`

### Design Principles to Check

- [ ] There is ONE config system; DO NOT parse configuration separately
- [ ] New interface layers MUST consume existing APIs directly
- [ ] ALWAYS use existing graph API functions

### Review Tasks

- [ ] Check for configuration parsing outside the config system
- [ ] Check for duplicated argument handling patterns
- [ ] Check for direct graph manipulation vs. using commands module
- [ ] Check consistency across command implementations

### Findings

```
[Document findings here after review]
```

---

## Phase 4: Annotators Review (865 lines)

**File**: `src/elspais/graph/annotators.py`

### Design Principles to Check

- [ ] Centralize statistical logic in aggregate functions for reuse
- [ ] ALWAYS use graph methods instead of materializing iterators
- [ ] DO NOT manually iterate when count method exists

### Review Tasks

- [ ] Check for statistics that should be aggregate functions but aren't
- [ ] Check for iterator materialization that could use count methods
- [ ] Check for duplicated aggregation patterns
- [ ] Verify all aggregate functions are documented for reuse

### Findings

```
[Document findings here after review]
```

---

## Phase 5: Config System Review (807 lines)

**File**: `src/elspais/config/__init__.py`

### Design Principles to Check

- [ ] There is ONE config system; DO NOT parse configuration separately
- [ ] DO NOT violate existing encapsulation

### Review Tasks

- [ ] Check for configuration being parsed elsewhere in codebase
- [ ] Check for proper encapsulation of config internals
- [ ] Check for duplicated config access patterns
- [ ] Verify config validation is centralized

### Findings

```
[Document findings here after review]
```

---

## Phase 6: Commands Module Review

**Files**: `src/elspais/commands/*.py`

### Design Principles to Check

- [ ] ALWAYS use existing graph API functions
- [ ] ALWAYS use aggregate functions for statistics
- [ ] Reuse existing modules in `src/elspais/`

### Review Tasks

- [ ] Check each command for duplicated logic
- [ ] Check for statistics computed manually vs. using aggregates
- [ ] Check for consistent patterns across commands
- [ ] Identify shared logic that should be extracted

### Findings

```
[Document findings here after review]
```

---

## Phase 7: Parsers Review

**Files**: `src/elspais/graph/parsers/*.py`

### Design Principles to Check

- [ ] DO NOT violate existing encapsulation
- [ ] Search the codebase for existing functionality before implementing

### Review Tasks

- [ ] Check for duplicated parsing patterns across parsers
- [ ] Check for consistent regex handling
- [ ] Check for proper use of ParsedContent structure
- [ ] Identify common patterns that could be extracted

### Findings

```
[Document findings here after review]
```

---

## Phase 8: Cross-Cutting Concerns Review

### Check for Global Anti-Patterns

- [ ] **God Objects**: Classes doing too much (> 500 lines, > 10 public methods)
- [ ] **Feature Envy**: Methods that use more from other classes than their own
- [ ] **Shotgun Surgery**: Changes requiring edits in many files
- [ ] **Duplicate Code**: Similar logic in multiple places

### Check for Specific Issues

- [ ] Functions computing statistics that should use annotators.py
- [ ] Direct iteration over nodes when find_by_id() would work
- [ ] Iterator materialization (list()) when not necessary
- [ ] Configuration parsing outside config module
- [ ] Mutation logic in interface layers

### Findings

```
[Document findings here after review]
```

---

## Phase 9: Documentation & Test Compliance

### Check Test Naming

- [ ] Test names MUST reference a specific assertion
- [ ] Pattern: `test_REQ_xxx_A_description`
- [ ] Identify tests without assertion references

### Check Documentation Sync

- [ ] Run `pytest tests/test_doc_sync.py`
- [ ] Check CLI --help matches docs
- [ ] Check CLAUDE.md reflects current architecture

### Findings

```
[Document findings here after review]
```

---

## Review Execution

### For Each Phase

1. Spawn `feature-dev:code-reviewer` agent with specific file(s)
2. Provide design principles checklist
3. Collect findings in the Findings section
4. Categorize by severity

### Severity Levels

| Level | Definition | Action |
|-------|------------|--------|
| CRITICAL | Violates core architecture principle | Must fix immediately |
| HIGH | Clear anti-pattern with impact | Fix in next sprint |
| MEDIUM | Code smell, maintainability issue | Add to backlog |
| LOW | Style or minor improvement | Optional |

---

## Output Format

For each finding:

```markdown
### [SEVERITY] Finding Title

**Location**: `file.py:line`
**Principle Violated**: [Which design principle]
**Description**: [What's wrong]
**Suggested Fix**: [How to fix]
```

---

## Summary Template

After all phases complete, summarize:

| Subsystem | Critical | High | Medium | Low |
|-----------|----------|------|--------|-----|
| MCP Server | | | | |
| Graph Builder | | | | |
| CLI | | | | |
| Annotators | | | | |
| Config | | | | |
| Commands | | | | |
| Parsers | | | | |
| Cross-cutting | | | | |
| Tests/Docs | | | | |
| **TOTAL** | | | | |

---

## Commit Message

```
[CUR-XXX] refactor: Address codebase review findings

Fixes identified during systematic design principle review:
- [List major fixes]

See MASTER_PLAN1.md for full findings and methodology.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```
