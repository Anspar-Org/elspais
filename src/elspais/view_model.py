# Implements: REQ-d00211-A, REQ-d00211-C
"""Pure view-model builders for the traceability viewer.

Level / namespace / status entries (with resolved colors) derived from typed
config. Shared by the static HTML generator (``elspais.html.generator``, the
``[trace-view]`` extra) and the live Starlette server (``elspais.server.*``, the
``[trace-review]`` extra).

This module MUST stay free of any web-framework import (starlette, etc.) so the
static ``viewer --static`` path can build its view model without the server
dependencies. It previously lived in ``elspais.server.routes_ui``, which imports
starlette at module top level — dragging starlette into the static path (CUR-1698).
"""

from __future__ import annotations

from typing import Any


def build_levels(typed) -> list[dict[str, Any]]:
    """List of level entries with resolved colors, sorted by rank."""
    from elspais.utilities.color import resolve_color

    items: list[dict[str, Any]] = []
    for key, level_cfg in typed.levels.items():
        rc = resolve_color(key, level_cfg.color)
        items.append(
            {
                "key": key,
                "label": level_cfg.display_name or key,
                "rank": level_cfg.rank,
                "letter": level_cfg.letter,
                "bg": rc.bg,
                "text": rc.text,
            }
        )
    items.sort(key=lambda x: x["rank"])
    return items


def _associate_namespaces(typed, federation) -> list[tuple[str, str, str | None]]:
    """The (name, namespace code, configured color) of each non-local repo.

    A federation is the authority on which repositories are present, so when
    one is supplied its members — including those reached only through an
    associate's own declarations — are what gets catalogued. The invoking
    repo's own ``[associates]`` declaration still supplies the code and color
    for the members it names, so a directly-declared associate renders from
    the same values whether or not a federation is on hand; a member it does
    not name falls back to that repo's own ``[project]`` identity. A member
    that neither declares nor could be loaded has no derivable code and is
    left out.
    """
    # A caller holding a single-repo TraceGraph rather than a federation has
    # nothing to enumerate, and its declarations are the whole answer anyway.
    if federation is None or not hasattr(federation, "iter_repos"):
        return [(name, entry.namespace, entry.color) for name, entry in typed.associates.items()]

    root_name = federation.root_repo_name
    out: list[tuple[str, str, str | None]] = []
    for entry in federation.iter_repos():
        if entry.name == root_name:
            continue
        declared = typed.associates.get(entry.name)
        project = entry.config.get("project", {})
        code = (declared.namespace if declared else "") or project.get("namespace", "")
        if not code:
            # Only a member that failed to load reaches here: it has no
            # config, contributes no nodes, and so has no namespace to
            # badge. A member with a graph always declares one.
            continue
        color = (declared.color if declared else None) or project.get("color")
        out.append((entry.name, code, color))
    return out


def build_namespaces(typed, federation=None) -> list[dict[str, Any]]:
    """List of namespaces (local first, then associates) with resolved colors.

    Exactly one entry has ``is_local=true``. Each entry's ``label`` is the
    namespace code (e.g. "DIARY", "CAL"); the project's friendly name is
    exposed separately as ``project_name`` so the header can show it once.

    Pass the ``FederatedGraph`` being rendered so that every repository in the
    federation is catalogued, not only those the invoking config names: the
    downstream CSS selectors and the JS ``LOCAL_NS`` exclusion index off this
    catalog, so a missing code leaves cross-repo badges unstyled and
    unlabelled.
    """
    from elspais.utilities.color import hex_with_alpha, resolve_color

    _TINT_ALPHA = 0.12

    items: list[dict[str, Any]] = []
    local_code = typed.project.namespace
    local_rc = resolve_color(local_code, typed.project.color)
    items.append(
        {
            "code": local_code,
            "label": local_code,
            "project_name": typed.project.name or local_code,
            "bg": local_rc.bg,
            "text": local_rc.text,
            "tint": hex_with_alpha(local_rc.bg, _TINT_ALPHA),
            "is_local": True,
        }
    )
    seen_codes = {local_code}
    for name, code, color in _associate_namespaces(typed, federation):
        if code in seen_codes:
            # Associate's namespace collides with the local project or with a
            # previously-listed associate. Skip — downstream consumers (CSS
            # selectors, ns_catalog dict, the JS LOCAL_NS exclusion) all assume
            # unique codes.
            import logging

            logging.getLogger(__name__).warning(
                "associate %r namespace %r collides with an existing entry; skipped",
                name,
                code,
            )
            continue
        seen_codes.add(code)
        rc = resolve_color(code, color)
        items.append(
            {
                "code": code,
                "label": code,
                "project_name": name,
                "bg": rc.bg,
                "text": rc.text,
                "tint": hex_with_alpha(rc.bg, _TINT_ALPHA),
                "is_local": False,
            }
        )
    return items


# Implements: REQ-d00279-B
def build_statuses(typed, candidates: list[str] | None = None) -> list[dict[str, Any]]:
    """List of statuses with resolved colors.

    If ``candidates`` is provided, that order is preserved (typically the
    role-sorted list of statuses actually used in the graph). Otherwise the
    list is derived from the ``status_roles`` union, sorted by key.
    """
    import logging

    from elspais.utilities.color import resolve_color

    # Union of status names declared in [rules.format.status_roles].
    role_names: set[str] = set()
    for statuses_list in typed.rules.format.status_roles.values():
        if isinstance(statuses_list, list):
            role_names.update(statuses_list)
        elif isinstance(statuses_list, str):
            role_names.add(statuses_list)

    # Warn (once per build) about [statuses.<key>] entries naming a status
    # that isn't present in any role. Catches typos like [statuses.Activ].
    log = logging.getLogger(__name__)
    for cfg_key in typed.statuses:
        if cfg_key not in role_names:
            log.warning(
                "[statuses.%s] is not present in any [rules.format.status_roles] "
                "list; the entry will have no effect (check for a typo)",
                cfg_key,
            )

    if candidates is None:
        candidates = sorted(role_names)

    items: list[dict[str, Any]] = []
    for key in candidates:
        cfg_entry = typed.statuses.get(key)
        configured = cfg_entry.color if cfg_entry else None
        rc = resolve_color(key, configured)
        items.append(
            {
                "key": key,
                "label": key,
                "bg": rc.bg,
                "text": rc.text,
            }
        )
    return items


def local_namespace_from_config(config: dict[str, Any]) -> str:
    """Return the local repo's namespace code from typed config."""
    from elspais.config.schema import ElspaisConfig

    try:
        typed = ElspaisConfig.model_validate(config)
    except Exception:
        typed = ElspaisConfig.model_validate({})
    return typed.project.namespace


# Implements: REQ-p00006-A
def build_tree_rows(graph: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    """The rows the navigation tree is drawn from, as a list in tree order.

    One builder serves the live route and the page that embeds its data, so
    the two cannot disagree about the shape of a row or about which nodes
    become one. A second builder drifted from this one: it returned a map
    keyed by requirement, where every reader of the rows expects a list, and
    the tree it fed drew nothing at all.
    """
    from elspais.config.schema import ElspaisConfig
    from elspais.graph import NodeKind
    from elspais.graph.parsers.patterns import JNY_ID_PATTERN
    from elspais.html.generator import compute_coverage_tiers
    from elspais.utilities.patterns import build_resolver

    g = graph
    local_ns = local_namespace_from_config(config)

    # Build one IdResolver per repo for component-extraction (federation-safe).
    try:
        _typed_cfg = ElspaisConfig.model_validate(config)
    except Exception:
        _typed_cfg = ElspaisConfig.model_validate({})
    ns_catalog: dict[str, dict] = {n["code"]: n for n in build_namespaces(_typed_cfg, g)}

    # Cache resolvers per repo. Keyed by namespace string (stable across the
    # request) rather than `id(cfg)` (object ids can be reused by Python after
    # GC, which would alias resolvers across distinct configs in long-running
    # servers).
    _LOCAL_KEY = "__local__"
    _resolver_cache: dict[str, Any] = {}

    def _resolver_for(node):
        try:
            entry = g.repo_for(node.id)
        except Exception:  # noqa: BLE001 - fail-soft per row, never break /api/tree-data
            entry = None
        if entry is not None:
            cfg = entry.config
            cache_key = (cfg.get("project") or {}).get("namespace") or _LOCAL_KEY
        else:
            cfg = config
            cache_key = _LOCAL_KEY
        if cache_key in _resolver_cache:
            return _resolver_cache[cache_key]
        try:
            r = build_resolver(cfg)
        except Exception:  # noqa: BLE001 - degrade to full-id component
            r = None
        _resolver_cache[cache_key] = r
        return r

    def _component_for(node) -> str:
        r = _resolver_for(node)
        if r is None:
            return node.id
        parsed = r.parse(node.id)
        return parsed.component if (parsed and parsed.component) else node.id

    rows: list[dict[str, Any]] = []
    visited: set[tuple[str, str, int]] = set()

    # Collect node IDs affected by pending mutations for "Unsaved" filter
    unsaved_ids: set[str] = set()
    for entry in g.mutation_log.iter_entries():
        if entry.target_id:
            unsaved_ids.add(entry.target_id)
        # Also check before/after state for node_id, source_id, parent_id
        for st in (entry.before_state, entry.after_state):
            if st:
                for key in ("node_id", "source_id", "parent_id"):
                    nid = st.get(key, "")
                    if nid:
                        unsaved_ids.add(nid)

    def _repo_namespace(node) -> str | None:
        """Resolve the node's owning-repo namespace via the federated graph.
        Returns None if the graph isn't federated or the lookup fails. Catches
        any exception so a single problematic node can't break the whole
        /api/tree-data response.
        """
        try:
            entry = g.repo_for(node.id)
        except Exception:  # noqa: BLE001 - fail-soft per row
            return None
        if entry is None:
            return None
        ns = (entry.config.get("project") or {}).get("namespace")
        return ns or None

    def _is_associated(node) -> bool:
        # Which repository holds a node is a question the federation
        # answers. Guessing it from the shape of an identifier would dress
        # a heuristic as an answer, and an identifier's shape is the
        # repository's to configure, not this surface's to assume.
        ns = _repo_namespace(node)
        if ns is not None:
            return ns != local_ns
        _fn = node.file_node()
        if _fn and _fn.get_field("repo"):
            return True
        return bool(node.get_field("associated", False))

    def _get_repo_prefix(node) -> str:
        # The federation knows which repo each node came from.
        ns = _repo_namespace(node)
        if ns is not None:
            return ns
        _fn = node.file_node()
        if _fn and _fn.get_field("repo"):
            return _fn.get_field("repo")
        # Otherwise local. The wire carries the configured namespace rather
        # than the "CORE" sentinel, so a JS client compares it against the
        # same string it receives in NAMESPACES.
        return local_ns

    def _walk(node, depth: int, parent_id: str | None, ancestors: frozenset[str]) -> None:
        from elspais.graph.relations import EdgeKind

        if node.kind != NodeKind.REQUIREMENT:
            return
        # Cycle guard: if this node is already on the current root->node path, a
        # traceability cycle (e.g. mutual `Integrates:` references) would recurse
        # forever. Stop descending — the node is already represented higher up on
        # this branch. This intentionally keys on the ancestor PATH, not a global
        # visited set, so a shared node still renders under each distinct parent
        # (multi-parent DAG behavior is preserved).
        if node.id in ancestors:
            return
        visit_key = (node.id, parent_id or "__root__", depth)
        if visit_key in visited:
            return
        visited.add(visit_key)

        assertion_data: list[tuple[float, str]] = []
        for edge in node.iter_outgoing_edges():
            if edge.kind == EdgeKind.STRUCTURES and edge.target.kind == NodeKind.ASSERTION:
                label = edge.target.get_field("label", "")
                order = edge.metadata.get("render_order", 0.0)
                if label:
                    assertion_data.append((order, label))
        assertion_data.sort()  # Sort by render_order (first element)
        assertions = [label for _, label in assertion_data]

        has_children = any(c.kind == NodeKind.REQUIREMENT for c in node.iter_children())
        is_changed = bool(node.get_metric("is_branch_changed", False))
        is_uncommitted = bool(node.get_metric("is_uncommitted", False))
        # Comment presence: direct comments on this node or its sub-elements
        _has_direct_comments = any(True for _ in g.iter_comments_for_card(node.id))
        tiers = compute_coverage_tiers(node, config)
        # REQ-d00292-A: coverage filter bucket comes from the severity-aware
        # combined_bucket (Task 6), not a naive combined_color check -- this
        # correctly classifies e.g. a fully-but-indirectly-covered requirement
        # as "full" instead of dropping it into "missing".
        coverage = tiers.get("combined_bucket") or "missing"

        _ns_entry = ns_catalog.get(_get_repo_prefix(node)) or {}
        rows.append(
            {
                "id": node.id,
                "kind": "requirement",
                "title": node.get_label() or "",
                "level": (node.get_field("level") or "").upper(),
                "status": (node.get_field("status") or "").upper(),
                "depth": depth,
                "parent_id": parent_id,
                "assertions": assertions,
                "has_children": has_children,
                "is_leaf": not has_children,
                "coverage": coverage,
                "is_changed": is_changed,
                "is_uncommitted": is_uncommitted,
                "is_unsaved": node.id in unsaved_ids,
                "is_associated": _is_associated(node),
                "is_test": False,
                "is_test_result": False,
                "result_status": "",
                "repo_prefix": _get_repo_prefix(node),
                "component": _component_for(node),
                "ns_bg": _ns_entry.get("bg", ""),
                "ns_text": _ns_entry.get("text", ""),
                "ns_tint": _ns_entry.get("tint", ""),
                "has_comments": _has_direct_comments,
                "source_file": node.get_field("source_file", ""),
                "source_line": node.get_field("source_line", 0),
                "validation_color": tiers.get("combined_color", ""),
                "validation_tip": tiers.get("combined_tip", ""),
                "impl_color": tiers.get("impl_color", ""),
                "impl_tip": tiers.get("impl_tip", ""),
                "tested_color": tiers.get("tested_color", ""),
                "tested_tip": tiers.get("tested_tip", ""),
                "verified_color": tiers.get("verified_color", ""),
                "verified_tip": tiers.get("verified_tip", ""),
                "uat_cov_color": tiers.get("uat_cov_color", ""),
                "uat_cov_tip": tiers.get("uat_cov_tip", ""),
                "uat_ver_color": tiers.get("uat_ver_color", ""),
                "uat_ver_tip": tiers.get("uat_ver_tip", ""),
            }
        )

        req_children = sorted(
            (c for c in node.iter_children() if c.kind == NodeKind.REQUIREMENT),
            key=lambda n: n.id,
        )
        child_ancestors = ancestors | {node.id}
        for child in req_children:
            _walk(child, depth + 1, node.id, child_ancestors)

    for root in sorted(g.iter_roots(), key=lambda n: n.id):
        if root.kind == NodeKind.REQUIREMENT:
            _walk(root, 0, None, frozenset())

    # Add USER_JOURNEY nodes
    _jn_entry = ns_catalog.get(local_ns) or {}

    def _journey_component(node_id: str) -> str:
        """Strip the literal "JNY-" prefix from a journey ID so the compact
        display mode shows e.g. "LOGIN-01" instead of "JNY-LOGIN-01".
        Falls back to the full ID if the canonical pattern doesn't match.
        """
        m = JNY_ID_PATTERN.match(node_id)
        if m:
            return f"{m.group('descriptor')}-{m.group('number')}"
        return node_id

    for node in sorted(g.nodes_by_kind(NodeKind.USER_JOURNEY), key=lambda n: n.id):
        _fn = node.file_node()
        source_file = _fn.get_field("relative_path") if _fn else ""
        source_line = node.get_field("parse_line") or 0
        rows.append(
            {
                "id": node.id,
                "kind": "journey",
                "title": node.get_label() or "",
                "level": "",
                "status": "",
                "depth": 0,
                "parent_id": None,
                "assertions": [],
                "has_children": False,
                "is_leaf": True,
                "coverage": "missing",
                "is_changed": False,
                "is_uncommitted": False,
                "is_unsaved": False,
                "is_associated": False,
                "is_test": False,
                "is_test_result": False,
                "is_journey": True,
                "result_status": "",
                "repo_prefix": local_ns,
                "component": _journey_component(node.id),
                "ns_bg": _jn_entry.get("bg", ""),
                "ns_text": _jn_entry.get("text", ""),
                "ns_tint": _jn_entry.get("tint", ""),
                "source_file": source_file,
                "source_line": source_line,
                "actor": node.get_field("actor", ""),
                "goal": node.get_field("goal", ""),
            }
        )
    return rows
