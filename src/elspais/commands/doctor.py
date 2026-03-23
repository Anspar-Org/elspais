# Implements: REQ-p00005-E
# Implements: REQ-d00080-C+D
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

import argparse
from pathlib import Path
from typing import Any

from elspais.commands.health import HealthCheck, HealthReport
from elspais.config.schema import ElspaisConfig

_SCHEMA_FIELDS = {f.alias or name for name, f in ElspaisConfig.model_fields.items()} | set(
    ElspaisConfig.model_fields.keys()
)


def _validate_config(config: dict) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig, stripping non-schema keys."""
    filtered = {k: v for k, v in config.items() if k in _SCHEMA_FIELDS}
    assoc = filtered.get("associates")
    if isinstance(assoc, dict) and "paths" in assoc:
        filtered.pop("associates", None)
    return ElspaisConfig.model_validate(filtered)


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


def check_config_required_fields(config: dict[str, Any]) -> HealthCheck:
    """Check that required configuration sections exist."""
    typed_config = _validate_config(config)
    missing = []

    if not typed_config.levels:
        missing.append("levels (requirement level definitions)")

    if not typed_config.scanning.spec.directories:
        missing.append("scanning.spec.directories (where to find spec files)")

    has_levels_with_implements = any(level.implements for level in typed_config.levels.values())
    if not has_levels_with_implements:
        missing.append("levels.*.implements (requirement hierarchy rules)")

    if missing:
        return HealthCheck(
            name="config.required_fields",
            passed=False,
            message=f"Configuration is missing required settings: {', '.join(missing)}",
            category="config",
            details={"missing": missing},
        )

    return HealthCheck(
        name="config.required_fields",
        passed=True,
        message="All required configuration settings are present",
        category="config",
    )


def check_config_pattern_tokens(config: dict[str, Any]) -> HealthCheck:
    """Validate that the ID pattern template uses valid placeholders."""
    import re

    typed_config = _validate_config(config)
    template = typed_config.id_patterns.canonical
    valid_tokens = {"{namespace}", "{level}", "{component}"}
    # Also allow {level.<field>} tokens (e.g. {level.letter})
    level_field_re = re.compile(r"\{level\.\w+\}")

    found_tokens = set(re.findall(r"\{[^}]+\}", template))

    invalid = set()
    for tok in found_tokens:
        if tok not in valid_tokens and not level_field_re.match(tok):
            invalid.add(tok)
    if invalid:
        return HealthCheck(
            name="config.pattern_tokens",
            passed=False,
            message=(
                f"ID pattern has unrecognized placeholders: {', '.join(invalid)}. "
                f"Valid ones are: {', '.join(sorted(valid_tokens))} and {{level.<field>}}"
            ),
            category="config",
            details={"invalid_tokens": list(invalid), "valid_tokens": list(valid_tokens)},
        )

    required = {"{component}"}
    missing = required - found_tokens
    if missing:
        return HealthCheck(
            name="config.pattern_tokens",
            passed=False,
            message=f"ID pattern is missing required placeholders: {', '.join(missing)}",
            category="config",
            details={"missing": list(missing)},
        )

    return HealthCheck(
        name="config.pattern_tokens",
        passed=True,
        message=f"ID pattern is valid: {template}",
        category="config",
    )


def check_config_hierarchy_rules(config: dict[str, Any]) -> HealthCheck:
    """Validate hierarchy rules are consistent."""
    typed_config = _validate_config(config)
    levels = typed_config.levels

    if not isinstance(levels, dict):
        return HealthCheck(
            name="config.hierarchy_rules",
            passed=False,
            message=f"Levels should be a table, but found {type(levels).__name__}",
            category="config",
        )

    issues = []

    for level_name, level_config in levels.items():
        if not isinstance(level_config.implements, list):
            issues.append(
                f"Implements for '{level_name}' should be a list, "
                f"found {type(level_config.implements).__name__}"
            )
            continue
        for parent in level_config.implements:
            if parent not in levels:
                issues.append(f"Level '{level_name}' references unknown parent level '{parent}'")

    if issues:
        return HealthCheck(
            name="config.hierarchy_rules",
            passed=False,
            message=f"Hierarchy rule issues: {'; '.join(issues)}",
            category="config",
            details={"issues": issues},
        )

    return HealthCheck(
        name="config.hierarchy_rules",
        passed=True,
        message=f"Hierarchy rules are valid ({len(levels)} levels configured)",
        category="config",
    )


def check_config_paths_exist(config: dict[str, Any], start_path: Path) -> HealthCheck:
    """Check that configured spec directories exist on disk."""
    typed_config = _validate_config(config)
    spec_dirs = typed_config.scanning.spec.directories

    if not isinstance(spec_dirs, list):
        return HealthCheck(
            name="config.paths_exist",
            passed=False,
            message=f"Spec directories setting should be a list, found {type(spec_dirs).__name__}",
            category="config",
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


def check_config_project_type(config: dict[str, Any]) -> HealthCheck:
    """Check project configuration is valid."""
    from pydantic import ValidationError

    raw = config

    try:
        typed_config = _validate_config(raw)
    except ValidationError as exc:
        errors = [str(e["msg"]) for e in exc.errors()]
        return HealthCheck(
            name="config.project_type",
            passed=False,
            message=errors[0] if errors else str(exc),
            category="config",
            details={"errors": errors},
        )

    project_name = typed_config.project.name
    if project_name:
        return HealthCheck(
            name="config.project_type",
            passed=True,
            message=f"Project '{project_name}' is properly configured",
            category="config",
            details={"name": project_name},
        )

    return HealthCheck(
        name="config.project_type",
        passed=True,
        message="Project name not set (using defaults)",
        category="config",
        severity="info",
    )


def check_config_associated_section(raw: dict) -> HealthCheck:
    """Check that associates configuration is valid."""
    typed_config = _validate_config(raw)
    associates = typed_config.associates
    if not associates:
        return HealthCheck(
            name="config.associated_section",
            passed=True,
            message="No associated projects configured",
            category="config",
            severity="info",
        )

    names = list(associates.keys())
    return HealthCheck(
        name="config.associated_section",
        passed=True,
        message=f"{len(names)} associate(s) configured: {', '.join(names)}",
        category="config",
    )


def run_config_checks(
    config_path: Path | None, config: dict[str, Any], start_path: Path
) -> list[HealthCheck]:
    """Run all configuration checks."""
    return [
        check_config_exists(config_path, start_path),
        check_config_syntax(config_path, start_path),
        check_config_required_fields(config),
        check_config_project_type(config),
        check_config_associated_section(config),
        check_config_pattern_tokens(config),
        check_config_hierarchy_rules(config),
        check_config_paths_exist(config, start_path),
    ]


# =============================================================================
# Environment Checks
# =============================================================================


def check_worktree_status(git_root: Path | None, canonical_root: Path | None) -> HealthCheck:
    """Detect if running in a git worktree."""
    if git_root is None:
        return HealthCheck(
            name="worktree.status",
            passed=True,
            message="Not in a git repository",
            category="environment",
            severity="info",
        )

    if canonical_root and canonical_root != git_root:
        return HealthCheck(
            name="worktree.status",
            passed=True,
            message=f"Running in a git worktree. Main repository: {canonical_root}",
            category="environment",
            severity="info",
            details={"git_root": str(git_root), "canonical_root": str(canonical_root)},
        )

    return HealthCheck(
        name="worktree.status",
        passed=True,
        message="Running in the main repository (not a worktree)",
        category="environment",
        severity="info",
    )


def check_associate_paths(config: dict, canonical_root: Path | None) -> HealthCheck:
    """Check that each configured associate path exists on disk."""
    # Implements: REQ-d00202-A, REQ-d00212-K
    from elspais.config import get_associates_config

    associates = get_associates_config(config)

    if not associates:
        return HealthCheck(
            name="associate.paths_resolvable",
            passed=True,
            message="No associated projects configured",
            category="environment",
            severity="info",
        )

    missing = []
    found = []
    for assoc_name, assoc_info in associates.items():
        path_str = assoc_info["path"]
        p = Path(path_str)
        if not p.is_absolute() and canonical_root:
            p = canonical_root / p
        if p.exists():
            found.append(str(path_str))
        else:
            missing.append(f"{assoc_name}: {path_str} (expected at {p})")

    if missing:
        return HealthCheck(
            name="associate.paths_resolvable",
            passed=False,
            message=f"Associated project paths not found: {'; '.join(missing)}",
            category="environment",
            details={"missing": missing, "found": found},
        )

    return HealthCheck(
        name="associate.paths_resolvable",
        passed=True,
        message=f"All {len(found)} associated project paths exist",
        category="environment",
        details={"found": found},
    )


def check_associate_configs(config: dict, canonical_root: Path | None) -> HealthCheck:
    """Check that each discovered associate has valid configuration."""
    from elspais.associates import discover_associate_from_path
    from elspais.config import get_associates_config  # Implements: REQ-d00202-A, REQ-d00212-K

    associates = get_associates_config(config)

    if not associates:
        return HealthCheck(
            name="associate.configs_valid",
            passed=True,
            message="No associated projects to check",
            category="environment",
            severity="info",
        )

    invalid = []
    valid = []
    for assoc_name, assoc_info in associates.items():
        path_str = assoc_info["path"]
        p = Path(path_str)
        if not p.is_absolute() and canonical_root:
            p = canonical_root / p
        if not p.exists():
            continue  # Already reported by check_associate_paths
        result = discover_associate_from_path(p)
        if isinstance(result, str):
            invalid.append(f"{assoc_name}: {result}")
        else:
            valid.append(f"{assoc_name} ({result.code})")

    if invalid:
        return HealthCheck(
            name="associate.configs_valid",
            passed=False,
            message=f"Associated project configuration issues: {'; '.join(invalid)}",
            category="environment",
            details={"invalid": invalid, "valid": valid},
        )

    return HealthCheck(
        name="associate.configs_valid",
        passed=True,
        message=f"All {len(valid)} associated projects have valid configuration",
        category="environment",
        details={"valid": valid},
    )


def check_local_toml_exists(start_path: Path) -> HealthCheck:
    """Check if local config override file exists."""
    local_path = start_path / ".elspais.local.toml"

    if local_path.exists():
        return HealthCheck(
            name="local_toml.exists",
            passed=True,
            message="Local configuration file found",
            category="environment",
            details={"path": str(local_path)},
        )

    return HealthCheck(
        name="local_toml.exists",
        passed=True,
        message=(
            "No .elspais.local.toml found. "
            "Create one for developer-specific settings (like associate paths)."
        ),
        category="environment",
        severity="info",
    )


def check_cross_repo_in_committed_config(config_path: Path | None) -> HealthCheck:
    """Warn if cross-repo paths are in the committed config file."""
    if not config_path or not config_path.exists():
        return HealthCheck(
            name="cross_repo.in_committed",
            passed=True,
            message="No committed configuration file to check",
            category="environment",
            severity="info",
        )

    try:
        content = config_path.read_text(encoding="utf-8")
        from elspais.config import parse_toml

        data = parse_toml(content)
    except Exception:
        return HealthCheck(
            name="cross_repo.in_committed",
            passed=True,
            message="Could not parse configuration file (reported by config.syntax check)",
            category="environment",
            severity="info",
        )

    # Implements: REQ-d00212-F
    cross_repo_paths = []
    spec_dirs = data.get("scanning", {}).get("spec", {}).get("directories", [])
    if isinstance(spec_dirs, list):
        for d in spec_dirs:
            if ".." in str(d):
                cross_repo_paths.append(f"scanning.spec.directories: {d}")

    # Check named associates for cross-repo paths (v3 format)
    associates = data.get("associates", {})
    if isinstance(associates, dict):
        for assoc_name, assoc_info in associates.items():
            if isinstance(assoc_info, dict):
                assoc_path = assoc_info.get("path", "")
                if ".." in str(assoc_path):
                    cross_repo_paths.append(f"associates.{assoc_name}.path: {assoc_path}")

    if cross_repo_paths:
        return HealthCheck(
            name="cross_repo.in_committed",
            passed=False,
            message=(
                f"Cross-project paths found in shared config ({', '.join(cross_repo_paths)}). "
                "Move these to .elspais.local.toml so they don't affect other developers."
            ),
            category="environment",
            severity="warning",
            details={"paths": cross_repo_paths},
        )

    return HealthCheck(
        name="cross_repo.in_committed",
        passed=True,
        message="No cross-project paths in shared configuration",
        category="environment",
    )


def run_environment_checks(
    config: dict,
    git_root: Path | None,
    canonical_root: Path | None,
    config_path: Path | None,
    start_path: Path,
) -> list[HealthCheck]:
    """Run all environment checks."""
    return [
        check_worktree_status(git_root, canonical_root),
        check_associate_paths(config, canonical_root),
        check_associate_configs(config, canonical_root),
        check_local_toml_exists(start_path),
        check_cross_repo_in_committed_config(config_path),
    ]


# =============================================================================
# Docs Drift Check
# =============================================================================


# Implements: REQ-d00210
# Schema sections to check (alias names for TOML keys).
# Excludes project-type-conditional sections (associates, core, associated).
_CONDITIONAL_SECTIONS = {"associates"}

_SCHEMA_SECTIONS: set[str] = set()


def _get_schema_sections() -> set[str]:
    """Return the set of required schema section names (cached)."""
    global _SCHEMA_SECTIONS  # noqa: PLW0603
    if _SCHEMA_SECTIONS:
        return _SCHEMA_SECTIONS

    sections: set[str] = set()
    for name, field_info in ElspaisConfig.model_fields.items():
        alias = field_info.alias or name
        sections.add(alias)
    _SCHEMA_SECTIONS = sections - _CONDITIONAL_SECTIONS
    return _SCHEMA_SECTIONS


def _parse_docs_sections(docs_path: Path) -> set[str]:
    """Extract top-level TOML section headers from a docs markdown file.

    Only looks inside fenced code blocks (```toml ... ```) and only
    captures top-level sections (no dots in the name).
    """
    import re

    content = docs_path.read_text(encoding="utf-8")
    sections: set[str] = set()
    in_toml_block = False
    in_section = False  # True once we see the first [section] header
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```toml"):
            in_toml_block = True
            in_section = False
            continue
        if stripped.startswith("```") and in_toml_block:
            in_toml_block = False
            continue
        if in_toml_block:
            # Match top-level [section] or extract parent from [section.sub]
            m = re.match(r"^\[([A-Za-z0-9_-]+)(?:\.[A-Za-z0-9_.-]+)?\]", stripped)
            if m:
                sections.add(m.group(1))
                in_section = True
            # Match bare top-level keys before any section (e.g. "version = 3")
            elif not in_section:
                m = re.match(r"^([A-Za-z0-9_-]+)\s*=", stripped)
                if m:
                    sections.add(m.group(1))
    return sections


def check_docs_drift(docs_path: Path) -> HealthCheck:
    """Check for drift between ElspaisConfig schema and docs/configuration.md."""
    if not docs_path.exists():
        return HealthCheck(
            name="docs.config_drift",
            passed=True,
            message="No docs/configuration.md found (skipping drift check)",
            category="docs",
            severity="info",
        )

    schema_sections = _get_schema_sections()
    docs_sections = _parse_docs_sections(docs_path) - _CONDITIONAL_SECTIONS

    undocumented = sorted(schema_sections - docs_sections)
    stale = sorted(docs_sections - schema_sections)

    if not undocumented and not stale:
        return HealthCheck(
            name="docs.config_drift",
            passed=True,
            message="docs/configuration.md is in sync with schema",
            category="docs",
        )

    parts = []
    if undocumented:
        parts.append(f"{len(undocumented)} undocumented: {', '.join(undocumented)}")
    if stale:
        parts.append(f"{len(stale)} stale: {', '.join(stale)}")

    return HealthCheck(
        name="docs.config_drift",
        passed=False,
        message=f"Config docs drift detected: {'; '.join(parts)}",
        category="docs",
        severity="warning",
        details={"undocumented": undocumented, "stale": stale},
    )


def _print_text_report(report: HealthReport, verbose: bool = False) -> None:
    """Print human-readable doctor report."""
    categories = ["config", "environment", "docs"]

    for category in categories:
        checks = list(report.iter_by_category(category))
        if not checks:
            continue

        passed = sum(1 for c in checks if c.passed)
        total = len(checks)
        status = "OK" if passed == total else "ISSUES FOUND"
        label = category.upper()
        print(f"\n{label} ({passed}/{total} checks passed) - {status}")
        print("-" * 50)

        for check in checks:
            if check.passed:
                icon = "ok"
            elif check.severity == "warning":
                icon = "!!"
            elif check.severity == "info":
                icon = "--"
            else:
                icon = "XX"

            print(f"  [{icon}] {check.message}")

            if verbose and check.details:
                for key, value in check.details.items():
                    if isinstance(value, list) and len(value) > 3:
                        print(f"        {key}: {value[:3]} ... ({len(value)} total)")
                    else:
                        print(f"        {key}: {value}")

    print()
    total = len(report.checks)
    failed = report.failed
    warnings = report.warnings
    if failed == 0 and warnings == 0:
        print(f"All {total} checks passed. Your elspais installation looks good.")
    elif failed == 0:
        print(f"{total - warnings} checks passed, {warnings} warnings. No critical issues.")
    else:
        print(f"{failed} issues found out of {total} checks. See above for details.")


def run(args: argparse.Namespace) -> int:
    """Run the doctor command."""
    from elspais.config import find_config_file, find_git_root, get_config

    config_path = getattr(args, "config", None)
    if config_path:
        config_path = Path(config_path)
    canonical_root = getattr(args, "canonical_root", None)
    start_path = Path.cwd()
    git_root = find_git_root(start_path)

    report = HealthReport()

    # Load config for checks
    config = None
    config_dict = {}
    try:
        config_dict = get_config(
            config_path,
            start_path=start_path,
        )
        config = config_dict
        for check in run_config_checks(config_path, config, start_path):
            report.add(check)
    except Exception as e:
        report.add(
            HealthCheck(
                name="config.load",
                passed=False,
                message=f"Could not load configuration: {e}",
                category="config",
            )
        )

    # Find the actual config file path for cross-repo check
    actual_config_path = config_path
    if not actual_config_path:
        actual_config_path = find_config_file(start_path)

    # Environment checks
    for check in run_environment_checks(
        config_dict, git_root, canonical_root, actual_config_path, start_path
    ):
        report.add(check)

    # Docs drift check
    docs_path = (git_root or start_path) / "docs" / "configuration.md"
    report.add(check_docs_drift(docs_path))

    # Output
    fmt = getattr(args, "format", "text") or "text"
    if fmt == "json":
        import json

        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_text_report(report, verbose=getattr(args, "verbose", False))

    return 0 if report.is_healthy else 1
