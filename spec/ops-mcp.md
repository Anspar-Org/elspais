# MCP Operations Requirements

## REQ-o00060: MCP Core Query Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide core query tools for graph inspection and requirement lookup.

### Assertions

A. `get_graph_status()` SHALL return graph staleness state, node counts by kind, and last refresh timestamp.

B. `refresh_graph(full)` SHALL force graph rebuild, with `full=True` clearing all caches.

C. `search(query, field, regex, limit)` SHALL search requirements by ID, title, body, or keyword content, supporting multi-term AND/OR queries with relevance scoring.

D. `get_requirement(req_id)` SHALL return full requirement details including assertions and relationships.

E. `get_hierarchy(req_id)` SHALL return ancestors and children for navigation.

F. All query tools SHALL read directly from TraceGraph nodes using the iterator-only API.

G. Read surfaces that return a node SHALL report the version a subsequent mutation of that node will require, and a requirement's payload SHALL also report the version of the file containing it, so that a caller never has to fetch a node twice to be allowed to change it. A means of retrieving versions for several nodes without their content SHALL exist, so a caller can refresh what it holds cheaply.

### Rationale

Core query tools enable AI agents to discover and explore requirements without modifying the graph. These are safe, read-only operations.

Mutations require the caller to supply the version of the state it intends to change, so every read that could precede a write has to hand that version back. Omitting it would force a second round-trip purely to obtain a token the caller had already earned, and would make the mandatory precondition feel like an obstacle rather than a guarantee.

### Changelog

- 2026-08-02 | 3a9ae713 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-26 | 25b3d4f7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 73c31134 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 73c31134 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *MCP Core Query Tools* | **Hash**: 3a9ae713
---

## REQ-o00061: MCP Workspace Context Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide workspace context tools that describe the current repository and project.

### Assertions

A. `get_workspace_info()` SHALL return repository path, project name, and configuration summary.

B. `get_project_summary()` SHALL return requirement counts by level, coverage statistics, and change metrics.

C. Workspace tools SHALL derive statistics from the shared coverage aggregation (graph aggregation module), not recompute them.

D. Configuration data SHALL be read from the unified config system, not parsed separately.

### Rationale

AI agents need context about the workspace they're operating in to provide relevant assistance. Workspace tools answer "what repo am I serving?" and "what's the state of this project?"

### Changelog

- 2026-07-31 | 3306c687 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | aaba2940 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 0aa9dff4 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 0aa9dff4 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *MCP Workspace Context Tools* | **Hash**: 3306c687
---

## REQ-o00062: MCP Graph Mutation Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide mutation tools for in-memory graph modifications with full undo support.

### Assertions

A. Node mutations SHALL include: rename, update_title, change_status, add_requirement, delete_requirement.

B. *Assertion* mutations SHALL include: add_assertion, update_assertion, delete_assertion, rename_assertion.

C. Edge mutations SHALL include: add_edge, change_edge_kind, change_edge_targets, delete_edge, fix_broken_reference.

D. All mutations SHALL delegate to TraceGraph mutation methods, not implement mutation logic directly.

E. All mutations SHALL return a MutationEntry for audit and undo.

F. Destructive operations (delete_*) SHALL require explicit `confirm=True` parameter.

G. The server SHALL support reversing the most recent mutation, and reversing history back to a named earlier mutation, restoring the graph state the mutation history records.

H. *Section* (remainder) mutations SHALL include: add_remainder, update_remainder, delete_remainder, covering non-normative prose such as Rationale and Notes.

I. Every mutation SHALL require the caller to supply the version of the state it intends to modify, and SHALL reject the mutation when that version does not match the graph's current state. A creation that names no existing node — a new root requirement with no parent — has no prior state to clobber and is the sole exemption.

J. A rejected mutation SHALL report the current version together with the current state of the target, so the caller can reconcile and retry without issuing a second read.

K. Every successful mutation SHALL report the resulting version of the authoring unit it modified; a deletion SHALL report the version of the surviving container that absorbed the change — the owning requirement for an assertion or section, the containing file for a whole node — so a caller performing a sequence of mutations need not re-read between them.

L. A mutation naming a node that does not exist SHALL be reported distinctly from a version mismatch, since retrying cannot resolve it.

M. Mutations that change a relationship SHALL be guarded on the referring node alone, because only the referring node's rendered form changes. Mutations that relocate content between files SHALL be guarded on the content node and on both the origin and destination files, because all three change. A participant that does not exist when the mutation is issued — an unlinked content node, or a destination file the relocation itself creates — has no version to require.

N. Mutations acting on the mutation history as a whole — reversing mutations, discarding pending mutations, and persisting them — SHALL require the caller to name the current end of that history, SHALL reject when it does not match, and SHALL report the entries recorded since the caller's position.

O. Every mutation reachable through the review server's HTTP interface SHALL also be reachable through the MCP interface, under the same preconditions and returning the same rejection shape, so that an agent and a human editing the same graph have the same capabilities and the same safety.

P. Undoing a deletion SHALL restore the node's structural attachment, not merely its existence: its file membership, both edge directions with their edge metadata and assertion targets, and its root membership SHALL be restored, so the node renders back into its original file at its original position and the versions of nodes it referenced are left unchanged.

Q. When the daemon serves HTTP, its MCP interface SHALL accept sessions at the documented endpoint and SHALL operate on the same in-memory graph as the review server's HTTP interface, so agent and human writers are guarded against each other rather than only against writers on their own transport. A mount that cannot be served SHALL be reported, not silently omitted.

### Rationale

In-memory mutations enable AI agents to draft requirement changes that can be reviewed before persisting. The undo system provides safety for exploratory editing.

A single daemon serves multiple concurrent writers — MCP agents and the viewer share one graph — and nothing else can detect that two of them read the same state before both writing it. Requiring the caller to state which version it believes it is modifying turns a silent lost update into a rejection the caller can act on. The precondition is mandatory rather than optional because an unguarded mutation is a blind write, which is the failure being prevented; returning the resulting version on success keeps the cost at one read per sequence rather than one per mutation. The history guards exist for the same reason at a different granularity: reversing, discarding, or persisting affects every writer's pending work, so no caller should be able to do it to a set of mutations it has never seen.

### Changelog

- 2026-08-02 | e4b381e0 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | ad214b71 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | ca1d9dee | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-26 | 7c83917e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-26 | ef195b50 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-09 | 69e70749 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | ef63f424 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | ef63f424 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *MCP Graph Mutation Tools* | **Hash**: e4b381e0
---

## REQ-o00063: MCP File Mutation Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide file mutation tools that persist changes to spec files on disk.

### Assertions

A. `change_reference_type(req_id, target_id, new_type)` SHALL modify Implements/Refines relationships in spec files.

B. `move_requirement(req_id, target_file)` SHALL relocate a requirement between spec files.

C. `transform_with_ai(req_id, prompt, save_branch)` SHALL use AI to rewrite requirement content.

D. File mutations SHALL create git safety branches when `save_branch=True`.

E. `restore_from_safety_branch(branch_name)` SHALL revert file changes from a safety branch.

F. After file mutations, `refresh_graph()` SHALL be called to synchronize the in-memory graph.

G. `modify_title(req_id, new_title)` SHALL modify a requirement's title text in its spec file.

H. `modify_assertion_text(req_id, label, new_text)` SHALL modify the text of an existing *Assertion* in its spec file.

I. `add_assertion(req_id, label, text)` SHALL add a new *Assertion* to a requirement in its spec file.

### Rationale

File mutations persist changes to the authoritative spec files. Git safety branches provide rollback capability for destructive operations.

### Changelog

- 2026-07-31 | 05c1e9c4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 291497b8 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 291497b8 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *MCP File Mutation Tools* | **Hash**: 05c1e9c4
---

## REQ-o00064: MCP Test Coverage Analysis Tools

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide test coverage analysis tools for identifying test-requirement relationships and coverage gaps.

### Assertions

A. `get_test_coverage(req_id)` SHALL return TEST nodes that reference the requirement and their TEST_RESULT nodes.

B. `get_uncovered_assertions(req_id=None)` SHALL identify assertions with no TEST node references.

C. `find_assertions_by_keywords(keywords, match_all)` SHALL search *Assertion* text for keyword matches.

D. Coverage tools SHALL consume graph edges directly without caching or recomputation.

E. Coverage tools SHALL support filtering by requirement ID or scanning all requirements.

### Rationale

AI agents performing requirement analysis need to understand test coverage and identify gaps. These tools enable systematic coverage improvement workflows like those in Phase 7 of the master plan.

### Changelog

- 2026-07-31 | a97fc5c4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | e7fd1b43 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | e7fd1b43 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *MCP Test Coverage Analysis Tools* | **Hash**: a97fc5c4
---

## REQ-o00065: Agent-Assisted Link Suggestion

**Level**: ops | **Status**: Active | **Implements**: REQ-p00050

The system SHALL provide an agent-assisted link suggestion engine that analyzes unlinked graph nodes and proposes requirement associations using scoring heuristics.

### Assertions

A. The suggestion engine SHALL identify unlinked TEST nodes (those without REQUIREMENT parents via VERIFIES edges) as suggestion candidates.

B. The suggestion engine SHALL score suggestions using multiple heuristics: import chain analysis, function name matching, file path proximity, and keyword overlap.

C. Each suggestion SHALL include a source node, target requirement, confidence score (0.0-1.0), confidence band (high/medium/low), and human-readable reason.

D. The suggestion engine SHALL be exposed through both CLI (`elspais link suggest`) and MCP tools (`suggest_links`).

E. The suggestion engine SHALL operate read-only on the graph, producing suggestions without modifying graph state.

F. The suggestion engine SHALL support applying suggestions by inserting `# Implements:` comments into source files.

### Rationale

Teams need to not just see what's unlinked but act on it efficiently. Combining existing building blocks (import analyzer, test-code linker, keyword search) into a scoring pipeline enables AI agents and humans to close *Traceability* gaps systematically.

### Changelog

- 2026-07-31 | 06f8e1ac | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 17851ae2 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 17851ae2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Agent-Assisted Link Suggestion* | **Hash**: 06f8e1ac
---

## REQ-o00067: MCP Subtree Extraction Tool

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a subtree extraction tool for scoped subgraph retrieval.

### Assertions

A. `get_subtree(root_id, depth, include_kinds, format)` SHALL extract a subgraph rooted at a given node using BFS traversal.

B. The subtree tool SHALL support depth limiting where `depth=0` means unlimited and `depth=N` limits to N levels from root.

C. The subtree tool SHALL support kind filtering via `include_kinds` parameter with conservative defaults per root kind.

D. The subtree tool SHALL support three output formats: `markdown`, `flat`, and `nested`.

E. The subtree tool SHALL deduplicate nodes in DAG structures using a visited set.

F. The subtree tool SHALL include coverage summary statistics for requirement nodes.

### Rationale

LLM agents need scoped requirement subsets for sub-agent consumption. Extracting a subtree avoids context pollution from the full graph.

### Changelog

- 2026-07-31 | ea2ba371 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | ab29e315 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | ab29e315 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *MCP Subtree Extraction Tool* | **Hash**: ea2ba371
---

## REQ-o00068: MCP Cursor Protocol

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a general-purpose cursor protocol for incremental iteration over read query results.

### Assertions

A. `open_cursor(query, params, batch_size)` SHALL materialize query results and return the first item with metadata.

B. `cursor_next(count)` SHALL return the next `count` items and advance the cursor position.

C. `cursor_info()` SHALL return cursor position, total count, and remaining count without advancing.

D. The cursor protocol SHALL support a single active cursor, with opening a new cursor auto-closing the previous.

E. The cursor protocol SHALL support `batch_size` semantics: `-1` for assertions as first-class items, `0` for nodes with inline assertions, `1` for nodes with children previews.

F. The cursor protocol SHALL support query types: `subtree`, `search`, `hierarchy`, `query_nodes`, `test_coverage`, `uncovered_assertions`, `scoped_search`.

### Rationale

LLMs benefit from incremental exploration of results, deciding when to stop rather than receiving everything at once. A cursor protocol enables this without modifying existing read tools.

### Changelog

- 2026-07-31 | f876db43 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 743877c3 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 743877c3 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *MCP Cursor Protocol* | **Hash**: f876db43
---

## REQ-o00069: MCP Minimize Requirement Set Tool

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a `minimize_requirement_set` tool that prunes a set of requirement IDs to their most-specific members by removing ancestors already covered by more-specific descendants.

### Assertions

A. `minimize_requirement_set(req_ids, edge_kinds)` SHALL accept a list of requirement IDs and an optional edge kinds filter defaulting to "implements,refines".

B. The tool SHALL return a minimal set containing only requirements that are not ancestors of other requirements in the input set.

C. The tool SHALL return pruned requirements with metadata indicating which input member(s) supersede each pruned item.

D. The tool SHALL report unknown IDs separately in a `not_found` list without failing the operation.

E. The tool SHALL follow IMPLEMENTS and REFINES edges when determining ancestor relationships, configurable via the `edge_kinds` parameter.

### Rationale

Agents listing requirements for a ticket often include both specific leaf requirements and their broad ancestors, creating noise. This tool enables automated pruning to the most-specific set.

### Changelog

- 2026-07-31 | 68c20489 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | c667abd2 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | c667abd2 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *MCP Minimize Requirement Set Tool* | **Hash**: 68c20489
---

## REQ-o00070: MCP Scoped Search Tool

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a `scoped_search` tool that restricts keyword search to descendants or ancestors of a scope node.

### Assertions

A. `scoped_search(query, scope_id, direction, field, regex, include_assertions, limit)` SHALL accept a query string, scope node ID, and direction ("descendants" or "ancestors").

B. The tool SHALL restrict search results to nodes reachable from the scope node in the specified direction, including the scope node itself.

C. When `include_assertions=True`, the tool SHALL also match against *Assertion* text and include `matched_assertions` metadata on matching parent requirements.

D. The tool SHALL return an error when the scope_id is not found in the graph.

E. The tool SHALL reuse `_matches_query()` for field/regex matching logic, maintaining a single code path per REQ-p00050-D.

### Rationale

Agents exploring requirements for a ticket need to search within a relevant subgraph rather than the entire graph, which produces too many unrelated matches.

### Changelog

- 2026-07-31 | c79f263d | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 7f1e6589 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 7f1e6589 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *MCP Scoped Search Tool* | **Hash**: c79f263d
---

## REQ-o00071: MCP Discover Requirements Tool

**Level**: ops | **Status**: Active | **Implements**: REQ-p00060

The MCP server SHALL provide a `discover_requirements` tool that chains scoped search with ancestor pruning to return only the most-specific matches within a subgraph.

### Assertions

A. `discover_requirements(query, scope_id, direction, field, regex, include_assertions, limit, edge_kinds)` SHALL accept scoped search parameters plus an edge_kinds filter for ancestor pruning.

B. The tool SHALL chain `scoped_search` results through `minimize_requirement_set` to remove ancestors already covered by more-specific descendants in the result set.

C. The tool SHALL return results in scoped_search format containing only the minimal set, plus pruned items with `superseded_by` metadata.

D. The tool SHALL pass through all results unchanged when no ancestor relationships exist between matches.

E. When `scope_id` is omitted, discovery SHALL span the entire federated view.

### Rationale

Agents won't compose scoped_search + minimize_requirement_set unprompted. A single wrapper tool is the most discoverable interface for finding the most-specific requirements within a subgraph.

A mandatory scope demands the answer to the question being asked: a caller who does not yet know which subtree is relevant must already know which subtree to scope to, and the natural way to find that is grep — which defeats the tool. Optional scope (E) makes the cold-start query expressible.

### Changelog

- 2026-07-31 | 128366d2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | 4ce416ba | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: make discovery scope optional (E)
- 2026-05-11 | fea647ee | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | fea647ee | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *MCP Discover Requirements Tool* | **Hash**: 128366d2
---

## REQ-o00073: MCP Org-Wide Context

**Level**: ops | **Status**: Draft | **Implements**: REQ-p00060, REQ-p00081, REQ-p00082

The MCP server SHALL serve the caller's full workspace context — including repositories outside the primary — with provenance on every cross-repository result and authority limits enforced at the tool surface.

### Assertions

A. The MCP server SHALL start and serve read tools when invoked outside any repository, provided the invocation path resolves to a declared workspace.

B. Read-tool results that include content owned outside the primary repository SHALL carry the owning repository, its federation role, and its freshness — live working copy, or baseline with its capture time.

C. Read tools SHALL accept a caller option selecting the baseline view of a repository that a local working copy currently shadows.

D. Mutation tools SHALL reject any target owned by a reference-role repository, returning an error that names the repository and its role and applying no change.

E. The view served SHALL be determined by the caller's invocation context — repository membership and workspace containment — with no mode declaration required from the caller.

### Rationale

A tool that requires a judgement call before use loses to the tool that needs none — which is how grep won over the MCP tools (1.8% of requirement-shaped lookups, measured 2026-07-29). One federated view with provenance, never two tools to choose between (E). Freshness disclosure (B) matters because baselines are refreshed periodically while worktrees are live; without an as-of time, agents cite stale org requirements as current. Branch skew is a feature for "does my draft duplicate something?" (shadowed view) and a bug for "what does the org currently specify?" (baseline view) — assertion C makes both askable from the same tools. Assertion D is the MCP surface of the structural refusal specified in the federation role model.

### Changelog

- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: author MCP org-wide context requirements

*End* *MCP Org-Wide Context* | **Hash**: 346f3031
---

## REQ-o00074: Background Daemon Lifetime

**Level**: ops | **Status**: Active | **Implements**: REQ-o00075, REQ-p00083

A background daemon's lifetime SHALL be bounded by the clients using it, and it SHALL preserve and account for the work it holds when it stops.

### Assertions

A. A daemon started implicitly on behalf of a client SHALL record, at the moment it is started, a handle to that client whose disappearance the daemon can afterwards observe without the client's cooperation.

B. The client handles a daemon has recorded SHALL be observable in the state record by which clients locate the daemon.

C. A daemon started explicitly rather than on behalf of a client SHALL record no client handle, and its lifetime SHALL remain governed solely by its idle timeout.

D. A client handle SHALL be derived only from evidence available at the moment it is recorded; where nothing available yields a handle whose disappearance can be observed, the daemon SHALL record none rather than one that stands in for it.

E. A client that begins using a daemon that is already running SHALL be recorded alongside the daemon's existing clients. The client-liveness rule SHALL NOT be the cause of a daemon's termination while any recorded client still exists, and SHALL NOT leave a daemon serving once none does. A client for which no handle can be derived from the evidence available is not recorded, and does not extend the daemon's life.

F. The obligation in assertion E SHALL hold under every idle-timeout configuration, including one in which the idle timeout never expires, and SHALL NOT be discharged by client request traffic.

G. A count of pending changes a daemon discloses SHALL be the number actually pending.

H. A change applied after a daemon observed every recorded client absent SHALL count as evidence that a writer is still using the daemon, and SHALL restart the interval before termination.

I. A daemon SHALL stop only by an ending it executes: every client it knows of gone, nothing asked of it for a long time, or something outside it telling it to stop. Where it persists the changes it holds, it SHALL record how many changes it covered and the condition that triggered it.

J. While a client persists pending changes at its own request, any outstanding record of a save the daemon performed on its own, and any outstanding finding that an earlier process ended holding unwritten changes, SHALL be retired.

K. If a daemon cannot persist the changes it holds, it SHALL report the failure, retain them rather than discarding them, and SHALL NOT complete a termination it is executing.

L. The record that a daemon is holding unsaved changes SHALL cease as soon as it holds none. A daemon that finds such a record left by a process which no longer exists SHALL report that the earlier process ended holding changes it never wrote, and SHALL NOT allow that finding to be read as a statement about what it is holding itself.

M. While a daemon is holding a termination open for a grace interval, it SHALL disclose how many changes are pending and the deadline at which it will persist them and stop.

N. Where a client's use of a daemon does not result in a recorded handle — because none could be established, or because one the client declared could not be used — the tool SHALL disclose that the daemon's lifetime is not bound to that client, and SHALL name what the client can supply to bind it. The disclosure SHALL NOT repeat for every use.

O. While a daemon has a recorded client that still exists, its idle timeout SHALL NOT be the cause of its termination; the idle timeout governs a daemon with no recorded client.

### Rationale

A daemon is started implicitly to serve one client and is then detached from it, so nothing in the running process can afterwards say whose disappearance should end it. The handle has to be handed over at start or it is unrecoverable, which is why assertion A fixes the moment rather than the means. What makes a handle a handle is that its disappearance can be observed without the client's cooperation: a client that crashes revokes no token and sends no goodbye, so anything that depends on the client acting at the end fails the case the requirement exists for. A process identifier tested by signalling it, and a connection the client holds open, both satisfy that property; a declared name or label does not, because it never disappears.

Assertion C keeps the two ways a daemon comes into existence distinguishable. A daemon a person started deliberately answers to that person, not to whichever shell happened to be nearby; inferring a client for it would make deliberate starts unpredictably mortal. Assertion D is the same caution stated for the implicit path, and it refuses two different things. A guessed handle attaches the daemon's life to an unrelated process. A stand-in whose disappearance is never observable disables the lifetime rule outright, leaving a daemon that nothing can end. Recording none is better than either, because none degrades to the existing idle-timeout behaviour.

Assertion B exists because a lifetime rule nobody can inspect cannot be diagnosed. The record that already tells clients where the daemon is is the place an operator will look to ask why one is, or is not, still running. What is published there has to describe each handle rather than assume its kind: a list that can only hold process identifiers leaves a session-held client watched and invisible, which is the failure B exists to prevent.

Assertion E is stated over clients rather than over the one that happened to start the daemon because a daemon is deliberately shared. It serves several clients at once, and it outlives the client that started it precisely so that a later one can pick it up; a lifetime tied to the starter alone would shut the daemon down underneath somebody who is actively using it. E binds the client-liveness rule's own behaviour rather than promising how long a daemon lives, because the lifetime a daemon actually has is the shortest of client liveness, the idle timeout, and an explicit stop. Read as a promise, an idle timeout that expires and an operator who stops the daemon would each breach it, and assertion K — which keeps a daemon alive precisely while it cannot write what it holds — would contradict it. Read as a bound, all of them stand: client liveness never ends a daemon that still has a client, and never leaves one serving once it has none.

E's last sentence follows from D. A client whose handle cannot be derived from the evidence available — a batch or continuous-integration shell with no controlling terminal, a harness that declares nothing, a platform that offers no such evidence — cannot be recorded without inventing a handle, which D forbids; and refusing to serve it instead would make the daemon a dependency, which REQ-o00075-G forbids. The exposure that leaves is bounded on both sides: a client that writes is covered by assertion H, and a daemon that stops while holding work persists it. What remains is an unidentified read-only client losing its daemon and paying for one rebuild.

Assertion F exists because the two obvious places to hang the check are both wrong: an idle timeout resets on every request, so a client that merely polls holds an abandoned daemon open forever, and an idle timeout can be configured never to expire at all, which would disable the check outright. The obligation is therefore stated against the daemon's own passage of time rather than against its traffic. Assertion H covers what liveness checks cannot see — a client for which no handle could be derived still leaves evidence when it writes — and it does so without reopening the loophole F closes, because reading changes nothing.

Assertion I enumerates the endings a daemon executes, and its point is that the list is complete: every way a daemon stops of its own accord is one of these three, so all of them fall inside the preservation rule REQ-p00083-A states rather than outside it. Which of them applies says nothing about the value of what the daemon is holding, so none of them may be the occasion on which work is quietly destroyed. What I adds beyond that is the content of the daemon's own account — how many changes it covered, and which condition triggered it — because a successor and a returning client both need to know how much arrived this way and why. The general obligations to preserve, to honour an instruction to discard, and to disclose the record are REQ-p00083's assertions A, B and C, and are not restated here.

The account is facts, not a characterisation. The changes themselves were authored deliberately, one at a time, by whoever made them; the only thing that happened without anyone asking is the save. Nor does the absence of a client tell the daemon anything about the work: a client can vanish because it finished, because it crashed, because a network dropped, or because a machine slept, and these are indistinguishable from inside the daemon. Naming the condition that triggered the save therefore reports what the daemon observed, and treating it as evidence of intent would be exactly the substitution of a conclusion for an observation that REQ-p00019 prohibits.

Assertion J refines the general retirement rule at REQ-p00083-H with the second record a daemon can leave, which exists only because a daemon can be succeeded by another process in the same working tree. A client that persists at its own request retires both: the daemon's account of a save it performed unasked, and any outstanding finding that an earlier process ended holding work it never wrote. Once the files have been written, both describe a state that no longer stands.

Assertion K covers the case where preservation is impossible: a daemon that cannot write must not resolve the deadlock by destroying the work instead, since that converts an infrastructure failure into data loss. It reports, retains, and does not treat the ending it is executing as complete. K binds only the terminations the daemon executes, because a stop signal it does not control cannot be declined; a rule that told a daemon not to complete such an ending would demand something no process can do and would make correct behaviour a permanent conformance failure. Work lost to an ending the daemon does not execute is disclosed under REQ-p00083-F rather than prevented here.

Assertion L keeps the record of held work honest at both ends. It ceases as soon as the daemon holds nothing, because a marker that outlives the condition it describes turns every later reader into a false alarm. The rest of L answers a problem particular to a daemon: the same evidence read at two moments answers two different questions — what this daemon holds now, and what an earlier one was holding when it died — and a successor in the same working tree is the reader who meets both. One that cannot tell which question was answered has learned nothing from either, so a record left by a process that no longer exists is reported as a statement about that process. When the record must be written, and the obligation to disclose the loss at all, are REQ-p00083's assertions E and F.

Assertion G's honest-count clause is there because a disclosure that understates what is at stake is REQ-p00019's silent-substitution failure wearing a warning's clothes. G carries no deadline because a deadline exists on only one of the paths by which a daemon stops, and that path is assertion M's: a daemon that has seen its clients go holds the termination open for a grace interval, and during that interval there is a future moment to name. An idle timeout and an external stop persist what is held and stop at once, so obliging them to disclose a deadline would oblige them to invent one, while the count remains meaningful everywhere.

Assertion N exists because a lifetime that is not bound to the client is invisible from the client's side. A daemon that lingers past its usefulness on an idle timeout, and one that dies before the job still using it, both look like arbitrary behaviour unless the client is told which regime it got. Naming what the client can supply is what makes the declared handle discoverable at all — a harness author has no other way to learn that a handle can be declared, or what it must contain — and it turns a bare condition into something actionable, since a job that publishes its runner's handle once at setup gets a daemon whose lifetime matches the job. The disclosure is a warning rather than a refusal at either of the two points a refusal could sit: refusing the command would make the daemon a dependency, which REQ-o00075-G forbids, and declining to use a daemon at all would tax the environments least able to act on the message. It does not repeat for every use, because a warning attached to every invocation is one readers learn to skip, and the second occurrence carries no information the first did not.

Assertion O settles which of a daemon's bounds answers when two of them disagree. Going quiet is not going away: a client that applies a change and then reasons about the next one sends nothing for long stretches, and an idle timeout counts that silence exactly as it counts an empty room. A timeout that cannot tell the two apart takes the daemon from the client least able to notice — one that is mid-task, holding work it has not written, and about to find its server gone. So which regime governs is decided by whether anyone is recorded as using the daemon, not by how recently they last spoke. The cost is real and is stated rather than hidden: a daemon with a live client outlives the idle timeout configured for it, for as long as that client exists. The client-liveness rule is what still bounds it, and assertion E is what makes that bound sufficient — a daemon whose recorded clients are all gone is ended by the same rule that spared it while one remained.

### Changelog

- 2026-08-10 | dace8fb0 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-08 | 870802ca | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-08 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-12: state the lifetime bound one-directionally, scope the deadline and failure clauses, and refine against the new parents
- 2026-08-08 | 1c2cc1cf | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-08 | f47c8b15 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-08 | 81945155 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-07 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-12: author background daemon lifetime, client-liveness, and unattended-persistence invariants

*End* *Background Daemon Lifetime* | **Hash**: dace8fb0
---

## REQ-o00075: Shared Graph Daemon

**Level**: ops | **Status**: Active | **Implements**: REQ-p00050

The tool SHALL be able to serve a working tree's graph from a process shared by the clients working in that tree.

### Assertions

A. The tool SHALL be able to serve a working tree's graph from a process that outlives the individual commands and sessions that use it.

B. Such a process SHALL be scoped to one working tree: at most one SHALL serve a given working tree at a time, so that every writer in that tree acts on one graph and no writer acts on a graph another writer cannot see.

C. Separate working trees SHALL be served independently, each by its own process holding its own graph, whether or not they belong to the same repository.

D. Such a process SHALL serve several clients at once, and a client SHALL be able to begin using a process that another client started.

E. A client SHALL be able to locate the process serving the working tree it is operating in, without prior arrangement; a process SHALL be discoverable for as long as it is serving, and what a client locates SHALL describe the process it would reach.

F. Such a process SHALL be startable either implicitly, on behalf of a client that needs it, or explicitly by an operator, and which of the two brought it into existence SHALL remain determinable for as long as it runs.

G. Every operation the tool offers SHALL remain available when no such process is running or its use is declined.

### Rationale

Rebuilding the graph once per command is the cost this process exists to amortise, and holding one graph is also what makes guarding concurrent writers meaningful at all — those guards are REQ-o00062's subject and are not restated here.

The unit of exclusivity is the working tree, not the repository. A worktree holds its own branch and its own unpersisted work, so two trees are two graphs: a shared process would answer one tree's questions from another tree's files, and would hold one tree's uncommitted work under the other's identity. Assertion C states that isolation affirmatively rather than by silence, because it is the property a future shared-baseline optimisation must be reconciled against — sharing derived read-only state across trees is compatible with C, sharing the mutable graph is not. The redundant-parse cost of one process per tree is accepted where the federation rules record it, and is not re-argued here.

Assertion G keeps the process an accelerator rather than a dependency: a tool whose correctness requires a background process fails whenever that process cannot start, and every path served by the daemon has a path that does not need it.

Assertion F fixes only that the origin stays determinable. The consequence — that the two origins carry different lifetimes — is REQ-o00074's subject.

REQ-p00005-F obliges associate paths to resolve from the canonical, non-worktree repository root so cross-repository paths stay valid when working from a worktree. That governs where a path points, not what a process serves. The two roots answer different questions, and keying a serving process on the canonical root would collapse the isolation assertion C requires.

### Changelog

- 2026-08-08 | 1fd622fe | - | Michael Lewis (<michael@anspar.org>) | TOOL-12: introduce the shared per-working-tree graph daemon
- 2026-08-08 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-12: introduce the shared per-working-tree graph daemon

*End* *Shared Graph Daemon* | **Hash**: 1fd622fe
