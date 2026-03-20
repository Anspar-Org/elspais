"""
elspais.commands.search_cmd - Search requirements by keyword.

Exposes the MCP search engine as a CLI subcommand.

Fast-path priority:
  1. Running viewer server (/api/search on port 5001) — ~10ms
  2. Running MCP daemon — ~200ms
  3. Auto-start MCP daemon, then query — ~4s first time, ~200ms after
  4. Local graph build (--no-daemon fallback) — ~2-4s every time
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from elspais.graph import NodeKind


def run(args: argparse.Namespace) -> int:
    """Run the search command."""
    query = getattr(args, "query", "") or ""
    if not query:
        print("Usage: elspais search 'search terms'", file=sys.stderr)
        return 1

    field = getattr(args, "field", "all")
    use_regex = getattr(args, "regex", False)
    limit = getattr(args, "limit", 50)
    fmt = getattr(args, "format", "text")
    no_daemon = getattr(args, "no_daemon", False)

    results = None

    if not no_daemon:
        results = _try_fast_search(query, field, use_regex, limit)

    # Fallback: local graph build
    if results is None:
        results = _local_search(args, query, field, use_regex, limit)

    if not results:
        if not getattr(args, "quiet", False):
            print("No results.", file=sys.stderr)
        return 0

    output = _render(results, fmt)
    sys.stdout.write(output)
    return 0


def _try_fast_search(
    query: str,
    field: str,
    regex: bool,
    limit: int,
) -> list[dict] | None:
    """Try viewer server, then MCP daemon."""
    # 1. Try viewer (fastest — stdlib-only HTTP GET, ~10ms)
    results = _try_viewer(query, field, regex, limit)
    if results is not None:
        return results

    # 2. Try MCP daemon (auto-starts if needed, ~43ms warm)
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import ensure_daemon, search_via_daemon

        repo_root = find_git_root()
        if repo_root is None:
            return None

        port = ensure_daemon(repo_root)
        return search_via_daemon(port, query, field, regex, limit)
    except Exception:
        return None


def _try_viewer(
    query: str,
    field: str,
    regex: bool,
    limit: int,
    port: int = 5001,
) -> list[dict] | None:
    """Query a running viewer server — stdlib only, no mcp import."""
    from urllib.error import URLError
    from urllib.parse import quote_plus
    from urllib.request import urlopen

    url = (
        f"http://127.0.0.1:{port}/api/search"
        f"?q={quote_plus(query)}&field={field}"
        f"&regex={'true' if regex else 'false'}&limit={limit}"
    )
    try:
        with urlopen(url, timeout=2) as resp:
            return json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        return None


def _local_search(
    args: argparse.Namespace,
    query: str,
    field: str,
    regex: bool,
    limit: int,
) -> list[dict]:
    """Build graph locally and search (slow path)."""
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    canonical_root = getattr(args, "canonical_root", None)

    raw_config = get_config(config_path)
    graph = build_graph(
        config=raw_config,
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        canonical_root=canonical_root,
    )
    return _search(graph, query, field=field, regex=regex, limit=limit)


def _search(
    graph,
    query: str,
    field: str = "all",
    regex: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Search requirements, returning scored results."""
    if regex:
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error as e:
            print(f"Invalid regex: {e}", file=sys.stderr)
            return []
        results: list[dict] = []
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            if _regex_matches(node, field, pattern):
                results.append(_summarize(node, score=1.0))
                if len(results) >= limit:
                    break
        return results

    from elspais.mcp.search import parse_query, score_node

    parsed = parse_query(query)
    if parsed.is_empty:
        return []

    scored: list[tuple[float, dict]] = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        s = score_node(node, parsed, field)
        if s > 0:
            scored.append((s, _summarize(node, score=s)))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


def _regex_matches(node, field: str, pattern: re.Pattern) -> bool:
    """Check if a regex matches any of the specified fields on a node."""
    fields = ("id", "title", "keywords", "body") if field == "all" else (field,)
    for f in fields:
        if f == "id":
            text = node.id
        elif f == "title":
            text = node.get_label() or ""
        elif f == "body":
            text = node.get_field("body_text", "")
        elif f == "keywords":
            kws = node.get_field("keywords", []) or []
            text = " ".join(kws)
        else:
            text = ""
        if text and pattern.search(text):
            return True
    return False


def _summarize(node, score: float) -> dict:
    """Create a summary dict for a requirement node."""
    return {
        "id": node.id,
        "title": node.get_label() or "",
        "level": node.get_field("level") or "",
        "status": node.get_field("status") or "",
        "score": score,
    }


def _render(results: list[dict], fmt: str) -> str:
    """Render search results to the requested format."""
    if fmt == "json":
        return json.dumps(results, indent=2) + "\n"

    # Text format: tabular
    lines: list[str] = []
    # Header
    lines.append(f"{'Score':>5}  {'ID':<20} {'Level':<5} {'Status':<10} Title")
    lines.append(f"{'-----':>5}  {'----':<20} {'-----':<5} {'------':<10} -----")
    for r in results:
        score_str = f"{r['score']:.0f}"
        lines.append(
            f"{score_str:>5}  {r['id']:<20} {r['level']:<5} {r['status']:<10} {r['title']}"
        )
    lines.append(f"\n{len(results)} result(s)")
    return "\n".join(lines) + "\n"
