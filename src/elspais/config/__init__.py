"""Config module - Configuration loading and management.

Exports:
- load_config: Load config from TOML file
- find_config_file: Find .elspais.toml in directory hierarchy
- config_defaults: Get default config dict from Pydantic schema
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit


# Implements: REQ-d00207-A
def config_defaults() -> dict[str, Any]:
    """Get default configuration dict derived from Pydantic schema.

    All defaults are defined as Pydantic field defaults in schema.py.
    This function validates an empty dict to produce the full defaults,
    then dumps to a dict keyed as the TOML is written, hyphens and all.

    Returns:
        Default configuration dictionary with hyphenated keys.
    """
    from elspais.config.schema import ElspaisConfig

    return ElspaisConfig.model_validate({}).model_dump(by_alias=True)


def default_level_keys() -> list[str]:
    """Return the default level keys (rank-sorted) for use as a fallback.

    Single source of truth for "what to fall back to when a config is missing
    or has no `[levels]` section". Consumers like `commands/summary.py`,
    `pdf/assembler.py`, and `html/generator.py` use this rather than hard-coding
    `["prd", "ops", "dev"]`.
    """
    levels = config_defaults().get("levels") or {}
    if not isinstance(levels, dict) or not levels:
        return []
    ranked = sorted(
        ((k, v.get("rank", 9999) if isinstance(v, dict) else 9999) for k, v in levels.items()),
        key=lambda kv: kv[1],
    )
    return [k for k, _r in ranked]


# Implements: REQ-d00291-A
def level_expects_validation(config: dict[str, Any], level_key: str | None) -> bool:
    """Return whether a level is expected to have UAT validation.

    Single source of truth for "does this level expect a USER_JOURNEY to
    Validate its requirements". When true, absence of UAT coverage for a
    requirement at that level is a real gap (health `uat.coverage` + `gaps
    unvalidated`) and renders red in the viewer. Default false so existing
    projects are unaffected until they opt in.

    The lookup is case-insensitive on the level key: `[levels]` sections are
    typically keyed lowercase (`prd`) while ``node.level`` is often upper
    (`PRD`) -- mirrors how summary.py / aggregation.py normalize level case.
    Consumers (viewer, health, gaps) MUST call this helper rather than reading
    ``config["levels"]`` directly.
    """
    if not level_key:
        return False
    levels = (config or {}).get("levels")
    if not isinstance(levels, dict):
        return False
    target = level_key.lower()
    for key, spec in levels.items():
        if not isinstance(key, str) or key.lower() != target:
            continue
        if isinstance(spec, dict):
            return bool(spec.get("expects_validation", False))
        return bool(getattr(spec, "expects_validation", False))
    return False


# Implements: REQ-d00291-D+E
def status_expects_implementation(config: dict[str, Any], status: str | None) -> bool:
    """Whether a requirement's STATUS expects implementation (design §3).

    Explicit ``[statuses.<Name>].expects_implementation`` wins; otherwise the
    status's ROLE decides (active-role -> True, else False). Single source of
    truth; consumers (viewer, aggregation, health, gaps, summary, mcp) MUST call
    this rather than reading status roles for coverage-expectation. Replaces the
    coverage roles of ``StatusRolesConfig.is_excluded_from_coverage``.

    Case-insensitive on the status name (mirrors ``level_expects_validation``).
    Unknown statuses derive True: ``role_of`` defaults them to ACTIVE.
    """
    statuses = (config or {}).get("statuses")
    if isinstance(statuses, dict) and status:
        target = status.lower()
        for key, spec in statuses.items():
            if isinstance(key, str) and key.lower() == target:
                val = (
                    spec.get("expects_implementation")
                    if isinstance(spec, dict)
                    else getattr(spec, "expects_implementation", None)
                )
                if val is not None:
                    return bool(val)
    from elspais.config.status_roles import StatusRole

    return get_status_roles(config or {}).role_of(status) == StatusRole.ACTIVE


# Implements: REQ-d00291-G
def statuses_weighed_active(treat_active: Iterable[str] | None) -> frozenset[str]:
    """The statuses that a run weighs as active (``--treat-active``).

    This function normalizes the names one time. All users of the names then
    spell them in the same way. The function puts each name into title case. A
    ``[statuses.<Name>]`` table uses title case also. The result is empty if
    the run weighs no status as active.
    """
    return frozenset(s.title() for s in (treat_active or ()))


# Implements: REQ-d00291-G
def config_with_active_overlay(
    config: dict[str, Any] | None,
    treat_active: Iterable[str] | None,
) -> dict[str, Any] | None:
    """``config`` with the statuses of a run added to its ``[statuses]`` table.

    ``--treat-active`` is an overlay on the configuration. The overlay is valid
    for one run. It is not a parameter that each user of the configuration
    receives. Therefore one function, :func:`status_expects_implementation`,
    answers for the status in all places. The coverage counts, the tally of
    held-out requirements and the reference checks cannot disagree
    (REQ-d00258-C). A project can also declare ``expects_implementation``. Such
    a declaration uses the same function. Thus a declaration and a run-time
    promotion are one mechanism, not two.

    A command applies the overlay at its edge. The build does not apply it. The
    statuses that a reader weighs as active are a property of the request of
    that reader. One graph can serve more than one reader. Therefore the graph
    must not hold the answer of one reader.

    The function returns ``config`` without a change if the run weighs no
    status as active. The behavior is then the default behavior. The function
    does not change the configuration that it receives.
    """
    flags = statuses_weighed_active(treat_active)
    if not flags:
        return config
    overlaid = dict(config or {})
    statuses = dict(overlaid.get("statuses") or {})
    # Put the value into the entry that is present. Ignore a difference of
    # case. Do not add a second key that has a different case. The function
    # that reads the table can find such a key first.
    existing_by_lower = {k.lower(): k for k in statuses if isinstance(k, str)}
    for flag in flags:
        key = existing_by_lower.get(flag.lower(), flag)
        entry = dict(statuses.get(key) or {})
        entry["expects_implementation"] = True
        statuses[key] = entry
    overlaid["statuses"] = statuses
    return overlaid


# Implements: REQ-d00291-F+G
def statuses_withheld_from_coverage(
    config: dict[str, Any] | None,
    treat_active: Iterable[str] | None = None,
) -> set[str]:
    """The statuses whose requirements no coverage figure and no work list counts.

    This function gives the result of
    :func:`status_expects_implementation` as a set. Some users of the result
    need a set of status names. They do not ask the question for each
    requirement. This function asks that function about each status in the
    vocabulary. Therefore this function holds out a status exactly when the
    counts hold it out. REQ-d00291-F speaks about the population of every
    coverage figure. A work list names the requirements that still need
    implementation. That list uses the same population.

    Do not use ``StatusRolesConfig.coverage_excluded_statuses()`` here. That
    function uses only the roles, and it cannot see a declaration. A read of
    the roles caused one surface to count a requirement and a different
    surface to hold the same requirement out.

    A status that is not in the vocabulary expects implementation. ``role_of``
    makes such a status active. Therefore this function never holds it out,
    and the vocabulary is sufficient.
    """
    overlaid = config_with_active_overlay(config, treat_active)
    roles = get_status_roles(config or {})
    vocabulary = set(roles.known_statuses())
    declared = (config or {}).get("statuses")
    if isinstance(declared, dict):
        vocabulary |= {k for k in declared if isinstance(k, str)}
    return {s for s in vocabulary if not status_expects_implementation(overlaid, s)}


# Implements: REQ-d00291-G
def reference_excluded_statuses(
    config: dict[str, Any] | None,
    treat_active: Iterable[str] | None = None,
) -> set[str]:
    """The statuses that cause a report if code or a test cites them.

    This question is not the question that
    :func:`status_expects_implementation` answers. That function asks if a
    status still needs implementation. This function asks if a citation of the
    status is worth a report. A project can declare
    ``expects_implementation = true`` for a status that has a retired role.
    The project then tells you that those requirements still need work. The
    project does not tell you to stop the report about a citation. Therefore
    the declaration does not change this function. A ``--treat-active``
    promotion does change this function. A request to weigh a status as active
    applies to all of the reading of that status in the run.
    """
    roles = get_status_roles(config or {})
    # Compare without case. A role table holds the spelling the project wrote,
    # and ``statuses_weighed_active`` gives the title case of what the caller
    # wrote. A subtraction of one set from the other kept a status that the
    # caller did name. REQ-d00291-G weighs EVERY status that a caller names,
    # and identifier matching admits a difference of case (REQ-d00212-S).
    weighed = {s.lower() for s in statuses_weighed_active(treat_active)}
    return {s for s in roles.coverage_excluded_statuses() if s.lower() not in weighed}


def _declaration(config: dict[str, Any], name: str) -> Any:
    """The declaration a project makes under ``name``.

    One name carries both halves of what an audience reads -- the requirements a
    report is about and the facts it states (REQ-d00280-C) -- so both accessors
    find the declaration the same way rather than each deciding for itself which
    spelling matches which declaration.

    Raises:
        KeyError: If the project declares nothing under that name.
    """
    declared = (config or {}).get("scopes") or {}
    if not isinstance(declared, dict):
        declared = {}
    match = None
    for key, value in declared.items():
        if isinstance(key, str) and key.lower() == name.lower():
            match = value
            break
    if match is None:
        known = ", ".join(sorted(str(k) for k in declared)) or "none"
        raise KeyError(
            f"No scope named {name!r} is declared in this project; declared scopes: {known}"
        )
    return match


def _declared_field(declaration: Any, field: str) -> Any:
    """One field of a declaration, whether it arrived as a mapping or a model."""
    if isinstance(declaration, dict):
        return declaration.get(field)
    return getattr(declaration, field, None)


# Implements: REQ-d00280-B
def declared_scope(config: dict[str, Any], name: str) -> Any:
    """The scope a project declares under ``name``.

    A name is a reference to a scope, never a second selection that happens to
    share a spelling: what a report produced under a name contains is what the
    declaration says and nothing else, so an author reading the declaration knows
    the answer without running the report.

    Consumers MUST reach a declared scope through here rather than reading the
    configuration, so one name has one meaning.

    Raises:
        KeyError: If the project declares no scope under that name. An
            undeclared name has no selection behind it, so there is nothing to
            report under.
    """
    from elspais.graph.scope import ReportScope

    match = _declaration(config, name)

    def _listed(field: str) -> tuple[str, ...]:
        return tuple(str(v) for v in (_declared_field(match, field) or []))

    include = {p: v for p in ("level", "status") if (v := _listed(p))}
    exclude = {p: v for p in ("level", "status") if (v := _listed(f"not_{p}"))}
    roles = _declared_field(match, "match_status_roles")
    return ReportScope(include=include, exclude=exclude, match_status_roles=bool(roles))


# Implements: REQ-d00280-C
def declared_values(config: dict[str, Any], name: str) -> Any:
    """The value selection a project declares under ``name``, or None.

    The companion to :func:`declared_scope`: one name answers for a whole
    audience, the requirements it reads and the facts it reads about them
    (REQ-d00280-C). The two remain independent choices -- a declaration naming
    no values constrains none, which is what None says here, and a report
    answering None states the values it would have anyway.

    The names read here are value keys, never the words a project displays a
    value under (REQ-d00282-J). They are not judged against any report: which
    values are on offer is known only where the report is produced, and that is
    where a name among them that does not resolve is refused (REQ-d00282-F).

    Raises:
        KeyError: If the project declares nothing under that name -- the same
            condition, and the same message, as an undeclared scope.
    """
    from elspais.graph.values import parse_value_selection

    match = _declaration(config, name)
    raw = _declared_field(match, "values")
    if raw is None:
        return None
    if isinstance(raw, str):
        return parse_value_selection(raw)
    return parse_value_selection([str(v) for v in raw])


CURRENT_CONFIG_VERSION = 5

# The severity settings, by the path each one lives at. Enumerated rather than
# walked: a blind walk over the configuration would inspect any string that
# happened to read "ok" -- a status word, a level name -- and the refusal would
# name settings it knows nothing about.


def _severity_paths() -> list[tuple[str, ...]]:
    paths: list[tuple[str, ...]] = [
        ("rules", "format", "no_assertions_severity"),
        ("rules", "format", "no_traceability_severity"),
        ("rules", "coverage", "uncredited_evidence"),
        ("rules", "coverage", "external_test_failure"),
    ]
    for dimension in ("implemented", "tested", "verified", "uat_coverage", "uat_verified"):
        for tier in ("full", "partial", "failing", "missing"):
            paths.append(("rules", "coverage", dimension, tier))
    for field in (
        "retired",
        "provisional",
        "aspirational",
        "malformed",
        "unknown_namespace",
        "unknown_requirement",
        "unknown_assertion",
        "forbidden",
        "keyword_form",
        "identifier_form",
        "undeclared",
    ):
        paths.append(("rules", "references", field))
    for field in (
        "duplicate",
        "undefined",
        "unmarked",
        "unused",
        "bad_definition",
        "collection_empty",
        "canonical_form",
    ):
        paths.append(("terms", "severity", field))
    return paths


# The term severities were once written flat under `[terms]`, one field per
# condition with a `_severity` suffix; they are written under `[terms.severity]`
# now, keyed by the condition alone.
_FLAT_TERM_SEVERITIES = {
    "duplicate_severity": "duplicate",
    "undefined_severity": "undefined",
    "unmarked_severity": "unmarked",
}

# `ok` and `off` once meant one thing between them and neither was honoured
# everywhere: `ok` passed a check while still listing its findings, `off`
# withheld them. One word says it now.
_RETIRED_SEVERITY = "ok"
_REPLACEMENT_SEVERITY = "off"

# Settings that were declared and documented and read by nothing, so a project
# could set one and change no outcome.
_WITHDRAWN_SETTINGS: tuple[tuple[str, ...], ...] = (("terms", "severity", "changed"),)


def _container_at(config: dict[str, Any], path: tuple[str, ...]) -> dict | None:
    """The table a setting lives in, or None where the file has no such table."""
    container: Any = config
    for key in path[:-1]:
        container = container.get(key) if isinstance(container, dict) else None
        if container is None:
            return None
    return container if isinstance(container, dict) else None


# Implements: REQ-d00212-V, REQ-d00212-X
def _setting_repairs(config: dict[str, Any]) -> list[tuple[str, str]]:
    """Each setting the file carries that this version does not read, and what
    to write in its place.

    Read out of the file in front of the author rather than recited from a
    fixed list, so a refusal names what this configuration actually has to
    change and cannot go stale against it.
    """
    repairs: list[tuple[str, str]] = []

    terms = config.get("terms")
    if isinstance(terms, dict):
        for flat, nested in _FLAT_TERM_SEVERITIES.items():
            if flat in terms:
                value = terms[flat]
                repairs.append(
                    (
                        f'[terms] {flat} = "{value}"',
                        f'[terms.severity] {nested} = "{value}"',
                    )
                )

    for path in _severity_paths():
        container = _container_at(config, path)
        if container is not None and container.get(path[-1]) == _RETIRED_SEVERITY:
            section = ".".join(path[:-1])
            repairs.append(
                (
                    f'[{section}] {path[-1]} = "{_RETIRED_SEVERITY}"',
                    f'[{section}] {path[-1]} = "{_REPLACEMENT_SEVERITY}"'
                    f'   ("{_RETIRED_SEVERITY}" is no longer a severity word; the '
                    f"admitted words are off, info, warning, error)",
                )
            )

    for path in _WITHDRAWN_SETTINGS:
        container = _container_at(config, path)
        if container is not None and path[-1] in container:
            section = ".".join(path[:-1])
            repairs.append(
                (
                    f"[{section}] {path[-1]}",
                    "delete the line -- nothing reads this setting",
                )
            )

    return repairs


def _declared_version_of(config: dict[str, Any], source: Path) -> int | None:
    """The version a TOML file declares, or None where it declares none.

    A file declaring nothing is making no claim about its shape, and the
    settings it carries are inspected regardless -- that is what actually
    catches a file written for an older elspais, whether or not it says so.
    """
    raw = config.get("version")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"{source}: version = {raw!r} is not a version number. Write "
            f"`version = {CURRENT_CONFIG_VERSION}`."
        ) from None


# Implements: REQ-d00212-X
def _outdated_config_message(
    config_path: Path,
    declared_version: int | None,
    repairs: list[tuple[str, str]],
) -> str:
    """Build the refusal for a configuration this version does not read."""
    lines: list[str] = []
    if declared_version is not None and declared_version != CURRENT_CONFIG_VERSION:
        lines.append(
            f"{config_path}: version = {declared_version}, but this elspais reads "
            f"version {CURRENT_CONFIG_VERSION} configurations."
        )
    else:
        lines.append(
            f"{config_path}: this file carries settings that version "
            f"{CURRENT_CONFIG_VERSION} does not read."
        )
    lines.append("")

    if declared_version is not None and declared_version > CURRENT_CONFIG_VERSION:
        lines.append(
            "The file was written for a newer elspais than the one running. Upgrade "
            f"elspais, or -- if this is in fact a version {CURRENT_CONFIG_VERSION} "
            f"file -- write `version = {CURRENT_CONFIG_VERSION}`."
        )
        return "\n".join(lines)

    lines.append(
        "An out-of-date configuration is not upgraded in place: what a project "
        "configured is what it gets, so the file says it rather than the tool "
        "guessing it. Edit the file as below."
    )
    lines.append("")

    if repairs:
        lines.append("Settings to change:")
        for found, instead in repairs:
            lines.append(f"  {found}")
            lines.append(f"    write instead:  {instead}")
    else:
        lines.append("No setting in this file has to change.")

    if declared_version != CURRENT_CONFIG_VERSION:
        lines.append("")
        lines.append("Then set:")
        lines.append(f"  version = {CURRENT_CONFIG_VERSION}")

    lines.append("")
    lines.append("`elspais docs config` lists every setting this version reads.")
    return "\n".join(lines)


# Implements: REQ-d00207-B
# Implements: REQ-d00212-V, REQ-d00212-X
def load_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from a TOML file.

    Loads config_path, then deep-merges .elspais.local.toml (if present
    alongside it) on top — following the docker-compose.override.yml / .env.local
    convention for developer-local overrides.

    All defaults are provided by `ElspaisConfig` Pydantic field defaults.
    Returns a plain dict produced by ``model_dump(by_alias=True)``.

    Args:
        config_path: Path to the .elspais.toml file.

    Returns:
        Configuration dictionary with hyphenated keys.
    """
    content = config_path.read_text(encoding="utf-8")
    user_config = _parse_toml(content)
    # Capture the user-supplied project name + namespace BEFORE merging in
    # defaults — the boundary checks below must reject a real TOML that
    # omits either field even when `config_defaults()` would supply a
    # placeholder (see ProjectConfig.name / ProjectConfig.namespace).
    _user_project = user_config.get("project") or {}
    _user_project_name = _user_project.get("name")
    _user_project_namespace = _user_project.get("namespace")
    _user_declared_version = _declared_version_of(user_config, config_path)
    merged = _merge_configs(config_defaults(), user_config)
    # `[levels]` is a hierarchy declaration. When the user supplies their own
    # levels, take only the user's keys (so a custom uppercase `[levels.PRD]`
    # doesn't coexist with the lowercase default `[levels.prd]`). For
    # user-keys that happen to match a default key, the per-field defaults
    # still fill in missing values (e.g. `implements`) — this is the same
    # pattern as the rest of the schema.
    _override_levels(merged, user_config)

    # Deep-merge developer-local overrides if present
    local_path = config_path.parent / ".elspais.local.toml"
    _local_project_name: Any = None
    _local_project_namespace: Any = None
    _local_declared_version: int | None = None
    if local_path.is_file():
        local_config = _parse_toml(local_path.read_text(encoding="utf-8"))
        # Same rule as the main TOML: capture pre-merge so we can tell whether
        # the user supplied name/namespace vs. the schema defaults leaking
        # through.
        _local_project = local_config.get("project") or {}
        _local_project_name = _local_project.get("name")
        _local_project_namespace = _local_project.get("namespace")
        _local_declared_version = _declared_version_of(local_config, local_path)
        merged = _merge_configs(merged, local_config)
        _override_levels(merged, local_config)

    # Implements: REQ-d00212-V
    # A configuration this version does not read is refused, naming each
    # setting that has to change and what to write in its place. The version
    # is read from the file rather than from `merged`, whose defaults supply
    # the current one and would mask what the author actually declared.
    _declared_version = _local_declared_version
    if _declared_version is None:
        _declared_version = _user_declared_version
    _repairs = _setting_repairs(merged)
    if (_declared_version is not None and _declared_version != CURRENT_CONFIG_VERSION) or _repairs:
        raise ValueError(_outdated_config_message(config_path, _declared_version, _repairs))

    # A pre-v2 configuration declared its identifiers in a `[patterns]`
    # section. Nothing reads that section now, so accepting one would mean
    # loading a configuration whose identifier settings are silently
    # ignored -- the reader would get whatever the defaults are, and the
    # spelling they configured would simply not happen.
    if "patterns" in merged:
        raise ValueError(
            f"{config_path}: [patterns] is the pre-v2 way of declaring identifiers "
            f"and is no longer read. Declare levels in [levels] and the identifier "
            f"form in [id-patterns]; see `elspais docs config`."
        )

    # Identifier settings are written under `[id-patterns]`. The underscore
    # spelling was once accepted alongside it, which let one file say the same
    # thing two ways and left a reader to work out which the tool had read.
    if "id_patterns" in merged:
        raise ValueError(
            f"{config_path}: [id_patterns] is not read. Identifier settings are "
            f"declared under [id-patterns], written with a hyphen."
        )

    # The set of statuses a requirement may declare is the union of the
    # lists in [rules.format.status_roles], so naming it again here could
    # only agree or disagree with them. It was dropped silently, which left
    # a project believing it had said something.
    fmt = merged.get("rules", {}).get("format", {})
    if "allowed_statuses" in fmt:
        raise ValueError(
            f"{config_path}: rules.format.allowed_statuses is no longer read. The "
            f"statuses a requirement may declare are the ones named in "
            f"[rules.format.status_roles], which also says what each one means."
        )

    # Validate via Pydantic schema
    from elspais.config.schema import ElspaisConfig

    validated = ElspaisConfig.model_validate(merged)

    # Boundary enforcement: a real .elspais.toml MUST declare [project].name
    # and [project].namespace. Bare ProjectConfig() construction in helpers
    # and tests still uses Pydantic defaults, but configs loaded from disk go
    # through this check, which is the only entry point that should accept
    # user-authored TOML. The checks inspect the pre-merge user/local TOML
    # values so the schema's placeholder defaults cannot mask a missing field.
    supplied_name = _local_project_name if _local_project_name is not None else _user_project_name
    if not supplied_name or not str(supplied_name).strip():
        raise ValueError(f"{config_path}: [project].name is required and must be non-empty")
    supplied_namespace = (
        _local_project_namespace
        if _local_project_namespace is not None
        else _user_project_namespace
    )
    if not supplied_namespace or not str(supplied_namespace).strip():
        raise ValueError(f"{config_path}: [project].namespace is required and must be non-empty")

    # Keyed as the TOML is written, hyphens and all
    result = validated.model_dump(by_alias=True)

    return result


def find_git_root(start_path: Path | None = None) -> Path | None:
    """Find the root directory of a git repository.

    Searches upward from start_path for a .git directory or file (worktree).

    Args:
        start_path: Directory to start searching from (defaults to cwd).

    Returns:
        Path to git repository root, or None if not in a git repo.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    if current.is_file():
        current = current.parent

    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.exists():
            # Could be a directory (normal repo) or file (worktree)
            return current

        current = current.parent

    return None


# Implements: REQ-p00005-F
def find_canonical_root(start_path: Path | None = None) -> Path | None:
    """Find the canonical (non-worktree) git repository root.

    For normal repos: returns same as find_git_root().
    For worktrees: returns the MAIN repo root via git-common-dir.
    Use this for resolving cross-repo sibling paths.

    Args:
        start_path: Directory to start searching from (defaults to cwd).

    Returns:
        Path to canonical git repository root, or None if not in a git repo.
    """
    import subprocess

    git_root = find_git_root(start_path)
    if git_root is None:
        return None

    git_marker = git_root / ".git"
    if git_marker.is_file():
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                capture_output=True,
                text=True,
                cwd=git_root,
            )
            if result.returncode == 0:
                common_dir = Path(result.stdout.strip())
                if not common_dir.is_absolute():
                    common_dir = (git_root / common_dir).resolve()
                return common_dir.parent
        except (OSError, subprocess.SubprocessError):
            pass

    return git_root


def find_config_file(start_path: Path) -> Path | None:
    """Find .elspais.toml configuration file.

    Searches from start_path up to git root or filesystem root.

    Args:
        start_path: Directory to start searching from.

    Returns:
        Path to config file if found, None otherwise.
    """
    current = start_path.resolve()

    if current.is_file():
        current = current.parent

    while current != current.parent:
        config_path = current / ".elspais.toml"
        if config_path.exists():
            return config_path

        # Stop at git root
        if (current / ".git").exists():
            break

        current = current.parent

    return None


def _override_levels(merged: dict[str, Any], user_config: dict[str, Any]) -> None:
    """If user_config supplies a non-empty [levels] table, replace merged's
    levels with only those keys. Per-field defaults from the matching default
    level (if any) are preserved for missing fields, so a user can write
    `[levels.prd] { rank, letter }` without re-stating `implements`.
    """
    user_levels = user_config.get("levels")
    if not isinstance(user_levels, dict) or not user_levels:
        return
    default_levels = merged.get("levels") or {}
    new_levels: dict[str, Any] = {}
    for key, user_entry in user_levels.items():
        if not isinstance(user_entry, dict):
            new_levels[key] = user_entry
            continue
        default_entry = default_levels.get(key)
        if isinstance(default_entry, dict):
            combined = dict(default_entry)
            combined.update(user_entry)
            new_levels[key] = combined
        else:
            new_levels[key] = dict(user_entry)
    merged["levels"] = new_levels


def _merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge configuration dictionaries.

    Args:
        base: Base configuration.
        override: Override configuration.

    Returns:
        Merged configuration.
    """
    result = dict(base)

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value

    return result


def _set_nested(data: dict[str, Any], key: str, value: Any) -> None:
    """Set a value at a nested key path."""
    parts = key.split(".")
    current = data

    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]

    current[parts[-1]] = value


# Implements: REQ-p00002-A
def _parse_toml(content: str) -> dict[str, Any]:
    """Parse TOML content into a plain dictionary.

    Uses tomlkit for full TOML 1.0 compliance. Returns a plain dict
    (unwrapped from TOMLDocument) to avoid downstream type surprises.

    Args:
        content: TOML file content.

    Returns:
        Parsed dictionary.
    """
    doc = tomlkit.parse(content)
    return doc.unwrap()


# Implements: REQ-p00002-A
def parse_toml_document(content: str) -> tomlkit.TOMLDocument:
    """Parse TOML content into a TOMLDocument for round-trip editing.

    Unlike parse_toml(), this preserves comments, whitespace, and
    formatting. Use this when modifying and writing back TOML content.

    Args:
        content: TOML file content.

    Returns:
        TOMLDocument that preserves formatting on dumps().
    """
    return tomlkit.parse(content)


_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


def _try_parse_numeric(value: str) -> int | float | None:
    """Try to parse a string as an integer or float.

    Args:
        value: String to parse.

    Returns:
        Parsed int or float, or None if not numeric.
    """
    if _INT_RE.match(value):
        return int(value)
    if _FLOAT_RE.match(value):
        return float(value)
    return None


def get_config(
    config_path: Path | None = None,
    start_path: Path | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Get configuration with auto-discovery and fallback.

    This is the standard helper for command modules to load configuration.
    It handles:
    - Explicit config file path (if provided)
    - Config file discovery from start_path
    - Fallback to defaults if no config found
    - Error reporting (unless quiet=True)

    Override precedence (highest first):
        env vars > ``.elspais.local.toml`` > ``.elspais.toml`` > defaults

    Args:
        config_path: Explicit config file path (optional)
        start_path: Directory to search for config (defaults to cwd)
        quiet: Suppress error messages

    Returns:
        Configuration dictionary (defaults if not found)
    """
    if start_path is None:
        start_path = Path.cwd()

    # Use explicit config path or discover
    resolved_path = config_path if config_path else find_config_file(start_path)

    if resolved_path and resolved_path.exists():
        try:
            config = load_config(resolved_path)
        except Exception as e:
            # A config file that exists but can't be parsed is always an error.
            # Silently falling back to defaults would hide the problem and cause
            # hard-to-diagnose issues (e.g. skip_dirs not working).
            # The advice names the file, not a cause: a config file is
            # refused for a malformed line, for a setting that no longer
            # exists, and for a value the schema will not admit, and telling
            # a reader to look for a syntax error sends them hunting for
            # something that is usually not there. The exception above says
            # which setting and why.
            raise ValueError(
                f"Failed to read config file {resolved_path}: {e}\n"
                f"Correct the reported setting in {resolved_path.name}, or see "
                f"`elspais docs config` for what it accepts."
            ) from e
    else:
        # Return defaults (no config file found)
        config = config_defaults()

    return config


def get_spec_directories(
    spec_dir_override: Path | None,
    config: dict[str, Any],
    base_path: Path | None = None,
) -> list[Path]:
    """Get the spec directories from override or config.

    Args:
        spec_dir_override: Explicit spec directory (e.g., from CLI --spec-dir)
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing spec directory paths
    """
    if spec_dir_override:
        return [spec_dir_override]

    if base_path is None:
        base_path = Path.cwd()

    # Get directories from v3 scanning.spec.directories
    dir_config = config.get("scanning", {}).get("spec", {}).get("directories", ["spec"])

    # Handle both string and list
    if isinstance(dir_config, str):
        dir_list = [dir_config]
    else:
        dir_list = list(dir_config)

    # Resolve paths and filter to existing
    result = []
    for d in dir_list:
        path = Path(d)
        if not path.is_absolute():
            path = base_path / path
        if path.exists() and path.is_dir():
            result.append(path)

    return result


def get_code_directories(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> list[Path]:
    """Get code directories from configuration.

    Args:
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing code directory paths
    """
    if base_path is None:
        base_path = Path.cwd()

    dir_config = config.get("scanning", {}).get("code", {}).get("directories", ["src"])

    # Handle both string and list
    if isinstance(dir_config, str):
        dir_list = [dir_config]
    else:
        dir_list = list(dir_config)

    # Resolve paths and filter to existing
    result = []
    for d in dir_list:
        path = Path(d)
        if not path.is_absolute():
            path = base_path / path
        if path.exists() and path.is_dir():
            result.append(path)

    return result


def get_docs_directories(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> list[Path]:
    """Get documentation directories from configuration.

    Uses [scanning.docs].directories config for scanning documentation files
    for requirement references and traceability.

    Args:
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing docs directory paths
    """
    if base_path is None:
        base_path = Path.cwd()

    dir_config = config.get("scanning", {}).get("docs", {}).get("directories", ["docs"])

    # Handle both string and list
    if isinstance(dir_config, str):
        dir_list = [dir_config]
    else:
        dir_list = list(dir_config)

    # Resolve paths and filter to existing
    result = []
    for d in dir_list:
        path = Path(d)
        if not path.is_absolute():
            path = base_path / path
        if path.exists() and path.is_dir():
            result.append(path)

    return result


# Re-export parse_toml for use by config_cmd
parse_toml = _parse_toml


@dataclass
class IgnoreConfig:
    """Unified configuration for ignoring files and directories.

    Supports glob patterns (fnmatch) for flexible matching.
    Patterns can be scoped to specific contexts (spec, code, test).

    Attributes:
        global_patterns: Patterns applied everywhere
        spec_patterns: Additional patterns for spec file scanning
        code_patterns: Additional patterns for code scanning
        test_patterns: Additional patterns for test scanning
    """

    global_patterns: list[str]
    spec_patterns: list[str]
    code_patterns: list[str]
    test_patterns: list[str]

    def should_ignore(self, path: str | Path, scope: str = "global") -> bool:
        """Check if a path should be ignored based on patterns.

        Matches against:
        1. Global patterns (always checked)
        2. Scope-specific patterns (if scope is provided)

        Supports glob patterns via fnmatch:
        - "*" matches any characters within a path component
        - "**" matches across directory separators (when using pathlib)
        - "?" matches a single character

        Args:
            path: Path to check (can be file or directory)
            scope: Context scope ("global", "spec", "code", "test")

        Returns:
            True if path should be ignored
        """
        if isinstance(path, Path):
            path_str = str(path)
            path_name = path.name
            path_parts = path.parts
        else:
            path_str = path
            path_obj = Path(path)
            path_name = path_obj.name
            path_parts = path_obj.parts

        # Collect all applicable patterns
        patterns = list(self.global_patterns)
        if scope == "spec":
            patterns.extend(self.spec_patterns)
        elif scope == "code":
            patterns.extend(self.code_patterns)
        elif scope == "test":
            patterns.extend(self.test_patterns)

        for pattern in patterns:
            # Check if pattern matches the file/dir name directly
            if fnmatch.fnmatch(path_name, pattern):
                return True

            # Check if pattern matches any path component
            for part in path_parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

            # Check if pattern matches the full relative path
            if fnmatch.fnmatch(path_str, pattern):
                return True

        return False

    def get_patterns_for_scope(self, scope: str) -> list[str]:
        """Get all patterns applicable to a scope (global + scope-specific).

        Args:
            scope: Context scope ("global", "spec", "code", "test")

        Returns:
            Combined list of patterns
        """
        patterns = list(self.global_patterns)
        if scope == "spec":
            patterns.extend(self.spec_patterns)
        elif scope == "code":
            patterns.extend(self.code_patterns)
        elif scope == "test":
            patterns.extend(self.test_patterns)
        return patterns


def get_test_directories(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> list[Path]:
    """Get test directories from configuration.

    Uses [scanning.test].directories config, falling back to common defaults.

    Args:
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing test directory paths
    """
    if base_path is None:
        base_path = Path.cwd()

    # Get from scanning.test.directories
    dir_config = config.get("scanning", {}).get("test", {}).get("directories", ["tests"])

    # Handle both string and list
    if isinstance(dir_config, str):
        dir_list = [dir_config]
    else:
        dir_list = list(dir_config)

    # Resolve paths and filter to existing
    result = []
    for d in dir_list:
        path = Path(d)
        if not path.is_absolute():
            path = base_path / path
        if path.exists() and path.is_dir():
            result.append(path)

    return result


def get_ignore_config(config: dict[str, Any]) -> IgnoreConfig:
    """Get IgnoreConfig from configuration dictionary.

    The IgnoreConfig provides a unified way to check if paths should be ignored
    during file scanning. It supports glob patterns and scope-specific rules.

    Args:
        config: Configuration dictionary from get_config() or load_config()

    Returns:
        IgnoreConfig instance with patterns from [scanning] section or defaults.
    """
    scanning = config.get("scanning", {})

    # Global skip patterns
    global_patterns = list(scanning.get("skip", []))

    # Per-kind skip patterns (skip_files + skip_dirs merged)
    def _kind_patterns(kind: str) -> list[str]:
        kind_cfg = scanning.get(kind, {})
        patterns = list(kind_cfg.get("skip_files", []))
        patterns.extend(kind_cfg.get("skip_dirs", []))
        return patterns

    return IgnoreConfig(
        global_patterns=global_patterns,
        spec_patterns=_kind_patterns("spec"),
        code_patterns=_kind_patterns("code"),
        test_patterns=_kind_patterns("test"),
    )


__all__ = [
    "IgnoreConfig",
    "config_defaults",
    "default_level_keys",
    "level_expects_validation",
    "status_expects_implementation",
    "load_config",
    "find_config_file",
    "find_git_root",
    "validate_config",
    "get_config",
    "get_spec_directories",
    "get_code_directories",
    "get_docs_directories",
    "get_test_directories",
    "get_ignore_config",
    "parse_toml",
    "parse_toml_document",
    "get_status_roles",
    "_try_parse_numeric",
    "_try_parse_env_value",
    "get_associates_config",
]


# Implements: REQ-d00202-A+B+C
def validate_config(config: dict[str, Any]) -> Any:
    """Validate a configuration dictionary into the typed schema.

    The one place a loaded configuration is turned into `ElspaisConfig`.
    Eleven copies of this existed, each filtering the dictionary to the
    schema's own field names first, because `load_config` used to hand back
    keys it had itself withheld from validation. It no longer does, so the
    filter is gone with them: a key the schema does not know is a key the
    configuration should not have carried, and it is reported here rather
    than dropped by every consumer separately.
    """
    from elspais.config.schema import ElspaisConfig

    return ElspaisConfig.model_validate(config)


# Implements: REQ-d00202-A, REQ-d00202-B, REQ-d00202-C
def get_associates_config(
    config: dict[str, Any],
    repo_root: Path | None = None,
) -> dict[str, dict]:
    """Read [associates] sections from config.

    Each associate is declared as ``[associates.<name>]`` and states:
    - path (str, required): relative path to the associate repo
    - namespace (str, required): the namespace expected at that path
    - git (str, optional): remote URL, for clone assistance only

    Args:
        config: The project configuration dictionary.
        repo_root: Unused; retained so callers may pass the repository
            root without knowing whether resolution needs it.

    Returns:
        Dict mapping associate name to {"path": str, "namespace": str}.
        Empty dict if no [associates] section exists.

    Raises:
        ValueError: A declaration omits its path or its namespace. Both
            are how a declaration says which repository it means, so a
            declaration missing either names nothing in particular.
    """
    associates = config.get("associates", {})
    if not associates:
        return {}
    result: dict[str, dict] = {}
    for name, entry in associates.items():
        if not isinstance(entry, dict):
            raise ValueError(
                f"Associate '{name}' is not a declaration table. Declare it as "
                f"[associates.{name}] with a path and a namespace."
            )
        if not entry.get("path"):
            raise ValueError(f"Associate '{name}' declares no path.")
        if not entry.get("namespace"):
            raise ValueError(
                f"Associate '{name}' declares no namespace. A declaration names "
                f"the namespace it expects to find at that path, which is what "
                f"identifies the repository it means."
            )
        result[name] = {
            "path": entry["path"],
            "namespace": entry["namespace"],
            "git": entry.get("git"),
        }

    return result


def get_status_roles(config: dict[str, Any]):
    """Get StatusRolesConfig from configuration dictionary."""
    from elspais.config.status_roles import StatusRolesConfig

    roles_data = config.get("rules", {}).get("format", {}).get("status_roles", {})
    if roles_data:
        return StatusRolesConfig.from_dict(roles_data)
    return StatusRolesConfig.default()


# Implements: REQ-d00283-A+B+C
def target_groups(target: Any) -> frozenset[str]:
    """The groups *target* belongs to.

    Every target belongs to ``all`` (REQ-d00283-B), and a target claiming no
    group beyond that belongs to ``default`` (REQ-d00283-C) -- so a project
    that declares no groups has every target in ``default`` and a run that
    selects nothing executes exactly what it executed before groups existed.

    Consumers MUST reach a target's membership through here rather than reading
    ``target.groups``, which records what the target *claimed* and not what it
    belongs to.
    """
    from elspais.config.schema import GROUP_ALL, GROUP_DEFAULT

    claimed = {g.strip().lower() for g in (getattr(target, "groups", None) or []) if g.strip()}
    claimed.discard(GROUP_ALL)
    if not claimed:
        claimed = {GROUP_DEFAULT}
    return frozenset(claimed | {GROUP_ALL})


# Implements: REQ-d00283-D+E+H+I
def targets_in_groups(config: Any, selected: list[str] | None) -> set[str]:
    """The names of the test targets *selected* names.

    ``None`` selects the ``default`` group (REQ-d00283-D); a selection names
    the targets belonging to any group in it (REQ-d00283-E).

    Raises:
        ValueError: If a selected name is neither declared nor reserved.
            Refused rather than resolved to no targets, because a selection
            that quietly selects nothing produces a report a reader cannot
            tell from one whose targets all passed (REQ-d00283-H).
    """
    from elspais.config.schema import GROUP_DEFAULT, RESERVED_GROUPS

    test_cfg = config.scanning.test
    wanted = (
        {GROUP_DEFAULT} if selected is None else {g.strip().lower() for g in selected if g.strip()}
    )
    known = {name.strip().lower() for name in test_cfg.groups} | RESERVED_GROUPS
    unknown = sorted(wanted - known)
    if unknown:
        raise ValueError(
            f"unknown test group(s): {', '.join(unknown)}. "
            f"Known groups: {', '.join(sorted(known))}."
        )
    return {t.name for t in test_cfg.targets if target_groups(t) & wanted}


# Implements: REQ-d00283-D+E+H+I, REQ-d00254-I+J
def selected_targets(config: Any, named: list[str] | None) -> set[str] | None:
    """The test targets a run naming *named* covers.

    ONE selector. A group is an alias for a set of targets rather than a second
    dimension they are classified on, so a run names targets, some of them by a
    name that stands for several, and covers everything it named
    (REQ-d00283-I). Naming nothing selects the ``default`` group
    (REQ-d00283-D), and the two namespaces cannot collide because a
    configuration holding a target and a group of one name is refused
    (REQ-d00283-G).

    ``None`` is returned where the selection covers every configured target,
    which is what makes a run full rather than selective (REQ-d00254-J). That
    is why the answer is a set of names and not the flags that produced it: a
    project declaring no groups has every target in ``default``, so its bare
    run covers everything and renders exactly as it did before groups existed.

    A name that is neither a configured target nor a known group is CARRIED
    rather than dropped: the caller that runs targets reports it as unknown
    (REQ-d00283-H), and resolving it away here would turn that report into
    silence.
    """
    configured = {t.name for t in config.scanning.test.targets}
    if named is None:
        return None if (sel := targets_in_groups(config, None)) == configured else sel

    wanted = [n for n in (x.strip() for x in named) if n]
    known_groups = known_group_names(config)
    as_groups = [n for n in wanted if n.lower() in known_groups]
    selection = {n for n in wanted if n.lower() not in known_groups}
    if as_groups:
        selection |= targets_in_groups(config, as_groups)
    return None if selection == configured else selection


def known_group_names(config: Any) -> set[str]:
    """Every group name this project admits, declared or reserved."""
    from elspais.config.schema import RESERVED_GROUPS

    return {str(name).strip().lower() for name in config.scanning.test.groups} | RESERVED_GROUPS


# Implements: REQ-d00283-H
def unknown_target_names(config: Any, named: list[str] | None) -> list[str]:
    """The names in *named* that are neither a configured target nor a group.

    The ONE place that question is answered, so every surface taking a
    selection refuses the same names. ``selected_targets`` deliberately carries
    an unknown name through rather than resolving it away -- a selection that
    quietly selects nothing renders exactly like one whose targets all passed
    (REQ-d00283-H) -- which leaves this as the check each caller makes before
    it renders anything.
    """
    if not named:
        return []
    configured = {t.name for t in config.scanning.test.targets}
    groups = known_group_names(config)
    return sorted({n for n in named if n not in configured and n.strip().lower() not in groups})
