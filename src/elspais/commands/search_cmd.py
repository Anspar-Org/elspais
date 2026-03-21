"""
elspais.commands.search_cmd - Search requirements by keyword.

Exposes the MCP search engine as a CLI subcommand.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from elspais.graph import NodeKind


def compute_search(graph: Any, config: dict[str, Any], params: dict[str, str]) -> dict:
    """Pure compute function: search requirements on a graph.

    Called by engine.call (local path) and by routes_api (server path).
    Returns {"results": [...]}.
    """
    query = params.get("q", "")
    field = params.get("field", "all")
    use_regex = params.get("regex", "false").lower() == "true"
    limit = int(params.get("limit", "50"))

    if not query:
        return {"results": []}

    results = _search(graph, query, field=field, regex=use_regex, limit=limit)
    return {"results": results}


def run(args: argparse.Namespace) -> int:
    """Run the search command."""
    from elspais.commands._engine import call as engine_call

    query = getattr(args, "query", "") or ""
    if not query:
        print("Usage: elspais search 'search terms'", file=sys.stderr)
        return 1

    field = getattr(args, "field", "all")
    use_regex = getattr(args, "regex", False)
    limit = getattr(args, "limit", 50)
    fmt = getattr(args, "format", "text")
    no_daemon = getattr(args, "no_daemon", False)

    params: dict[str, str] = {
        "q": query,
        "field": field,
        "regex": "true" if use_regex else "false",
        "limit": str(limit),
    }

    data = engine_call(
        "/api/search",
        params,
        compute_search,
        skip_daemon=no_daemon,
    )

    results = data.get("results", [])

    if not results:
        if not getattr(args, "quiet", False):
            print("No results.", file=sys.stderr)
        return 0

    output = _render(results, fmt)
    sys.stdout.write(output)
    return 0


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
