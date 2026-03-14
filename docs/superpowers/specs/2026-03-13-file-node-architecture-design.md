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
| `file_type` | FileType enum | One of: `SPEC`, `JOURNEY`, `CODE`, `TEST`, `RESULT` |
| `absolute_path` | str | Full filesystem path at parse time |
| `relative_path` | str | Repo-relative path (used for IDs, display) |
| `repo` | str or None | Repository identifier (`None` for core project, string for associates) |
| `git_branch` | str or None | Branch name at parse time |
| `git_commit` | str or None | Commit hash at parse time |

`FileType` is an enum (like `NodeKind`, `EdgeKind`) rather than a string, for type safety and consistency.

### 1.2 Edge Kinds: New and Changed

#### Edge Direction Convention

Edges have a consistent directional pattern based on their semantic category:

- **Structural edges** point downward (parent → child): CONTAINS, STRUCTURES, DEFINES, YIELDS
- **Traceability edges** point upward (child → parent): IMPLEMENTS, REFINES, VALIDATES, SATISFIES

The edge kind name reads as subject-verb-object where the source node is the subject: "FILE contains REQUIREMENT", "CODE implements ASSERTION", "TEST yields TEST_RESULT."

#### New Edge Kinds

**`CONTAINS`** — from FILE node to a content node (downward). Indicates the node's text is physically present in this file at the specified lines.

Edge metadata (stored in `Edge.metadata` dict):

| Field | Type | Description |
|-------|------|-------------|
| `start_line` | int | 1-based line number (snapshot from parse time) |
| `end_line` | int or None | End line (snapshot from parse time) |
| `render_order` | float | Canonical ordering for rendering; mutable. Float to allow insertion between existing items (e.g., 1.5 between 1.0 and 2.0). |

**`DEFINES`** — from FILE node to an INSTANCE node (downward). Indicates this file (via its declaring requirement's `Satisfies:` clause) caused the INSTANCE node to exist. The INSTANCE node's content was cloned from a template, not physically present in this file.

**`STRUCTURES`** — domain-internal hierarchy edge (downward). Connects a node to its structural children:
- REQUIREMENT → ASSERTION (the requirement declares this assertion)
- REQUIREMENT → REMAINDER section (non-normative content within the requirement)

This is distinct from CONTAINS (physical file containment) and from traceability edges like IMPLEMENTS/REFINES. A REQUIREMENT's ASSERTION children are connected via STRUCTURES, not CONTAINS — because the assertion is structurally part of the requirement, not independently contained by the file.

STRUCTURES does not contribute to coverage. It represents structural containment, not traceability.

**`YIELDS`** — from TEST node to TEST_RESULT node (downward). A test yields its execution results. Replaces the current misuse of `CONTAINS` for the TEST_RESULT → TEST relationship (which was also in the wrong direction).

YIELDS does not contribute to coverage. Coverage flows through VALIDATES (TEST → REQUIREMENT).

#### Changed Edge Kinds

The existing `CONTAINS` edge between TEST_RESULT and TEST is replaced by `YIELDS` (TEST → TEST_RESULT), correcting both the edge kind name and the direction.

#### Edge Metadata

The `Edge` dataclass gains a `metadata: dict[str, Any]` field (default empty dict) to carry edge-specific data like line ranges and render_order. Metadata is NOT part of edge identity — `Edge.__eq__` and `__hash__` continue to compare only `source.id`, `target.id`, `kind`, and `assertion_targets`. Metadata is mutable annotation (e.g., `render_order` changes during mutations).

#### Complete Edge Kind Reference

| EdgeKind | Direction | From | To | Coverage | Description |
|----------|-----------|------|----|----------|-------------|
| CONTAINS | downward | FILE | content node | no | Physical file containment |
| STRUCTURES | downward | REQUIREMENT | ASSERTION, REMAINDER section | no | Domain-internal hierarchy |
| DEFINES | downward | FILE | INSTANCE | no | Virtual node provenance |
| YIELDS | downward | TEST | TEST_RESULT | no | Test execution results |
| IMPLEMENTS | upward | CODE, REQUIREMENT | REQUIREMENT, ASSERTION | yes | Traceability link |
| REFINES | upward | REQUIREMENT | REQUIREMENT, ASSERTION | yes | Refinement link |
| VALIDATES | upward | TEST | REQUIREMENT, ASSERTION | yes | Test coverage link |
| SATISFIES | upward | REQUIREMENT | REQUIREMENT (template) | no | Template compliance |
| INSTANCE | upward | INSTANCE | original node | no | Clone-to-original link |
| ADDRESSES | upward | REQUIREMENT | USER_JOURNEY | no | Journey coverage |

### 1.3 Eliminate Edge-less Parent-Child Links

Currently `GraphNode` has two relationship mechanisms:
- `add_child()` — creates `_children`/`_parents` links with no Edge object
- `link()` — creates Edge objects AND `_children`/`_parents` links

The edge-less `add_child()` is eliminated. All relationships use `link()` with a typed `EdgeKind`.

The `_children`/`_parents` lists are retained as caches for O(1) access, automatically maintained by `link()` (which already does this). The only change is removing the separate `add_child()` entry point. Undo operations that currently call `add_child()` migrate to `link()` with the appropriate edge kind.

`remove_child()` is renamed to `unlink()` for symmetry with `link()`. It retains its current behavior: severs all edges between two nodes and removes cache entries.

This enables filtered traversal on all relationships universally.

### 1.4 SourceLocation Removal

The `SourceLocation` class and `GraphNode.source` field are removed. Replaced by:
- **File path:** navigate to FILE parent via CONTAINS edge
- **Line numbers:** stored as fields on the content node (`parse_line`, `parse_end_line`) — these are snapshots from parse time

A convenience method `GraphNode.file_node()` walks up the graph via incoming edges to find the nearest ancestor with `kind == NodeKind.FILE`. The traversal path depends on the node's position:
- **Top-level content node** (REQUIREMENT, file-level REMAINDER): one hop via incoming CONTAINS edge to FILE.
- **ASSERTION or REMAINDER section**: two hops — incoming STRUCTURES edge to REQUIREMENT, then incoming CONTAINS edge to FILE.
- **INSTANCE node**: returns `None` (no CONTAINS edge). Use DEFINES edge or navigate via INSTANCE edge to original, then to FILE.

Returns `None` for virtual nodes and any node not reachable from a FILE.

### 1.5 File Type to Parser Mapping

| FileType | Domain Parser | Notes |
|----------|--------------|-------|
| `SPEC` | RequirementParser | REQ + ASSERTION + REMAINDER |
| `JOURNEY` | JourneyParser | USER_JOURNEY + REMAINDER |
| `CODE` | CodeParser | CODE + REMAINDER |
| `TEST` | TestParser | TEST + REMAINDER |
| `RESULT` | JUnitXMLParser / PytestJSONParser / (future: DartResultParser) | TEST_RESULT only; RemainderParser skipped for structured formats |

**Note on ResultFile:** Structured formats like JUnit XML and pytest JSON are fully consumed by their domain parser. RemainderParser is not applicable — there are no "unclaimed lines" in a structured format. These FILE nodes may have no REMAINDER children.

### 1.6 CONTAINS Edge Scope

CONTAINS edges go only from FILE to **top-level** content nodes — nodes that exist independently in the file, not as internal parts of another node. Specifically:

- REQUIREMENT, USER_JOURNEY, file-level REMAINDER, CODE, TEST — these get CONTAINS edges from FILE.
- ASSERTION, requirement-level REMAINDER sections — these do NOT get CONTAINS edges from FILE. They are reached through their parent REQUIREMENT via STRUCTURES edges.

This avoids redundant paths. An ASSERTION's file is always its REQUIREMENT's file — there is no need for a separate CONTAINS edge to express that.

**REMAINDER nodes** exist at two levels with different parent relationships:
- **File-level REMAINDER:** connected to FILE via CONTAINS. Represents unclaimed lines between domain blocks.
- **Requirement-level REMAINDER:** connected to REQUIREMENT via STRUCTURES. Represents non-normative sections (Rationale, Notes, etc.) within a requirement.

Both use `NodeKind.REMAINDER`. The builder distinguishes them by context: content parsed inside a requirement block gets STRUCTURES to the requirement; content parsed outside gets CONTAINS to the file.

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
      parse with [domain_parser, RemainderParser]  (RemainderParser skipped for RESULT)
      for each parsed content:
        create content node
        create CONTAINS edge from FILE to content node (with line range, render_order)
        for domain-internal children (e.g. ASSERTIONs within REQ):
          create STRUCTURES edge from parent to child
        queue domain edges (IMPLEMENTS, REFINES, etc.) in pending_links
  builder.build() --> TraceGraph
    (satisfies instantiation creates DEFINES edges from declaring FILE to INSTANCE nodes)
    (satisfies instantiation uses STRUCTURES edges for cloned internal hierarchy)
```

**Key changes:**
- `factory.py` creates the FILE node before calling `DomainFile.deserialize()`, since it knows the file path and type.
- `DomainFile` / deserializer is unchanged — it still reads files, splits into lines, runs parsers.
- `GraphBuilder.add_parsed_content()` receives a FILE node reference along with parsed content.
- `RemainderParser` is mandatory for text-based files — always registered, always runs as catch-all. Skipped for structured formats (RESULT).
- `render_order` is assigned sequentially from natural file order at parse time (0.0, 1.0, 2.0, ...).
- ASSERTION and REMAINDER-section children of REQUIREMENTs get STRUCTURES edges from the REQUIREMENT (domain-internal). They do NOT get direct CONTAINS edges from the FILE — they are reached through their parent REQUIREMENT.
- Cloned INSTANCE subtrees use STRUCTURES edges internally, mirroring the original structure.

### 2.3 Satisfies / Template Instantiation

During `_instantiate_satisfies_templates()`:
- INSTANCE nodes are created as before (cloned from template subtree with composite IDs).
- INSTANCE nodes get no CONTAINS edge (they are not physically in any file).
- Cloned subtrees use STRUCTURES edges internally (e.g., cloned REQUIREMENT → cloned ASSERTION), mirroring the original template's internal structure.
- DEFINES edges are created from the declaring requirement's FILE node to each INSTANCE node.
- To find the file for an INSTANCE node, navigate: INSTANCE --INSTANCE edge--> original node, then `file_node()`. Or navigate via DEFINES edge directly.

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
- `iter_roots()` with no argument — default to current behavior (REQ + JOURNEY), excluding FILE nodes

FILE nodes are always parentless (nothing contains a file). They are stored in `_index` like all other nodes and returned by `iter_roots(NodeKind.FILE)` or `iter_by_kind(NodeKind.FILE)`. The default `iter_roots()` excludes them to preserve existing consumer behavior.

### 3.2 Filtered Traversal

Traversal methods accept optional edge-kind filters:

- `iter_children(edge_kinds={IMPLEMENTS, REFINES})` — domain traceability children only
- `iter_children(edge_kinds={CONTAINS})` — file contents only
- `iter_children(edge_kinds={STRUCTURES})` — domain-internal children (assertions, sections)
- `iter_children()` — all children (unfiltered, current behavior)
- Same for `iter_parents()`, `walk()`, `ancestors()`

Filtered `walk()` applies the edge-kind filter at each recursion level: at every node, only children reachable via the specified edge kinds are visited. This produces view-specific subtrees:
- `walk(edge_kinds={CONTAINS})` from a FILE node yields the file's physical contents
- `walk(edge_kinds={IMPLEMENTS, REFINES, STRUCTURES})` from a REQUIREMENT yields the domain subtree
- `walk()` with no filter yields everything reachable (current behavior, not recommended with dual parentage)

This allows consumers to stay in one "view" of the graph without crossing between file structure and domain structure.

### 3.3 Convenience Methods

- `GraphNode.file_node()` — walk incoming edges upward to the nearest FILE ancestor. See Section 1.4 for traversal paths by node type.
- `TraceGraph.iter_by_kind(kind)` — filter `_index` by NodeKind.

### 3.4 Impact on MCP `get_subtree()`

`get_subtree()` uses filtered traversal to produce view-specific results:
- Starting from a FILE node: walks CONTAINS edges, produces the file's contents
- Starting from a REQUIREMENT node: walks domain edges (IMPLEMENTS, REFINES, STRUCTURES), produces the traceability subtree
- The `include_kinds` parameter already filters by NodeKind; edge-kind filtering is the new dimension

## 4. Line Numbers & Ordering

### 4.1 Two Distinct Concepts

- **`parse_line` / `parse_end_line`** (on node and CONTAINS edge metadata) — line numbers as read from disk. Informational snapshot. Becomes stale after any in-memory mutation.
- **`render_order`** (on CONTAINS edge metadata) — canonical ordinal for rendering. Mutable. Determines the sequence when writing the file. Always `float` to allow insertion between existing items (e.g., 1.5 between 1.0 and 2.0) without renumbering.

At parse time, `render_order` is assigned from natural file order (0.0, 1.0, 2.0, ...). After mutations, `render_order` is the authoritative ordering; `parse_line` values may be stale.

### 4.2 Ordering Hierarchy

Ordering operates at two levels:

1. **FILE level:** CONTAINS edges from FILE to top-level content nodes (REQUIREMENTs, file-level REMAINDERs) carry `render_order` that determines file-level sequencing.
2. **REQUIREMENT level:** STRUCTURES edges from REQUIREMENT to its children (ASSERTIONs, REMAINDER sections) carry their own ordering. For ASSERTIONs, this ordering is locked to the assertion sequence (A=0, B=1, C=2, ...).

These are independent — reordering requirements within a file does not affect assertion ordering within a requirement, and vice versa.

### 4.3 Assertion Ordering Constraint

For ASSERTION children of an active REQUIREMENT:
- Ordering is locked to assertion sequence (A=0, B=1, C=2, ...).
- Reordering assertions requires recomputing labels and updating all references.
- Assertion reorder is a deferred feature (future plan).

### 4.4 Order-Independent Assertion Hashing

The requirement hash must not change when assertions are reordered:

1. Compute normalized text hash for each assertion individually.
2. Sort the individual assertion hashes lexicographically.
3. Hash the sorted collection into the requirement's final hash.

This ensures assertion reordering does not trigger change-detection review, while assertion text edits still do.

**Migration impact:** This changes the hash computation algorithm. Existing hashes will change on first run. No mitigation needed — no project using elspais (other than elspais itself) currently has Active requirements.

## 5. Rendering & Serialization

### 5.1 Render Protocol

Each NodeKind implements a render method returning its text representation:

| NodeKind | Renders As |
|----------|-----------|
| `REQUIREMENT` | Full `## REQ-xxx: Title` block (metadata, body, assertions, sections, `*End*` marker). Renders its STRUCTURES children (assertions, sections) inline, ordered by their sequence. |
| `ASSERTION` | Rendered inline by parent REQUIREMENT (not independently to file) |
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

**Note on step 4-5:** The rebuild-and-compare step proves round-trip fidelity. It may be expensive for large projects. It can be made optional (e.g., enabled by default, skippable via config flag for performance) but should always run during development and testing.

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

**Common pattern:** `node.file_node()` provides the FILE parent. Consumers switch from `node.source.path` to `node.file_node().get_field("relative_path")` (or similar).

**Existing `move_requirement` MCP tool:** Currently implemented in persistence.py. Must be reimplemented to work with FILE nodes: remove the CONTAINS edge from the old FILE, add a CONTAINS edge to the new FILE with appropriate `render_order`. The domain edges (IMPLEMENTS, etc.) are unchanged.

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
