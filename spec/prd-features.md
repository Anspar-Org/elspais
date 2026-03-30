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

## Assertions

A. The tool SHALL support requirement references across repository boundaries using configurable namespace prefixes.

B. The tool SHALL generate combined **Traceability** matrices spanning multiple repositories.

C. The tool SHALL support CLI-based configuration of associate repository paths so that external systems can register associates without manually editing configuration files.

D. The tool SHALL discover an associated repository's identity — including its project type and namespace prefix — by reading that repository's own configuration file.

E. The tool SHALL report a clear configuration error when a configured associate path does not exist or does not contain a valid associated-repository configuration.

F. The tool SHALL resolve relative associate paths from the canonical (non-worktree) repository root so that cross-repository paths remain valid when working from git worktrees.

## Changelog

- 2026-03-30 | f935e564 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Multi-Repository Requirements* | **Hash**: c3303546
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

## Changelog

- 2026-03-30 | b3dd4d1a | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms
- 2026-03-30 | b3dd4d1a | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms
- 2026-03-30 | b3dd4d1a | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms
- 2026-03-30 | b3dd4d1a | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Interactive Traceability Viewer* | **Hash**: b3dd4d1a
---

## REQ-p00014: Satisfies Relationship

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Cross-cutting concerns — regulatory compliance frameworks, security policies, accessibility standards, operational baselines — define obligations that multiple independent subsystems must satisfy. The `Satisfies:` relationship enables a template-instance pattern: a set of requirements is defined once as a reusable template, and individual subsystems declare that they satisfy it. When a requirement declares `Satisfies: X`, the graph builder clones the template's REQ subtree with composite IDs, creating instance nodes that participate in normal coverage computation. A `Stereotype` enum (`CONCRETE`, `TEMPLATE`, `INSTANCE`) classifies nodes, and an `INSTANCE` edge connects each clone to its template original.

## Assertions

A. The system SHALL support a `Satisfies:` metadata field on requirements. The target MAY be a requirement or a specific *Assertion*.

B. When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree (all descendant REQs and their assertions) with composite IDs of the form `declaring_id::original_id`. The cloned root SHALL be linked to the declaring requirement via a SATISFIES edge. Internal edges and assertions SHALL be preserved exactly as in the original. Coverage of cloned nodes SHALL use the standard coverage mechanism — no special computation is needed.

C. The system SHALL classify nodes using a `Stereotype` field: `CONCRETE` (default), `TEMPLATE` (original nodes targeted by Satisfies), or `INSTANCE` (cloned copies). Each instance node SHALL have an INSTANCE edge to its template original.

D. The system SHALL attribute `Implements:` references to template assertions to the correct instance by finding a sibling `Implements:` reference to a CONCRETE node in the same source file, walking that node's ancestors to the first node with a `Satisfies:` declaration matching the template, and constructing the instance ID from the declaring node's ID and the referenced node's ID.

## Changelog

- 2026-03-30 | 9115ce0d | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Satisfies Relationship* | **Hash**: 9115ce0d
---

## REQ-p00016: NOT APPLICABLE Status

**Level**: prd | **Status**: Draft | **Implements**: REQ-p00001

## Rationale

When a cross-cutting template *Assertion* does not apply to a specific subsystem, the declaring requirement must be able to explicitly exclude it. This uses normative *Assertion* language consistent with the rest of the spec system, and follows the same semantics as deprecated status — the *Assertion* is excluded from the coverage denominator.

## Assertions

A. The system SHALL support explicit N/A declarations for template assertions using normative assertions on the declaring requirement (e.g., `REQ-p80001-D SHALL be NOT APPLICABLE`).

B. N/A assertions SHALL be treated the same as deprecated status: they SHALL NOT count toward the coverage target for the relevant template instance.

C. Any `Implements:` references to a N/A *Assertion* SHALL NOT count toward coverage and SHALL produce errors.

*End* *NOT APPLICABLE Status* | **Hash**: cf53ad98
---

## REQ-p00050: Unified Graph Architecture

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

The elspais system SHALL use a unified graph-based architecture where TraceGraph is the single source of truth for all requirement data, hierarchy, and metrics.

## Assertions

A. The system SHALL use TraceGraph as the ONE and ONLY data structure for representing requirement hierarchies and relationships.

B. ALL outputs (HTML, Markdown, CSV, JSON, MCP resources) SHALL consume TraceGraph directly without creating intermediate data structures.

C. The system SHALL NOT create parallel data structures that duplicate information already in the graph.

D. The system SHALL NOT have multiple code paths that independently compute hierarchy, coverage, or relationships.

## Rationale

Multiple data structures lead to synchronization bugs, duplicated logic, and maintenance burden. A single graph provides:

- Single source of truth
- Consistent hierarchy traversal
- Centralized metrics computation
- Easier testing and debugging

*End* *Unified Graph Architecture* | **Hash**: 4a1e5d0b
---

## REQ-p00060: MCP Server for AI-Driven Requirements Management

**Level**: prd | **Status**: Active | **Implements**: REQ-p00050

The elspais system SHALL provide an MCP server that enables AI agents to query, navigate, and mutate requirements through the unified TraceGraph.

## Assertions

A. The MCP server SHALL expose TraceGraph data through standardized MCP tools.

B. The MCP server SHALL consume TraceGraph directly without creating intermediate data structures, per REQ-p00050-B.

C. The MCP server SHALL provide read-only query tools for requirement discovery and navigation.

D. The MCP server SHALL provide mutation tools for AI-assisted requirement management.

E. The MCP server SHALL support undo operations for all graph mutations.

## Rationale

AI agents need programmatic access to requirements data for tasks like coverage analysis, requirement drafting, and *Traceability* verification. The MCP protocol provides a standardized interface that works with multiple AI platforms.

## Changelog

- 2026-03-30 | 3ebc237a | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *MCP Server for AI-Driven Requirements Management* | **Hash**: 3ebc237a
---

## REQ-d00226: Comment Data Models

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. CommentEvent SHALL be a frozen dataclass with fields: event, id, anchor, author, author_id, date, text, parent, target, old_anchor, new_anchor, reason, from_file.

B. CommentEvent optional fields SHALL default to empty string.

C. CommentThread SHALL be a mutable dataclass with root, replies, anchor, resolved, promoted_from, and promotion_reason fields.

D. CommentThread anchor SHALL default to the root event anchor when not explicitly provided.

*End* *Comment Data Models* | **Hash**: dd5c745e

## REQ-d00227: Comment Index

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. CommentIndex SHALL provide an iterator-only query API: iter_threads, thread_count, has_threads, iter_orphaned, iter_all_anchors_for_node, source_file_for.

B. CommentIndex iter_all_anchors_for_node SHALL match exact node_id and node_id#fragment patterns.

C. CommentIndex SHALL support merge for federation following the TermDictionary pattern.

*End* *Comment Index* | **Hash**: ff891bd9

## REQ-d00228: Comment JSONL Storage

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. Anchor parsing SHALL handle bare requirement IDs, *Assertion* fragments, section fragments, and edge fragments.

B. Comment ID generation SHALL produce format c-YYYYMMDD-6hexchars using utilities/hasher.py.

C. JSONL load and append SHALL read/write CommentEvent records as one JSON object per line.

D. Thread assembly SHALL group events by root, attach replies, apply resolve/promote events, and filter resolved threads.

E. Comment file path resolution SHALL mirror repo structure under .elspais/comments/.

## Changelog

- 2026-03-30 | cdaa4044 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Comment JSONL Storage* | **Hash**: cdaa4044

## REQ-d00229: Comment Promotion Engine

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. Anchor validation SHALL check node existence, *Assertion* existence, section existence, and edge existence against the live graph.

B. Orphaned comment promotion SHALL walk parent hierarchy to find the nearest living ancestor, falling back to an orphaned file.

C. Rename-triggered promotion SHALL update all anchors prefixed with the old ID and emit promote events with rename reason.

## Changelog

- 2026-03-30 | 3048ea60 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Comment Promotion Engine* | **Hash**: 3048ea60

## REQ-d00230: Comment Graph Integration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. TraceGraph SHALL expose comment delegate methods (iter_comments, comment_count, has_comments, iter_orphaned_comments) that delegate to the internal CommentIndex.

B. FederatedGraph SHALL route comment queries to the owning repo's TraceGraph using anchor-based ownership lookup and aggregate orphaned comments across all repos.

C. TraceGraph rename_node and rename_assertion SHALL call update_anchors_on_rename to keep comment anchors consistent after ID changes.

D. FederatedGraph SHALL provide a repo_root_for(node_id) public method that returns the repo root Path for write routing.

*End* *Comment Graph Integration* | **Hash**: 0eed8546

## REQ-d00231: Comment API Endpoints

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. POST /api/comment/add SHALL create a new comment event, persist it to the JSONL file, update the in-memory index, and return the created event. Missing text SHALL return 400.

B. POST /api/comment/reply SHALL attach a reply event to an existing thread, persist it, and return the reply. Missing parent SHALL return 404.

C. POST /api/comment/resolve SHALL remove a thread from the in-memory index, persist a resolve event, and return success. Missing comment SHALL return 404.

D. GET /api/comments SHALL return serialized threads for a given anchor. GET /api/comments/card SHALL return threads grouped by anchor for all anchors of a node. GET /api/comments/orphaned SHALL return all orphaned threads.

E. Author identity SHALL be resolved server-side via get_author_info using the changelog.id_source config, never from client input.

*End* *Comment API Endpoints* | **Hash**: b8533d82

## REQ-d00232: Comment UI Anchors and Margin Column

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. All commentable DOM elements SHALL have data-anchor attributes: card header (node ID), *Assertion* rows (node#label), edge rows (node#edge:target), body sections (node#section:name), and journey equivalents.

B. A comment margin column SHALL render speech bubble icons with count badges for anchors that have comment threads, fetched via /api/comments/card when a card opens.

## Changelog

- 2026-03-30 | 6869aa8a | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Comment UI Anchors and Margin Column* | **Hash**: 6869aa8a

## REQ-d00233: Comment Inline Threads and Comment Mode

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. Inline thread rendering SHALL display author, date, text, replies, and edit-mode-only Resolve/Reply controls below the target element.

B. Comment mode SHALL be a one-shot mode entered via C key or toolbar button (Edit Mode required), showing a textarea on click, posting via /api/comment/add, then exiting.

*End* *Comment Inline Threads and Comment Mode* | **Hash**: 792d13ce

## REQ-d00234: Lost Comments Card

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. A Lost Comments card SHALL appear at the top of the card column when orphaned comments exist, fetched via /api/comments/orphaned on page load, showing original anchor context and edit-mode-only Resolve buttons.

*End* *Lost Comments Card* | **Hash**: 7fc99c6a

## REQ-d00235: Comment Compaction CLI

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. compact_file SHALL rewrite JSONL files stripping resolved threads entirely and collapsing promote chains to keep only the final promote event, returning the count of removed events.

B. The elspais comments compact CLI command SHALL glob .elspais/comments/**/*.json, call compact_file on each, and report total events removed.

*End* *Comment Compaction CLI* | **Hash**: f3547362

## REQ-d00242: Terms API Endpoints

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. GET /api/terms SHALL return a JSON array of term objects sorted alphabetically by term name, each containing fields: term, key, definition_short (truncated to 150 chars), defined_in, namespace, collection, indexed, ref_count. An empty TermDictionary SHALL return an empty array.

B. GET /api/term/{term_key} SHALL return the full term detail including definition, defined_in, namespace, collection, indexed, and a references array where each reference includes node_id, node_title (resolved server-side via find_by_id), namespace, marked, and line.

C. GET /api/term/{nonexistent_key} SHALL return HTTP 404 with an error message.

*End* *Terms API Endpoints* | **Hash**: 6c934e14

## REQ-d00243: Terms Tab in Viewer Nav Tree

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. A Terms tab button with data-kind="terms" SHALL appear in the nav-tabs bar. switchNavTab('terms') SHALL activate it, persist via cookie, and render terms content.

B. The Terms tab SHALL display a flat alphabetical list of terms with letter headings (A, B, C...). Each term row SHALL show the term name and a reference count badge. An empty TermDictionary SHALL show "No defined terms found".

C. Expand/collapse buttons, tree/flat toggle, and filter groups (status, git, hierarchy, coverage) SHALL be hidden when the Terms tab is active. The text filter SHALL filter terms by name substring.

*End* *Terms Tab in Viewer Nav Tree* | **Hash**: 3328f677

## REQ-d00244: Term Cards in Viewer Card Stack

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. openTermCard(termKey) SHALL fetch GET /api/term/{key} and open a card in the card stack with ID "term:{lowercase-key}". The card SHALL show term name header, definition text, defined-in link, namespace, and a "Collection" badge for collection terms.

B. The references section SHALL group references by namespace, with each reference row clickable to open that node's card. Empty references SHALL show "No references resolved yet". Clicking defined-in link SHALL open the source requirement card.

C. Term cards SHALL be read-only with no edit controls. The card SHALL be rendered via buildTermCardHtml() and wired into renderCardStack() via a kind === 'term' branch.

*End* *Term Cards in Viewer Card Stack* | **Hash**: 5dd49a51

## REQ-d00245: Inline Term Highlighting in Viewer Cards

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

## Assertions

A. simpleMarkdown(text, true) SHALL wrap defined terms in span elements with class "defined-term", data-term-key, and data-tip (truncated definition) attributes. Matching SHALL be longest-first, word-boundary anchored, and case-insensitive.

B. Clicking a defined-term span SHALL open the term card via a delegated click handler on the card-stack-body. Hover SHALL show a truncated definition tooltip via the data-tip attribute. Term annotation SHALL NOT be applied inside term cards to prevent recursion.

*End* *Inline Term Highlighting in Viewer Cards* | **Hash**: 62a44ed3
