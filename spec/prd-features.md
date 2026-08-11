# Feature Product Requirements

# REQ-p00005: Multi-Repository Requirements

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001
**Refines**: REQ-p00001

## Rationale

Large organizations often split requirements across multiple repositories:

- A **core** repository containing product-level requirements
- **Associated** repositories for subsystems, services, or components
- **Sponsor** repositories for customer-specific or partner-specific requirements

Each repository maintains its own spec directory, but requirements must reference and implement requirements from other repositories. The tool must validate these cross-repository links and generate combined *Traceability* matrices.

This architecture supports:

- Independent versioning of subsystem specifications
- Access control (not everyone needs access to all specs)
- Modular development with clear interface contracts
- Combined views for regulatory submissions

CI/CD pipelines and diverse developer environments mean associated repositories may be located at different filesystem paths on each machine. Rather than requiring each environment to maintain a separate override file, the tool treats all cross-repository resolution as a local path concern: CI systems clone repos and then configure paths via the CLI, developers set paths to match their local directory layout, and the associated repository's own configuration file declares its identity (project type, namespace prefix). This keeps repository topology — which repos exist and where they are hosted — as a CI/infrastructure concern outside the tool, while the tool focuses on discovering and validating whatever local repos it is pointed at.

Pattern compatibility is part of configuration validity: any two valid repository configurations must compose into a federation without contested identifiers, so a conflict surfaces as a build-time configuration error (assertion G) rather than as misattributed references.

## Assertions

A. The tool SHALL support requirement references across repository boundaries using configurable namespace prefixes.

B. The tool SHALL generate combined **Traceability** matrices spanning multiple repositories.

C. The tool SHALL support CLI-based configuration of associate repository paths so that external systems can register associates without manually editing configuration files.

D. The tool SHALL discover an associated repository's identity — including its project type and namespace prefix — by reading that repository's own configuration file.

E. The tool SHALL report a clear configuration error when a configured associate path does not exist or does not contain a valid associated-repository configuration.

F. The tool SHALL resolve relative associate paths from the canonical (non-worktree) repository root so that cross-repository paths remain valid when working from git worktrees.

G. If the identifier-pattern configurations of two repositories in a federation can each claim the same identifier, then the tool SHALL report the pattern conflict when the federation is built.

## Changelog

- 2026-08-02 | de05471c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: federated pattern compatibility — two repos whose patterns can claim the same identifier is a build-time configuration conflict (G)
- 2026-07-31 | 3a6f18bd | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-03-30 | c3303546 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-03-30 | f935e564 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Multi-Repository Requirements* | **Hash**: de05471c
---

# REQ-p00081: Org-Wide Requirement Visibility

**Level**: prd | **Status**: Draft | **Implements**: REQ-p00005
**Satisfies**: REQ-p00019

## Rationale

An organization keeps cross-cutting requirements — CI conventions, secrets handling, storage rules, sponsor abstraction — in a policy repository that is *meta* to the repositories it governs. An author working in a governed repository needs those obligations surfaced without having to know they exist before looking for them. Measured against the live estate (2026-07-29; method preserved in the internal archive): of ~620 *Traceability* references across the organization, 2 targeted a cross-cutting requirement, 0 resolved, and no repository federated the policy repository — so "0.3% referencing" could not be distinguished from "nobody knows these apply".

This requirement states the visibility invariants (V1–V3, H2). The mechanisms that realize them — the per-user workspace registry, role model, and shadowing rules — are specified at the dev level and may change without weakening these obligations.

The discovery surface declares `Satisfies:` against the REQ-p00019 anti-pattern template; assertions B, C, D, and F are its concretizations of the template's omission, staleness, and verdict-integrity classes for workspace discovery, where an undisclosed narrowing of scope makes an empty result indistinguishable from an incomplete search.

## Assertions

A. The tool SHALL make a requirement authored in any repository of the caller's workspace discoverable from every repository of that workspace, without the caller naming the repository that owns it.

B. The tool SHALL NOT narrow workspace discovery scope in response to an omission or error in an individual member repository's own configuration.

C. The tool SHALL disclose, with every discovery result, the repository that owns the result and the freshness of the content it was computed from — a live working copy, or a baseline captured at a disclosed time.

D. When a repository in the resolved discovery scope cannot be loaded, the tool SHALL report the narrowed scope — identifying the repository and the cause — on the same surface that reports the results, so that an empty result is distinguishable from an incomplete search.

E. When invoked from a location that is inside a declared workspace but not inside any repository, the tool SHALL serve the workspace view rather than failing for want of a repository.

F. Every surface that reports results SHALL disclose the resolved workspace scope — the workspace serving the view, or that none resolved and the view is repository-local.

## Changelog

- 2026-08-01 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: declare satisfaction of the REQ-p00019 anti-pattern template; rationale maps B/C/D/F to template classes
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: add unconditional workspace-scope disclosure (F) — registry-absent decision
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-37: inline design-doc content; the scaffolding doc is retired
- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: author org-wide visibility invariants (V1, V2, V3, H2)

*End* *Org-Wide Requirement Visibility* | **Hash**: 17fa4417
---

# REQ-p00082: Federated Authority and Verdict Scoping

**Level**: prd | **Status**: Draft | **Implements**: REQ-p00005

## Rationale

Enlarging the federated view multiplies the copies of any repository that a caller can reach (worktrees, clones, baselines) and multiplies the findings a validation run can surface. Without authority rules, a wider view degrades into noise: two versions of one requirement presented as peers, verdicts failing on defects the caller cannot fix, and tools writing into repositories the caller does not own. These are the authority invariants (A1, A2a, A2b, A3) and the expressibility invariant (E1).

Visibility without authority is legitimate — it is how one files a ticket against another team's repository. What is scoped here is the *verdict* and the *write path*, not what a caller may see. Reporting breadth remains a caller choice (assertion E). Coverage needs no authority mechanism of its own: cross-repository coverage flows only along declared *Traceability* edges, so widening membership cannot silently move coverage numbers.

Rejected shapes, recorded so they are not relitigated (2026-07-29 review). **Encoding policy scope in namespaces** was rejected: namespaces are an identity and ownership concept, and policy applicability is a judgment that changes as the organization changes — putting it in an identifier puts it in the least revisable place in the system, and cannot express the real many-to-many between obligations and repositories. **Top-down applicability relations** (an obligation naming which repositories must comply) were ruled out of scope: realizing that an obligation applies is the un-mechanizable part, and recording the decision does not create the decision — the declaration therefore stays on the complying repository's side (assertion G).

## Assertions

A. For any requirement visible in a federated view, the tool SHALL present exactly one authoritative version at any moment.

B. The tool SHALL NOT merge two copies of the same requirement, and SHALL NOT present two copies as peers, when the owning repository is reachable through more than one path or at more than one freshness.

C. The tool SHALL attribute every validation finding to the repository that owns the content the finding is about.

D. The pass/fail verdict of a validation run SHALL be computed exclusively from findings attributed to repositories within the caller's change scope, so that a finding the caller cannot fix never contributes to a failing exit status.

E. Whether findings attributed to repositories outside the caller's change scope are displayed SHALL be selectable by the caller, without altering the verdict.

F. The tool SHALL NOT modify content owned by a repository outside the caller's write authority, under any configuration.

G. The tool SHALL support declaring, from a requirement in one workspace repository, compliance with an obligation authored in another workspace repository.

H. A reference to a cross-repository obligation SHALL either resolve to that obligation or be reported as a broken reference.

## Changelog

- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: drop the umbrella-rejection paragraph — granularity is an authoring choice; non-root Satisfies, N/A declarations, and the chained-instantiation prohibition already cover applicability
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-37: inline design-doc content; the scaffolding doc is retired
- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: author federated authority invariants (A1, A2a, A2b, A3, E1)

*End* *Federated Authority and Verdict Scoping* | **Hash**: a8311d6c
---

# REQ-p00006: Interactive Traceability Viewer

**Level**: prd | **Status**: Active | **Implements**: REQ-p00003

## Rationale

Static *Traceability* matrices—whether Markdown tables or CSV exports—answer the question "what implements what?" but fail to support exploratory analysis. Reviewers need to navigate requirement hierarchies, drill into specific branches, and understand the full context of a requirement including its test coverage, implementation references, and change history.

The interactive trace viewer transforms the *Traceability* matrix into an explorable interface:

- **Clickable navigation**: Click a requirement to see what it implements and what implements it
- **Test coverage overlay**: See which requirements have tests, which are untested, and test pass/fail status
- **Git state awareness**: Visual indicators for uncommitted changes, moved requirements, and branch differences
- **Implementation references**: Links to source files that reference each requirement
- **Embedded content**: Optionally include full requirement text for offline review

This supports:

- Design reviews (navigate the hierarchy without switching files)
- Test planning (identify coverage gaps)
- Change impact analysis (see what's affected by a modification)
- Regulatory audits (demonstrate complete *Traceability* in one view)

## Assertions

A. The tool SHALL generate an interactive HTML view with clickable requirement navigation.

B. The tool SHALL display test coverage information per requirement when test data is available.

C. The viewer SHALL display source files inline in a side panel with syntax-highlighted content and stable line numbers, when embedded content is enabled.

D. The viewer SHALL present, on demand, current results for every analysis report the tool provides, without requiring the reviewer to leave the viewer.

## Changelog

- 2026-07-31 | 185217a3 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-03-30 | b3dd4d1a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Interactive Traceability Viewer* | **Hash**: 185217a3
---

## REQ-p00014: Satisfies Relationship

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

### Rationale

Cross-cutting concerns — regulatory compliance frameworks, security policies, accessibility standards, operational baselines — define obligations that multiple independent subsystems must satisfy. The `Satisfies:` relationship enables a template-instance pattern: a set of requirements is defined once as a reusable template, and individual subsystems declare that they satisfy it. When a requirement declares `Satisfies: X`, the graph builder clones the template's REQ subtree with composite IDs, creating instance nodes that participate in normal coverage computation. A `Stereotype` enum (`CONCRETE`, `TEMPLATE`, `INSTANCE`) classifies nodes, and an `INSTANCE` edge connects each clone to its template original. Templates are declared explicitly with a `**Template**` metadata-line marker so authors opt in deliberately and so the validator can catch mis-targeted `Satisfies:`/`Refines:`/`Implements:` references at build time.

A template is a *subtree*, not a single REQ: template-marked REQs refine other template-marked REQs to decompose one cross-cutting obligation into levels of detail (a policy root refined by its specific provisions). `Satisfies:` may target any member of a template subtree — the clone is the subtree rooted at the target, so declaring against an interior member is simply a narrower declaration. An earlier revision restricted templates to single-REQ scope (root plus directly-attached assertions, inbound `Refines:` prohibited); that made real policy hierarchies unrepresentable and is retired. The validation matrix's complements are deliberate permissions: template-to-template `Refines:` is the subtree-forming edge, and `Implements:` from CODE / `Verifies:` from TEST against template targets is the cross-cutting evidence path — assertion D produces the direct edge, assertion P makes that evidence count on every instance. Instances need no special analysis: evidence recorded against a template *Assertion* counts on each of its instances (assertion P), and from there every surface treats instances as ordinary directly-declared nodes (assertion K) — the standard rollup aggregates a cloned subtree like any other. The INSTANCE edge is the wiring by which implementations realize assertion P; whether that is computed as query-time inheritance or by materializing evidence edges onto clones is an implementation choice the spec does not fix. Which members of a subtree apply to a given repository is that repository's authoring decision, expressed by what it targets — the granularity question is no different from deciding what belongs in one REQ.

Two conformance details keep the model usable with named ID schemes. Named-component styles (kebab-case, snake_case) put the assertion-separator character inside requirement names, so a string like `HHT-OPS-production-readiness-A` is lexically ambiguous between a longer requirement name and an assertion-targeted reference; the configuration guard that rejects overlapping separator/label styles (REQ-d00251-F) makes the split well-defined, and assertion Q obliges every accepting field — the metadata line included — to apply the same split, so a reference never resolves differently in a `Satisfies:`/`Refines:` header than the identical string would in a code marker. And because template targets are where authors first collide with the validation matrix, assertion R separates the two ways a reference can fail — the ID resolves to nothing, or it resolves to a node the matrix forbids — so a diagnostic never sends an author hunting a "missing" requirement that in fact exists, or relaxing a rule when the real problem is a typo.

Three uniformity guarantees complete the reference contract. Reserving `:` out of every configurable pattern element (assertion S) leaves `::` unambiguous as the composite instance-ID joiner in any federation of valid configurations. Assertions T and U extend Q from parsing to the full round trip: one set of acceptance rules and one rendered form per entity — determined by the owning repository — in every file type, so a repository configured with separator `/` cites `REQ-p00001/F` everywhere, never `-F` on one surface and `/F` on another. Journey and journey-step references ride the same contract, steps standing in for *Assertions* (REQ-p00002-G).

### Assertions

A. The system SHALL support a `Satisfies:` metadata field on requirements. The target MAY be a requirement or a specific *Assertion*.

B. When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template subtree rooted at the target — the target template REQ with its directly-attached *Assertions*, plus every descendant template REQ that refines a member of the subtree, recursively, with their *Assertions* — using composite IDs of the form `declaring_id::original_id`.

C. The system SHALL classify nodes using a `Stereotype` field: `CONCRETE` (default), `TEMPLATE` (original nodes targeted by Satisfies), or `INSTANCE` (cloned copies). Each instance node SHALL have an INSTANCE edge to its template original.

D. CODE that declares `Implements: <template-assertion>` and TEST that declares `Verifies: <template-assertion>` SHALL produce a direct IMPLEMENTS or VERIFIES edge to the template *Assertion*.

E. Authors SHALL mark a requirement as a template by adding the no-value `**Template**` flag (markdown decoration optional) anywhere on the pipe-separated metadata line. The parser SHALL set `Stereotype.TEMPLATE` on the resulting REQ and on each of its *Assertions*. The render protocol SHALL emit the flag verbatim on the metadata line for any node with `Stereotype.TEMPLATE`.

F. `BrokenReference` SHALL carry an optional `diagnostic` field that explains why a reference is invalid. The `elspais checks` command SHALL surface the diagnostic verbatim in its health-finding message so authors get actionable guidance (e.g. *"REQ-A is not marked **Template**; mark REQ-A with **Template** if it's intended to be satisfiable."*).

G. The graph builder SHALL enforce a static validation matrix at build time, raising typed `BrokenReference` diagnostics for each invalid combination: `Satisfies:` against a target that exists but is not marked `**Template**`; `Satisfies:` against an `INSTANCE` target (chained instantiation); `Refines:` against a `TEMPLATE` target from a REQ not itself marked `**Template**` (a template's refiners must themselves be templates); `Refines:` against an `INSTANCE` target (refining instance content); `Implements:` from CODE against an `INSTANCE` target; `Verifies:` from TEST against an `INSTANCE` target; a REQ marked `**Template**` that declares `Implements:`/`Refines:` metadata targeting nodes outside its template subtree.

H. When a requirement declares `Satisfies:` against a template owned by an associated repository, the federated graph builder SHALL clone the template subtree (the target REQ, its directly-attached *Assertions*, and descendant template REQs with theirs) into the declaring repo's index with composite IDs of the form `declaring_id::original_id`, wiring intra-graph `SATISFIES`, `STRUCTURES`, `REFINES`, and `DEFINES` edges and a cross-graph `INSTANCE` edge from each clone to its template original.

J. When a cross-repository `Satisfies:` target is not claimed by any associated repository, the federated graph builder SHALL emit a typed `BrokenReference` whose diagnostic names the target ID, lists the currently-declared associates (or states that none are declared), and points authors at the `[associates.<name>]` block in `.elspais.toml`. When transitively walking `SATISFIES` and `INSTANCE` edges produces a cycle, the federated graph builder SHALL emit a typed `BrokenReference` whose diagnostic contains the word `cycle` and the cycle path; reporting one cycle per build is sufficient.

K. Coverage computation, rollup, and reporting SHALL treat an instance node exactly as a directly declared node of the same kind.

L. When a `Satisfies:` declaration is instantiated, the graph builder SHALL link the cloned subtree root to the declaring requirement via a SATISFIES edge.

M. Cloned template-subtree nodes SHALL preserve the *Assertion* content, STRUCTURES edges, and intra-subtree REFINES edges of their template originals.

N. When an as-authored `Satisfies:` target ID is non-canonical (e.g. unpadded), the federated graph builder SHALL canonicalize the target via per-repo ID resolution before cloning, so that all satisfiers of the same template produce composites using the same canonical original ID.

O. Each cross-repo `INSTANCE` clone SHALL record the owning template repository name in a `template_repo` field so viewers can display the template's provenance.

P. Evidence declared against a template *Assertion* SHALL count as evidence on every instance of that *Assertion*.

Q. The system SHALL parse each requirement or *Assertion* reference according to the ID-pattern rules of the repository that owns the referenced identifier.

R. When a declared reference fails to produce a valid relationship, the resulting diagnostic SHALL state which failure class occurred: resolution failure (the referenced ID matches no requirement or *Assertion*) or rule violation (the target exists but the relationship is forbidden by the validation matrix).

S. The system SHALL reject at configuration-validation time an identifier-pattern configuration able to produce an identifier or reference containing the character `:`.

T. The system SHALL apply the owning repository's reference-acceptance rules identically in every context that accepts references — spec, code, test, result, and journey files — so that a reference string valid in one context is valid in every context.

U. When the system renders a reference to a requirement, *Assertion*, journey, or journey step on any surface, it SHALL emit the form determined by the owning repository's canonical ID pattern.

### Changelog

- 2026-08-02 | ee2b9541 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-01 | 50f072e0 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 064c817a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: reserve `:` out of configurable pattern elements so `::` is unambiguously the composite joiner (S); uniform reference acceptance across file types (T); canonical rendered form per owning repo (U)
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-44: add Q (references parsed per the owning repository's ID-pattern rules) and R (diagnostics separate resolution failure from rule violation)
- 2026-07-30 | 47baf2fc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | 7adf98fa | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: templates become subtrees — B/H clone the subtree rooted at any satisfied member, G requires a template's refiners to be templates, composite obligations split out as L-P, K restated as instance uniformity with P carrying the cross-cutting evidence rule
- 2026-05-16 | 6c1d002c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-05-16 | - | - | Michael Lewis (<michael@anspar.org>) | CUR-1353 Phase 10: refresh assertion B to match single-REQ scope (no descendant REQs)
- 2026-05-16 | 6c1d002c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-16 | c7521067 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-05-16 | - | - | Michael Lewis (<michael@anspar.org>) | CUR-1353 Phase 5: add inherited-coverage assertion (K) for INSTANCE assertions and satisfier rollups
- 2026-05-16 | ed72021a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-16 | - | - | Michael Lewis (<michael@anspar.org>) | CUR-1353 Phase 4: add federated diagnostics (J) for missing associates and Satisfies cycles
- 2026-05-16 | - | - | Michael Lewis (<michael@anspar.org>) | CUR-1353 Phase 3: add federated cross-repo template instantiation (H)
- 2026-05-16 | 6e4308ff | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-05-16 | - | - | Michael Lewis (<michael@anspar.org>) | CUR-1353 Phase 2: add Template marker (E), diagnostic field (F), validation matrix (G); rewrite D to reflect the removal of file-based attribution
- 2026-05-11 | bae1b85d | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-05-04 | bae1b85d | - | Developer (<dev@example.com>) | Auto-fix: canonicalize term forms, update hash
- 2026-03-30 | 9115ce0d | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Satisfies Relationship* | **Hash**: ee2b9541
---

## REQ-p00016: NOT APPLICABLE Status

**Level**: prd | **Status**: Draft | **Implements**: REQ-p00001

### Rationale

When a cross-cutting template *Assertion* does not apply to a specific subsystem, the declaring requirement must be able to explicitly exclude it. This uses normative *Assertion* language consistent with the rest of the spec system, and follows the same semantics as deprecated status — the *Assertion* is excluded from the coverage denominator.

### Assertions

A. The system SHALL support explicit N/A declarations for template assertions using normative assertions on the declaring requirement (e.g., `REQ-p80001-D SHALL be NOT APPLICABLE`).

B. N/A assertions SHALL be treated the same as deprecated status: they SHALL NOT count toward the coverage target for the relevant template instance.

C. Any `Implements:` references to a N/A *Assertion* SHALL NOT count toward coverage and SHALL produce errors.

*End* *NOT APPLICABLE Status* | **Hash**: 2211802a
---

## REQ-p00050: Unified Graph Architecture

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

The elspais system SHALL use a unified graph-based architecture where TraceGraph is the single source of truth for all requirement data, hierarchy, and metrics.

### Assertions

A. The system SHALL use TraceGraph as the ONE and ONLY data structure for representing requirement hierarchies and relationships.

B. ALL outputs (HTML, Markdown, CSV, JSON, MCP resources) SHALL consume TraceGraph directly without creating intermediate data structures.

C. The system SHALL NOT create parallel data structures that duplicate information already in the graph.

D. The system SHALL NOT have multiple code paths that independently compute hierarchy, coverage, or relationships.

E. A node's identifier SHALL denote exactly one node.

### Rationale

Multiple data structures lead to synchronization bugs, duplicated logic, and maintenance burden. A single graph provides:

- Single source of truth
- Consistent hierarchy traversal
- Centralized metrics computation
- Easier testing and debugging

An identifier that denotes two nodes makes the graph two sources of truth wearing one name, which is the synchronization failure A exists to prevent rather than a separate concern. A lookup has to be able to answer, and a caller that writes based on that answer has to be writing to the thing it asked for.

### Changelog

- 2026-08-10 | 3a0fb899 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 46ac5f6a | - | Michael Lewis (<michael@anspar.org>) | Oblige an identifier to denote one node
- 2026-07-31 | 46ac5f6a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 4a1e5d0b | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 4a1e5d0b | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Unified Graph Architecture* | **Hash**: 3a0fb899
---

## REQ-p00060: MCP Server for AI-Driven Requirements Management

**Level**: prd | **Status**: Active | **Implements**: REQ-p00050

The elspais system SHALL provide an MCP server that enables AI agents to query, navigate, and mutate requirements through the unified TraceGraph.

### Assertions

A. The MCP server SHALL expose TraceGraph data through standardized MCP tools.

B. The MCP server SHALL consume TraceGraph directly without creating intermediate data structures, per REQ-p00050-B.

C. The MCP server SHALL provide read-only query tools for requirement discovery and navigation.

D. The MCP server SHALL provide mutation tools for AI-assisted requirement management.

E. The MCP server SHALL support undo operations for all graph mutations.

### Rationale

AI agents need programmatic access to requirements data for tasks like coverage analysis, requirement drafting, and *Traceability* verification. The MCP protocol provides a standardized interface that works with multiple AI platforms.

### Changelog

- 2026-07-31 | a729a853 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 3ebc237a | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 3ebc237a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *MCP Server for AI-Driven Requirements Management* | **Hash**: a729a853
---

## REQ-d00226: Comment Data Models

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. CommentEvent SHALL be a frozen dataclass with fields: event, id, anchor, author, author_id, date, text, parent, target, old_anchor, new_anchor, reason, from_file.

B. CommentEvent optional fields SHALL default to empty string.

C. CommentThread SHALL be a mutable dataclass with root, replies, anchor, resolved, promoted_from, and promotion_reason fields.

D. CommentThread anchor SHALL default to the root event anchor when not explicitly provided.

### Changelog

- 2026-07-31 | 6d420b96 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | dd5c745e | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | dd5c745e | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Comment Data Models* | **Hash**: 6d420b96

## REQ-d00227: Comment Index

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. CommentIndex SHALL provide an iterator-only query API: iter_threads, thread_count, has_threads, iter_orphaned, iter_all_anchors_for_node, source_file_for.

B. CommentIndex iter_all_anchors_for_node SHALL match exact node_id and node_id#fragment patterns.

C. CommentIndex SHALL support merge for federation following the TermDictionary pattern.

### Changelog

- 2026-07-31 | 6ca252cb | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | ff891bd9 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | ff891bd9 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Comment Index* | **Hash**: 6ca252cb

## REQ-d00228: Comment JSONL Storage

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. Anchor parsing SHALL handle bare requirement IDs, *Assertion* fragments, section fragments, and edge fragments.

B. Comment ID generation SHALL produce format c-YYYYMMDD-6hexchars using utilities/hasher.py.

C. JSONL load and append SHALL read/write CommentEvent records as one JSON object per line.

D. Thread assembly SHALL group events by root, attach replies, apply resolve/promote events, and filter resolved threads.

E. Comment file path resolution SHALL mirror repo structure under .elspais/comments/.

### Changelog

- 2026-07-31 | 7415991a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | cdaa4044 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | cdaa4044 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Comment JSONL Storage* | **Hash**: 7415991a

## REQ-d00229: Comment Promotion Engine

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. Anchor validation SHALL check node existence, *Assertion* existence, section existence, and edge existence against the live graph.

B. Orphaned comment promotion SHALL walk parent hierarchy to find the nearest living ancestor, falling back to an orphaned file.

C. Rename-triggered promotion SHALL update all anchors prefixed with the old ID and emit promote events with rename reason.

### Changelog

- 2026-07-31 | ec366878 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 3048ea60 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 3048ea60 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Comment Promotion Engine* | **Hash**: ec366878

## REQ-d00230: Comment Graph Integration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. TraceGraph SHALL expose comment delegate methods (iter_comments, comment_count, has_comments, iter_orphaned_comments) that delegate to the internal CommentIndex.

B. FederatedGraph SHALL route comment queries to the owning repo's TraceGraph using anchor-based ownership lookup and aggregate orphaned comments across all repos.

C. TraceGraph rename_node and rename_assertion SHALL call update_anchors_on_rename to keep comment anchors consistent after ID changes.

D. FederatedGraph SHALL provide a repo_root_for(node_id) public method that returns the repo root Path for write routing.

### Changelog

- 2026-07-31 | 1eb4899c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 0eed8546 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 0eed8546 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Comment Graph Integration* | **Hash**: 1eb4899c

## REQ-d00231: Comment API Endpoints

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. POST /api/comment/add SHALL create a new comment event, persist it to the JSONL file, update the in-memory index, and return the created event. Missing text SHALL return 400.

B. POST /api/comment/reply SHALL attach a reply event to an existing thread, persist it, and return the reply. Missing parent SHALL return 404.

C. POST /api/comment/resolve SHALL remove a thread from the in-memory index, persist a resolve event, and return success. Missing comment SHALL return 404.

D. GET /api/comments SHALL return serialized threads for a given anchor. GET /api/comments/card SHALL return threads grouped by anchor for all anchors of a node. GET /api/comments/orphaned SHALL return all orphaned threads.

E. Author identity SHALL be resolved server-side via get_author_info using the changelog.id_source config, never from client input.

### Changelog

- 2026-07-31 | 639d0eb5 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | b8533d82 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | b8533d82 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Comment API Endpoints* | **Hash**: 639d0eb5

## REQ-d00232: Comment UI Anchors and Margin Column

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. All commentable DOM elements SHALL have data-anchor attributes: card header (node ID), *Assertion* rows (node#label), edge rows (node#edge:target), body sections (node#section:name), and journey equivalents.

B. A comment margin column SHALL render speech bubble icons with count badges for anchors that have comment threads, fetched via /api/comments/card when a card opens.

### Changelog

- 2026-07-31 | 34656218 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 6869aa8a | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 6869aa8a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Comment UI Anchors and Margin Column* | **Hash**: 34656218

## REQ-d00233: Comment Inline Threads and Comment Mode

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. Inline thread rendering SHALL display author, date, text, replies, and edit-mode-only Resolve/Reply controls below the target element.

B. Comment mode SHALL be a one-shot mode entered via C key or toolbar button (Edit Mode required), showing a textarea on click, posting via /api/comment/add, then exiting.

### Changelog

- 2026-07-31 | fd4019ef | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 792d13ce | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 792d13ce | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Comment Inline Threads and Comment Mode* | **Hash**: fd4019ef

## REQ-d00234: Lost Comments Card

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. A Lost Comments card SHALL appear at the top of the card column when orphaned comments exist, fetched via /api/comments/orphaned on page load, showing original anchor context and edit-mode-only Resolve buttons.

### Changelog

- 2026-07-31 | 0bd322d3 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 7fc99c6a | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 7fc99c6a | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Lost Comments Card* | **Hash**: 0bd322d3

## REQ-d00235: Comment Compaction CLI

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Rationale

Resolved review threads are disposable working notes, not audit evidence. The audit record of *why* a requirement changed lives in requirement changelogs, version control, or the requirement itself.

### Assertions

A. compact_file SHALL rewrite JSONL files stripping resolved threads entirely and collapsing promote chains to keep only the final promote event, returning the count of removed events.

B. The elspais comments compact CLI command SHALL glob .elspais/comments/**/*.json, call compact_file on each, and report total events removed.

### Changelog

- 2026-07-31 | 69df1fbc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | f3547362 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | f3547362 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Comment Compaction CLI* | **Hash**: 69df1fbc

## REQ-d00242: Terms API Endpoints

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. GET /api/terms SHALL return a JSON array of term objects sorted alphabetically by term name, each containing fields: term, key, definition_short (truncated to 150 chars), defined_in, namespace, collection, indexed, ref_count. An empty TermDictionary SHALL return an empty array.

B. GET /api/term/{term_key} SHALL return the full term detail including definition, defined_in, namespace, collection, indexed, and a references array where each reference includes node_id, node_title (resolved server-side via find_by_id), namespace, marked, and line.

C. GET /api/term/{nonexistent_key} SHALL return HTTP 404 with an error message.

### Changelog

- 2026-07-31 | a4522e0f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 6c934e14 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 6c934e14 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Terms API Endpoints* | **Hash**: a4522e0f

## REQ-d00243: Terms Tab in Viewer Nav Tree

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. A Terms tab button with data-kind="terms" SHALL appear in the nav-tabs bar. switchNavTab('terms') SHALL activate it, persist via cookie, and render terms content.

B. The Terms tab SHALL display a flat alphabetical list of terms with letter headings (A, B, C...). Each term row SHALL show the term name and a reference count badge. An empty TermDictionary SHALL show "No defined terms found".

C. Expand/collapse buttons, tree/flat toggle, and filter groups (status, git, hierarchy, coverage) SHALL be hidden when the Terms tab is active. The text filter SHALL filter terms by name substring.

### Changelog

- 2026-07-31 | 2873ed03 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 3328f677 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 3328f677 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Terms Tab in Viewer Nav Tree* | **Hash**: 2873ed03

## REQ-d00244: Term Cards in Viewer Card Stack

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. openTermCard(termKey) SHALL fetch GET /api/term/{key} and open a card in the card stack with ID "term:{lowercase-key}". The card SHALL show term name header, definition text, defined-in link, namespace, and a "Collection" badge for collection terms.

B. The references section SHALL group references by namespace, with each reference row clickable to open that node's card. Empty references SHALL show "No references resolved yet". Clicking defined-in link SHALL open the source requirement card.

C. Term cards SHALL be read-only with no edit controls. The card SHALL be rendered via buildTermCardHtml() and wired into renderCardStack() via a kind === 'term' branch.

### Changelog

- 2026-07-31 | 0a48035f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 5dd49a51 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 5dd49a51 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Term Cards in Viewer Card Stack* | **Hash**: 0a48035f

## REQ-d00245: Inline Term Highlighting in Viewer Cards

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

### Assertions

A. simpleMarkdown(text, true) SHALL wrap defined terms in span elements with class "defined-term", data-term-key, and data-tip (truncated definition) attributes. Matching SHALL be longest-first, word-boundary anchored, and case-insensitive.

B. Clicking a defined-term span SHALL open the term card via a delegated click handler on the card-stack-body. Hover SHALL show a truncated definition tooltip via the data-tip attribute. Term annotation SHALL NOT be applied inside term cards to prevent recursion.

### Changelog

- 2026-07-31 | 697c60cc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 62a44ed3 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 62a44ed3 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Inline Term Highlighting in Viewer Cards* | **Hash**: 697c60cc

## REQ-d00267: Viewer Pending-Work Indicator Truth

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006, REQ-p00015

The viewer's pending-change indicator is server-truth: the changes it counts are
held in the server process, not in the page. So the page has three states to
tell apart, not two — the server reported nothing pending, the server reported
work pending, and the server could not be asked — and collapsing the third into
either of the first two makes the page lie. Reporting the last known count as
though it were current asserts work that may exist in no process; reporting zero
hides work that may still be pending behind a momentary network failure. This is
REQ-p00015-E's distinction between a value and the absence of one, applied in the
presentation layer.

The navigation warning is the same distinction with consequences. Because the
pending changes live in the server and not in the tab, closing the tab destroys
none of the changes the indicator counts, and the warning is a courtesy about
server-side state rather than a guard on data in the page. Obstructing
navigation over a claim the viewer cannot verify therefore buys no safety and
can leave an operator unable to leave the page at all.

An operation that acts on the server-side changes themselves is the opposite
case, and the two must not be conflated. Switching branches, checkpointing, or
reverting can discard or strand pending changes, so the cost of proceeding on a
wrong belief is real; there, an unknown count has to be treated as work that may
exist. Navigation is permissive under uncertainty because it destroys nothing;
operations that destroy are restrictive under the same uncertainty. Where the
refusal already happens at the server — a history-level operation that carries
the change-history position the caller has seen is rejected outright when
anything unseen is pending, and an unread position is sent as "I believe
nothing is pending" — the obligation is discharged there and needs no second
check in the page. It binds in the page exactly where nothing else refuses.

That last failure mode is reported from the field and its cause is not yet
established: a page that will not close looks identical whether the navigation
warning fired and its dialog never rendered, or the page never got as far as
deciding. The two are told apart by the state the decision reads and by whether
the decision was reached at all, so that state and that decision must be
recoverable after the fact by an operator with nothing but the browser's own
console — not reconstructed by inference from what the page happens to be
displaying.

### Assertions

A. When the viewer cannot obtain the pending-change count from the server, the viewer SHALL present the count as unknown, SHALL present it neither as the last count obtained nor as zero, and SHALL NOT record the change history it failed to read as seen.

B. When the server reports a pending-change count after the viewer has presented the count as unknown, the viewer SHALL replace the unknown presentation with the reported count.

C. The viewer SHALL warn an operator before navigating away only while the server has reported that changes are pending; while the pending-change count is unknown, the viewer SHALL NOT obstruct navigation.

D. The viewer SHALL make the state that decides whether it warns before navigation inspectable on demand — the count, whether the count is known, and when it was last established — and SHALL report the decision it reached at the moment navigation is attempted.

E. An operation that would discard, strand, or commit around pending changes SHALL treat an unknown pending-change count as changes that may exist, never as zero.

### Changelog

- 2026-08-07 | c1be85e3 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-07 | 5d25457c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-07 | 94abbc63 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: add missing changelog section

*End* *Viewer Pending-Work Indicator Truth* | **Hash**: c1be85e3
