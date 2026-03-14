# FILE Node Architecture Design

**Date:** 2026-03-13
**Status:** Draft
**Scope:** Graph data model, build pipeline, serialization, traversal

## Problem

Source file identity is currently implicit in the graph. Nodes store a `SourceLocation` with a file path string and line number, but files are not first-class participants in the graph. This makes file-level operations (rename, move requirements between files, render files from graph state) awkward — they require ad-hoc text surgery (`persistence.py`) rather than graph-native operations.

## Design Goals

1. Every scanned file becomes a `FILE` node in the graph.
2. Every line of every scanned file is represented by some node (domain kind or REMAINDER).
3. Mutations propagate through the graph; writing all FILE nodes reconstructs the filesystem.
4. Round-trip fidelity: reading the written files produces an identical graph (modulo normalization).
5. Language-agnostic: parsers work across Python, Dart, JS/TS, Go, etc. via configurable comment styles.

## Constraints

- **One file, one domain kind.** Each file is scanned by exactly one domain parser plus RemainderParser. No file gets multiple domain parsers.
- **User Journeys in separate files.** JNY blocks must not co-locate with REQ blocks. This enforces the one-domain-kind constraint.
- **No backwards compatibility concerns** for internal APIs. External behavior (CLI output, MCP responses, config format) should remain consistent where possible.

## 1. Node Model

### 1.1 New NodeKind: FILE

A `FILE` node represents a single source file on disk.

- **ID:** `file:<repo-relative-path>` (e.g., `file:spec/requirements.md`)
- **Kind:** `NodeKind.FILE`
- **Label:** the filename (e.g., `requirements.md`)

**Content fields:**

| Field | Type | Description |
|-------|------|-------------|
| `file_type` | str | One of: `SpecFile`, `JourneyFile`, `CodeFile`, `TestFile`, `ResultFile` |
| `absolute_path` | str | Full filesystem path at parse time |
| `relative_path` | str | Repo-relative path (used for IDs, display) |
| `repo` | str or None | Repository identifier (`None` for core project, string for associates) |
| `git_branch` | str or None | Branch name at parse time |
| `git_commit` | str or None | Commit hash at parse time |

### 1.2 New Edge Kinds

**`CONTAINS`** — from FILE node to a content node. Indicates the node's text is physically present in this file at the specified lines.

Edge metadata:

| Field | Type | Description |
|-------|------|-------------|
| `start_line` | int | 1-based line number (snapshot from parse time) |
| `end_line` | int or None | End line (snapshot from parse time) |
| `render_order` | float or int | Canonical ordering for rendering; mutable |

**`DEFINES`** — from FILE node to an INSTANCE node. Indicates this file (via its declaring requirement's `Satisfies:` clause) caused the INSTANCE node to exist. The INSTANCE node's content was cloned from a template, not physically present in this file.

### 1.3 Eliminate Edge-less Parent-Child Links

Currently `GraphNode` has two relationship mechanisms:
- `add_child()` — creates `_children`/`_parents` links with no Edge object
- `link()` — creates Edge objects AND `_children`/`_parents` links

The edge-less `add_child()` is eliminated. All relationships use `link()` with a typed `EdgeKind`. The `_children`/`_parents` lists become derived from edges.

This enables filtered traversal on all relationships universally.

### 1.4 SourceLocation Removal

The `SourceLocation` class and `GraphNode.source` field are removed. Replaced by:
- **File path:** navigate to FILE parent via CONTAINS edge
- **Line numbers:** stored as fields on the content node (`parse_line`, `parse_end_line`) — these are snapshots from parse time

A convenience method `GraphNode.file_node()` navigates up via CONTAINS edge to find the FILE parent. Returns `None` for INSTANCE nodes (which have DEFINES edges instead) and other virtual nodes.

### 1.5 File Type to Parser Mapping

| file_type | Domain Parser | Notes |
|-----------|--------------|-------|
| `SpecFile` | RequirementParser | REQ + ASSERTION + REMAINDER |
| `JourneyFile` | JourneyParser | USER_JOURNEY + REMAINDER |
| `CodeFile` | CodeParser | CODE + REMAINDER |
| `TestFile` | TestParser | TEST + REMAINDER |
| `ResultFile` | JUnitXMLParser / PytestJSONParser / (future: DartResultParser) | TEST_RESULT; REMAINDER may not apply to structured formats |

## 2. Build Pipeline

### 2.1 Current Flow

```text
factory.py:
  for spec_dirs:    DomainFile.deserialize(spec_registry)   --> builder.add_parsed_content()
  for code_dirs:    DomainFile.deserialize(code_registry)    --> builder.add_parsed_content()
  for test_dirs:    DomainFile.deserialize(test_registry)    --> builder.add_parsed_content()
  for result_files: DomainFile.deserialize(result_registry)  --> builder.add_parsed_content()
  builder.build() --> TraceGraph
```

### 2.2 New Flow

```text
factory.py:
  capture git_branch, git_commit once per repo
  for each configured directory:
    determine file_type from config context
    select domain parser for this file_type
    for each file in directory:
      create FILE node (with file_type, paths, repo, git context)
      parse with [domain_parser, RemainderParser]
      for each parsed content:
        create content node
        create CONTAINS edge from FILE to content node (with line range, render_order)
        queue domain edges (IMPLEMENTS, REFINES, etc.) in pending_links
  builder.build() --> TraceGraph
    (satisfies instantiation creates DEFINES edges from declaring FILE to INSTANCE nodes)
```

**Key changes:**
- `factory.py` creates the FILE node before calling `DomainFile.deserialize()`, since it knows the file path and type.
- `DomainFile` / deserializer is unchanged — it still reads files, splits into lines, runs parsers.
- `GraphBuilder.add_parsed_content()` receives a FILE node reference along with parsed content.
- `RemainderParser` is mandatory — always registered, always runs as catch-all.
- `render_order` is assigned sequentially from natural file order at parse time (0, 1, 2, ...).

### 2.3 Satisfies / Template Instantiation

During `_instantiate_satisfies_templates()`:
- INSTANCE nodes are created as before (cloned from template subtree with composite IDs).
- INSTANCE nodes get no CONTAINS edge (they are not physically in any file).
- DEFINES edges are created from the declaring requirement's FILE node to each INSTANCE node.
- To find the file for an INSTANCE node, navigate: INSTANCE --INSTANCE edge--> original node --CONTAINS edge (incoming)--> FILE node. Or navigate via DEFINES edge directly.

### 2.4 Post-Build Steps

Unchanged:
- `link_tests_to_code()` — uses FILE parent navigation instead of `SourceLocation`
- `annotate_keywords()` — unchanged
- `annotate_coverage()` — unchanged
- `annotate_git_state()` — navigates to FILE parent node, reads its path

## 3. Traversal & Views

### 3.1 Parameterized Roots

`iter_roots()` becomes parameterized by NodeKind:

- `iter_roots(NodeKind.REQUIREMENT)` — parentless REQ nodes (current default behavior)
- `iter_roots(NodeKind.FILE)` — all FILE nodes (always parentless)
- `iter_roots(NodeKind.USER_JOURNEY)` — parentless journey nodes
- `iter_roots()` with no argument — default to current behavior (REQ + JOURNEY)

### 3.2 Filtered Traversal

Traversal methods accept optional edge-kind filters:

- `iter_children(edge_kinds={IMPLEMENTS, REFINES})` — domain children only
- `iter_children(edge_kinds={CONTAINS})` — file contents only
- `iter_children()` — all children (unfiltered, current behavior)
- Same for `iter_parents()`, `walk()`, `ancestors()`

This allows consumers to stay in one "view" of the graph without crossing between file structure and domain structure.

### 3.3 Convenience Methods

- `GraphNode.file_node()` — navigate up via CONTAINS edge to FILE parent. Returns `None` for virtual nodes.
- `TraceGraph.iter_by_kind(kind)` — filter `_index` by NodeKind.

## 4. Line Numbers & Ordering

### 4.1 Two Distinct Concepts

- **`parse_line` / `parse_end_line`** (on node and CONTAINS edge) — line numbers as read from disk. Informational snapshot. Becomes stale after any in-memory mutation.
- **`render_order`** (on CONTAINS edge) — canonical ordinal for rendering. Mutable. Determines the sequence when writing the file.

At parse time, `render_order` is assigned from natural file order. After mutations, `render_order` is the authoritative ordering; `parse_line` values may be stale.

### 4.2 Assertion Ordering Constraint

For ASSERTION children of an active REQUIREMENT:
- `render_order` is locked to assertion sequence (A=0, B=1, C=2, ...).
- Reordering assertions requires recomputing labels and updating all references.
- Assertion reorder is a deferred feature (future plan).

### 4.3 Order-Independent Assertion Hashing

The requirement hash must not change when assertions are reordered:

1. Compute normalized text hash for each assertion individually.
2. Sort the individual assertion hashes lexicographically.
3. Hash the sorted collection into the requirement's final hash.

This ensures assertion reordering does not trigger change-detection review, while assertion text edits still do.

## 5. Rendering & Serialization

### 5.1 Render Protocol

Each NodeKind implements a render method returning its text representation:

| NodeKind | Renders As |
|----------|-----------|
| `REQUIREMENT` | Full `## REQ-xxx: Title` block (metadata, body, assertions, sections, `*End*` marker) |
| `ASSERTION` | Rendered as part of parent REQUIREMENT (not independently to file) |
| `REMAINDER` | Raw text verbatim |
| `USER_JOURNEY` | Full `## JNY-xxx: Title` block |
| `CODE` | The `# Implements:` comment line(s); surrounding code is REMAINDER |
| `TEST` | The `# Tests:` / `# Validates:` comment line(s); surrounding code is REMAINDER |
| `TEST_RESULT` | Read-only (generated by test runners); not rendered back to disk |
| `FILE` | Not rendered directly; its content is the concatenation of its CONTAINS children's renders |

### 5.2 Save Operation

1. Identify dirty FILE nodes (those whose subtree has pending mutations).
2. For each dirty FILE node:
   a. Walk CONTAINS children sorted by `render_order`.
   b. Call render on each content node.
   c. Concatenate into file content.
   d. Write to disk.
3. Create safety branch before writing (existing mechanism).
4. Rebuild graph from disk (re-read all files).
5. Compare new graph to pre-save in-memory graph as consistency check.

### 5.3 What Gets Deleted

- `persistence.py` — replaced entirely by render-based save
- `SourceLocation` class
- `GraphNode.source` field
- Edge-less `add_child()` mechanism

## 6. Consumer Migration

~15 consumers currently read `SourceLocation`. All migrate to the same pattern:

**File-path consumers** (navigate to FILE parent):
- `annotate_git_state()`, `annotate_display_info()` — navigate to FILE parent, read path
- `git.py` (`_extract_req_locations_from_graph`) — navigate to FILE parent
- `index.py`, `pdf/assembler.py` — group by FILE parent
- `link_suggest.py`, `test_code_linker.py` — FILE parent path for proximity matching

**File+line consumers** (FILE parent path + node's `parse_line` field):
- `mcp/server.py`, `html/generator.py`, `server/app.py` — display file:line
- `commands/trace.py`, `commands/validate.py` — output file:line
- `graph/serialize.py` — serialize FILE parent path + line fields

**Common pattern:** `node.file_node()` provides the FILE parent. Consumers switch from `node.source.path` to `node.file_node().relative_path` (or similar).

## 7. Language-Agnostic Parser Support

### 7.1 Current State

- CodeParser: supports Python, JS/TS, Go, Rust, C/Java comment styles and function detection
- TestParser: heavily Python-biased (`def test_foo`, `class TestBar`)
- ResultParsers: JUnit XML, pytest JSON

### 7.2 Design Direction

The `# Implements:` / `# Tests:` comment markers are the language-agnostic layer. Comment style and keywords are already configurable via `[references]` config. Function/class context detection (for canonical node IDs and TEST-CODE linking) is the language-specific part.

Function context detection becomes a pluggable strategy within the parser, not a different parser. The file's role (CodeFile, TestFile) determines which domain parser runs; the parser uses `[references]` config for comment styles and keywords, and a language-specific function detector for context.

New language support (e.g., Dart) requires:
- Function/class detection strategy for that language's syntax
- Result parser for that language's test output format (if different from JUnit XML)
- No changes to the FILE node architecture itself

## 8. Deferred Features

The following are enabled by this architecture but deferred to future plans:

- **Assertion reordering** with automatic label recomputation and reference updating
- **Drag-and-drop reordering** in the UI (render_order mutation)
- **File rename** as a graph mutation (update FILE node path, persist)
- **Move requirement between files** as a graph mutation (change CONTAINS edge from one FILE to another)
- **Dart/Flutter parser support** (function detection strategy, result parser)
