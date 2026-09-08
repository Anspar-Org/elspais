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

D. Standard metrics keys SHALL include: is_uncommitted, is_moved, is_new, is_roadmap, display_filename, repo_prefix, implementation_files.

E. Custom metrics MAY be added by specific annotators without modifying TraceNode class.

### Rationale

Using metrics dict as the extension point enables adding new annotations without modifying the core TraceNode dataclass.

### Changelog

- 2026-08-19 | 83148e40 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 1c90d8fa | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 0073a9c3 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 0073a9c3 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Node Metrics as Extension Point* | **Hash**: 83148e40
---

## REQ-d00069: Indirect Coverage Source

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

The coverage annotation system SHALL support an INDIRECT coverage source for whole-requirement tests that do not target specific assertions.

### Assertions

A. `CoverageSource` enum SHALL include distinct test-evidence values -- `TEST_DIRECT` for an assertion-targeted `Verifies:` and `TEST_INDIRECT` for a whole-requirement `Verifies:` -- kept separate from implementation-evidence sources (`DIRECT`/`EXPLICIT`/`INFERRED`) so that a test that verifies an *Assertion* credits the Tested dimension only and never the Implemented dimension (REQ-d00084-D). (`INDIRECT` remains for the transitive CODE->TEST provenance path.)

B. A whole-requirement (assertion-less) reference SHALL credit every *Assertion* of the target requirement in its immediate indirect measure, at full value, and SHALL credit no immediate direct measure. This SHALL hold for `Verifies:` (Tested), `Implements:` on CODE (Implemented), `Implements:`/`Refines:` from a child requirement, and `Validates:` from a journey alike -- a reference that names no *Assertion* names them all equally, whatever keyword carried it. What such a reference conducts from a refining requirement is a separate question, answered by REQ-d00069-J.

C. `RollupMetrics` SHALL track `validated_with_indirect` count for assertions validated when including INDIRECT sources.

D. `RollupMetrics.finalize()` SHALL compute the Implemented dimension from implementation-evidence sources only (`DIRECT`/`EXPLICIT`/`INFERRED`); test-evidence sources (`TEST_DIRECT`/`TEST_INDIRECT`) SHALL populate the Tested dimension via `populate_test_dimensions()` and SHALL NOT be counted toward Implemented (REQ-d00084-D).

E. The coverage annotator SHALL emit `TEST_INDIRECT` contributions for all *Assertion* labels when a TEST (`Verifies:`) edge has empty `assertion_targets`, and `TEST_DIRECT` contributions for the named labels of an assertion-targeted TEST edge; both feed the Tested dimension, not Implemented (REQ-d00084-D).

F. When a whole-requirement test has passing results, the annotator SHALL count all assertions as validated for indirect mode.

G. A leaf *Assertion* SHALL be defined as any *Assertion* that has no `Refines:` child pointing at it. Leaf assertions can occur at any level or place in the hierarchy.

H. When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree with composite IDs (`declaring_id::original_id`), creating INSTANCE nodes linked to the declaring requirement via a SATISFIES edge. Coverage SHALL be computed through the standard coverage mechanism operating on the cloned nodes.

I. 100% coverage of a template instance SHALL be achieved when every leaf *Assertion* in the cloned template subtree (excluding N/A assertions) has at least one inbound coverage edge (`Implements:`, `Verifies:`, or `Validates:`) on its template original, consistent with the inherited-coverage rule (REQ-p00014-K).

J. A `Refines:` relationship SHALL NOT contribute coverage by itself; it SHALL conduct the coverage of the refining requirement to the assertions its own citation names -- the *Assertion* it names, or every *Assertion* of the requirement where it names only the requirement. Each measure SHALL conduct into the same measure, direct into direct and indirect into indirect, so that no measure is ever composed of another. The value conducted SHALL be the mean, in that measure, of the contributing requirements' own coverage, a requirement's coverage being the mean over its assertions, computed independently per dimension.

K. The system SHALL report coverage gaps on template instance nodes through the standard coverage mechanisms. Instance nodes are normal graph nodes and participate in existing health checks.

L. Coverage SHALL be measured on two independent axes per dimension. The first axis is what a citation named: *direct* where it named the *Assertion* it credits, *indirect* where it named only the requirement and is therefore attributed equally to every *Assertion* of it. The second axis is where the evidence sits: *immediate* where it is attached to what is being reported, and *rolled-up* where it is conducted from a refining requirement, in which case the first axis describes the refining requirement's own evidence. Each measure the axes yield SHALL be measured from the evidence itself and reported in its own right.

M. An *Assertion*'s immediate coverage SHALL record the strength of the evidence attached to it. That strength SHALL be whole wherever the evidence is whole, a citation either naming the *Assertion* or not; it MAY be partial where the evidence itself is partial, as a journey verified in part credits in proportion to its verification (REQ-d00255-C). Rolled-up coverage MAY likewise be fractional, being the mean of the coverage of the requirements refining it, so that a partially finished refinement reads as partially done.

N. Total coverage SHALL be reported as well, taken per *Assertion* as the greatest of that *Assertion*'s four measures, so that an *Assertion* covered more than one way is counted once and a requirement's total can never exceed its number of assertions.

### Rationale

Two questions are asked of coverage and they are not the same question. "What still needs doing here" is answered by what a citation names and where it is attached: an *Assertion* nobody has cited is work, however finished the requirements refining it may be. "How much of this is real" is answered by conduction: a requirement high in the tree is rarely cited by code at all, and what makes it true is the state of everything beneath it. One number cannot answer both, and a number that tries answers neither -- averaging an *Assertion*'s own citation together with the progress of a refinement made the figure move when nothing about that *Assertion* had changed, and let an *Assertion* nobody had cited read as fully covered because something below it was finished.

A measure conducts only into itself, because the two are not the same unit. Direct coverage counts assertions somebody wrote evidence against; indirect counts assertions reached by evidence written against their requirement. Adding one to the other, or letting a requirement covered only as a whole raise an *Assertion*'s direct figure one level up, would put a number under a description that is not true of it -- and would do so invisibly, since nothing downstream can tell which part of a summed figure came from where. What the refining citation names decides which assertions receive a conducted value; it does not decide which measure that value belongs to.

Separating the axes is what makes each measure sayable in a sentence. Direct and indirect say what a citation named; immediate and rolled-up say whether the evidence is attached here or conducted from below. Each of the four is reported in its own right, so no measure is defined as another's remainder, and each can independently be complete: a requirement whose assertions are each cited AND which is also cited as a whole is fully covered twice over, which the old nested pair could not express.

Total exists because a reader also wants one number, and taking it per *Assertion* as the greatest of that *Assertion*'s measures is what keeps it honest -- an *Assertion* covered three ways is still one covered *Assertion*, so a requirement's total can never exceed the number of assertions it has.

Whole-requirement tests (e.g., `test_implements_req_d00087` with no *Assertion* suffix) currently contribute zero *Assertion* coverage. Adding INDIRECT as a separate source allows a "progress indicator" view alongside strict *Traceability*, following the same pattern as INFERRED coverage for requirement-to-requirement relationships.

### Changelog

- 2026-08-19 | 665b798a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-18 | a8b306bc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-18 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: superseded — four published measures answer what the toggle asked; A was the only assertion ever built, and it fed a list nothing renders
- 2026-08-18 | a8b306bc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-18 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: scope the whole-requirement crediting rule to the immediate measures, leaving what it conducts to J (B)
- 2026-08-18 | bbad16d5 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-18 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: immediate coverage records the strength of the evidence attached, whole where the evidence is whole and partial where the evidence is (M)
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

*End* *Indirect Coverage Source* | **Hash**: 665b798a
---

## REQ-d00070: Indirect Coverage Toggle Display

**Level**: dev | **Status**: Superseded | **Implements**: REQ-p00006

This requirement offered a reader a choice between two coverage views because only one could be shown at a time. Coverage is no longer measured as a pair of nested footings to choose between: it is four independent measures, each reported in its own right, with a total taken per *Assertion* (REQ-d00069-L, REQ-d00069-N). A surface names the evidence each figure it shows counts (REQ-d00258-A), and a reader may ask for any measure in its own right (REQ-d00282-B), so the question the toggle asked is answered without asking the reader to pick a mode first.

The need its rationale named is met and not withdrawn: a strict *Traceability* view is the immediate direct measure, which is also what every work-listing surface answers on (REQ-d00258-M), and the progress-indicator view is the total.

### Assertions

A. <RETIRED> a per-row field derived from one of two nested footings. The measures a row reports are REQ-d00258-A, and what a work list answers on is REQ-d00258-M.

B. <RETIRED> an attribute carrying the toggle's second mode. There is no second mode.

C. <RETIRED> the toggle itself. With every measure published there is nothing to switch between.

D. <RETIRED> the toggle's default. There is no toggle.

E. <RETIRED> failures showing regardless of toggle state. That a failing *Assertion* reads failing whatever else credits it is REQ-d00258-G, which does not depend on a display mode.

### Rationale

The toggle was the shape a two-footing model forced: with one number on screen and a second hidden behind it, a control had to exist to swap them, and a reader had to know which mode they were in before they could read a figure. Publishing the measures removes both the swap and the question.

Retiring this cost no working behaviour. A alone was built -- a `TreeRow.coverage_indirect` field feeding a list no template iterates -- while B, C and D were never implemented at all, so the view has never had the toggle this requirement described.

- 2026-07-31 | a55fcb89 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 3e5b1766 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 3e5b1766 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Indirect Coverage Toggle Display* | **Hash**: eda3f31c
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

## REQ-d00272: Reference Fault Diagnosis

**Level**: dev | **Status**: Active | **Implements**: REQ-p00014-R
**Satisfies**: REQ-p00019

What a reference is composed of and what it produces are REQ-d00287's subject. This governs what the tool says about a reference afterwards: which class an item carries, which repository a name is attributed to, and how much of a defect may be named without guessing.

### Assertions

A. An item SHALL be reported under the class of the furthest stage of reading it reached.

B. <RETIRED> tested an item for a space. What an identifier is composed of is REQ-d00287-A, and what a name that no grammar accepts is attributed to is C.

C. An item no grammar of the federation accepts SHALL be attributed to the repository that declares the namespace it opens with, and to no repository where none declares it. That declaration SHALL decide the attribution, rather than the item's resemblance to any identifier pattern.

D. Where relaxations of the grammar make an item acceptable, the report SHALL name the smallest set of relaxations that does so.

E. <RETIRED> reported a reference followed by content the grammar did not account for. An identifier that declares no relationship is one condition wherever it sits, and O reports it.

F. <RETIRED> held that reading within an item never contributes a relationship. What produces one is REQ-d00287-E.

G. A *Traceability* keyword written in other than its canonical case SHALL be reported.

H. A *Traceability* keyword introducing no content SHALL be reported as having introduced none.

J. A *Traceability* keyword its file's kind does not admit SHALL be read and reported as a declaration that file may not make.

K. Where a reference list names the same target more than once, every instance SHALL be reported.

L. An item that both opens with an acceptable reference and reads as one differing by a relaxation SHALL be reported under the relaxation. Trailing content SHALL be reported only where no relaxation accounts for the item.

M. <RETIRED> named the characters an identifier cannot hold. What an identifier is composed of is REQ-d00287-A.

N. A reference written in an admitted spelling other than its canonical one SHALL be reported.

O. An identifier that declares no relationship SHALL be reported as undeclared, whether it opens a comment no *Traceability* keyword introduces or follows a reference list that has ended.

P. The report SHALL name a reference that did not read as an identifier malformed, and one that read as an identifier and named nothing the federation holds unresolved.

Q. <RETIRED> admitted trailing content that opened a comment. A reference list is composed of identifiers, separators and whitespace (REQ-d00287-B), so what follows one needs no admitting.

R. <RETIRED> reported trailing content that opened neither a reference nor a comment. Content that is not part of the list is reported under E.

### Rationale

Classes are only as useful as the rule that assigns them. Reading either reaches a stage or it does not, so a class is a fact about the item rather than a judgement of it, and the report says what was reached and stops there.

Attribution decided by a declared namespace separates three populations a project acts on differently: text that was never a reference, an estate identifier spelled wrongly, and a name belonging to a repository nobody configured. Resemblance cannot separate them, because a shape can always be argued with, while a declaration is a fact the federation holds. Collapsing any two sends an author to work that will not fix anything.

Minimality bounds diagnosis without a list of defects worth naming. The smallest set of relaxations is the one the input determines; a larger set that also succeeds contains a relaxation the input never asked for, and naming it describes a defect the author does not have.

Trailing content ranks beneath every named relaxation because an item opening with a valid reference can always be read as that reference plus whatever follows. Unranked, that reading accounts for every malformed item and leaves every diagnosis generic. The ranking governs what is reported and settles nothing about what binds.

A non-canonical form is a fact about the file rather than a defect in the reference. One canonical spelling exists for a keyword and for an identifier alike, and admitting more than one form is not writing more than one, so the report names the form that was written.

A keyword its file may not use is unmistakably a declaration, and reading it as prose leaves its author never told why the annotation did nothing. An identifier that declares nothing is the opposite case: nothing about it is malformed, and the message worth giving is that spelling it with a keyword would make it count.

Where such an identifier sits does not change what it is. One opening a comment and one left after a reference list has ended are the same fact -- a requirement named where naming it does nothing -- and they carry the same remedy. Reported apart they would need two severities for one decision, and a project that had reviewed its estate would have to silence both.

No test distinguishes a mention worth reporting from one worth ignoring. Any rule narrow enough to catch a missing separator also catches every deliberate mention of a requirement in prose, and a tool cannot read intent. So every instance is reported and the severity is the project's: listed while an estate is being reviewed, and withheld once it has been. A list naming a target twice is a list its author has lost track of, and reporting every instance rather than the first is what makes that visible.

This requirement concretizes the REQ-p00019 anti-pattern template for reference reading. Misattribution and double-counting are the classes this subsystem is most exposed to, and they are answered by one class per item, by attribution that follows what a repository declares, and by reporting every instance of a repeated target. A defect the tool could not determine is carried as the generic code rather than passed off as no defect at all.

### Changelog

- 2026-08-25 | 9f1a7a6a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-25 | e46b563e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-25 | 27a0182e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-24 | 3a1ca059 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-24 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-66: malformed and unresolved named against the failure classes; a comment ends a reference, and content that opens neither a reference nor a comment is reported
- 2026-08-16 | d01290ac | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-16 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: an identifier opening a comment with no keyword is reported as an undeclared relationship and produces none (O)
- 2026-08-16 | fadb924e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-16 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: Active — the five classes now reach `elspais checks` as `references.*`, each with its own severity, and G/N's keyword/identifier-form reporting is `references.keyword_form`
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: generalise the space test to any character no configuration can admit (M); one canonical spelling per identifier, reported not withheld (N)
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: a keyword its file may not use is read and refused rather than passed over (J); every instance of a repeated target is reported and none resolves (K); trailing content ranks beneath every named relaxation (L); any space character reaches the space test (M)
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: record how each REQ-p00019 class is answered for this subsystem — concretized, bound through the instance, or left visibly uncovered with its reason
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | Initial authoring: the rule assigning reference failure classes — the space and namespace tests, minimal relaxation, and reading within an item without binding from it

*End* *Reference Fault Diagnosis* | **Hash**: 9f1a7a6a
---

## REQ-d00287: Reading a Reference

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00014-R

A *Traceability* reference is read from the characters its author wrote, and the reading produces the relationship those characters name. This states what an identifier and a reference list are composed of, and which readings produce a relationship.

### Assertions

A. An identifier SHALL be composed of characters drawn from a set its grammar defines.

B. A reference list SHALL be composed of identifiers, separators, and whitespace.

C. A reference the grammar admits SHALL produce the relationship it names, in the canonical spelling and in every other spelling the configuration admits.

D. A *Traceability* keyword SHALL produce the relationships it introduces, in whatever case it is written.

E. A relationship SHALL exist only where its author spelled it. What is read to describe an item SHALL describe it and nothing more.

F. A reference list SHALL produce a relationship only for a target it names exactly once.

G. A *Traceability* keyword SHALL produce relationships only in a file whose kind admits it.

### Rationale

Reading a reference asks two questions: where the writing ends, and what the reading produces. Each is settled by stating what something is composed of, rather than by listing the cases that end it.

The character set and the list composition answer the first question completely. An identifier is made of the characters its set allows, so it ends at the first character that is not one of them; a list is made of identifiers, separators and whitespace, so it ends at the first content that is none of those. Every question about what may follow a reference is answered at once, for a space, a bracket, a word, and a character nobody has thought of yet. Enumerating terminators would state one property once per case and leave the estate a single unlisted character away from a reference with no end.

The remaining assertions answer the second question, and answer it narrowly. A file is read for two reasons -- to build the graph, and to describe what was found -- and the moment those readings share a result, a requirement is credited by evidence its author never cited. Description is therefore given no power to produce: an item examined closely enough to say what is wrong with it produces nothing by having been examined. Getting this backwards costs nothing visible, because a relationship that exists reads in every report exactly like one somebody wrote.

Case and padding are admitted rather than tolerated. A configuration that accepts an unpadded number or a lower-case keyword has said those forms are the same reference, and honouring one while dropping the other makes coverage depend on typing rather than on meaning. The two remaining assertions cover readings that look successful and are not: a list naming one target twice has lost track of itself, and choosing an instance resolves its author's confusion invisibly; a keyword outside its file's kind is unmistakably a declaration, and unmistakably one that file may not make.

### Changelog

- 2026-08-25 | - | - | Michael Lewis (<michael@anspar.org>) | Initial authoring: what a reference is composed of, and what a reading produces

*End* *Reading a Reference* | **Hash**: 0803d023

## REQ-d00254: Test Evidence: Attribution, Ingestion, and Coverage Crediting

**Level**: dev | **Status**: Active | **Implements**: REQ-o00051

Test verification evidence SHALL be attributed per test as it is scanned and ingested from configured test targets. Line coverage of implementation code is measured alongside it as its own dimension, answering a different question from *Traceability* and never standing in for it.

### Assertions

A. Where no result record binds to a test, that test SHALL contribute no verdict, and the assertions it declares SHALL be reported as awaiting a result. No verdict SHALL be inferred for a test from the results of other tests -- neither from the file it is written in nor from the application it belongs to.

B. The annotator SHALL compute a separate `lcov_tested` dimension by measuring the fraction of implementation lines (from `Implements:` edges) covered by execution data. When the fraction meets or exceeds the configured minimum, the relevant assertions SHALL be credited in `lcov_tested`. That dimension SHALL be reported in its own right and SHALL NOT credit any *Traceability* coverage dimension.

C. The configuration surface SHALL express test result and coverage ingestion via `[[scanning.test.targets]]` entries, each declaring how a target's results and coverage are produced (`command`, `groups`) and ingested (`reporter`, `results`, `coverage`, `match`, `classname`, `credit_coverage`, `min_coverage_fraction`). User documentation SHALL include a `test-targets` topic describing the target model, the available reporters, and a worked Flutter recipe.

D. A run of citations with no executable line between them SHALL attribute the lines of the function it is written above, or else the executable lines following it up to the next citation, the end of its enclosing function, or the end of the file, whichever comes first.

E. A reporter registry SHALL map each `reporter` format name to a parser and an input channel (`stdout` or `file`). The registry SHALL include a native `flutter test --machine` reporter that parses the machine JSON event stream into result records carrying each test's real source-file path (from the suite path), pass/fail/skip status, and line -- without an external JUnit converter.

F. For each configured target, the system SHALL obtain the reporter's output (captured from the command's stdout for stdout-channel reporters, or read from the `results` glob for file-channel reporters), build RESULT nodes carrying the real test-file path (`source_file`, repo-relative) and the target's `match` mode, and ingest the target's `coverage` file. Coverage crediting SHALL be derived from the targets' `credit_coverage`/`min_coverage_fraction`. File-channel results SHALL additionally record where each result was recorded — the results artifact's repo-relative path and, when derivable from the artifact (e.g. one JUnit `<testcase>` per line), the per-result line — as provenance distinct from the test's source path, and result links in reporting surfaces SHALL point at that artifact location.

G. Each target SHALL select its result-to-test matching via `match`: `source` SHALL bind each result at the most precise scope available — first step scope, when the result's recorded test name embeds exactly one journey-step reference (in the configured reference form) that resolves to a step whose verifying test(s) live in the result's source file; then test scope, resolving the result's real source-file path and `test()` source line to the specific test node at that `(path, line)`. A result that binds at neither scope SHALL credit nothing. `aggregate` SHALL derive the per-app green/red signal, which informs the line-coverage dimension only.

H. `elspais checks --run-tests` SHALL accept a `--targets` selector naming a subset of `[[scanning.test.targets]]` to execute; an unknown target name SHALL be an error, and an absent selector SHALL execute the targets a run executes when no selection is made (REQ-d00283). The same `--targets` flag on `summary`/`trace` SHALL mark provenance without executing anything.

I. A configured target a run did not execute, whose results are ingested from disk, SHALL be tagged *carried*; its verdict SHALL be honored faithfully (a carried failing result still flags the requirement as failing), and the `verified` dimension SHALL carry a `carried` flag orthogonal to its pass/fail tier so the matrix can render it as `(baseline)`.

J. In a selective run (a run that did not execute every configured target), a requirement with test references but zero result records SHALL render as not-run (`—`), distinct from a run-but-uncovered `0%`; in a full run zero results SHALL keep the existing rendering. Which of the two a run is SHALL follow from the targets it executed and not from how its selection was expressed.

K. For every configured test framework, the system SHALL bind each scanned test to its own identity within its source file and to that test's line extent, regardless of the framework's implementation language.

L. Where an external test-prescan command is configured, the system SHALL obtain per-test attribution for the candidate test files from that command.

M. The system SHALL exchange prescan data with a configured external test-prescan command by writing the candidate test file paths to the command's standard input and reading attribution records from its standard output, each record binding one test to its source file, its identity within that file, and its starting line.

N. Where an external test-prescan command returns attribution records for a scanned test file, the system SHALL bind that file's tests from those records in preference to the system's built-in attribution.

O. A line number a reporter records SHALL be read in the origin that reporter counts from. That origin SHALL be declared with the reporter and SHALL be overridable per target, and a recorded line SHALL be normalised to the numbering the tool uses for source lines before it is matched against a test or shown to a reader.

P. A file the tool cannot read in full SHALL still yield the results it could read.

Q. A result derived from a partial read SHALL be distinguishable from one derived from a complete read.

### Rationale

A line number means nothing without its origin, and producers disagree: the `line` attribute pytest writes into JUnit XML counts from zero, while the tool numbers source lines from one. Read as though they agreed, every such result missed the test it named by exactly one line and bound at file granularity instead -- which the file-granular inference then papered over, so the disagreement never surfaced as an error. Declaring the origin with the reporter puts the knowledge where the format is known rather than in each project's config, and the per-target override is for a producer that departs from its format's convention. Normalising once, at ingestion, is what keeps the rest of the system able to treat a line as a line -- to match on it, and to point a reader at it.

A test that returned no result is awaiting one, and nothing else is known about it. The inference this replaces -- reading a verdict for one test off the results of its neighbours, in the same file or the same application -- was built to work around test files that supposedly could not carry their own `Verifies:` annotation. They can, in every language the tool reads tests in, so the workaround bought nothing and cost the distinction: a deselected tier, an unbuilt target and a crashed runner all left their assertions reported as passing on the strength of tests that say nothing about them. Its failing half was worse, blaming an *Assertion* for a sibling test's failure, which REQ-d00258-G forbids one level down. Aggregate results still say something real about an application, and that is where they are read: the line-coverage dimension, which measures the code rather than the *Traceability*.

K states the outcome the scanning side owes the crediting side: without per-test identity and extent, the line-level dimensions computed here have nothing to intersect implementation ranges against, and a framework's tests can only ever be credited at file granularity. The obligation is deliberately language-neutral — it fixes what attribution must yield, not whether a given language earns built-in support or is served through an external command.

L, M and N cut the external route into a capability, a mechanism, and a precedence rule so each can change independently. L and M differ in kind: L survives a reimplementation that swaps the transport, while M memorializes the transport itself — file paths on standard input, attribution records on standard output. M is frozen not because it is an invariant but because it is a published integration point that third-party prescan scripts already implement, so breaking it breaks consumers outside this repository. Recording it as its own letter keeps that compatibility obligation targeted: a future transport change, or an added record field, edits M and leaves the capability and precedence untouched, and M can be retired without withdrawing either.

M binds each record to a starting line only. Extent on the external route is derived from the surrounding records rather than reported, so the derivation stays an implementation choice while K's extent obligation still holds for tests attributed that way.

N resolves per file, not per configuration, because both routes are routinely live in a single run: a project may configure a command that returns records for one file type while every other scanned test file falls to built-in attribution.

P and Q are about what a partial read produces, not about how it is announced. A file that will not parse in full is common and usually benign -- a coverage tool that cannot re-analyse a template still knows which of its lines ran -- and discarding what was read would lose evidence over a defect in a part of it.

Q is the half that bites. Evidence read in part yields a figure whose basis is not the one a reader assumes: lines that never ran are absent from the denominator, so a file reads as fully covered on the strength of a failure. Stating the distinction against a COMPLETE read rather than against no read at all is deliberate -- nobody acts differently on "could not read" versus "read in part", but a reader comparing a partial figure with a whole one acts on it constantly.

### Changelog

- 2026-09-06 | 4ec40251 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-06 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-80: one rule for what a citation attributes, bounded by the run, the next citation and the enclosing function (D)
- 2026-09-04 | 4374955e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-04 | 6ca69e33 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-04 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-80: block attribution follows from an unknown function extent, not from a one-line comment (D)
- 2026-08-25 | 8264ac9a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-24 | e16eaff7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-24 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-66: an artifact ingestion could not read is reported, and a partial read is told apart from a total one
- 2026-08-22 | 00518ba3 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-22 | cbc2e2cd | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-22 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-74: a run with no selection executes a named set a project can narrow rather than every configured target; whether a run counts as selective follows from the targets it executed rather than from how it was asked; the target model carries the two settings that make that set and a recorded identity's form declarable (C, H, I, J)
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

*End* *Test Evidence: Attribution, Ingestion, and Coverage Crediting* | **Hash**: 4ec40251

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

A. The *Traceability* report SHALL offer a named default set of values stating what user-acceptance evidence a requirement carries.

B. That set SHALL state, for each requirement, the journeys validating it with their verification verdicts, and the requirement's UAT coverage figures.

C. That set SHALL state no figure for implementation, for test verification, or for line coverage.

### Rationale

A reader asking what a journey has established is asking about a different kind of evidence from a reader asking what a test has, and a named set of values is how a report answers one question rather than both at once.

The set states no implementation or test figure because those answer the other question. It is a set of values and nothing more: it does not decide which requirements the report is about. A report of user-acceptance evidence over every requirement tells a reader which ones have none, which is usually what they came to find out; and selecting requirements by whether a journey validates them is a question about requirements, which REQ-d00282-H keeps out of a set of values and REQ-d00278 is where it would belong.

*End* *UAT-Scoped Traceability Report* | **Hash**: 1ea68210

---

## REQ-d00258: Reporting Surface Consistency

**Level**: dev | **Status**: Active | **Implements**: REQ-d00069

Reporting surfaces (trace, summary, MCP project summary, HTML viewer) SHALL present coverage using a single consistent vocabulary, aggregation, and tier-derived color scheme so that identical underlying data yields identical answers across surfaces.

### Assertions

A. A surface reporting a coverage figure SHALL name the evidence the figure counts, so that a reader is never shown a figure without being told what produced it.

B. <RETIRED> a fixed set of display words, which REQ-d00258-K had already made configurable per project. Each dimension is now stated on its own in REQ-d00277, so one can be added, redefined or withdrawn without rewriting a list.

C. A surface reporting a coverage figure or reaching a coverage verdict SHALL derive it from the one shared aggregation, so that two surfaces asked the same question give the same answer.

D. Viewer coverage badge colors SHALL resolve from the coverage standing through the theme catalog by standing name — the same resolution for requirement dimension badges and per-*Assertion* badges — so a given standing is one color on every surface (full green, partial yellow, failing red), never through hard-coded color values and never recolored by the dimension's configured severity. A missing standing SHALL render red only when it is a required gap (its resolved severity is error) and grey otherwise. Severity SHALL govern combined-bucket dragging and the checks gate, not the badge color for the full, partial, and failing standings. The coverage standings SHALL appear in the viewer Legend.

E. Viewer coverage filters SHALL bucket requirements by tier semantics using the unified state names (full, partial, failing, missing), never by color string. The requirement-level line coverage cell SHALL NOT render a direct-attribution count for targets whose tooling provides only aggregate coverage.

F. A per-level `expects_validation` flag (default false) SHALL declare that requirements at that level are expected to have UAT validation (a USER_JOURNEY that `Validates:` them). When a level expects validation, a requirement of that level with no UAT coverage SHALL be a reported gap: flagged by the health `uat.coverage` check and listed under `gaps unvalidated`, and its viewer UAT badge SHALL render at error severity (red). When a level does not expect validation (the default), absent UAT SHALL be neither flagged by health, listed as a gap, nor badged in the viewer, and SHALL NOT drag the requirement's combined coverage bucket. The `uat.coverage` check SHALL count only requirements at expects_validation levels; when no level expects validation it SHALL pass trivially. All surfaces SHALL resolve this flag through a single shared helper rather than reading the level config independently.

G. The viewer SHALL assign each *Assertion* a semantic coverage *standing* (full, partial, failing, or missing) per coverage dimension, projected from the requirement's rollup metrics, so that if every *Assertion* is full on a dimension the requirement badge for that dimension reads full, and if any *Assertion* is failing the requirement dimension reports a failure. An *Assertion*'s standing SHALL read failing only when that *Assertion* itself has a failing result or verification for the dimension, not because a sibling *Assertion* covered by a different, non-failing test or journey failed; a failing test or journey attributes the failure to exactly the assertions it covers (its named targets, or every assertion when it covers the whole requirement). The standing SHALL be computed server-side and applied on initial render, without depending on a lazy client prefetch. Standing colors SHALL be resolved through the theme catalog by standing name (never hard-coded in the badge logic), the same decoupling severity colors use per D, so the standing-to-color association is configurable, and the standings SHALL appear in the viewer Legend. A per-*Assertion* pill SHALL make the measures behind its standing available to a reader, and SHALL NOT carry a caveat standing in for a measure it does not show (REQ-d00258-J). The distinction between the measures SHALL NOT introduce a separate *Assertion* badge tier color.

H. The requirement-level coverage tier, the per-*Assertion* coverage standing, and the viewer filter bucket SHALL be drawn from one shared set of coverage state names — full, partial, failing, and missing — so that a given coverage condition maps to the same state word on every surface. The prior split of the full state into separate direct and indirect states SHALL NOT reappear as distinct tier states.

I. A chained dimension (REQ-d00277) SHALL be measured within one measure, so that a figure and its denominator are made of the same kind of evidence. A chained dimension whose denominator is empty SHALL read missing at neutral severity -- neither a reported gap nor error-colored -- and SHALL NOT drag the requirement's combined coverage bucket. A failing result on any assertion within a dimension's denominator SHALL render that dimension failing regardless of the covered fraction.

J. A surface SHALL NOT annotate a coverage figure with a caveat standing in for a measure it did not show. Where the difference between measures matters, the measures themselves SHALL be reported (REQ-d00069-L).

K. The coverage dimension labels and the labels of the measures behind them SHALL each be derived from a single configurable mapping — from each coverage-conferring relationship to its display word, and from each measure to its display word — and every surface SHALL render those labels through those mappings.

L. A per-status `expects_implementation` flag SHALL declare whether a requirement in that status is expected to have implementation; its default SHALL be derived from the status's role, so that active-role statuses expect implementation and others do not. When a status does not expect implementation, absent implementation SHALL be neither flagged as a gap, nor error-colored, nor counted against aggregate implemented coverage. All surfaces SHALL resolve this flag through a single shared helper, and it SHALL supersede the coverage-exclusion role when determining coverage inclusion.

M. A surface reporting which assertions need work SHALL read the immediate direct measure, so that an *Assertion* no citation names is reported however much whole-requirement evidence its requirement carries and however finished the requirements refining it are.

N. <RETIRED> moved to REQ-d00277-C, where every coverage dimension is defined. Two authorities for what Passing counts is the duplication that split exists to remove.

O. Tested SHALL be reported with a breakdown of the assertions it counts into those that passed, those that failed, and those awaiting a result, and the three counts SHALL together account for every tested *Assertion*. The breakdown qualifies the Tested figure and SHALL NOT introduce a coverage dimension of its own.

P. A coverage figure a surface states for a group of requirements SHALL be the credit and the assertions of that group each summed, so that a group is measured over the same assertions its members are.

### Rationale

P settles what a figure over many requirements means, because there is more than one defensible answer and they disagree. Summing the credit and the assertions weights each requirement by how much it obliges; averaging the members' own proportions weights each requirement equally, and answers how far along the typical requirement is rather than how far along the work is. Both are worth knowing and only one can be the figure a surface states unasked, or two surfaces answer the same question differently -- which is the divergence this requirement exists to prevent. Summing is the one chosen because it is what a per-*Assertion* credit already is: REQ-d00069-M makes coverage a real number so that partial evidence counts in proportion, and summing those proportions keeps a group's figure made of the same evidence as its members'. A surface that later offers the other has to name which it states, since the two share a shape and not a meaning.

The measures answer different questions, so the surfaces divide along the same line: what still needs doing is read from the immediate direct measure, because an *Assertion* no citation names is work whatever is happening below it, while a summary headlines total, because a reader asking how far along something is wants one number that counts each *Assertion* once.

A caveat marker was how a single figure used to admit it was standing in for two. With the measures published there is nothing for it to admit, and a marker that means "this number is partly something else" is worse than the something else being shown.

N draws the line between measuring a requirement's tests and measuring its code. A test that names an *Assertion* and passes is the only thing that says that *Assertion* passes; that a line of implementing code ran during some test run says the code was reached, which is a different fact about a different subject. Crediting the second as the first was a workaround for an inability that does not exist: a test can carry its `Verifies:` in every language the tool reads tests in, so an *Assertion* reported as passing without one is reporting an annotation nobody wrote. It also broke the chain -- Passing could credit an *Assertion* Tested did not, leaving the two figures incomparable and the excess unexplainable to a reader.

Line coverage is kept and reported in its own right, because how much of the implementation a run exercised is worth knowing. It answers about lines, not about assertions, and REQ-d00254-B keeps it there: a dimension beside the *Traceability* ones, never folded into them. Correlating executable lines with the assertions they implement is a coherent thing to want, and would remain a separate dimension if it were ever built.

O says a tested *Assertion* is always in exactly one of three states, and that a reader is told all three. Passing alone leaves the remainder ambiguous: an *Assertion* absent from it either failed or never returned a verdict, and those call for opposite actions -- one is a defect to fix, the other a run to complete or ingest. An estate can be entirely green on Passing while most of its tests never ran, and until the three are counted together nothing says so. They break Tested down rather than standing beside it, because each one is a tested *Assertion* seen from closer up, not a further dimension of coverage.

A reports how the estate is doing and M reports what is left to do; the two questions want different measures. Crediting whole-requirement evidence to every *Assertion* is defensible when summarising, because the evidence plausibly reaches them and the indirect measures are published beside the total, so a reader can see how much of it there is. It is not defensible when listing work, because an *Assertion* nobody has written evidence for is precisely what the list exists to surface — and on a measure that credits whole-requirement evidence it is the one thing the list can never show.

### Changelog

- 2026-08-24 | 15129897 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-21 | 6c978321 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-21 | 24015cbc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-19 | 879012b7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-18 | e6e17ee9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-18 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: a per-assertion pill shows the measures behind its standing rather than a caveat standing in for one (G)
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

*End* *Reporting Surface Consistency* | **Hash**: 15129897

---

## REQ-d00274: Uncredited Coverage Evidence

**Level**: dev | **Status**: Active | **Implements**: REQ-p00015

Coverage dimensions are chained: one dimension counts only the assertions another dimension already covers. Evidence can therefore name an *Assertion* its dimension does not count, and so contribute to no answer the tool gives. This requirement obliges the tool to say that the evidence exists and reaches nothing, rather than let it disappear into a denominator it was never in.

### Assertions

A. Where evidence for a coverage dimension names an *Assertion* that the dimension does not count, the tool SHALL report the evidence, the *Assertion* it names, and the dimension the evidence does not reach.

B. Whether a dimension counts an *Assertion* SHALL be decided by the same rule that produces that dimension's figures under the project's own configuration, so that what is reported as uncredited is exactly what the project's coverage answers leave out.

C. The severity of the report SHALL be what the project configures for it, and SHALL be an error where the project configures nothing.

D. The report SHALL name the file and the line the evidence was written on, and SHALL distinguish evidence that only names the *Assertion* from evidence that also carries a result.

E. Reporting SHALL NOT alter what the evidence credits: the *Assertion* SHALL remain uncounted by that dimension, and the reported evidence SHALL NOT enter any coverage figure on any measure.

F. Where a dimension counts no *Assertion* of a requirement at all, the tool SHALL report that once for the requirement rather than once for each *Assertion* the evidence names.

G. A citation in a scanned test file that binds to no test SHALL be reported.

H. A citation that binds to no test SHALL contribute no coverage to the assertions it names.

### Rationale

An error default is the honest reading of what the condition means. A test that names an *Assertion* nothing implements is one of two defects: the implementation exists and its `Implements:` reference was never written, or the test is aimed at an *Assertion* it does not exercise. Neither is a matter of style, and both cost the estate the same thing — a requirement that reads as untested when it is tested, or as tested when it is not. A warning would leave the author to decide which of those two they are looking at without telling them there is a decision to make.

B ties the report to the project's own arithmetic rather than to a measure named once here, because the two must not be able to drift apart: a finding that an *Assertion* went uncounted is only true if that same *Assertion* is uncounted in the figures the project reads. Satisfying B is therefore a matter of reading one definition rather than restating it — a second statement of what a dimension counts is a second thing to keep in step, and the report would eventually contradict the numbers beside it. A dimension counting whole-requirement evidence is the ordinary case: an *Assertion* credited only that way is inside the dimension and a test naming it credits normally, so an estate that annotates implementation per requirement and tests per *Assertion* is not reported wholesale for a pattern the tool encourages elsewhere.

A and B divide the question between them. B settles what the dimension counts, which is the figures' business; A settles what the evidence names, which is not a matter of measure at all. Whole-requirement evidence names the requirement, and crediting it to every *Assertion* is the indirect measures' doing rather than the author's, so an *Assertion* reached only that way was named by nobody and cannot be reported as though evidence were aimed at it. F is where such evidence is answered, against the requirement it did name.

This is not the question REQ-d00258-M answers. That assertion governs surfaces listing what remains to be done, which read the immediate direct measure so an *Assertion* with no evidence naming it cannot hide behind its requirement's. Here the *Assertion* is not missing evidence; it has evidence that credits nothing.

### Changelog

- 2026-08-25 | 01a8f7d7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-24 | b29be09f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-24 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-66: a citation binding to no test is reported and credits nothing
- 2026-08-18 | 2f1e6599 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | b7624174 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: add missing changelog section

*End* *Uncredited Coverage Evidence* | **Hash**: 01a8f7d7

## REQ-d00276: Tests Outside the Requirement Estate

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00015

A test that no requirement claims still runs, and still passes or fails. Nothing about it reaches a coverage figure, because coverage answers for requirements and this test belongs to none. This requirement obliges the tool to report those tests as a set of their own, so that work happening outside the estate reads as work rather than as silence.

### Assertions

A. Tests that reach no requirement SHALL be reported together as their own set, and reporting them SHALL NOT credit or discredit any coverage figure.

B. The report SHALL say what each such test returned, distinguishing one that passed, one that failed, and one awaiting a result.

C. A failing test that reaches no requirement SHALL be reported, and SHALL be a warning where the project configures nothing.

D. The report SHALL name the file and the line each reported test was written at.

E. A scanned test file that no configured target can execute SHALL be reported.

### Rationale

The two states this set holds are different problems wearing one shape. A test that fails and belongs to nothing is most often a defect in the test itself -- aimed at something that no longer exists, or never named what it was for -- and it cannot be found through any requirement, because it hangs off none. A test that passes and belongs to nothing is work the estate cannot see: either its `Verifies:` was never written, or it exercises something no requirement claims, and which of those it is only the author can say.

Neither belongs in a coverage figure, and putting them there is what the figures exist to avoid: a set of tests that reaches no requirement is exactly the population coverage is not measuring. Reporting them separately is the only way both facts stay true at once -- the figures stay about requirements, and the tests stop being invisible.

C defaults to warning rather than error because the condition is not always a defect. A repository legitimately carries tests for things it has not written requirements for. What is not legitimate is not knowing.

### Changelog

- 2026-08-24 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-66: a scanned test file nothing configured can run is reported

*End* *Tests Outside the Requirement Estate* | **Hash**: ca4cd1fc

---

## REQ-d00277: Coverage Dimensions

**Level**: dev | **Status**: Active | **Implements**: REQ-d00069

Each coverage dimension answers a different question about a requirement, conferred by a different relationship and read for a different purpose. They are stated one at a time so that one can be added, redefined or withdrawn without disturbing the others.

### Assertions

A. Implemented SHALL count an *Assertion* credited by an `Implements:` citation, by coverage conducted to it, or inherited through an INSTANCE or INTEGRATES relationship, measured over every *Assertion* of the requirement.

B. Tested SHALL count an *Assertion* credited by a `Verifies:` citation, measured over the assertions Implemented counts.

C. Passing SHALL count only an *Assertion* where a test declared against that *Assertion* returned a passing result and no such test returned a failure, measured over the assertions Tested counts.

D. UAT Covered SHALL count an *Assertion* a journey `Validates:`, measured over every *Assertion* of the requirement.

E. UAT Passed SHALL count an *Assertion* whose validating journey returned a passing result, measured over the assertions UAT Covered counts.

### Rationale

A dimension is a question, not a label. Implemented asks whether anything was built; Tested whether what was built is exercised; Passing whether the exercise succeeded. UAT Covered and UAT Passed ask that same pair of a user journey. A reader choosing between them is choosing which question to ask, so each is stated on its own and none is defined as a variation of another.

The denominator is part of the definition. Tested measured over every *Assertion* would report an estate as untested when it is merely unbuilt, and those two call for different work.

A single failure is decisive for the *Assertion* it lands on: C requires that no declared test returned a failure, because a passing sibling test does not retract a failure a test reported. How a failure reaches the requirement as a whole is a reporting rule, not a definition, and stays with the surfaces (REQ-d00258-I).

The magnitude a dimension credits is governed by REQ-d00069-M, so a journey verified in part credits in proportion without any dimension restating the rule.

The word each dimension is reported under is configurable (REQ-d00258-K); the names used here are the defaults, not the definitions.

### Changelog

- 2026-08-19 | b097dcd7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash, add missing changelog section

*End* *Coverage Dimensions* | **Hash**: b097dcd7

---

## REQ-d00283: Test Target Groups

**Level**: dev | **Status**: Draft | **Implements**: REQ-o00051

A project's test targets are not alike in what it costs to run them. Some are a
compilation away; others need a live backend, a device farm, or an account
somebody pays for. Groups are how a project says which of its targets a run is
about.

### Assertions

A. Every test target SHALL belong to one or more groups.

B. Every test target SHALL belong to the group `all`.

C. A test target that claims no other group SHALL belong to the group `default`.

D. A run that selects no group SHALL execute the targets of the group `default`.

E. A run that selects one or more groups SHALL execute only targets belonging to those groups.

F. A test target SHALL be able to claim any declared group, and SHALL NOT claim a name no declaration and no reservation defines.

G. A project SHALL be able to declare any number of groups, each declared with a keyword unique among every group name, the reserved names included, and a description of what the group is for.

H. A run selecting a name no declaration and no reservation defines SHALL be refused rather than resolved to no targets.

I. Each selector a run states SHALL narrow the targets it executes.

### Rationale

The cost of a target is not something the tool can read off its configuration, and it is not the tool's judgement to make. What the tool can do is let the project say it once, in a place a reader of the configuration will find, and then honour it. A description is required with each declaration for that reason: a group called `slow` tells a newcomer nothing about whether their change should have run it, and the declaration is the only place that explanation has to live.

B makes `all` a membership rather than a selector, so E needs no exception for it: selecting `all` selects every target by the same rule that selects any other group, and nothing has to know that one name means something different from the rest.

C is what keeps this addition from changing what an existing project's run does. A project that declares no groups has every target in `default`, so the targets a bare run executes are the targets it executed before. The capability arrives inert and is switched on by declaring a group, which is the only way to introduce a selection mechanism into an estate where reports are already committed.

F and H are the same discipline reached from the two directions a name arrives from. A group that exists because a target claimed it can never be wrong, so a misspelling in configuration silently creates a group nobody selects and quietly removes that target from every run. A selection that resolves to nothing is indistinguishable, in the report it produces, from a selection whose targets all passed — and the second is the reading a reader will reach for. In both directions the undefined name is refused, because refusal is the only answer neither can be misread.

G requires uniqueness across every group name rather than across the declared ones, which is what bars a project from declaring `all` or `default`. Their meanings are fixed by B, C and D; a project able to attach its own description to either could describe something the tool does not do, and a reader would have no way to tell which was true.

I settles what two selectors mean together. Both name what a run is to execute, so a run stating both is describing its subject twice, and the targets it executes are those both descriptions admit. The alternative — each selector adding to the set — would make naming a target *widen* a run that named a group, so a caller narrowing their invocation would watch it grow.

*End* *Test Target Groups* | **Hash**: bc95d36b

## REQ-d00284: How a Result Names Its Test

**Level**: dev | **Status**: Draft | **Implements**: REQ-o00051

A results file says which test produced each result. Some name the test's source
file; others give only a name whose meaning depends on the tool that wrote the
file. This says how that name is read.

### Assertions

A. Each test target SHALL declare how its results name the test that produced them.

B. A result SHALL be matched to a test only where its name picks out exactly one test scanned for that target.

C. A result matched to no test SHALL be reported, saying whether its name picked out no test or more than one.

### Rationale

When a results file names the test's source file there is nothing to work out. When it does not, all the tool has is a name -- `epistaxis-diary.spec.ts`, say, or `tests.test_login` -- and what that name refers to depends entirely on the tool that wrote it. The tool currently assumes a Python module path. That is right for one producer and wrong for every other, and it fails quietly: the name matches no test, the result is dropped, and the coverage figure that follows reads zero. Accurate about what the tool could read, and misleading about what was actually run.

A asks the project to say what the name is rather than leaving the tool to guess. Which form a producer writes is a fixed fact about that producer, so it only has to be said once. The reporter says what its format usually carries and a target may say otherwise, because several producers write the same format and disagree about what goes in that field. This is the same arrangement REQ-d00254-O makes for the line numbers a producer counts.

B keeps the match strict. The tests it looks among are the ones scanned for that target: a name matching a file some other target scans says nothing about where this result came from. Requiring a single match matters because a result attached to the wrong test looks exactly like one attached to the right test in every figure afterwards. It also rules out trying a second reading when the first finds nothing, which would rescue some results and misattach others with no way to tell the two apart later.

C makes the failure visible. A result matching nothing is not an error where it happens, so without C nothing mentions it and the only sign is a coverage figure lower than expected. Saying whether the name matched nothing or matched several tells an author which problem they have: a name pointing at a file that is not there, or two files sharing one name.

*End* *How a Result Names Its Test* | **Hash**: 7baae0b0

## REQ-d00281: Level Vocabulary of a Reported Graph

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00015

A report that groups requirements by level draws those groups from somewhere, and the graph a report is computed over is not the same thing as the configuration it was invoked under. A federated graph holds every member's requirements, and the levels they carry are the union of the members' vocabularies. This requirement fixes which of the two the grouping follows.

### Assertions

A. Every level carried by a requirement a report includes SHALL form a group in that report.

B. Every requirement a report includes SHALL fall in exactly one of that report's groups.

C. Whether the configuration a report is produced under defines a requirement's level SHALL NOT decide whether that requirement is counted in a figure the report aggregates.

D. Where a requirement carries a level the configuration a report is produced under does not define, the tool SHALL report that requirement together with the level it carries.

E. A group formed from a level the configuration does not define SHALL be ordered after the groups formed from levels it does define.

### Rationale

The subject of a report is the graph, and in a federation that graph is an assembly: each member declares its own levels, and every requirement any member holds is part of what the report is about. Forming the groups from the invoking configuration instead makes the report's shape a fact about who asked rather than about what was asked, so a member whose vocabulary differs from the asker's contributes requirements the report has nowhere to put. Drawing the groups from the requirements themselves is what makes one graph yield one answer whoever runs the report, and it is the same settlement REQ-d00251-L reaches for identifiers, reached here for the vocabulary a report is organised by.

A and B are the two halves of accounting for every requirement, and neither is sufficient alone. A says no requirement's level is missing a group; B says each requirement lands in one group and is not divided between several or counted in two. Without B a report could satisfy A and still misstate its totals; without A a requirement can be complete inside a group that was never formed, which is a completeness nothing checks. Stating both is what lets a reader add the groups up and get the report back.

C is where the asymmetry between a requirement's level and its status is deliberate. A status carries a role the project assigns it, and that role is a statement about whether the obligation is live — a withdrawn requirement genuinely should not drag a coverage figure, so status decides membership in that figure. A level says who the requirement is for and at what altitude it sits; it makes no claim about whether the obligation is owed. A requirement at a level this configuration happens not to define is real work somebody owes, and dropping it flatters every figure it would have lowered. C bars the definedness of the level from deciding the question, which leaves a reader's own selection free to narrow a report deliberately — a narrowing REQ-p00084 governs, and which discloses itself.

D is REQ-p00015-A reached by a second route. Content excluded from an answer is reportable whether it was refused admission or admitted and then passed over, because the reader cannot tell the two apart from the answer they are holding. It also catches the case no comparison between configurations would: a single repository where a level was misspelled on a requirement, or removed from the configuration while requirements still carry it, has no second configuration to differ from, and the requirements simply stop being counted. Naming the requirement and the level it carries is what turns that into something an author can act on, rather than a figure that quietly moved.

E settles an ordering that would otherwise be decided independently by each surface, and decided differently. The levels a project defines are ordered by the ranks it gave them; a level it did not define has no rank to be ordered by, and inventing one would put it somewhere a reader has no way to predict. Placing such groups after the ranked ones keeps the familiar shape of a report intact and gathers what the configuration does not account for in one place, where D's report is about the same requirements.

*End* *Level Vocabulary of a Reported Graph* | **Hash**: 4bde246d
