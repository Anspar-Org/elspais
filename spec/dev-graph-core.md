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

- 2026-07-31 | c9217201 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 8ca0389e | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 8ca0389e | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Node Annotator Functions* | **Hash**: c9217201
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

- 2026-07-31 | ca876d95 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 97c0f6fc | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 97c0f6fc | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Graph Aggregate Functions* | **Hash**: ca876d95
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

- 2026-07-31 | abb3f6b8 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | c5dd0546 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | a3575fcc | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | a3575fcc | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Output Generators Consume Graph Directly* | **Hash**: abb3f6b8
---

## REQ-d00054: Annotation Pipeline Pattern

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

Output generators SHALL follow a standard annotation pipeline pattern.

### Assertions

A. The pipeline SHALL be: parse -> build graph -> annotate nodes -> generate output.

### Rationale

A standard pipeline ensures consistent annotation across all output formats and simplifies debugging.

### Changelog

- 2026-07-31 | 374f7365 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 0256df47 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 0256df47 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Annotation Pipeline Pattern* | **Hash**: 374f7365
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

- 2026-07-31 | 1c90d8fa | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 0073a9c3 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 0073a9c3 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Node Metrics as Extension Point* | **Hash**: 1c90d8fa
---

## REQ-d00069: Indirect Coverage Source

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

The coverage annotation system SHALL support an INDIRECT coverage source for whole-requirement tests that do not target specific assertions.

### Assertions

A. `CoverageSource` enum SHALL include distinct test-evidence values -- `TEST_DIRECT` for an assertion-targeted `Verifies:` and `TEST_INDIRECT` for a whole-requirement `Verifies:` -- kept separate from implementation-evidence sources (`DIRECT`/`EXPLICIT`/`INFERRED`) so that a test that verifies an *Assertion* credits the Tested dimension only and never the Implemented dimension (REQ-d00084-D). (`INDIRECT` remains for the transitive CODE->TEST provenance path.)

B. A whole-requirement (assertion-less) reference SHALL credit every *Assertion* of the target requirement in the indirect measure, at full value, and SHALL credit no direct measure. This SHALL hold for `Verifies:` (Tested), `Implements:` on CODE (Implemented), `Implements:`/`Refines:` from a child requirement, and `Validates:` from a journey alike -- a reference that names no *Assertion* names them all equally, whatever keyword carried it.

C. `RollupMetrics` SHALL track `validated_with_indirect` count for assertions validated when including INDIRECT sources.

D. `RollupMetrics.finalize()` SHALL compute the Implemented dimension from implementation-evidence sources only (`DIRECT`/`EXPLICIT`/`INFERRED`); test-evidence sources (`TEST_DIRECT`/`TEST_INDIRECT`) SHALL populate the Tested dimension via `populate_test_dimensions()` and SHALL NOT be counted toward Implemented (REQ-d00084-D).

E. The coverage annotator SHALL emit `TEST_INDIRECT` contributions for all *Assertion* labels when a TEST (`Verifies:`) edge has empty `assertion_targets`, and `TEST_DIRECT` contributions for the named labels of an assertion-targeted TEST edge; both feed the Tested dimension, not Implemented (REQ-d00084-D).

F. When a whole-requirement test has passing results, the annotator SHALL count all assertions as validated for indirect mode.

G. A leaf *Assertion* SHALL be defined as any *Assertion* that has no `Refines:` child pointing at it. Leaf assertions can occur at any level or place in the hierarchy.

H. When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree with composite IDs (`declaring_id::original_id`), creating INSTANCE nodes linked to the declaring requirement via a SATISFIES edge. Coverage SHALL be computed through the standard coverage mechanism operating on the cloned nodes.

I. 100% coverage of a template instance SHALL be achieved when every leaf *Assertion* in the cloned template subtree (excluding N/A assertions) has at least one inbound coverage edge (`Implements:`, `Verifies:`, or `Validates:`) on its template original, consistent with the inherited-coverage rule (REQ-p00014-K).

J. A `Refines:` relationship SHALL NOT contribute coverage by itself; it SHALL conduct the coverage of the refining requirement to the assertions its own citation names -- the *Assertion* it names, or every *Assertion* of the requirement where it names only the requirement. Each measure SHALL conduct into the same measure, direct into direct and indirect into indirect, so that no measure is ever composed of another. The value conducted SHALL be the mean, in that measure, of the contributing requirements' own coverage, a requirement's coverage being the mean over its assertions, computed independently per dimension.

K. The system SHALL report coverage gaps on template instance nodes through the standard coverage mechanisms. Instance nodes are normal graph nodes and participate in existing health checks.

L. Coverage SHALL be measured on two independent axes per dimension. The first axis is what a citation named: *direct* where it named the *Assertion* it credits, *indirect* where it named only the requirement and is therefore attributed equally to every *Assertion* of it. The second axis is where the evidence sits: *immediate* where it is attached to what is being reported, and *rolled-up* where it is conducted from a refining requirement, in which case the first axis describes the refining requirement's own evidence. The four measures they yield SHALL each be reported in their own right, and none SHALL be defined in terms of another.

M. An *Assertion*'s immediate coverage SHALL be whole or absent, since a citation either names it or does not. Its rolled-up coverage MAY be fractional, being the mean of the coverage of the requirements refining it, so that a partially finished refinement reads as partially done.

N. Total coverage SHALL be reported as well, taken per *Assertion* as the greatest of that *Assertion*'s four measures, so that an *Assertion* covered more than one way is counted once and a requirement's total can never exceed its number of assertions.

### Rationale

Two questions are asked of coverage and they are not the same question. "What still needs doing here" is answered by what a citation names and where it is attached: an *Assertion* nobody has cited is work, however finished the requirements refining it may be. "How much of this is real" is answered by conduction: a requirement high in the tree is rarely cited by code at all, and what makes it true is the state of everything beneath it. One number cannot answer both, and a number that tries answers neither -- averaging an *Assertion*'s own citation together with the progress of a refinement made the figure move when nothing about that *Assertion* had changed, and let an *Assertion* nobody had cited read as fully covered because something below it was finished.

A measure conducts only into itself, because the two are not the same unit. Direct coverage counts assertions somebody wrote evidence against; indirect counts assertions reached by evidence written against their requirement. Adding one to the other, or letting a requirement covered only as a whole raise an *Assertion*'s direct figure one level up, would put a number under a description that is not true of it -- and would do so invisibly, since nothing downstream can tell which part of a summed figure came from where. What the refining citation names decides which assertions receive a conducted value; it does not decide which measure that value belongs to.

Separating the axes is what makes each measure sayable in a sentence. Direct and indirect say what a citation named; immediate and rolled-up say whether the evidence is attached here or conducted from below. Each of the four is reported in its own right, so no measure is defined as another's remainder, and each can independently be complete: a requirement whose assertions are each cited AND which is also cited as a whole is fully covered twice over, which the old nested pair could not express.

Total exists because a reader also wants one number, and taking it per *Assertion* as the greatest of that *Assertion*'s measures is what keeps it honest -- an *Assertion* covered three ways is still one covered *Assertion*, so a requirement's total can never exceed the number of assertions it has.

Whole-requirement tests (e.g., `test_implements_req_d00087` with no *Assertion* suffix) currently contribute zero *Assertion* coverage. Adding INDIRECT as a separate source allows a "progress indicator" view alongside strict *Traceability*, following the same pattern as INFERRED coverage for requirement-to-requirement relationships.

### Changelog

- 2026-08-17 | 6de09e95 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | 6ac9e8a6 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: measure coverage on two axes -- what a citation named, and whether the evidence is attached or conducted -- reporting each measure in its own right plus a per-assertion total (J, L, M, N)
- 2026-07-31 | 8c02235b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-07 | 2d89da53 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | ddbc50c8 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-02 | 738d94e4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-20 | 2d05ad7b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-19 | acbdf3da | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | e9b5c3f1 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | e9b5c3f1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Indirect Coverage Source* | **Hash**: 6de09e95
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

- 2026-07-31 | a55fcb89 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 3e5b1766 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 3e5b1766 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Indirect Coverage Toggle Display* | **Hash**: a55fcb89
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

- 2026-07-31 | f2cb5f45 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 4bd239f1 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 4bd239f1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Unified Root vs Orphan Classification* | **Hash**: f2cb5f45
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

- 2026-07-31 | 9d57c2ad | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 95f09aea | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 95f09aea | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Link Suggestion Core Engine* | **Hash**: 9d57c2ad
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

- 2026-07-31 | db477d99 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | ebe57660 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | ebe57660 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Keyword Extraction Annotator* | **Hash**: db477d99

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

- 2026-07-31 | 0caf26af | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | a007d5ed | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | a007d5ed | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *TraceGraph Deep Clone* | **Hash**: 0caf26af

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

- 2026-07-31 | 48fc2f11 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 903349d2 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-05-11 | 903349d2 | - | Developer (<dev@example.com>) | Auto-fix: update hash, add missing changelog section

*End* *Section Header Depth Canonicalization* | **Hash**: 48fc2f11

## REQ-d00268: Report Malformed Assertion Labels

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

Spec files are ordinary markdown that any editor can produce, so the labelling a requirement arrives with cannot be assumed well-formed. A label the parser cannot place is reported against its source rather than passed over.

### Assertions

A. An *Assertion* label outside the configured label series SHALL be reported, naming the file, the requirement and the label, and SHALL NOT be read as an assertion, skipped, or absorbed into surrounding prose.

B. An *Assertion* label that repeats one already used in the same requirement SHALL be reported, naming both occurrences.

C. An *Assertion* label that is not the successor of the label before it SHALL be reported, naming the label found and the label expected, so that a series with a label missing from the middle is reported rather than read as complete.

D. A requirement whose assertions do not form a single run SHALL be reported, naming the requirement and the number of runs found; no run SHALL displace another.

E. A requirement carrying any condition in assertions A through D SHALL NOT be reported as parsed successfully, and the conditions found SHALL be reported together rather than only the first.

### Rationale

A label is a permanent name: references point at it, coverage accrues to it, and a reader relies on the sequence to tell whether they have seen everything. Each condition here is a label the parser cannot honour, and the failure being prevented is the same in all of them — reading a requirement as complete when part of it was not understood, which leaves the omission to be discovered as a coverage gap that was never real. Assertion C is what makes a series legible: a removed *Assertion* keeps its label and is marked retired rather than vanishing, so a label missing from the middle is evidence of loss rather than of removal. Assertion E prevents the diagnosis arriving one item at a time, which for a file being repaired by hand is the difference between one pass and four.

### Changelog

- 2026-08-10 | cb7e96dd | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | Initial authoring: report malformed assertion labelling instead of discarding it

*End* *Report Malformed Assertion Labels* | **Hash**: cb7e96dd

## REQ-d00272: Reference Fault Classification

**Level**: dev | **Status**: Active | **Implements**: REQ-p00014-R
**Satisfies**: REQ-p00019

A reference that fails is described by how far reading it got, and the classes are only as useful as the rule that assigns them. This states that rule: what decides that an item was written as an identifier at all, which repository's grammar it should be read against, and how much of a defect may be named without guessing.

### Assertions

A. An item SHALL be assigned the class of the furthest stage of reading it completed, and no later stage SHALL be reported for it.

B. An item containing a space SHALL NOT be read as an identifier. A report SHALL NOT describe such an item as naming a repository, an unconfigured repository included.

C. An item no grammar of the federation accepts SHALL be attributed to a repository where the namespace it opens with is one that repository declares, and to no repository otherwise. What separates an identifier of this estate written wrongly from a name belonging outside it SHALL be that declaration, not the item's resemblance to any pattern.

D. Where re-reading an item under relaxations of the grammar that accepts its namespace makes it acceptable, the report SHALL name the smallest set of relaxations that does so.

E. An item that opens with an acceptable reference and continues into content no grammar accounts for SHALL be reported naming both the reference found and the content unaccounted for.

F. Reading within an item SHALL inform what is reported about it and SHALL NOT contribute a relationship, so that no relationship exists that its author did not spell.

G. A *Traceability* keyword SHALL have one canonical spelling. A keyword recognised in any other SHALL be reported at a severity the project configures, and SHALL produce the relationships it introduced regardless.

H. A keyword introducing no content SHALL be reported as having introduced none.

J. A *Traceability* keyword a file's kind does not admit SHALL be read, and the relationship it declares SHALL be refused as one the keyword may not take. It SHALL NOT be passed over as though it were prose.

K. Where a reference list names the same target more than once, every instance SHALL be reported and none SHALL produce a relationship.

L. Where an item both opens with an acceptable reference and can be read as differing from one by a relaxation, the relaxation SHALL be reported. Trailing content SHALL be reported only where no relaxation accounts for the item.

M. An item holding any character no identifier configuration can admit SHALL be treated under B. A character the writing system counts as a space is such a character, whichever one it is, as is any character reserved out of every identifier pattern.

N. An identifier SHALL have one canonical spelling. A reference written in another spelling the configuration admits SHALL be reported at a severity the project configures, and SHALL produce the relationship it names regardless.

O. Where an identifier is the first content of a comment that no *Traceability* keyword introduces, and the comment does not continue a list, the tool SHALL report that a relationship appears to be intended and is not declared, at a severity the project configures. It SHALL produce no relationship.

### Rationale

B and C are the whole of the decidability claim, and they are stated as tests on the item rather than as descriptions of what an identifier looks like because a shape can always be argued with. A space is what no identifier of any configuration contains, and a declared namespace is a fact the federation holds rather than an inference about the text; between them they separate three populations that a project acts on differently — text that was never a reference, an estate identifier spelled wrongly, and a name belonging to a repository nobody configured. Collapsing any two of those sends an author to work that will not fix anything.

D bounds diagnosis by minimality rather than by a list of defects worth naming. The smallest set is the one the input determines; a larger set that also succeeds contains a relaxation the input never asked for, and naming it describes a defect the author does not have.

E and F are a pair, and F is what makes E safe. Looking inside an item is exactly the move that, allowed to produce a relationship, credits a requirement its author never named — and credits it silently, since a reference that resolved is a reference that looked fine. The distinction that keeps E is not how far the tool may look but what it may do with what it finds: describing costs nothing, because a description cannot be mistaken downstream for a declaration.

G separates recognition from form. What a keyword is cannot depend on its case without making a report's absence depend on it too, so a differently-cased keyword is read; that its form is non-canonical is a fact about the file worth reporting, but withholding the relationships it introduced would punish the reference for the keyword's spelling.

J settles what a keyword does where the file's kind does not admit it. Passing it over reads as prose a line that is unmistakably a declaration, and the author of an annotation that did nothing is never told why — the failure a journey's misplaced validation declaration is already reported to prevent. Reading it and refusing the relationship says both true things at once: this is a declaration, and it is not one this file may make.

K makes a repeated target an error rather than a convenience. Silently keeping the first instance leaves the others producing neither a relationship nor a report, which is the silence this requirement exists to remove; and the silence is not even uniform, since two spellings of one identifier that differ in case are not recognised as repeats and so do report. Refusing all instances rather than keeping one is what makes the report actionable: a list that names a target twice is a list its author has lost track of, and resolving it for them would hide that.

L ranks trailing content beneath every named relaxation. An item that opens with a valid reference can always be read as that reference plus whatever follows, so an unranked trailing-content reading accounts for every malformed item and would either win every time or tie every time — leaving the named relaxations unreachable and every diagnosis generic. Ranking it last makes it what it should be: the account that applies when nothing more specific does.

M keeps the space test from turning on which space was typed, and generalises past spaces for the same reason. A character that reads as a space to an author but not to the test would take an item that is plainly not an identifier and report it as a name from a repository nobody configured — the precise misattribution B exists to prevent, reintroduced by an invisible character. The same holds for a character reserved out of every identifier pattern: no configuration can produce one, so an item carrying it was not written as an identifier, and saying so needs no judgement about what it resembles. Stating the test as a property of the character rather than listing the characters means a newly reserved one is covered when it is reserved rather than when someone remembers to add it here.

O names a habit rather than a defect. Opening a comment with an identifier and then explaining, in prose, why the code below answers to it is a natural way to write, and an author doing it means the relationship — they have simply not spelled it in the form the tool reads. Reporting it as a malformed reference would be wrong twice: nothing about it is malformed, and the useful message is not that something is broken but that saying it with a keyword would make it count.

What makes the report safe is that it produces nothing. An informal citation is evidence of intent, not a declaration, and inferring a relationship from intent is the failure every other assertion here exists to prevent — an edge nobody wrote, indistinguishable downstream from one they did. So the tool says what it sees and leaves the declaring to the author.

The exclusions are what keep it from firing on text that means something else. A comment a keyword introduces is already a declaration and is judged as one. A comment continuing a list is part of that list, and its identifier is an item rather than a citation. Everything else that opens a comment with an identifier is an author pointing at a requirement without linking to it, which is worth one line of report and no more.

N pairs with G, one for the referent and one for the keyword. Both say the same thing: a spelling the configuration admits produces its relationship, and that it is not the canonical spelling is a fact about the file worth reporting rather than a reason to withhold an edge. Which spellings a configuration admits is settled elsewhere; what N adds is that admitting more than one form does not mean writing more than one.

This requirement declares `Satisfies:` against the REQ-p00019 anti-pattern template and concretizes its classes for reference reading. Misattribution and double-counting are the classes this subsystem exists to answer, and assertions A, B and C pin them: one class per item and never a later one, no describing an item holding a space as though it named a repository, and attribution decided by what a repository declares rather than by what the text resembles. Silent omission and unreported non-performance are pinned by the obligation to report every recognised reference that produces no relationship (REQ-d00269-F, REQ-d00269-G), and phantom success by the rule that reading within an item informs a report and never contributes an edge (assertion F, REQ-d00269-J). Undisclosed substitution is pinned twice over: a list of which some items bound and others did not is a partial result, disclosed by reporting each item that failed, and a defect the tool could not determine is carried as the generic code rather than passed off as no defect at all (REQ-d00271-C).

The template's remaining classes bind to this subsystem through the instance without a tool-specific strengthening. That a failure report names the operation, the cause, and a remedy or the absence of one is one of them, and it does not compete with the rule that a code names a defect rather than a repair: the code says what is wrong, the report may also say what would answer it, and the two are different layers of the same finding.

One class has no purchase here and is left visibly uncovered rather than answered. A classification is computed from file content at every build and no verdict is cached, so this subsystem serves no value that can diverge from the sources it came from. Divergence between a served answer and changed sources is real elsewhere in the tool and is covered where it lives (REQ-p00015-E, REQ-p00015-G).

### Changelog

- 2026-08-16 | d01290ac | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-16 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: an identifier opening a comment with no keyword is reported as an undeclared relationship and produces none (O)
- 2026-08-16 | fadb924e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-16 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: Active — the five classes now reach `elspais checks` as `references.*`, each with its own severity, and G/N's keyword/identifier-form reporting is `references.keyword_form`
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: generalise the space test to any character no configuration can admit (M); one canonical spelling per identifier, reported not withheld (N)
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: a keyword its file may not use is read and refused rather than passed over (J); every instance of a repeated target is reported and none resolves (K); trailing content ranks beneath every named relaxation (L); any space character reaches the space test (M)
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: record how each REQ-p00019 class is answered for this subsystem — concretized, bound through the instance, or left visibly uncovered with its reason
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | Initial authoring: the rule assigning reference failure classes — the space and namespace tests, minimal relaxation, and reading within an item without binding from it

*End* *Reference Fault Classification* | **Hash**: d01290ac

## REQ-d00254: Test Evidence: Attribution, Ingestion, and Coverage Crediting

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

Test verification evidence SHALL be attributed per test as it is scanned and ingested from configured test targets. Line coverage of implementation code is measured alongside it as its own dimension, answering a different question from *Traceability* and never standing in for it.

### Assertions

A. Where no result record binds to a test, that test SHALL contribute no verdict, and the assertions it declares SHALL be reported as awaiting a result. No verdict SHALL be inferred for a test from the results of other tests -- neither from the file it is written in nor from the application it belongs to.

B. The annotator SHALL compute a separate `lcov_tested` dimension by measuring the fraction of implementation lines (from `Implements:` edges) covered by execution data. When the fraction meets or exceeds the configured minimum, the relevant assertions SHALL be credited in `lcov_tested`. That dimension SHALL be reported in its own right and SHALL NOT credit any *Traceability* coverage dimension.

C. The configuration surface SHALL express test result and coverage ingestion via `[[scanning.test.targets]]` entries, each declaring how a target's results and coverage are produced (`command`) and ingested (`reporter`, `results`, `coverage`, `match`, `credit_coverage`, `min_coverage_fraction`). User documentation SHALL include a `test-targets` topic describing the target model, the available reporters, and a worked Flutter recipe.

D. When an `// Implements:` marker has no function range (i.e., `impl_start_line == impl_end_line`), the annotator SHALL attribute coverage via block-scoped attribution: a run of consecutive marker lines with no executable line strictly between them forms one block, and that block owns the executable lines that follow it up to the next block's first marker or end-of-file. This enables languages without function detection (e.g. Dart) to receive lcov coverage credit for the code each marker precedes.

E. A reporter registry SHALL map each `reporter` format name to a parser and an input channel (`stdout` or `file`). The registry SHALL include a native `flutter test --machine` reporter that parses the machine JSON event stream into result records carrying each test's real source-file path (from the suite path), pass/fail/skip status, and line -- without an external JUnit converter.

F. For each configured target, the system SHALL obtain the reporter's output (captured from the command's stdout for stdout-channel reporters, or read from the `results` glob for file-channel reporters), build RESULT nodes carrying the real test-file path (`source_file`, repo-relative) and the target's `match` mode, and ingest the target's `coverage` file. Coverage crediting SHALL be derived from the targets' `credit_coverage`/`min_coverage_fraction`. File-channel results SHALL additionally record where each result was recorded — the results artifact's repo-relative path and, when derivable from the artifact (e.g. one JUnit `<testcase>` per line), the per-result line — as provenance distinct from the test's source path, and result links in reporting surfaces SHALL point at that artifact location.

G. Each target SHALL select its result-to-test matching via `match`: `source` SHALL bind each result at the most precise scope available — first step scope, when the result's recorded test name embeds exactly one journey-step reference (in the configured reference form) that resolves to a step whose verifying test(s) live in the result's source file; then test scope, resolving the result's real source-file path and `test()` source line to the specific test node at that `(path, line)`. A result that binds at neither scope SHALL credit nothing. `aggregate` SHALL derive the per-app green/red signal, which informs the line-coverage dimension only.

H. `elspais checks --run-tests` SHALL accept a `--targets` selector naming a subset of `[[scanning.test.targets]]` to execute; an unknown target name SHALL be an error, and an absent selector SHALL execute all targets. The same `--targets` flag on `summary`/`trace` SHALL mark provenance without executing anything.

I. A target absent from `--targets` (the fresh set) whose results are ingested from disk SHALL be tagged *carried*; its verdict SHALL be honored faithfully (a carried failing result still flags the requirement as failing), and the `verified` dimension SHALL carry a `carried` flag orthogonal to its pass/fail tier so the matrix can render it as `(baseline)`.

J. In a selective run (a `--targets` set is present), a requirement with test references but zero result records SHALL render as not-run (`—`), distinct from a run-but-uncovered `0%`; in a full run (no `--targets`) zero results SHALL keep the existing rendering.

K. For every configured test framework, the system SHALL bind each scanned test to its own identity within its source file and to that test's line extent, regardless of the framework's implementation language.

L. Where an external test-prescan command is configured, the system SHALL obtain per-test attribution for the candidate test files from that command.

M. The system SHALL exchange prescan data with a configured external test-prescan command by writing the candidate test file paths to the command's standard input and reading attribution records from its standard output, each record binding one test to its source file, its identity within that file, and its starting line.

N. Where an external test-prescan command returns attribution records for a scanned test file, the system SHALL bind that file's tests from those records in preference to the system's built-in attribution.

O. A line number a reporter records SHALL be read in the origin that reporter counts from. That origin SHALL be declared with the reporter and SHALL be overridable per target, and a recorded line SHALL be normalised to the numbering the tool uses for source lines before it is matched against a test or shown to a reader.

### Rationale

A line number means nothing without its origin, and producers disagree: the `line` attribute pytest writes into JUnit XML counts from zero, while the tool numbers source lines from one. Read as though they agreed, every such result missed the test it named by exactly one line and bound at file granularity instead -- which the file-granular inference then papered over, so the disagreement never surfaced as an error. Declaring the origin with the reporter puts the knowledge where the format is known rather than in each project's config, and the per-target override is for a producer that departs from its format's convention. Normalising once, at ingestion, is what keeps the rest of the system able to treat a line as a line -- to match on it, and to point a reader at it.

A test that returned no result is awaiting one, and nothing else is known about it. The inference this replaces -- reading a verdict for one test off the results of its neighbours, in the same file or the same application -- was built to work around test files that supposedly could not carry their own `Verifies:` annotation. They can, in every language the tool reads tests in, so the workaround bought nothing and cost the distinction: a deselected tier, an unbuilt target and a crashed runner all left their assertions reported as passing on the strength of tests that say nothing about them. Its failing half was worse, blaming an *Assertion* for a sibling test's failure, which REQ-d00258-G forbids one level down. Aggregate results still say something real about an application, and that is where they are read: the line-coverage dimension, which measures the code rather than the *Traceability*.

K states the outcome the scanning side owes the crediting side: without per-test identity and extent, the line-level dimensions computed here have nothing to intersect implementation ranges against, and a framework's tests can only ever be credited at file granularity. The obligation is deliberately language-neutral — it fixes what attribution must yield, not whether a given language earns built-in support or is served through an external command.

L, M and N cut the external route into a capability, a mechanism, and a precedence rule so each can change independently. L and M differ in kind: L survives a reimplementation that swaps the transport, while M memorializes the transport itself — file paths on standard input, attribution records on standard output. M is frozen not because it is an invariant but because it is a published integration point that third-party prescan scripts already implement, so breaking it breaks consumers outside this repository. Recording it as its own letter keeps that compatibility obligation targeted: a future transport change, or an added record field, edits M and leaves the capability and precedence untouched, and M can be retired without withdrawing either.

M binds each record to a starting line only. Extent on the external route is derived from the surrounding records rather than reported, so the derivation stays an implementation choice while K's extent obligation still holds for tests attributed that way.

N resolves per file, not per configuration, because both routes are routinely live in a single run: a project may configure a command that returns records for one file type while every other scanned test file falls to built-in attribution.

### Changelog

- 2026-08-17 | b7f71d81 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: a reporter's line numbers are read in the origin it counts from, declared with the reporter and normalised at ingestion (O)
- 2026-08-17 | 11ca8985 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-08-17 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: a test with no result of its own contributes no verdict; no verdict is inferred from other tests in the file or the application (A, G)
- 2026-08-17 | 87077749 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-08-03 | 22faeb40 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | cbd59482 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | ea4e01b1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | fb1ca602 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-08 | 0f7323ff | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-01 | 4975d47a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-06-26 | 0b87cbd4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-26 | abc6e487 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-21 | 6962b5a4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-20 | 81f6cdcd | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-20 | 98120740 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-20 | 00000000 | - | Michael Lewis (<michael@anspar.org>) | CUR-1533: initial

*End* *Test Evidence: Attribution, Ingestion, and Coverage Crediting* | **Hash**: b7f71d81

---

## REQ-d00255: Test-to-Journey UAT Verification

**Level**: dev | **Status**: Draft | **Implements**: REQ-o00051

### Assertions

A. elspais SHALL accept a `USER_JOURNEY` id as a `Verifies:` target in code and test files, recording that the referencing test (or code) verifies the journey via a VERIFIES edge carried on the journey node (mirroring how an assertion-scoped `Verifies:` attaches to its parent requirement).

B. The annotation pipeline SHALL roll up verifying test results to the journey via the standard coverage convention, computing a per-journey verification metric from the pass/fail status of all tests that `Verifies:` the journey.

C. A journey SHALL feed `uat_verified` credit on each requirement its `Validates:` edges name in proportion to its verification, using the same `uat_verified` dimension populated by the existing UAT annotation pass: a fully-verified journey SHALL credit full; a partially-verified journey with no failing step SHALL credit partial (its verified-step ratio); a journey with any failing step SHALL contribute a failure signal (`has_failures`) to the named assertions rather than positive credit; an unverified journey SHALL credit none. This aligns with the partial verification tier of REQ-d00256-C.

D. The test-to-journey-to-requirement *Traceability* chain SHALL be visible in `elspais trace` output and the viewer, showing which journeys verify which requirements and their verification status.

*End* *Test-to-Journey UAT Verification* | **Hash**: ab5cb648

---

## REQ-d00256: Step-Level UAT Verification

**Level**: dev | **Status**: Draft | **Implements**: REQ-o00051

### Assertions

A. A journey's `## Steps` numbered list SHALL be parsed into addressable `STEP` nodes whose ids suffix the step number to the journey id using the configured *Assertion*-reference separator (mirroring assertion addressing), linked under the journey via `STRUCTURES` edges.

B. A STEP node id SHALL be a legal `Verifies:` target in test and code files, creating a VERIFIES edge scoped to that step on the parent journey node.

C. Steps SHALL roll up to the journey's verification metric: a step SHALL be considered verified if it has at least one passing and zero failing verifying tests; an untested step SHALL leave the journey in a partial verification tier rather than fully verified.

D. When a journey's verification tier is failing, the system SHALL identify the specific failing step(s) by step number in the journey's verification output and API payload.

E. Test results SHALL be attributed per step: a step's verification status and its surfaced result entries SHALL reflect only results bound to that step's own verifying tests (plus whole-journey verifying tests), never results belonging to a sibling step.

*End* *Step-Level UAT Verification* | **Hash**: 8bf40a7c

---

## REQ-d00257: UAT-Scoped Traceability Report

**Level**: dev | **Status**: Draft | **Implements**: REQ-o00051

### Assertions

A. The `trace` command SHALL accept a `--dimension uat` flag that selects a UAT-scoped output mode.

B. The UAT report SHALL include only requirements that have at least one incoming VALIDATES edge, and for each such requirement SHALL list the validating journeys with their verification verdicts and the `uat_coverage`/`uat_verified` coverage tiers.

C. The UAT report SHALL exclude code implementation and test verification columns (`implemented`, `tested`, `verified`, `code_tested`, `lcov_tested`).

*End* *UAT-Scoped Traceability Report* | **Hash**: 2a8aab8b

---

## REQ-d00258: Reporting Surface Consistency

**Level**: dev | **Status**: Active | **Implements**: REQ-d00069

Reporting surfaces (trace, summary, MCP project summary, HTML viewer) SHALL present coverage using a single consistent vocabulary, aggregation, and tier-derived color scheme so that identical underlying data yields identical answers across surfaces.

### Assertions

A. All reporting surfaces (trace, summary, MCP project summary, HTML viewer) SHALL headline total coverage (REQ-d00069-N) and SHALL make the measures behind it available, so that a reader is never shown a figure without being able to see what evidence produced it.

B. The coverage display terms available to a reporting surface SHALL be Implemented, Tested, Passing, UAT Covered, and UAT Passed, and no other word SHALL denote a coverage dimension.

C. The CLI summary, the MCP project summary, and the viewer SHALL derive their coverage statistics from a single shared aggregation so identical questions receive identical answers.

D. Viewer coverage badge colors SHALL resolve from the coverage standing through the theme catalog by standing name — the same resolution for requirement dimension badges and per-*Assertion* badges — so a given standing is one color on every surface (full green, partial yellow, failing red), never through hard-coded color values and never recolored by the dimension's configured severity. A missing standing SHALL render red only when it is a required gap (its resolved severity is error) and grey otherwise. Severity SHALL govern combined-bucket dragging and the checks gate, not the badge color for the full, partial, and failing standings. The coverage standings SHALL appear in the viewer Legend.

E. Viewer coverage filters SHALL bucket requirements by tier semantics using the unified state names (full, partial, failing, missing), never by color string. The requirement-level line coverage cell SHALL NOT render a direct-attribution count for targets whose tooling provides only aggregate coverage.

F. A per-level `expects_validation` flag (default false) SHALL declare that requirements at that level are expected to have UAT validation (a USER_JOURNEY that `Validates:` them). When a level expects validation, a requirement of that level with no UAT coverage SHALL be a reported gap: flagged by the health `uat.coverage` check and listed under `gaps unvalidated`, and its viewer UAT badge SHALL render at error severity (red). When a level does not expect validation (the default), absent UAT SHALL be neither flagged by health, listed as a gap, nor badged in the viewer, and SHALL NOT drag the requirement's combined coverage bucket. The `uat.coverage` check SHALL count only requirements at expects_validation levels; when no level expects validation it SHALL pass trivially. All surfaces SHALL resolve this flag through a single shared helper rather than reading the level config independently.

G. The viewer SHALL assign each *Assertion* a semantic coverage *standing* (full, partial, failing, or missing) per coverage dimension, projected from the requirement's rollup metrics, so that if every *Assertion* is full on a dimension the requirement badge for that dimension reads full, and if any *Assertion* is failing the requirement dimension reports a failure. An *Assertion*'s standing SHALL read failing only when that *Assertion* itself has a failing result or verification for the dimension, not because a sibling *Assertion* covered by a different, non-failing test or journey failed; a failing test or journey attributes the failure to exactly the assertions it covers (its named targets, or every assertion when it covers the whole requirement). The standing SHALL be computed server-side and applied on initial render, without depending on a lazy client prefetch. Standing colors SHALL be resolved through the theme catalog by standing name (never hard-coded in the badge logic), the same decoupling severity colors use per D, so the standing-to-color association is configurable, and the standings SHALL appear in the viewer Legend. Per-*Assertion* pills SHALL honor `allow_indirect` when computing standing and SHALL render the unified `~` caveat (REQ-d00069-L) when applicable, though the direct-versus-indirect distinction SHALL NOT introduce a separate *Assertion* badge tier color.

H. The requirement-level coverage tier, the per-*Assertion* coverage standing, and the viewer filter bucket SHALL be drawn from one shared set of coverage state names — full, partial, failing, and missing — so that a given coverage condition maps to the same state word on every surface. The prior split of the full state into separate direct and indirect states SHALL NOT reappear as distinct tier states.

I. Tested SHALL be measured as the coverage of the implemented assertions, Passing as the coverage of the tested assertions, and UAT Passed as the coverage of the UAT-covered assertions, each chain measured within one measure so that a figure and its denominator are made of the same kind of evidence. A chained dimension whose denominator is empty SHALL read missing at neutral severity -- neither a reported gap nor error-colored -- and SHALL NOT drag the requirement's combined coverage bucket. A failing result on any assertion within a dimension's denominator SHALL render that dimension failing regardless of the covered fraction.

J. A surface SHALL NOT annotate a coverage figure with a caveat standing in for a measure it did not show. Where the difference between measures matters, the measures themselves SHALL be reported (REQ-d00069-L).

K. The coverage dimension labels SHALL be derived from a single configurable mapping from each coverage-conferring relationship to its display word, and every surface SHALL render dimension labels through that one mapping.

L. A per-status `expects_implementation` flag SHALL declare whether a requirement in that status is expected to have implementation; its default SHALL be derived from the status's role, so that active-role statuses expect implementation and others do not. When a status does not expect implementation, absent implementation SHALL be neither flagged as a gap, nor error-colored, nor counted against aggregate implemented coverage. All surfaces SHALL resolve this flag through a single shared helper, and it SHALL supersede the coverage-exclusion role when determining coverage inclusion.

M. A surface that reports which assertions need work (`gaps`, the health coverage checks, and the MCP uncovered-*Assertion* and test-coverage tools) SHALL read the immediate direct measure, so that an *Assertion* no citation names is reported however much whole-requirement evidence its requirement carries and however finished the requirements refining it are.

N. Passing SHALL count an *Assertion* only where a test declared against that *Assertion* returned a passing result, and no such test returned a failure. Evidence that no test named the *Assertion* -- line coverage of the code implementing it, or a result reached through the code rather than through the test -- SHALL NOT credit Passing.

O. Tested SHALL be reported with a breakdown of the assertions it counts into those that passed, those that failed, and those awaiting a result, and the three counts SHALL together account for every tested *Assertion*. The breakdown qualifies the Tested figure and SHALL NOT introduce a coverage dimension of its own.

### Rationale

The measures answer different questions, so the surfaces divide along the same line: what still needs doing is read from the immediate direct measure, because an *Assertion* no citation names is work whatever is happening below it, while a summary headlines total, because a reader asking how far along something is wants one number that counts each *Assertion* once.

A caveat marker was how a single figure used to admit it was standing in for two. With the measures published there is nothing for it to admit, and a marker that means "this number is partly something else" is worse than the something else being shown.

N draws the line between measuring a requirement's tests and measuring its code. A test that names an *Assertion* and passes is the only thing that says that *Assertion* passes; that a line of implementing code ran during some test run says the code was reached, which is a different fact about a different subject. Crediting the second as the first was a workaround for an inability that does not exist: a test can carry its `Verifies:` in every language the tool reads tests in, so an *Assertion* reported as passing without one is reporting an annotation nobody wrote. It also broke the chain -- Passing could credit an *Assertion* Tested did not, leaving the two figures incomparable and the excess unexplainable to a reader.

Line coverage is kept and reported in its own right, because how much of the implementation a run exercised is worth knowing. It answers about lines, not about assertions, and REQ-d00254-B keeps it there: a dimension beside the *Traceability* ones, never folded into them. Correlating executable lines with the assertions they implement is a coherent thing to want, and would remain a separate dimension if it were ever built.

O says a tested *Assertion* is always in exactly one of three states, and that a reader is told all three. Passing alone leaves the remainder ambiguous: an *Assertion* absent from it either failed or never returned a verdict, and those call for opposite actions -- one is a defect to fix, the other a run to complete or ingest. An estate can be entirely green on Passing while most of its tests never ran, and until the three are counted together nothing says so. They break Tested down rather than standing beside it, because each one is a tested *Assertion* seen from closer up, not a further dimension of coverage.

A reports how the estate is doing and M reports what is left to do; the two questions want different footings. Crediting whole-requirement evidence to every *Assertion* is defensible when summarising, because the evidence plausibly reaches them and the `~` marker says as much. It is not defensible when listing work, because an *Assertion* nobody has written evidence for is precisely what the list exists to surface — and on the generous footing it is the one thing the list can never show.

### Changelog

- 2026-08-17 | cc6480b3 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: headline total and publish the measures behind it (A); read work-lists from immediate direct evidence (M); retire the caveat marker that stood in for an unshown measure (J); chain each dimension within one measure (I)
- 2026-08-17 | c0428191 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-08-17 | 0f7c5cf2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | 2371dd44 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-11 | e0925092 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: state the display terms as the permitted set rather than a count (B); give Passing its own assertion, requiring one kind of evidence to indicate passing and neither to indicate failing (N); partition Tested into passed, failed and awaiting a result as a breakdown of it (O)
- 2026-08-17 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: Passing counts only a declared test's own passing result; line coverage credits no traceability dimension (N)
- 2026-08-11 | 5270fa45 | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: gap surfaces answer on the strict footing (M)
- 2026-07-31 | 5270fa45 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-07 | 90053f29 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-07 | 4767b41c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-07 | 172301f4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-06 | 06550baf | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-06 | dd54712c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-06 | 489752cd | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | c843c727 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-02 | be97c170 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: add missing changelog section

*End* *Reporting Surface Consistency* | **Hash**: cc6480b3

---

## REQ-d00274: Uncredited Coverage Evidence

**Level**: dev | **Status**: Active | **Implements**: REQ-p00015

Coverage dimensions are chained: one dimension counts only the assertions another dimension already covers. Evidence can therefore name an *Assertion* its dimension does not count, and so contribute to no answer the tool gives. This requirement obliges the tool to say that the evidence exists and reaches nothing, rather than let it disappear into a denominator it was never in.

### Assertions

A. Where evidence for a coverage dimension names an *Assertion* that the dimension does not count, the tool SHALL report the evidence, the *Assertion* it names, and the dimension the evidence does not reach.

B. Whether a dimension counts an *Assertion* SHALL be decided by the same rule that produces that dimension's figures under the project's own configuration, so that what is reported as uncredited is exactly what the project's coverage answers leave out.

C. The severity of the report SHALL be what the project configures for it, and SHALL be an error where the project configures nothing.

D. The report SHALL name the file and the line the evidence was written on, and SHALL distinguish evidence that only names the *Assertion* from evidence that also carries a result.

E. Reporting SHALL NOT alter what the evidence credits: the *Assertion* SHALL remain uncounted by that dimension, and the reported evidence SHALL NOT enter any coverage figure on either footing.

F. Where a dimension counts no *Assertion* of a requirement at all, the tool SHALL report that once for the requirement rather than once for each *Assertion* the evidence names.

### Rationale

An error default is the honest reading of what the condition means. A test that names an *Assertion* nothing implements is one of two defects: the implementation exists and its `Implements:` reference was never written, or the test is aimed at an *Assertion* it does not exercise. Neither is a matter of style, and both cost the estate the same thing — a requirement that reads as untested when it is tested, or as tested when it is not. A warning would leave the author to decide which of those two they are looking at without telling them there is a decision to make.

B ties the report to the project's own arithmetic rather than to a footing named once here, because the two must not be able to drift apart: a finding that an *Assertion* went uncounted is only true if that same *Assertion* is uncounted in the figures the project reads. Satisfying B is therefore a matter of reading one definition rather than restating it — a second statement of what a dimension counts is a second thing to keep in step, and the report would eventually contradict the numbers beside it. A dimension counting whole-requirement evidence is the ordinary case: an *Assertion* credited only that way is inside the dimension and a test naming it credits normally, so an estate that annotates implementation per requirement and tests per *Assertion* is not reported wholesale for a pattern the tool encourages elsewhere.

A and B divide the question between them. B settles what the dimension counts, which is the figures' business; A settles what the evidence names, which is not a matter of footing at all. Whole-requirement evidence names the requirement, and crediting it to every *Assertion* is the generous footing's doing rather than the author's, so an *Assertion* reached only that way was named by nobody and cannot be reported as though evidence were aimed at it. F is where such evidence is answered, against the requirement it did name.

This is not the question REQ-d00258-M answers. That assertion governs surfaces listing what remains to be done, which read the strict footing so an *Assertion* with no evidence naming it cannot hide behind its requirement's. Here the *Assertion* is not missing evidence; it has evidence that credits nothing.

### Changelog

- 2026-08-17 | b7624174 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: add missing changelog section

*End* *Uncredited Coverage Evidence* | **Hash**: b7624174

## REQ-d00276: Tests Outside the Requirement Estate

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00015

A test that no requirement claims still runs, and still passes or fails. Nothing about it reaches a coverage figure, because coverage answers for requirements and this test belongs to none. This requirement obliges the tool to report those tests as a set of their own, so that work happening outside the estate reads as work rather than as silence.

### Assertions

A. Tests that reach no requirement SHALL be reported together as their own set, and reporting them SHALL NOT credit or discredit any coverage figure.

B. The report SHALL say what each such test returned, distinguishing one that passed, one that failed, and one awaiting a result.

C. A failing test that reaches no requirement SHALL be reported at the severity the project configures for it, and SHALL be a warning where the project configures nothing.

D. The report SHALL name the file and the line each reported test was written at.

### Rationale

The two states this set holds are different problems wearing one shape. A test that fails and belongs to nothing is most often a defect in the test itself -- aimed at something that no longer exists, or never named what it was for -- and it cannot be found through any requirement, because it hangs off none. A test that passes and belongs to nothing is work the estate cannot see: either its `Verifies:` was never written, or it exercises something no requirement claims, and which of those it is only the author can say.

Neither belongs in a coverage figure, and putting them there is what the figures exist to avoid: a set of tests that reaches no requirement is exactly the population coverage is not measuring. Reporting them separately is the only way both facts stay true at once -- the figures stay about requirements, and the tests stop being invisible.

C defaults to warning rather than error because the condition is not always a defect. A repository legitimately carries tests for things it has not written requirements for. What is not legitimate is not knowing.

*End* *Tests Outside the Requirement Estate* | **Hash**: 922d1382
