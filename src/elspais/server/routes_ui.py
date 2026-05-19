# Implements: REQ-p00006-B
# Implements: REQ-d00010-A
"""Starlette UI route handlers — template rendering and helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

# Implements: REQ-d00211
# User-selectable relationship kinds for the edit UI.
_USER_RELATIONSHIP_KINDS = ["implements", "refines", "satisfies"]


def _extract_viewer_config(config: dict[str, Any]) -> dict[str, Any]:
    """Extract viewer-relevant values from the config dict.

    Returns a dict with keys suitable for unpacking into the Jinja2
    template context. Includes legacy `config_types` / `config_statuses` for
    backward compatibility, plus the dynamic `levels` / `namespaces` /
    `statuses` lists (each item carrying resolved bg/text colors) that the
    templates and API responses consume.
    """
    from elspais.config.schema import ElspaisConfig

    try:
        typed = ElspaisConfig.model_validate(config)
    except Exception:
        typed = ElspaisConfig.model_validate({})

    config_types = []
    for name, level_cfg in typed.levels.items():
        entry: dict[str, Any] = {"name": name, "level": level_cfg.rank}
        entry["letter"] = level_cfg.letter or name[0]
        config_types.append(entry)
    config_types.sort(key=lambda t: t["level"])

    # Derive allowed statuses from status_roles
    config_statuses: list[str] = []
    for statuses in typed.rules.format.status_roles.values():
        if isinstance(statuses, list):
            config_statuses.extend(statuses)
        elif isinstance(statuses, str):
            config_statuses.append(statuses)
    config_statuses.sort()

    return {
        "config_types": config_types,
        "config_relationship_kinds": list(_USER_RELATIONSHIP_KINDS),
        "config_statuses": config_statuses,
        "levels": build_levels(typed),
        "namespaces": build_namespaces(typed),
    }


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


async def index(request: Request):
    """Serve the trace-edit UI template with enriched context."""
    from starlette.templating import Jinja2Templates

    state = request.app.state.app_state
    templates_dir = Path(__file__).parent.parent / "html" / "templates"

    try:
        from elspais.config import get_status_roles
        from elspais.html.generator import HTMLGenerator
        from elspais.html.highlighting import get_pygments_css
        from elspais.html.theme import get_catalog

        templates = Jinja2Templates(directory=str(templates_dir))

        gen = HTMLGenerator(state.graph, base_path=str(state.repo_root), config=state.config)
        gen._annotate_git_state()
        stats = gen._compute_stats()
        journeys = gen._collect_journeys()
        stats.journey_count = len(journeys)
        roles = get_status_roles(state.config)
        status_keys = roles.sort_by_role(list(gen._collect_unique_values("status")))
        topics = sorted(gen._collect_unique_values("topic"))
        default_hidden = roles.default_hidden_statuses()

        viewer_cfg = _extract_viewer_config(state.config)
        # Build status entries with resolved colors, preserving role-sorted order.
        from elspais.config.schema import ElspaisConfig

        try:
            typed = ElspaisConfig.model_validate(state.config)
        except Exception:
            typed = ElspaisConfig.model_validate({})
        statuses = build_statuses(typed, candidates=status_keys)

        context = {
            "request": request,
            "mode": "edit",
            "stats": stats,
            "journeys": journeys,
            "statuses": statuses,
            "topics": topics,
            "default_hidden_statuses": sorted(default_hidden),
            "version": gen.version,
            "base_path": str(state.repo_root),
            "repo_name": state.config["project"]["name"],
            "pygments_css": get_pygments_css(),
            "pygments_css_dark": get_pygments_css(style="monokai", scope=".theme-dark .highlight"),
            "node_index": {},
            "coverage_index": {},
            "status_data": {},
            "catalog": get_catalog(),
            "config": state.config,
            **viewer_cfg,
        }

        return templates.TemplateResponse(request, "trace_unified.html.j2", context)
    except Exception:
        return JSONResponse(
            {"message": "trace_unified.html.j2 template not yet available"},
            status_code=200,
        )
