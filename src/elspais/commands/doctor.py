# Implements: REQ-p00005-E
"""
elspais.commands.doctor - Diagnose environment and installation health.

Checks the elspais setup on this machine:
- Configuration file exists and is valid
- Required settings are present
- Spec directories exist
- Worktree detection and canonical root
- Associate path resolution
- Local config overrides
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from elspais.commands.health import HealthCheck

if TYPE_CHECKING:
    from elspais.config import ConfigLoader


# =============================================================================
# Config Checks (moved from health.py, messages rewritten for lay-persons)
# =============================================================================


def check_config_exists(config_path: Path | None, start_path: Path) -> HealthCheck:
    """Check if config file exists and is accessible."""
    from elspais.config import find_config_file

    if config_path and config_path.exists():
        return HealthCheck(
            name="config.exists",
            passed=True,
            message=f"Configuration file found at {config_path}",
            category="config",
            details={"path": str(config_path)},
        )

    found = find_config_file(start_path)
    if found:
        return HealthCheck(
            name="config.exists",
            passed=True,
            message=f"Configuration file found at {found}",
            category="config",
            details={"path": str(found)},
        )

    return HealthCheck(
        name="config.exists",
        passed=True,
        message="No configuration file found (using defaults). Run 'elspais init' to create one.",
        category="config",
        severity="info",
    )


def check_config_syntax(config_path: Path | None, start_path: Path) -> HealthCheck:
    """Check if config file has valid TOML syntax."""
    from elspais.config import find_config_file

    actual_path = (
        config_path if config_path and config_path.exists() else find_config_file(start_path)
    )

    if not actual_path:
        return HealthCheck(
            name="config.syntax",
            passed=True,
            message="No configuration file to check (using defaults)",
            category="config",
            severity="info",
        )

    try:
        content = actual_path.read_text(encoding="utf-8")
        from elspais.config import parse_toml

        parse_toml(content)
        return HealthCheck(
            name="config.syntax",
            passed=True,
            message="Configuration file syntax is valid",
            category="config",
        )
    except Exception as e:
        return HealthCheck(
            name="config.syntax",
            passed=False,
            message=f"Configuration file has a formatting error: {e}",
            category="config",
            details={"error": str(e), "path": str(actual_path)},
        )


def check_config_required_fields(config: ConfigLoader) -> HealthCheck:
    """Check that required configuration sections exist."""
    raw = config.get_raw()
    missing = []

    patterns = raw.get("patterns", {})
    if not patterns.get("types"):
        missing.append("patterns.types (requirement type definitions)")

    spec = raw.get("spec", {})
    if not spec.get("directories"):
        missing.append("spec.directories (where to find spec files)")

    rules = raw.get("rules", {})
    if not rules.get("hierarchy"):
        missing.append("rules.hierarchy (requirement hierarchy rules)")

    if missing:
        return HealthCheck(
            name="config.required_fields",
            passed=False,
            message=f"Configuration is missing required settings: {', '.join(missing)}",
            category="config",
            severity="warning",
            details={"missing": missing},
        )

    return HealthCheck(
        name="config.required_fields",
        passed=True,
        message="All required configuration settings are present",
        category="config",
    )


def check_config_pattern_tokens(config: ConfigLoader) -> HealthCheck:
    """Validate that the ID pattern template uses valid placeholders."""
    import re

    template = config.get("patterns.id_template", "")
    valid_tokens = {"{prefix}", "{type}", "{id}", "{associated}"}

    found_tokens = set(re.findall(r"\{[^}]+\}", template))

    invalid = found_tokens - valid_tokens
    if invalid:
        return HealthCheck(
            name="config.pattern_tokens",
            passed=False,
            message=(
                f"ID pattern has unrecognized placeholders: {', '.join(invalid)}. "
                f"Valid ones are: {', '.join(sorted(valid_tokens))}"
            ),
            category="config",
            details={"invalid_tokens": list(invalid), "valid_tokens": list(valid_tokens)},
        )

    required = {"{prefix}", "{id}"}
    missing = required - found_tokens
    if missing:
        return HealthCheck(
            name="config.pattern_tokens",
            passed=False,
            message=f"ID pattern is missing required placeholders: {', '.join(missing)}",
            category="config",
            severity="warning",
            details={"missing": list(missing)},
        )

    return HealthCheck(
        name="config.pattern_tokens",
        passed=True,
        message=f"ID pattern is valid: {template}",
        category="config",
    )


def check_config_hierarchy_rules(config: ConfigLoader) -> HealthCheck:
    """Validate hierarchy rules are consistent."""
    hierarchy = config.get("rules.hierarchy", {})
    types = config.get("patterns.types", {})

    if not isinstance(hierarchy, dict):
        return HealthCheck(
            name="config.hierarchy_rules",
            passed=False,
            message=f"Hierarchy rules should be a table, but found {type(hierarchy).__name__}",
            category="config",
            severity="warning",
        )

    if not isinstance(types, dict):
        return HealthCheck(
            name="config.hierarchy_rules",
            passed=False,
            message=f"Requirement types should be a table, but found {type(types).__name__}",
            category="config",
            severity="warning",
        )

    issues = []
    non_level_keys = {"allowed_implements", "allow_circular", "allow_orphans", "allowed"}

    for level, allowed_parents in hierarchy.items():
        if level in non_level_keys:
            continue
        if level not in types:
            issues.append(f"Rule references unknown level '{level}'")
            continue
        if not isinstance(allowed_parents, list):
            issues.append(
                f"Rule for '{level}' should be a list, found {type(allowed_parents).__name__}"
            )
            continue
        for parent in allowed_parents:
            if parent not in types:
                issues.append(f"Level '{level}' references unknown parent level '{parent}'")

    if issues:
        return HealthCheck(
            name="config.hierarchy_rules",
            passed=False,
            message=f"Hierarchy rule issues: {'; '.join(issues)}",
            category="config",
            severity="warning",
            details={"issues": issues},
        )

    return HealthCheck(
        name="config.hierarchy_rules",
        passed=True,
        message=f"Hierarchy rules are valid ({len(hierarchy)} levels configured)",
        category="config",
    )


def check_config_paths_exist(config: ConfigLoader, start_path: Path) -> HealthCheck:
    """Check that configured spec directories exist on disk."""
    spec_dirs = config.get("spec.directories", ["spec"])

    if not isinstance(spec_dirs, list):
        return HealthCheck(
            name="config.paths_exist",
            passed=False,
            message=f"Spec directories setting should be a list, found {type(spec_dirs).__name__}",
            category="config",
            severity="warning",
        )

    missing = []
    found = []

    for spec_dir in spec_dirs:
        full_path = start_path / spec_dir
        if full_path.exists():
            found.append(str(spec_dir))
        else:
            missing.append(str(spec_dir))

    if missing:
        return HealthCheck(
            name="config.paths_exist",
            passed=False,
            message=f"Spec directories not found on disk: {', '.join(missing)}",
            category="config",
            details={"missing": missing, "found": found},
        )

    return HealthCheck(
        name="config.paths_exist",
        passed=True,
        message=f"All {len(found)} spec directories exist",
        category="config",
        details={"directories": found},
    )


def check_config_project_type(config: ConfigLoader) -> HealthCheck:
    """Check project type configuration is consistent."""
    from elspais.config import validate_project_config

    raw = config.get_raw()
    errors = validate_project_config(raw)

    if errors:
        return HealthCheck(
            name="config.project_type",
            passed=False,
            message=errors[0],
            category="config",
            severity="warning",
            details={"errors": errors},
        )

    project_type = raw.get("project", {}).get("type")
    if project_type:
        return HealthCheck(
            name="config.project_type",
            passed=True,
            message=f"Project type '{project_type}' is properly configured",
            category="config",
            details={"type": project_type},
        )

    return HealthCheck(
        name="config.project_type",
        passed=True,
        message="Project type not set (using defaults)",
        category="config",
        severity="info",
    )


def run_config_checks(
    config_path: Path | None, config: ConfigLoader, start_path: Path
) -> list[HealthCheck]:
    """Run all configuration checks."""
    return [
        check_config_exists(config_path, start_path),
        check_config_syntax(config_path, start_path),
        check_config_required_fields(config),
        check_config_project_type(config),
        check_config_pattern_tokens(config),
        check_config_hierarchy_rules(config),
        check_config_paths_exist(config, start_path),
    ]
