# MASTER_PLAN: Graph Iterator-Only API + Factory

## Architecture Principles
1. **Commands only traverse the graph. They never read from disk.**
2. **Don't make helper functions when you can just use the graph directly.** The graph structure is the API - use it inline.
3. **Always use iterators, never extract lists/dicts.** Process one node at a time. No `sorted()`, no `list()`, no materializing iterators.

## Files to Modify
- **MODIFY**: `src/elspais/graph/builder.py` - Refactor TraceGraph to iterator-only API
- **MODIFY**: `src/elspais/graph/GraphNode.py` - Refactor to iterator-only API
- **NEW**: `src/elspais/graph/factory.py` - Shared graph-building utility

---

## Issue Queue

### [x] Part 0: Refactor Graph to Iterator-Only API
**Files**: `builder.py`, `GraphNode.py`
**Scope**: Delete public list/dict attributes, add iterator methods, add UUID for GUI referencing

#### TraceGraph Changes (`builder.py`)

**DELETE these public attributes:**
```python
roots: list[GraphNode]           # DELETE - exposes list
```

**Refactored (iterator-only):**
```python
@dataclass
class TraceGraph:
    _roots: list[GraphNode] = field(default_factory=list)  # Internal
    _index: dict[str, GraphNode] = field(default_factory=dict, repr=False)  # Internal
    repo_root: Path = field(default_factory=Path.cwd)

    def iter_roots(self) -> Iterator[GraphNode]:
        """Iterate root nodes."""
        yield from self._roots

    def find_by_id(self, node_id: str) -> GraphNode | None:
        """Find single node by ID."""  # Returns node
        return self._index.get(node_id)

    def all_nodes(self, order: str = "pre") -> Iterator[GraphNode]:
        """Iterate all nodes."""  # Returns iterator
        ...

    def nodes_by_kind(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Iterate nodes of a kind."""  # Returns iterator
        ...

    def node_count(self) -> int:
        """Return count."""  # Returns int
        return len(self._index)
```

#### GraphNode Changes (`GraphNode.py`)

**DELETE these public attributes and methods:**
```python
children: list[GraphNode]        # DELETE - exposes list
parents: list[GraphNode]         # DELETE - exposes list
outgoing_edges: list[Edge]       # DELETE - exposes list
incoming_edges: list[Edge]       # DELETE - exposes list
content: dict[str, Any]          # DELETE - exposes dict
metrics: dict[str, Any]          # DELETE - exposes dict

def edges_by_kind(self, kind) -> list[Edge]:  # DELETE - returns list
```

**Refactored (iterators + field accessors):**
```python
@dataclass
class GraphNode:
    id: str
    kind: NodeKind
    label: str = ""
    source: SourceLocation | None = None
    uuid: str = field(default_factory=lambda: uuid4().hex)  # Stable reference for GUI

    # Internal storage (prefixed)
    _children: list[GraphNode] = field(default_factory=list)
    _parents: list[GraphNode] = field(default_factory=list, repr=False)
    _outgoing_edges: list[Edge] = field(default_factory=list, repr=False)
    _incoming_edges: list[Edge] = field(default_factory=list, repr=False)
    _content: dict[str, Any] = field(default_factory=dict)
    _metrics: dict[str, Any] = field(default_factory=dict)

    # Iterator access
    def iter_children(self) -> Iterator[GraphNode]:
        yield from self._children

    def iter_parents(self) -> Iterator[GraphNode]:
        yield from self._parents

    def iter_outgoing_edges(self) -> Iterator[Edge]:
        yield from self._outgoing_edges

    def iter_incoming_edges(self) -> Iterator[Edge]:
        yield from self._incoming_edges

    def iter_edges_by_kind(self, edge_kind: EdgeKind) -> Iterator[Edge]:
        for e in self._outgoing_edges:
            if e.kind == edge_kind:
                yield e

    # Field accessors (return single value)
    def get_field(self, key: str, default: Any = None) -> Any:
        return self._content.get(key, default)

    def get_metric(self, key: str, default: Any = None) -> Any:
        return self._metrics.get(key, default)

    def set_metric(self, key: str, value: Any) -> None:
        self._metrics[key] = value

    # Convenience properties for common fields
    @property
    def level(self) -> str | None:
        return self._content.get("level")

    @property
    def status(self) -> str | None:
        return self._content.get("status")

    @property
    def hash(self) -> str | None:
        return self._content.get("hash")
```

#### UUID for GUI References
Each node gets a stable UUID (`uuid4().hex`) for direct referencing in HTML/GUI contexts. Unlike `id` (which may contain special characters or be hierarchical like `REQ-p00001-A`), the UUID is a simple 32-char hex string suitable for DOM IDs, URL fragments, and API endpoints.

```python
from uuid import uuid4
```

#### Update GraphBuilder to use internal attributes
The builder sets `_children`, `_parents`, etc. instead of public lists.

---

### [ ] Part 1: Graph Factory (`src/elspais/graph/factory.py`)
**Files**: NEW `src/elspais/graph/factory.py`
**Scope**: Single utility that builds a `TraceGraph` from config/spec directories

#### Purpose
All commands call this instead of implementing their own file reading.

#### Function Signature
```python
def build_graph(
    config: dict | None = None,
    spec_dirs: list[Path] | None = None,
    config_path: Path | None = None,
) -> TraceGraph:
    """Build a TraceGraph from spec directories.

    Args:
        config: Pre-loaded config dict (optional)
        spec_dirs: Explicit spec directories (optional)
        config_path: Path to config file (optional)

    Priority: spec_dirs > config > config_path > defaults

    Returns:
        Complete TraceGraph with all requirements linked.
    """
```

#### Implementation Flow
```python
from pathlib import Path
from elspais.config import get_config, get_spec_directories
from elspais.utilities.patterns import PatternConfig
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.parsers.journey import JourneyParser
from elspais.graph.parsers.code import CodeParser
from elspais.graph.parsers.test import TestParser
from elspais.graph.deserializer import DomainFile
from elspais.graph.builder import GraphBuilder, TraceGraph

def build_graph(...) -> TraceGraph:
    # 1. Resolve config
    if config is None:
        config = get_config(config_path, Path.cwd())

    # 2. Resolve spec directories
    if spec_dirs is None:
        spec_dirs = get_spec_directories(None, config)

    # 3. Create parser registry with ALL parsers
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    registry = ParserRegistry()
    registry.register(RequirementParser(pattern_config))
    registry.register(JourneyParser())
    registry.register(CodeParser())
    registry.register(TestParser())

    # 4. Build graph from all spec directories
    builder = GraphBuilder(repo_root=Path.cwd())
    for spec_dir in spec_dirs:
        domain_file = DomainFile(spec_dir, patterns=["*.md"], recursive=True)
        for parsed_content in domain_file.deserialize(registry):
            builder.add_parsed_content(parsed_content)

    return builder.build()
```

---

## Verification

1. **Graph API tests**: `pytest tests/graph/ -v` - Verify iterator-only API works
2. **Factory import**: `python -c "from elspais.graph.factory import build_graph"`
3. **Verify iterator-only**: Grep GraphNode.py for `-> list` or `-> dict` - should find none in public methods
