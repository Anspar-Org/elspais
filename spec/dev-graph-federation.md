# Graph Federation Development Requirements

## REQ-d00200: FederatedGraph Read-Only Delegation

**Level**: dev | **Status**: Active | **Implements**: REQ-p00005, REQ-p00050

FederatedGraph SHALL wrap one or more TraceGraph instances, each paired with its own configuration and repo root, delegating all read-only TraceGraph methods with documented federation strategies.

## Assertions

A. FederatedGraph SHALL wrap one or more TraceGraph instances via RepoEntry dataclass containing: name, graph (TraceGraph | None), config (ConfigLoader | None), repo_root (Path), git_origin (str | None), error (str | None).

B. FederatedGraph.from_single() classmethod SHALL create a federation-of-one from a single TraceGraph, config, and repo_root, using "root" as the default repo name.

C. All read-only TraceGraph public methods SHALL be explicitly implemented on FederatedGraph with a strategy comment (by_id, aggregate, or special).

D. by_id strategy methods (find_by_id, has_root) SHALL look up the owning graph via an internal ownership mapping and delegate to the correct sub-graph.

E. aggregate strategy methods (iter_roots, all_nodes, node_count, root_count, iter_by_kind, nodes_by_kind, all_connected_nodes, orphaned_nodes, has_orphans, orphan_count, broken_references, has_broken_references, iter_unlinked, iter_structural_orphans, deleted_nodes, has_deletions) SHALL combine results from all sub-graphs.

F. Aggregate methods SHALL skip repos with graph set to None (error-state repos).

G. repo_for(node_id) SHALL return the RepoEntry for the graph owning that node. config_for(node_id) SHALL return the config for that node's owning repo.

H. iter_repos() SHALL yield all RepoEntry objects including error-state repos.

## Rationale

FederatedGraph provides config isolation for multi-repo builds while presenting a unified API to consumers. The federation-of-one pattern ensures all code paths go through FederatedGraph, preventing accidental direct TraceGraph usage. Error-state repos (missing associates) are represented in the federation but skipped during aggregation, preserving graceful degradation.

## Changelog

- 2026-04-23 | 72471144 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *FederatedGraph Read-Only Delegation* | **Hash**: 72471144
---

## REQ-d00201: FederatedGraph Mutation Delegation

**Level**: dev | **Status**: Active | **Implements**: REQ-d00200, REQ-p00050

FederatedGraph SHALL delegate all mutation operations to the appropriate sub-graph, maintain a unified mutation log across repos, and update internal ownership when IDs change.

## Assertions

A. by_id mutation methods (rename_node, update_title, change_status, delete_requirement, add_assertion, delete_assertion, update_assertion, rename_assertion, rename_file, fix_broken_reference) SHALL look up the owning repo via `_ownership`, delegate to the sub-graph, and update `_ownership` when IDs change.

B. FederatedGraph SHALL maintain a unified mutation log that records lightweight entries pointing to the repo name and sub-graph mutation ID, providing chronological ordering across all repos.

C. undo_last() SHALL read the federated log to identify which repo was last mutated, then delegate undo to that sub-graph. undo_to() SHALL undo back to a specific mutation ID across repos.

D. add_requirement SHALL accept a target_repo parameter to specify which sub-graph receives the new node. If omitted for federation-of-one, it SHALL default to the root repo.

E. Cross-graph mutation methods (add_edge, delete_edge, change_edge_kind, change_edge_targets, move_node_to_file) SHALL resolve source and target repos independently.

F. The mutation_log property SHALL return a log object whose iter_entries() yields full MutationEntry objects from sub-graphs in federated chronological order, compatible with existing consumers.

G. clone() SHALL perform federation-aware deep copy: deep-copy each sub-graph independently, then rebuild cross-graph edges and the ownership map.

## Rationale

Mutation delegation preserves TraceGraph's existing mutation+undo logic while adding federation awareness. The lightweight federated log avoids duplicating MutationEntry data. Ownership tracking ensures by_id lookups remain O(1) after mutations.

## Changelog

- 2026-04-23 | 1a0942a4 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *FederatedGraph Mutation Delegation* | **Hash**: 1a0942a4
---

## REQ-d00202: Associates Config Loading

**Level**: dev | **Status**: Active | **Implements**: REQ-p00005

The config system SHALL parse `[associates.<name>]` sections from `.elspais.toml` to declare federated repository associations.

## Assertions

A. `get_associates_config(config)` SHALL read `[associates]` sections and return a `dict[str, dict]` mapping associate name to `{path: str, git: str | None}`.

B. The `path` field SHALL be required for each associate. The `git` field SHALL be optional (for clone assistance).

C. When no `[associates]` section exists in config, `get_associates_config()` SHALL return an empty dict.

D. Associates declaring their own `[associates]` section SHALL be a hard error: "Associate 'X' declares its own associates -- only the root repo may declare associates."

## Rationale

Associates are declared in the root repo's `.elspais.toml` using a structured TOML section. Each associate specifies a relative filesystem path and optional git remote URL. Transitive federation (associates of associates) is disallowed to keep the topology simple and predictable.

## Changelog

- 2026-04-23 | 479dcbb8 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Associates Config Loading* | **Hash**: 479dcbb8
---

## REQ-d00203: Multi-Repo Build Pipeline

**Level**: dev | **Status**: Active | **Implements**: REQ-d00200, REQ-p00005

The `build_graph()` factory SHALL build separate TraceGraph instances per repository when associates are configured, constructing a multi-repo FederatedGraph.

## Assertions

A. When `[associates]` config is present, `build_graph()` SHALL create a separate `TraceGraph` per associate repo, each with its own config-derived resolver.

B. Each associate's config SHALL be loaded from its own `.elspais.toml` and validated for transitive associates before building.

C. Missing associate paths SHALL produce error-state `RepoEntry` with `graph=None` and a descriptive `error` message (soft fail).

D. A `strict` parameter on `build_graph()` SHALL cause missing associates to raise an error instead of soft-failing.

E. The root repo and all valid associates SHALL be combined into a single `FederatedGraph` with the root repo as `_root_repo`.

## Rationale

Per-repo building ensures config isolation: each repo's hierarchy rules, format rules, and hash mode apply only to its own nodes. Error-state entries preserve visibility of missing associates in health reports without blocking the build.

## Changelog

- 2026-04-23 | 31e019a1 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Multi-Repo Build Pipeline* | **Hash**: 31e019a1
---

## REQ-d00204: Per-Repo Health Check Delegation

**Level**: dev | **Status**: Active | **Implements**: REQ-d00200, REQ-p00002

Health checks that depend on per-repo configuration SHALL run once per federated repo using that repo's own config, ensuring config isolation in multi-repo federations.

## Assertions

A. Config-sensitive health checks (hierarchy levels, format rules, reference resolution, structural orphans, changelog checks) SHALL run per-repo using each repo's own `ConfigLoader` from `RepoEntry.config`.

B. Non-config-sensitive health checks (file parseability, duplicate IDs, hash integrity, index staleness) SHALL run once on the full `FederatedGraph`.

C. Per-repo checks SHALL produce a separate `HealthCheck` per repo per check type, with `HealthFinding` entries annotated with a `repo` field identifying the source repository.

D. `HealthFinding` SHALL support an optional `repo` field (str | None) for per-repo attribution.

E. `check_broken_references` SHALL distinguish within-repo broken references (error severity) from cross-repo broken references where the target repo is in error state (warning severity with clone assistance info).

F. `run_spec_checks` SHALL accept a `FederatedGraph` and iterate `iter_repos()` for config-sensitive checks, using `FederatedGraph.from_single()` to create per-repo sub-federations.

## Rationale

Without per-repo delegation, all nodes are validated against the root repo's config. When repos have different hierarchy rules, format rules, or changelog policies, this produces false positives (root config rejects valid associate nodes) or false negatives (root config allows invalid associate nodes). Per-repo delegation ensures each repo is validated by its own rules.

## Changelog

- 2026-04-23 | 2313140d | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Per-Repo Health Check Delegation* | **Hash**: 2313140d
---
