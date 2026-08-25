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

from elspais.commands.health import HealthCheck, HealthReport, skipped_check
from elspais.config.schema import ElspaisConfig
from elspais.utilities.findings import Severity, severity_for


def _validate_config(config: dict[str, Any]) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig (see config.validate_config)."""
    from elspais.config import validate_config

    return validate_config(config)


# =============================================================================
# Config Checks (moved from health.py, messages rewritten for lay-persons)
# =============================================================================


def check_config_exists(
    config_path: Path | None, start_path: Path, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Check if config file exists and is accessible."""
    severity = severity_for("config.exists", config)
    if severity == Severity.OFF:
        return skipped_check("config.exists", "A missing configuration file")

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


def check_config_syntax(
    config_path: Path | None, start_path: Path, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Check if config file has valid TOML syntax."""
    severity = severity_for("config.syntax", config)
    if severity == Severity.OFF:
        return skipped_check("config.syntax", "A configuration file that does not parse")

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
            severity=severity,
            details={"error": str(e), "path": str(actual_path)},
        )


def check_config_required_fields(config: dict[str, Any]) -> HealthCheck:
    """Check that required configuration sections exist."""
    severity = severity_for("config.required_fields", config)
    if severity == Severity.OFF:
        return skipped_check(
            "config.required_fields", "Required configuration fields that are absent"
        )

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
            severity=severity,
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
    severity = severity_for("config.pattern_tokens", config)
    if severity == Severity.OFF:
        return skipped_check("config.pattern_tokens", "Identifier patterns that do not read")

    import re

    typed_config = _validate_config(config)
    template = typed_config.id_patterns.canonical
    valid_tokens = {"{namespace}", "{level}", "{type}", "{component}"}
    # Also allow {level.<field>} and {type.<field>} tokens (e.g. {level.letter})
    level_field_re = re.compile(r"\{(?:level|type)\.\w+\}")

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
            severity=severity,
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
            severity=severity,
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
    severity = severity_for("config.hierarchy_rules", config)
    if severity == Severity.OFF:
        return skipped_check("config.hierarchy_rules", "Hierarchy rules that do not read")

    typed_config = _validate_config(config)
    levels = typed_config.levels

    if not isinstance(levels, dict):
        return HealthCheck(
            name="config.hierarchy_rules",
            passed=False,
            message=f"Levels should be a table, but found {type(levels).__name__}",
            category="config",
            severity=severity,
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
            severity=severity,
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
    severity = severity_for("config.paths_exist", config)
    if severity == Severity.OFF:
        return skipped_check("config.paths_exist", "Configured directories that do not exist")

    typed_config = _validate_config(config)
    spec_dirs = typed_config.scanning.spec.directories

    if not isinstance(spec_dirs, list):
        return HealthCheck(
            name="config.paths_exist",
            passed=False,
            message=f"Spec directories setting should be a list, found {type(spec_dirs).__name__}",
            category="config",
            severity=severity,
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
            severity=severity,
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
    severity = severity_for("config.project_type", config)
    if severity == Severity.OFF:
        return skipped_check("config.project_type", "A project type the tool does not know")

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
            severity=severity,
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


def check_config_associated_section(raw: dict, config: dict[str, Any] | None = None) -> HealthCheck:
    """Check the `[associates]` declarations in this repository's own config.

    This reads one file and reports what that file says. The federation
    the tool actually builds is usually wider, because associates carry
    declarations of their own; the associate path and configuration
    checks are what speak for the federation as a whole.
    """
    severity = severity_for("config.associated_section", config)
    if severity == Severity.OFF:
        return skipped_check("config.associated_section", "Associate declarations that do not read")

    typed_config = _validate_config(raw)
    associates = typed_config.associates
    if not associates:
        return HealthCheck(
            name="config.associated_section",
            passed=True,
            message="No associated projects declared in this configuration",
            category="config",
            severity="info",
        )

    names = list(associates.keys())
    return HealthCheck(
        name="config.associated_section",
        passed=True,
        message=(f"{len(names)} associate(s) declared in this configuration: {', '.join(names)}"),
        category="config",
    )


def run_config_checks(
    config_path: Path | None, config: dict[str, Any], start_path: Path
) -> list[HealthCheck]:
    """Run all configuration checks."""
    return [
        check_config_exists(config_path, start_path, config),
        check_config_syntax(config_path, start_path, config),
        check_config_required_fields(config),
        check_config_project_type(config),
        check_config_associated_section(config, config),
        check_config_pattern_tokens(config),
        check_config_hierarchy_rules(config),
        check_config_paths_exist(config, start_path),
    ]


# =============================================================================
# Environment Checks
# =============================================================================


def check_worktree_status(
    git_root: Path | None, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Report git repository status."""
    severity = severity_for("worktree.status", config)
    if severity == Severity.OFF:
        return skipped_check("worktree.status", "The state of the git worktree")

    if git_root is None:
        return HealthCheck(
            name="worktree.status",
            passed=True,
            message="Not in a git repository",
            category="environment",
            severity="info",
        )

    return HealthCheck(
        name="worktree.status",
        passed=True,
        message=f"Git root: {git_root}",
        category="environment",
        severity="info",
    )


def check_associate_paths(config: dict, git_root: Path | None) -> HealthCheck:
    """Check that every federated project's path exists on disk.

    Membership is the whole federation: a project reached through an
    associate's own declarations is built into the same graph, so a
    report that covered only the projects named here would describe less
    than the tool actually uses.
    """
    severity = severity_for("associate.paths_resolvable", config)
    if severity == Severity.OFF:
        return skipped_check("associate.paths_resolvable", "Associate paths that do not resolve")

    # Implements: REQ-d00202-A+D+I, REQ-d00203-C, REQ-d00212-K
    from elspais.graph.federation_plan import plan_federation_or_error

    plan, plan_error = plan_federation_or_error(config, git_root or Path.cwd())
    if plan_error is not None:
        return HealthCheck(
            name="associate.paths_resolvable",
            passed=False,
            message=f"Associated projects could not be resolved: {plan_error}",
            category="environment",
            severity=severity,
            details={"error": plan_error},
        )

    members = plan[1:]
    if not members:
        return HealthCheck(
            name="associate.paths_resolvable",
            passed=True,
            message="No associated projects configured",
            category="environment",
            severity="info",
        )

    missing = []
    found = []
    for member in members:
        via = " -> ".join(member.declaration_path)
        if member.repo_root.exists():
            found.append(str(member.repo_root))
        else:
            missing.append(f"{member.name}: {member.repo_root} (declared via {via})")

    if missing:
        return HealthCheck(
            name="associate.paths_resolvable",
            passed=False,
            message=f"Associated project paths not found: {'; '.join(missing)}",
            category="environment",
            severity=severity,
            details={"missing": missing, "found": found},
        )

    return HealthCheck(
        name="associate.paths_resolvable",
        passed=True,
        message=f"All {len(found)} federated project paths exist",
        category="environment",
        details={"found": found},
    )


def check_associate_configs(config: dict, git_root: Path | None) -> HealthCheck:
    """Check that every federated project has a usable configuration.

    A project whose configuration cannot be loaded is named here with its
    path and the reason, wherever in the federation it was declared.
    """
    severity = severity_for("associate.configs_valid", config)
    if severity == Severity.OFF:
        return skipped_check("associate.configs_valid", "Associate configurations that do not load")

    # Implements: REQ-d00202-A+D+I, REQ-d00203-C, REQ-d00212-K
    from elspais.associates import discover_associate_from_path
    from elspais.graph.federation_plan import plan_federation_or_error

    plan, plan_error = plan_federation_or_error(config, git_root or Path.cwd())
    if plan_error is not None:
        return HealthCheck(
            name="associate.configs_valid",
            passed=False,
            message=f"Associated project configuration could not be resolved: {plan_error}",
            category="environment",
            severity=severity,
            details={"error": plan_error},
        )

    members = plan[1:]
    if not members:
        return HealthCheck(
            name="associate.configs_valid",
            passed=True,
            message="No associated projects to check",
            category="environment",
            severity="info",
        )

    invalid = []
    valid = []
    for member in members:
        via = " -> ".join(member.declaration_path)
        if member.error is not None:
            if not member.repo_root.exists():
                continue  # Already reported by check_associate_paths
            invalid.append(f"{member.name} (declared via {via}): {member.error}")
            continue
        # Loading a configuration for a directory is not the same question
        # as the directory being an elspais project of its own; discovery
        # is what answers the second.
        result = discover_associate_from_path(member.repo_root)
        if isinstance(result, str):
            invalid.append(f"{member.name} (declared via {via}): {result}")
        else:
            valid.append(f"{member.name} ({result.code})")

    if invalid:
        return HealthCheck(
            name="associate.configs_valid",
            passed=False,
            message=f"Associated project configuration issues: {'; '.join(invalid)}",
            category="environment",
            severity=severity,
            details={"invalid": invalid, "valid": valid},
        )

    return HealthCheck(
        name="associate.configs_valid",
        passed=True,
        message=f"All {len(valid)} federated projects have valid configuration",
        category="environment",
        details={"valid": valid},
    )


def check_local_toml_exists(start_path: Path, config: dict[str, Any] | None = None) -> HealthCheck:
    """Check if local config override file exists."""
    severity = severity_for("local_toml.exists", config)
    if severity == Severity.OFF:
        return skipped_check("local_toml.exists", "A local configuration override")

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


def check_cross_repo_in_committed_config(
    config_path: Path | None, config: dict[str, Any] | None = None
) -> HealthCheck:
    """Warn if cross-repo paths are in the committed config file."""
    severity = severity_for("cross_repo.in_committed", config)
    if severity == Severity.OFF:
        return skipped_check(
            "cross_repo.in_committed", "Cross-project paths in shared configuration"
        )

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
            severity=severity,
            details={"paths": cross_repo_paths},
        )

    return HealthCheck(
        name="cross_repo.in_committed",
        passed=True,
        message="No cross-project paths in shared configuration",
        category="environment",
    )


# Implements: REQ-o00076-M
def check_mcp_address(git_root: Path | None, config: dict[str, Any] | None = None) -> HealthCheck:
    """Whether the address a client here would use reaches this tree.

    A client configured with an address it resolves once cannot tell a
    wrong address from a right one nothing is serving yet: both fail to
    connect. Only the tool can compare the address against the tree, so
    only the tool can say which it is.

    This asks about a client's connection and nothing else. Which
    repositories this tree federates does not bear on it -- a tree may
    properly name any other tree as an associate.
    """
    severity = severity_for("mcp.address", config)
    if severity == Severity.OFF:
        return skipped_check("mcp.address", "An address that does not reach this working tree")

    import os
    from urllib.parse import urlparse

    configured = os.environ.get("ELSPAIS_MCP_URL", "").strip()
    if not configured:
        return HealthCheck(
            name="mcp.address",
            passed=True,
            message="No client address is set here, so nothing reaches past this tree",
            category="environment",
            severity="info",
        )

    if git_root is None:
        return HealthCheck(
            name="mcp.address",
            passed=True,
            message="Not a working tree, so there is no address to agree with",
            category="environment",
            severity="info",
        )

    try:
        configured_port = urlparse(configured).port
    except ValueError:
        configured_port = None
    if configured_port is None:
        return HealthCheck(
            name="mcp.address",
            passed=False,
            message=f"ELSPAIS_MCP_URL names no port that can be read: {configured}",
            category="environment",
            severity=severity,
            details={"configured": configured},
        )

    from elspais.mcp.daemon import get_daemon_info, reserved_port

    info = get_daemon_info(git_root) or {}
    tree_port = reserved_port(git_root) or info.get("port")
    if not isinstance(tree_port, int):
        return HealthCheck(
            name="mcp.address",
            passed=True,
            message=(
                f"This tree has settled no address yet, so {configured_port} "
                "cannot be judged against it"
            ),
            category="environment",
            severity="info",
            details={"configured_port": configured_port},
        )

    if configured_port == tree_port:
        return HealthCheck(
            name="mcp.address",
            passed=True,
            message=f"A client here reaches this tree, on port {tree_port}",
            category="environment",
            details={"port": tree_port},
        )

    return HealthCheck(
        name="mcp.address",
        passed=False,
        message=(
            f"A client here would connect to port {configured_port}, but this "
            f"working tree is served on port {tree_port}. The address names "
            f"another tree, or was written down rather than resolved. Re-derive "
            f'it in this shell with: eval "$(elspais mcp env)"'
        ),
        category="environment",
        severity=severity,
        details={"configured_port": configured_port, "tree_port": tree_port},
    )


# Implements: REQ-o00076-M
def _main_repo_root(git_root: Path) -> Path | None:
    """The repository a worktree belongs to, which is where its client
    configuration is keyed. Worktrees share it, so an entry written under
    one is read by all of them."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    common = Path(out.stdout.strip())
    if not common.is_absolute():
        common = (git_root / common).resolve()
    return common.parent


# Implements: REQ-o00076-M
def _registration_sources(git_root: Path, claude_config: Path | None) -> list[tuple[str, dict]]:
    """Every place a client here could read an elspais registration from.

    Precedence between them is the client's business and changes with the
    client. Every literal is wrong under REQ-o00076-L whichever one wins,
    and the reader has to correct all of them, so all are reported rather
    than one being picked.
    """
    import json

    sources: list[tuple[str, dict]] = []

    project_file = git_root / ".mcp.json"
    try:
        entry = json.loads(project_file.read_text()).get("mcpServers", {}).get("elspais")
        if isinstance(entry, dict):
            sources.append((".mcp.json", entry))
    except (OSError, json.JSONDecodeError, AttributeError):
        pass

    config_path = claude_config or (Path.home() / ".claude.json")
    try:
        data = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return sources
    if not isinstance(data, dict):
        return sources

    entry = (data.get("mcpServers") or {}).get("elspais")
    if isinstance(entry, dict):
        sources.append((f"user scope in {config_path.name}", entry))

    projects = data.get("projects") or {}
    seen: set[str] = set()
    for root in (git_root, _main_repo_root(git_root)):
        if root is None:
            continue
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        entry = ((projects.get(key) or {}).get("mcpServers") or {}).get("elspais")
        if isinstance(entry, dict):
            sources.append((f"{key} in {config_path.name}", entry))
    return sources


# Implements: REQ-o00076-M
def check_mcp_registration(
    git_root: Path | None,
    config: dict[str, Any] | None = None,
    claude_config: Path | None = None,
) -> HealthCheck:
    """Whether any registration a client here reads names a fixed address.

    A registration is read in every working tree that shares it, so an
    address written into one names the tree that wrote it as though it
    were the tree reading (REQ-o00076-L). Such an entry is wrong from the
    moment it is written rather than stale later, and it fails the same
    way an address nobody is serving fails, which is why it has to be
    named rather than left to be inferred from a refused connection.

    Registrations naming a variable are resolved by the reader and are
    not judged here; whether the reader supplies one is `mcp.address`.
    An entry naming a command rather than an address carries no address
    to be wrong about.
    """
    severity = severity_for("mcp.registration", config)
    if severity == Severity.OFF:
        return skipped_check("mcp.registration", "A registration naming a fixed address")

    if git_root is None:
        return HealthCheck(
            name="mcp.registration",
            passed=True,
            message="Not a working tree, so no registration belongs to it",
            category="environment",
            severity="info",
        )

    literals: list[str] = []
    for where, entry in _registration_sources(git_root, claude_config):
        url = entry.get("url")
        if not isinstance(url, str) or "${" in url or not url.strip():
            continue
        literals.append(f"{where}: {url}")

    if not literals:
        return HealthCheck(
            name="mcp.registration",
            passed=True,
            message="No client registration reaching this tree names a fixed address",
            category="environment",
        )

    return HealthCheck(
        name="mcp.registration",
        passed=False,
        message=(
            f"{len(literals)} client registration(s) reaching this tree name a "
            f"fixed address, which cannot be right for every tree that reads "
            f"them: {'; '.join(literals)}. Re-run `elspais mcp install` to "
            f"register the variable instead."
        ),
        category="environment",
        severity=severity,
        details={"literals": literals},
    )


def run_environment_checks(
    config: dict,
    git_root: Path | None,
    config_path: Path | None,
    start_path: Path,
) -> list[HealthCheck]:
    """Run all environment checks."""
    return [
        check_worktree_status(git_root, config),
        check_associate_paths(config, git_root),
        check_associate_configs(config, git_root),
        check_local_toml_exists(start_path, config),
        check_cross_repo_in_committed_config(config_path, config),
        check_mcp_address(git_root, config),
        check_mcp_registration(git_root, config),
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
            # Match top-level [section] or [[array.of.tables]] headers,
            # extracting the parent from dotted names ([section.sub] or
            # [[section.sub.arr]] both yield "section"). Double-bracket
            # headers must enter a section too, or their bare keys would be
            # misparsed as top-level sections by the fallback below.
            m = re.match(r"^\[\[?([A-Za-z0-9_-]+)(?:\.[A-Za-z0-9_.-]+)?\]\]?", stripped)
            if m:
                sections.add(m.group(1))
                in_section = True
            # Match bare top-level keys before any section (e.g. "version = 3")
            elif not in_section:
                m = re.match(r"^([A-Za-z0-9_-]+)\s*=", stripped)
                if m:
                    sections.add(m.group(1))
    return sections


def check_docs_drift(docs_path: Path, config: dict[str, Any] | None = None) -> HealthCheck:
    """Check for drift between ElspaisConfig schema and docs/configuration.md."""
    severity = severity_for("docs.config_drift", config)
    if severity == Severity.OFF:
        return skipped_check("docs.config_drift", "Documentation that has drifted from the schema")

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
        severity=severity,
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
    for check in run_environment_checks(config_dict, git_root, actual_config_path, start_path):
        report.add(check)

    # Docs drift check
    docs_path = (git_root or start_path) / "docs" / "configuration.md"
    report.add(check_docs_drift(docs_path, config_dict))

    # Output
    fmt = getattr(args, "format", "text") or "text"
    if fmt == "json":
        import json

        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_text_report(report, verbose=getattr(args, "verbose", False))

    return 0 if report.is_healthy else 1
