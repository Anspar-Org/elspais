# Implements: REQ-d00285-D+E, REQ-d00212-P+U
"""The one severity vocabulary, and the one authority that resolves a check's
severity from its name.

A finding's severity is a project decision, and it is decided HERE -- not at
the point the finding is built. Every check the tool runs is registered below
with the category it reports under, the severity it carries when the project
says nothing, and the ONE configuration path that overrides it. A check reads
one path and only one: where two paths could answer, a project that sets the
one it read about sees nothing move.

The vocabulary is four words:

``off``
    The condition is not reported here. The check reports as skipped and
    produces no findings.
``info``
    Worth saying; never a failure.
``warning``
    Needs attention.
``error``
    A defect.

A check name that carries no legacy setting of its own is configured under
``[rules.severity]``, keyed by the check name -- which is what keeps every
finding inside the settings a project can reach.

The registry is also where a check's REMEDY lives: the action a reader takes
to resolve what it reports. It belongs here rather than in a table the text
renderer consults, because a render-time table reaches only the format that
consults it, and a finding that names its remedy in one format and not another
is two different findings to two readers (REQ-d00285-B+C). A check for which no
action is known carries `NO_KNOWN_REMEDY`, which says so rather than saying
nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

# The admitted values, in increasing order of loudness. `off` is first because
# it reports nothing at all.
SEVERITY_VALUES: tuple[str, ...] = ("off", "info", "warning", "error")

# The type the configuration schema admits. Declared here so the schema and the
# resolver cannot drift: there is one vocabulary, written once.
SeverityValue = Literal["off", "info", "warning", "error"]

# What a check that is actually reported may carry. `off` never reaches a
# report -- a check resolving to it is emitted as a skipped `info` check -- so
# a severity outside this set falling through to the counting is impossible.
REPORTED_SEVERITIES: tuple[str, ...] = ("info", "warning", "error")


class Severity(str, Enum):
    """The severity vocabulary. Values are the strings a configuration writes."""

    OFF = "off"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# What a finding says where no action is known to resolve it. Naming the
# absence is the obligation (REQ-d00285-B): a finding that says nothing about
# its remedy is indistinguishable from one whose remedy was forgotten.
NO_KNOWN_REMEDY = "no command resolves this; resolve it by hand"


@dataclass(frozen=True)
class CheckRule:
    """What is registered about one check.

    Attributes:
        name: The check name, as it appears in every report.
        category: The report section the check belongs to.
        default: The severity the check carries where the project says nothing.
        path: The ONE configuration path that overrides it, as a tuple of keys.
            A tuple rather than a dotted string because check names contain
            dots -- ``("rules", "severity", "spec.parseable")`` is one key
            under two, and splitting a dotted string would shear it.
        remedy: The action that resolves what the check reports, carried by
            every finding the check produces in every format it renders in.
    """

    name: str
    category: str
    default: str
    path: tuple[str, ...]
    remedy: str = NO_KNOWN_REMEDY


def _named(name: str, category: str, default: str, *path: str) -> CheckRule:
    """A check configured under a setting of its own."""
    return CheckRule(name=name, category=category, default=default, path=path)


def _general(name: str, category: str, default: str) -> CheckRule:
    """A check configured under the general `[rules.severity]` table."""
    return CheckRule(
        name=name, category=category, default=default, path=("rules", "severity", name)
    )


# The action that resolves what each check reports. A name absent here carries
# `NO_KNOWN_REMEDY`; a name here that no rule declares is refused when the
# registry is built, so the two cannot drift apart in silence.
_REMEDIES: dict[str, str] = {
    # -- config ----------------------------------------------------------
    "config.load": "elspais doctor",
    "config.exists": "elspais init",
    "config.syntax": "elspais doctor",
    "config.required_fields": "elspais doctor",
    "config.pattern_tokens": "elspais doctor",
    "config.hierarchy_rules": "elspais doctor",
    "config.paths_exist": "elspais doctor",
    "config.project_type": "elspais doctor",
    "config.associated_section": "elspais doctor",
    "config.associate_paths": "elspais associate list",
    "config.no_requirements": "elspais example",
    "associate.paths_resolvable": "elspais associate list",
    "associate.configs_valid": "elspais associate list",
    # -- spec ------------------------------------------------------------
    "spec.hash_integrity": "elspais fix",
    "spec.needs_rewrite": "elspais fix",
    "spec.format_rules": "elspais errors",
    "spec.no_assertions": "elspais errors",
    "spec.unfixable_issues": "elspais errors",
    "spec.parseable": "elspais errors",
    "spec.index_current": "elspais fix",
    "spec.no_duplicates": "elspais -v checks --spec",
    "spec.no_cycles": "elspais -v checks --spec",
    "spec.implements_resolve": "elspais broken",
    "spec.refines_resolve": "elspais broken",
    "spec.satisfies_resolve": "elspais broken",
    "spec.structural_orphans": "elspais -v checks --spec",
    "spec.hierarchy_levels": "elspais -v checks --spec",
    "spec.changelog_present": "elspais fix",
    "spec.changelog_current": "elspais fix -m 'Update changelog'",
    "spec.changelog_format": "elspais -v checks --spec",
    # -- references ------------------------------------------------------
    "references.malformed": "elspais broken",
    "references.unknown_namespace": "elspais broken",
    "references.unknown_requirement": "elspais broken",
    "references.unknown_assertion": "elspais broken",
    "references.forbidden": "elspais broken",
    "references.keyword_form": "elspais -v checks --spec",
    "references.identifier_form": "elspais -v checks --spec",
    "references.undeclared": "elspais -v checks --spec",
    # -- code ------------------------------------------------------------
    "code.unlinked": "elspais unlinked",
    "code.implemented": "elspais uncovered",
    "code.no_traceability": "elspais unlinked",
    # The `{code,tests}.{role}_references` checks are deliberately absent: a
    # citation naming a requirement whose status carries a role is resolved by
    # editing the citation or the requirement, and no command does either.
    # Naming one would send a reader to a surface that reports the condition
    # again rather than resolving it.
    # -- tests -----------------------------------------------------------
    "tests.unlinked": "elspais unlinked",
    "tests.results": "elspais failing",
    "tests.results_stale": "elspais checks --run-tests",
    "tests.unmatched_results": "elspais -v checks --tests",
    "tests.tested": "elspais untested",
    "tests.verified": "elspais failing",
    "tests.uncredited_evidence": "elspais -v checks --tests",
    "tests.external": "elspais failing",
    # -- uat -------------------------------------------------------------
    "uat.results": "elspais failing",
    "uat.uat_coverage": "elspais unvalidated",
    "uat.uat_verified": "elspais failing",
    # -- terms -----------------------------------------------------------
    "terms.duplicates": "elspais -v checks --terms",
    "terms.undefined": "elspais glossary",
    "terms.unmarked": "elspais -v checks --terms",
    "terms.unused": "elspais -v checks --terms",
    "terms.bad_definition": "elspais -v checks --terms",
    "terms.collection_empty": "elspais -v checks --terms",
    "terms.canonical_form": "elspais fix",
}


# The reference fault classes and the status roles are configured under
# `[rules.references]`, keyed by the class or role a reference reached.
_REFERENCES = ("rules", "references")
_TERMS = ("terms", "severity")


def _registry() -> dict[str, CheckRule]:
    rules: list[CheckRule] = [
        # -- config ------------------------------------------------------
        _general("config.load", "config", Severity.ERROR),
        _general("config.exists", "config", Severity.ERROR),
        _general("config.syntax", "config", Severity.ERROR),
        _general("config.required_fields", "config", Severity.ERROR),
        _general("config.pattern_tokens", "config", Severity.ERROR),
        _general("config.hierarchy_rules", "config", Severity.ERROR),
        _general("config.paths_exist", "config", Severity.ERROR),
        _general("config.project_type", "config", Severity.ERROR),
        _general("config.associated_section", "config", Severity.ERROR),
        _general("config.associate_paths", "spec", Severity.ERROR),
        _general("config.no_requirements", "spec", Severity.WARNING),
        _general("config.governed_rules", "spec", Severity.INFO),
        _general("local_toml.exists", "environment", Severity.ERROR),
        _general("cross_repo.in_committed", "environment", Severity.WARNING),
        _general("docs.config_drift", "docs", Severity.WARNING),
        _general("worktree.status", "environment", Severity.INFO),
        _general("associate.paths_resolvable", "environment", Severity.ERROR),
        _general("associate.configs_valid", "environment", Severity.ERROR),
        # -- spec --------------------------------------------------------
        _general("graph.build", "spec", Severity.ERROR),
        _general("spec.parseable", "spec", Severity.WARNING),
        _general("spec.no_duplicates", "spec", Severity.ERROR),
        _general("spec.implements_resolve", "spec", Severity.WARNING),
        _general("spec.refines_resolve", "spec", Severity.WARNING),
        _general("spec.satisfies_resolve", "spec", Severity.WARNING),
        _general("spec.needs_rewrite", "spec", Severity.WARNING),
        _general("spec.unfixable_issues", "spec", Severity.ERROR),
        _general("spec.undefined_levels", "spec", Severity.INFO),
        _general("spec.hierarchy_levels", "spec", Severity.WARNING),
        _general("spec.structural_orphans", "spec", Severity.ERROR),
        _general("spec.format_rules", "spec", Severity.ERROR),
        _general("spec.hash_integrity", "spec", Severity.WARNING),
        _general("spec.changelog_present", "spec", Severity.ERROR),
        _general("spec.changelog_current", "spec", Severity.ERROR),
        _general("spec.changelog_format", "spec", Severity.ERROR),
        _general("spec.index_current", "spec", Severity.WARNING),
        _general("spec.no_cycles", "spec", Severity.ERROR),
        _named(
            "spec.no_assertions",
            "spec",
            Severity.WARNING,
            "rules",
            "format",
            "no_assertions_severity",
        ),
        # -- references --------------------------------------------------
        _named("references.malformed", "references", Severity.WARNING, *_REFERENCES, "malformed"),
        _named(
            "references.unknown_namespace",
            "references",
            Severity.INFO,
            *_REFERENCES,
            "unknown_namespace",
        ),
        _named(
            "references.unknown_requirement",
            "references",
            Severity.ERROR,
            *_REFERENCES,
            "unknown_requirement",
        ),
        _named(
            "references.unknown_assertion",
            "references",
            Severity.ERROR,
            *_REFERENCES,
            "unknown_assertion",
        ),
        _named("references.forbidden", "references", Severity.ERROR, *_REFERENCES, "forbidden"),
        _named(
            "references.keyword_form", "references", Severity.WARNING, *_REFERENCES, "keyword_form"
        ),
        _named(
            "references.identifier_form",
            "references",
            Severity.WARNING,
            *_REFERENCES,
            "identifier_form",
        ),
        _named("references.undeclared", "references", Severity.WARNING, *_REFERENCES, "undeclared"),
        # -- code --------------------------------------------------------
        _general("code.unlinked", "code", Severity.INFO),
        _general("code.code_tested", "code", Severity.INFO),
        _general("code.whole_req_only_coverage", "code", Severity.INFO),
        _general("code.implemented", "code", Severity.ERROR),
        _named(
            "code.no_traceability",
            "code",
            Severity.WARNING,
            "rules",
            "format",
            "no_traceability_severity",
        ),
        # -- tests -------------------------------------------------------
        _general("tests.unlinked", "tests", Severity.INFO),
        _general("tests.results", "tests", Severity.WARNING),
        _general("tests.results_stale", "tests", Severity.WARNING),
        _general("tests.unmatched_results", "tests", Severity.WARNING),
        _general("tests.tested", "tests", Severity.ERROR),
        _general("tests.verified", "tests", Severity.ERROR),
        _general("tests.lcov_tested", "tests", Severity.ERROR),
        _named(
            "tests.uncredited_evidence",
            "tests",
            Severity.ERROR,
            "rules",
            "coverage",
            "uncredited_evidence",
        ),
        _named(
            "tests.external",
            "tests",
            Severity.WARNING,
            "rules",
            "coverage",
            "external_test_failure",
        ),
        # -- uat ---------------------------------------------------------
        _general("uat.results", "uat", Severity.WARNING),
        _general("uat.uat_coverage", "uat", Severity.ERROR),
        _general("uat.uat_verified", "uat", Severity.ERROR),
        # -- terms -------------------------------------------------------
        _named("terms.duplicates", "terms", Severity.ERROR, *_TERMS, "duplicate"),
        _named("terms.undefined", "terms", Severity.WARNING, *_TERMS, "undefined"),
        _named("terms.unmarked", "terms", Severity.WARNING, *_TERMS, "unmarked"),
        _named("terms.unused", "terms", Severity.WARNING, *_TERMS, "unused"),
        _named("terms.bad_definition", "terms", Severity.ERROR, *_TERMS, "bad_definition"),
        _named("terms.collection_empty", "terms", Severity.WARNING, *_TERMS, "collection_empty"),
        _named("terms.canonical_form", "terms", Severity.WARNING, *_TERMS, "canonical_form"),
    ]
    # A source node citing a requirement whose status carries a role follows
    # the same setting as a reference that reached that class: one setting,
    # one question ("how much does this project mind a retired target").
    for category in ("code", "tests"):
        for role, default in (
            ("retired", Severity.WARNING),
            ("provisional", Severity.INFO),
            ("aspirational", Severity.INFO),
        ):
            rules.append(
                _named(
                    f"{category}.{role}_references",
                    category,
                    default,
                    *_REFERENCES,
                    role,
                )
            )
    # A remedy recorded for a name no rule declares is a remedy no finding can
    # ever carry, so it is refused here rather than ignored.
    declared = {r.name for r in rules}
    stray = sorted(set(_REMEDIES) - declared)
    if stray:
        raise ValueError(
            f"_REMEDIES names checks that are not registered: {', '.join(stray)}. "
            f"Every remedy must belong to a registered check."
        )
    # Defaults are stored as the plain strings a configuration writes -- a
    # `Severity` member stringifies to its member name, not its value.
    return {
        r.name: CheckRule(
            r.name,
            r.category,
            Severity(r.default).value,
            r.path,
            _REMEDIES.get(r.name, NO_KNOWN_REMEDY),
        )
        for r in rules
    }


REGISTRY: dict[str, CheckRule] = _registry()


def is_registered(check_name: str) -> bool:
    """Whether a check name has a registered category and severity."""
    return check_name in REGISTRY


def _lookup(container: Any, key: str) -> Any:
    """One step along a configuration path, over a dict or a model."""
    if container is None:
        return None
    if isinstance(container, dict):
        return container.get(key)
    return getattr(container, key, None)


# Implements: REQ-d00285-E
def severity_for(check_name: str, config: Any = None) -> str:
    """The severity a check's findings carry, from its registered category.

    Args:
        check_name: The name the check reports under.
        config: The project configuration -- a loaded dict or the validated
            model. ``None`` means "nothing configured", which yields the
            registered default.

    Returns:
        One of `SEVERITY_VALUES`.

    Raises:
        KeyError: If the check name is not registered. A finding outside the
            registry is a finding whose severity no project can configure
            (REQ-d00285-D), so it is refused rather than defaulted.
        ValueError: If the configuration holds a value outside the vocabulary.
            The schema refuses those when the configuration is read
            (REQ-d00212-V); reaching one here means the value bypassed it.
    """
    try:
        rule = REGISTRY[check_name]
    except KeyError:
        raise KeyError(
            f"{check_name!r} is not a registered check. Every finding must fall in a "
            f"category whose severity a project can configure -- register it in "
            f"elspais.utilities.findings.REGISTRY."
        ) from None

    if config is None:
        return rule.default

    value: Any = config
    for key in rule.path:
        value = _lookup(value, key)
        if value is None:
            return rule.default

    if not isinstance(value, str) or value not in SEVERITY_VALUES:
        raise ValueError(
            f"{'.'.join(rule.path)} is {value!r}, which is not a severity. "
            f"The severities are: {', '.join(SEVERITY_VALUES)}."
        )
    return value


# Implements: REQ-d00285-B
def remedy_for(check_name: str) -> str:
    """The action that resolves what a check reports.

    Args:
        check_name: The name the check reports under.

    Returns:
        The remedy, or `NO_KNOWN_REMEDY` where none is known. Never empty: a
        finding names the absence of a remedy rather than staying silent about
        it.

    Raises:
        KeyError: If the check name is not registered, for the reason
            `severity_for` refuses one -- an unregistered name is outside what
            a project can configure and outside what a reader can be told.
    """
    try:
        return REGISTRY[check_name].remedy
    except KeyError:
        raise KeyError(
            f"{check_name!r} is not a registered check. Register it in "
            f"elspais.utilities.findings.REGISTRY so its findings can name a remedy."
        ) from None
