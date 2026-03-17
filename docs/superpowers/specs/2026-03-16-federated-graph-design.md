# FederatedGraph Design

## Problem

When building a traceability graph from multiple repositories, the current architecture merges all nodes into a single `TraceGraph` with a single config. Spec parsing is properly isolated per repo, but everything post-build (hierarchy validation, format rules, hash mode, health checks, render/save) uses the root repo's config for all nodes. This causes silent config bleed that can't be easily guarded against because the architecture assumes one config.

## Solution

Replace the single merged graph with a `FederatedGraph` that wraps one or more `TraceGraph` instances, each paired with its own config. `TraceGraph` becomes an internal implementation detail. All consumers interact exclusively with `FederatedGraph`.

## Core Data Model

```python
@dataclass
class RepoEntry:
    name: str                      # e.g. "core", "deployment", "module-a"
    graph: TraceGraph | None       # None if repo unavailable
    config: ElspaisConfig | None   # None if repo unavailable
    repo_root: Path                # expected local path
    git_origin: str | None         # for clone assistance
    error: str | None = None       # e.g. "Repository not found at ../core"

class FederatedGraph:
    _repos: dict[str, RepoEntry]
    _ownership: dict[str, str]     # node_id -> repo name
    _root_repo: str                # name of the starting repo
    _mutation_log: MutationLog     # unified across all repos
```

Cross-graph edges are direct Python object references on the nodes (the existing `node.link()` mechanism). Traversal crosses graph boundaries transparently. When config-sensitive operations need to know which repo a node belongs to, they call `federated.repo_for(node_id)`.

Node IDs are globally unique across all federated repos by convention. ID conflicts are detected at federation time and are a hard error.

## Configuration

Associates are declared in the root repo's `.elspais.toml`:

```toml
[associates.core]
path = "../elspais-core"
git = "git@github.com:org/elspais-core.git"

[associates.module-a]
path = "../module-a"
git = "git@github.com:org/module-a.git"
```

- `path` is relative to the root repo
- `git` is optional; used for clone assistance in the viewer/server
- Each associate must have its own `.elspais.toml`
- Associates declaring their own `[associates]` is a hard error (no transitive federation)
- The current `sponsors.yml` associate discovery is replaced by this config

## Build Pipeline

1. Load root repo's `.elspais.toml`, read `[associates]`
2. For each associate:
   - Resolve path relative to root repo
   - If missing: create error-state `RepoEntry` (soft fail by default, hard fail with `--strict`)
   - If present: load its `.elspais.toml`, hard error if it declares own associates, build its `TraceGraph` with its own config
3. Build root repo's `TraceGraph` with root config
4. Construct `FederatedGraph` from all `RepoEntry` objects
5. ID conflict detection (hard error)
6. Cross-graph edge wiring:
   - Collect `broken_references()` from each sub-graph
   - For each broken ref, check if `target_id` exists in another graph
   - If found: call `source_graph.add_edge(source_id, target_id, edge_kind, target_graph=target_graph)`
   - If not found: remains a genuine broken reference

Missing repos leave unresolved cross-repo references as broken references, making the cause visible in health reports. The viewer can show clone assistance actions next to these errors.

## Cross-Graph Edge Wiring

`TraceGraph.add_edge()` gains an optional `target_graph` parameter (defaults to `self`):

```python
def add_edge(self, source_id, target_id, edge_kind,
             assertion_targets=None, target_graph=None):
    source = self._index[source_id]
    target = (target_graph or self)._index.get(target_id)
    # ... existing logic unchanged
```

When `target_graph` is provided, the target node is looked up in that graph's index. The edge is wired via `node.link()` as usual. `_orphaned_ids` on the source's graph is updated by the existing mutation logic.

## Always Federated

`build_graph()` always returns a `FederatedGraph`, even for single-repo projects (a federation of one). This eliminates the risk of consumers accidentally working with a bare `TraceGraph` that's part of a federation, which would bypass the unified mutation log and ownership tracking.

`TraceGraph` is never exposed outside the `graph/` package. Every type hint that currently says `TraceGraph` changes to `FederatedGraph`.

## Method Federation Strategies

Every `TraceGraph` public method has an explicit implementation on `FederatedGraph` with a documented federation strategy:

- **by_id**: Look up owning graph, delegate. Examples: `find_by_id`, `rename_node`, `update_title`, `change_status`, `add_assertion`, `delete_assertion`, `update_assertion`, `rename_assertion`, `move_node_to_file`, `rename_file`, `fix_broken_reference`, `has_root`, `delete_requirement`.
- **aggregate**: Combine results from all graphs. Examples: `iter_roots`, `all_nodes`, `all_connected_nodes`, `nodes_by_kind`, `iter_by_kind`, `node_count`, `root_count`, `has_orphans`, `orphan_count`, `orphaned_nodes`, `has_broken_references`, `broken_references`, `deleted_nodes`, `has_deletions`, `iter_unlinked`, `iter_structural_orphans`.
- **broadcast**: Run on each graph with its own config/repo_root. Examples: `clone`, `render_save`.
- **cross-graph**: Source and target may be in different graphs. Examples: `add_edge`, `delete_edge`, `change_edge_kind`, `change_edge_targets`.
- **special**: `add_requirement` requires caller to specify target repo. `is_reachable_to_requirement` traversal may cross graph boundaries (works naturally via object references).

## Unified Mutation Log

All mutations flow through `FederatedGraph` into a single `MutationLog`. Each `MutationEntry` is tagged with the repo it affected:

```python
@dataclass
class MutationEntry:
    # ... existing fields ...
    repo: str | None = None
```

When `FederatedGraph` delegates a mutation to a sub-graph, it pops the entry from the sub-graph's log, tags it with `repo=name`, and appends it to the federated log.

`undo_last()` reads the federated log, identifies the repo, and delegates to that sub-graph's undo.

## Render and Persistence

`render_save()` iterates repos, calling render on each sub-graph with its own config and repo_root. Only sub-graphs with pending mutations get written.

Cross-repo references are always persisted in the downstream repo's spec files (the repo whose node declares `Implements:`, `Refines:`, etc.). The spec file is always the "subject" of the verb.

## Staleness Detection

Staleness checking (is a local clone behind its remote?) is a server/viewer concern, not a build concern. The viewer GUI shows staleness indicators. The server API includes staleness info in repo info responses. The CLI build does not check git remotes.

## Typical Topology

```text
core repo (public, PRDs/OPS)
  ^
  |  Implements/Refines
  |
deployment repo (private, DEV/OPS)   <-- root repo (where you run elspais)
  ^         ^
  |         |
module-a  module-b  ...  (optional associates)
```

The root repo is wherever you start from, not necessarily the top of the requirement hierarchy. Typically the deployment repo refines the core repo's requirements.
