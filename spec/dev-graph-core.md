# Graph Core Development Requirements

## REQ-d00050: Node Annotator Functions

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

The `core/annotators.py` module SHALL provide standalone annotator functions for enriching graph nodes.

### Assertions

A. Graph nodes SHALL carry git state annotations (is_uncommitted, is_moved, is_new) in node.metrics.

B. Graph nodes SHALL carry display metadata (is_roadmap, display_filename, repo_prefix) in node.metrics.

C. Graph nodes SHALL carry implementation file references in node.metrics.

D. Annotator functions SHALL only operate on REQUIREMENT nodes (skip other node kinds).

E. Annotator functions SHALL be idempotent - calling twice produces same result.

### Rationale

Per-node annotators enable fine-grained control over which annotations are applied and when.

### Changelog

- 2026-05-11 | 8ca0389e | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 8ca0389e | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Node Annotator Functions* | **Hash**: 8ca0389e
---

## REQ-d00051: Graph Aggregate Functions

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051, REQ-p00050

The `core/annotators.py` module SHALL provide aggregate functions that compute statistics from annotated graphs.

### Assertions

A. The system SHALL provide aggregate requirement counts by level (PRD/OPS/DEV) with active/all breakdown.

B. The system SHALL provide aggregate requirement counts by repository prefix.

C. The system SHALL provide total implementation file count.

D. The system SHALL provide a sorted list of unique topics derived from file names.

E. The system SHALL provide per-requirement coverage status (Full/Partial/Unimplemented) from node.metrics.

F. Aggregate functions SHALL NOT duplicate iteration - they SHALL use graph.all_nodes().

### Rationale

Aggregate functions provide reusable statistics computation that any output format can use.

### Changelog

- 2026-05-11 | 97c0f6fc | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 97c0f6fc | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Graph Aggregate Functions* | **Hash**: 97c0f6fc
---

## REQ-d00052: Output Generators Consume Graph Directly

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

All output generators SHALL consume TraceGraph directly without creating intermediate data structures.

### Assertions

A. HTMLGenerator SHALL accept TraceGraph in constructor, not Dict[str, Requirement].

B. Markdown generator SHALL use graph.roots and node.children for hierarchy traversal.

C. CSV generator SHALL iterate graph.all_nodes() for flat output.

D. Generators SHALL NOT create Dict[str, TraceViewRequirement] or similar intermediate structures.

E. Generators SHALL read node.metrics for display information, not recompute it.

F. Generators SHALL derive statistics from shared aggregate functions (the graph aggregation module and annotator count helpers), not recompute them.

G. All file write operations in output commands SHALL specify explicit `encoding="utf-8"` for cross-platform portability.

### Rationale

Direct graph consumption eliminates data structure conversion overhead and ensures consistency.

### Changelog

- 2026-07-03 | c5dd0546 | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-05-11 | a3575fcc | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-04-23 | a3575fcc | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Output Generators Consume Graph Directly* | **Hash**: c5dd0546
---

## REQ-d00054: Annotation Pipeline Pattern

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

Output generators SHALL follow a standard annotation pipeline pattern.

### Assertions

A. The pipeline SHALL be: parse -> build graph -> annotate nodes -> generate output.

### Rationale

A standard pipeline ensures consistent annotation across all output formats and simplifies debugging.

### Changelog

- 2026-05-11 | 0256df47 | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 0256df47 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Annotation Pipeline Pattern* | **Hash**: 0256df47
---

## REQ-d00055: Node Metrics as Extension Point

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

TraceNode.metrics SHALL be the single extension point for adding data to nodes.

### Assertions

A. All annotation data SHALL be stored in node.metrics dict.

B. Annotators SHALL NOT modify node.children, node.parents, or other structural fields.

C. Metrics keys SHALL use consistent naming (snake_case, descriptive names).

D. Standard metrics keys SHALL include: is_uncommitted, is_moved, is_new, is_roadmap, display_filename, repo_prefix, implementation_files, referenced_pct.

E. Custom metrics MAY be added by specific annotators without modifying TraceNode class.

### Rationale

Using metrics dict as the extension point enables adding new annotations without modifying the core TraceNode dataclass.

### Changelog

- 2026-05-11 | 0073a9c3 | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 0073a9c3 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Node Metrics as Extension Point* | **Hash**: 0073a9c3
---

## REQ-d00069: Indirect Coverage Source

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

The coverage annotation system SHALL support an INDIRECT coverage source for whole-requirement tests that do not target specific assertions.

### Assertions

A. `CoverageSource` enum SHALL include distinct test-evidence values -- `TEST_DIRECT` for an assertion-targeted `Verifies:` and `TEST_INDIRECT` for a whole-requirement `Verifies:` -- kept separate from implementation-evidence sources (`DIRECT`/`EXPLICIT`/`INFERRED`) so that a test that verifies an *Assertion* credits the Tested dimension only and never the Implemented dimension (REQ-d00084-D). (`INDIRECT` remains for the transitive CODE->TEST provenance path.)

B. `RollupMetrics` SHALL track `indirect_referenced_pct` as a separate percentage alongside strict `referenced_pct`.

C. `RollupMetrics` SHALL track `validated_with_indirect` count for assertions validated when including INDIRECT sources.

D. `RollupMetrics.finalize()` SHALL compute the Implemented dimension from implementation-evidence sources only (`DIRECT`/`EXPLICIT`/`INFERRED`); test-evidence sources (`TEST_DIRECT`/`TEST_INDIRECT`) SHALL populate the Tested dimension via `populate_test_dimensions()` and SHALL NOT be counted toward Implemented (REQ-d00084-D).

E. The coverage annotator SHALL emit `TEST_INDIRECT` contributions for all *Assertion* labels when a TEST (`Verifies:`) edge has empty `assertion_targets`, and `TEST_DIRECT` contributions for the named labels of an assertion-targeted TEST edge; both feed the Tested dimension, not Implemented (REQ-d00084-D).

F. When a whole-requirement test has passing results, the annotator SHALL count all assertions as validated for indirect mode.

G. A leaf *Assertion* SHALL be defined as any *Assertion* that has no `Refines:` child pointing at it. Leaf assertions can occur at any level or place in the hierarchy.

H. When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree with composite IDs (`declaring_id::original_id`), creating INSTANCE nodes linked to the declaring requirement via a SATISFIES edge. Coverage SHALL be computed through the standard coverage mechanism operating on the cloned nodes.

I. 100% coverage of a template instance SHALL be achieved when every leaf *Assertion* in the cloned template subtree (excluding N/A assertions) has at least one inbound coverage edge (`Implements:`, `Verifies:`, or `Validates:`) on its template original, consistent with the inherited-coverage rule (REQ-p00014-K).

J. A `Refines:` relationship SHALL NOT contribute coverage by itself, but it SHALL conduct the refining requirement's own rolled-up coverage upward to the *Assertion* it targets. A requirement's coverage SHALL be the mean of its assertions' coverage (assertions are unweighted), computed independently per coverage dimension. An *Assertion*'s coverage SHALL be determined as follows: if the *Assertion* has direct coverage (local evidence on it, or any assertion-targeted `Refines:`/`Implements:` edge naming it), its coverage SHALL be the equal-weight mean of those direct contributions (each contributor -- direct evidence at full value, each assertion-targeted refining requirement at its own rolled-up coverage -- carrying equal weight regardless of how many target the *Assertion*), and whole-requirement (blanket) credit SHALL be ignored for it. Otherwise (the *Assertion* has no direct coverage), it SHALL receive whole-requirement credit: full value if the requirement has local whole-requirement evidence (a whole-requirement test/code/journey), else `1/N` times the mean coverage of the requirement's whole-requirement (blanket) `Refines:` edges, where `N` is the requirement's assertion count -- so a blanket `Refines:` names no *Assertion* and is therefore worth at most one *Assertion*'s share, and a requirement refined by many whole-requirement children is not credited beyond that share. Only the *Assertion* with direct coverage forgoes blanket credit; its sibling *Assertions* without direct coverage still accrue it.

K. The system SHALL report coverage gaps on template instance nodes through the standard coverage mechanisms. Instance nodes are normal graph nodes and participate in existing health checks.

L. Coverage SHALL be tracked on two footings per dimension: strict (direct, assertion-targeted evidence only) and generous (indirect, additionally counting whole-requirement, inferred, conducted, and inherited evidence). Reporting surfaces SHALL headline the generous footing and SHALL express precision as a tier (full-direct, full-indirect, partial, none, failing), rendering an indirect-evidence marker rather than a second count.

### Rationale

Whole-requirement tests (e.g., `test_implements_req_d00087` with no *Assertion* suffix) currently contribute zero *Assertion* coverage. Adding INDIRECT as a separate source allows a "progress indicator" view alongside strict *Traceability*, following the same pattern as INFERRED coverage for requirement-to-requirement relationships.

### Changelog

- 2026-07-03 | ddbc50c8 | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-07-02 | 738d94e4 | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-06-20 | 2d05ad7b | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-06-19 | acbdf3da | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-05-11 | e9b5c3f1 | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-03-30 | e9b5c3f1 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Indirect Coverage Source* | **Hash**: ddbc50c8
---

## REQ-d00070: Indirect Coverage Toggle Display

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

The interactive trace view SHALL provide a toggle to switch between strict and indirect coverage display modes.

### Assertions

A. `TreeRow` SHALL include a `coverage_indirect` attribute computed from `indirect_referenced_pct` using the same thresholds as strict coverage (0=none, <100=partial, 100=full).

B. The template SHALL render a `data-coverage-indirect` attribute on each requirement row.

C. The template SHALL include a toggle control in the filter bar area to switch between strict and indirect coverage views.

D. The default display SHALL show strict coverage (toggle OFF).

E. The `has_failures` warning indicator SHALL display regardless of toggle state.

### Rationale

Users need both a strict *Traceability* view (only *Assertion*-targeted tests count) and a progress indicator view (whole-requirement tests cover all assertions). A toggle lets users switch between modes without regenerating the trace.

### Changelog

- 2026-05-11 | 3e5b1766 | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 3e5b1766 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Indirect Coverage Toggle Display* | **Hash**: 3e5b1766
---

## REQ-d00071: Unified Root vs Orphan Classification

**Level**: dev | **Status**: Active | **Implements**: REQ-o00050, REQ-p00002

The graph builder SHALL distinguish between root nodes and orphan nodes using a unified classification based on meaningful children.

### Assertions

A. The graph builder SHALL classify a parentless node as a root only when it has at least one child whose kind is not a satellite kind.

B. The graph builder SHALL classify a parentless node as an orphan when it has no children whose kind is not a satellite kind.

C. Satellite node kinds SHALL be configurable via `[graph].satellite_kinds` in `.elspais.toml`, defaulting to *Assertion* and TEST_RESULT.

D. USER_JOURNEY nodes SHALL follow the same root vs orphan classification rules as REQUIREMENT nodes.

### Rationale

Currently, all parentless REQUIREMENTs and all USER_JOURNEYs are unconditionally treated as roots, even when disconnected from the rest of the graph. A PRD with only assertions but no OPS/DEV implementations is effectively orphaned — it anchors no subgraph. Unifying the classification rule across all node kinds simplifies the logic and produces more accurate orphan detection.

### Changelog

- 2026-05-11 | 4bd239f1 | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 4bd239f1 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Unified Root vs Orphan Classification* | **Hash**: 4bd239f1
---

## REQ-d00072: Link Suggestion Core Engine

**Level**: dev | **Status**: Active | **Implements**: REQ-o00065

The `graph/link_suggest.py` module SHALL implement the link suggestion scoring pipeline using existing graph analysis building blocks.

### Assertions

A. The suggestion engine SHALL orchestrate all heuristics and return deduplicated suggestions sorted by confidence descending, supporting optional file path and limit filters.

B. The suggestion engine SHALL extract meaningful keywords from test node metadata (function name, class name, file path, docstring), filter stopwords and short tokens, and produce a query string for *Assertion* matching.

C. Deduplication SHALL merge suggestions for the same (test, requirement) pair, keeping the highest confidence and combining reasons.

### Rationale

The core engine composes existing building blocks into a scoring pipeline. Each heuristic reuses proven code rather than reimplementing analysis logic.

### Changelog

- 2026-05-11 | 95f09aea | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 95f09aea | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Link Suggestion Core Engine* | **Hash**: 95f09aea
---

## REQ-d00215: Keyword Extraction Annotator

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

### Assertions

A. The keyword extractor SHALL tokenize text into lowercase words, filtering stopwords, short words (fewer than 3 characters), and punctuation, returning a deduplicated list.

B. The keyword annotator SHALL extract keywords from a node's title, body, and *Assertion* text, storing them in the node's keyword field.

C. The keyword annotator SHALL operate on all node kinds with textual content, not only requirements.

D. Keyword search SHALL return nodes matching given keywords with case-insensitive comparison.

E. Keyword collection SHALL return a sorted, deduplicated list of all keywords across the graph.

### Changelog

- 2026-05-11 | ebe57660 | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-03-30 | ebe57660 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Keyword Extraction Annotator* | **Hash**: ebe57660

## REQ-d00216: TraceGraph Deep Clone

**Level**: dev | **Status**: Active | **Implements**: REQ-p00050

### Assertions

A. The graph clone operation SHALL create a fully independent deep copy such that mutations to the clone do not affect the original.

B. The clone SHALL preserve all node data including IDs, content fields, and metrics.

C. The clone SHALL preserve all edges including parent-child relationships and edge kinds.

D. The clone SHALL preserve the root set, maintaining iteration equivalence with the original.

E. The clone SHALL preserve graph-level metadata such as repository root.

F. The clone SHALL handle DAG structures with multiple parents without infinite recursion.

### Changelog

- 2026-05-11 | a007d5ed | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-04-23 | a007d5ed | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *TraceGraph Deep Clone* | **Hash**: a007d5ed

## REQ-d00250: Section Header Depth Canonicalization

**Level**: dev | **Status**: Active | **Implements**: -

The parser MUST recognize section block headers (`Assertions`,
`Changelog`, named sections) and hash-style sub-headings at any
markdown depth from H1 through H6. The `fix` command MUST
canonicalize too-shallow section headers to `parent.depth + 1`,
preserving legal-but-deeper author choices. The `validate` /
health-check command MUST flag too-shallow section headers
as a fixable issue and flag requirements at H6 with section
blocks as an unfixable issue.

### Assertions

A. Section block headers parse correctly at depths H1 through H6.

B. A section header at depth less than or equal to its parent's
   heading_level is marked parse_dirty with reason
   `section_header_depth`.

C. A requirement at H6 with any section block is marked with
   reason `section_header_depth_unfixable` (stored on
   `parse_unfixable_reasons`, separate from `parse_dirty_reasons`).

D. Render emits each section header at
   `max(stored_depth, parent.heading_level + 1)`, clamped to H6.

E. The `fix` command auto-canonicalizes B and reports C to stderr
   with non-zero exit code.

F. The `validate` / health-check command reports B and C as
   findings with non-zero exit code.

### Changelog

- 2026-05-11 | 903349d2 | - | Developer (dev@example.com) | Auto-fix: canonicalize section header depth
- 2026-05-11 | 903349d2 | - | Developer (dev@example.com) | Auto-fix: update hash, add missing changelog section

*End* *Section Header Depth Canonicalization* | **Hash**: 903349d2

## REQ-d00254: Coverage-Based and Aggregate Test Verification

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

The coverage annotation system SHALL credit test verification through two complementary paths: aggregate app-green status for unmatched test-file edges, and line-coverage fraction for implementation-code edges; both are tracked as separate dimensions distinct from direct `Verifies:` evidence.

### Assertions

A. When a test-file edge has no matching result record, the annotator SHALL consult the per-app green/red signal derived from result nodes whose source path falls within the same app directory. A green app SHALL credit the assertion as verified; a red app SHALL flag the requirement as having failures.

B. The annotator SHALL compute a separate `lcov_tested` dimension by measuring the fraction of implementation lines (from `Implements:` edges) covered by execution data. When the fraction meets or exceeds the configured minimum, the relevant assertions SHALL be credited in `lcov_tested`, which feeds into the `tested_and_passing` union score alongside `verified`.

C. The configuration surface SHALL express test result and coverage ingestion via `[[scanning.test.targets]]` entries, each declaring how a target's results and coverage are produced (`command`) and ingested (`reporter`, `results`, `coverage`, `match`, `credit_coverage`, `min_coverage_fraction`). User documentation SHALL include a `test-targets` topic describing the target model, the available reporters, and a worked Flutter recipe.

D. When an `// Implements:` marker has no function range (i.e., `impl_start_line == impl_end_line`), the annotator SHALL attribute coverage via block-scoped attribution: a run of consecutive marker lines with no executable line strictly between them forms one block, and that block owns the executable lines that follow it up to the next block's first marker or end-of-file. This enables languages without function detection (e.g. Dart) to receive lcov coverage credit for the code each marker precedes.

E. A reporter registry SHALL map each `reporter` format name to a parser and an input channel (`stdout` or `file`). The registry SHALL include a native `flutter test --machine` reporter that parses the machine JSON event stream into result records carrying each test's real source-file path (from the suite path), pass/fail/skip status, and line -- without an external JUnit converter.

F. For each configured target, the system SHALL obtain the reporter's output (captured from the command's stdout for stdout-channel reporters, or read from the `results` glob for file-channel reporters), build RESULT nodes carrying the real test-file path (`source_file`, repo-relative) and the target's `match` mode, and ingest the target's `coverage` file. Coverage crediting SHALL be derived from the targets' `credit_coverage`/`min_coverage_fraction`.

G. Each target SHALL select its result-to-test matching via `match`: `source` SHALL credit verification per test by resolving a result's real source-file path and `test()` source line to the specific test node at that `(path, line)`; when no test node matches that line (e.g. shared-helper or generated tests), it SHALL fall back to file granularity (all passing credits the file's `Verifies:` assertions; any failure flags them). `aggregate` SHALL use the per-app green/red engine.

H. `elspais checks --run-tests` SHALL accept a `--targets` selector naming a subset of `[[scanning.test.targets]]` to execute; an unknown target name SHALL be an error, and an absent selector SHALL execute all targets. The same `--targets` flag on `summary`/`trace` SHALL mark provenance without executing anything.

I. A target absent from `--targets` (the fresh set) whose results are ingested from disk SHALL be tagged *carried*; its verdict SHALL be honored faithfully (a carried failing result still flags the requirement as failing), and the `verified` dimension SHALL carry a `carried` flag orthogonal to its pass/fail tier so the matrix can render it as `(baseline)`.

J. In a selective run (a `--targets` set is present), a requirement with test references but zero result records SHALL render as not-run (`—`), distinct from a run-but-uncovered `0%`; in a full run (no `--targets`) zero results SHALL keep the existing rendering.

### Changelog

- 2026-07-01 | 4975d47a | - | Michael Lewis (michael@anspar.org) | Auto-fix: sync changelog hash
- 2026-06-26 | 0b87cbd4 | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-06-26 | abc6e487 | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-06-21 | 6962b5a4 | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-06-20 | 81f6cdcd | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-06-20 | 98120740 | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-06-20 | 00000000 | - | Michael Lewis (michael@anspar.org) | CUR-1533: initial

*End* *Coverage-Based and Aggregate Test Verification* | **Hash**: 4975d47a

---

## REQ-d00255: Test-to-Journey UAT Verification

**Level**: dev | **Status**: Draft | **Implements**: REQ-o00051

### Assertions

A. elspais SHALL accept a `USER_JOURNEY` id as a `Verifies:` target in code and test files, recording that the referencing test (or code) verifies the journey via a VERIFIES edge carried on the journey node (mirroring how an assertion-scoped `Verifies:` attaches to its parent requirement).

B. The annotation pipeline SHALL roll up verifying test results to the journey via the standard coverage convention, computing a per-journey verification metric from the pass/fail status of all tests that `Verifies:` the journey.

C. A journey SHALL feed `uat_verified` credit on each requirement its `Validates:` edges name in proportion to its verification, using the same `uat_verified` dimension populated by the existing UAT annotation pass: a fully-verified journey SHALL credit full; a partially-verified journey with no failing step SHALL credit partial (its verified-step ratio); a journey with any failing step SHALL contribute a failure signal (`has_failures`) to the named assertions rather than positive credit; an unverified journey SHALL credit none. This aligns with the partial verification tier of REQ-d00256-C.

D. The test-to-journey-to-requirement *Traceability* chain SHALL be visible in `elspais trace` output and the viewer, showing which journeys verify which requirements and their verification status.

*End* *Test-to-Journey UAT Verification* | **Hash**: bdad84a0

---

## REQ-d00256: Step-Level UAT Verification

**Level**: dev | **Status**: Draft | **Implements**: REQ-o00051

### Assertions

A. A journey's `## Steps` numbered list SHALL be parsed into addressable `STEP` nodes with ids of the form `JNY-.../step-N`, linked under the journey via `STRUCTURES` edges.

B. A STEP node id (`JNY-.../step-N`) SHALL be a legal `Verifies:` target in test and code files, creating a VERIFIES edge scoped to that step on the parent journey node.

C. Steps SHALL roll up to the journey's verification metric: a step SHALL be considered verified if it has at least one passing and zero failing verifying tests; an untested step SHALL leave the journey in a partial verification tier rather than fully verified.

D. When a journey's verification tier is failing, the system SHALL identify the specific failing step(s) by id in the journey's verification output and API payload.

*End* *Step-Level UAT Verification* | **Hash**: 44671fc1

---

## REQ-d00257: UAT-Scoped Traceability Report

**Level**: dev | **Status**: Draft | **Implements**: REQ-o00051

### Assertions

A. The `trace` command SHALL accept a `--dimension uat` flag that selects a UAT-scoped output mode.

B. The UAT report SHALL include only requirements that have at least one incoming VALIDATES edge, and for each such requirement SHALL list the validating journeys with their verification verdicts and the `uat_coverage`/`uat_verified` coverage tiers.

C. The UAT report SHALL exclude code implementation and test verification columns (`implemented`, `tested`, `verified`, `code_tested`, `lcov_tested`).

*End* *UAT-Scoped Traceability Report* | **Hash**: 45bb196f

---

## REQ-d00258: Reporting Surface Consistency

**Level**: dev | **Status**: Active | **Implements**: REQ-d00069

Reporting surfaces (trace, summary, MCP project summary, HTML viewer) SHALL present coverage using a single consistent vocabulary, aggregation, and tier-derived color scheme so that identical underlying data yields identical answers across surfaces.

### Assertions

A. All reporting surfaces (trace, summary, MCP project summary, HTML viewer) SHALL headline coverage counts on the generous footing per REQ-d00069-L, and text surfaces SHALL append a `~` marker to any count whose evidence is not fully direct.

B. Reporting surfaces SHALL use exactly five coverage display terms: Implemented, Tested, Passing, UAT Covered, UAT Passed. The term "Validated" SHALL NOT denote test coverage. Passing SHALL be the union of result-verified and line-coverage-credited evidence.

C. The CLI summary, the MCP project summary, and the viewer SHALL derive their coverage statistics from a single shared aggregation so identical questions receive identical answers.

D. Viewer coverage colors SHALL be resolved through the theme catalog by severity name (tier -> configured severity -> named catalog entry), never through hard-coded color values, and the coverage tier states SHALL appear in the viewer Legend.

E. Viewer coverage filters SHALL bucket requirements by tier semantics (full = any full tier, partial, none, plus a failing overlay), never by color string. The requirement-level line coverage cell SHALL NOT render a direct-attribution count for targets whose tooling provides only aggregate coverage.

F. A per-level `expects_validation` flag (default false) SHALL declare that requirements at that level are expected to have UAT validation (a USER_JOURNEY that `Validates:` them). When a level expects validation, a requirement of that level with no UAT coverage SHALL be a reported gap: flagged by the health `uat.coverage` check and listed under `gaps unvalidated`, and its viewer UAT badge SHALL render at error severity (red). When a level does not expect validation (the default), absent UAT SHALL be neither flagged by health, listed as a gap, nor badged in the viewer, and SHALL NOT drag the requirement's combined coverage bucket. The `uat.coverage` check SHALL count only requirements at expects_validation levels; when no level expects validation it SHALL pass trivially. All surfaces SHALL resolve this flag through a single shared helper rather than reading the level config independently.

G. The viewer SHALL assign each *Assertion* a semantic coverage *standing* (full, partial, failing, or missing) per coverage dimension, projected from the requirement's rollup metrics, so that if every *Assertion* is full on a dimension the requirement badge for that dimension reads full, and if any *Assertion* is failing the requirement dimension reports a failure. An *Assertion*'s standing SHALL read failing only when that *Assertion* itself has a failing result or verification for the dimension, not because a sibling *Assertion* covered by a different, non-failing test or journey failed; a failing test or journey attributes the failure to exactly the assertions it covers (its named targets, or every assertion when it covers the whole requirement). The standing SHALL be computed server-side and applied on initial render, without depending on a lazy client prefetch. Standing colors SHALL be resolved through the theme catalog by standing name (never hard-coded in the badge logic), the same decoupling severity colors use per D, so the standing-to-color association is configurable, and the standings SHALL appear in the viewer Legend. The direct-versus-indirect distinction need not be surfaced at the *Assertion* badge level.

### Changelog

- 2026-07-06 | 06550baf | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-07-06 | dd54712c | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-07-06 | 489752cd | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-07-03 | c843c727 | - | Michael Lewis (michael@anspar.org) | Auto-fix: update hash
- 2026-07-02 | be97c170 | - | Michael Lewis (michael@anspar.org) | Auto-fix: add missing changelog section

*End* *Reporting Surface Consistency* | **Hash**: 06550baf
