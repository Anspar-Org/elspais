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
    template context: config_types, config_relationship_kinds,
    config_statuses.
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

    config_statuses: list[str] = []
    if typed.rules.format.allowed_statuses:
        config_statuses = list(typed.rules.format.allowed_statuses)
    elif typed.rules.format.status_roles:
        # Derive from status_roles when allowed_statuses not explicitly set
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
    }


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

        gen = HTMLGenerator(state.graph, base_path=str(state.repo_root))
        gen._annotate_git_state()
        stats = gen._compute_stats()
        journeys = gen._collect_journeys()
        stats.journey_count = len(journeys)
        roles = get_status_roles(state.config)
        statuses = roles.sort_by_role(list(gen._collect_unique_values("status")))
        topics = sorted(gen._collect_unique_values("topic"))
        default_hidden = roles.default_hidden_statuses()

        viewer_cfg = _extract_viewer_config(state.config)

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
            "repo_name": state.config.get("project", {}).get("name") or "unknown",
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
