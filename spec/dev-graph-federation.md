# Graph Federation Development Requirements

## REQ-d00200: FederatedGraph Read-Only Delegation

**Level**: dev | **Status**: Active | **Implements**: REQ-p00005, REQ-p00050

FederatedGraph SHALL wrap one or more TraceGraph instances, each paired with its own configuration and repo root, delegating all read-only TraceGraph methods with documented federation strategies.

### Assertions

A. FederatedGraph SHALL wrap one or more TraceGraph instances via RepoEntry dataclass containing: name, graph (TraceGraph | None), config (ConfigLoader | None), repo_root (Path), git_origin (str | None), error (str | None).

B. FederatedGraph.from_single() classmethod SHALL create a federation-of-one from a single TraceGraph, config, and repo_root, using "root" as the default repo name.

C. All read-only TraceGraph public methods SHALL be explicitly implemented on FederatedGraph with a strategy comment (by_id, aggregate, or special).

D. by_id strategy methods (find_by_id, has_root) SHALL look up the owning graph via an internal ownership mapping and delegate to the correct sub-graph.

E. aggregate strategy methods (iter_roots, all_nodes, node_count, root_count, iter_by_kind, nodes_by_kind, all_connected_nodes, orphaned_nodes, has_orphans, orphan_count, broken_references, has_broken_references, iter_unlinked, iter_structural_orphans, deleted_nodes, has_deletions) SHALL combine results from all sub-graphs.

F. Aggregate methods SHALL skip repos with graph set to None (error-state repos).

G. repo_for(node_id) SHALL return the RepoEntry for the graph owning that node. config_for(node_id) SHALL return the config for that node's owning repo.

H. iter_repos() SHALL yield all RepoEntry objects including error-state repos.

### Rationale

FederatedGraph provides config isolation for multi-repo builds while presenting a unified API to consumers. The federation-of-one pattern ensures all code paths go through FederatedGraph, preventing accidental direct TraceGraph usage. Error-state repos (missing associates) are represented in the federation but skipped during aggregation, preserving graceful degradation.

### Changelog

- 2026-07-31 | 06b84d97 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 72471144 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 72471144 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *FederatedGraph Read-Only Delegation* | **Hash**: 06b84d97
---

## REQ-d00201: FederatedGraph Mutation Delegation

**Level**: dev | **Status**: Active | **Implements**: REQ-d00200, REQ-p00050

FederatedGraph SHALL delegate all mutation operations to the appropriate sub-graph, maintain a unified mutation log across repos, and update internal ownership when IDs change.

### Assertions

A. by_id mutation methods (rename_node, update_title, change_status, delete_requirement, add_assertion, delete_assertion, update_assertion, rename_assertion, rename_file, fix_broken_reference) SHALL look up the owning repo via `_ownership`, delegate to the sub-graph, and update `_ownership` when IDs change.

B. FederatedGraph SHALL maintain a unified mutation log that records lightweight entries pointing to the repo name and sub-graph mutation ID, providing chronological ordering across all repos.

C. undo_last() SHALL read the federated log to identify which repo was last mutated, then delegate undo to that sub-graph. undo_to() SHALL undo back to a specific mutation ID across repos.

D. add_requirement SHALL accept a target_repo parameter to specify which sub-graph receives the new node. If omitted for federation-of-one, it SHALL default to the root repo.

E. Cross-graph mutation methods (add_edge, delete_edge, change_edge_kind, change_edge_targets, move_node_to_file) SHALL resolve source and target repos independently.

F. The mutation_log property SHALL return a log object whose iter_entries() yields full MutationEntry objects from sub-graphs in federated chronological order, compatible with existing consumers.

G. clone() SHALL perform federation-aware deep copy: deep-copy each sub-graph independently, then rebuild cross-graph edges and the ownership map.

### Rationale

Mutation delegation preserves TraceGraph's existing mutation+undo logic while adding federation awareness. The lightweight federated log avoids duplicating MutationEntry data. Ownership tracking ensures by_id lookups remain O(1) after mutations.

### Changelog

- 2026-07-31 | 85081cae | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 1a0942a4 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 1a0942a4 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *FederatedGraph Mutation Delegation* | **Hash**: 85081cae
---

## REQ-d00202: Associates Config Loading

**Level**: dev | **Status**: Active | **Implements**: REQ-p00005

The config system SHALL parse `[associates.<name>]` sections from `.elspais.toml` to declare federated repository associations.

### Assertions

A. A repository's associate declarations SHALL be read from its `[associates]` sections, each declaration yielding the associate's name together with its path, its namespace, and its git remote.

B. A declaration SHALL require a path and a namespace. The git remote SHALL be optional and SHALL serve clone assistance only.

C. When no `[associates]` section exists in config, `get_associates_config()` SHALL return an empty dict.

D. When an associate declares its own `[associates]` section, those declarations SHALL be resolved transitively into the same federation, so that the tool works identically from any repository in a dependency chain.

E. When directed dependency declarations form a cycle, the build SHALL report a configuration error naming the declaration path that forms the cycle.

F. When the same repository is reachable through more than one dependency chain (a diamond), the federation SHALL resolve it to a single entry and SHALL NOT report a cycle.

G. The federation SHALL identify a repository across discovery paths by its git origin, not by its filesystem path or declared name.

H. When two federated repositories both claim the same requirement ID, the build SHALL fail with an error naming the ID and both repositories.

I. When scanning directories for candidate associates, a directory whose elspais configuration fails to parse or validate SHALL be skipped without aborting the scan, and each skip SHALL be reported with the directory path and the reason. Directories without an elspais configuration are not candidates and need no report.

J. When two distinct repositories would enter one federation under the same declared name, the build SHALL fail with an error naming both repository paths and the declaration chain that reached each.

K. When two distinct repositories would enter one federation declaring the same namespace, the build SHALL fail with an error naming both repository paths and the declaration chain that reached each.

L. When the repository at an associate's declared path declares a namespace other than the one the declaration names, the build SHALL fail with an error naming the path, the namespace the declaration named, and the namespace found.

### Rationale

Associates are declared in `.elspais.toml` using a structured TOML section. Each associate specifies a relative filesystem path, a namespace, and an optional git remote URL. Transitive resolution (assertion D) is what lets the tool work from any repository in a dependency chain rather than from the root alone, and it is what allows an org-policy repository reachable only through a chain to be federated at all. Directed cycles are a genuine error because dependency direction drives resolution order; diamonds are convergence, not cycles, and the git-origin identity rule (assertion G) is what makes the two distinguishable. Disjoint ID spaces (assertion H) are a precondition of federation rather than a preference: a reference resolves to a repository by asking which one claims the identifier, so two claimants make the answer arbitrary.

A repository declares everything it directly needs in order to resolve on its own, without regard to what its associates happen to declare. Redundancy between those declarations is therefore expected rather than exceptional, and assertion F is what makes it harmless: a repository reached both directly and through a chain resolves to one entry, so declaring it twice is idempotent. Pruning a declaration because some other repository already reaches it would couple the two configurations and break the pruned repository's own invocations.

Name uniqueness (assertion J) becomes an obligation only once declarations from several repositories are combined. A single declaration table cannot collide with itself, so under root-only resolution uniqueness was guaranteed by TOML's own syntax. A federation keys repositories by name, so two repositories arriving under one name would leave only the later of them reachable — the earlier repository's requirements would resolve against the wrong configuration and its graph would never be read at all. Failing is the honest outcome because the alternative is a silent partial federation.

A namespace answers whose identifiers these are, so a federation in which two repositories claim one namespace can answer nothing — the same argument disjoint requirement IDs rest on under H. A repository owns its own namespace; an associate declaration does not name a second one but states the namespace the declaring repository expects at that path, so a mismatch means the declaration points somewhere its author did not intend. Both are declaration-time failures, reported before any graph is built, because a federation assembled on an ambiguous or mistaken namespace produces wrong answers rather than missing ones.

### Changelog

- 2026-08-10 | 0522f86c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | b599e6ec | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: require a namespace to be unique across a federation (K) and to match the repository the declaration points at (L)
- 2026-08-08 | b599e6ec | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | 9b0f1733 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | 2a648c8e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | 1bc0e4b5 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | de074317 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38/TOOL-33: replace the transitive-associates hard error (D) with transitive resolution; add cycle (E), diamond (F), git-origin identity (G), and disjoint-ID-space (H) rules
- 2026-07-30 | 0379ce9c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 479dcbb8 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 479dcbb8 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Associates Config Loading* | **Hash**: 0522f86c
---

## REQ-d00203: Multi-Repo Build Pipeline

**Level**: dev | **Status**: Active | **Implements**: REQ-d00200, REQ-p00005

The `build_graph()` factory SHALL build separate TraceGraph instances per repository when associates are configured, constructing a multi-repo FederatedGraph.

### Assertions

A. When `[associates]` config is present, `build_graph()` SHALL create a separate `TraceGraph` per associate repo, each with its own config-derived resolver.

B. Each associate's config SHALL be loaded from its own `.elspais.toml`, and any associates it declares SHALL be discovered and built into the same federation.

C. Missing associate paths SHALL produce error-state `RepoEntry` with `graph=None` and a descriptive `error` message (soft fail).

D. A `strict` parameter on `build_graph()` SHALL cause missing associates to raise an error instead of soft-failing.

E. The root repo and all valid associates SHALL be combined into a single `FederatedGraph` with the root repo as `_root_repo`.

### Rationale

Per-repo building ensures config isolation: each repo's hierarchy rules, format rules, and hash mode apply only to its own nodes. Error-state entries preserve visibility of missing associates in health reports without blocking the build.

### Changelog

- 2026-07-31 | 957568b6 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | 5544c03c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38/TOOL-33: amend B — transitive associates are built into the federation instead of being validated against
- 2026-05-11 | 31e019a1 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 31e019a1 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Multi-Repo Build Pipeline* | **Hash**: 957568b6
---

## REQ-d00204: Per-Repo Health Check Delegation

**Level**: dev | **Status**: Active | **Implements**: REQ-d00200, REQ-p00002

Health checks that depend on per-repo configuration SHALL run once per federated repo using that repo's own config, ensuring config isolation in multi-repo federations.

### Assertions

A. Config-sensitive health checks (hierarchy levels, format rules, reference resolution, structural orphans, changelog checks) SHALL run per-repo using each repo's own `ConfigLoader` from `RepoEntry.config`.

B. Non-config-sensitive health checks (file parseability, duplicate IDs, hash integrity, index staleness) SHALL run once on the full `FederatedGraph`.

C. Per-repo checks SHALL produce a separate `HealthCheck` per repo per check type, with `HealthFinding` entries annotated with a `repo` field identifying the source repository.

D. `HealthFinding` SHALL support an optional `repo` field (str | None) for per-repo attribution.

E. `check_broken_references` SHALL distinguish within-repo broken references (error severity) from cross-repo broken references where the target repo is in error state (warning severity with clone assistance info).

F. `run_spec_checks` SHALL accept a `FederatedGraph` and iterate `iter_repos()` for config-sensitive checks, using `FederatedGraph.from_single()` to create per-repo sub-federations.

G. A non-config-sensitive check SHALL detect requirement cycles (a requirement reachable as its own descendant through *Traceability* edges) and report each detected cycle as a failing finding naming the requirements that form the cycle, so that a cyclic graph surfaces as a clear diagnostic rather than crashing downstream traversals.

H. A finding about a reference that fails to resolve SHALL be attributed to the repository declaring the reference, not to the repository that owns (or would own) the target.

I. The health-check exit status SHALL be computed exclusively from findings attributed to repositories within the invocation's write scope — the primary repository plus dependency repositories marked writable — so that a finding the caller cannot fix never fails the run.

J. Findings attributed to repositories outside the invocation's write scope SHALL be available for display at the caller's option, marked with their owning repository.

### Rationale

Without per-repo delegation, all nodes are validated against the root repo's config. When repos have different hierarchy rules, format rules, or changelog policies, this produces false positives (root config rejects valid associate nodes) or false negatives (root config allows invalid associate nodes). Per-repo delegation ensures each repo is validated by its own rules.

Assertions H–J realize REQ-p00082's verdict-scoping invariants for the checks surface: a broken reference from the caller's repository *into* an org repository is the caller's bug and must gate the caller's change, while a malformed requirement *inside* a repository the caller cannot write to must never turn the command into noise by failing runs the caller cannot fix.

### Changelog

- 2026-07-31 | 7e0f5586 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | 32a98213 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: add finding-ownership attribution (H) and write-scope verdict scoping (I, J)
- 2026-06-18 | 844d12d1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-05-11 | 2313140d | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 2313140d | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Per-Repo Health Check Delegation* | **Hash**: 7e0f5586
---

## REQ-d00252: External Library Integration via Integrates Keyword

**Level**: dev | **Status**: Active | **Implements**: REQ-p00005

A requirement MAY declare that its implementation is provided by a requirement in a configured associate (external library) repository, so that a reusable library need not contain references to any specific consumer.

### Assertions

A. A requirement in a spec file MAY declare an `Integrates:` metadata field naming one or more requirement IDs in a configured associate repository; the field SHALL be parsed and stored on the requirement node and rendered back verbatim.

B. The `Integrates:` keyword SHALL be valid only in spec files; in code, test, and journey files it SHALL NOT create a *Traceability* edge.

C. When the resolved target of an `Integrates:` reference belongs to the same repository as the declaring requirement, the build SHALL report it as a broken reference.

D. When the associate owning an `Integrates:` target participates in the federated build, the build SHALL wire an INTEGRATES edge from the declaring requirement to the target library node such that the declaring requirement counts as implemented and inherits the library node's implemented and passing coverage (result-verified or line-coverage-credited), while the library's own source files SHALL remain unmodified.

E. When an `Integrates:` target cannot be resolved, the build SHALL report a broken reference if a configured associate claims the target's ID format but lacks the ID, and SHALL record a presumed-foreign reference that does not fail the build if no configured associate claims the ID format.

F. Coverage inherited through `Integrates:` edges SHALL count toward the declaring requirement's implemented status in coverage reports (so an integrating requirement is not reported as an uncovered gap), and coverage reports SHALL summarize integrated requirements' implemented and passing coverage (result-verified or line-coverage-credited) grouped by the owning associate, with a federation total.

G. The generic presumed-foreign determination applied after cross-repo wiring to any broken *Traceability* reference that does not already carry a diagnostic (independent of the `Integrates:`-specific determination in assertion E) SHALL NOT mark a reference foreign when the federation has no configured associates, since there is no other repository the reference could belong to. It also SHALL NOT mark a reference foreign when the target's leading token matches the declaring repo's own configured namespace and no configured associate declares that same namespace; such a reference is a malformed same-repo reference, not a cross-repo one, and SHALL remain a hard broken reference whose cause is named.

K. A cause is named by recording the code that identifies it together with the file and the line the reference was written on, where that code's meaning is documented for a reader. Prose accompanying a code SHALL NOT name a cause the code does not.

### Rationale

K settles what naming a cause requires, because the obligation was being met by a sentence and a sentence cannot be relied on to stay true. A fixed string that reads "check the assertion separator" is correct for the defect it was written for and wrong for every other defect that reaches the same code path — and it went wrong exactly when the tool became able to say something more precise, which is the worst moment for a report to start misdescribing what it found. What is durable is the code: it is decided where the defect is decided, it carries no claim beyond its own definition, and a reader who does not know it can look it up. Recording where the reference was written is what makes it actionable, and documenting the code is what makes it legible; a code without either is an opaque string, and prose that contradicts one is worse than no prose at all.

The bottom-up reference model (`Implements:` authored on the implementer) would force a reusable library to name each consumer's requirement IDs, coupling the library to its consumers and breaking isolated builds. `Integrates:` is the top-down inverse: authored and stored on the consumer, it points into the library and is wired as a distinct INTEGRATES edge during federation. A dedicated edge kind keeps the library's `Implements:` derivation clean (no consumer IDs leak into library files on render), while contributing to coverage like IMPLEMENTS. Passing status (the result-verified or line-coverage-credited union, REQ-d00258-B) propagates by a live-query overlay that reads the library node's own metrics, consistent with the existing cross-repo inheritance mechanism.

### Changelog

- 2026-08-16 | be93221f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-16 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: naming a cause means a recorded code with its file and line and a documented meaning, not a fixed sentence (K)
- 2026-07-31 | 8e07589c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | d9d4bc98 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | 425d61aa | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-31 | d1f691f0 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-31 | b576d134 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash, add missing changelog section

*End* *External Library Integration via Integrates Keyword* | **Hash**: be93221f
---

## REQ-d00253: Federation Write/Generation Scope

**Level**: dev | **Status**: Active | **Implements**: REQ-d00200

Associate repositories SHALL affect only read and validation surfaces by default; the write and generation surfaces SHALL be primary-repo-only unless explicitly opted in via the `[federation]` config table.

### Assertions

A. The `[federation]` config table SHALL expose `write_associates` and `index_associates`, both defaulting to false.

B. `elspais fix` SHALL write spec files only in the primary (root) repo unless `federation.write_associates` is true; with it false, primary-repo output SHALL be byte-identical whether or not an associate is configured.

C. Generated `INDEX.md` and `term-index.md` SHALL contain only primary-repo requirements and terms unless `federation.index_associates` is true.

D. MCP mutation tools SHALL reject mutations targeting associate-owned nodes when `federation.write_associates` is false, returning a read-only error and applying no in-memory change.

E. Write and index eligibility SHALL be declarable per associate entry, with the `[federation]` table values serving as defaults for entries that do not declare their own.

F. When `elspais fix` detects fixable issues in associate-owned content it will not write, its report SHALL distinguish those from applied fixes by prefixing each such line with `[skipping]`; the output SHALL never claim an associate-owned fix was applied.

### Rationale

Federation is fundamentally a read and validation aggregation: associates provide cross-repo reference resolution and coverage inheritance without surrendering write authority. Making the write and generation surfaces primary-repo-only by default prevents `elspais fix` and MCP mutations from silently editing files in repositories the operator does not own. The `[federation]` opt-in flags keep the safe default while allowing deliberate multi-repo authoring when an operator owns every associate.

Global booleans alone cannot express the common cross-repo workflow — enable writes for exactly one associate that points at a matching worktree while everything else stays read-only — which is why eligibility is per-entry with the global table as default (assertion E). Note `index_associates` governs only associate-repo *references* in the term index and collection manifests; term definitions federate regardless.

### Changelog

- 2026-08-02 | f454041e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | 6bd9cd1d | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | f145d18a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | e3cca300 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | 9a6e0bd7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: add per-entry write/index eligibility (E)
- 2026-06-01 | 28c8c538 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: add missing changelog section

*End* *Federation Write/Generation Scope* | **Hash**: f454041e
---

## REQ-d00260: Workspace Registry and Federated View Assembly

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00081, REQ-p00082

Workspace membership SHALL be declared once per machine in a per-user registry, and SHALL feed the same federation assembly as directed dependency declarations, under one set of identity and deduplication rules.

### Assertions

A. The tool SHALL read workspace declarations from a per-user registry file at a canonical location outside any repository.

B. The tool SHALL honor an environment-variable override for the registry file location.

C. Each workspace declaration SHALL name a root directory and the workspace's member repositories.

D. The tool SHALL resolve the caller's workspace by path containment: a caller whose working path lies beneath a declared workspace root belongs to that workspace, including checkouts and worktrees anywhere beneath that root.

E. Workspace membership SHALL be undirected: a repository is federated as a member without declaring, or being declared by, any other member repository's configuration.

F. When the caller's repository belongs to a resolved workspace, the federated view SHALL contain every workspace member in addition to the associates declared by the repository's own configuration.

G. When the same repository — identified by git origin — is reachable both as a local working copy and as a workspace baseline entry, the federated view SHALL contain the local working copy wholesale and drop the baseline copy, never a merge of the two.

H. A caller SHALL be able to request the baseline view of a repository that a local working copy currently shadows.

I. A workspace member that fails to load SHALL be represented in the federated view as an error-state entry naming the repository and the cause of failure.

J. The configuration fingerprint used to detect stale cached graphs and daemons SHALL cover the content of the workspace registry file.

K. The tool SHALL support a boolean workspace-expectation setting in repository configuration, defaulting to false.

L. When the effective workspace-expectation setting is true and no workspace resolves for the caller, the tool SHALL report an error naming the registry location consulted, rather than serving a repository-local view.

M. When the registry location is explicitly configured via the environment override and the file cannot be read, the tool SHALL report an error rather than serving a view without the registry.

N. When the registry file exists but cannot be parsed, the tool SHALL report an error naming the file and the parse failure, rather than treating the registry as absent.

O. Registry-related errors — unmet workspace expectation, unreadable registry, or unparsable registry — SHALL direct the user to the tool's own workspace documentation for remediation.

### Rationale

The registry is the second discovery source beside `[associates]` (directed dependencies): membership is flat and undirected, so cycles are impossible by construction, while dependency direction — which drives resolution order and base/overlay relationships — stays in `[associates]` where cycles remain a genuine error. Both sources feed one assembly keyed by git origin, which is stable across worktrees and clones where path and name are not. This is what dissolves the symmetric-configuration circularity: neither of two mutually-dependent repos needs to declare the other for membership.

A per-user file solves what committed config cannot: associate paths are machine-specific, so org membership cannot live in `.elspais.toml`; one list per machine replaces one list per repo per machine; a workspace root is addressable even though it is not a repository (REQ-p00081-E); and CI points the environment override at a generated file resolving that job's checkout paths.

Shadowing (G) serves "does my draft duplicate something?"; the explicit baseline request (H) serves "what does the org currently specify?" — same view, two legitimate freshness choices, distinguished by provenance labels rather than by a second tool. Error-state entries (I) uphold REQ-p00081-D: a repository that fails to load must narrow-and-say-so, never silently vanish from answers.

The workspace-expectation setting (K, L) closes the registry's bootstrap hole: the registry is itself an omittable per-machine file, so without a signal the tool cannot distinguish "this machine legitimately has no workspaces" (an outside user of the tool — erroring would be wrong) from "a workspace was expected and the registry is missing" (the entire org layer silently vanishing from every answer). A committed `true` travels with every clone of an org-governed repository, so a fresh machine or a CI job without registry provisioning fails loudly instead of validating against a narrower corpus, while repositories outside any organization never see the error. The standard local-configuration override applies, serving the same purpose it does for associates (e.g. pointing an associate at a worktree during joint work): a developer can locally override the expectation when deliberately working outside the workspace. The error text points at the tool's own workspace documentation (O), which explains registry provisioning generically — which workspace to join and where an organization keeps its canonical registry content is organizational onboarding knowledge, not this tool's concern. The companion error checks (M, N) and the unconditional scope disclosure on every surface (REQ-p00081-F) cover the remaining silence: a pointed-at-but-unreadable or corrupt registry is never equivalent to "no workspaces", and even the legitimate no-workspace case is visibly labeled repo-local rather than left ambiguous.

Known deviation, accepted 2026-07-29: redundant-work cost (invariant C1 — the same unchanged content is not re-parsed once per caller) is *not* required here — per-worktree daemons each parse every workspace repo. Accepted because this is on-developer-machine work at tolerable cost; revisit if it becomes noticeable, in which case the known answer is a single always-on daemon parsing the org baseline once and sharing read-only baseline graphs by reference across per-caller views.

### Changelog

- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-37: inline design-doc content; the scaffolding doc is retired
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: registry-absent decision — workspace-expectation setting (K, L) plus registry error checks (M, N)
- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: author workspace registry and view assembly requirements

*End* *Workspace Registry and Federated View Assembly* | **Hash**: 510a0f67
---

## REQ-d00261: Federation Role Model

**Level**: dev | **Status**: Draft | **Implements**: REQ-d00253, REQ-p00082

Every repository in a federated view SHALL carry a role that determines its treatment per surface, replacing the single root-versus-associate axis.

### Assertions

A. Each repository in a federated view SHALL carry exactly one role: primary (the caller's repository), dependency (a directed associate declared for resolution and coverage), or reference (a workspace member present for resolution and discovery only).

B. The graph layer SHALL refuse any mutation whose target node is owned by a reference-role repository, independent of any configuration setting.

C. Search and discovery surfaces SHALL include repositories of every role, labeling each result with the owning repository's role.

D. Generation surfaces — index, glossary, and document compilation — SHALL include only the primary repository plus dependency repositories marked indexable.

E. Coverage rollups SHALL credit cross-repository coverage exclusively along declared *Traceability* edges, so that adding a repository to the federated view alters no coverage number by membership alone.

### Rationale

Reference repositories exist so cross-cutting obligations resolve and surface (REQ-p00081, REQ-p00082-G/H); writing into one from a consuming repository is incoherent under any setting, which is why refusal is structural at the graph layer (B) rather than a flippable boolean — configuration can widen dependency writability (REQ-d00253-E) but can never make a reference repository writable. Health-check treatment per role is specified in the per-repo health delegation requirement (finding attribution and write-scope verdicts); this REQ deliberately does not restate it. Assertion E is why membership growth is safe: a reference repository contributes coverage only where a repository explicitly declares a *Traceability* relationship into it.

### Changelog

- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: author federation role model

*End* *Federation Role Model* | **Hash**: fb8db8a9
---

## REQ-d00269: Cross-Repository Coverage Credit

**Level**: dev | **Status**: Active | **Implements**: REQ-p00005

Evidence recorded in one repository of a federation credits the requirement it names in another. A federated view reports the coverage its declared *Traceability* edges justify, whichever repository each end of an edge lives in.

### Assertions

A. Coverage SHALL be computed after every cross-repository *Traceability* edge has been wired, so that no coverage number depends on the order in which a federation was assembled.

B. A cross-repository *Traceability* edge SHALL carry the same shape as the equivalent same-repository edge, including the *Assertion* labels the reference targets, so that one coverage computation reads both.

C. An identifier owned by any repository in a federation SHALL be recognised in the code and test annotations of every repository in that federation.

D. A *Traceability* reference whose target identifier cannot be resolved SHALL be recorded as a broken reference, whatever kind of file it appears in.

E. A *Traceability* keyword SHALL introduce a reference only where it is the first content of a comment or of a metadata line, with the separator that ends the keyword abutting it. The same keyword occurring elsewhere in a line, or within inline-quoted or fenced text, SHALL NOT introduce a reference. What a keyword is SHALL NOT depend on its case.

F. Every reference recognised under E that produces no relationship SHALL be reported, at a severity the project configures among informational, warning and failing independently for each class R distinguishes.

G. The content a *Traceability* keyword introduces SHALL be a separated list of references, and each item of that list SHALL be judged on its own: an item the grammar accounts for produces its relationship, and an item it does not is reported under the class it reached. An item SHALL be matched whole, so that a reference is never resolved by an identifier found within a larger item.

H. A list whose content ends with the separator SHALL continue onto the next line that may hold reference content — the next line of the same comment block, or the next line of the same metadata block. A line holding no content, and a line whose own first content is a *Traceability* keyword, SHALL NOT be such a line. A list ending with the separator and having no such line to continue onto SHALL bind the references it holds and report the separator that introduced nothing.

J. Where a reference is spelled in a way the grammar does not accept, the report SHALL name the defect it can determine and SHALL NOT produce the relationship the reference would have produced had it been spelled acceptably.

### Rationale

Cross-repository credit is what multi-repository *Traceability* is for: a sponsor repository's tests verifying a platform requirement is the ordinary case, not an exotic one. The obligations here are separated because each fails independently and each fails silently. Computing coverage before the federation is wired starves the computation of the very edges that cross repositories (A). Wiring those edges in a shape the coverage computation does not read starves it a second time, so ordering alone is not sufficient (B). Refusing to recognise a foreign identifier in a code or test comment drops the evidence before any edge exists at all (C), which bites hardest because annotating code and tests is where cross-repository evidence is most naturally authored.

D is the diagnostic floor beneath C. A reference the tool cannot resolve is a fact about the estate that its author needs to see; discarding it silently is worse than reporting it broken, because a requirement with no evidence and a requirement whose evidence was thrown away read identically in every report.

E is what makes D decidable. A target no repository claims is by definition outside every configured grammar, so nothing about its *shape* can be trusted to say whether it was meant as a reference — guessing from the target invents findings out of prose, and an unrestricted net over this estate produced thirty-five of them from sentences that merely contain a keyword. Position is the property that can be relied on instead: a reference is written where a reference belongs, and prose that discusses one is quoted. That also gives documentation a way to name a keyword without invoking it, which a shape-based rule cannot offer at any strictness.

F exists because the honest report of an unresolvable reference is not always an error. A repository may reference a requirement that a sibling has not authored yet, and the same finding is informational to one project and a build failure to another. Severity is therefore the project's decision, while noticing is not. The decision is per class rather than for unresolvability as a whole, because the classes differ in what would resolve them: a repository nobody configured is answered by configuring it, and a name that never read as a reference is answered only by rewriting it. A project silencing the first while still hearing the second is expressing a real position, and one severity for both denies it.

E settles where a keyword may introduce a reference; G settles what it may introduce. Searching the introduced content for anything identifier-shaped reads a reference out of text that names one only incidentally — a description mentioning a requirement becomes a citation of it, and an identifier that merely contains another repository's namespace resolves to a requirement its author did not write. Both are silent: the reference resolves, so nothing reports it. Matching each item whole makes the unresolvable case visible on the channel D already provides.

Judging items one at a time does not weaken that. A defect in one item is evidence about that item, not about the list, and refusing the whole list makes a single typo cost every reference beside it — silently, since the refusal reads in every report exactly like a line nobody annotated. What must not vary with the number of items is how a reference is recognised, and matching whole is what holds that fixed.

The prohibition on shape in E is about recognition, and does not extend to describing an item on a line already recognised. Nothing about a target's shape can say whether it was *meant* as a reference, which is why position decides that; but once position has decided it, the author has said the item is a reference, and shape is the only evidence left about which kind of defect it carries. A repository declaring the namespace an item opens with is what separates an identifier of this estate written wrongly from a name belonging to a repository nobody configured, and the two send an author to different work. J keeps that separation honest in the direction that matters: describing a defect is not licence to act on the description, because a relationship built from a guess about what an author meant is indistinguishable, everywhere downstream, from one they declared.

H exists because a list long enough to need a second line is ordinary, and a form the tool neither accepts nor rejects is the worst of the three answers available. The separator already means the list has not ended, so continuation asks nothing of an author that spelling the list correctly did not already ask; and a separator with nothing after it says the same thing about a list that has, in fact, ended.

Two lines are excluded from continuing a list, and both exclusions keep continuation from overriding something that was already decided. A line whose first content is a keyword is a declaration, and E makes that the whole of what opens a reference list; letting a separator on the line above capture it would take a plainly intended declaration, read it as one item holding spaces, and lose every reference in it. A line holding no content cannot be where the list resumes either, because reading past it would mean looking further than the line that follows — and a lookahead that skips is a lookahead with no bound, which is how a list reaches content written far below it and never meant for it.

The complementary negative rule — that federation membership alone credits nothing — belongs to the federation role model and is not restated here. Together the two bound the behaviour from both sides: coverage crosses a boundary exactly where a *Traceability* edge crosses it, and nowhere else.

Coverage computed over a wired federation is idempotent, so a surface may recompute without double-counting.

A concurrency version is derived from a node's content and its outgoing *Traceability* edges, so normalizing a cross-repository edge onto the owning requirement per B brings that edge into the requirement's version. That is the correct outcome and not a side effect to be engineered away: a version guards against a writer modifying state it has not seen, and within one federated view that edge is state a writer can add. Each federated view answers for its own membership, so the same requirement legitimately carries different versions in two federations that reach it — versions are compared only against the graph that issued them, never between them.

### Changelog

- 2026-08-15 | af36a1b3 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-15 | c861d2bc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: neither an empty line nor a line opening with a keyword may continue a list (H)
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: judge list items one at a time (G); keyword recognition is case-independent with an abutting separator (E); severity per failure class (F); list continuation onto a following line (H); a named defect never yields the relationship (J)
- 2026-08-11 | 8cac4dcd | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-11 | f5855c6e | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: a keyword introduces a list of references and nothing else (G)
- 2026-08-09 | f5855c6e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-08 | bd05142f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-08 | bc8f5d09 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-08 | bd05142f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms
- 2026-08-09 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: cross-repository coverage credit

*End* *Cross-Repository Coverage Credit* | **Hash**: af36a1b3
---
