# MASTER_PLAN: Trace Command Implementation [COMPLETED]

**Depends on**: OLD_PLAN2.md (Graph iterator-only API + Factory)

## Files to Modify
- **MODIFY**: `src/elspais/commands/trace.py` - Use factory, implement formats

---

## Trace Command (`src/elspais/commands/trace.py`)

### Core Principle
- Command only works with graph data (zero file I/O for reading requirements)
- One pure function per format (graph in, iterator out)
- `run()` is thin orchestration: build graph → format → write output

### Pure Format Functions

Each function takes a `TraceGraph` and yields strings. No side effects.

```python
from elspais.graph.relations import EdgeKind

def format_markdown(graph: TraceGraph) -> Iterator[str]:
    """Generate markdown table. Streams one node at a time."""
    yield "# Traceability Matrix"
    yield ""
    yield "| ID | Title | Level | Status | Implements |"
    yield "|----|-------|-------|--------|------------|"

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        # Use iterator API for edges
        impl_ids = (e.target.id for e in node.iter_edges_by_kind(EdgeKind.IMPLEMENTS))
        impl = ", ".join(impl_ids) or "-"
        yield f"| {node.id} | {node.label} | {node.level or ''} | {node.status or ''} | {impl} |"


def format_csv(graph: TraceGraph) -> Iterator[str]:
    """Generate CSV. Streams one node at a time."""
    def escape(s: str) -> str:
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    yield "id,title,level,status,implements"

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        impl_ids = (e.target.id for e in node.iter_edges_by_kind(EdgeKind.IMPLEMENTS))
        impl = ";".join(impl_ids)
        yield ",".join([
            escape(node.id),
            escape(node.label or ""),
            escape(node.level or ""),
            escape(node.status or ""),
            escape(impl),
        ])


def format_html(graph: TraceGraph) -> Iterator[str]:
    """Generate basic HTML table. Streams one node at a time."""
    yield "<!DOCTYPE html><html><body><table>"
    yield "<tr><th>ID</th><th>Title</th><th>Level</th><th>Status</th><th>Implements</th></tr>"

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        impl_ids = (e.target.id for e in node.iter_edges_by_kind(EdgeKind.IMPLEMENTS))
        impl = ", ".join(impl_ids) or "-"
        yield f"<tr><td>{node.id}</td><td>{node.label}</td><td>{node.level or ''}</td><td>{node.status or ''}</td><td>{impl}</td></tr>"

    yield "</table></body></html>"


def format_json(graph: TraceGraph) -> Iterator[str]:
    """Generate JSON array. Streams one node at a time."""
    yield "["
    first = True
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not first:
            yield ","
        first = False
        # Stream implements IDs via iterator
        impl_ids = [e.target.id for e in node.iter_edges_by_kind(EdgeKind.IMPLEMENTS)]
        node_json = json.dumps({
            "id": node.id,
            "title": node.label,
            "level": node.level,
            "status": node.status,
            "hash": node.hash,
            "implements": impl_ids,
            "source": {
                "path": node.source.path if node.source else None,
                "line": node.source.line if node.source else None,
            },
        }, indent=2)
        yield node_json
    yield "]"


def format_view(graph: TraceGraph, embed_content: bool = False) -> str:
    """Generate interactive HTML via HTMLGenerator."""
    from elspais.html import HTMLGenerator
    generator = HTMLGenerator(graph)
    return generator.generate(embed_content=embed_content)
```

### `run(args) -> int` - Thin Orchestration

```python
def run(args: argparse.Namespace) -> int:
    # Handle not-implemented features
    for flag in ("edit_mode", "review_mode", "server"):
        if getattr(args, flag, False):
            print(f"Error: --{flag.replace('_', '-')} not yet implemented", file=sys.stderr)
            return 1

    # Build graph using factory
    from elspais.graph.factory import build_graph
    graph = build_graph(
        spec_dirs=[args.spec_dir] if getattr(args, "spec_dir", None) else None,
        config_path=getattr(args, "config", None),
    )

    # Select formatter (returns generator)
    if getattr(args, "view", False):
        # format_view returns a single string (HTMLGenerator)
        content = format_view(graph, getattr(args, "embed_content", False))
        output_path = args.output or Path("traceability_view.html")
        Path(output_path).write_text(content)
    else:
        formatters = {
            "markdown": format_markdown,
            "csv": format_csv,
            "html": format_html,
            "json": format_json,
        }
        line_generator = formatters[args.format](graph)
        output_path = args.output

        # Stream output line by line
        if output_path:
            with open(output_path, "w") as f:
                for line in line_generator:
                    f.write(line + "\n")
        else:
            for line in line_generator:
                print(line)

    if output_path and not getattr(args, "quiet", False):
        print(f"Generated: {output_path}", file=sys.stderr)

    return 0
```

---

## Verification

1. **Trace tests**: `pytest tests/test_trace_command.py -v`
2. **CLI test**: `elspais trace spec/ --format markdown`
3. **View test**: `elspais trace spec/ --view --embed-content`
