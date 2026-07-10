# Implements: REQ-d00211
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


def build_namespaces(typed) -> list[dict[str, Any]]:
    """List of namespaces (local first, then associates) with resolved colors.

    Exactly one entry has ``is_local=true``. Each entry's ``label`` is the
    namespace code (e.g. "DIARY", "CAL"); the project's friendly name is
    exposed separately as ``project_name`` so the header can show it once.
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
    for name, entry in typed.associates.items():
        if entry.namespace in seen_codes:
            # Associate's namespace collides with the local project or with a
            # previously-listed associate. Skip — downstream consumers (CSS
            # selectors, ns_catalog dict, the JS LOCAL_NS exclusion) all assume
            # unique codes.
            import logging

            logging.getLogger(__name__).warning(
                "associate %r namespace %r collides with an existing entry; skipped",
                name,
                entry.namespace,
            )
            continue
        seen_codes.add(entry.namespace)
        rc = resolve_color(entry.namespace, entry.color)
        items.append(
            {
                "code": entry.namespace,
                "label": entry.namespace,
                "project_name": name,
                "bg": rc.bg,
                "text": rc.text,
                "tint": hex_with_alpha(rc.bg, _TINT_ALPHA),
                "is_local": False,
            }
        )
    return items


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
