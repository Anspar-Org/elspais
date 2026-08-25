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

A check name that carries no setting of its own is configured under
``[rules.severity]``, keyed by the check name -- which is what keeps every
finding inside the settings a project can reach.

The registry is also where a check's REMEDY lives: the action a reader takes
to resolve what it reports. It belongs here rather than in a table the text
renderer consults, because a render-time table reaches only the format that
consults it, and a finding that names its remedy in one format and not another
is two different findings to two readers (REQ-d00285-B+C). A check for which no
action is known carries `NO_KNOWN_REMEDY`, which says so rather than saying
nothing.

It is where a check's DESCRIPTION lives for the same reason. The published
catalog of checks is rendered from this registry rather than written beside it,
so the catalog cannot name a check the tool does not run, or miss one it does
(REQ-d00286-E).
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
        description: What the check answers, in one sentence. The published
            catalog of checks is rendered from this field, so the catalog and
            the registry cannot name different sets or say different things
            about the same check (REQ-d00286-E).
    """

    name: str
    category: str
    default: str
    path: tuple[str, ...]
    remedy: str = NO_KNOWN_REMEDY
    description: str = ""


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
    "mcp.address": "elspais mcp env",
    "mcp.registration": "elspais mcp install",
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
    "spec.implements_resolve": "elspais unresolved",
    "spec.refines_resolve": "elspais unresolved",
    "spec.satisfies_resolve": "elspais unresolved",
    "spec.structural_orphans": "elspais -v checks --spec",
    "spec.hierarchy_levels": "elspais -v checks --spec",
    "spec.changelog_present": "elspais fix",
    "spec.changelog_current": "elspais fix -m 'Update changelog'",
    "spec.changelog_format": "elspais -v checks --spec",
    # -- references ------------------------------------------------------
    "references.malformed": "elspais unresolved",
    "references.unknown_namespace": "elspais unresolved",
    "references.unknown_requirement": "elspais unresolved",
    "references.unknown_assertion": "elspais unresolved",
    "references.forbidden": "elspais unresolved",
    "references.keyword_form": "elspais -v checks --spec",
    "references.identifier_form": "elspais -v checks --spec",
    "references.undeclared": "elspais -v checks --spec",
    # -- code ------------------------------------------------------------
    "code.uncited_file": "elspais uncited",
    "code.implemented": "elspais uncovered",
    # `code.no_traceability` is deliberately absent. It reports the files of
    # UNLINKED code nodes -- a citation that was read and reached no
    # requirement -- and no command lists that population: `elspais uncited`
    # lists files that cite nothing, which is the other population entirely,
    # and sending a reader there would hand them a list their file is not on.
    # The `{code,tests}.{role}_references` checks are deliberately absent: a
    # citation naming a requirement whose status carries a role is resolved by
    # editing the citation or the requirement, and no command does either.
    # Naming one would send a reader to a surface that reports the condition
    # again rather than resolving it.
    # -- tests -----------------------------------------------------------
    "tests.uncited_file": "elspais uncited",
    "tests.results": "elspais failing",
    "tests.results_stale": "elspais checks --run-tests",
    "tests.unmatched_results": "elspais -v checks --tests",
    "tests.tested": "elspais untested",
    "tests.verified": "elspais failing",
    "tests.uncredited_evidence": "elspais -v checks --tests",
    "tests.external": "elspais failing",
    # `tests.unbound_citation`, `tests.unrunnable_file` and
    # `tests.ingestion_fault` are deliberately absent, as
    # `code.unscanned_keyword_file` is: each is resolved by moving a citation
    # onto the test it describes, by repairing the artifact a target names, or
    # by editing the configuration that decides which files are scanned and
    # what can run them. No command does any of those, and naming one would
    # send a reader to a surface that reports the condition again rather than
    # resolving it.
    # -- uat -------------------------------------------------------------
    "uat.results": "elspais failing",
    "uat.uat_coverage": "elspais unvalidated",
    "uat.unvalidated": "elspais unvalidated",
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


# Implements: REQ-d00286-E
# What each check answers, in the one sentence the published catalog prints.
# It lives beside the registration rather than in the documentation because a
# hand-written catalog is correct on the day it is written and wrong on the day
# the tool gains one more check. Every registered check must have one, and a
# name here that no rule declares is refused when the registry is built -- the
# same guard `_REMEDIES` carries, in both directions.
_DESCRIPTIONS: dict[str, str] = {
    # -- config ------------------------------------------------------------
    "config.load": "The configuration file loads at all",
    "config.exists": "Verifies config file exists or using defaults",
    "config.syntax": "Validates TOML syntax is correct",
    "config.required_fields": "Ensures required sections present",
    "config.pattern_tokens": "Validates pattern template tokens",
    "config.hierarchy_rules": "Checks hierarchy rules consistency",
    "config.paths_exist": "Verifies spec directories exist",
    "config.project_type": "The declared project type is one the tool knows",
    "config.associated_section": "Every associate declaration reads (both a path and a namespace)",
    "mcp.address": "The address a client here would use reaches this working tree",
    "mcp.registration": "No client registration reaching this tree names a fixed address",
    # -- spec --------------------------------------------------------------
    "config.associate_paths": (
        "Validates that every federated repository — those declared here and those reached through "
        "an associate's own `[associates]` declarations — loads and contains spec files, reporting "
        "each failure with its path and reason"
    ),
    "config.no_requirements": "Flags when no requirements are found (likely config issue)",
    "config.governed_rules": (
        "Discloses each governed setting (coverage rules, reference severities, status roles) a "
        "federated member would judge by differently from the repository the run was invoked from "
        "— whether the member declared it or kept a default the invoking project overrode — naming "
        "the setting, both values and the member; never fails a run"
    ),
    "graph.build": "The traceability graph builds at all",
    "spec.parseable": "All spec files can be parsed",
    "spec.unknown_directive": (
        "Assertions opening with a parsing directive the tool does not recognize"
    ),
    "spec.no_duplicates": "No duplicate requirement IDs",
    "spec.implements_resolve": "All Implements: references resolve",
    "spec.refines_resolve": "All Refines: references resolve",
    "spec.satisfies_resolve": "All Satisfies: references resolve",
    "spec.needs_rewrite": (
        "Flags requirements that will be rewritten on next save (duplicate refs, stale hash)"
    ),
    "spec.unfixable_issues": "Issues `elspais fix` cannot repair, so a person has to",
    "spec.undefined_levels": (
        "No requirement carries a level the configuration does not define (such a requirement is "
        "still counted and grouped, so this discloses it rather than dropping it)"
    ),
    "spec.hierarchy_levels": "Requirements follow hierarchy rules",
    "spec.structural_orphans": "No nodes without a FILE ancestor (build bugs)",
    "spec.format_rules": "Requirements satisfy the enabled `[rules.format]` rules",
    "spec.hash_integrity": (
        "Flags Satisfies-linked requirements for review when their template hash is stale"
    ),
    "spec.changelog_present": (
        "Active requirements must have at least one changelog entry (when `changelog.present = "
        "true`)"
    ),
    "spec.changelog_current": (
        "Active requirements' latest changelog hash must match content hash (when "
        "`changelog.hash_current = true`)"
    ),
    "spec.changelog_format": (
        "Changelog entries must include required fields (reason, author, etc.)"
    ),
    "spec.index_current": "INDEX.md must be up to date with current requirements and journeys",
    "spec.no_cycles": "No cycle in the requirement hierarchy",
    "spec.no_assertions": "Requirements with no assertions (not testable)",
    # -- environment -------------------------------------------------------
    "local_toml.exists": "Reports whether a `.elspais.local.toml` developer override is present",
    "cross_repo.in_committed": (
        "Cross-project paths written into the shared, committed configuration (they belong in the "
        "local override)"
    ),
    "worktree.status": "The state of the git worktree the run was invoked from",
    "associate.paths_resolvable": "Every configured associate path resolves to a directory",
    "associate.configs_valid": "Every configured associate's own configuration loads",
    # -- docs --------------------------------------------------------------
    "docs.config_drift": (
        "Compares config schema sections against `docs/configuration.md`; reports undocumented and "
        "stale sections (runs in `elspais doctor`)"
    ),
    # -- references --------------------------------------------------------
    "references.malformed": "No reference fails to read as a reference at all",
    "references.unknown_namespace": "No reference names a target no configured repository claims",
    "references.unknown_requirement": (
        "No claimed reference names a requirement that repository does not hold"
    ),
    "references.unknown_assertion": (
        "No claimed reference names an assertion label its requirement lacks"
    ),
    "references.forbidden": (
        "No reference that reads and resolves has its relationship refused — a keyword the file "
        "kind may not use, or a target the list names twice"
    ),
    "references.keyword_form": (
        "No keyword is written in a non-canonical case, spacing, or markdown-emphasis form (never "
        "costs the edge its keyword introduces)"
    ),
    "references.identifier_form": (
        "No reference is spelled in a non-canonical form the configuration admits (never costs the "
        "relationship it names)"
    ),
    "references.undeclared": (
        "No comment opens with an identifier that no keyword introduces (produces no relationship)"
    ),
    # -- code --------------------------------------------------------------
    "code.uncited_file": (
        "A scanned code file that cites nothing -- no `# Implements:`, no `# Verifies:`. Not the "
        "same population as the unlinked NODES the graph API and the MCP `get_unlinked_nodes` "
        "tool answer about"
    ),
    "code.code_tested": "Line coverage over the implementation lines attributed to requirements",
    "code.whole_req_only_coverage": (
        "Coverage resting entirely on whole-requirement evidence, with no citation naming an "
        "assertion"
    ),
    "code.implemented": (
        "The `implemented` coverage dimension (CODE or child REQ covers assertions)"
    ),
    "code.no_traceability": (
        "Code files holding a citation that reaches no requirement -- the files of the unlinked "
        "CODE nodes (test files are covered separately by `tests.uncited_file`)"
    ),
    "code.unscanned_keyword_file": (
        "A file inside a scanned directory that the ignore configuration does not exclude, that "
        "the patterns declared for its kind do not select, and that carries a *Traceability* "
        "keyword anyway -- the citation was never read"
    ),
    "code.retired_references": (
        "Code referencing requirements with retired status (Deprecated, Superseded, Rejected)"
    ),
    "code.provisional_references": (
        "Code referencing requirements with provisional status (Draft, Proposed)"
    ),
    "code.aspirational_references": (
        "Code referencing requirements with aspirational status (Roadmap, Future, Idea)"
    ),
    # -- tests -------------------------------------------------------------
    "tests.uncited_file": (
        "A scanned test file in which no test cites anything -- either no test functions found, "
        "or no test in the file links to any requirement (a file with at least one linked test is "
        "not flagged). Not the same population as the unlinked NODES the graph API and the MCP "
        "`get_unlinked_nodes` tool answer about"
    ),
    "tests.results": "Test pass/fail status from JUnit XML or pytest JSON results",
    "tests.results_stale": "Test results older than the code they cover",
    "tests.unmatched_results": "Results matching no known test",
    "tests.tested": "The `tested` coverage dimension (TEST nodes linked to assertions)",
    "tests.verified": "The `verified` (Passing) coverage dimension",
    "tests.lcov_tested": "Line-coverage-derived credit keyed by assertion label",
    "tests.uncredited_evidence": (
        "Evidence naming an assertion its dimension does not count -- a test on an assertion "
        "nothing implements -- so it reaches no coverage figure"
    ),
    "tests.external": (
        "A test that failed and reaches no requirement, so nobody will find the failure through "
        "the spec"
    ),
    "tests.unbound_citation": (
        "A citation in a scanned test file that found no test to attach to -- it names assertions "
        "but sits where no test was declared, so no result can ever reach it; it contributes no "
        "coverage and is reported here instead"
    ),
    "tests.ingestion_fault": (
        "An artifact ingestion could not read, or could not read in full -- a results or coverage "
        "report that would not parse, one in a format no reporter reads, a reporter name that "
        "matches none, a results pattern that matched nothing, a coverage file that is not "
        "there, a target whose working directory leaves the repository, or a report that was "
        "read while part of what it says was declined. What went unread is absent from every "
        "figure, and absence reads as a zero"
    ),
    "tests.unrunnable_file": (
        "A scanned test file that no configured test target can execute, so what it verifies can "
        "raise the Tested figure while Passing has no way to move"
    ),
    "tests.retired_references": (
        "Tests referencing requirements with retired status (Deprecated, Superseded, Rejected)"
    ),
    "tests.provisional_references": (
        "Tests referencing requirements with provisional status (Draft, Proposed)"
    ),
    "tests.aspirational_references": (
        "Tests referencing requirements with aspirational status (Roadmap, Future, Idea)"
    ),
    # -- uat ---------------------------------------------------------------
    "uat.results": "Journey pass/fail status from a CSV results file",
    "uat.uat_coverage": (
        "The `uat_coverage` (UAT Covered) coverage dimension, counted over requirements at levels "
        "that set `expects_validation = true`. Levels without `expects_validation` are not "
        "counted; when no level expects validation the check passes trivially. Which requirements "
        "are unvalidated is reported by `uat.unvalidated`"
    ),
    "uat.unvalidated": (
        "A requirement at a level that sets `expects_validation = true` that no USER_JOURNEY "
        "validates, or that a journey names without naming its assertions -- reported by name, "
        "on the same verdict `elspais unvalidated` reaches"
    ),
    "uat.uat_verified": "The `uat_verified` (UAT Passed) coverage dimension",
    # -- terms -------------------------------------------------------------
    "terms.duplicates": "Same term defined in two locations",
    "terms.undefined": "Bold/italic token with no matching definition",
    "terms.unmarked": "Indexed term used without markup or with wrong markup",
    "terms.unused": "Defined term with zero references",
    "terms.bad_definition": "Term with blank or trivial definition text",
    "terms.collection_empty": "Collection term with no references",
    "terms.canonical_form": "Term references must use canonical casing and markup",
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
        _general("mcp.address", "environment", Severity.INFO),
        _general("mcp.registration", "environment", Severity.WARNING),
        _general("associate.configs_valid", "environment", Severity.ERROR),
        # -- spec --------------------------------------------------------
        _general("graph.build", "spec", Severity.ERROR),
        _general("spec.parseable", "spec", Severity.WARNING),
        _general("spec.unknown_directive", "spec", Severity.WARNING),
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
        _general("code.uncited_file", "code", Severity.INFO),
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
        # A file the scan declined to read is reported at info because the
        # probe is deliberately generous about what counts as a citation: a
        # keyword behind a comment marker in documentation prose reads the
        # same as a dropped citation in a grammar file, and the two cannot be
        # told apart without reading the file the scan just declined to read.
        # Under-reporting is the safe direction, and a false warning about
        # prose costs more than a quiet true finding about a citation.
        _general("code.unscanned_keyword_file", "code", Severity.INFO),
        # -- tests -------------------------------------------------------
        _general("tests.uncited_file", "tests", Severity.INFO),
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
        # A citation that bound to no test is reported at warning because the
        # condition is not always the author's doing: a pre-scan that does not
        # reach a language's declaration form produces it just as an
        # ill-placed comment does. What it credits is not a severity question
        # at all -- REQ-d00274-H withdraws the coverage whatever this says.
        _general("tests.unbound_citation", "tests", Severity.WARNING),
        # An artifact ingestion could not read, or could not read in full, is
        # reported at `warning`, which is "needs attention" -- the true claim,
        # and the whole of what the tool knows. `error` says "a defect", and that is not true of
        # every cause this name covers: a results pattern matching nothing is
        # the ordinary state of a checkout whose suite has not run yet, so an
        # `error` default would fail every build made before its tests and
        # push projects to turn the check off, ending the reporting outright.
        # Severity is also not what cures the harm here. What makes an
        # unreadable report indistinguishable from a suite that never ran is
        # that nobody was told WHICH artifact went unread; the findings name
        # each one with its path, its line and its target, and that is the
        # repair. A project for which an unread artifact IS a defect -- one
        # whose results are always present by the time the graph is built --
        # raises it to `error` under `[rules.severity]`.
        _general("tests.ingestion_fault", "tests", Severity.WARNING),
        # A target may legitimately carry no command -- the schema says so
        # ("omitted in CI", where the tests already ran) -- so a project whose
        # every target is ingest-only would be told at warning, on every file
        # it scans, about a configuration it chose. The fact is worth stating
        # and is not a defect, which is what `info` is for.
        _general("tests.unrunnable_file", "tests", Severity.INFO),
        # -- uat ---------------------------------------------------------
        _general("uat.results", "uat", Severity.WARNING),
        _general("uat.uat_coverage", "uat", Severity.ERROR),
        # A requirement no journey validates is reported at `warning` while the
        # dimension it belongs to fails at `error`. Two conditions, two
        # defaults (REQ-d00285-F): the dimension answers over every counted
        # assertion and a shortfall there is a defect in the figures, while a
        # named requirement awaiting a journey is work a reader schedules --
        # and a project that wants it to fail the run raises it here.
        _general("uat.unvalidated", "uat", Severity.WARNING),
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
    # Implements: REQ-d00286-E
    # A description is refused in BOTH directions: one for a check that is not
    # registered would appear in no catalog, and a registered check without one
    # would print an empty cell in the catalog rendered from this registry.
    stray_descriptions = sorted(set(_DESCRIPTIONS) - declared)
    if stray_descriptions:
        raise ValueError(
            f"_DESCRIPTIONS names checks that are not registered: "
            f"{', '.join(stray_descriptions)}. Every description must belong to a "
            f"registered check."
        )
    undescribed = sorted(declared - set(_DESCRIPTIONS))
    if undescribed:
        raise ValueError(
            f"These registered checks have no description: {', '.join(undescribed)}. "
            f"The published catalog of checks is rendered from _DESCRIPTIONS, so a "
            f"check without one would appear there with an empty cell."
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
            _DESCRIPTIONS[r.name],
        )
        for r in rules
    }


REGISTRY: dict[str, CheckRule] = _registry()


def is_registered(check_name: str) -> bool:
    """Whether a check name has a registered category and severity."""
    return check_name in REGISTRY


# Implements: REQ-d00285-C+F
# name: PRESETS
# use:  which checks each shortcut command lists.
# def:  command name -> the checks it selects, as a narrowing of the one
#       findings stream.
#
# `elspais unresolved`, `elspais errors` and `elspais uncited` are not reports
# of their own. Each is `elspais checks` narrowed to the checks that answer one
# question, so a shortcut cannot say less about a finding than the report it is
# a view of -- which is what a second renderer, reading the same facts and
# rendering fewer of them, always ends up doing (REQ-d00285-C).
#
# A preset names CHECKS rather than a category, because a category is not the
# question. `references` holds the five fault classes AND the style and
# undeclared-reference checks, and a reader asking what does not resolve is not
# asking about spelling.
PRESETS: dict[str, tuple[str, ...]] = {
    # The five classes partition every reference that resolves to nothing: a
    # fault belongs to exactly one, so the listing counts distinct facts
    # (REQ-p00019-K). `spec.implements_resolve` and its two siblings answer
    # over the same population by another route and are deliberately NOT here:
    # under both, one unresolved target would be listed twice.
    "unresolved": (
        "references.malformed",
        "references.unknown_namespace",
        "references.unknown_requirement",
        "references.unknown_assertion",
        "references.forbidden",
    ),
    # What is wrong with a spec file itself, as opposed to what it points at.
    "errors": (
        "spec.parseable",
        "spec.format_rules",
        "spec.no_assertions",
        "spec.unfixable_issues",
    ),
    # Both read one predicate (`collect_uncited`), so the two checks and this
    # listing cannot report different sets.
    "uncited": (
        "code.uncited_file",
        "tests.uncited_file",
    ),
}


def preset_checks(preset: str) -> tuple[str, ...]:
    """The checks one shortcut command lists.

    Raises:
        KeyError: If no preset carries that name.
    """
    try:
        return PRESETS[preset]
    except KeyError:
        raise KeyError(
            f"{preset!r} is not a preset listing. The presets are: {', '.join(sorted(PRESETS))}."
        ) from None


def _check_presets() -> None:
    """Refuse a preset naming a check the tool does not run.

    A preset is resolved into a narrowing of the report, and a name the report
    never carries would narrow it to nothing while looking like a selection --
    the condition REQ-d00282-F refuses for a reader's own narrowing, applied to
    the one the tool ships.
    """
    for preset, names in PRESETS.items():
        stray = sorted(set(names) - set(REGISTRY))
        if stray:
            raise ValueError(
                f"The {preset!r} preset names checks that are not registered: {', '.join(stray)}."
            )


_check_presets()


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
