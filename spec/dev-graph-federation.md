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

A. `get_associates_config(config)` SHALL read `[associates]` sections and return a `dict[str, dict]` mapping associate name to `{path: str, git: str | None}`.

B. The `path` field SHALL be required for each associate. The `git` field SHALL be optional (for clone assistance).

C. When no `[associates]` section exists in config, `get_associates_config()` SHALL return an empty dict.

D. When an associate declares its own `[associates]` section, those declarations SHALL be resolved transitively into the same federation, so that the tool works identically from any repository in a dependency chain.

E. When directed dependency declarations form a cycle, the build SHALL report a configuration error naming the declaration path that forms the cycle.

F. When the same repository is reachable through more than one dependency chain (a diamond), the federation SHALL resolve it to a single entry and SHALL NOT report a cycle.

G. The federation SHALL identify a repository across discovery paths by its git origin, not by its filesystem path or declared name.

H. When two federated repositories both claim the same requirement ID, the build SHALL fail with an error naming the ID and both repositories.

I. When scanning directories for candidate associates, a directory whose elspais configuration fails to parse or validate SHALL be skipped without aborting the scan, and each skip SHALL be reported with the directory path and the reason. Directories without an elspais configuration are not candidates and need no report.

### Rationale

Associates are declared in `.elspais.toml` using a structured TOML section. Each associate specifies a relative filesystem path and optional git remote URL. Transitive federation was originally disallowed (assertion D was a hard error) to keep the topology simple; that guard made symmetric or chained repo arrangements unusable from any repository but the root (TOOL-33) and blocked federating an org-policy repository reachable through a chain (TOOL-38). Directed cycles remain a genuine error because dependency direction drives resolution order; diamonds are convergence, not cycles, and the git-origin identity rule (assertion G) is what makes the two distinguishable. Disjoint ID spaces (assertion H) were previously enforced but undocumented — federating repositories must use non-overlapping ID patterns.

### Changelog

- 2026-08-02 | 9b0f1733 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | 2a648c8e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | 1bc0e4b5 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | de074317 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38/TOOL-33: replace the transitive-associates hard error (D) with transitive resolution; add cycle (E), diamond (F), git-origin identity (G), and disjoint-ID-space (H) rules
- 2026-07-30 | 0379ce9c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 479dcbb8 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 479dcbb8 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Associates Config Loading* | **Hash**: 9b0f1733
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

G. The generic presumed-foreign determination applied after cross-repo wiring to any broken *Traceability* reference that does not already carry a diagnostic (independent of the `Integrates:`-specific determination in assertion E) SHALL NOT mark a reference foreign when the federation has no configured associates, since there is no other repository the reference could belong to. It also SHALL NOT mark a reference foreign when the target's leading token matches the declaring repo's own configured namespace and no configured associate declares that same namespace; such a reference is a malformed same-repo reference, not a cross-repo one, and SHALL remain a hard broken reference carrying a diagnostic naming the likely cause (e.g. an `[id-patterns.assertions]` separator/multi_separator mismatch).

### Rationale

The bottom-up reference model (`Implements:` authored on the implementer) would force a reusable library to name each consumer's requirement IDs, coupling the library to its consumers and breaking isolated builds. `Integrates:` is the top-down inverse: authored and stored on the consumer, it points into the library and is wired as a distinct INTEGRATES edge during federation. A dedicated edge kind keeps the library's `Implements:` derivation clean (no consumer IDs leak into library files on render), while contributing to coverage like IMPLEMENTS. Passing status (the result-verified or line-coverage-credited union, REQ-d00258-B) propagates by a live-query overlay that reads the library node's own metrics, consistent with the existing cross-repo inheritance mechanism.

### Changelog

- 2026-07-31 | 8e07589c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | d9d4bc98 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | 425d61aa | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-31 | d1f691f0 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-31 | b576d134 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash, add missing changelog section

*End* *External Library Integration via Integrates Keyword* | **Hash**: 8e07589c
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

The registry is the second discovery source beside `[associates]` (directed dependencies): membership is flat and undirected, so cycles are impossible by construction, while dependency direction — which drives resolution order and base/overlay relationships — stays in `[associates]` where cycles remain a genuine error. Both sources feed one assembly keyed by git origin, which is stable across worktrees and clones where path and name are not. This dissolves the symmetric-configuration circularity of TOOL-33: neither of two mutually-dependent repos needs to declare the other for membership.

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
